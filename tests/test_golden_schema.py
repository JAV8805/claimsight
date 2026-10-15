import copy

import pytest
from pydantic import ValidationError

from claimsight.evals.schema import GoldenCase

CAMRY = {"make": "TOYOTA", "model": "Camry", "model_year": 2020}
SYNTHETIC_VIN = "4T1G11AK8LU000001"  # real Camry pattern + invented serial

VALID_CASE = {
    "case_id": "GC-0001",
    "language": "en",
    "policy": {
        "policy_id": "AUTO-TEST-001",
        "country": "US",
        "insured_vin": SYNTHETIC_VIN,
        "insured_vehicle": CAMRY,
    },
    "inputs": {
        "narrative": "Hail hit the car while it was parked on the street.",
        "vin": SYNTHETIC_VIN,
        "declared_vehicle": CAMRY,
        "incident_date": "2025-05-20",
        "location": {"address": "Houston, TX", "latitude": 29.76, "longitude": -95.37},
        "claimed_event": "hail",
        "policy_id": "AUTO-TEST-001",
    },
    "expected": {
        "claim_type": "hail",
        "vin_matches_policy": True,
        "vin_format_valid": True,
        "external_vehicle": CAMRY,
        "declared_matches_external": True,
        "weather_verdict": "inconclusive",
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


def test_vehicle_not_externally_verifiable_is_accepted_without_fraud() -> None:
    """FR-10: a vehicle outside the external source's coverage is not suspicious by itself."""
    case = make_case(external_vehicle=None, declared_matches_external=None)
    case["policy"]["country"] = "CO"
    assert GoldenCase.model_validate(case).expected.fraud_flag is False


def test_dry_day_hail_case_is_accepted_with_weather_mismatch() -> None:
    """FR-06: a dry day (< 0.1 mm) does not support a hail claim and raises weather_mismatch."""
    case = make_case(
        weather_verdict="does_not_support",
        fraud_flag=True,
        fraud_signals=["weather_mismatch"],
        routing="adjuster_review",
    )
    assert GoldenCase.model_validate(case).expected.fraud_signals == ["weather_mismatch"]


def test_vin_mismatch_case_is_accepted_when_labeled_consistently() -> None:
    case = make_case(
        vin_matches_policy=False,
        fraud_flag=True,
        fraud_signals=["vin_mismatch"],
        routing="siu_referral",
    )
    case["inputs"]["vin"] = "4T1G11AK0LU000002"
    assert GoldenCase.model_validate(case).expected.routing == "siu_referral"


@pytest.mark.parametrize(
    "overrides",
    [
        {"weather_verdict": None},  # weather event without weather label
        {"weather_verdict": "maybe"},  # not a verdict value
        {"weather_verdict": "does_not_support"},  # dry day without weather_mismatch
        {"fraud_flag": True, "fraud_signals": ["weather_mismatch"]},  # signal, inconclusive
        {  # signal with supporting weather
            "weather_verdict": "supports",
            "fraud_flag": True,
            "fraud_signals": ["weather_mismatch"],
        },
        {"fraud_flag": True},  # fraud without signals
        {"fraud_signals": ["late_report"]},  # signals without fraud flag
        {"routing": "siu_referral"},  # SIU without fraud
        {"fraud_flag": True, "fraud_signals": ["late_report"], "routing": "fast_track"},
        {"coverage_decision": "covered"},  # covered without a cited clause
        {"vin_matches_policy": False},  # contradicts identical VINs
        {"fraud_flag": True, "fraud_signals": ["vin_mismatch"]},  # signal without mismatch
        {"vin_format_valid": False},  # contradicts a well-formed VIN
        {"external_vehicle": None},  # comparison with a vehicle that does not exist
    ],
)
def test_inconsistent_labels_are_rejected(overrides) -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(make_case(**overrides))


def test_policy_id_mismatch_is_rejected() -> None:
    case = copy.deepcopy(VALID_CASE)
    case["inputs"]["policy_id"] = "AUTO-OTHER"
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(case)
