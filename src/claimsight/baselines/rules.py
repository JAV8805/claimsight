"""Rules-only baseline: no LLM, no narrative understanding.

It applies the deterministic rules of the functional spec to the structured inputs and the
case facts. Whatever needs language understanding (a narrative that contradicts the claimed
event, a prompt injection) is invisible to it; those cases are the reason to build the LLM
pipeline.
"""

from claimsight.evals.enrich import same_vehicle, vehicle_from_vpic
from claimsight.evals.schema import (
    CaseFacts,
    ClaimInput,
    Expected,
    FraudSignal,
    PolicyRecord,
)
from claimsight.evals.vin import VIN_RE
from claimsight.rules.routing import route
from claimsight.rules.weather import weather_verdict


def predict(policy: PolicyRecord, inputs: ClaimInput, facts: CaseFacts) -> Expected:
    claim_type = inputs.claimed_event  # no narrative understanding (FR-11 needs an LLM)
    vin = inputs.vin.upper()
    vin_matches = vin == policy.insured_vin
    vin_format_valid = bool(VIN_RE.match(vin))

    external = vehicle_from_vpic(facts.vpic) if facts.vpic else None
    precipitation = (facts.weather or {}).get("precipitation_sum")
    verdict = weather_verdict(claim_type, precipitation)

    signals: list[FraudSignal] = []
    if vin_format_valid and not vin_matches:  # FR-05: a malformed VIN is not a signal
        signals.append("vin_mismatch")
    if verdict == "does_not_support":  # FR-06
        signals.append("weather_mismatch")

    return Expected(
        claim_type=claim_type,
        vin_matches_policy=vin_matches,
        vin_format_valid=vin_format_valid,
        external_vehicle=external,
        declared_matches_external=(
            same_vehicle(inputs.declared_vehicle, external) if external else None
        ),
        weather_verdict=verdict,
        fraud_flag=bool(signals),
        fraud_signals=signals,
        routing=route(claim_type, vin_matches and vin_format_valid, signals),
    )
