"""Integration tests for the HTTP surface (api.py).

The unit tests verify the engine; these verify the endpoints. The load-bearing
test is test_every_labelled_claim_triages_to_its_ground_truth: each of the 38
labelled claims round-trips through POST /triage_claim/{id} and the response
must carry the label from EXPECTED_RECOMMENDATIONS. A defect introduced only
in the API layer - wrong driver-context wiring, a missing claim, a serialisation
that drops the recommendation - fails here even when the engine is fine.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from api import app
from eval.outcomes import ClaimOutcome, OutcomeSet
from motor_claims.mock_data import EXPECTED_RECOMMENDATIONS
from motor_claims.models import Recommendation

client = TestClient(app)


class TestRoot:
    def test_root_lists_endpoints(self):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["service"] == "Motor Claims Triage API"
        assert "triage" in body["endpoints"]


class TestClaimsEndpoints:
    def test_list_claims_returns_all_mock_claims(self):
        r = client.get("/claims")
        assert r.status_code == 200
        claims = r.json()
        assert len(claims) == 38
        # Shape: the summary fields the UI/clients rely on.
        assert {"claim_id", "policy_number", "driver", "repair_cost"} <= set(claims[0])

    def test_get_claim_found(self):
        r = client.get("/claims/CLM-001")
        assert r.status_code == 200
        assert r.json()["claim_id"] == "CLM-001"

    def test_get_claim_404(self):
        r = client.get("/claims/CLM-999")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"]

    def test_list_policies(self):
        r = client.get("/policies")
        assert r.status_code == 200
        policies = r.json()
        assert len(policies) == 8
        assert all("policy_number" in p for p in policies)


class TestTriageEndpoints:
    def test_every_labelled_claim_triages_to_its_ground_truth(self):
        """Round-trip all 38 claims through the API and compare against the
        labels the engine tests assert. The HTTP layer must agree with the
        engine, not merely return 200."""
        mismatches = []
        for cid, expected in EXPECTED_RECOMMENDATIONS.items():
            r = client.post(f"/triage_claim/{cid}")
            if r.status_code != 200:
                mismatches.append(f"{cid}: HTTP {r.status_code}")
                continue
            got = r.json()["recommendation"]
            if got != expected:
                mismatches.append(f"{cid}: expected {expected}, got {got}")
        assert mismatches == []

    def test_triage_all_returns_every_claim(self):
        r = client.get("/triage_all")
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 38
        assert {x["claim_id"] for x in results} == set(EXPECTED_RECOMMENDATIONS)

    def test_triage_existing_claim_404(self):
        r = client.post("/triage_claim/CLM-999")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"]

    def test_triage_new_claim_accepted(self):
        """POST a claim body (fetched from GET /claims/{id}) to the
        ad-hoc triage endpoint; it must produce the same recommendation as
        triaging the same claim by id."""
        claim = client.get("/claims/CLM-001").json()
        r = client.post("/triage_claim", json=claim)
        assert r.status_code == 200
        by_id = client.post("/triage_claim/CLM-001").json()
        assert r.json()["recommendation"] == by_id["recommendation"]

    def test_triage_new_claim_unknown_policy_400(self):
        claim = client.get("/claims/CLM-001").json()
        claim["policy_number"] = "POL-DOES-NOT-EXIST"
        r = client.post("/triage_claim", json=claim)
        assert r.status_code == 400
        assert "not found" in r.json()["detail"]

    def test_malformed_claim_body_422(self):
        """Pydantic validation must reject an incomplete claim rather than
        let it reach the engine with None fields."""
        r = client.post("/triage_claim", json={"claim_id": "X-1"})
        assert r.status_code == 422


class TestResponseContract:
    def test_triage_result_carries_explainability_fields(self):
        """The CBUAE-facing claim is explainable decisions; the response must
        carry the reasoning, not just the verdict: the narrative plus the
        factor lists and coverage check behind it."""
        r = client.post("/triage_claim/CLM-001")
        body = r.json()
        for key in ("claim_id", "recommendation", "narrative", "coverage", "scoring"):
            assert key in body
        assert isinstance(body["narrative"], str) and body["narrative"]
        scoring = body["scoring"]
        assert "complexity_factors" in scoring and "fraud_risk_factors" in scoring

    def test_recommendation_is_one_of_the_three(self):
        r = client.get("/triage_all")
        allowed = {"fast_track", "standard_review", "investigate"}
        assert {x["recommendation"] for x in r.json()} <= allowed


class TestFeedbackEndpoint:
    """POST /feedback captures what handlers actually did, in the exact
    schema the calibration harness loads (eval.outcomes.ClaimOutcome)."""

    def test_stored_record_is_harness_shaped_and_engine_rec_frozen(self, tmp_path, monkeypatch):
        path = tmp_path / "captured.jsonl"
        monkeypatch.setenv("FEEDBACK_PATH", str(path))
        r = client.post(
            "/feedback",
            json={
                "claim_id": "CLM-007",
                "handler_decision": "fast_track",
                "amount_paid": 12000.5,
                "settled_on": "2024-10-02",
                "notes": "Settled quickly.",
            },
        )
        assert r.status_code == 201
        body = r.json()
        # The engine's own rec for this claim rides along, for agreement later
        # (CLM-007 is the engine's investigate case - ground truth restated).
        assert body["engine_recommendation"] == "investigate"
        # On disk: one ClaimOutcome per line, loadable by the harness as-is.
        record = ClaimOutcome.model_validate_json(path.read_text(encoding="utf-8").strip())
        assert record.handler_decision == Recommendation.FAST_TRACK
        assert record.amount_paid == 12000.5
        assert record.settled_on == date(2024, 10, 2)
        assert record.notes == "Settled quickly."

    def test_unknown_claim_ids_are_accepted(self, tmp_path, monkeypatch):
        """Partner extracts use the partner's own deidentified IDs; the
        harness joins on ID only, so capture must not require demo IDs."""
        monkeypatch.setenv("FEEDBACK_PATH", str(tmp_path / "captured.jsonl"))
        r = client.post(
            "/feedback", json={"claim_id": "PARTNER-42", "handler_decision": "standard_review"}
        )
        assert r.status_code == 201
        assert r.json()["engine_recommendation"] is None

    def test_duplicate_claim_id_is_rejected_not_overwritten(self, tmp_path, monkeypatch):
        """OutcomeSet rejects two outcomes per claim; the capture endpoint
        keeps that invariant at write time instead of at load time."""
        path = tmp_path / "captured.jsonl"
        monkeypatch.setenv("FEEDBACK_PATH", str(path))
        first = client.post(
            "/feedback", json={"claim_id": "CLM-001", "handler_decision": "fast_track"}
        )
        second = client.post(
            "/feedback", json={"claim_id": "CLM-001", "handler_decision": "investigate"}
        )
        assert first.status_code == 201
        assert second.status_code == 409
        assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    def test_extra_field_is_rejected_silently_dropped_nothing(self, tmp_path, monkeypatch):
        """ClaimOutcome forbids extras: a typo'd field name must 422, not
        vanish into a record that looks complete."""
        monkeypatch.setenv("FEEDBACK_PATH", str(tmp_path / "captured.jsonl"))
        r = client.post(
            "/feedback",
            json={"claim_id": "CLM-001", "handler_decision": "fast_track", "handlername": "oops"},
        )
        assert r.status_code == 422

    def test_missing_handler_decision_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FEEDBACK_PATH", str(tmp_path / "captured.jsonl"))
        r = client.post("/feedback", json={"claim_id": "CLM-001"})
        assert r.status_code == 422

    def test_capture_accumulates_into_a_harness_loadable_extract(self, tmp_path, monkeypatch):
        """Two captured decisions must load as one extract - the file the
        prototype writes is the file the harness reads."""
        path = tmp_path / "captured.jsonl"
        monkeypatch.setenv("FEEDBACK_PATH", str(path))
        client.post("/feedback", json={"claim_id": "CLM-001", "handler_decision": "fast_track"})
        client.post("/feedback", json={"claim_id": "CLM-007", "handler_decision": "investigate"})
        records = [
            ClaimOutcome.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        extract = OutcomeSet(outcomes=records)  # raises on duplicates
        assert set(extract.by_claim()) == {"CLM-001", "CLM-007"}
