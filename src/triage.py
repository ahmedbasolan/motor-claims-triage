"""Main triage orchestrator for motor claims."""

from src.coverage import check_coverage
from src.models import Claim, Policy, TriageResult
from src.narrative import generate_narrative
from src.recommendation import generate_recommendation
from src.scoring import score_claim


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
