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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from api import app
from src.mock_data import EXPECTED_RECOMMENDATIONS

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
