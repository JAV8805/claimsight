# ClaimSight — Functional Specification

Version 0.3 · Living document, updated every lesson. This document describes how the system behaves; test evidence lives in `docs/evals/validation-log.md`.

## 1. Purpose and scope

ClaimSight is a copilot for **auto claims triage at first notice of loss (FNOL)**. It receives the claimant's report and prepares an evidence-backed brief for the adjuster: detected damage, vehicle verification, weather verification, coverage with policy citations, fraud signals and a routing recommendation.

**ClaimSight recommends; it does not decide.** Every denial, SIU referral or high amount requires human approval.

## 2. Actors

| Actor | Role |
| --- | --- |
| Claimant | Reports the loss: narrative or voice note, photos, VIN, date, location |
| Adjuster | Reviews the brief and makes the decision |
| Fraud analyst (SIU) | Reviews claims referred for fraud risk |
| Claims lead | Oversees queues, quality and metrics |

## 3. Claim inputs

| Field | Description | Required |
| --- | --- | --- |
| Narrative | Text or voice-note transcript (EN/ES) | Yes |
| Photos | Images of the damage | No |
| VIN | Vehicle identifier as reported, 17 characters expected | Yes |
| Declared vehicle | Make, model and year declared by the claimant | Yes |
| Incident date | Day the loss happened | Yes |
| Location | Address and coordinates | Yes |
| Claimed event | collision, hail, flood, theft, glass, vandalism, other | Yes |
| Policy | Policy identifier; the policy record holds the insured VIN and vehicle | Yes |
| Repair estimate | Estimated amount in USD | No |

## 4. Outputs

| Output | Description | Status |
| --- | --- | --- |
| Claim type | Event classification | Planned |
| Vehicle verification | Policy match, VIN format validity and, when an external source is available, make, model and year | Planned (L2.1) |
| Weather verification | Whether historical weather supports the claimed event | Planned (L2.1) |
| Coverage | Covered / not covered / needs review, with cited clauses | Planned (L3.1) |
| Fraud signals and score | Signals detected and an explained score | Planned (L5.3) |
| Routing | Fast track, adjuster review or SIU referral | Planned (L5.1) |
| Adjuster brief | Summary with evidence and citations | Planned (L5.1) |

## 5. Functional rules

| ID | Rule | Status |
| --- | --- | --- |
| FR-01 | **Human oversight.** Every denial, SIU referral, amount above the threshold or low-confidence result goes to human approval. There is never an automatic denial | Planned (L5.2) |
| FR-02 | **Coverage with citations.** A "covered" decision must cite at least one clause retrieved from the policy; without a citation the claim is rejected | Planned (L3.2) |
| FR-03 | **Routing values:** fast track, adjuster review or SIU referral. Fast track is forbidden when fraud is flagged; SIU referral requires a fraud flag | Planned (L5.1) |
| FR-04 | **Fraud with evidence.** Flagging fraud requires at least one signal; any signal implies a fraud flag | Planned (L5.3) |
| FR-05 | **Country-independent three-level vehicle verification** (see 5.1). Level 1, primary: the claim VIN must match the insured VIN in the policy; otherwise a "VIN mismatch" signal. Level 2: VIN format (global) and check digit where mandatory. Level 3, optional: external enrichment under the acceptance rule | Planned (L2.1) |
| FR-06 | **Weather verification.** For hail and flood, historical weather (Open-Meteo) is checked for the incident date and location. Weather is a **signal for the adjuster, not proof**. If it does not support the claim, a "weather mismatch" signal is raised | Planned (L2.1); thresholds to be calibrated |
| FR-07 | **Weather in the brief.** The brief of every hail or flood claim states the weather check result: supports, does not support, or no data | Planned (L2.1) |
| FR-08 | **Privacy.** Personal data is anonymized before it is sent to any LLM or written to logs | Planned (L3.4) |
| FR-09 | **Data minimization.** The system stores and sends only the data each step needs. Non-production environments use synthetic VINs: real pattern (positions 1–11), invented serial and recomputed check digit | Implemented in non-production data (L1.3) |
| FR-10 | **No discrimination by data origin.** Being unable to verify a vehicle in an external source (for example, a vehicle outside the US market) is never, on its own, a fraud signal or a reason for worse treatment | Planned (L2.1) |

### 5.1 Three-level vehicle verification (FR-05)

**Principle:** the claim question is not "which car is this according to an external database?" but "is the car in the claim the one insured in the policy?". The insurer already holds that data in any country, so the policy is the primary check.

| Level | What it checks | Scope | If it fails |
| --- | --- | --- | --- |
| 1. Against the policy (primary) | The claim VIN matches the insured VIN | Any country | "VIN mismatch" signal |
| 2. Format | 17 characters without I, O or Q (ISO 3779, global); check digit where mandatory (North America) | Format: global; check digit: North America | Possible typo; the data is confirmed with the claimant |
| 3. External enrichment (optional) | Make, model and year in an external source; recalls and complaints | NHTSA: US market. RUNT or an authorized provider: Colombia | **Not a fraud signal** (FR-10): recorded as "not externally verifiable" |

The external source is an interchangeable component (adapter): connecting RUNT or an authorized provider does not change the rest of the system. RUNT offers no free public API; its web lookup has a captcha and is not automated, so access must be through an agreement or an authorized provider.

**External enrichment acceptance rule (level 3):** an external result is used only when the source reports a clean decode (NHTSA: `ErrorCode 0`) and returns make, model and model year. Otherwise the vehicle is recorded as "not externally verifiable" and is **not compared** with the declared vehicle.

### 5.2 Weather interpretation criteria (FR-06)

WMO codes returned by Open-Meteo:

| Code | Meaning | Supports hail |
| --- | --- | --- |
| 0–3 | Clear to overcast | No |
| 51–55 | Drizzle | No |
| 61–67, 80–82 | Rain, showers | No |
| 95 | Thunderstorm | Possible (hail may not be recorded) |
| 96, 99 | Thunderstorm with hail | Yes |

For flood, the daily accumulated precipitation (`precipitation_sum`) is used; the threshold will be calibrated with real cases in L2.1 and recorded here.

**Limitation:** the data comes from gridded weather models, not from a station at the exact point. Hail is very local and may not appear even if it fell. That is why the rule raises a signal and never rejects a claim on its own.

## 6. Fraud signals

| Signal | When it is raised |
| --- | --- |
| Weather mismatch | Historical weather does not support the claimed event (FR-06) |
| VIN mismatch | The claim VIN does not match the insured VIN in the policy (FR-05, level 1) |
| Inflated estimate | The amount is not consistent with the severity of the detected damage |
| Damage vs narrative | The photos are not consistent with the narrative |
| Late report | Unusual delay between the incident date and the report |
| Prompt injection | A document or image contains instructions aimed at the system |

## 7. Data sources

| Source | Use | Notes |
| --- | --- | --- |
| Policy record (insurer's internal data) | Insured VIN and vehicle: primary check (FR-05, level 1) | Any country; test policies in this project |
| NHTSA vPIC | VIN decoding | Free; US-market vehicles |
| NHTSA Recalls and Complaints | Recalls and complaints by model | Free |
| Open-Meteo Historical Weather | Historical weather by date and location | Free; gridded model data |
| OpenStreetMap Nominatim | Address to coordinates | Free; respect usage limits |
| CarDD | Damage images for training and evaluation | Check license |
| Public policy wordings | Policy corpus for RAG | Check terms of use |
| RUNT (Colombia) | External enrichment for Colombian vehicles (FR-05, level 3) | No free public API; agreement or authorized provider only. Out of scope for v1 |

## 8. Out of scope

Injury claims, claims in litigation, complex multi-party liability, total-loss valuation and any adverse decision without human review.

## 9. Glossary

| Term | Meaning |
| --- | --- |
| FNOL | First Notice of Loss |
| Adjuster | Professional who assesses the claim and decides |
| SIU | Special Investigations Unit: anti-fraud unit |
| Fast track | Simplified handling for simple, low-risk claims |
| VIN | Vehicle Identification Number, 17 characters |
| WMO | World Meteorological Organization; defines the weather codes |

## 10. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.3 | 2026-10-15 | Test evidence moved to the validation log; external enrichment acceptance rule added to FR-05; FR-07 and FR-09 rewritten as system behavior; rule status now tracks system implementation |
| 0.2 | 2026-10-15 | FR-05 redesigned as three country-independent levels (policy, format, optional external enrichment); new FR-10 on no discrimination by data origin; sources: policy record and RUNT |
| 0.1 | 2026-10-15 | First version: scope, inputs, outputs, rules FR-01 to FR-09, weather criteria, fraud signals, data sources |
