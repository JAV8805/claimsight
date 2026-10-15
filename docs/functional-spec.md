# ClaimSight - Functional Specification

Version 0.2 - Living document, updated at every lesson.

## 1. Purpose and scope
ClaimSight is a copilot for **auto-claims triage at First Notice of Loss (FNOL)**. It takes the
claimant's report and prepares an evidence-based brief for the adjuster: detected damage, vehicle
verification, weather verification, coverage with policy citations, fraud signals and a routing
recommendation. It is designed to work in any country.

**ClaimSight recommends; it does not decide.** Every denial, SIU referral or high amount requires
human approval.

## 2. Actors
| Actor | Role |
|---|---|
| Claimant | Reports the claim: narrative or voice note, photos, VIN, date, place |
| Adjuster | Reviews the brief and makes the decision |
| SIU analyst | Reviews cases referred for fraud risk |
| Claims team lead | Oversees queues, quality and metrics |

## 3. Claim inputs
| Field | Description | Required |
|---|---|---|
| Narrative | Text or voice-note transcript (ES/EN) | Yes |
| Photos | Damage images | No |
| VIN | Vehicle identifier as reported (may contain typing errors) | Yes |
| Declared vehicle | Make, model and year stated by the claimant | Yes |
| Incident date | Day it happened | Yes |
| Location | Address and coordinates | Yes |
| Declared event | collision, hail, flood, theft, glass, vandalism, other | Yes |
| Policy | Policy identifier | Yes |
| Repair estimate | Estimated amount in USD | No |

The policy record held by the insurer (country, insured VIN, insured vehicle) is the source of truth
for the vehicle.

## 4. Outputs
| Output | Description | Status |
|---|---|---|
| Claim type | Event classification | Planned |
| Vehicle verification | Three levels: policy match, VIN format, optional external enrichment | Planned (L2.1) |
| Weather verification | Whether historical weather supports the declared event | Planned (L2.1) |
| Coverage | Covered / not covered / needs review, with cited clauses | Planned (L3.1) |
| Fraud signals and score | Detected signals and an explained score | Planned (L5.3) |
| Routing | Fast track, adjuster review or SIU referral | Planned (L5.1) |
| Adjuster brief | Summary with evidence and citations | Planned (L5.1) |

## 5. Functional rules
| ID | Rule | Status |
|---|---|---|
| FR-01 | **Human oversight.** Any denial, SIU referral, amount above threshold or low confidence goes to human approval. No automatic denial, ever | Planned (L5.2) |
| FR-02 | **Cited coverage.** A "covered" decision must cite at least one clause retrieved from the policy; without a citation the statement is rejected | Encoded in golden set (L1.3); in the system, L3.2 |
| FR-03 | **Routing values:** fast track, adjuster review or SIU referral. Fast track is forbidden when fraud is flagged; SIU referral requires a fraud flag | Encoded in golden set (L1.3) |
| FR-04 | **Fraud with evidence.** A fraud flag requires at least one signal; any signal implies a fraud flag | Encoded in golden set (L1.3) |
| FR-05 | **Country-independent vehicle verification in three levels** (see 5.2). Level 1, primary: the claim VIN must match the VIN insured in the policy; otherwise the "VIN mismatch" signal. Level 2: VIN format (global) and check digit where mandatory. Level 3, optional: external enrichment (NHTSA for US-market vehicles; RUNT or an authorized provider in Colombia) | Redesigned in v0.2; encoded in golden set (L1.3); in the system, L2.1 |
| FR-06 | **Weather verification.** For hail and flood, historical weather (Open-Meteo) is checked at the incident date and place. Weather is a **signal for the adjuster, not proof**. If it does not support the event, the "weather mismatch" signal is raised | Planned (L2.1); thresholds to calibrate |
| FR-07 | **Weather events labeled.** Every hail or flood case must state whether the weather supports it | Encoded in golden set (L1.3) |
| FR-08 | **Privacy.** Personal data is redacted before reaching any LLM or log | Planned (L3.4) |
| FR-09 | **Minimization in test data.** Test cases use synthetic VINs: real pattern (positions 1-11) with an invented serial and a recomputed check digit | Implemented (L1.3) |
| FR-10 | **No discrimination by data origin.** Being unable to verify a vehicle in an external source (e.g. a car not built for the US market) is never, on its own, a fraud signal or a reason for worse treatment | Encoded in golden set (L1.3) |

**FR-09 evidence (2026-10-15):** the synthetic VIN `1M8GDM9A1KP000123`, built from the pattern
`1M8GDM9AXKP` and the invented serial `000123`, was decoded by NHTSA vPIC as the same vehicle as the
real pattern (Motor Coach Industries 102C3 Intercity, 1989), with `ErrorCode 0` and a correct check
digit.

### 5.1 Weather interpretation criteria (FR-06)
WMO codes returned by Open-Meteo:

| Code | Meaning | Supports hail |
|---|---|---|
| 0-3 | Clear to overcast | No |
| 51-55 | Drizzle | No |
| 61-67, 80-82 | Rain, showers | No |
| 95 | Thunderstorm | Possible (hail may not be recorded) |
| 96, 99 | Thunderstorm with hail | Yes |

For flood, the daily rainfall total (`precipitation_sum`) is used; the threshold will be calibrated
with real cases in L2.1 and recorded here.

**Limitation:** the data comes from gridded weather models, not from a station at the exact spot.
Hail is very local and may not appear even if it fell. The rule therefore raises a signal and never
rejects a claim on its own.

**Verified example with real data:** Bogota (4.711, -74.072), 1-7 October 2025. The whole week
recorded drizzle only (codes 51-55), daily rain between 0.3 and 2.9 mm and gusts of 27-35 km/h, with
no thunderstorms or hail. A hail claim reported in Bogota on those days would **not be supported by
the weather**: the "weather mismatch" signal is raised and the case goes to adjuster review.

### 5.2 Vehicle verification in three levels (FR-05, v0.2)
**Why it was redesigned:** in v0.1 verification depended on NHTSA, which only covers vehicles built
for the US market, tying the system to one country. The real question in a claim is "is the vehicle
in the claim the one insured in the policy?", and the insurer already holds that data.

| Level | What it checks | Coverage | If it fails |
|---|---|---|---|
| 1. Against the policy (primary) | Claim VIN equals the insured VIN | Any country | "VIN mismatch" signal |
| 2. Format | 17 characters without I, O or Q (ISO 3779, global); check digit where mandatory (North America) | Format: global; check digit: North America | Possible typing error; ask to confirm |
| 3. External enrichment (optional) | Make, model and year in an external source; recalls and complaints | NHTSA: US market. RUNT or authorized provider: Colombia | **Not a fraud signal** (FR-10): recorded as "not externally verifiable" |

The external source sits behind a swappable component (adapter): connecting RUNT or an authorized
provider does not change the rest of the system. RUNT has no free public API; its web lookup has a
captcha and is not automated: access must be through an agreement or an authorized provider.

## 6. Fraud signals
| Signal | When it is raised |
|---|---|
| weather_mismatch | Historical weather does not support the declared event (FR-06) |
| vin_mismatch | The claim VIN differs from the insured VIN (FR-05, level 1) |
| inflated_estimate | The amount is inconsistent with the detected damage severity |
| damage_narrative_mismatch | The photos are inconsistent with the narrative |
| late_report | Unusual delay between the incident date and the report |
| prompt_injection | A document or image contains instructions aimed at the system |

## 7. Data sources
| Source | Use | Notes |
|---|---|---|
| Policy record (insurer's own data) | Insured VIN and vehicle: primary verification (FR-05, level 1) | Any country; test policies in this project |
| NHTSA vPIC | Decode the VIN (FR-05, level 3) | Free; US-market vehicles |
| NHTSA Recalls and Complaints | Recalls and complaints by model | Free |
| RUNT (Colombia) | External enrichment for Colombian vehicles (FR-05, level 3) | No free public API; agreement or authorized provider only. Out of v1 scope |
| Open-Meteo Historical Weather | Historical weather by date and place | Free; gridded model data |
| OpenStreetMap Nominatim | Address to coordinates | Free; respect usage limits |
| CarDD | Damage images for training and evaluation | Check license |
| Public policy wordings | Policy corpus for RAG | Check terms of use |

## 8. Out of scope
Bodily-injury claims, litigated claims, complex multi-party liability, total-loss valuation, and any
adverse decision without human review.

## 9. Glossary
| Term | Meaning |
|---|---|
| FNOL | First Notice of Loss |
| Adjuster | Professional who assesses the claim and decides |
| SIU | Special Investigations Unit (anti-fraud) |
| Fast track | Simplified handling for simple, low-risk claims |
| VIN | Vehicle Identification Number, 17 characters |
| RUNT | Registro Unico Nacional de Transito, Colombia's national vehicle registry |
| Golden set | Test cases with the correct answer labeled |
| WMO | World Meteorological Organization; defines the weather codes |

## 10. Change log
| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-10-15 | First version: scope, inputs, outputs, rules FR-01 to FR-09, weather criteria with a verified example, fraud signals, data sources |
| 0.2 | 2026-10-15 | FR-05 redesigned in three country-independent levels (policy, format, optional external enrichment); new FR-10 on no discrimination by data origin; FR-09 evidence with NHTSA; sources: policy record and RUNT |
