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
        routing="adjuster_review",
    )
    case["inputs"]["vin"] = "4T1G11AK0LU000002"
    assert GoldenCase.model_validate(case).expected.routing == "adjuster_review"


def malformed_vin_case(**expected_overrides):
    """Claim VIN with a letter O: wrong format, so it cannot match the insured VIN."""
    case = make_case(vin_matches_policy=False, vin_format_valid=False, **expected_overrides)
    case["inputs"]["vin"] = "4T1G11AK8LU0000O1"
    return case


def test_malformed_vin_without_signal_is_accepted() -> None:
    """FR-05 level 2: a malformed VIN is a possible typo, not fraud."""
    exp = GoldenCase.model_validate(malformed_vin_case()).expected
    assert exp.fraud_signals == [] and exp.fraud_flag is False


def test_malformed_vin_with_vin_mismatch_signal_is_rejected() -> None:
    case = malformed_vin_case(fraud_flag=True, fraud_signals=["vin_mismatch"])
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(case)


def test_fast_track_requires_vin_match() -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(malformed_vin_case(routing="fast_track"))


def test_siu_referral_with_two_signals_is_accepted() -> None:
    case = make_case(
        fraud_flag=True, fraud_signals=["late_report", "inflated_estimate"], routing="siu_referral"
    )
    assert GoldenCase.model_validate(case).expected.routing == "siu_referral"


def test_siu_referral_with_duplicated_signal_is_rejected() -> None:
    case = make_case(
        fraud_flag=True, fraud_signals=["late_report", "late_report"], routing="siu_referral"
    )
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(case)


def test_siu_referral_with_prompt_injection_alone_is_accepted() -> None:
    case = make_case(fraud_flag=True, fraud_signals=["prompt_injection"], routing="siu_referral")
    assert GoldenCase.model_validate(case).expected.routing == "siu_referral"


@pytest.mark.parametrize("signal", ["late_report", "weather_mismatch", "damage_narrative_mismatch"])
def test_siu_referral_with_one_ordinary_signal_is_rejected(signal) -> None:
    overrides = {"fraud_flag": True, "fraud_signals": [signal], "routing": "siu_referral"}
    if signal == "weather_mismatch":
        overrides["weather_verdict"] = "does_not_support"
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(make_case(**overrides))


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
        {"fraud_flag": True, "fraud_signals": ["late_report"], "routing": "siu_referral"},
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
