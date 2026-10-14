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

    def test_excluded_driver_match_ignores_case_and_whitespace(self):
        """An exact-string miss lets an excluded driver's claim pass - a
        missed exclusion, the error this check exists to prevent."""
        for spelling in ["excluded person", "EXCLUDED  PERSON", "Excluded Person"]:
            claim = _make_claim()
            claim.driver.name = spelling
            policy = _make_policy(excluded_drivers=["Excluded Person"])
            result = check_coverage(claim, policy)
            assert "excluded_driver" in result.exclusions_triggered, spelling

    def test_distinct_names_still_differ(self):
        claim = _make_claim()
        claim.driver.name = "Excluded Persons"
        policy = _make_policy(excluded_drivers=["Excluded Person"])
        result = check_coverage(claim, policy)
        assert "excluded_driver" not in result.exclusions_triggered

    def test_vehicle_mismatch(self):
        claim = _make_claim()
        claim.vehicle.registration_number = "B-99999"
        policy = _make_policy()
        result = check_coverage(claim, policy)
        assert result.is_covered is False
        assert "vehicle_mismatch" in result.exclusions_triggered

    def test_registration_match_ignores_case_and_separators(self):
        """Plates arrive from different systems with different spacing;
        denying a covered claim over 'a-12345' vs 'A-12345' is the worst
        error this component can make."""
        for plate in ["a-12345", "A 12345", "A12345", "a12345"]:
            claim = _make_claim()
            claim.vehicle.registration_number = plate
            policy = _make_policy()
            result = check_coverage(claim, policy)
            assert "vehicle_mismatch" not in result.exclusions_triggered, plate

    def test_different_registrations_still_mismatch(self):
        claim = _make_claim()
        claim.vehicle.registration_number = "A-12346"
        policy = _make_policy()
        result = check_coverage(claim, policy)
        assert "vehicle_mismatch" in result.exclusions_triggered

    def test_driver_key_normalises_for_claim_grouping(self):
        """The repeat-claims window groups claims by driver; grouping must not
        miss prior claims because a name was typed differently."""
        from src.scoring import driver_key

        assert driver_key("John  Smith") == driver_key("JOHN SMITH")
        assert driver_key("John Smith") != driver_key("John Smith Jr")

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

    def test_claim_predating_inception_is_not_called_a_new_policy(self):
        """A claim submitted before the policy started yields a negative age,
        which passed `< 30` and was narrated as "New policy (-42 days old)".
        Pre-inception is a coverage failure, not a fraud factor."""
        claim = _make_claim(submitted_at=datetime(2024, 8, 10))
        claim.repair_estimate.estimated_cost = 45000
        policy = _make_policy(policy_start_date=date(2024, 9, 23))  # age -44 days
        level, factors = score_fraud_risk(claim, policy=policy)
        assert not any("New policy" in f for f in factors), factors
        assert not any("days old" in f for f in factors), factors

    def test_repeated_claims(self):
        claim = _make_claim()
        other_claim = _make_claim()
        other_claim.claim_id = "TEST-002"
        other_claim.accident.date = datetime(2024, 9, 5)
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, other_claim])
        assert level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
        assert any("previous claim" in f for f in factors)

    def test_future_claims_are_not_previous_claims(self):
        # A claim dated after the current accident is not a previous claim.
        # The window used to be one-sided (`delta <= 90 days`), so a future
        # claim produced a negative delta and was counted as "previous".
        claim = _make_claim()  # accident 2024-09-10
        future = _make_claim()
        future.claim_id = "TEST-002"
        future.accident.date = datetime(2024, 9, 20)  # 10 days after
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, future])
        assert level == RiskLevel.LOW
        assert not any("previous claim" in f for f in factors)

    def test_claims_older_than_90_days_are_not_counted(self):
        claim = _make_claim()  # accident 2024-09-10
        old = _make_claim()
        old.claim_id = "TEST-002"
        old.accident.date = datetime(2024, 6, 1)  # 101 days before
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, old])
        assert level == RiskLevel.LOW
        assert not any("previous claim" in f for f in factors)

    def test_boundary_claims_at_90_days_are_counted(self):
        claim = _make_claim()  # accident 2024-09-10
        exactly = _make_claim()
        exactly.claim_id = "TEST-002"
        exactly.accident.date = datetime(2024, 6, 12)  # exactly 90 days before
        level, factors = score_fraud_risk(claim, all_claims_for_driver=[claim, exactly])
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


class TestNarrativeFinancials:
    """The narrative states figures a handler may act on, so the payout must
    respect the policy limit. It previously ignored max_sum_insured entirely:
    a AED 120,000 repair on a AED 100,000 policy was reported as a
    "Estimated Net Payout: AED 119,700", a figure the policy could never pay."""

    def test_payout_is_capped_at_sum_insured(self):
        claim = _make_claim()
        claim.repair_estimate.estimated_cost = 120000  # excess 500, sum insured 300000
        policy = _make_policy(max_sum_insured=100000)
        result = triage_claim(claim, policy)
        assert "**Estimated Net Payout:** AED 100,000" in result.narrative
        assert "Capped at the policy sum insured" in result.narrative

    def test_uncapped_payout_is_repair_minus_excess(self):
        claim = _make_claim()
        claim.repair_estimate.estimated_cost = 5000  # excess 500
        policy = _make_policy(max_sum_insured=300000)
        result = triage_claim(claim, policy)
        assert "**Estimated Net Payout:** AED 4,500" in result.narrative
        assert "Capped at the policy sum insured" not in result.narrative

    def test_payout_never_negative(self):
        claim = _make_claim()
        claim.repair_estimate.estimated_cost = 300  # below the 500 excess
        policy = _make_policy()
        result = triage_claim(claim, policy)
        assert "**Estimated Net Payout:** AED 0" in result.narrative

    def test_uncovered_claim_states_no_payout(self):
        # A denied claim must not quote a payout figure - a handler skimming
        # the narrative would otherwise reserve against a claim the engine
        # recommends investigating for denial.
        claim = _make_claim()
        claim.driver.name = "Excluded Person"
        policy = _make_policy(excluded_drivers=["Excluded Person"])
        result = triage_claim(claim, policy)
        assert result.coverage.is_covered is False
        assert (
            "**Estimated Net Payout:** Not estimated - coverage checks did not pass."
            in result.narrative
        )
        assert "AED 4,500" not in result.narrative

    def test_third_party_claim_states_no_payout_from_own_repair(self):
        # Third-party cover responds to liability to other parties; the
        # own-vehicle repair estimate is not a basis for a payout figure.
        claim = _make_claim()
        policy = _make_policy(coverage_type=CoverageType.THIRD_PARTY)
        result = triage_claim(claim, policy)
        assert result.coverage.is_covered is True
        assert "**Estimated Net Payout:** Not estimated from this figure" in result.narrative
        assert "liability to other parties" in result.narrative


class TestMockData:
    def test_generates_labelled_claims(self):
        from src.mock_data import EXPECTED_RECOMMENDATIONS, generate_claims

        claims = generate_claims()
        assert len(claims) == len(EXPECTED_RECOMMENDATIONS) == 38

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


class TestGroundTruth:
    """The dataset carries its own labels: every claim has an expected
    recommendation in EXPECTED_RECOMMENDATIONS. These tests assert the engine
    reproduces them, so a silent behaviour change fails here instead of
    shipping."""

    def _triage_all(self):
        from src.mock_data import EXPECTED_RECOMMENDATIONS, POLICIES, generate_claims

        policy_map = {p.policy_number: p for p in POLICIES}
        claims = generate_claims()
        results = {}
        for claim in claims:
            policy = policy_map[claim.policy_number]
            driver_claims = [c for c in claims if c.driver.name == claim.driver.name]
            results[claim.claim_id] = triage_claim(claim, policy, driver_claims)
        return results, EXPECTED_RECOMMENDATIONS

    def test_every_claim_matches_its_label(self):
        results, expected = self._triage_all()
        mismatches = [
            (cid, exp, results[cid].recommendation.value)
            for cid, exp in expected.items()
            if results[cid].recommendation.value != exp
        ]
        assert mismatches == [], f"engine/label mismatches: {mismatches}"

    def test_every_coverage_rule_fires_at_least_once(self):
        results, _ = self._triage_all()
        fired = {e for r in results.values() for e in r.coverage.exclusions_triggered}
        # Every exclusion the coverage checker can emit must appear in the
        # dataset, otherwise that branch ships unverified.
        assert fired == {
            "policy_not_active",
            "excluded_driver",
            "vehicle_mismatch",
            "rental_use",
            "ride_hailing_use",
            "taxi_use",
            "delivery_use",
        }

    def test_every_fraud_rule_fires_at_least_once(self):
        results, _ = self._triage_all()
        factors = " | ".join(f for r in results.values() for f in r.scoring.fraud_risk_factors)
        assert "previous claim" in factors  # repeat-claims window
        assert "New policy" in factors  # recently-purchased policy indicator
        assert "inconsistency" in factors  # story-inconsistency keywords
        assert "documentation" in factors  # thin-documentation indicator

    def test_every_complexity_rule_fires_at_least_once(self):
        results, _ = self._triage_all()
        factors = " | ".join(f for r in results.values() for f in r.scoring.complexity_factors)
        assert "Multiple vehicles" in factors
        assert "Injury" in factors
        assert "Liability disputed" in factors
        assert "total loss" in factors  # >70% repair-to-value tier
        assert "of vehicle value" in factors  # 40-70% tier
        assert "Young driver" in factors

    def test_third_party_advisory_is_a_note_not_a_denial(self):
        results, _ = self._triage_all()
        r = results["CLM-033"]
        assert r.coverage.is_covered is True
        assert any("Third-party policy" in n for n in r.coverage.notes)
        assert r.recommendation == Recommendation.FAST_TRACK

    def test_negative_controls_stay_covered(self):
        """The two defect-regression controls: a delivery word on a
        rental-excluding policy, and a new policy with a low-value claim,
        must not trigger their indicators."""
        results, _ = self._triage_all()
        assert results["CLM-030"].coverage.is_covered is True
        assert results["CLM-030"].coverage.exclusions_triggered == []
        assert not any("New policy" in f for f in results["CLM-037"].scoring.fraud_risk_factors)
