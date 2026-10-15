"""Golden-set schema: what a correct ClaimSight answer looks like."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ClaimType = Literal["collision", "hail", "flood", "theft", "glass", "vandalism", "other"]
Routing = Literal["fast_track", "adjuster_review", "siu_referral"]
CoverageDecision = Literal["covered", "not_covered", "needs_review"]
FraudSignal = Literal[
    "weather_mismatch",
    "vin_mismatch",
    "inflated_estimate",
    "damage_narrative_mismatch",
    "late_report",
    "prompt_injection",
]
WEATHER_EVENTS = {"hail", "flood"}

VIN_PATTERN = r"^[A-HJ-NPR-Z0-9]{17}$"  # 17 chars, letters I, O, Q are never used


class Location(BaseModel):
    address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DeclaredVehicle(BaseModel):
    make: str
    model: str
    model_year: int = Field(ge=1980, le=2030)


class ClaimInput(BaseModel):
    narrative: str = Field(min_length=10, description="Claimant's account (text or transcript)")
    audio_path: str | None = None
    image_paths: list[str] = []
    vin: str = Field(pattern=VIN_PATTERN)
    declared_vehicle: DeclaredVehicle
    incident_date: date
    location: Location
    claimed_event: ClaimType
    policy_id: str
    estimate_amount_usd: float | None = Field(default=None, ge=0)


class ExpectedVehicle(BaseModel):
    make: str
    model: str
    model_year: int


class Expected(BaseModel):
    claim_type: ClaimType
    vehicle: ExpectedVehicle = Field(description="Ground truth from NHTSA vPIC decoding")
    vin_matches_declared: bool
    weather_supports_claim: bool | None = None
    coverage_decision: CoverageDecision | None = Field(
        default=None, description="Filled once the policy corpus exists (L2.2)"
    )
    clause_ids: list[str] = []
    fraud_flag: bool
    fraud_signals: list[FraudSignal] = []
    routing: Routing


class GoldenCase(BaseModel):
    case_id: str = Field(pattern=r"^GC-\d{4}$")
    language: Literal["es", "en"]
    adversarial: bool = False
    tags: list[str] = []
    notes: str = ""
    inputs: ClaimInput
    expected: Expected

    @model_validator(mode="after")
    def check_label_consistency(self) -> "GoldenCase":
        exp = self.expected
        if exp.claim_type in WEATHER_EVENTS and exp.weather_supports_claim is None:
            raise ValueError("weather events must label weather_supports_claim")
        if exp.fraud_flag and not exp.fraud_signals:
            raise ValueError("fraud_flag=True requires at least one fraud signal")
        if exp.fraud_signals and not exp.fraud_flag:
            raise ValueError("fraud signals present but fraud_flag=False")
        if exp.routing == "siu_referral" and not exp.fraud_flag:
            raise ValueError("siu_referral requires fraud_flag=True")
        if exp.routing == "fast_track" and exp.fraud_flag:
            raise ValueError("fast_track is not allowed when fraud_flag=True")
        if exp.coverage_decision == "covered" and not exp.clause_ids:
            raise ValueError("a 'covered' decision must cite at least one clause")
        if exp.vin_matches_declared and "vin_mismatch" in exp.fraud_signals:
            raise ValueError("vin_mismatch signal contradicts vin_matches_declared=True")
        return self
