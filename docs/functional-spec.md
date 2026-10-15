# ClaimSight - Functional Specification

Version 0.1 - Living document, updated at every lesson.

## 1. Purpose and scope
ClaimSight is a copilot for **auto-claims triage at First Notice of Loss (FNOL)**. It takes the
claimant's report and prepares an evidence-based brief for the adjuster: detected damage, vehicle
verification, weather verification, coverage with policy citations, fraud signals and a routing
recommendation.

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
| VIN | Vehicle identifier, 17 characters | Yes |
| Declared vehicle | Make, model and year stated by the claimant | Yes |
| Incident date | Day it happened | Yes |
| Location | Address and coordinates | Yes |
| Declared event | collision, hail, flood, theft, glass, vandalism, other | Yes |
| Policy | Policy identifier | Yes |
| Repair estimate | Estimated amount in USD | No |

## 4. Outputs
| Output | Description | Status |
|---|---|---|
| Claim type | Event classification | Planned |
| Vehicle verification | Make, model and year per NHTSA, and whether they match the declaration | Planned (L2.1) |
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
| FR-05 | **Vehicle verification.** The VIN is decoded with NHTSA vPIC and make, model and year are compared with the declaration. A mismatch raises the "VIN mismatch" signal | Planned (L2.1) |
| FR-06 | **Weather verification.** For hail and flood, historical weather (Open-Meteo) is checked at the incident date and place. Weather is a **signal for the adjuster, not proof**. If it does not support the event, the "weather mismatch" signal is raised | Planned (L2.1); thresholds to calibrate |
| FR-07 | **Weather events labeled.** Every hail or flood case must state whether the weather supports it | Encoded in golden set (L1.3) |
| FR-08 | **Privacy.** Personal data is redacted before reaching any LLM or log | Planned (L3.4) |
| FR-09 | **Minimization in test data.** Test cases use synthetic VINs: real pattern (positions 1-11) with an invented serial and a recomputed check digit | Implemented (L1.3) |

### Weather interpretation criteria (FR-06)
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
the weather**: the "weather mismatch" signal is raised and the case goes to adjuster review. This is
an adversarial golden-set case.

## 6. Fraud signals
| Signal | When it is raised |
|---|---|
| weather_mismatch | Historical weather does not support the declared event (FR-06) |
| vin_mismatch | The vehicle per NHTSA differs from the declared one (FR-05) |
| inflated_estimate | The amount is inconsistent with the detected damage severity |
| damage_narrative_mismatch | The photos are inconsistent with the narrative |
| late_report | Unusual delay between the incident date and the report |
| prompt_injection | A document or image contains instructions aimed at the system |

## 7. Data sources
| Source | Use | Notes |
|---|---|---|
| NHTSA vPIC | Decode the VIN | Free; US-market vehicles |
| NHTSA Recalls and Complaints | Recalls and complaints by model | Free |
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
| Golden set | Test cases with the correct answer labeled |
| WMO | World Meteorological Organization; defines the weather codes |

## 10. Change log
| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-10-15 | First version: scope, inputs, outputs, rules FR-01 to FR-09, weather criteria with a verified example, fraud signals, data sources |
