# Golden set v0 — data card

60 synthetic auto-claim cases (FNOL triage) for evaluating ClaimSight. `v0.jsonl` is compiled
from generated facts (`drafts/`) plus human judgment (`labels.json`) with `make golden`.
GC-0001 and GC-0002 were labeled first; GC-0003 to GC-0060 carry labels proposed by Claude and
decided by José in review (see "Labeling process").

## Sources

| Data | Source | How it enters |
| --- | --- | --- |
| Vehicle make, model, year | NHTSA vPIC `DecodeVinValues` (US market) | Fetched by `make golden-drafts`; used only under the acceptance rule (FR-05: `ErrorCode 0` and full make/model/year) |
| Vehicle identity | `vin_patterns.csv`: 8 US patterns and 1 CO pattern (`VF1RJL006TC`) | Policy VINs are synthetic: real pattern for positions 1–11, invented serial, recomputed check digit (FR-09). No real VIN is stored |
| Weather | Open-Meteo historical archive (ERA5 reanalysis): daily weather code, precipitation, gusts | Fetched by `make golden-drafts` for each case's date and coordinates. Dates were chosen from archive data (full-year scans of 2025 and Jan–Oct 2026 per city), never invented |
| Weather verdict | `claimsight.rules.weather.weather_verdict` (FR-06) | Stored in each draft as `facts.weather_rule` |
| Narratives | Written by hand (Claude, reviewed by José in the PR) | Synthetic; see limitations |
| City coordinates | Public city-center coordinates | Stored as `latitude`/`longitude` in `seeds.csv` |

Cities: US (Houston, Dallas, Denver, Miami, Atlanta) and Colombia (Bogotá, Medellín, Cali, Barranquilla,
Cartagena, Bucaramanga, Quibdó). Colombian cases use 2026 dates because the CO pattern is a 2026
model year; US cases use 2025–2026 dates. Every VIN serial is distinct.

## Counts

By language: 30 EN (US policies), 30 ES (CO policies).

By claimed event:

| Event | Total | EN | ES |
| --- | --- | --- | --- |
| collision | 17 | 8 | 9 |
| hail | 12 | 7 | 5 |
| theft | 9 | 4 | 5 |
| flood | 9 | 5 | 4 |
| glass | 7 | 3 | 4 |
| vandalism | 6 | 3 | 3 |

By weather verdict (`facts.weather_rule`): 39 no verdict (non-weather events), 14 inconclusive,
4 supports (flood at 50 mm or more), 3 does not support (2 dry-day hail, 1 flood under 10 mm).
The count comes from the generated facts: GC-0053 is counted as inconclusive there, but its label is a
collision with no weather verdict (FR-11), so the labels hold 13 inconclusive.
Flood cases cover both 50 mm or more (4 cases, including Houston 2026-06-15 at 55.4 mm and Dallas 2025-05-18
at 77.7 mm) and 10–50 mm days. Non-adversarial hail cases fall on days with some rain (0.2 mm to 82.8 mm, including Houston 2025-05-06 at 82.8 mm); the two dry-day hail cases are adversarial.

Adversarial: 10 cases (`adversarial: true`), exactly:

| Type | Cases | What it tests |
| --- | --- | --- |
| `vin_mismatch` | 2 | Valid claim VIN with a different serial than the insured VIN (FR-05 level 1) |
| `malformed_vin` | 2 | Claim VIN containing O or I (FR-05 level 2) |
| `dry_day_hail` | 2 | Hail claimed on a day with 0.0 mm (FR-06) |
| `flood_low` | 1 | Flood claimed on a day under 10 mm (FR-06) |
| `narrative_contradiction` | 2 | Narrative describes a different event than the claimed one |
| `prompt_injection` | 1 | Narrative contains instructions aimed at the system |

## Labeling process

1. **Machine facts.** `scripts/build_golden_drafts.py` turns each row of `seeds.csv` into a draft
   with fetched facts (vPIC decode, Open-Meteo weather, `weather_rule`) and leaves judgment fields empty.
2. **Human judgment.** `labels.json` holds `claim_type`, `weather_verdict`, `fraud_flag`,
   `fraud_signals`, `routing` and a rationale in `notes`. Labels are José's decision.
   For GC-0003 to GC-0060 they were first **proposed** by Claude, starting from
   `facts.weather_rule`, and then reviewed and decided by José; each note starts with "Decided:" and gives a one-line rationale.
3. **Compile.** `make golden` merges drafts and labels, validates every case against the schema
   (including label-consistency rules) and writes `v0.jsonl`; a CI test checks the committed file is in sync.

Decisions that shape the labels (spec v0.5):
- A malformed VIN is not fraud: no signal, adjuster review (FR-05 level 2).
- A narrative that contradicts the claimed event is not fraud: `claim_type` follows the narrative,
  so a hail claim described as a collision has no weather verdict (FR-11).
- SIU referral needs 2 or more fraud signals or `prompt_injection`; a single VIN mismatch goes to
  adjuster review. Fast track needs a VIN match (FR-03).
- GC-0023, GC-0050 and GC-0058 stay fast track.

## Known limitations

- **One CO VIN pattern.** All 30 Colombian policies share the Renault Arkana pattern `VF1RJL006TC`
  (only the serial varies), and none can be verified externally (NHTSA `ErrorCode 8`), so level 3
  enrichment is untested for CO beyond the "not verifiable" path.
- **Weather source cannot see hail.** The gridded archive never reports thunderstorms or hail (WMO 95–99 never
  appear in a full-year scan of five cities), so weather can only rule hail out on a dry day and never
  confirm it. Gridded data also misses very local rain, so a 0.0 mm day is still only a signal for the adjuster.
- **Synthetic narratives.** Narratives are written, not collected from claimants: they are cleaner and
  more uniform than real claims, short, and contain no typos, slang, photos or audio. Colombian Spanish
  is a single register.
- **Synthetic policies.** Policy records and VINs are invented (real pattern, invented serial); the
  set has no coverage decisions yet (L3.1). `expected.clause_ids` (the clauses a correct decision must cite) is decided
  for all 60 cases against the fictional ClaimSight Mutual Auto Policy (`corpus/policies/`).
- **Small and not representative.** 60 cases are for regression and rule checks, not for estimating real-world rates.
- **Label-rule circularity.** Labels were proposed from the same rules the baseline implements, so
  baseline accuracy measures policy consistency, not real-world accuracy. The informative signal is the
  language-dependent failures (GC-0009, GC-0012, GC-0053), and routing in GC-0009 and GC-0053 is right
  for the wrong reason. The golden set must grow with cases rules cannot solve.
