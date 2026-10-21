"""FastAPI endpoint for motor claims triage."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from eval.outcomes import ClaimOutcome
from src.mock_data import POLICIES, generate_claims
from src.models import Claim, TriageResult
from src.triage import triage_with_context

app = FastAPI(
    title="Motor Claims Triage API",
    description="Decision-support copilot for motor insurance claims",
    version="0.1.0",
)

# Origins are configurable; the default is open because this is a prototype
# with mock data and no authentication. Two things were wrong with the
# previous configuration: allow_credentials=True with a wildcard origin is
# rejected by browsers per the Fetch spec (a credentialed request must name
# its origins), and the API uses no cookies or auth at all, so credentials
# had nothing to grant. When this fronts real data, set CORS_ORIGINS to an
# explicit list and drop the wildcard.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Load mock data at startup
MOCK_CLAIMS = generate_claims()
POLICY_MAP = {p.policy_number: p for p in POLICIES}


@app.get("/")
def root():
    return {
        "service": "Motor Claims Triage API",
        "version": "0.1.0",
        "endpoints": {
            "triage": "POST /triage_claim",
            "claims": "GET /claims",
            "claim": "GET /claims/{claim_id}",
            "policies": "GET /policies",
            "feedback": "POST /feedback",
        },
    }


@app.get("/claims")
def list_claims():
    return [
        {
            "claim_id": c.claim_id,
            "policy_number": c.policy_number,
            "driver": c.driver.name,
            "vehicle": f"{c.vehicle.year} {c.vehicle.make} {c.vehicle.model}",
            "repair_cost": c.repair_estimate.estimated_cost if c.repair_estimate else 0,
            "status": c.status.value,
        }
        for c in MOCK_CLAIMS
    ]


@app.get("/claims/{claim_id}")
def get_claim(claim_id: str):
    for c in MOCK_CLAIMS:
        if c.claim_id == claim_id:
            return c
    raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")


@app.get("/policies")
def list_policies():
    return POLICIES


@app.post("/triage_claim", response_model=TriageResult)
def triage_single_claim(claim: Claim):
    result = triage_with_context(claim, POLICY_MAP, MOCK_CLAIMS)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Policy {claim.policy_number} not found",
        )
    return result


@app.post("/triage_claim/{claim_id}", response_model=TriageResult)
def triage_existing_claim(claim_id: str):
    claim = None
    for c in MOCK_CLAIMS:
        if c.claim_id == claim_id:
            claim = c
            break

    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    result = triage_with_context(claim, POLICY_MAP, MOCK_CLAIMS)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Policy {claim.policy_number} not found",
        )
    return result


@app.get("/triage_all")
def triage_all_claims():
    results = []
    for claim in MOCK_CLAIMS:
        result = triage_with_context(claim, POLICY_MAP, MOCK_CLAIMS)
        if result is not None:
            results.append(result)
    return results


# Feedback capture: the prototype's own calibration data. Handlers (or the
# demo) POST what actually happened to a claim; the body is the very schema
# the harness loads (eval.outcomes.ClaimOutcome), so what lands on disk is
# one JSON per line, directly consumable by eval/. FEEDBACK_PATH is read per
# request, unlike CORS_ORIGINS: tests redirect the file without an import
# dance, and a one-off run can point at a different extract. No locking -
# one uvicorn process at prototype scale; the file is human-editable JSONL.
_DEFAULT_FEEDBACK_PATH = "eval/captured_outcomes.jsonl"


def _feedback_path() -> Path:
    return Path(os.environ.get("FEEDBACK_PATH", _DEFAULT_FEEDBACK_PATH))


@app.post("/feedback", status_code=201)
def receive_feedback(record: ClaimOutcome) -> dict[str, object]:
    """Record a handler's decision (and any outcome fields) for a claim.

    The response carries the engine's own recommendation for the claim when
    it is known to the demo set - the raw material of the decision-agreement
    metric, frozen at capture. Unknown (partner) claim IDs are accepted: the
    harness joins on ID only. A second record for the same claim_id is
    refused (409), keeping OutcomeSet's one-outcome-per-claim invariant at
    write time rather than at load time; to correct a record, edit the JSONL
    line directly.
    """
    path = _feedback_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("claim_id") == record.claim_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Feedback for claim {record.claim_id} already recorded in "
                        f"{path}; edit the file to correct it."
                    ),
                )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.model_dump(mode="json")) + "\n")

    engine_recommendation = None
    for c in MOCK_CLAIMS:
        if c.claim_id == record.claim_id:
            result = triage_with_context(c, POLICY_MAP, MOCK_CLAIMS)
            if result is not None:
                engine_recommendation = result.recommendation.value
            break

    return {
        "stored": record.model_dump(mode="json"),
        "engine_recommendation": engine_recommendation,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
