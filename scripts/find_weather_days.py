"""List storm/hail days and the wettest days for a location, to pick golden-case dates from data.

Usage: uv run python scripts/find_weather_days.py LAT LON START END
Example: uv run python scripts/find_weather_days.py 32.78 -96.80 2025-03-01 2025-07-31
"""

import sys

import httpx2

METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
STORM_CODES = {95: "thunderstorm", 96: "thunderstorm+hail", 99: "thunderstorm+heavy hail"}


def summarize(daily: dict, top: int = 5) -> list[str]:
    rows = list(
        zip(
            daily["time"],
            daily["weather_code"],
            daily["precipitation_sum"],
            daily["wind_gusts_10m_max"],
            strict=True,
        )
    )
    out = ["STORM/HAIL DAYS:"]
    out += [
        f"  {day} code={code} ({STORM_CODES[code]}) precip={rain}mm gust={gust}km/h"
        for day, code, rain, gust in rows
        if code in STORM_CODES
    ] or ["  none"]
    out.append(f"TOP {top} WETTEST DAYS:")
    wettest = sorted((r for r in rows if r[2] is not None), key=lambda r: r[2], reverse=True)
    out += [f"  {day} code={code} precip={rain}mm" for day, code, rain, _ in wettest[:top]]
    return out


def main(lat: str, lon: str, start: str, end: str) -> int:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "weather_code,precipitation_sum,wind_gusts_10m_max",
        "timezone": "auto",
    }
    resp = httpx2.get(METEO_URL, params=params, timeout=30)
    resp.raise_for_status()
    print("\n".join(summarize(resp.json()["daily"])))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
