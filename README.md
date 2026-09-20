# Motor Claims Triage & Decision-Support Copilot

A prototype claims triage system for UAE motor insurance that automates coverage checks, risk scoring, and decision recommendations.

## Features

- **Coverage Verification**: Checks driver exclusions, vehicle matches, use-case restrictions, and policy validity
- **Complexity Scoring**: Evaluates multi-vehicle incidents, injuries, liability disputes, and repair cost ratios
- **Fraud Risk Detection**: Flags new policies with high claims, repeated claims, and inconsistent stories
- **Recommendation Engine**: Fast-track / Standard Review / Investigate based on risk assessment
- **Narrative Generation**: Human-readable rationale for handler notes
- **API & UI**: FastAPI endpoint + Streamlit dashboard

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
