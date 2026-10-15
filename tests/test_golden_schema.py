import copy

import pytest
from pydantic import ValidationError

from claimsight.evals.schema import GoldenCase

# Format-valid sample. The VIN is the widely published check-digit example,
# used here only to exercise the format rule.
VALID_CASE = {
    "case_id": "GC-0001",
    "language": "es",
    "inputs": {
        "narrative": "Granizada fuerte mientras el carro estaba parqueado en la calle.",
        "vin": "1M8GDM9AXKP042788",
        "declared_vehicle": {"make": "Motor Coach", "model": "Bus", "model_year": 1989},
        "incident_date": "2026-04-10",
        "location": {"address": "Bogota, Colombia", "latitude": 4.711, "longitude": -74.072},
        "claimed_event": "hail",
        "policy_id": "AUTO-TEST-001",
    },
    "expected": {
        "claim_type": "hail",
        "vehicle": {"make": "Motor Coach", "model": "Bus", "model_year": 1989},
        "vin_matches_declared": True,
        "weather_supports_claim": True,
        "fraud_flag": False,
        "routing": "adjuster_review",
    },
}


def make_case(**expected_overrides):
    case = copy.deepcopy(VALID_CASE)
    case["expected"].update(expected_overrides)
    return case


def test_valid_case_is_accepted() -> None:
    assert GoldenCase.model_validate(VALID_CASE).case_id == "GC-0001"


@pytest.mark.parametrize(
    "overrides",
    [
        {"weather_supports_claim": None},  # weather event without weather label
        {"fraud_flag": True},  # fraud without signals
        {"fraud_signals": ["late_report"]},  # signals without fraud flag
        {"routing": "siu_referral"},  # SIU without fraud
        {"fraud_flag": True, "fraud_signals": ["late_report"], "routing": "fast_track"},
        {"coverage_decision": "covered"},  # covered without a cited clause
        {"fraud_flag": True, "fraud_signals": ["vin_mismatch"]},  # contradicts VIN match
    ],
)
def test_inconsistent_labels_are_rejected(overrides) -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(make_case(**overrides))


def test_invalid_vin_is_rejected() -> None:
    case = copy.deepcopy(VALID_CASE)
    case["inputs"]["vin"] = "1M8GDM9AXKP04278O"  # contains the letter O
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(case)
