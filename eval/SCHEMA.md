# Outcome data schema

The calibration harness (`eval/`) measures the triage engine against what
actually happened to claims. This document specifies what an insurer partner
would need to supply, so the gap the README calls "unvalidated guesses" can
be closed with data instead of opinion.

## Why this data

Every threshold in `src/scoring.py` — 30 days for "new policy", AED 15,000
for "high claim", the 90-day repeat window, the medium/high cut points — is a
prototype default. The engine is now internally consistent and every rule is
verified against labelled synthetic claims, but internal consistency cannot
tell you whether 30 days is the right threshold. Only outcomes can.

## File format

JSON, one record per settled claim, validated by `eval.outcomes.OutcomeSet`:

```json
{
  "outcomes": [
    {
      "claim_id": "CLM-001",
      "handler_decision": "fast_track",
      "fraud_confirmed": false,
      "amount_paid": 3000.0,
      "settled_on": "2024-10-02",
      "notes": "Settled at garage's quoted price."
    }
  ]
}
```

## Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `claim_id` | string | yes | Matches the engine's claim ID. Duplicates are rejected at load. |
| `handler_decision` | `fast_track` \| `standard_review` \| `investigate` | yes | What a human handler actually did — the practice the engine is compared against. Not ground truth: handlers can be wrong too, which is why the fraud verdict is tracked separately. |
| `fraud_confirmed` | bool \| null | no | SIU's finding, where investigation happened. `null` means *never investigated* — kept distinct from *investigated and cleared* (`false`). Metrics depending on this skip nulls and say so. |
| `amount_paid` | float \| null | no | Final net settlement, after excess. `null` if unpaid or not yet settled. |
| `settled_on` | date | no | Date the claim reached a final state. |
| `notes` | string | no | Handler's free text; carried into reports, never scored. |

## What the harness produces

1. **Decision agreement** — where the engine's recommendation differs from
   the handler's actual decision. Volume of difference, not accuracy.
2. **Indicator precision/recall** — for each fraud indicator (new policy,
   repeat claims, inconsistency, thin documentation): of the claims it
   flagged, the share SIU confirmed (precision); of the confirmed fraud
   claims, the share it caught (recall). An indicator with low precision
   wastes investigator time; low recall misses fraud.
3. **Threshold sensitivity** — needs no outcomes at all: sweeps each
   threshold and counts label changes across the 38-claim set. Run it today
   (`python -m eval.harness`) to see which guesses currently matter most.

## Assembly notes for a partner extract

- One record per claim **as it was finally decided**, not as the engine
  would decide it. Extract independently of any triage run.
- `handler_decision` should be the decision recorded *before* the engine's
  output was shown to the handler, where such history exists; otherwise the
  agreement metric measures the engine agreeing with itself.
- Deidentified claim IDs are fine; the harness joins on ID only. No names,
  plates, or free text are required for any metric.
- A few hundred settled claims with SIU verdicts is enough for indicator
  precision/recall to say something; the sensitivity report is useful from
  day one with zero outcomes.

## Honest limits

- The harness reports agreement with handlers, not correctness. A
  confirmed-fraud verdict is the one field that approximates truth, and only
  for claims that were investigated.
- Precision computed on a partner's historically-investigated subset is
  biased toward what the *old* process flagged. Recall is the more honest
  number until the engine's own escalations have been adjudicated.
- `demo_outcomes.json` is synthetic. It demonstrates the harness; it
  validates nothing about the engine.
