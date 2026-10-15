"""Streamlit UI for Motor Claims Triage Copilot — Dossier theme."""

import os
import re
import sys

import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.theme import (
    aed,
    alert_html,
    data_table,
    fact_grid,
    fmt_dt,
    inject_theme,
    inline_values,
    note_block,
    page_header,
    risk_panel,
    section_label,
    stamp,
    wordmark,
)
from src.mock_data import POLICIES, generate_claims
from src.models import Recommendation, RiskLevel
from src.triage import triage_with_context

st.set_page_config(
    page_title="Motor Claims Triage",
    page_icon=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brand", "mark.svg"
    ),
    layout="wide",
)
inject_theme()

REC_STYLE = {
    Recommendation.FAST_TRACK: ("FAST-TRACK", "pass"),
    Recommendation.STANDARD_REVIEW: ("STANDARD REVIEW", "caution"),
    Recommendation.INVESTIGATE: ("INVESTIGATE", "danger"),
}
RISK_STYLE = {
    RiskLevel.LOW: ("Low", "pass"),
    RiskLevel.MEDIUM: ("Medium", "caution"),
    RiskLevel.HIGH: ("High", "danger"),
}

# Load data
POLICY_MAP = {p.policy_number: p for p in POLICIES}
ALL_CLAIMS = generate_claims()

# Sidebar — wordmark + claim selection
st.sidebar.markdown(wordmark(), unsafe_allow_html=True)
st.sidebar.markdown(section_label("Select claim"), unsafe_allow_html=True)
claim_options = {c.claim_id: f"{c.claim_id} — {c.driver.name}" for c in ALL_CLAIMS}
selected_id = st.sidebar.selectbox(
    "Claim file",
    options=list(claim_options.keys()),
    format_func=lambda x: claim_options[x],
    label_visibility="collapsed",
)

# Find selected claim
selected_claim = next(c for c in ALL_CLAIMS if c.claim_id == selected_id)

# Run triage (shared wiring: policy resolution + driver context)
result = triage_with_context(selected_claim, POLICY_MAP, ALL_CLAIMS)
if result is None:
    # In-brand alert: st.error cannot carry the mono value spans, and this
    # message names a policy number ("IDs are never sans").
    st.markdown(
        alert_html(
            f"Policy {selected_claim.policy_number} not found - claim cannot be triaged.",
            "danger",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

# Page header
st.markdown(
    page_header("Motor Claims Triage", "Decision-support copilot · UAE motor · Prototype"),
    unsafe_allow_html=True,
)

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown(section_label("Claim details"), unsafe_allow_html=True)

    repair = selected_claim.repair_estimate
    facts = [
        ("Claim ID", selected_claim.claim_id),
        ("Policy", selected_claim.policy_number),
        ("Driver", selected_claim.driver.name),
        ("Age", f"{selected_claim.driver.age} years"),
        ("Licence held", f"{selected_claim.driver.license_tenure_years} years"),
        (
            "Vehicle",
            f"{selected_claim.vehicle.year} {selected_claim.vehicle.make} "
            f"{selected_claim.vehicle.model}",
        ),
        ("Registration", selected_claim.vehicle.registration_number),
        ("Vehicle value", aed(selected_claim.vehicle.estimated_value)),
        ("Accident", fmt_dt(selected_claim.accident.date)),
        ("Location", selected_claim.accident.location),
        ("Repair estimate", aed(repair.estimated_cost) if repair else "—"),
        ("Garage", repair.garage_name if repair else "—"),
        ("Vehicles involved", str(selected_claim.accident.num_vehicles_involved)),
        (
            "Injury reported",
            "Yes" if selected_claim.accident.injury_reported else "No",
        ),
        (
            "Liability disputed",
            "Yes" if selected_claim.accident.liability_disputed else "No",
        ),
    ]
    st.markdown(fact_grid(facts), unsafe_allow_html=True)

    st.markdown(section_label("Incident description"), unsafe_allow_html=True)
    st.markdown(note_block(selected_claim.accident.description), unsafe_allow_html=True)

with col2:
    st.markdown(section_label("Triage result"), unsafe_allow_html=True)

    rec_label, rec_kind = REC_STYLE[result.recommendation]
    st.markdown(stamp(rec_label, rec_kind), unsafe_allow_html=True)

    # Coverage
    st.markdown(section_label("Coverage check"), unsafe_allow_html=True)
    if result.coverage.is_covered:
        st.markdown(stamp("Covered", "pass", compact=True), unsafe_allow_html=True)
    else:
        st.markdown(stamp("Exclusion triggered", "danger", compact=True), unsafe_allow_html=True)
        for exclusion in result.coverage.exclusions_triggered:
            label = exclusion.replace("_", " ").strip().title()
            st.markdown(alert_html(f"Exclusion — {label}", "danger"), unsafe_allow_html=True)

    for note in result.coverage.notes:
        st.markdown(alert_html(note, "info"), unsafe_allow_html=True)

    # Scoring
    st.markdown(section_label("Risk scoring"), unsafe_allow_html=True)
    score_col1, score_col2 = st.columns(2)

    c_label, c_kind = RISK_STYLE[result.scoring.complexity_score]
    with score_col1:
        st.markdown(
            risk_panel("Complexity", c_label, c_kind, result.scoring.complexity_factors),
            unsafe_allow_html=True,
        )

    f_label, f_kind = RISK_STYLE[result.scoring.fraud_risk_score]
    with score_col2:
        st.markdown(
            risk_panel("Fraud risk", f_label, f_kind, result.scoring.fraud_risk_factors),
            unsafe_allow_html=True,
        )

# Narrative section — strip the generator's own H1 (the eyebrow above is the
# heading here); render the rest as real markdown so bold labels and lists work.
# Values (money, policy numbers) go into mono spans via inline_values().
narrative_body = re.sub(r"^##[^\n]*\n+", "", result.narrative).strip()
st.markdown(section_label("Triage rationale"), unsafe_allow_html=True)
st.markdown(inline_values(narrative_body), unsafe_allow_html=True)

# Bulk triage view
st.markdown(section_label("Bulk triage — all claims"), unsafe_allow_html=True)

bulk_results = []
for claim in ALL_CLAIMS:
    r = triage_with_context(claim, POLICY_MAP, ALL_CLAIMS)
    if r is not None:
        repair = claim.repair_estimate
        repair_str = aed(repair.estimated_cost) if repair else "—"
        bulk_results.append(
            {
                "Claim ID": claim.claim_id,
                "Driver": claim.driver.name,
                "Vehicle": f"{claim.vehicle.year} {claim.vehicle.make}",
                "Repair cost": repair_str,
                "Coverage": "Clear" if r.coverage.is_covered else "Issues",
                "Complexity": r.scoring.complexity_score.value.upper(),
                "Fraud risk": r.scoring.fraud_risk_score.value.upper(),
                "Recommendation": REC_STYLE[r.recommendation][0],
            }
        )

# In-brand HTML table: the dataframe grid draws cells on a canvas and
# cannot be styled to the brand (mono cells), so it renders via
# theme.data_table() like the other signature components.
st.markdown(data_table(bulk_results), unsafe_allow_html=True)

# Stats
st.markdown(section_label("Triage statistics"), unsafe_allow_html=True)
fast_count = sum(1 for r in bulk_results if r["Recommendation"] == "FAST-TRACK")
standard_count = sum(1 for r in bulk_results if r["Recommendation"] == "STANDARD REVIEW")
investigate_count = sum(1 for r in bulk_results if r["Recommendation"] == "INVESTIGATE")

stat_col1, stat_col2, stat_col3 = st.columns(3)
stat_col1.metric("Fast-track", fast_count)
stat_col2.metric("Standard review", standard_count)
stat_col3.metric("Investigate", investigate_count)
