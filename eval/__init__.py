"""Calibration harness: measures the triage engine against claim outcomes.

The engine's thresholds are prototype defaults, not calibrated against real
data. This package closes that gap when outcome data exists:

- eval.outcomes  - the schema an insurer partner supplies (one record per
                   settled claim: what the handler did, what SIU found, what
                   was actually paid)
- eval.harness   - per-indicator precision/recall against confirmed fraud,
                   decision-level agreement with handlers, and threshold
                   sensitivity sweeps

Run the demo on synthetic outcomes:  python -m eval.harness
"""
