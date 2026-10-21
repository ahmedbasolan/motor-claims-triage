"""UI tests: the Streamlit dashboard via streamlit.testing.v1.AppTest.

The unit tests verify the engine and the API tests verify the HTTP surface;
these verify what a handler actually sees. The load-bearing tests are
test_every_claim_renders_expected_content (each of the 38 labelled claims is
selected in the sidebar; the verdict stamp, every fact-grid figure, the
coverage stamp and both risk chips must match the claim data and the engine -
a dashboard that shows the wrong verdict, stale details, or crashes on
selection fails here even when the engine and API are correct) and
test_every_claim_wraps_prose_values_in_mono_spans (the brand mono rule:
money, dates and identifiers in prose render in mono spans, and the prose
around them is untouched). test_bulk_table_matches_ground_truth checks the
in-brand bulk table cell by cell for all 38 claims.
"""

import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest

from motor_claims.mock_data import EXPECTED_RECOMMENDATIONS, POLICIES, generate_claims
from motor_claims.triage import triage_with_context

_APP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "ui.py"
)

# Stamp contract: the label text and kind (REC_STYLE in app/ui.py) the UI must
# render for each recommendation. Deliberately restated here rather than
# imported - ui.py runs a script at import time, and a test that imports the
# constants it checks cannot catch them changing. If ui.py's labels change,
# this must be changed with it, consciously.
REC_STAMP = {
    "fast_track": ("FAST-TRACK", "pass"),
    "standard_review": ("STANDARD REVIEW", "caution"),
    "investigate": ("INVESTIGATE", "danger"),
}

# Metric labels (stat_colN.metric) per stamp label.
METRIC_OF_STAMP = {
    "FAST-TRACK": "Fast-track",
    "STANDARD REVIEW": "Standard review",
    "INVESTIGATE": "Investigate",
}

# Risk chip contract (RISK_STYLE in app/ui.py), restated.
RISK_CHIP = {
    "low": ("Low", "pass"),
    "medium": ("Medium", "caution"),
    "high": ("High", "danger"),
}

# Value-span contract (brand/BRAND.md mono rule: money, dates and identifiers
# are mono wherever they appear, prose is never mono, "IDs are never sans").
# The dashboard wraps each occurrence in <span class="mct-val">. Restated,
# like REC_STAMP, rather than imported from the code under test.
VAL_OPEN = '<span class="mct-val">'
VAL_CLOSE = "</span>"
VAL_RE = re.compile(
    r"AED \d{1,3}(?:,\d{3})*"  # money
    r"|\b\d{4}-\d{2}-\d{2}\b"  # ISO dates
    r"|\b\d{1,2} [A-Z][a-z]{2} \d{4}\b"  # text dates
    r"|\b[A-Z]{3}-\d{4}-\d{3}\b"  # policy numbers
    r"|\b[A-Z]{1,3}-\d{3,6}\b"  # claim IDs / registrations
)

# Expected side: the claims and their engine results, computed independently
# of ui.py - the test compares rendered output against these, not against
# whatever ui.py itself derived.
CLAIMS = generate_claims()
CLAIMS_BY_ID = {c.claim_id: c for c in CLAIMS}
POLICY_MAP = {p.policy_number: p for p in POLICIES}
RESULTS = {c.claim_id: triage_with_context(c, POLICY_MAP, CLAIMS) for c in CLAIMS}


def _run() -> AppTest:
    at = AppTest.from_file(_APP_PATH, default_timeout=60)
    at.run()
    return at


def _markdown(at: AppTest) -> list[str]:
    return [str(m.value) for m in at.markdown]


def _spans(at: AppTest) -> list[str]:
    return [v for v in _markdown(at) if 'class="mct-stamp mct-stamp--' in v]


def _result(cid: str):
    res = RESULTS[cid]
    assert res is not None, f"engine produced no result for {cid}"
    return res


def _strip_vals(text: str) -> str:
    return text.replace(VAL_OPEN, "").replace(VAL_CLOSE, "")


def _unwrapped_values(text: str) -> list[str]:
    """Value occurrences not immediately inside a mono span."""
    bad = []
    for m in VAL_RE.finditer(text):
        if not (text[: m.start()].endswith(VAL_OPEN) and text[m.end() :].startswith(VAL_CLOSE)):
            bad.append(m.group(0))
    return bad


def _expected_narrative_body(narrative: str) -> str:
    """Drop the generator's leading heading - computed independently of the
    regex ui.py uses, so both must agree with the engine text."""
    lines = narrative.split("\n")
    i = 0
    if lines and lines[0].lstrip().startswith("#"):
        i = 1
        while i < len(lines) and lines[i].strip() == "":
            i += 1
    return "\n".join(lines[i:]).strip()


def _expected_alerts(res) -> list[str]:
    """Exclusion alerts (title-cased tokens, ui's display transform) followed
    by the coverage notes verbatim."""
    alerts = []
    if not res.coverage.is_covered:
        alerts += [
            f"Exclusion — {e.replace('_', ' ').strip().title()}"
            for e in res.coverage.exclusions_triggered
        ]
    alerts += list(res.coverage.notes)
    return alerts


def _expected_facts(claim) -> dict[str, str]:
    """Fact-grid contract: label -> displayed value, computed from the claim
    with the stated formats restated here (AED 1,234 / 05 Sep 2024, 00:00)."""
    r = claim.repair_estimate
    return {
        "Claim ID": claim.claim_id,
        "Policy": claim.policy_number,
        "Driver": claim.driver.name,
        "Age": f"{claim.driver.age} years",
        "Licence held": f"{claim.driver.license_tenure_years} years",
        "Vehicle": f"{claim.vehicle.year} {claim.vehicle.make} {claim.vehicle.model}",
        "Registration": claim.vehicle.registration_number,
        "Vehicle value": f"AED {claim.vehicle.estimated_value:,.0f}",
        "Accident": claim.accident.date.strftime("%d %b %Y, %H:%M"),
        "Location": claim.accident.location,
        "Repair estimate": f"AED {r.estimated_cost:,.0f}" if r else "—",
        "Garage": r.garage_name if r else "—",
        "Vehicles involved": str(claim.accident.num_vehicles_involved),
        "Injury reported": "Yes" if claim.accident.injury_reported else "No",
        "Liability disputed": "Yes" if claim.accident.liability_disputed else "No",
    }


def test_dashboard_renders_without_exception():
    at = _run()
    assert not at.exception, f"dashboard crashed on load: {at.exception}"


def test_sidebar_lists_every_labelled_claim():
    at = _run()
    # options are format_func output ("CLM-001 — Name"); the raw values are
    # claim ids, which is what set_value accepts - verified by the round-trip
    # test below.
    options = {str(o) for o in at.sidebar.selectbox[0].options}
    expected = {f"{cid} — {CLAIMS_BY_ID[cid].driver.name}" for cid in EXPECTED_RECOMMENDATIONS}
    assert options == expected
    # The open option list is a virtual dropdown portaled outside .stApp with
    # no font rule of its own, so the mono rule must be in the injected CSS -
    # the rows expose no DOM contract AppTest could reach.
    css = next((v for v in _markdown(at) if "stSelectboxVirtualDropdown" in v), "")
    assert re.search(
        r'\[data-testid="stSelectboxVirtualDropdown"\] \{[^}]*font-family: var\(--font-mono\)',
        css,
    ), "dropdown option list is not mono"


def test_default_selection_shows_first_claim():
    at = _run()
    assert at.sidebar.selectbox[0].value == "CLM-001"
    label, kind = REC_STAMP[EXPECTED_RECOMMENDATIONS["CLM-001"]]
    span = f'<span class="mct-stamp mct-stamp--{kind}">{label}</span>'
    assert any(span in v for v in _spans(at)), f"stamp {label!r} not rendered"


def test_every_claim_renders_expected_content():
    """Round-trip all 38 claims through the sidebar selector: the stamp must
    carry the ground-truth label, the fact grid must show this claim's fields
    (not a stale claim's), the coverage stamp must match the engine's
    is_covered, and both risk chips must carry the engine's level."""
    at = _run()
    failures = []
    for cid, expected in EXPECTED_RECOMMENDATIONS.items():
        at.sidebar.selectbox[0].set_value(cid)
        at.run()
        if at.exception:
            failures.append(f"{cid}: crashed: {at.exception[0]}")
            continue
        claim = CLAIMS_BY_ID[cid]
        res = _result(cid)
        vals = _markdown(at)
        joined = "\n".join(vals)

        label, kind = REC_STAMP[expected]
        span = f'<span class="mct-stamp mct-stamp--{kind}">{label}</span>'
        if not any(span in v for v in _spans(at)):
            failures.append(f"{cid}: expected stamp {label!r} not rendered")

        fact_text = "\n".join(v for v in vals if 'class="mct-facts"' in v)
        got_facts = {
            html.unescape(k): html.unescape(v)
            for k, v in re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", fact_text, re.S)
        }
        want_facts = _expected_facts(claim)
        for name, want in want_facts.items():
            if got_facts.get(name) != want:
                failures.append(f"{cid}: fact {name!r}: {got_facts.get(name)!r} != {want!r}")
        for name in set(got_facts) - set(want_facts):
            failures.append(f"{cid}: unexpected fact {name!r}")

        cov_span = (
            'mct-stamp--pass mct-stamp--compact">Covered<'
            if res.coverage.is_covered
            else 'mct-stamp--danger mct-stamp--compact">Exclusion triggered<'
        )
        if cov_span not in joined:
            failures.append(f"{cid}: coverage stamp wrong (is_covered={res.coverage.is_covered})")

        for title, score in (
            ("Complexity", res.scoring.complexity_score),
            ("Fraud risk", res.scoring.fraud_risk_score),
        ):
            want_label, want_kind = RISK_CHIP[score.value]
            panel = next((v for v in vals if f'mct-card__title">{title}<' in v), "")
            m = re.search(r'mct-chip mct-chip--(\w+)">([^<]+)<', panel)
            if m is None or m.group(1) != want_kind or m.group(2) != want_label:
                failures.append(
                    f"{cid}: {title} chip: "
                    f"{(m.group(1), m.group(2)) if m else None} != {(want_kind, want_label)}"
                )
    assert failures == []


def test_bulk_table_matches_ground_truth():
    """The bulk view is checked column by column against the claims and the
    engine for all 38 claims - the whole-table equivalent of the per-claim
    round-trip. The table is an in-brand HTML component (the dataframe grid
    draws cells on a canvas and cannot be styled to the brand), so both its
    contents and its CSS contract are asserted."""
    at = _run()
    table = next((v for v in _markdown(at) if 'class="mct-table"' in v), "")
    assert table, "bulk table not rendered"

    css = next((v for v in _markdown(at) if ".mct-table" in v), "")
    assert re.search(r"\.mct-table td \{[^}]*font-family: var\(--font-mono\)", css), (
        "mct-table cells are not mono"
    )

    headers = [html.unescape(h) for h in re.findall(r"<th>(.*?)</th>", table)]
    assert headers == [
        "Claim ID",
        "Driver",
        "Vehicle",
        "Repair cost",
        "Coverage",
        "Complexity",
        "Fraud risk",
        "Recommendation",
    ]

    tbody = re.search(r"<tbody>(.*?)</tbody>", table, re.S)
    row_html = re.findall(r"<tr>(.*?)</tr>", tbody.group(1) if tbody else "", re.S)
    assert len(row_html) == 38, f"expected 38 rows, got {len(row_html)}"
    rows = {}
    for r in row_html:
        cells = [html.unescape(c) for c in re.findall(r"<td>(.*?)</td>", r)]
        if cells:
            rows[cells[0]] = dict(zip(headers, cells, strict=True))

    failures = []
    for cid, exp in EXPECTED_RECOMMENDATIONS.items():
        claim = CLAIMS_BY_ID[cid]
        res = _result(cid)
        r = claim.repair_estimate
        want = {
            "Claim ID": cid,
            "Driver": claim.driver.name,
            "Vehicle": f"{claim.vehicle.year} {claim.vehicle.make}",
            "Repair cost": f"AED {r.estimated_cost:,.0f}" if r else "—",
            "Coverage": "Clear" if res.coverage.is_covered else "Issues",
            "Complexity": res.scoring.complexity_score.value.upper(),
            "Fraud risk": res.scoring.fraud_risk_score.value.upper(),
            "Recommendation": REC_STAMP[exp][0],
        }
        row = rows.get(cid)
        if row is None:
            failures.append(f"{cid}: missing from bulk table")
            continue
        for col, want_val in want.items():
            if row.get(col) != want_val:
                failures.append(f"{cid}: {col}: {row.get(col)!r} != {want_val!r}")
    assert failures == []


def test_stats_metrics_match_label_distribution():
    """The three headline counts must equal the label distribution, not a
    separately computed tally that could drift from it."""
    at = _run()
    expected_counts = {label: 0 for label, _kind in REC_STAMP.values()}
    for exp in EXPECTED_RECOMMENDATIONS.values():
        expected_counts[REC_STAMP[exp][0]] += 1
    seen = {m.label: int(m.value) for m in at.metric}
    assert seen == {METRIC_OF_STAMP[stamp]: n for stamp, n in expected_counts.items()}


def test_every_claim_wraps_prose_values_in_mono_spans():
    """Brand mono rule regression: every money/date/identifier occurrence in
    the prose surfaces (narrative, coverage alerts, risk factors, incident
    note) renders inside a mono .mct-val span, the surrounding prose is
    unchanged, and the .mct-val CSS rule reaches the page (spans without it
    would silently render in the body face)."""
    at = _run()
    failures = []

    css = next((v for v in _markdown(at) if ".mct-val" in v), "")
    if not re.search(r"\.mct-val\s*\{[^}]*font-family:\s*var\(--font-mono\)", css):
        failures.append("injected CSS lacks .mct-val { font-family: var(--font-mono) ... }")

    for cid in EXPECTED_RECOMMENDATIONS:
        at.sidebar.selectbox[0].set_value(cid)
        at.run()
        if at.exception:
            failures.append(f"{cid}: crashed: {at.exception[0]}")
            continue
        res = _result(cid)
        claim = CLAIMS_BY_ID[cid]
        vals = _markdown(at)

        # Narrative: content intact once spans are stripped, values wrapped.
        want_body = _expected_narrative_body(res.narrative)
        got_narr = next(
            (v for v in vals if _strip_vals(html.unescape(v)).strip() == want_body), None
        )
        if got_narr is None:
            failures.append(f"{cid}: narrative body not rendered intact")
        else:
            bad = _unwrapped_values(got_narr)
            if bad:
                failures.append(f"{cid}: narrative values not in mono spans: {bad}")

        # Coverage alerts: expected texts in order, values wrapped.
        raw_alerts = [
            m for v in vals for m in re.findall(r'<div class="mct-alert[^"]*">(.*?)</div>', v, re.S)
        ]
        got_alerts = [_strip_vals(html.unescape(a)) for a in raw_alerts]
        if got_alerts != _expected_alerts(res):
            failures.append(f"{cid}: alerts changed: {got_alerts!r} != {_expected_alerts(res)!r}")
        bad = [b for a in raw_alerts for b in _unwrapped_values(a)]
        if bad:
            failures.append(f"{cid}: alert values not in mono spans: {bad}")

        # Risk factors: factor text intact, any embedded values wrapped.
        for title, factors in (
            ("Complexity", res.scoring.complexity_factors),
            ("Fraud risk", res.scoring.fraud_risk_factors),
        ):
            panel = next((v for v in vals if f'mct-card__title">{title}<' in v), None)
            if panel is None:
                failures.append(f"{cid}: {title} panel missing")
                continue
            raw_lis = re.findall(r"<li>(.*?)</li>", panel)
            if factors:
                got_lis = [_strip_vals(html.unescape(x)) for x in raw_lis]
                if got_lis != factors:
                    failures.append(f"{cid}: {title} factors changed: {got_lis!r} != {factors!r}")
                bad = [b for li in raw_lis for b in _unwrapped_values(li)]
                if bad:
                    failures.append(f"{cid}: {title} values not in mono spans: {bad}")
            elif "No factors recorded." not in panel:
                failures.append(f"{cid}: {title} empty-factor placeholder missing")

        # Incident note: description intact once spans are stripped.
        note = next((v for v in vals if 'class="mct-note"' in v), "")
        m = re.search(r'<div class="mct-note">(.*?)</div>', note, re.S)
        got_desc = _strip_vals(html.unescape(m.group(1))) if m else None
        if got_desc != claim.accident.description:
            failures.append(f"{cid}: incident description not rendered intact")
        if m:
            bad = _unwrapped_values(m.group(1))
            if bad:
                failures.append(f"{cid}: description values not in mono spans: {bad}")

    assert failures == []
