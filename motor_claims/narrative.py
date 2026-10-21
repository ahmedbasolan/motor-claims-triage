"""Narrative generation for motor claims triage decisions."""

from motor_claims.models import (
    Claim,
    CoverageCheckResult,
    CoverageType,
    Recommendation,
    RiskLevel,
    ScoringResult,
)

RECOMMENDATION_LABELS = {
    Recommendation.FAST_TRACK: "Fast-Track",
    Recommendation.STANDARD_REVIEW: "Standard Review",
    Recommendation.INVESTIGATE: "Investigate",
}

RISK_LABELS = {
    RiskLevel.LOW: "Low",
    RiskLevel.MEDIUM: "Medium",
    RiskLevel.HIGH: "High",
}


def generate_narrative(
    claim: Claim,
    coverage: CoverageCheckResult,
    scoring: ScoringResult,
    recommendation: Recommendation,
) -> str:
    """Generate a human-readable rationale for the triage decision."""
    sections: list[str] = []

    # Header
    sections.append(f"## Triage Rationale for Claim {claim.claim_id}")
    sections.append("")

    # Coverage summary
    if coverage.is_covered:
        sections.append(
            f"**Coverage:** Clear. {claim.driver.name} is covered under "
            f"{coverage.coverage_type.value.replace('_', ' ').title()} policy "
            f"{claim.policy_number}."
        )
    else:
        exclusions_str = ", ".join(e.replace("_", " ") for e in coverage.exclusions_triggered)
        sections.append(f"**Coverage:** Issue detected. Exclusions triggered: {exclusions_str}.")
    sections.append("")

    # Complexity summary
    sections.append(f"**Complexity:** {RISK_LABELS[scoring.complexity_score]}")
    if scoring.complexity_factors:
        for factor in scoring.complexity_factors[:3]:
            sections.append(f"  - {factor}")
    sections.append("")

    # Fraud risk summary
    sections.append(f"**Fraud Risk:** {RISK_LABELS[scoring.fraud_risk_score]}")
    if scoring.fraud_risk_factors:
        for factor in scoring.fraud_risk_factors[:3]:
            sections.append(f"  - {factor}")
    sections.append("")

    # Financial summary
    if claim.repair_estimate:
        sections.append(
            f"**Estimated Repair Cost:** AED {claim.repair_estimate.estimated_cost:,.0f}"
        )
        sections.append(f"**Excess:** AED {coverage.excess_amount:,.0f}")
        # The payout figure is only stated when it means something. It used to
        # be printed unconditionally, so a claim denied on an exclusion still
        # read "Estimated Net Payout: AED 2,000" - a handler skimming the
        # narrative would reserve against a claim the engine recommends
        # investigating for denial. Third-party policies respond to liability
        # to other parties, not to the own-vehicle repair estimate, so the
        # estimate is not a basis for a payout figure there either.
        if not coverage.is_covered:
            sections.append(
                "**Estimated Net Payout:** Not estimated - coverage checks did not pass."
            )
        elif coverage.coverage_type == CoverageType.THIRD_PARTY:
            sections.append(
                "**Estimated Net Payout:** Not estimated from this figure - "
                "third-party cover responds to liability to other parties, not to "
                "own-vehicle repair."
            )
        else:
            # The payout is capped by the policy's sum insured. This was
            # missing: a AED 120,000 repair on a AED 100,000 policy was reported
            # as a "Estimated Net Payout: AED 119,700", a figure the policy
            # could never pay. The cap is applied, and stated, whenever it binds.
            net = claim.repair_estimate.estimated_cost - coverage.excess_amount
            capped = net > coverage.max_payout
            payable = min(net, coverage.max_payout) if net > 0 else 0
            sections.append(f"**Estimated Net Payout:** AED {payable:,.0f}")
            if capped:
                sections.append(
                    f"Capped at the policy sum insured (AED {coverage.max_payout:,.0f}); "
                    "the repair estimate exceeds the policy limit."
                )
    sections.append("")

    # Recommendation
    sections.append(f"**Recommendation:** {RECOMMENDATION_LABELS[recommendation]}")

    # Final rationale
    if recommendation == Recommendation.FAST_TRACK:
        sections.append(
            "This claim meets all coverage criteria with low complexity and "
            "low fraud risk. Recommend fast-track processing for prompt settlement."
        )
    elif recommendation == Recommendation.STANDARD_REVIEW:
        sections.append(
            "This claim requires standard review due to moderate complexity "
            "or risk indicators. A handler should verify details before proceeding."
        )
    else:
        sections.append(
            "This claim requires investigation due to coverage concerns, "
            "high complexity, or fraud risk indicators. Escalate to SIU or "
            "senior handler for detailed review."
        )

    return "\n".join(sections)
