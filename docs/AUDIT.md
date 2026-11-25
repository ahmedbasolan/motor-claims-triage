# Defects found by auditing the logic and the stated figures

_Moved out of the README. Each entry is a defect the audit found and the fix that followed._

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

