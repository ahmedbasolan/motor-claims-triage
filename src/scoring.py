"""Complexity and fraud risk scoring for motor claims."""

from datetime import timedelta

from src.models import Claim, Policy, RiskLevel, ScoringResult

# ── Thresholds ───────────────────────────────────────────────────────────
# Every tunable number lives here, read at call time, so the calibration
# harness (eval/) can sweep each one and report how decisions move. These
# values are prototype defaults, not calibrated against outcome data - the
# README says so, and eval/ is how that gap gets closed.

# Complexity points
CX_MULTI_VEHICLE = 2
CX_INJURY = 3
CX_LIABILITY_DISPUTED = 2
CX_TOTAL_LOSS = 3
CX_ELEVATED_REPAIR = 1
CX_YOUNG_DRIVER = 1
# Complexity risk-level cut points
CX_MEDIUM_AT = 2
CX_HIGH_AT = 5
# Repair-to-value ratios
TOTAL_LOSS_RATIO = 0.7
ELEVATED_REPAIR_RATIO = 0.4
# Young-driver criteria
YOUNG_DRIVER_AGE = 25
YOUNG_DRIVER_TENURE_YEARS = 2

# Fraud points
FR_NEW_POLICY = 3
FR_REPEAT_MANY = 3
FR_REPEAT_ONE = 1
FR_INCONSISTENCY = 2
FR_THIN_DOCS = 1
# Fraud risk-level cut points
FR_MEDIUM_AT = 2
FR_HIGH_AT = 5
# A policy held for less than this is treated as recently purchased.
NEW_POLICY_DAYS = 30
# A repair estimate above this is "high" for the new-policy indicator.
HIGH_CLAIM_AED = 15000
# Repeat-claims window and tiers
REPEAT_WINDOW_DAYS = 90
REPEAT_MANY_CLAIMS = 2
# Documentation below this count is "thin" for a claim carrying an estimate.
MIN_DOCS = 2


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
        score += CX_MULTI_VEHICLE
        factors.append(f"Multiple vehicles involved ({claim.accident.num_vehicles_involved})")

    # Injury reported
    if claim.accident.injury_reported:
        score += CX_INJURY
        factors.append("Injury reported - requires medical assessment")

    # Liability disputed
    if claim.accident.liability_disputed:
        score += CX_LIABILITY_DISPUTED
        factors.append("Liability disputed between parties")

    # High repair cost relative to vehicle value
    if claim.repair_estimate and claim.vehicle.estimated_value > 0:
        cost_ratio = claim.repair_estimate.estimated_cost / claim.vehicle.estimated_value
        if cost_ratio > TOTAL_LOSS_RATIO:
            score += CX_TOTAL_LOSS
            factors.append(
                f"Repair cost ({cost_ratio:.0%} of vehicle value) indicates potential total loss"
            )
        elif cost_ratio > ELEVATED_REPAIR_RATIO:
            score += CX_ELEVATED_REPAIR
            factors.append(f"Repair cost is {cost_ratio:.0%} of vehicle value")

    # Young driver with low experience
    if (
        claim.driver.age < YOUNG_DRIVER_AGE
        and claim.driver.license_tenure_years < YOUNG_DRIVER_TENURE_YEARS
    ):
        score += CX_YOUNG_DRIVER
        factors.append("Young driver with limited experience")

    # Determine risk level
    if score >= CX_HIGH_AT:
        return RiskLevel.HIGH, factors
    elif score >= CX_MEDIUM_AT:
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
                score += FR_NEW_POLICY
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
    # within the window, are previous claims. The factor text states the
    # window actually applied, so a swept window is never narrated as 90.
    if all_claims_for_driver:
        window = timedelta(days=REPEAT_WINDOW_DAYS)
        recent_claims = [
            c
            for c in all_claims_for_driver
            if c.claim_id != claim.claim_id
            and timedelta(0) <= (claim.accident.date - c.accident.date) <= window
        ]
        if len(recent_claims) >= REPEAT_MANY_CLAIMS:
            score += FR_REPEAT_MANY
            factors.append(
                f"{len(recent_claims)} previous claims in last "
                f"{REPEAT_WINDOW_DAYS} days for this driver"
            )
        elif len(recent_claims) == 1:
            score += FR_REPEAT_ONE
            factors.append(f"One previous claim in last {REPEAT_WINDOW_DAYS} days for this driver")

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
                    score += FR_INCONSISTENCY
                    factors.append(f"Potential inconsistency detected: {category}")
                    break

    # High repair cost without clear documentation
    if claim.repair_estimate:
        if not claim.documents or len(claim.documents) < MIN_DOCS:
            score += FR_THIN_DOCS
            factors.append("Limited documentation for high-value repair estimate")

    # Determine risk level
    if score >= FR_HIGH_AT:
        return RiskLevel.HIGH, factors
    elif score >= FR_MEDIUM_AT:
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
