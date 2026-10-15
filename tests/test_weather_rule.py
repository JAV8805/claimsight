import pytest

from claimsight.rules.weather import (
    FLOOD_DRY_MM,
    FLOOD_SUPPORTS_MM,
    HAIL_DRY_DAY_MM,
    weather_verdict,
)


@pytest.mark.parametrize(
    ("event", "precipitation_mm", "expected"),
    [
        ("hail", 0.0, "does_not_support"),  # dry day
        ("hail", HAIL_DRY_DAY_MM - 0.01, "does_not_support"),
        ("hail", HAIL_DRY_DAY_MM, "inconclusive"),  # any rain: the source cannot see hail
        ("hail", 4.8, "inconclusive"),  # GC-0001, Houston 2025-05-20
        ("hail", 82.8, "inconclusive"),  # Houston's wettest 2025 day: still not hail evidence
        ("flood", FLOOD_SUPPORTS_MM, "supports"),
        ("flood", 82.8, "supports"),
        ("flood", FLOOD_SUPPORTS_MM - 0.1, "inconclusive"),
        ("flood", FLOOD_DRY_MM, "inconclusive"),
        ("flood", FLOOD_DRY_MM - 0.1, "does_not_support"),
        ("flood", 0.0, "does_not_support"),
        ("hail", None, "inconclusive"),  # missing data
        ("flood", None, "inconclusive"),
        ("collision", 82.8, None),  # non-weather events get no verdict
        ("theft", None, None),
    ],
)
def test_weather_verdict(event, precipitation_mm, expected) -> None:
    assert weather_verdict(event, precipitation_mm) == expected


@pytest.mark.parametrize("precipitation_mm", [0.0, 0.1, 10.0, 50.0, 500.0, None])
def test_hail_is_never_supported(precipitation_mm) -> None:
    assert weather_verdict("hail", precipitation_mm) != "supports"
