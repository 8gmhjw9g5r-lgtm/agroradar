# Milpa crop risk — MVP Space Apps 2026

The farmer marks a plot on the map, says what they will plant and when, and gets, for three rotations
(maize after maize, maize with beans, maize with green manure), a success index from 0 to 100 with its range,
the risk of each variable with its probability and interval, and an explanation in plain language.

**Success** = yield above the zone's historical 25th percentile. The index never comes out without a range, and it is
not published until it is calibrated against MAG yields (see `docs/DECISIONS.md`).

The page is in Spanish by default, for farmers in El Salvador, with an ES/EN switch. Code, data and docs are in English.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your GEMINI_API_KEY (optional: without it there is no agent text)
uvicorn backend.api:app --reload
```
Open http://localhost:8000.

## Tests

```bash
python -m unittest -v tests.test_mvp
```
Layers 5, 6 and 8 use real POWER data (the first time they download about 13,000 days per cell and then read from `data/cache`).
Layer 7 with real Gemini only runs if `GEMINI_API_KEY` is set.

## Validation and calibration

```bash
python -m backend.validate
```
Leaves one year out, computes the Brier score and writes `data/validation.json`.

```bash
python -m backend.validate mag
```
Computes the AUC against MAG department yields (`data/mag_yields.csv`, 2001-2022) and writes `data/calibration.json`. Current result: primera AUC 0.90 (published); postrera AUC 0.33 (not published, risks only). See `docs/DECISIONS.md`.

## API

`POST /api/farm` with:

```json
{"lang": "es", "enso_phase": null, "plots": [{"plot_id": "p1", "geometry": {"type": "Point", "coordinates": [-88.18, 13.48]},
  "planned_crop": "maize", "planting_date": "2026-05-25", "season": "primera", "priorities": ["water"]}]}
```
`lang` is `es` (default) or `en`; it only changes the texts. Crops: `maize`, `bean`, `green_manure`. Priorities: `water`, `erosion`, `nitrogen`.

## Declared data

| Source | Use | Access |
|---|---|---|
| NASA POWER (daily, MERRA-2) | Rain, temperatures and relative humidity from 1991 to today | No key |
| NASA AppEEARS (SMAP, NASADEM, HLS, MODIS) | Moisture, slope and greenness; preloaded per pilot zone | Earthdata account |
| NASA GIBS (MODIS, GPM IMERG, SMAP) | Satellite layers on the map, for viewing only | No key |
| NOAA CPC ONI | El Niño phase per year | No key |
| ISRIC SoilGrids | Texture, carbon and nitrogen (evidence C) | No key |
| Open-Meteo | 7-day forecast | No key, non-commercial use |
| Google Gemini | Text explanation | Each user's key in `.env` |

## Structure

```
config/thresholds.yaml  thresholds and tables (all assumptions except those cited in DECISIONS.md)
config/graph.yaml       causal relationships the agent may use
backend/clients/        POWER with cache; Open-Meteo, SoilGrids, ONI
backend/features.py     rain onset, dry spell, VPD, ET0, RUSLE
backend/models.py       Wilson, analogs, gamma, ENSO, bootstrap index, trend, AUC
backend/satellite.py    preloaded AppEEARS reader
backend/i18n.py         Spanish and English messages
backend/agent/          prompts (es, en) and Gemini call with a rule checker
backend/api.py          POST /api/farm endpoint and the page
backend/validate.py     leave-one-year-out and MAG calibration
frontend/index.html     map with GIBS layers, form and cards (ES/EN)
tests/test_mvp.py       the 12 layers of the test plan
docs/                   DECISIONS.md (sources and assumptions) and ROADMAP.md
```

MIT licence. Each user puts their own key in `.env`; no key goes into the repository, and a test checks it.
