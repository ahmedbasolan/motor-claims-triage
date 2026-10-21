# Motor Claims Triage & Decision-Support Copilot

A prototype claims triage system for UAE motor insurance that automates coverage checks, risk scoring, and decision recommendations. [MIT](LICENSE) licensed.

**Status: prototype.** Logic is exercised against 38 synthetic claims and 8 synthetic
policies. It has never run against real claims, and the scoring thresholds are
unvalidated guesses, not calibrated against outcome data. The `eval/` package
measures that gap (see [Calibration](#calibration)) — it reports what outcomes
would need to say for the thresholds to be right, and which thresholds the
current data can even distinguish.

Every claim carries a ground-truth label (`EXPECTED_RECOMMENDATIONS` in
`motor_claims/mock_data.py`), and the dataset is built so that every rule in the engine
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

105 tests: `pytest tests/ -v` — engine and ground-truth labels, eval harness,
API endpoints (all 38 labels round-tripped over HTTP, plus outcome capture at
`/feedback`), and the dashboard
(each of the 38 claims round-tripped through the sidebar: verdict and
coverage stamps, every fact-grid figure, risk levels, prose values in mono,
plus the bulk table's columns and the headline metrics — all checked
against the claim data and the engine), a theme liveness check (every
Streamlit element the theme styles must still exist in the installed
version's frontend assets), and six in-browser render checks that read
computed styles out of a real Chromium — fonts, tints and DOM structure,
the surfaces AppTest cannot see. The render checks need
`pip install playwright && python -m playwright install chromium` and
skip where Chromium is absent.
Run automatically on every push and PR by
GitHub Actions (`.github/workflows/ci.yml`): ruff check (with the B, C4,
SIM and RUF rule families), ruff format, mypy over `motor_claims`/`app`/`eval`/`api.py`,
pytest on Python 3.10 (the `requires-python` floor) and 3.13, plus a
render job that installs Chromium and treats an unlaunchable browser as
a failure rather than a skip.

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
  `motor_claims/scoring.py` and counts how many of the 38 labelled claims change
  recommendation. On the current dataset `NEW_POLICY_DAYS`, `REPEAT_WINDOW_DAYS`
  and `FR_HIGH_AT` move nothing at all (the data cannot distinguish them);
  only `CX_HIGH_AT` (up to 3 claims) and `HIGH_CLAIM_AED` (1 claim) currently
  change any decision — those are the guesses that matter most today.

`eval/SCHEMA.md` specifies exactly what an insurer partner would need to
supply — fields already recorded in ordinary claims handling, deidentified,
joined on claim ID only. `eval/demo_outcomes.json` is **synthetic** and
labelled as such: it demonstrates the harness, it validates nothing about the
engine.

Until that partner data exists, `POST /feedback` lets the prototype accrue its
own calibration-shaped data: the body **is** the harness schema
(`eval.outcomes.ClaimOutcome`), validated field-for-field, and each accepted
record is appended as one JSON per line to `FEEDBACK_PATH` (default
`eval/captured_outcomes.jsonl`, gitignored) — a file the harness reads as-is.
The response freezes the engine's own recommendation alongside the handler's
decision, and a duplicate `claim_id` is refused (409) so the extract keeps
OutcomeSet's one-outcome-per-claim invariant from the moment it is written.
Captured demo data is not evidence about real claims, but the capture loop
is the same one a pilot would run.

## Defects found by auditing the logic and the stated figures

All were found by checking the rules and stated figures against the data rather
than by reading the code, and each produced confidently wrong output: decisional
figures the data refuted, or presentation that contradicted the project's own
stated rules. The regulatory entry at the end was found the same way — a stated
claim checked against its primary source instead of against the code.

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

**Typography: the sidebar's claim ID rendered in Streamlit's default
sans — a rule against an element that does not exist.** The mono rule
("IDs are never sans", the brand's spine) had been verified as markup
and CSS text for two rounds; nothing had read a rendered pixel. The new
in-browser suite (`tests/test_render_browser.py`) starts the real app
and reads computed styles out of a real Chromium — and on its first
run, the most prominent identifier on the dashboard, the claim file
always on display in the sidebar selector, computed to Streamlit's
default face. The theme's rule targeted
`[data-testid="stSelectbox"] div[role="button"]` — BaseWeb-era markup.
The current selectbox is a react-aria ComboBox: the selected value
("CLM-001 – …") lives in `input[role="combobox"]`, and no
`div[role="button"]` exists anywhere in the rendered tree, so the rule
had been styling nothing while the ID on display was sans. The rule now
targets the element that actually carries the ID, and the regression
test asserts the computed font on that input.

**Typography: prose rendered in "Source Sans", not the brand's IBM Plex
Sans.** The same instrument, the next assertion: computed
font-family on every markdown container was `"Source Sans", sans-serif`.
The theme set the brand body face only on `.stApp` — inheritance — and
Streamlit's own rules on `[data-testid="stMarkdownContainer"]` beat
inheritance directly, so every prose surface in the app (narrative,
eyebrows, section labels) wore Streamlit's default typeface while the
mono values inside it were finally correct. The other half of the mono
pairing — "prose is never mono" — had been true all along; what nobody
checked was that prose was in the *brand* face. Markdown containers and
their `p`/`li` now carry an explicit body-font rule; the render test
asserts both sides of the pairing on one page (container sans, values
mono).

**Regulatory: "CBUAE requirements" overstated guidance as binding rules —
and cited nothing.** The context section claimed the prototype "addresses
CBUAE requirements for: explainable AI decisions… auditability… consistent
coverage… fraud detection", naming no instrument, so no reader could check
whether the regulator asks for any of it — and the word "requirements" said
binding law. Checked against the CBUAE Rulebook (October 2026): the two
instruments that actually cover AI at licensed financial institutions are
the *Guidelines for Financial Institutions Adopting Enabling Technologies*
(issued 15/11/2021, in force) and the *Guidance Note on Consumer Protection
and Responsible Adoption and Use of AI/ML* (issued 11/2/2026, covering LFIs
"including insurance providers", whose definition of a high-impact decision
uses an insurance claim as its worked example). Both are supervisory
guidance — "should" language, and the Guidance Note "shall supplement and
not replace any laws, regulations or directives" — not binding requirements.
The four claims themselves survived the check: explainability (Guidelines
2.27, Note §4), auditability (Note §2 and §5a, "audit trails"), consistency
(Guidelines 2.29, Note §3c), fraud detection (Note §5e). What was confidently
wrong was the status and the sourcing: the section now names each instrument
and clause, states the guidance-not-law status, and records that
"CBUAE-aligned" is a design posture nobody has reviewed, not certification.

**Build: the wheel shipped the engine as loose top-level modules — the
installed package could not import itself.** Found while auditing the build
for the `src` → `motor_claims` rename (auto-discovery must be re-checked
whenever a layout changes): setuptools read the old `src/` as a src-layout
root and packaged its *contents* flat, so the wheel held `models.py`,
`scoring.py`, `triage.py`, … at the top level with no package directory at
all. Verified both directions in a clean directory: installing the wheel
fails `import src` while *succeeding* at `import models` — polluting every
environment that installs it with generic top-level module names that would
shadow any other `models`. The repo only worked because every documented
command runs from the checkout, where the working directory supplies the
package ahead of anything installed. `packages = ["motor_claims"]` is now
declared explicitly instead of inferred, and the built wheel was re-verified:
it carries `motor_claims/`, and `import motor_claims.triage` resolves from a
directory with no checkout on the path.

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
from tokens to app — never the reverse. Theme changes are verified two
ways: `tests/test_theme.py` (every selector target still exists in the
installed Streamlit) and `tests/test_render_browser.py` (computed styles
read out of a real browser). The brand book's anti-pattern list
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
| `/feedback` | POST | Record a handler decision/outcome (body = `eval.outcomes.ClaimOutcome`); appends JSONL to `FEEDBACK_PATH`, 409 on duplicate `claim_id` |

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
├── motor_claims/
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
│   ├── test_ui.py              # Dashboard tests (38 claims, every figure)
│   ├── test_theme.py           # Theme-selector liveness vs installed Streamlit
│   └── test_render_browser.py  # Chromium computed-style render checks
├── .github/workflows/ci.yml    # CI: ruff + format + mypy + pytest + render job
├── LICENSE                     # MIT
├── api.py                      # FastAPI endpoints (triage + /feedback capture)
└── pyproject.toml              # Dependencies
```

## UAE Insurance Context

Insurance in the UAE is supervised by the Central Bank of the UAE (CBUAE),
whose Rulebook explicitly covers "licensed financial institutions, including
insurance providers". Every regulatory claim here was checked against the
CBUAE Rulebook itself (as of October 2026) rather than assumed, and each is
tied to the instrument and clause that carries it:

| What the prototype does | Where CBUAE asks for it |
|---|---|
| Stated, readable reasons on every recommendation | *Guidelines for Financial Institutions Adopting Enabling Technologies* 2.27 (in force): material AI models must be "reliable, transparent, and explainable"; *AI Guidance Note* §4: clear disclosure of how AI makes decisions, for high-impact decisions — defined using an insurance claim as the worked example |
| An audit trail of every triage step (rules, factors, scores, rationale) | *AI Guidance Note* §2 (governance, board reporting, internal-audit roles, AI inventory) and §5a ("clear provenance and audit trails") |
| The same coverage rules applied the same way to every claim | *Guidelines* 2.29 (AI outcomes "objective, consistent, ethical, and fair"); *AI Guidance Note* §3c (AI-supported decisions consistent with fair treatment) |
| Fraud factors raised for SIU attention | *AI Guidance Note* §5e (LFIs "should … try to utilise, where feasible, AI to identify potential fraud") |
| Recommendations only — a human decides | *AI Guidance Note* §7: meaningful human oversight, "human-in-the-loop" where "a human decision maker retains full authority" |

Instruments, so the table can be re-verified at source:

- **Guidelines for Financial Institutions Adopting Enabling Technologies** —
  CBUAE Rulebook, issued 15/11/2021, in force; scope: "all Institutions
  licensed and supervised by the Supervisory Authorities" that use enabling
  technologies, filed under *All Licensed Financial Institutions*.
- **Guidance Note on Consumer Protection and Responsible Adoption and Use
  of Artificial Intelligence and Machine Learning by Licensed Financial
  Institutions** — issued 11/2/2026; applies to LFIs "including insurance
  providers", and defines a *high-impact decision* as one that materially
  affects a customer's access to products or services, "for example … an
  insurance claim".

Both are supervisory guidance — "should" language, and the Guidance Note
"shall supplement and not replace any laws, regulations or directives". So
"CBUAE-aligned" (the sidebar tagline) means the design follows these clauses:
it is not compliance certification, and nothing in this prototype has been
reviewed or approved by the CBUAE.
