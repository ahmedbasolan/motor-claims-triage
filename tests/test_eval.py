"""Tests for the calibration harness (eval/)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from eval.harness import evaluate, indicator_of, sensitivity
from eval.outcomes import ClaimOutcome, OutcomeSet
from src import scoring
from src.models import Recommendation


def _outcome(cid: str, **kw) -> ClaimOutcome:
    defaults = {"claim_id": cid, "handler_decision": Recommendation.STANDARD_REVIEW}
    defaults.update(kw)
    return ClaimOutcome(**defaults)


class TestOutcomeSchema:
    def test_duplicate_claim_ids_rejected(self):
        with pytest.raises(ValueError, match="Duplicate outcome"):
            OutcomeSet(outcomes=[_outcome("X-1"), _outcome("X-1")])

    def test_unknown_fields_are_rejected_not_ignored(self):
        """A typo'd field name must fail loudly. Pydantic's default is to
        ignore extras, which would turn 'fraud_confirmmed' into 'no verdict'
        - a silent data hole."""
        with pytest.raises(ValueError):
            ClaimOutcome(
                claim_id="X-1",
                handler_decision=Recommendation.FAST_TRACK,
                fraud_fully_proven=True,  # not a field
            )

    def test_unknown_fields_rejected_at_set_level_too(self):
        with pytest.raises(ValueError):
            OutcomeSet(outcomes=[], surprises=True)  # type: ignore[call-arg]

    def test_optional_fields_default_to_none(self):
        o = _outcome("X-1")
        assert o.fraud_confirmed is None
        assert o.amount_paid is None
        assert o.settled_on is None

    def test_by_claim_indexes(self):
        s = OutcomeSet(outcomes=[_outcome("A"), _outcome("B")])
        assert set(s.by_claim()) == {"A", "B"}


class TestIndicatorMapping:
    def test_every_scoring_factor_maps_to_an_indicator(self):
        """If scoring.py rewords a factor, this fails before the calibration
        report silently drops it into the unknown bucket."""
        factors = [
            "New policy (14 days old) with high claim AED 45,000",
            "3 previous claims in last 90 days for this driver",
            "One previous claim in last 90 days for this driver",
            "Potential inconsistency detected: location",
            "Limited documentation for high-value repair estimate",
        ]
        for f in factors:
            assert indicator_of(f) is not None, f

    def test_leading_count_does_not_break_repeat_claims(self):
        # Regression: the first implementation used startswith, and the
        # repeat-claims factor leads with a count, so it never matched.
        assert indicator_of("2 previous claims in last 90 days for this driver") == "repeat_claims"

    def test_unknown_factor_returns_none(self):
        assert indicator_of("Some future factor") is None


class TestEvaluate:
    def test_agreement_counted(self):
        from src.mock_data import generate_claims

        claims = generate_claims()
        # Handler always agrees with whatever the engine decides -> full
        # agreement, computed by re-reading the engine inside evaluate().
        outcomes = {}
        for c in claims:
            outcomes[c.claim_id] = _outcome(c.claim_id)  # placeholder, fixed below

        # Build outcomes that match the engine exactly.
        from eval.harness import _triage_all

        results = _triage_all(claims)
        for cid, r in results.items():
            outcomes[cid] = _outcome(cid, handler_decision=r.recommendation)

        report = evaluate(outcomes, claims)
        assert report.total_with_outcomes == len(claims)
        disagree = [k for k in report.agreement if k[0] != k[1]]
        assert disagree == []

    def test_precision_and_recall(self):
        """Three outcomes against the full dataset. The full dataset is the
        triage *context*: CLM-007's repeat-claims indicator needs the driver's
        other claims present, so passing a 3-claim slice would silently strip
        the history and the indicator could never fire."""
        from src.mock_data import generate_claims

        claims = generate_claims()
        # CLM-007 is the investigate claim carrying '2 previous claims'
        # (repeat indicator). Verify that on full context before asserting.
        from eval.harness import _triage_all

        results = _triage_all(claims)
        fired_7 = results["CLM-007"].scoring.fraud_risk_factors
        assert any("previous claim" in f for f in fired_7), fired_7

        outcomes = {
            "CLM-001": _outcome("CLM-001", fraud_confirmed=False),
            "CLM-002": _outcome("CLM-002", fraud_confirmed=False),
            "CLM-007": _outcome("CLM-007", fraud_confirmed=True),
        }
        report = evaluate(outcomes, claims)
        st = report.indicators["repeat_claims"]
        # All three claims carry the repeat indicator (same driver group);
        # only CLM-007 is confirmed fraud.
        assert st.fired == 3
        assert st.confirmed == 1
        assert st.precision == pytest.approx(1 / 3)
        assert st.recall == 1.0
        assert report.fraud_confirmed == 1
        assert report.fraud_cleared == 2

    def test_never_investigated_is_unknown_not_cleared(self):
        from src.mock_data import generate_claims

        claims = [c for c in generate_claims() if c.claim_id == "CLM-001"]
        report = evaluate({"CLM-001": _outcome("CLM-001")}, claims)
        assert report.fraud_unknown == 1
        assert report.fraud_cleared == 0

    def test_outcomes_for_missing_claims_are_skipped(self):
        from src.mock_data import generate_claims

        claims = [c for c in generate_claims() if c.claim_id == "CLM-001"]
        report = evaluate({"NOPE": _outcome("NOPE")}, claims)
        assert report.total_with_outcomes == 0
        assert any("NOPE" in s for s in report.skipped)


class TestSensitivity:
    def test_threshold_is_restored_after_sweep(self):
        """The sweep mutates scoring module state; it must not leak."""
        before = scoring.NEW_POLICY_DAYS
        sensitivity("NEW_POLICY_DAYS")
        assert scoring.NEW_POLICY_DAYS == before

    def test_restored_even_if_a_value_raises(self):
        before = scoring.FR_HIGH_AT
        with pytest.raises(ValueError):
            sensitivity("FR_HIGH_AT", values=[5, "not-an-int"])  # type: ignore[list-item]
        assert scoring.FR_HIGH_AT == before

    def test_baseline_row_reports_zero_changes(self):
        rows = sensitivity("CX_HIGH_AT")
        baseline_row = next(r for r in rows if r[0] == scoring.CX_HIGH_AT)
        assert baseline_row[2] == 0

    def test_sweep_covers_every_claim(self):
        from src.mock_data import generate_claims

        rows = sensitivity("CX_HIGH_AT")
        for _, counts, _ in rows:
            assert sum(counts.values()) == len(generate_claims())


class TestDemoOutcomes:
    def test_demo_file_validates(self):
        import json
        from pathlib import Path

        path = Path(__file__).parent.parent / "eval" / "demo_outcomes.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        s = OutcomeSet.model_validate(raw)
        assert len(s.outcomes) == 38

    def test_demo_file_is_labelled_synthetic(self):
        import json
        from pathlib import Path

        path = Path(__file__).parent.parent / "eval" / "demo_outcomes.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        s = OutcomeSet.model_validate(raw)
        assert s.comment and "SYNTHETIC" in s.comment
