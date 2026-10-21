"""Coverage check logic for motor claims."""

import re

from src.models import (
    Claim,
    CoverageCheckResult,
    CoverageType,
    Policy,
)

# How a policy's free-text excluded_uses entries map onto the exclusion codes
# emitted by the description keyword scan. Accepts the common spellings a
# policy document might carry.
_USE_CODE_ALIASES = {
    "rental": "rental_use",
    "hire": "rental_use",
    "ride_hailing": "ride_hailing_use",
    "ridehailing": "ride_hailing_use",
    "taxi": "taxi_use",
    "delivery": "delivery_use",
}


def _excluded_use_codes(excluded_uses: list[str]) -> set[str]:
    """Normalise a policy's excluded_uses into the codes used in results."""
    codes: set[str] = set()
    for use in excluded_uses or []:
        key = re.sub(r"[^a-z]+", "_", str(use).lower()).strip("_")
        if key in _USE_CODE_ALIASES:
            codes.add(_USE_CODE_ALIASES[key])
        elif key.endswith("_use") and key[:-4] in _USE_CODE_ALIASES:
            codes.add(key)
    return codes


def _norm_name(value: str) -> str:
    """Normalise a person name for comparison: case and internal whitespace
    only. 'john smith' and 'John  Smith' are the same driver; punctuation is
    left alone so distinct names stay distinct."""
    return " ".join(str(value).split()).casefold()


def _norm_reg(value: str) -> str:
    """Normalise a registration plate for comparison: case-insensitive and
    ignoring separators, so 'a-12345', 'A 12345' and 'A12345' compare equal.
    Plates arrive from different systems with different spacing."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


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

    # Check if driver is excluded. Compared case- and whitespace-insensitively:
    # an exact-string miss let an excluded driver's claim pass, and that is a
    # missed exclusion, the fraud-side error this check exists to prevent.
    claim_driver = _norm_name(claim.driver.name)
    if any(claim_driver == _norm_name(d) for d in policy.excluded_drivers):
        exclusions.append("excluded_driver")
        notes.append(f"Driver '{claim.driver.name}' is listed as excluded on policy")

    # Check vehicle matches policy. Plates are compared ignoring case and
    # separators: an exact-string mismatch on 'a-12345' vs 'A-12345' denied a
    # covered claim over formatting, the worst error this component can make.
    if _norm_reg(claim.vehicle.registration_number) != _norm_reg(policy.vehicle_registration):
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
    # Which use codes this policy actually excludes.
    #
    # The previous test was `keyword in policy.excluded_uses or
    # policy.excluded_uses`, and the second clause made the first irrelevant:
    # any policy with a non-empty exclusion list rejected a claim for *any*
    # use-case word in the description. A policy excluding only "rental" denied
    # delivery claims, and one excluding "ride_hailing" denied taxi claims.
    # Denying a covered claim is the worst error this component can make, so
    # the keyword is now matched against the specific excluded code, and on
    # word boundaries so "delivery" does not match inside another word.
    excluded_codes = _excluded_use_codes(policy.excluded_uses)
    desc_lower = claim.accident.description.lower()
    for keyword, exclusion in excluded_use_keywords.items():
        if exclusion not in excluded_codes or exclusion in exclusions:
            continue
        if re.search(rf"\b{re.escape(keyword)}\b", desc_lower):
            exclusions.append(exclusion)
            notes.append(f"Use case '{keyword}' is excluded under policy terms")

    # Check claim type coverage based on policy type. Third party only
    # covers damage to other parties, not own vehicle.
    if policy.coverage_type == CoverageType.THIRD_PARTY and (
        "own vehicle" in desc_lower or "my car" in desc_lower
    ):
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
