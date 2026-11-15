# Roadmap

Status as of 2026-11-15. Technical detail and assumptions in `DECISIONS.md`.

## Current phase: 3 of 7, validation and calibration (about halfway)

| Area | Status |
|---|---|
| Concept and spec (success = yield above the zone's 25th percentile; 3 rotations; index always with a range) | ✅ Done |
| Data: NASA POWER with cache, ONI, Open-Meteo, SoilGrids client | ✅ Built |
| Model: Wilson, analogs, gamma, ENSO, bootstrap index, RUSLE, AUC | ✅ Built |
| API, page and Gemini agent with a rule checker | ✅ Built |
| 12-layer test plan and no-keys test | ✅ Written, 33 tests pass |
| Leave-one-year-out (Brier) | ✅ Done |
| Version control (git) and Python environment (`.venv`, `requirements.txt`) | ✅ Done |
| Code, data and docs in English; page and Gemini in Spanish or English | ✅ Done |
| NASA GIBS satellite layers on the map (viewing only) | ✅ Done |
| MAG calibration v2 | ⚠️ Primera AUC 0.90 (published); postrera AUC 0.33 (not published, risks only) |
| AppEEARS (SMAP, NASADEM, HLS) | ❌ Not downloaded |
| SoilGrids | ❌ Not responding; client untested against a real reply |
| Sources for table E, the nitrogen table and the thresholds | ❌ All ASSUMPTION |

## Next
1. Freeze calibration v2 as the baseline. Write the postrera hypotheses in `DECISIONS.md` **before** testing them
   (overfitting risk: 2 design changes on 50 points).

## Phase 3 (now): finish validation and calibration
- Postrera: find what explains the bad years. Options: local stations (MARN), rain retreat date, MAG or FEWS NET damage
  reports, pests, the 0.5° POWER cell. Excess rain has already been ruled out. Recalibrate with `python -m backend.validate mag`.
- Dry-day threshold: POWER almost never gives days < 1 mm (long canícula in 3 of 36 years). Compare with stations.
- Write the root-zone saturation hypothesis for postrera (RZSM > 95% for > 3 days; see `SOIL_MOISTURE_ALERTS.md`),
  and test the wider maize sensitive window as a calibration variant, not a switch.
- **Done when:** postrera reaches AUC ≥ 0.60 or is formally limited to "risks only", and primera holds up with more years.

## Phase 4: complete the data
- Earthdata account, AppEEARS requests for the 3 pilot zones and conversion to the CSV in `data/appeears/README.md`.
- Root-zone SMAP (`smap_rz`) in the AppEEARS CSV and reader: days of saturation and available-water anomaly per season.
- SoilGrids working, or a local K and N (and field capacity / wilting point for available water).
- Sources for table E, the weakest part of the index.
- **Done when:** slope, greenness and soil come from real data and evidence C is left only where something is truly missing.

## Phase 5: expert review and field pilot
- An agronomist (CENTA, CRS) reviews `config/thresholds.yaml` and every edge in `config/graph.yaml`.
- Test with farmers in San Miguel, La Unión and Chalatenango: that the Spanish is clear, that the 3 field questions help
  and that the range is understood.
- **Done when:** thresholds are approved by an expert and there are notes from real farmers.

## Phase 6: hardening and deployment
- CI that runs the tests, a deployment, and a decision on how the Gemini key works in a hosted service.
- Check Open-Meteo's terms (non-commercial use only) before going wider.
- Error handling when an API does not respond.
- **Done when:** there is a public URL, CI passes, and the pages about the data and the method are published.

## Phase 7: expand
- Process the queue of plots outside the pilot (`data/appeears/queue.jsonl`).
- Add the market priority (no data today).
- A season monitor with the five soil-moisture alert colours, using check-in-the-field messages, not irrigation orders.
- Recalibrate when new MAG yearbooks come out (restricted since 2026).
