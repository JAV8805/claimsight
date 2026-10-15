from claimsight.evals.enrich import same_vehicle, vehicle_from_vpic
from claimsight.evals.schema import VehicleInfo

CAMRY_ROW = {"ErrorCode": "0", "Make": "TOYOTA", "Model": "Camry", "ModelYear": "2020"}
# Real NHTSA answer for a Renault Arkana 2026 pattern: empty make/model, wrong year.
ARKANA_ROW = {"ErrorCode": "8", "Make": "", "Model": "", "ModelYear": "1996"}
CAMRY = VehicleInfo(make="TOYOTA", model="Camry", model_year=2020)


def test_complete_error_free_result_is_accepted() -> None:
    assert vehicle_from_vpic(CAMRY_ROW) == CAMRY


def test_non_us_vehicle_is_not_verifiable_not_wrong() -> None:
    assert vehicle_from_vpic(ARKANA_ROW) is None


def test_error_code_zero_without_model_is_rejected() -> None:
    assert vehicle_from_vpic({**CAMRY_ROW, "Model": ""}) is None


def test_same_vehicle_ignores_case() -> None:
    a = VehicleInfo(make="toyota", model="CAMRY", model_year=2020)
    assert same_vehicle(a, vehicle_from_vpic(CAMRY_ROW))
