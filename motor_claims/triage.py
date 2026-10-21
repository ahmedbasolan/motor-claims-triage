"""Main triage orchestrator for motor claims."""

from motor_claims.coverage import check_coverage
from motor_claims.models import Claim, Policy, TriageResult
from motor_claims.narrative import generate_narrative
from motor_claims.recommendation import generate_recommendation
from motor_claims.scoring import driver_key, score_claim


def triage_claim(
    claim: Claim,
    policy: Policy,
    all_claims_for_driver: list[Claim] | None = None,
) -> TriageResult:
    """Run full triage pipeline on a claim."""
    # Step 1: Coverage check
    coverage = check_coverage(claim, policy)

    # Step 2: Score complexity and fraud risk. The policy is required: the
    # new-policy fraud indicator measures how long the policy has been held.
    scoring = score_claim(claim, all_claims_for_driver, policy)

    # Step 3: Generate recommendation
    recommendation = generate_recommendation(coverage, scoring)

    # Step 4: Generate narrative
    narrative = generate_narrative(claim, coverage, scoring, recommendation)

    return TriageResult(
        claim_id=claim.claim_id,
        recommendation=recommendation,
        coverage=coverage,
        scoring=scoring,
        narrative=narrative,
    )


def triage_with_context(
    claim: Claim,
    policies: dict[str, Policy],
    all_claims: list[Claim],
) -> TriageResult | None:
    """Triage one claim against the dataset it lives in.

    The wiring every entry point needs - API, UI, eval harness, ground-truth
    tests - previously hand-rolled it in seven places: resolve the claim's
    policy, gather the driver's other claims for the repeat-claims window
    (grouped via driver_key, so a name recorded differently between systems
    does not hide claim history - the A3 defect), then run the engine.
    Keeping it in one place means the grouping cannot silently diverge
    between surfaces again.

    Returns None when the claim's policy number is not in ``policies``;
    callers decide what that means - the API answers 400, bulk views skip
    the claim.
    """
    policy = policies.get(claim.policy_number)
    if policy is None:
        return None
    key = driver_key(claim.driver.name)
    driver_claims = [c for c in all_claims if driver_key(c.driver.name) == key]
    return triage_claim(claim, policy, driver_claims)
