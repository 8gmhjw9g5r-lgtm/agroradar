# Decisions, sources and assumptions

Log of the work loop: every threshold or formula, with its source or the mark **ASSUMPTION**.
Every number lives in `config/thresholds.yaml`; the graph lives in `config/graph.yaml`.

## Language (2026-11-15)
- Code, configuration, API fields, data files and docs are in English.
- Farmers see Spanish by default. The page has an ES/EN switch, and the API takes `"lang": "es" | "en"` (default `es`).
  Only texts change with the language (warnings, success definition, Gemini explanation, checker messages);
  every number is identical in both. A test checks this.
- Local terms are kept as they are: **primera** and **postrera** (the two growing seasons), **canícula**
  (the mid-summer dry spell, `dry_spell` in the code), **mz** (manzana, about 0.7 ha) and **qq** (quintal, 46 kg).
- Gemini has one prompt per language (`backend/agent/prompt_es.md`, `prompt_en.md`), with the same rules.
- The rename was checked against the old Spanish code: all 532 numbers of the API output (real calibration,
  publishable calibration and El Niño filter), plus `calibration.json` and `validation.json`, came out identical.

## Satellite layers on the map (NASA GIBS, 2026-11-15)
We were asked to add PML's GISportal. We did not bundle it: it is a 2017-era Node + Redis + Python 2 + GDAL stack
whose job is to view WMS/WMTS layers. Instead the page shows the same kind of layers straight from NASA GIBS
(WMTS, EPSG:3857, no key) on the existing Leaflet map. Layer names, tile matrix sets and legends were checked against
`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml`:

| Layer | Level | Use |
|---|---|---|
| `MODIS_Terra_CorrectedReflectance_TrueColor` | 9 | True colour |
| `MODIS_Terra_L3_NDVI_16Day` | 9 | Greenness |
| `IMERG_Precipitation_Rate` | 6 | Daily rain rate |
| `SMAP_L4_Analyzed_Root_Zone_Soil_Moisture` | 6 | Root-zone soil moisture |
| `MODIS_Terra_Land_Surface_Temp_Day` | 7 | Daytime land surface temperature |

The layers are **for viewing only** and do not enter the index. With no date, GIBS serves the latest image (`default`).

**The farmer never picks a layer (2026-11-15).** `backend/views.py` chooses up to 2 views per farm and the API returns
them as `satellite_views` with reason codes; the results page shows them with what they show, why they were chosen and
how to read them. Rules (**ASSUMPTION**, a UX choice): a plot's top risk scores 3 for its main view (water → soil
moisture, heat → ground heat, erosion → satellite photo, greenness → greenness); each ticked priority and bare soil add 1;
ties follow a fixed order. The page is a 4-question guided flow (plot, planting, land, priorities) and then results,
each step with a "why we ask this" note.

## Soil moisture alert proposal (2026-11-15)
An unsourced proposal for SMAP surface and root-zone moisture alerts (`docs/references/soil-moisture-alerts-source.pdf`) is
translated and evaluated in `docs/SOIL_MOISTURE_ALERTS.md`. Nothing from it is in the model yet. Adopted as next steps:
root-zone SMAP in the AppEEARS reader, and RZSM saturation as a postrera hypothesis. Rejected: irrigation instructions
and 24-hour plot alerts (rainfed farms; 9 km SMAP with days of delay).

## APIs verified with a real call (2026-11-15)

| Source | Result |
|---|---|
| NASA POWER daily | `https://power.larc.nasa.gov/api/temporal/daily/point`, `community=AG`. Parameters: `PRECTOTCORR` (mm/day), `T2M_MAX`, `T2M_MIN` (°C), `RH2M` (%). `fill_value` = -999. 1991-01-01 to 2026-11-12 without a single -999 in the two pilot cells. The response repeats the requested point in `geometry.coordinates`. |
| NOAA ONI | `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt` responds (columns SEAS YR TOTAL ANOM). Latest value: ASO 2026 = +2.46 (strong El Niño). |
| Open-Meteo | `/v1/forecast` with `daily=precipitation_sum,temperature_2m_max` responds. |
| SoilGrids | **Did not respond** (90 s timeout, then HTTP 503). The client is written from memory; units to be confirmed. If it fails, K and N use defaults with evidence C and the report says so. |
| AppEEARS | **Not tested**: needs an Earthdata account. The reader uses a normalized CSV (see `data/appeears/README.md`). |
| NASA GIBS | WMTS capabilities and tiles respond (see above). |
| POWER climatology | Not used: the 1991-2020 normal is computed from the daily series. |
| CMR, IRI | Outside the MVP. |

## POWER cache
- Key: `round(lat/0.5)*0.5`, `round(lon/0.625)*0.625` + parameters + schema version. One request per cell, no expiry (delete the file to refresh).
- San Miguel and La Unión fall in the same cell (13.5, -88.125); they share climate and differ by slope, greenness and soil.

## Formulas with a source
- e_s and VPD: Tetens equation in the FAO-56 form (Allen et al., 1998). VPD(30 °C, 50%) = 2.12 kPa (test 1).
- ET0: Hargreaves (FAO-56 eq. 52) with extraterrestrial radiation from FAO-56 eq. 21. Hargreaves is used because it only needs temperatures.
- R (erosivity): Renard and Freimund (1994), J. Hydrology 157: R = 0.0483·P^1.61 if P < 850 mm; otherwise 587.8 − 1.219·P + 0.004105·P².
- K (erodibility): Williams (1995), EPIC model, from sand, silt, clay and organic carbon; ×0.1317 to SI units.
- LS: S factor from McCool et al. (1987); L = 1 because a 22.13 m length is assumed (**ASSUMPTION**).
- C from NDVI: van der Knijff et al. (2000): C = exp(−2·NDVI/(1−NDVI)).
- Wilson at 80% with z = 1.2816.
- Gamma: Thom's estimator; CDF via the regularized incomplete gamma.

## Assumptions (all in `config/thresholds.yaml`)
- Pilot lat/lon bounds; pilot zones (San Miguel, La Unión, Chalatenango) and 15 km radius.
- Rain onset (20 mm in 3 days, no 7-day dry spell in the following 21, counted from day 4).
- Canícula: 15/07–31/08, risk if > 10 days; dry day < 1 mm. In postrera, the dry spell and stress are measured from planting to the end of flowering (the canícula has passed and the end of the cycle falls in the expected dry season).
- Heat: > 35 °C, risk if > 3 days at flowering. Cycle and flowering: maize 120 d (55–75), beans 75 d (35–50).
- Late onset = more than 15 days after the historical median.
- Water stress: fraction of 10-day blocks with rain/ET0 < 0.5.
- Season inferred from the month: January–July primera; August–December postrera.
- Default slope 10%; default K 0.03; C by declared cover (bare soil 0.45, stubble 0.2, green manure 0.1); `erosion_ref` = 200.
- Nitrogen: reference N 3 g/kg; the fixation and uptake table per crop has **no source**; the output is only a direction.
- **Rotation effects table (E)**: every cell is an assumption. It is the weakest part of the index and the index inherits that weakness.
- Weights: base 1 per variable; ×2 if the farmer marks that priority; nitrogen ×0.25 without a soil analysis. "Market" has no data in the MVP.
- Publication cutoffs: AUC ≥ 0.70 normal; 0.60–0.70 low confidence; < 0.60 not published.
- Erosion trend: "no clear trend" if the 80% CI of the slope includes 0 (p ≈ 0.2). It is a loose criterion, so we only talk about direction, never magnitude.
- ENSO: each year's phase is taken from the JJA ONI (the canícula season), with a ±0.5 threshold.

## Model design decisions
- **Threshold u of model 5**: set per plot as the 25th percentile of the base rotation's score, so maize after maize gives 75 by construction. Filtering by ENSO phase keeps that u, which is why the base index changes. Test 10 computes u on the series without drought and applies it to the series with drought.
- **Contribution to the index**: points the base index would rise if that variable were always as in its best observed year (counterfactual). A constant variable (no data) contributes 0.
- **Plot ranking**: only uses variables with real data. An assumed neutral risk, such as greenness without satellite, does not order plots.
- The index evaluates the planned crop's cycle (maize or beans; for green manure, the maize cycle). Rotations differ only through table E.
- The graph adds the edge `long_dry_spell → low_rain` (evidence A, by definition) to connect the canícula with the water chain. Greenness has no edge in the draft and is explained without a chain.
- If the index is not publishable, the backend removes `index`, `range_80` and `index_contribution` before responding and before calling the agent; in addition, the checker flags any "index … number" in the text, in Spanish or English.

## Validation findings (2026-11-15, `python -m backend.validate`)
- The spec says Wilson with k=13, n=35 gives "28 to 47%". The exact calculation gives **27.5–48.0%**, and the test uses that value.
- Leave-one-year-out Brier, long canícula: unadjusted frequency 0.0830; analog adjustment 0.0804 (San Miguel). The adjustment wins by very little, so it stays on, but the difference is within the noise.
- The long canícula is rare (3 of 36 years in San Miguel). POWER (MERRA-2 at 0.5°) tends to daily drizzle and almost never gives days < 1 mm in season. **The dry-day threshold needs review with an agronomist or local stations.**
- Rain onset 2025: day 150 (30 May) against a median of 136.5 in San Miguel. It is later than the median, but by about 2 weeks, not almost a month as FEWS NET reports, and it does not cross the "late onset" threshold (+15 days). It is reported without forcing it.

## MAG yields and calibration (2026-11-15)

**Data** (`data/mag_yields.csv`): total maize yield (qq/mz) for the 14 departments over 20 seasons, 2001-02 to 2022-23. It is Table 3 of each Anuario de Estadísticas Agropecuarias (DGEA-MAG).
- **PDF origin:** 2018-19 to 2022-23 come from mag.gob.sv; earlier ones from Internet Archive copies of `mag.gob.sv/download/anuario-de-estadisticas-agropecuarias-*`.
- **Missing years:** 2007-08 and 2008-09 are not archived. 1996-97 has no department table as text.
- **Later years:** there are no yearbooks after 2022-23. According to the press, in 2026 MAG restricted recent yearbooks citing statistical secrecy.
- **Extraction:** 15 years came from the PDF text (`pdftotext -layout`). Because the layout misaligns the names, rows are taken in the table's fixed order and accepted only if each region adds up to its departments.
- **Manual transcription:** 2002, 2006, 2019, 2020 and 2022 were transcribed from the page image (column `extraction`).
- **Validation:** all 280 rows satisfy production/area = yield (±0.3). National totals match MAG's retrospective, except 2004 and 2005, where the yearbook's own figure is used (the later retrospective looks revised). 2005 was also checked by eye against the page.
- **MAG's own errors:** the 2020-21 table has small internal inconsistencies; for example, the Ahuachapán total is not the sum of its seasons.
- **Sanity:** the worst years match known droughts. In 2001, La Unión gave 7.4 and San Miguel 16.2. In 2014, Chalatenango gave 28.9. In 2009, San Miguel gave 27.4.

**Yields by season** (rows with `season` = primera or postrera): from 2013-14 to 2022-23, only for Chalatenango, San Miguel and La Unión. They were transcribed from the page and yield was recomputed as production/area. Total yield mixes two harvests that can move in opposite directions. In 2014 (El Niño), San Miguel gave 19.9 in primera and 40.1 in postrera, with a total of 30.0. The mix also changes over time: San Miguel had more primera than postrera in 2013, and postrera dominates since 2015.

### Calibration v1 (discarded)
Total yield against the dominant season (San Miguel and La Unión in postrera, Chalatenango in primera), with 60 department-years. AUC 0.61 (0.51–0.71). By department: Chalatenango 0.92 · La Unión 0.66 · San Miguel 0.46.

### Calibration v2 (current, `data/calibration.json`)
**Changes decided from diagnosis and agronomic reasons, before looking at the AUC:**
1. **Postrera window.** The dry spell and water stress were measured from planting to harvest (August→December), so they included the normal dry season. The spell came out at 15 to 48 days every year and the risk was saturated, with no signal. Now in postrera they are measured from planting to the end of flowering (day 75; with planting on 25/08, until early November). In San Miguel the spell now varies between 2 and 16 days. Primera does not change.
2. **Each yield against its own season.**
   - Chalatenango: total 2001–2022 against primera (more than 97% is the rainy-season crop in every table).
   - San Miguel: primera against primera and postrera against postrera, 2013–2022.
   - La Unión: postrera only, because its primera is under 2,000 mz almost every year.
   - Eastern totals before 2013 are dropped, because their season mix is unknown.
3. **The publication cutoff is applied per season:** they are two different models (different windows) and each must earn its publication.

**Result:**
| Series | AUC | n | failures |
|---|---|---|---|
| Chalatenango / total (primera) | 0.92 | 20 | 6 |
| San Miguel / primera | 1.00 | 10 | 3 |
| San Miguel / postrera | 0.38 | 10 | 3 |
| La Unión / postrera | 0.29 | 10 | 3 |
| **Primera (pooled)** | **0.90** (CI80 0.81–0.99) | 30 | → **normal, published** |
| **Postrera (pooled)** | **0.33** (CI80 0.13–0.57) | 20 | → **not published**, risks only |
| All together (reference) | 0.67 (0.54–0.79) | 50 | |

**Honest reading:**
- **Primera:** the model works in primera, which is where the canícula and heat at flowering act. Even so, the sample is small: the AUC of 1.00 in San Miguel comes from 10 years with 3 failures.
- **Postrera:** the model does not explain postrera. The AUC below 0.5 in both series suggests that what damages postrera is not what we measure.
- **Excess-rain hypothesis:** tested only as a diagnosis, without changing the model, and **not confirmed**. The correlation with September–October rain was −0.19 in San Miguel and −0.33 in La Unión; with the 3-day maximum, +0.26 and +0.05.
- **Explanations to investigate:** pests, prices, the retreat of the rains according to local stations, or the 0.5° POWER cell not capturing eastern rainfall.
- **Overfitting risk:** 2 design changes were made with 50 points. Neither was chosen by AUC, but the calibration should be repeated when more years are available.

## Still needed to trust the index
1. Postrera: find what explains its bad years (local stations, rain retreat date, MAG or FEWS NET damage reports) and recalibrate with `python -m backend.validate mag`.
2. AppEEARS downloads for the pilot zones (SMAP, NASADEM, HLS/MODIS) converted to the normalized CSV.
3. Sources for table E, the nitrogen table and every threshold.
4. SoilGrids responding again, or a local K and N.
