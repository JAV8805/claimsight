"""Build golden-case drafts from seeds: facts are fetched, judgments are left to a human.

Usage: uv run python scripts/build_golden_drafts.py [seeds.csv] [out_dir]
Existing drafts are never overwritten: they may already hold your labels.
"""

import csv
import json
import sys
from pathlib import Path

import httpx2

from claimsight.evals.enrich import same_vehicle, vehicle_from_vpic
from claimsight.evals.schema import VehicleInfo
from claimsight.evals.vin import VIN_RE, synthesize

VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}"
METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ("weather_code", "precipitation_sum", "wind_gusts_10m_max")


def decode_vin(client: httpx2.Client, vin: str) -> dict[str, str]:
    resp = client.get(VPIC_URL.format(vin=vin), params={"format": "json"})
    resp.raise_for_status()
    return resp.json()["Results"][0]


def daily_weather(client: httpx2.Client, lat: str, lon: str, day: str) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": day,
        "end_date": day,
        "daily": ",".join(DAILY),
        "timezone": "auto",
    }
    resp = client.get(METEO_URL, params=params)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    return {key: daily[key][0] for key in DAILY}


def build_draft(seed: dict[str, str], client: httpx2.Client) -> dict:
    policy_vin = synthesize(seed["pattern"], int(seed["serial"]))
    claim_vin = (seed["claim_vin"] or policy_vin).strip().upper()
    vehicle = VehicleInfo(
        make=seed["make"], model=seed["model"], model_year=int(seed["model_year"])
    )
    vpic = decode_vin(client, claim_vin) if VIN_RE.match(claim_vin) else {}
    external = vehicle_from_vpic(vpic)
    weather = daily_weather(client, seed["latitude"], seed["longitude"], seed["incident_date"])
    policy_id = f"POL-{seed['country']}-{seed['case_id'][3:]}"
    vin_matches = claim_vin == policy_vin
    return {
        "case_id": seed["case_id"],
        "language": seed["language"],
        "adversarial": seed["adversarial"].lower() == "true",
        "tags": [t for t in seed["tags"].split("|") if t],
        "notes": "",
        "policy": {
            "policy_id": policy_id,
            "country": seed["country"],
            "insured_vin": policy_vin,
            "insured_vehicle": vehicle.model_dump(),
        },
        "inputs": {
            "narrative": seed["narrative"],
            "vin": claim_vin,
            "declared_vehicle": vehicle.model_dump(),
            "incident_date": seed["incident_date"],
            "location": {
                "address": seed["address"],
                "latitude": float(seed["latitude"]),
                "longitude": float(seed["longitude"]),
            },
            "claimed_event": seed["claimed_event"],
            "policy_id": policy_id,
        },
        "facts": {
            "vpic": {k: vpic.get(k) for k in ("ErrorCode", "Make", "Model", "ModelYear")},
            "weather": weather,
            "sources": ["NHTSA vPIC DecodeVinValues", "Open-Meteo archive (ERA5)"],
        },
        "expected": {
            "claim_type": None,  # HUMAN: read the narrative, do not copy claimed_event blindly
            "vin_matches_policy": vin_matches,
            "vin_format_valid": bool(VIN_RE.match(claim_vin)),
            "external_vehicle": external.model_dump() if external else None,
            "declared_matches_external": same_vehicle(vehicle, external) if external else None,
            "weather_supports_claim": None,  # HUMAN: apply spec 5.1 to facts.weather
            "fraud_flag": None,  # HUMAN
            "fraud_signals": [] if vin_matches else ["vin_mismatch"],
            "routing": None,  # HUMAN
        },
    }


def main(seeds_path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = 0
    with seeds_path.open(newline="", encoding="utf-8") as f, httpx2.Client(timeout=20) as client:
        for seed in csv.DictReader(f):
            out = out_dir / f"{seed['case_id']}.json"
            if out.exists():
                print(f"{seed['case_id']}: SKIPPED (draft exists, labels protected)")
                continue
            try:
                draft = build_draft(seed, client)
            except (httpx2.HTTPError, ValueError, KeyError) as exc:
                errors += 1
                print(f"{seed['case_id']}: FAILED ({exc})")
                continue
            out.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            ext = draft["expected"]["external_vehicle"]
            w = draft["facts"]["weather"]
            print(
                f"{seed['case_id']}: external={'verified' if ext else 'not verifiable'} "
                f"weather_code={w['weather_code']} precip={w['precipitation_sum']}mm "
                f"gust={w['wind_gusts_10m_max']}km/h"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    seeds = Path(args[0] if args else "evals/golden/seeds.csv")
    out = Path(args[1] if len(args) > 1 else "evals/golden/drafts")
    sys.exit(main(seeds, out))
