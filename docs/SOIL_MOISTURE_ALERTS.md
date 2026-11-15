# Soil moisture alerts (SMAP SSM + RZSM): proposal and evaluation

Source: `docs/references/soil-moisture-alerts-source.pdf` (3 pages, Spanish, added 2026-11-15).
It is a design proposal **with no cited references**. Every threshold below is an **ASSUMPTION** until an
agronomist or a published source backs it (same rule as `config/thresholds.yaml`). Nothing here is in the model yet.

## What the proposal says

### Four indicators
| Indicator | Meaning | Data needed |
|---|---|---|
| Plant-available water (RAW/AWD) | % of root-zone water the plant can extract, between field capacity and permanent wilting point | SMAP RZSM + soil field capacity and wilting point |
| Infiltration / surface decoupling | A sudden SSM rise with no RZSM change means rain stayed in the top 5 cm | SMAP SSM and RZSM, daily |
| Crop water stress (CWSI or a moisture-anomaly equivalent) | How fast root water is used up against atmospheric demand (temperature, radiation) | RZSM + ET0 |
| Days without effective recharge | Consecutive days with no useful rain or irrigation reaching the root zone | RZSM or rain |

### Alert matrix
| Level | Condition (SSM + RZSM) | Diagnosis | Message in the proposal |
|---|---|---|---|
| 🚨 Critical (red) | RZSM < 40% of available water during flowering or grain filling | Imminent severe stress; irreversible yield loss (flower abortion, empty grain) | "Urgent irrigation within 24 h" |
| ⚠️ Preventive (yellow) | RZSM 40–50% and SSM falling fast in high temperatures | Approaching the management allowed depletion (MAD) | "Best irrigation window in the next 2–3 days" |
| ℹ️ Informative / false alarm (blue) | SSM > 80% after light drizzle, RZSM low or unchanged (< 45%) | Water stayed at the surface | "Wet surface alert: roots are still dry" |
| 🟢 Optimal (green) | RZSM 65–85% of available water | Balanced moisture | "Ideal water conditions" |
| 🌊 Saturation (purple) | RZSM > 95% for more than 3 consecutive days | Root anoxia and root fungi (*Fusarium*) | "Waterlogging / excess water alert; check drainage" |

### Crop notes
- **Maize:** most sensitive from 2 weeks before tasselling to 3 weeks after. Tighten the preventive alert to 55% available water (instead of 50%) in that window.
- **Beans:** shallower roots (most uptake in the top 20–30 cm). Watch SSM and the upper root zone more closely; drought at flowering causes heavy flower and pod drop.

## Evaluation against this project

| Idea | Verdict | Why |
|---|---|---|
| Use SMAP **root-zone** moisture, not only surface | **Adopt (Phase 4)** | The AppEEARS reader only takes `smap` (surface). RZSM (SMAP L4) is closer to what the crop feels. Add a `smap_rz` layer to the normalized CSV. The map already shows SMAP L4 root-zone moisture from GIBS. |
| **Saturation / excess water** alert (RZSM > 95% for > 3 days) | **Adopt as a postrera hypothesis** | Postrera AUC is 0.33. Excess rain was tested with rainfall only and not confirmed; RZSM saturation and *Fusarium* are a different, testable signal. Write the hypothesis in `DECISIONS.md` before testing it. |
| Wider **maize sensitive window** (≈ day 41–96 instead of flowering 55–75) | **Test, don't switch** | Plausible, but it changes the model. Run it as a calibration variant and keep it only if primera AUC holds and postrera improves, with the overfitting caveat. |
| **Beans: weight the surface layer more** | **Adapt** | Reasonable once SMAP data is loaded; until then the model has no soil moisture per layer. |
| **Days without effective recharge** | **Already covered** | The dry-spell count from POWER rain (`dry_spell_days`) is this indicator measured with rain instead of RZSM. |
| Stress index vs atmospheric demand | **Already covered** | `stress_fraction` (rain/ET0 per 10-day block) and flowering VPD play this role. Real CWSI needs canopy temperature, which we do not have. |
| % of **plant-available water** thresholds (40/50/65–85/95) | **Adapt, mark as assumption** | Needs field capacity and wilting point per plot (SoilGrids 2.0 publishes water content at 33 and 1500 kPa, but SoilGrids is down) or SMAP L4 wetness. The cut-offs have no source. |
| **Irrigation actions** ("irrigate within 24 h", "start pumps") | **Reject** | Most Dry Corridor maize and beans are rainfed. The tool explains seasonal risk and never gives instructions the JSON does not support (Gemini rule 1). Messages would be about checking the field, not irrigating. |
| **Real-time 24 h alerts** per plot | **Reject for the MVP** | SMAP is about 9 km and arrives with days of delay; a 24 h plot alert would claim more precision than the data has. It could be a later "season monitor" with honest ranges. |

## Proposed changes, in order
1. Docs only (done): this page, plus links from `DECISIONS.md` and `ROADMAP.md`.
2. Phase 3: write the RZSM-saturation hypothesis for postrera; test it when RZSM data exists.
3. Phase 4: add `smap_rz` to the AppEEARS CSV and reader; compute days of saturation and an available-water anomaly per season.
4. Phase 5: ask the agronomist to review the 40/50/55/65–85/95 cut-offs and the maize window.
5. Later: a season monitor with the five alert colours, using check-in-the-field messages instead of irrigation orders.
