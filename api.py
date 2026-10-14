"""FastAPI endpoint for motor claims triage."""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.mock_data import POLICIES, generate_claims
from src.models import Claim, TriageResult
from src.scoring import driver_key
from src.triage import triage_claim

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
    policy = POLICY_MAP.get(claim.policy_number)
    if not policy:
        raise HTTPException(
            status_code=400,
            detail=f"Policy {claim.policy_number} not found",
        )

    # Find other claims for same driver to check repeated claims.
    key = driver_key(claim.driver.name)
    driver_claims = [c for c in MOCK_CLAIMS if driver_key(c.driver.name) == key]

    return triage_claim(claim, policy, driver_claims)


@app.post("/triage_claim/{claim_id}", response_model=TriageResult)
def triage_existing_claim(claim_id: str):
    claim = None
    for c in MOCK_CLAIMS:
        if c.claim_id == claim_id:
            claim = c
            break

    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    policy = POLICY_MAP.get(claim.policy_number)
    if not policy:
        raise HTTPException(
            status_code=400,
            detail=f"Policy {claim.policy_number} not found",
        )

    key = driver_key(claim.driver.name)
    driver_claims = [c for c in MOCK_CLAIMS if driver_key(c.driver.name) == key]

    return triage_claim(claim, policy, driver_claims)


@app.get("/triage_all")
def triage_all_claims():
    results = []
    for claim in MOCK_CLAIMS:
        policy = POLICY_MAP.get(claim.policy_number)
        if policy:
            key = driver_key(claim.driver.name)
            driver_claims = [c for c in MOCK_CLAIMS if driver_key(c.driver.name) == key]
            result = triage_claim(claim, policy, driver_claims)
            results.append(result)
    return results


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
