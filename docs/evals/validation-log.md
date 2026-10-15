# ClaimSight — Validation Log

Test evidence that confirmed or changed a rule. The rules live in `docs/functional-spec.md`; this log shows why they are the way they are. Newest first.

| Date | Finding | Rule | Outcome |
| --- | --- | --- | --- |
| 2026-10-15 | Hail claim in Houston (29.76, −95.37) on 2025-05-20: ERA5 daily code WMO 61 (slight rain), 4.8 mm, gusts 38.5 km/h; no hail code | FR-06 | Golden case GC-0001 labeled `weather_mismatch`, routed to adjuster review, not SIU: a single weak signal from gridded data |
| 2026-10-15 | Renault Arkana, model year 2026, Colombian market (pattern `VF1RJL006TC`): NHTSA returned empty make and model, `ErrorCode 8` and model year 1996. The year letter T means 1996 or 2026; NHTSA's North American position-7 tiebreak picked 1996 | FR-05 acceptance rule, FR-10 | Without the rule the system would compare 1996 with the real year and raise a false fraud signal. Golden case GC-0002: not externally verifiable, fast track |
| 2026-10-15 | Bogotá (4.711, −74.072), 1–7 Oct 2025: drizzle only (WMO 51–55), 0.3–2.9 mm per day, gusts 27–35 km/h | FR-06 | A hail claim on those days is not supported by weather; planned adversarial golden case |
| 2026-10-15 | 8 US-market VIN patterns (`evals/golden/vin_patterns.csv`) decoded by NHTSA with `ErrorCode 0` (`make check-vins`) | FR-09 | Synthetic VINs built from them are valid for verification |
| 2026-10-15 | Synthetic VIN `1M8GDM9A1KP000123` (pattern `1M8GDM9AXKP`, invented serial `000123`) decoded as the real pattern's vehicle (Motor Coach Industries 102C3, 1989), `ErrorCode 0`, check digit correct | FR-09 | Synthetic VINs keep verification valid without identifying a real vehicle |
