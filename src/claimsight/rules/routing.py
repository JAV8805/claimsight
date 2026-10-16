"""Routing policy (FR-03): deterministic code; no model ever sets routing directly."""

from claimsight.evals.schema import FraudSignal, Routing

# FR-03 (spec v0.6): fast track applies only to collision and glass claims.
FAST_TRACK_TYPES = frozenset({"collision", "glass"})


def route(
    claim_type: str, vin_ok: bool, signals: list[FraudSignal], event_clarified: bool = True
) -> Routing:
    """FR-03 routing policy. `event_clarified` is False when the narrative contradicts the
    claimed event (FR-11): a human must clarify, so the claim is never fast-tracked."""
    if len(set(signals)) >= 2 or "prompt_injection" in signals:
        return "siu_referral"
    # a single signal, an unconfirmed VIN or an unclarified event: a human decides
    if signals or not vin_ok or not event_clarified:
        return "adjuster_review"
    return "fast_track" if claim_type in FAST_TRACK_TYPES else "adjuster_review"
