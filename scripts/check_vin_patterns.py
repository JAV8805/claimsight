"""Check VIN patterns against NHTSA vPIC by decoding a synthetic VIN built from each pattern."""

import csv
import sys

import httpx2

from claimsight.evals.vin import synthesize

VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


def decode(client: httpx2.Client, vin: str) -> dict:
    response = client.get(VPIC_URL.format(vin=vin), timeout=30)
    response.raise_for_status()
    return response.json()["Results"][0]


def main(path: str) -> int:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    errors = 0
    with httpx2.Client() as client:
        for line, row in enumerate(rows, start=2):  # line 1 is the header
            try:
                vin = synthesize(row["pattern"], 1)
            except ValueError as exc:
                errors += 1
                print(f"line {line}: SKIPPED ({exc})")
                continue
            result = decode(client, vin)
            print(
                f"{row['pattern']}  {row['market']}  {vin}  "
                f"{result.get('Make', '')} | {result.get('Model', '')} | "
                f"{result.get('ModelYear', '')}  ErrorCode={result.get('ErrorCode', '')}"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "evals/golden/vin_patterns.csv"))
