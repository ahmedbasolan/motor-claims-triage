"""Tests for motor claims triage core logic."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime

from src.coverage import check_coverage
from src.models import (
    AccidentDetails,
    Claim,
    CoverageType,
    DriverDetails,
    Policy,
    Recommendation,
    RepairEstimate,
    RiskLevel,
    VehicleDetails,
)
from src.recommendation import generate_recommendation
from src.scoring import score_complexity, score_fraud_risk
from src.triage import triage_claim


def _make_claim(**overrides) -> Claim:
    defaults = {
        "claim_id": "TEST-001",
        "policy_number": "POL-TEST",
        "vehicle": VehicleDetails(
            make="Toyota", model="Camry", year=2022,
            registration_number="A-12345", estimated_value=85000,
        ),
        "driver": DriverDetails(name="Test Driver", age=30, license_tenure_years=5),
        "accident": AccidentDetails(
            date=datetime(2024, 9, 10),
            location="Dubai, UAE",
            description="Rear-ended at traffic light",
            num_vehicles_involved=1,
            injury_reported=False,
            liability_disputed=False,
        ),
        "documents": [],
        "repair_estimate": RepairEstimate(
            estimated_cost=5000, garage_name="Test Garage", items=["Repair"]
        ),
        "submitted_at": datetime(2024, 9, 1),
    }
    defaults.update(overrides)
    return Claim(**defaults)


def _make_policy(**overrides) -> Policy:
    defaults = {
        "policy_number": "POL-TEST",
        "coverage_type": CoverageType.COMPREHENSIVE,
        "excess": 500,
        "max_sum_insured": 300000,
        "excluded_drivers": [],
        "excluded_uses": [],
        "policy_start_date": date(2024, 1, 1),
        "policy_end_date": date(2025, 1, 1),
        "vehicle_registration": "A-12345",
    }
    defaults.update(overrides)
    return Policy(**defaults)


class TestCoverage:
    def test_clear_coverage(self):
        claim = _make_claim()
        policy = _make_policy()
        result = check_coverage(claim, policy)
        assert result.is_covered is True
        assert len(result.exclusions_triggered) == 0

    def test_excluded_driver(self):
        claim = _make_claim()
        claim.driver.name = "Excluded Person"
        policy = _make_policy(excluded_drivers=["Excluded Person"])
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "excluded_driver" in result.exclusions_triggered

    def test_vehicle_mismatch(self):
        claim = _make_claim()
        claim.vehicle.registration_number = "B-99999"
        policy = _make_policy()
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "vehicle_mismatch" in result.exclusions_triggered

    def test_policy_expired(self):
        claim = _make_claim()
        claim.accident.date = datetime(2026, 6, 1)
        policy = _make_policy()
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "policy_not_active" in result.exclusions_triggered

    def test_ride_hailing_exclusion(self):
        claim = _make_claim()
        claim.accident.description = "Accident while doing ride-hailing"
        policy = _make_policy(excluded_uses=["ride-hailing"])
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "ride_hailing_use" in result.exclusions_triggered


class TestScoring:
    def test_low_complexity(self):
        claim = _make_claim()
        level, factors = score_complexity(claim)
        assert level == RiskLevel.LOW
        assert len(factors) == 0

    def test_high_complexity_multiple_vehicles(self):
        claim = _make_claim()
        claim.accident.num_vehicles_involved = 3
        claim.accident.injury_reported = True
        claim.accident.liability_disputed = True
        level, factors = score_complexity(claim)
        assert level == RiskLevel.HIGH
        assert len(factors) >= 3

    def test_low_fraud_risk(self):
        claim = _make_claim()
        level, factors = score_fraud_risk(claim)
        assert level == RiskLevel.LOW

    def test_fraud_new_policy_high_claim(self):
        claim = _make_claim()
        claim.submitted_at = datetime(2024, 8, 20)  # 14 days before accident
        claim.repair_estimate.estimated_cost = 50000
        level, factors = score_fraud_risk(claim)
        assert level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert any("New policy" in f for f in factors)

    def test_repeated_claims(self):
        claim = _make_claim()
        other_claim = _make_claim()
        other_claim.claim_id = "TEST-002"
        other_claim.accident.date = datetime(2024, 9, 5)
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, other_claim])
        assert level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert any("previous claim" in f for f in factors)

    def test_combined_fraud_indicators_reach_high(self):
        claim = _make_claim()
        claim.submitted_at = datetime(2024, 8, 20)  # 14 days old policy
        claim.repair_estimate.estimated_cost = 50000
        other_claim = _make_claim()
        other_claim.claim_id = "TEST-002"
        other_claim.accident.date = datetime(2024, 9, 5)
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, other_claim])
        assert level == RiskLevel.HIGH
        assert len(factors) >= 2


class TestRecommendation:
    def test_fast_track(self):
        from src.models import CoverageCheckResult, ScoringResult
        coverage = CoverageCheckResult(
            is_covered=True, coverage_type=CoverageType.COMPREHENSIVE,
            excess_amount=500, max_payout=300000,
        )
        scoring = ScoringResult(
            complexity_score=RiskLevel.LOW,
            fraud_risk_score=RiskLevel.LOW,
            overall_risk=RiskLevel.LOW,
        )
        assert generate_recommendation(coverage, scoring) == Recommendation.FAST_TRACK

    def test_investigate_high_fraud(self):
        from src.models import CoverageCheckResult, ScoringResult
        coverage = CoverageCheckResult(
            is_covered=True, coverage_type=CoverageType.COMPREHENSIVE,
            excess_amount=500, max_payout=300000,
        )
        scoring = ScoringResult(
            complexity_score=RiskLevel.LOW,
            fraud_risk_score=RiskLevel.HIGH,
            overall_risk=RiskLevel.HIGH,
        )
        assert generate_recommendation(coverage, scoring) == Recommendation.INVESTIGATE

    def test_investigate_not_covered(self):
        from src.models import CoverageCheckResult, ScoringResult
        coverage = CoverageCheckResult(
            is_covered=False, coverage_type=CoverageType.COMPREHENSIVE,
            excess_amount=500, max_payout=300000,
            exclusions_triggered=["excluded_driver"],
        )
        scoring = ScoringResult(
            complexity_score=RiskLevel.LOW,
            fraud_risk_score=RiskLevel.LOW,
            overall_risk=RiskLevel.LOW,
        )
        assert generate_recommendation(coverage, scoring) == Recommendation.INVESTIGATE


class TestTriage:
    def test_full_triage(self):
        claim = _make_claim()
        policy = _make_policy()
        result = triage_claim(claim, policy)
        assert result.claim_id == "TEST-001"
        assert result.recommendation in [
            Recommendation.FAST_TRACK,
            Recommendation.STANDARD_REVIEW,
            Recommendation.INVESTIGATE,
        ]
        assert result.narrative is not None
        assert len(result.narrative) > 0

    def test_narrative_contains_key_sections(self):
        claim = _make_claim()
        policy = _make_policy()
        result = triage_claim(claim, policy)
        assert "Coverage:" in result.narrative
        assert "Complexity:" in result.narrative
        assert "Fraud Risk:" in result.narrative
        assert "Recommendation:" in result.narrative


class TestMockData:
    def test_generates_25_claims(self):
        from src.mock_data import generate_claims
        claims = generate_claims()
        assert len(claims) == 25

    def test_all_claims_have_valid_policies(self):
        from src.mock_data import POLICIES, generate_claims
        policy_map = {p.policy_number: p for p in POLICIES}
        claims = generate_claims()
        for claim in claims:
            assert claim.policy_number in policy_map

    def test_triage_all_claims(self):
        from src.mock_data import POLICIES, generate_claims
        policy_map = {p.policy_number: p for p in POLICIES}
        claims = generate_claims()
        for claim in claims:
            policy = policy_map[claim.policy_number]
            result = triage_claim(claim, policy)
            assert result.recommendation is not None
