"""UI tests: the Streamlit dashboard via streamlit.testing.v1.AppTest.

The unit tests verify the engine and the API tests verify the HTTP surface;
these verify what a handler actually sees. The load-bearing test is
test_every_claim_shows_ground_truth_stamp: each of the 38 labelled claims is
selected in the sidebar and the rendered stamp must carry its
EXPECTED_RECOMMENDATIONS label - a dashboard that shows the wrong verdict,
stale details, or crashes on selection fails here even when the engine and
API are correct.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streamlit.testing.v1 import AppTest

from src.mock_data import EXPECTED_RECOMMENDATIONS

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


def _run() -> AppTest:
    at = AppTest.from_file(_APP_PATH, default_timeout=60)
    at.run()
    return at


def _markdown(at: AppTest) -> list[str]:
    return [str(m.value) for m in at.markdown]


def _spans(at: AppTest) -> list[str]:
    return [v for v in _markdown(at) if 'class="mct-stamp mct-stamp--' in v]


def test_dashboard_renders_without_exception():
    at = _run()
    assert not at.exception, f"dashboard crashed on load: {at.exception}"


def test_sidebar_lists_every_labelled_claim():
    at = _run()
    # options carry format_func output ("CLM-001 - Name"); the raw values are
    # claim ids, which is what set_value accepts - verified by the round-trip
    # test below.
    options = at.sidebar.selectbox[0].options
    ids = {str(o).split(" ")[0] for o in options}
    assert ids == set(EXPECTED_RECOMMENDATIONS)


def test_default_selection_shows_first_claim():
    at = _run()
    assert at.sidebar.selectbox[0].value == "CLM-001"
    label, kind = REC_STAMP[EXPECTED_RECOMMENDATIONS["CLM-001"]]
    span = f'<span class="mct-stamp mct-stamp--{kind}">{label}</span>'
    assert any(span in v for v in _spans(at)), f"stamp {label!r} not rendered"


def test_every_claim_shows_ground_truth_stamp():
    """Round-trip all 38 claims through the sidebar selector: the stamp must
    carry the ground-truth label and the fact grid must show the selected
    claim's id (not a stale one)."""
    at = _run()
    failures = []
    for cid, expected in EXPECTED_RECOMMENDATIONS.items():
        at.sidebar.selectbox[0].set_value(cid)
        at.run()
        if at.exception:
            failures.append(f"{cid}: crashed: {at.exception[0]}")
            continue
        label, kind = REC_STAMP[expected]
        span = f'<span class="mct-stamp mct-stamp--{kind}">{label}</span>'
        if not any(span in v for v in _spans(at)):
            failures.append(f"{cid}: expected stamp {label!r} not rendered")
        if not any(f"<dd>{cid}</dd>" in v for v in _markdown(at)):
            failures.append(f"{cid}: fact grid does not show {cid}")
    assert failures == []


def test_bulk_table_matches_ground_truth():
    """The bulk view's recommendation column is checked against the labels
    for all 38 claims - the whole-table equivalent of the stamp round-trip."""
    at = _run()
    df = at.dataframe[0].value
    assert len(df) == 38
    got = dict(zip(df["Claim ID"], df["Recommendation"]))
    expected = {cid: REC_STAMP[exp][0] for cid, exp in EXPECTED_RECOMMENDATIONS.items()}
    mismatches = {
        cid: (expected[cid], got.get(cid)) for cid in expected if got.get(cid) != expected[cid]
    }
    assert mismatches == {}


def test_stats_metrics_match_label_distribution():
    """The three headline counts must equal the label distribution, not a
    separately computed tally that could drift from it."""
    at = _run()
    expected_counts = {label: 0 for label, _kind in REC_STAMP.values()}
    for exp in EXPECTED_RECOMMENDATIONS.values():
        expected_counts[REC_STAMP[exp][0]] += 1
    seen = {m.label: int(m.value) for m in at.metric}
    assert seen == {METRIC_OF_STAMP[stamp]: n for stamp, n in expected_counts.items()}
