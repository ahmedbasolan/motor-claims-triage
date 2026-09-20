"""Coverage check logic for motor claims."""

from src.models import (
    Claim,
    CoverageCheckResult,
    CoverageType,
    Policy,
)


def check_coverage(claim: Claim, policy: Policy) -> CoverageCheckResult:
    """Check if a claim is covered under the given policy."""
    exclusions: list[str] = []
    notes: list[str] = []

    # Check policy is active
    claim_date = claim.accident.date.date()
    if claim_date < policy.policy_start_date or claim_date > policy.policy_end_date:
        exclusions.append("policy_not_active")
        notes.append(
            f"Accident date {claim_date} is outside policy period "
            f"({policy.policy_start_date} to {policy.policy_end_date})"
        )

    # Check if driver is excluded
    if claim.driver.name in policy.excluded_drivers:
        exclusions.append("excluded_driver")
        notes.append(f"Driver '{claim.driver.name}' is listed as excluded on policy")

    # Check vehicle matches policy
    if claim.vehicle.registration_number != policy.vehicle_registration:
        exclusions.append("vehicle_mismatch")
        notes.append(
            f"Claim vehicle {claim.vehicle.registration_number} does not match "
            f"policy vehicle {policy.vehicle_registration}"
        )

    # Check use case exclusions (simulated via keywords in description)
    excluded_use_keywords = {
        "rental": "rental_use",
        "ride-hailing": "ride_hailing_use",
        "uber": "ride_hailing_use",
        "careem": "ride_hailing_use",
        "taxi": "taxi_use",
        "delivery": "delivery_use",
    }
    desc_lower = claim.accident.description.lower()
    for keyword, exclusion in excluded_use_keywords.items():
        if keyword in desc_lower and exclusion not in exclusions:
            if keyword in [u.lower() for u in policy.excluded_uses] or policy.excluded_uses:
                exclusions.append(exclusion)
                notes.append(f"Use case '{keyword}' may be excluded under policy terms")

    # Check claim type coverage based on policy type
    if policy.coverage_type == CoverageType.THIRD_PARTY:
        # Third party only covers damage to other parties, not own vehicle
        if "own vehicle" in desc_lower or "my car" in desc_lower:
            notes.append(
                "Third-party policy: own vehicle damage may not be covered. "
                "Only liability to other parties is covered."
            )

    # Determine if covered
    is_covered = len(exclusions) == 0

    if is_covered:
        notes.append("Claim passes all coverage checks")

    return CoverageCheckResult(
        is_covered=is_covered,
        coverage_type=policy.coverage_type,
        exclusions_triggered=exclusions,
        excess_amount=policy.excess,
        max_payout=policy.max_sum_insured,
        notes=notes,
    )
