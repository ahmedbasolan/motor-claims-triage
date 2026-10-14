"""Complexity and fraud risk scoring for motor claims."""

from datetime import timedelta

from src.models import Claim, Policy, RiskLevel, ScoringResult

# A policy held for less than this is treated as recently purchased.
NEW_POLICY_DAYS = 30
# A repair estimate above this is "high" for the new-policy indicator.
HIGH_CLAIM_AED = 15000


def driver_key(name: str) -> str:
    """Normalise a driver name for grouping claims: case- and
    whitespace-insensitive. The repeat-claims window must not miss a prior
    claim because the same driver was typed differently in two systems."""
    return " ".join(str(name).split()).casefold()


def score_complexity(claim: Claim) -> tuple[RiskLevel, list[str]]:
    """Score claim complexity based on multiple factors."""
    score = 0
    factors: list[str] = []

    # Multiple vehicles involved
    if claim.accident.num_vehicles_involved > 1:
        score += 2
        factors.append(f"Multiple vehicles involved ({claim.accident.num_vehicles_involved})")

    # Injury reported
    if claim.accident.injury_reported:
        score += 3
        factors.append("Injury reported - requires medical assessment")

    # Liability disputed
    if claim.accident.liability_disputed:
        score += 2
        factors.append("Liability disputed between parties")

    # High repair cost relative to vehicle value
    if claim.repair_estimate and claim.vehicle.estimated_value > 0:
        cost_ratio = claim.repair_estimate.estimated_cost / claim.vehicle.estimated_value
        if cost_ratio > 0.7:
            score += 3
            factors.append(
                f"Repair cost ({cost_ratio:.0%} of vehicle value) indicates potential total loss"
            )
        elif cost_ratio > 0.4:
            score += 1
            factors.append(f"Repair cost is {cost_ratio:.0%} of vehicle value")

    # Young driver with low experience
    if claim.driver.age < 25 and claim.driver.license_tenure_years < 2:
        score += 1
        factors.append("Young driver with limited experience")

    # Determine risk level
    if score >= 5:
        return RiskLevel.HIGH, factors
    elif score >= 2:
        return RiskLevel.MEDIUM, factors
    return RiskLevel.LOW, factors


def score_fraud_risk(
    claim: Claim,
    all_claims_for_driver: list[Claim] | None = None,
    policy: Policy | None = None,
) -> tuple[RiskLevel, list[str]]:
    """Score fraud risk from indicators.

    `policy` is required for the new-policy indicator. Without it the rule is
    skipped rather than guessed: the indicator is about how long the policy has
    been held, which cannot be derived from the claim alone.
    """
    score = 0
    factors: list[str] = []

    # Recently-purchased policy with a large claim. Age is measured from
    # policy start, not from the gap between accident and submission - that gap
    # is the reporting lag, which is near zero for every ordinary claim, so
    # using it flagged any claim above AED 15,000 as "new policy".
    #
    # The window is bounded on both sides, like the repeat-claims window: a
    # claim predating inception yields a negative age, which passed `< 30` and
    # was reported as "New policy (-42 days old)". A claim before inception is
    # a coverage failure (policy_not_active), not a new-policy indicator, so
    # negative ages are skipped rather than narrated as a fraud factor.
    if policy is not None:
        policy_age_days = (claim.submitted_at.date() - policy.policy_start_date).days
        if 0 <= policy_age_days < NEW_POLICY_DAYS:
            if claim.repair_estimate and claim.repair_estimate.estimated_cost > HIGH_CLAIM_AED:
                score += 3
                factors.append(
                    f"New policy ({policy_age_days} days old) with high claim "
                    f"AED {claim.repair_estimate.estimated_cost:,.0f}"
                )

    # Repeated claims for same driver/vehicle in short period.
    #
    # The window is bounded on both sides. The previous test was only
    # `(claim.accident.date - c.accident.date) <= timedelta(days=90)`, and a
    # claim from the *future* yields a negative delta, which passes: "3
    # previous claims in last 90 days" could be three claims that had not
    # happened yet. Only claims dated at or before the current accident, and
    # within 90 days of it, are previous claims.
    if all_claims_for_driver:
        window = timedelta(days=90)
        recent_claims = [
            c
            for c in all_claims_for_driver
            if c.claim_id != claim.claim_id
            and timedelta(0) <= (claim.accident.date - c.accident.date) <= window
        ]
        if len(recent_claims) >= 2:
            score += 3
            factors.append(f"{len(recent_claims)} previous claims in last 90 days for this driver")
        elif len(recent_claims) == 1:
            score += 1
            factors.append("One previous claim in last 90 days for this driver")

    # Inconsistent story detection (keyword-based)
    inconsistency_keywords = {
        "location": ["different location", "changed story", "inconsistent"],
        "time": ["late report", "delayed report", "unclear timeline"],
        "damage": ["damage doesn't match", "inconsistent damage", "suspicious damage"],
        "cause": ["contradicting", "conflicting account", "varying details"],
    }

    desc_lower = claim.accident.description.lower()
    if claim.accident.police_report_summary:
        report_lower = claim.accident.police_report_summary.lower()
        for category, keywords in inconsistency_keywords.items():
            for keyword in keywords:
                if keyword in desc_lower or keyword in report_lower:
                    score += 2
                    factors.append(f"Potential inconsistency detected: {category}")
                    break

    # High repair cost without clear documentation
    if claim.repair_estimate:
        if not claim.documents or len(claim.documents) < 2:
            score += 1
            factors.append("Limited documentation for high-value repair estimate")

    # Determine risk level
    if score >= 5:
        return RiskLevel.HIGH, factors
    elif score >= 2:
        return RiskLevel.MEDIUM, factors
    return RiskLevel.LOW, factors


def score_claim(
    claim: Claim,
    all_claims_for_driver: list[Claim] | None = None,
    policy: Policy | None = None,
) -> ScoringResult:
    """Generate comprehensive scoring for a claim."""
    complexity_level, complexity_factors = score_complexity(claim)
    fraud_level, fraud_factors = score_fraud_risk(claim, all_claims_for_driver, policy)

    # Overall risk is the higher of the two
    risk_order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
    overall = (
        RiskLevel.HIGH
        if risk_order[complexity_level] >= 2 or risk_order[fraud_level] >= 2
        else RiskLevel.MEDIUM
        if risk_order[complexity_level] >= 1 or risk_order[fraud_level] >= 1
        else RiskLevel.LOW
    )

    return ScoringResult(
        complexity_score=complexity_level,
        complexity_factors=complexity_factors,
        fraud_risk_score=fraud_level,
        fraud_risk_factors=fraud_factors,
        overall_risk=overall,
    )
