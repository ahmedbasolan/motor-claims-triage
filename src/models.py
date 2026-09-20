"""Pydantic models for motor claims triage system."""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class CoverageType(str, Enum):
    THIRD_PARTY = "third_party"
    COMPREHENSIVE = "comprehensive"


class ClaimStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    FAST_TRACKED = "fast_tracked"
    INVESTIGATING = "investigating"
    REJECTED = "rejected"
    APPROVED = "approved"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(str, Enum):
    FAST_TRACK = "fast_track"
    STANDARD_REVIEW = "standard_review"
    INVESTIGATE = "investigate"


class VehicleDetails(BaseModel):
    make: str
    model: str
    year: int
    registration_number: str
    estimated_value: float


class DriverDetails(BaseModel):
    name: str
    age: int
    license_tenure_years: int
    is_excluded: bool = False


class AccidentDetails(BaseModel):
    date: datetime
    location: str
    description: str
    police_report_summary: str | None = None
    num_vehicles_involved: int = 1
    injury_reported: bool = False
    liability_disputed: bool = False


class DocumentMetadata(BaseModel):
    doc_type: str  # police_report, photo, repair_estimate, medical_report
    description: str
    uploaded_at: datetime | None = None


class RepairEstimate(BaseModel):
    estimated_cost: float
    garage_name: str
    items: list[str] = []


class Policy(BaseModel):
    policy_number: str
    coverage_type: CoverageType
    excess: float
    max_sum_insured: float
    excluded_drivers: list[str] = []
    excluded_uses: list[str] = []  # e.g., rental, ride_hailing
    policy_start_date: date
    policy_end_date: date
    vehicle_registration: str


class Claim(BaseModel):
    claim_id: str
    policy_number: str
    vehicle: VehicleDetails
    driver: DriverDetails
    accident: AccidentDetails
    documents: list[DocumentMetadata] = []
    repair_estimate: RepairEstimate | None = None
    submitted_at: datetime = Field(default_factory=datetime.now)
    status: ClaimStatus = ClaimStatus.SUBMITTED


class CoverageCheckResult(BaseModel):
    is_covered: bool
    coverage_type: CoverageType
    exclusions_triggered: list[str] = []
    excess_amount: float
    max_payout: float
    notes: list[str] = []


class ScoringResult(BaseModel):
    complexity_score: RiskLevel
    complexity_factors: list[str] = []
    fraud_risk_score: RiskLevel
    fraud_risk_factors: list[str] = []
    overall_risk: RiskLevel


class TriageResult(BaseModel):
    claim_id: str
    recommendation: Recommendation
    coverage: CoverageCheckResult
    scoring: ScoringResult
    narrative: str
    timestamp: datetime = Field(default_factory=datetime.now)
