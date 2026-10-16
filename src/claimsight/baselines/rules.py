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
    Routing,
)
from claimsight.evals.vin import VIN_RE
from claimsight.rules.weather import weather_verdict

# FR-03 says fast track *requires* a VIN match and no fraud; it does not say which claims
# qualify. The golden labels fast-track only these low-risk types, so the baseline does too.
FAST_TRACK_TYPES = frozenset({"collision", "glass"})


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
        routing=_route(claim_type, vin_matches and vin_format_valid, signals),
    )


def _route(claim_type: str, vin_ok: bool, signals: list[FraudSignal]) -> Routing:
    """FR-03 routing policy."""
    if len(set(signals)) >= 2 or "prompt_injection" in signals:
        return "siu_referral"
    if signals or not vin_ok:  # a single signal or an unconfirmed VIN: a human decides
        return "adjuster_review"
    return "fast_track" if claim_type in FAST_TRACK_TYPES else "adjuster_review"
