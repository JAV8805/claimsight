"""Level-3 vehicle enrichment: the acceptance rule for external decoders (FR-05).

An external result is used only when it is complete and error-free. Anything else
means "not verifiable" (None), which is never a fraud signal on its own (FR-10).
"""

from pydantic import ValidationError

from claimsight.evals.schema import VehicleInfo


def vehicle_from_vpic(row: dict[str, str | None]) -> VehicleInfo | None:
    """Accept an NHTSA vPIC DecodeVinValues row only if ErrorCode is 0 and make/model exist."""
    make = (row.get("Make") or "").strip()
    model = (row.get("Model") or "").strip()
    year = (row.get("ModelYear") or "").strip()
    if row.get("ErrorCode") != "0" or not make or not model or not year.isdigit():
        return None
    try:
        return VehicleInfo(make=make.upper(), model=model, model_year=int(year))
    except ValidationError:
        return None


def same_vehicle(a: VehicleInfo, b: VehicleInfo) -> bool:
    """Make, model and year match, ignoring letter case."""
    return (a.make.upper(), a.model.casefold(), a.model_year) == (
        b.make.upper(),
        b.model.casefold(),
        b.model_year,
    )
