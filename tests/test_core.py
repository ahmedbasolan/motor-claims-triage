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
            make="Toyota",
            model="Camry",
            year=2022,
            registration_number="A-12345",
            estimated_value=85000,
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

    def test_ride_hailing_alias_matches_platform_name(self):
        """The description may name the platform rather than the use case."""
        claim = _make_claim()
        claim.accident.description = "Driver was on an Uber shift when the crash happened"
        policy = _make_policy(excluded_uses=["ride_hailing"])
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "ride_hailing_use" in result.exclusions_triggered


class TestUseCaseExclusionsAreSpecific:
    """Regression: `... or policy.excluded_uses` made any non-empty exclusion
    list deny a claim for any use-case word, so a rental-only policy also denied
    delivery claims. Denying a covered claim is the worst error here."""

    def test_rental_policy_does_not_exclude_delivery(self):
        claim = _make_claim()
        claim.accident.description = "Delivery van rear-ended a car"
        policy = _make_policy(excluded_uses=["rental"])
        result = check_coverage(claim, policy)
        assert result.is_covered is True, result.exclusions_triggered
        assert "delivery_use" not in result.exclusions_triggered

    def test_delivery_policy_does_not_exclude_rental(self):
        claim = _make_claim()
        claim.accident.description = "Rental car accident"
        policy = _make_policy(excluded_uses=["delivery"])
        result = check_coverage(claim, policy)
        assert result.is_covered is True, result.exclusions_triggered

    def test_ride_hailing_policy_does_not_exclude_taxi(self):
        claim = _make_claim()
        claim.accident.description = "Working as a taxi driver at the time"
        policy = _make_policy(excluded_uses=["ride_hailing"])
        result = check_coverage(claim, policy)
        assert result.is_covered is True, result.exclusions_triggered

    def test_taxi_policy_excludes_taxi(self):
        claim = _make_claim()
        claim.accident.description = "Working as a taxi driver at the time"
        policy = _make_policy(excluded_uses=["taxi"])
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "taxi_use" in result.exclusions_triggered

    def test_matching_use_is_still_excluded(self):
        claim = _make_claim()
        claim.accident.description = "Vehicle was being used as a rental"
        policy = _make_policy(excluded_uses=["rental"])
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "rental_use" in result.exclusions_triggered

    def test_keyword_matching_respects_word_boundaries(self):
        """'uber' must not match inside an unrelated word."""
        claim = _make_claim()
        claim.accident.description = "Collision on a main road, no injuries"
        policy = _make_policy(excluded_uses=["ride_hailing"])
        result = check_coverage(claim, policy)
        assert result.is_covered is True

    def test_policy_with_excluded_uses_code_suffix(self):
        """Policies may carry the code form directly."""
        claim = _make_claim()
        claim.accident.description = "Accident while doing ride-hailing"
        policy = _make_policy(excluded_uses=["ride_hailing_use"])
        result = check_coverage(claim, policy)
        assert result.is_covered is False


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
        # A genuinely recently-purchased policy: started 14 days before the
        # claim was submitted. Previously this test set submitted_at 14 days
        # before the accident, which is a reporting lag of +14, not policy age,
        # so it passed for the wrong reason.
        claim = _make_claim(submitted_at=datetime(2024, 9, 10))
        claim.repair_estimate.estimated_cost = 50000
        policy = _make_policy(policy_start_date=date(2024, 8, 27))
        level, factors = score_fraud_risk(claim, policy=policy)
        assert level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert any("New policy" in f for f in factors)
        assert any("14 days old" in f for f in factors)

    def test_long_held_policy_is_not_called_new(self):
        """Regression: the indicator used the accident-to-submission gap, which
        is near zero for every ordinary claim, so any claim over AED 15,000 was
        reported as a new policy. A year-old policy must not trigger it."""
        claim = _make_claim(submitted_at=datetime(2024, 9, 10))
        claim.repair_estimate.estimated_cost = 62000
        policy = _make_policy(policy_start_date=date(2023, 9, 10))
        level, factors = score_fraud_risk(claim, policy=policy)
        assert not any("New policy" in f for f in factors), factors
        assert level == RiskLevel.LOW

    def test_new_policy_rule_is_skipped_without_a_policy(self):
        """The indicator cannot be evaluated without the policy, so it is
        skipped rather than guessed from claim dates."""
        claim = _make_claim(submitted_at=datetime(2024, 9, 10))
        claim.repair_estimate.estimated_cost = 62000
        level, factors = score_fraud_risk(claim)
        assert not any("New policy" in f for f in factors), factors

    def test_low_value_claim_on_new_policy_is_not_flagged(self):
        claim = _make_claim(submitted_at=datetime(2024, 9, 10))
        claim.repair_estimate.estimated_cost = 4000
        policy = _make_policy(policy_start_date=date(2024, 9, 1))
        level, factors = score_fraud_risk(claim, policy=policy)
        assert not any("New policy" in f for f in factors), factors

    def test_repeated_claims(self):
        claim = _make_claim()
        other_claim = _make_claim()
        other_claim.claim_id = "TEST-002"
        other_claim.accident.date = datetime(2024, 9, 5)
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, other_claim])
        assert level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert any("previous claim" in f for f in factors)

    def test_combined_fraud_indicators_reach_high(self):
        claim = _make_claim(submitted_at=datetime(2024, 9, 10))
        claim.repair_estimate.estimated_cost = 50000
        policy = _make_policy(policy_start_date=date(2024, 8, 27))
        other_claim = _make_claim()
        other_claim.claim_id = "TEST-002"
        other_claim.accident.date = datetime(2024, 9, 5)
        level, factors = score_fraud_risk(
            claim, all_claims_for_driver=[claim, other_claim], policy=policy
        )
        assert level == RiskLevel.HIGH
        assert len(factors) >= 2


class TestRecommendation:
    def test_fast_track(self):
        from src.models import CoverageCheckResult, ScoringResult

        coverage = CoverageCheckResult(
            is_covered=True,
            coverage_type=CoverageType.COMPREHENSIVE,
            excess_amount=500,
            max_payout=300000,
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
            is_covered=True,
            coverage_type=CoverageType.COMPREHENSIVE,
            excess_amount=500,
            max_payout=300000,
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
            is_covered=False,
            coverage_type=CoverageType.COMPREHENSIVE,
            excess_amount=500,
            max_payout=300000,
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
