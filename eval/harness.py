"""Calibration metrics: how well the engine's thresholds track reality.

Three reports, in increasing order of what they need:

- decision agreement  (outcomes only): engine recommendation vs handler
  decision. Shows where the engine would change practice, not whether it is
  right - handlers are a baseline, not ground truth.
- indicator precision/recall (outcomes with fraud findings): for each fraud
  indicator, how often it fired on claims SIU confirmed as fraud (precision),
  and how often it fired on the fraud claims that existed (recall).
- threshold sensitivity (no outcomes needed): sweep each threshold and count
  how many of the labelled claims change recommendation. The steeper the
  curve around the current value, the more the unvalidated guess matters.

Every metric degrades honestly: records with unknown fields are excluded
from the metrics that need them, and the report says what it skipped.
"""

from collections import Counter
from dataclasses import dataclass, field

from eval.outcomes import ClaimOutcome
from src import scoring
from src.mock_data import POLICIES, generate_claims
from src.models import Claim, TriageResult
from src.scoring import driver_key
from src.triage import triage_claim

# Fraud factor text -> stable indicator key. The engine narrates factors as
# prose; calibration needs to group them. Substring match, not prefix: the
# repeat-claims factor leads with a count ("2 previous claims in last 90
# days..."), so a prefix test silently never matches.
_INDICATOR_PATTERNS = {
    "new_policy": "New policy",
    "repeat_claims": "previous claim",
    "inconsistency": "Potential inconsistency",
    "thin_documentation": "Limited documentation",
}


def indicator_of(factor: str) -> str | None:
    """Map a fraud factor string to its indicator key, or None if unknown."""
    for key, pattern in _INDICATOR_PATTERNS.items():
        if pattern.lower() in factor.lower():
            return key
    return None


def _triage_all(claims: list[Claim]) -> dict[str, TriageResult]:
    policy_map = {p.policy_number: p for p in POLICIES}
    results = {}
    for c in claims:
        key = driver_key(c.driver.name)
        dc = [x for x in claims if driver_key(x.driver.name) == key]
        results[c.claim_id] = triage_claim(c, policy_map[c.policy_number], dc)
    return results


@dataclass
class IndicatorStats:
    fired: int = 0
    confirmed: int = 0  # fired AND fraud confirmed
    missed: int = 0  # fraud confirmed but did not fire

    @property
    def precision(self) -> float | None:
        """Of the claims this indicator flagged, the share SIU confirmed."""
        return self.confirmed / self.fired if self.fired else None

    @property
    def recall(self) -> float | None:
        """Of the confirmed fraud claims, the share this indicator caught."""
        total = self.confirmed + self.missed
        return self.confirmed / total if total else None


@dataclass
class CalibrationReport:
    # Decision agreement
    total_with_outcomes: int = 0
    agreement: Counter = field(default_factory=Counter)  # (engine, handler) -> n
    # Indicator metrics
    indicators: dict[str, IndicatorStats] = field(default_factory=dict)
    # What was excluded and why
    skipped: list[str] = field(default_factory=list)
    # Fraud base rate among investigated claims
    fraud_confirmed: int = 0
    fraud_cleared: int = 0
    fraud_unknown: int = 0

    def summary(self) -> str:
        lines = ["# Calibration report", ""]

        lines.append(f"Claims with outcomes: {self.total_with_outcomes}")
        if self.total_with_outcomes:
            agree = sum(n for (e, h), n in self.agreement.items() if e == h)
            lines.append(f"Engine agrees with handler on: {agree}")
            lines.append("")
            lines.append("## Where the engine differs from the handler")
            for (e, h), n in sorted(self.agreement.items(), key=lambda x: -x[1]):
                if e != h:
                    lines.append(f"  {n}x engine={e.value} vs handler={h.value}")

        lines.append("")
        lines.append("## Fraud findings")
        lines.append(f"  confirmed: {self.fraud_confirmed}")
        lines.append(f"  cleared:   {self.fraud_cleared}")
        lines.append(f"  unknown:   {self.fraud_unknown} (never investigated)")

        lines.append("")
        lines.append("## Indicator quality (vs confirmed fraud)")
        lines.append(f"  {'indicator':<20} {'fired':>6} {'prec':>6} {'recall':>7}")
        for name, st in sorted(self.indicators.items()):
            prec = f"{st.precision:.0%}" if st.precision is not None else "  n/a"
            rec = f"{st.recall:.0%}" if st.recall is not None else "  n/a"
            lines.append(f"  {name:<20} {st.fired:>6} {prec:>6} {rec:>7}")

        if self.skipped:
            lines.append("")
            lines.append("## Skipped (insufficient data)")
            for s in self.skipped:
                lines.append(f"  - {s}")

        return "\n".join(lines)


def evaluate(
    outcomes: dict[str, ClaimOutcome], claims: list[Claim] | None = None
) -> CalibrationReport:
    """Compare engine output against recorded outcomes."""
    claims = claims if claims is not None else generate_claims()
    results = _triage_all(claims)
    report = CalibrationReport()

    for cid, outcome in outcomes.items():
        result = results.get(cid)
        if result is None:
            report.skipped.append(f"{cid}: no claim with this id in the dataset")
            continue

        report.total_with_outcomes += 1
        report.agreement[(result.recommendation, outcome.handler_decision)] += 1

        # Fraud-finding metrics need the SIU verdict.
        if outcome.fraud_confirmed is None:
            report.fraud_unknown += 1
            continue
        if outcome.fraud_confirmed:
            report.fraud_confirmed += 1
        else:
            report.fraud_cleared += 1

        fired_indicators = {k for f in result.scoring.fraud_risk_factors if (k := indicator_of(f))}
        for key in _INDICATOR_PATTERNS:
            st = report.indicators.setdefault(key, IndicatorStats())
            fired = key in fired_indicators
            if fired:
                st.fired += 1
            if outcome.fraud_confirmed:
                if fired:
                    st.confirmed += 1
                else:
                    st.missed += 1

    return report


# ── Threshold sensitivity ────────────────────────────────────────────────
# Threshold name (scoring-module attribute) -> values to try around the
# current default. Extend this map to add a threshold; the sweep restores
# state, so order does not matter.
SWEEPS: dict[str, list[float]] = {
    "NEW_POLICY_DAYS": [15, 30, 45, 60, 90],
    "HIGH_CLAIM_AED": [10000, 15000, 25000, 50000],
    "REPEAT_WINDOW_DAYS": [30, 60, 90, 180],
    "FR_HIGH_AT": [4, 5, 6, 8],
    "CX_HIGH_AT": [4, 5, 6, 8],
}


def sensitivity(
    attribute: str, values: list[float] | None = None, claims: list[Claim] | None = None
) -> list[tuple[float, Counter, int]]:
    """Sweep one threshold; return (value, recommendation counts, changes).

    Changes counts claims whose recommendation differs from the baseline at
    the current (default) setting. The sweep restores the original value, so
    repeated calls do not leak state between thresholds.
    """
    claims = claims if claims is not None else generate_claims()
    values = values if values is not None else SWEEPS[attribute]
    original = getattr(scoring, attribute)

    baseline_per_claim = {cid: r.recommendation for cid, r in _triage_all(claims).items()}

    rows: list[tuple[float, Counter, int]] = []
    try:
        for v in values:
            setattr(scoring, attribute, int(v))
            results = _triage_all(claims)
            counts = Counter(r.recommendation.value for r in results.values())
            changes = sum(
                1 for cid, r in results.items() if r.recommendation != baseline_per_claim[cid]
            )
            rows.append((v, counts, changes))
    finally:
        setattr(scoring, attribute, original)

    return rows


def sensitivity_report() -> str:
    """Human-readable sweep of every threshold in SWEEPS."""
    lines = ["# Threshold sensitivity", ""]
    lines.append("Claims whose recommendation changes as each threshold moves, against")
    lines.append("the current defaults. Steeper = the unvalidated guess matters more.")
    for attribute, values in SWEEPS.items():
        default = getattr(scoring, attribute)
        lines.append("")
        lines.append(f"## {attribute} (default: {default})")
        for v, counts, changes in sensitivity(attribute, values):
            marker = " <- default" if v == default else ""
            dist = ", ".join(
                f"{k}={counts.get(k, 0)}" for k in ("fast_track", "standard_review", "investigate")
            )
            lines.append(f"  {v:>6}: {dist}  ({changes} changed){marker}")
    return "\n".join(lines)


def _demo() -> None:
    """Print both reports. Outcomes come from eval/demo_outcomes.json, which
    is synthetic - it demonstrates the harness, it does not validate the
    engine. Replace with real extracts to calibrate."""
    import json
    from pathlib import Path

    from eval.outcomes import OutcomeSet

    path = Path(__file__).parent / "demo_outcomes.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    outcome_set = OutcomeSet.model_validate(raw)
    report = evaluate(outcome_set.by_claim())
    print(report.summary())
    print()
    print(sensitivity_report())


if __name__ == "__main__":
    _demo()
