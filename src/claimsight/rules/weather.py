"""Weather verdict for weather events (FR-06, spec 5.2).

The source is Open-Meteo's historical archive (gridded reanalysis). It cannot estimate
thunderstorms or hail: WMO codes 95-99 never appear in it, so weather can never confirm
hail. It can only show a dry day, which does not support a hail claim. Flood is judged on
daily accumulated precipitation.
"""

from typing import Literal

WeatherVerdict = Literal["supports", "does_not_support", "inconclusive"]

WEATHER_EVENTS = frozenset({"hail", "flood"})
HAIL_DRY_DAY_MM = 0.1  # below this the day was dry: no storm to produce hail
FLOOD_SUPPORTS_MM = 50.0  # at or above: heavy rain consistent with flooding
FLOOD_DRY_MM = 10.0  # below: too little rain to cause a flood


def weather_verdict(event: str, precipitation_mm: float | None) -> WeatherVerdict | None:
    """Verdict on whether the day's precipitation supports the claimed event.

    Returns None for non-weather events and "inconclusive" when data is missing.
    Hail never returns "supports": the source cannot see hail.
    """
    if event not in WEATHER_EVENTS:
        return None
    if precipitation_mm is None:
        return "inconclusive"
    if event == "hail":
        return "does_not_support" if precipitation_mm < HAIL_DRY_DAY_MM else "inconclusive"
    if precipitation_mm >= FLOOD_SUPPORTS_MM:
        return "supports"
    if precipitation_mm < FLOOD_DRY_MM:
        return "does_not_support"
    return "inconclusive"
