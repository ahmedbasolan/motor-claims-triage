# Motor Claims Triage & Decision-Support Copilot

A prototype claims triage system for UAE motor insurance that automates coverage checks, risk scoring, and decision recommendations. [MIT](LICENSE) licensed.

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

93 tests: `pytest tests/ -v` — engine and ground-truth labels, eval harness,
API endpoints (all 38 labels round-tripped over HTTP), and the dashboard
(each of the 38 claims round-tripped through the sidebar: verdict and
coverage stamps, every fact-grid figure, risk levels, prose values in mono,
plus the bulk table's columns and the headline metrics — all checked
against the claim data and the engine), plus a theme liveness check: every
Streamlit element the theme styles must still exist in the installed
version's frontend assets.
Run automatically on every push and PR by
GitHub Actions (`.github/workflows/ci.yml`): ruff check, ruff format, pytest,
on Python 3.10 (the `requires-python` floor) and 3.13.

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
than by reading the code, and each produced confidently wrong output: decisional
figures the data refuted, or presentation that contradicted the project's own
stated rules.

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

**Build: the declared setuptools floor rejected this file's own syntax.**
`build-system.requires` pinned `setuptools>=68.0` while the `license = "MIT"`
SPDX string (PEP 639) needs setuptools 77+, so a fresh install at the floor
*the project itself declared* failed while preparing metadata. Verified in
both directions: builds and emits `License-Expression: MIT` at 77.0.1, fails
at 76.1.0. The floor is now `>=77.0`. Found the same way as the scoring
defects — a stated figure (the floor) checked against the data (what the
file's own syntax requires) rather than against the code that was read.

**README: the stated test count lagged the suite.** After the endpoint
tests landed, the header still claimed 72 while `pytest` reported 85 — a
stated figure never re-checked against a run after the suite grew. Trivial
in isolation, but the README asserts its figures are audited, so a stale
one undercuts the claim it makes. The count now states what each suite
covers, updated in the same commit as any test addition.

**Typography: money, dates and identifiers rendered in the body face.**
The brand book calls the mono rule "the spine of the system" — values a
handler reads back on a call are mono wherever they appear, *"prose is
never mono; IDs are never sans"* — and the design section below promises
"IBM Plex Mono for every claim ID, date and AED figure". Checked against
what the dashboard actually renders, that claim was false on every claim
shown: the narrative's repair/excess/payout figures and policy numbers,
the coverage alerts' dates (*"Accident date 2024-05-15 is outside policy
period (2024-07-01 to 2025-07-01)"*) and registrations, and the
new-policy fraud factor's AED figure all sat in prose surfaces with no
font rule, so they inherited the body sans. The figures themselves were
correct — what was confidently wrong was every stated claim about how
they are presented. Values are now wrapped in `.mct-val` mono spans at
render time (`theme.inline_values()`; the prose around them stays sans,
per the brand book) with engine output untouched, and the regression test
fails with 42 findings against the pre-fix app.

**Design: the bulk table never rendered mono — a dead selector, and a
canvas no CSS can reach.** The fix above verified its spans and its CSS
text, but the table's rule targeted `[data-testid="stArrowTable"]`, and
that testid appears in **zero of the 310 frontend bundles** Streamlit
1.64 ships: `st.dataframe` (and `st.table`, now migrated to the same
grid) draws its cells on a canvas, so there is no DOM node any
`font-family` rule could reach. The README's "mono for every … AED
figure" and the brand book's "Table: … mono cells at 13px" were still
false on the dashboard's largest surface — found by reviewing the
round-3 fix and verified by grepping what the installed Streamlit
actually renders, not by the audit, which compared cell values (all
correct) and could not see fonts. The table now renders as in-brand
HTML (`theme.data_table()`, `.mct-table`): sunken header, mono 13px
tabular cells, zebra `paper-50`, hairlines only — the brand table spec
is enforceable because the markup is ours. The review also closed two
smaller sans surfaces: the selectbox's open option list (a portaled
virtual dropdown, mono now inherited from a rule on its container) and
the policy-miss error message (names a policy number; now rendered
through the in-brand alert helper, which wraps values). Deliberate
non-change: durations and ratios inside factor sentences ("12 days
old", "78% of vehicle value") stay in the body face — the brand rule
binds money, identifiers and dates, and wrapping every duration would
put prose in mono. Cost of the table switch: the bulk view lost the
dataframe's interactive column sorting; the mono rule is "the spine of
the system", sorting was not.

**Design: nine theme selector targets styled nothing — the dead-selector
class, applied to the whole theme.** The table fix above proved a CSS
rule can target an element that does not exist and nothing catches it,
so every selector target in `app/theme.py` was checked the same way
against the shipped Streamlit 1.64 assets, matched as whole quoted
tokens (`stError` cannot pass on `stErrorBoundary` hits). Seven
data-testids styled nothing: `baseButton-primary`/`baseButton-secondary`
(the BaseButton family is gone upstream — buttons are `stButton`),
`stDivider`, and `stSuccess`/`stError`/`stWarning`/`stInfo` through the
alert block (only `stAlert` exists). Two data attributes were worse:
`data-baseweb="select"` was dropped upstream between the declared floor
and the installed version (33 hits in the 1.49.0 wheel, 0 in 1.64), and
`data-kind` has **never** appeared in any Streamlit asset — so the
brand's per-status alert tints ("tinted paper bg, 3px left rule in
status ink") matched nothing in any version ever supported: the spec now
lives only where the app controls the markup (`.mct-alert`), and a block
comment records why the native-alert tints are absent. The same probe
against the `streamlit>=1.49.0` floor found every testid for elements
the app actually renders present at the floor, so the floor claim holds
as stated. Regression: `tests/test_theme.py` parses the theme's CSS and
asserts every `data-testid`, data attribute and `.st*` class in it
occurs as a whole token in the installed Streamlit's assets — red on
the pre-fix tree with all nine dead targets, and an upstream rename now
fails CI loudly instead of silently unstyling the UI.

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
│   ├── test_core.py            # Unit + ground-truth tests
│   ├── test_api_config.py      # API configuration tests
│   ├── test_api_integration.py # Endpoint tests (all 38 labels round-tripped)
│   ├── test_eval.py            # Calibration harness tests
│   └── test_ui.py              # Dashboard tests (38 claims, every figure)
├── .github/workflows/ci.yml    # CI: ruff + pytest on push/PR
├── LICENSE                     # MIT
├── api.py                      # FastAPI endpoint
└── pyproject.toml              # Dependencies
```

## UAE Insurance Context

This prototype addresses CBUAE requirements for:
- Explainable AI decisions in claims processing
- Auditability of triage reasoning
- Consistent handling of coverage logic
- Fraud detection in motor claims
