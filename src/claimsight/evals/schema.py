"""Golden-set schema: what a correct ClaimSight answer looks like.

Vehicle verification is country-independent (FR-05, FR-10):
  level 1 - claim VIN vs the VIN insured in the policy (primary, any country)
  level 2 - VIN format (global) and check digit where mandatory
  level 3 - optional external enrichment (e.g. NHTSA for US-market vehicles)
Not being externally verifiable is never, on its own, a fraud signal.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from claimsight.evals.vin import VIN_RE

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
VIN_PATTERN = r"^[A-HJ-NPR-Z0-9]{17}$"


class Location(BaseModel):
    address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class VehicleInfo(BaseModel):
    make: str
    model: str
    model_year: int = Field(ge=1980, le=2030)


class PolicyRecord(BaseModel):
    """What the insurer already knows: the source of truth for the vehicle (level 1)."""

    policy_id: str
    country: str = Field(pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2, e.g. CO, US")
    insured_vin: str = Field(pattern=VIN_PATTERN)
    insured_vehicle: VehicleInfo


class ClaimInput(BaseModel):
    narrative: str = Field(min_length=10, description="Claimant's account (text or transcript)")
    audio_path: str | None = None
    image_paths: list[str] = []
    vin: str = Field(min_length=1, description="As reported; may be mistyped (level 2)")
    declared_vehicle: VehicleInfo
    incident_date: date
    location: Location
    claimed_event: ClaimType
    policy_id: str
    estimate_amount_usd: float | None = Field(default=None, ge=0)


class Expected(BaseModel):
    claim_type: ClaimType
    vin_matches_policy: bool = Field(description="Level 1: claim VIN equals the insured VIN")
    vin_format_valid: bool = Field(description="Level 2: well-formed 17-character VIN")
    external_vehicle: VehicleInfo | None = Field(
        default=None, description="Level 3: external source result; None = not verifiable"
    )
    declared_matches_external: bool | None = None
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
    policy: PolicyRecord
    inputs: ClaimInput
    expected: Expected

    @model_validator(mode="after")
    def check_label_consistency(self) -> "GoldenCase":
        exp, inp, pol = self.expected, self.inputs, self.policy
        if inp.policy_id != pol.policy_id:
            raise ValueError("inputs.policy_id must match policy.policy_id")
        if exp.vin_matches_policy != (inp.vin.upper() == pol.insured_vin):
            raise ValueError("vin_matches_policy contradicts the claim VIN and the insured VIN")
        if exp.vin_format_valid != bool(VIN_RE.match(inp.vin.upper())):
            raise ValueError("vin_format_valid contradicts the VIN format")
        if ("vin_mismatch" in exp.fraud_signals) != (not exp.vin_matches_policy):
            raise ValueError("vin_mismatch must be present if and only if the VIN mismatches")
        if exp.external_vehicle is None and exp.declared_matches_external is not None:
            raise ValueError("cannot compare with an external vehicle that does not exist")
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
        return self
