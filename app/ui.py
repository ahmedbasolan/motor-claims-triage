"""Streamlit UI for Motor Claims Triage Copilot."""

import os
import sys

import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mock_data import POLICIES, generate_claims
from src.models import Recommendation, RiskLevel
from src.triage import triage_claim

st.set_page_config(
    page_title="Motor Claims Triage Copilot",
    page_icon="🚗",
    layout="wide",
)

st.title("Motor Claims Triage & Decision-Support Copilot")
st.markdown("---")

# Load data
POLICY_MAP = {p.policy_number: p for p in POLICIES}
ALL_CLAIMS = generate_claims()

# Sidebar - Claim Selection
st.sidebar.header("Select Claim")
claim_options = {c.claim_id: f"{c.claim_id} - {c.driver.name}" for c in ALL_CLAIMS}
selected_id = st.sidebar.selectbox(
    "Choose a claim to triage:",
    options=list(claim_options.keys()),
    format_func=lambda x: claim_options[x],
)

# Find selected claim
selected_claim = next(c for c in ALL_CLAIMS if c.claim_id == selected_id)
policy = POLICY_MAP[selected_claim.policy_number]

# Run triage
driver_claims = [c for c in ALL_CLAIMS if c.driver.name == selected_claim.driver.name]
result = triage_claim(selected_claim, policy, driver_claims)

# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Claim Details")
    st.markdown(f"**Claim ID:** {selected_claim.claim_id}")
    st.markdown(f"**Policy:** {selected_claim.policy_number}")
    st.markdown(f"**Driver:** {selected_claim.driver.name} (Age: {selected_claim.driver.age})")
    st.markdown(f"**License Tenure:** {selected_claim.driver.license_tenure_years} years")
    st.markdown(
        f"**Vehicle:** {selected_claim.vehicle.year} {selected_claim.vehicle.make} "
        f"{selected_claim.vehicle.model}"
    )
    st.markdown(f"**Registration:** {selected_claim.vehicle.registration_number}")
    st.markdown(f"**Vehicle Value:** AED {selected_claim.vehicle.estimated_value:,.0f}")
    st.markdown(f"**Accident Date:** {selected_claim.accident.date.strftime('%Y-%m-%d %H:%M')}")
    st.markdown(f"**Location:** {selected_claim.accident.location}")
    st.markdown(f"**Description:** {selected_claim.accident.description}")
    if selected_claim.repair_estimate:
        cost = selected_claim.repair_estimate.estimated_cost
        st.markdown(f"**Repair Estimate:** AED {cost:,.0f}")
        st.markdown(f"**Garage:** {selected_claim.repair_estimate.garage_name}")

with col2:
    st.subheader("Triage Result")

    # Recommendation badge
    rec_colors = {
        Recommendation.FAST_TRACK: "green",
        Recommendation.STANDARD_REVIEW: "orange",
        Recommendation.INVESTIGATE: "red",
    }
    rec_labels = {
        Recommendation.FAST_TRACK: "FAST-TRACK",
        Recommendation.STANDARD_REVIEW: "STANDARD REVIEW",
        Recommendation.INVESTIGATE: "INVESTIGATE",
    }

    rec_label = rec_labels[result.recommendation]
    rec_color = rec_colors[result.recommendation]
    st.markdown(f"### Recommendation: :{rec_color}[{rec_label}]")

    # Coverage
    st.markdown("#### Coverage Check")
    if result.coverage.is_covered:
        st.success("Coverage: CLEAR")
    else:
        st.error("Coverage: ISSUES DETECTED")
        for exclusion in result.coverage.exclusions_triggered:
            st.warning(f"Exclusion: {exclusion.replace('_', ' ').title()}")

    for note in result.coverage.notes:
        st.info(note)

    # Scoring
    st.markdown("#### Risk Scoring")

    risk_colors = {RiskLevel.LOW: "green", RiskLevel.MEDIUM: "orange", RiskLevel.HIGH: "red"}

    score_col1, score_col2 = st.columns(2)
    with score_col1:
        st.markdown(
            f"**Complexity:** :{risk_colors[result.scoring.complexity_score]}"
            f"[{result.scoring.complexity_score.value.upper()}]"
        )
        for factor in result.scoring.complexity_factors:
            st.markdown(f"- {factor}")

    with score_col2:
        st.markdown(
            f"**Fraud Risk:** :{risk_colors[result.scoring.fraud_risk_score]}"
            f"[{result.scoring.fraud_risk_score.value.upper()}]"
        )
        for factor in result.scoring.fraud_risk_factors:
            st.markdown(f"- {factor}")

# Narrative section
st.markdown("---")
st.subheader("Triage Rationale")
st.markdown(result.narrative)

# Bulk triage view
st.markdown("---")
st.subheader("Bulk Triage Overview")

bulk_results = []
for claim in ALL_CLAIMS:
    p = POLICY_MAP.get(claim.policy_number)
    if p:
        dc = [c for c in ALL_CLAIMS if c.driver.name == claim.driver.name]
        r = triage_claim(claim, p, dc)
        repair = claim.repair_estimate
        repair_str = f"AED {repair.estimated_cost:,.0f}" if repair else "N/A"
        bulk_results.append(
            {
                "Claim ID": claim.claim_id,
                "Driver": claim.driver.name,
                "Vehicle": f"{claim.vehicle.year} {claim.vehicle.make}",
                "Repair Cost": repair_str,
                "Coverage": "Clear" if r.coverage.is_covered else "Issues",
                "Complexity": r.scoring.complexity_score.value.upper(),
                "Fraud Risk": r.scoring.fraud_risk_score.value.upper(),
                "Recommendation": rec_labels[r.recommendation],
            }
        )

st.dataframe(bulk_results, use_container_width=True)

# Stats
st.markdown("---")
st.subheader("Triage Statistics")
fast_count = sum(1 for r in bulk_results if "FAST-TRACK" in r["Recommendation"])
standard_count = sum(1 for r in bulk_results if "STANDARD" in r["Recommendation"])
investigate_count = sum(1 for r in bulk_results if "INVESTIGATE" in r["Recommendation"])

stat_col1, stat_col2, stat_col3 = st.columns(3)
stat_col1.metric("Fast-Track", fast_count)
stat_col2.metric("Standard Review", standard_count)
stat_col3.metric("Investigate", investigate_count)
