"""Recommendation engine for motor claims triage."""

from src.models import (
    CoverageCheckResult,
    Recommendation,
    RiskLevel,
    ScoringResult,
)


def generate_recommendation(
    coverage: CoverageCheckResult,
    scoring: ScoringResult,
) -> Recommendation:
    """Generate a triage recommendation based on coverage and scoring."""

    # Not covered -> Investigate (may be rejection)
    if not coverage.is_covered:
        return Recommendation.INVESTIGATE

    # High fraud risk -> Always investigate
    if scoring.fraud_risk_score == RiskLevel.HIGH:
        return Recommendation.INVESTIGATE

    # High complexity -> Investigate
    if scoring.complexity_score == RiskLevel.HIGH:
        return Recommendation.INVESTIGATE

    # Coverage exclusions triggered -> Investigate
    if coverage.exclusions_triggered:
        return Recommendation.INVESTIGATE

    # Medium on either -> Standard review
    if scoring.complexity_score == RiskLevel.MEDIUM or scoring.fraud_risk_score == RiskLevel.MEDIUM:
        return Recommendation.STANDARD_REVIEW

    # Low complexity, low fraud, clear coverage -> Fast track
    return Recommendation.FAST_TRACK
