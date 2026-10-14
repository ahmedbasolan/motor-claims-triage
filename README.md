# Motor Claims Triage & Decision-Support Copilot

A prototype claims triage system for UAE motor insurance that automates coverage checks, risk scoring, and decision recommendations.

**Status: prototype.** Logic is exercised against 38 synthetic claims and 8 synthetic
policies. It has never run against real claims, and the scoring thresholds are
unvalidated guesses, not calibrated against outcome data. The `eval/` package
measures that gap (see [Calibration](#calibration)) — it reports what outcomes
would need to say for the thresholds to be right, and which thresholds the
current data can even distinguish.

Every claim carries a ground-truth label (`EXPECTED_RECOMMENDATIONS` in
`src/mock_data.py`), and the dataset is built so that every rule in the engine
fires on at least one claim. Tests assert the engine reproduces the labels and
that each rule branch is exercised — a silent behaviour change fails the suite.

## Features

- **Coverage Verification**: Checks driver exclusions, vehicle matches, use-case restrictions, and policy validity
- **Complexity Scoring**: Evaluates multi-vehicle incidents, injuries, liability disputes, and repair cost ratios
- **Fraud Risk Detection**: Flags recently-purchased policies with high claims, repeated claims, and inconsistent stories
- **Recommendation Engine**: Fast-track / Standard Review / Investigate based on risk assessment
- **Narrative Generation**: Human-readable rationale for handler notes
- **API & UI**: FastAPI endpoint + Streamlit dashboard

## Rules implemented

| Area | Rules |
|---|---|
| Coverage | 3 hard checks (policy in force, driver not excluded, vehicle matches) + 4 use-case exclusions (`rental_use`, `ride_hailing_use`, `taxi_use`, `delivery_use`) detected from 6 description keywords + 1 third-party advisory |
| Complexity | 5 factors: multi-vehicle, injury reported, liability disputed, repair cost vs vehicle value (2 tiers), young/inexperienced driver |
| Fraud | 5 factors: recently-purchased policy with high claim, repeat claims in 90 days (2 tiers), story inconsistency (4 keyword families), thin documentation for a high-value estimate |
| Decision | 3 outcomes, each with a stated reason: fast-track, standard review, investigate |

72 tests: `pytest tests/ -v`

## Calibration

The engine is internally consistent — every rule verified against labelled
claims — but internal consistency cannot tell you whether 30 days is the right
"new policy" threshold. Only outcomes can. `eval/` is the harness that closes
that gap when outcome data exists:

```bash
python -m eval.harness    # calibration report + threshold sensitivity
```

- **Decision agreement** — where the engine's recommendation differs from what
  a human handler actually did. Volume of difference, not accuracy.
- **Indicator precision/recall** — for each fraud indicator, the share of
  flagged claims SIU confirmed (precision) and the share of confirmed fraud it
  caught (recall).
- **Threshold sensitivity** — needs no outcome data: sweeps every threshold in
  `src/scoring.py` and counts how many of the 38 labelled claims change
  recommendation. On the current dataset `NEW_POLICY_DAYS`, `REPEAT_WINDOW_DAYS`
  and `FR_HIGH_AT` move nothing at all (the data cannot distinguish them);
  only `CX_HIGH_AT` (up to 3 claims) and `HIGH_CLAIM_AED` (1 claim) currently
  change any decision — those are the guesses that matter most today.

`eval/SCHEMA.md` specifies exactly what an insurer partner would need to
supply — fields already recorded in ordinary claims handling, deidentified,
joined on claim ID only. `eval/demo_outcomes.json` is **synthetic** and
labelled as such: it demonstrates the harness, it validates nothing about the
engine.

## Defects found by auditing the logic and the stated figures

All were found by checking the rules and stated figures against the data rather
than by reading the code, and each produced confidently wrong output.

**Fraud: "new policy" was measured as reporting lag.** The indicator computed
`accident.date - submitted_at` and named the result `policy_age_days`. That gap
is the reporting lag, which is ~0 for every ordinary claim, so the rule fired on
any claim above AED 15,000. It flagged **9 of 25 claims and missed all 9
genuine cases** — the shortest-held policy in the dataset is 32 days. The
narrative told handlers *"New policy (0 days old) with high claim AED 62,000"*,
a fabricated fact, and escalated 4 claims to SIU investigation on it. `score_fraud_risk`
never received the `Policy`, so it could not compute a real age; the policy is now
threaded through and the rule is skipped rather than guessed when absent.

**Coverage: any use-case exclusion denied every use case.** The test was
`keyword in policy.excluded_uses or policy.excluded_uses`, and the second clause
made the first irrelevant. A policy excluding only `rental` also rejected
delivery claims; one excluding `ride_hailing` also rejected taxi claims. Denial
of a covered claim is the worst error this component can make, so the keyword is
now matched against the specific excluded code, on word boundaries, with the
platform aliases (`Uber`, `Careem`) resolving to `ride_hailing_use`.

Effect on the 25-claim set: fast-track 3 → 5, investigate 10 → 6, and all 6
remaining investigations have a stated, verifiable reason.

**Fraud: the repeat-claims window counted future claims.** The indicator tested
`(claim.accident.date - c.accident.date) <= 90 days` with no lower bound, so a
claim from the future yields a negative delta and passes: *"3 previous claims in
last 90 days"* could be three claims that had not happened yet. 15 of 25 claims
changed count under a correct `0 ≤ delta ≤ 90d` window, and the phantom factor
dominated the fraud score — 14 of 25 claims scored medium fraud, mostly on this
rule alone. The window is now bounded on both sides. Effect on the 25-claim set:
fast-track 5 → 10, standard review 14 → 9, investigate unchanged at 6.


**Narrative: the estimated payout ignored the policy limit.** The financial
summary computed `repair − excess` and reported it as the estimated net payout
without ever consulting `max_sum_insured` — a AED 120,000 repair on a AED
100,000 policy was reported as *"Estimated Net Payout: AED 119,700"*, a figure
the policy could never pay, and a handler reading it would reserve too much.
The payout is now capped at the sum insured, and the cap is stated whenever it
binds. This was found by auditing the narrative's stated figures against the
policy data — the same failure mode as the scoring defects: a confidently
asserted fact that the data contradicts.

**Narrative: denied and third-party claims were quoted a payout.** Every
uncovered claim still printed an *Estimated Net Payout* — an excluded-driver
claim read *"AED 2,000"* — so a handler skimming would reserve against a claim
the engine recommends investigating for denial. Third-party policies, which do
not cover own-vehicle repair, were quoted a payout from the own-vehicle
estimate too. The figure is now withheld when coverage failed, and stated in
liability terms for third-party cover.

**Fraud: claims predating inception were narrated as "new policies."** The
recently-purchased-policy rule tested only `age < 30`, so a negative age — a
claim submitted before the policy started — passed, and the narrative stated
*"New policy (-42 days old)"*. Pre-inception is a coverage failure, not a fraud
factor; the window is now `0 ≤ age < 30`, matching the bounded-window
discipline the repeat-claims fix established.

**Coverage: driver and registration checks were exact-string matches.**
`"john smith"` did not match an exclusion list naming `"John Smith"`, so an
excluded driver's claim passed; `"a-12345"` against policy `"A-12345"` raised
`vehicle_mismatch` and denied a covered claim over formatting. Both sides now
compare case- and separator-insensitively, and the repeat-claims window groups
drivers the same way (shared `driver_key`), so prior claims are not missed
where a name was typed differently between systems.

**Mock data: accident dates were clamped, fabricating same-day accidents.**
The date builder subtracted days within a single month, so any `days_ago ≥ 14`
landed on the same day — six claims labeled 14–30 days apart shared one
accident date, compressing the repeat-claims window the dataset exists to
exercise. Dates are now real subtractions.

Also fixed in the same pass: the `streamlit` floor was raised to 1.49.0 to
match the `width="stretch"` API the UI uses (a fresh install on the old floor
crashed at the bulk table), and the API's CORS no longer pairs a wildcard
origin with credentials, which browsers reject; origins are configurable via
`CORS_ORIGINS`.

## Design system — "Dossier"

The UI runs on a branded design system in `brand/` (see `brand/BRAND.md` for the
full brand book). Warm paper stock, ink, oxblood rubber stamps, archival green
primary; Source Serif 4 headings, IBM Plex Sans body, IBM Plex Mono for every
claim ID, date and AED figure. Three verdicts, three inks, fixed mapping:

| Verdict | Ink |
|---|---|
| Fast-track / covered | Archival green `#2C4F43` |
| Standard review | Ochre `#9A7B3F` |
| Investigate / exclusion | Oxblood `#8C2F39` |

Tokens live in `brand/tokens.json` (source of truth) and `brand/tokens.css`;
the Streamlit theme is `app/theme.py` + `.streamlit/config.toml`. Changes flow
from tokens to app — never the reverse. The brand book's anti-pattern list
(gradients, pure black/white, emoji icons, neon status colors, radius > 3px)
is enforced as review policy.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run API
python api.py
# Or: uvicorn api:app --reload --port 8000

# Run Streamlit UI
streamlit run app/ui.py

# Run tests
pytest tests/ -v
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/claims` | GET | List all mock claims |
| `/claims/{id}` | GET | Get claim details |
| `/policies` | GET | List all policies |
| `/triage_claim` | POST | Triage a new claim |
| `/triage_claim/{id}` | POST | Triage an existing claim |
| `/triage_all` | GET | Triage all claims |

## Project Structure

```
motor-claims-triage/
├── brand/
│   ├── BRAND.md           # Brand book (voice, color, type, stamps, anti-slop rules)
│   ├── tokens.json        # Design tokens: primitive → semantic → component
│   ├── tokens.css         # CSS variables generated from the token set
│   └── mark.svg           # Stamp mark (favicon)
├── .streamlit/
│   └── config.toml        # Base Streamlit theme (Dossier palette)
├── src/
│   ├── models.py          # Pydantic data models
│   ├── coverage.py        # Coverage check logic
│   ├── scoring.py         # Complexity & fraud scoring
│   ├── recommendation.py  # Decision engine
│   ├── narrative.py       # Rationale generation
│   ├── triage.py          # Main orchestrator
│   └── mock_data.py       # 38 labelled claims + 8 policies
├── app/
│   ├── theme.py           # Dossier CSS + stamp/fact-grid/note helpers
│   └── ui.py              # Streamlit dashboard
├── eval/
│   ├── harness.py          # Calibration: agreement, precision/recall, sensitivity
│   ├── outcomes.py         # Outcome-record schema (what a partner supplies)
│   ├── SCHEMA.md           # Data contract for closing the calibration gap
│   └── demo_outcomes.json  # SYNTHETIC demo data (not real outcomes)
├── tests/
│   ├── test_core.py        # Unit + ground-truth tests
│   ├── test_api_config.py  # API configuration tests
│   └── test_eval.py        # Calibration harness tests
├── api.py                 # FastAPI endpoint
└── pyproject.toml         # Dependencies
```

## UAE Insurance Context

This prototype addresses CBUAE requirements for:
- Explainable AI decisions in claims processing
- Auditability of triage reasoning
- Consistent handling of coverage logic
- Fraud detection in motor claims
