# Motor Claims Triage & Decision-Support Copilot

A prototype claims triage system for UAE motor insurance that automates coverage checks, risk scoring, and decision recommendations.

**Status: prototype.** Logic is exercised against 25 synthetic claims and 8 synthetic
policies. It has never run against real claims, and the scoring thresholds are
unvalidated guesses, not calibrated against outcome data.

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

30 tests: `pytest tests/ -v`

## Two defects found by auditing the scoring logic

Both were found by checking the rules against the 25-claim dataset rather than by
reading the code, and both produced confidently wrong decisions.

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
├── src/
│   ├── models.py          # Pydantic data models
│   ├── coverage.py        # Coverage check logic
│   ├── scoring.py         # Complexity & fraud scoring
│   ├── recommendation.py  # Decision engine
│   ├── narrative.py       # Rationale generation
│   ├── triage.py          # Main orchestrator
│   └── mock_data.py       # 25 claims + 8 policies
├── app/
│   └── ui.py              # Streamlit dashboard
├── tests/
│   └── test_core.py       # Unit tests
├── api.py                 # FastAPI endpoint
└── pyproject.toml         # Dependencies
```

## UAE Insurance Context

This prototype addresses CBUAE requirements for:
- Explainable AI decisions in claims processing
- Auditability of triage reasoning
- Consistent handling of coverage logic
- Fraud detection in motor claims
