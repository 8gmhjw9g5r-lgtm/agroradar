# NASA Space Apps 2026 — project page text

Team: Adapting Cuzucos · Challenge: Field Shift: Adapting Farms with NASA Data
Each section below is one field of the project page form, ready to paste. Items in **[brackets]** need the team before submitting.

---

## Project Name

AgroRadar

---

## High-Level Project Summary

AgroRadar is a free web app that tells small farmers in El Salvador, before they plant, how likely their next harvest is to succeed and which crop rotation gives them the best chance. A farmer marks the plot on a map (or uses GPS or coordinates), answers three simple questions, and in about a minute gets an estimated success rate from 0 to 100 with its range, the main climate risks (long canícula, late rains, heat at flowering), the rain to expect, the slope and erosion risk of the land, a 7-day forecast and satellite views chosen for that plot.

It addresses Field Shift by turning NASA's free and open Earth data — 35 years of NASA POWER climate records plus MODIS greenness, NASADEM slope and SMAP soil moisture — into a decision a farmer can act on: compare corn after corn, corn with beans and corn with green manure for their own field. This matters because in 2026 a long canícula (the mid-summer dry spell) cost local farmers a large share of their crops; most of them decide what and when to plant without any data. AgroRadar works on a phone, in Spanish and English, needs no account, and says plainly which parts are measured and which are assumed. It supports the farmer's judgment; it does not replace it.

---

## Link to Project Demo

**[Upload `demo/agroradar-demo.mp4` (29 s) to YouTube as "Unlisted" or "Public", or to Google Drive with "Anyone with the link can view", and paste that link here. Test it in a private browser window first.]**

---

## Link to Final Project

https://agroradar.space

**[Optional second link: the code at https://github.com/8gmhjw9g5r-lgtm/agroradar — only once the repository is made public; right now it is private and judges cannot open it.]**

---

## Detailed Project Description

**What it does.** AgroRadar estimates, for a specific plot, how often each of three rotations — corn after corn, corn with beans, corn with green manure — has given a good harvest in that place over the last 35 years, where a "good" harvest is one that is not among the worst quarter of harvests in the zone. The result is a success rate from 0 to 100, always shown with an 80% range, plus:
- the climate risks for that season and how often each happened (long canícula, late rains, very hot days while the plant flowers);
- rain while the crop grows in a normal year and in a dry year (1 in 4), and when the rains typically start;
- the slope of the plot and what it means for erosion, separately from rain;
- which factors take the most points off the result, each marked as measured, estimated or assumed;
- a 7-day weather forecast and NASA satellite maps (soil moisture, greenness, rain, ground heat or a true-colour photo), chosen automatically from the farmer's answers and results, each with a "what it shows / why we show it / how to read it" explanation;
- a list of where every number comes from, so assumed values are never hidden.

**How it works.** The farmer goes through a guided flow: (1) mark the plot by tapping the map, using GPS or pasting coordinates; (2) say what they will plant and between which dates — the app works out whether it is the first (primera) or second (postrera) harvest; (3) describe the soil cover and slope with picture choices; (4) choose what worries them most (water, erosion, nitrogen) and, optionally, compare only with El Niño, La Niña or neutral years. The server then downloads 35 years of daily NASA POWER rain, temperature and humidity for that grid cell, computes for every past year the rain onset, the longest dry spell inside the sensitive weeks of the crop, heat days at flowering, vapour pressure deficit, evapotranspiration and soil loss (RUSLE), and builds the success index with bootstrap resampling so it always comes with a range. For three pilot zones (San Miguel, La Unión, Chalatenango) it adds satellite data we pre-processed with NASA AppEEARS: MODIS NDVI greenness 2000–2026 and NASADEM slope. The index was checked against official corn yields from El Salvador's Ministry of Agriculture (MAG) for 2001–2022: for the first harvest (primera) it separates good and bad years with an AUC of 0.90 (80% range 0.81–0.99), so it is published; for the second harvest (postrera) it does not yet (AUC 0.33), so the app shows risks only and says so. An optional Gemini explanation turns the result into plain language, and a rule checker rejects any sentence with a number that is not in the data.

**Benefits.**
- A farmer can see the risk of a canícula or late rains for their own field before spending on seed and fertilizer.
- It makes the case for soil-protecting rotations (beans, green manure) with numbers from their own land: on steep plots, covering the soil raises the success rate.
- It is free, needs no account, works on a phone, in Spanish and English, with large readable text (Atkinson Hyperlegible) for low-literacy and older users.
- It is honest about uncertainty: every result has a range, unvalidated results are not published, and assumed values are labelled.
- Results can be shared on WhatsApp as plain text, so extension workers and cooperatives can pass them on.

**What we hope to achieve.** We want AgroRadar to become a planting-season companion for El Salvador's small producers and the technicians who advise them (CENTA, MAG, cooperatives): first a field pilot in San Miguel, La Unión and Chalatenango with agronomist review of every threshold; then soil-moisture alerts during the season, root-zone SMAP data to explain the bad postrera years, and coverage of every plot in the country — and later any farm in Central America's Dry Corridor facing a changing climate.

**Tools and languages.**
- Backend: Python 3.9, FastAPI, Uvicorn, PyYAML; 39 automated tests (unittest).
- Frontend: HTML, CSS and JavaScript (no framework), Leaflet 1.9.4 maps, the team's AgroRadar design system (palette, Atkinson Hyperlegible typography, components).
- Data pipeline: Python scripts for NASA AppEEARS (submit, status, download, convert), NASA POWER client with cache, SoilGrids pre-fetch.
- Hosting: Render (web service), GitHub, domain agroradar.space (Hostinger DNS).
- Demo video: headless Google Chrome for the scenes, Pillow and FFmpeg for animation and encoding, ElevenLabs for the narration voice.
- Hardware: no special hardware; a laptop for development and any smartphone to use it.

---

## Use of Super Intelligence (SI)

Yes. The idea, the problem framing (the 2026 canícula losses in El Salvador), the choice of challenge, the success definition, the scope decisions and the reviews of every change came from the team. We used SI tools as follows:

- **Code and data (Anthropic Claude, through Claude Code):** wrote and tested most of the code under our direction — the FastAPI backend and statistical model, the NASA POWER and AppEEARS data scripts, the bilingual web interface built from our design system, the 39 automated tests, the deployment configuration and the project documentation. It also proposed fixes we reviewed (for example dropping NASA POWER days that are not processed yet). Acknowledged in the repository README and in `docs/SPACE_APPS_SUBMISSION.md`.
- **Demo video (Claude):** wrote the 29-second script with us and generated the scene graphics and the editing script. The video carries a visible "AI-generated" watermark on every frame. App screenshots are real captures of AgroRadar; the backgrounds are NASA Blue Marble imagery.
- **Audio (ElevenLabs, voice "Zara"):** the narration voice is AI-generated; this is stated here, in the video description and in the video file's metadata.
- **In the product (Google Gemini, optional):** when a Gemini key is configured, the app writes a plain-language explanation of the result; a rule checker rejects any text with numbers or claims not in the data. The public site currently runs without it.
- **[Team: confirm whether the AgroRadar logo and design system were made by hand or with an image-generation tool; if with a tool, name it here.]**

No NASA logos, flags or mission identifiers are used in AgroRadar or in the SI-generated content.

---

## NASA Data

- **NASA POWER (Prediction of Worldwide Energy Resources), daily point API, AG community** — precipitation (PRECTOTCORR), maximum and minimum temperature at 2 m (T2M_MAX, T2M_MIN) and relative humidity (RH2M), 1991 to the present, for the farmer's 0.5° × 0.625° grid cell. This is the core of the model: rain onset, dry spells (canícula), heat at flowering, evapotranspiration, rain erosivity and every risk probability. https://power.larc.nasa.gov
- **NASA AppEEARS (Application for Extracting and Exploring Analysis Ready Samples)** with a NASA Earthdata account, used to extract point time series for our three pilot zones:
  - **MOD13Q1.061** (MODIS Terra Vegetation Indices, 16-day, 250 m): NDVI and pixel reliability, 2000–2026 — vegetation greenness, its 10-year trend and bare-soil days.
  - **NASADEM_NC.001** (NASADEM elevation, 30 m): slope of each plot, used in the RUSLE erosion model.
  - **SPL4SMGP.008** (SMAP Level 4 surface and root-zone soil moisture, 3-hourly, 9 km): requested and being integrated for soil-moisture anomalies.
- **NASA GIBS (Global Imagery Browse Services) WMTS** — satellite layers shown in the app, chosen per plot: MODIS Terra Corrected Reflectance True Color, MODIS Terra NDVI 16-day, GPM IMERG precipitation rate, SMAP L4 analyzed root-zone soil moisture and MODIS Terra land surface temperature (day), with GIBS legends. https://gibs.earthdata.nasa.gov
- **NASA Blue Marble (shaded relief and bathymetry) via GIBS** — background imagery of El Salvador and the Americas in the demo video.
- **NASA Earthdata** — account and documentation for AppEEARS and the product user guides.

---

## Space Agency Partner Data and Other References

**Space Agency Partner data:** we did not use partner-agency data in this version. Our next step is ESA Copernicus Sentinel-2 imagery (10 m) to see crop greenness at the scale of a single small plot, and JAXA GSMaP rainfall to cross-check NASA rain over El Salvador.

**Data**
- MAG El Salvador (Ministerio de Agricultura y Ganadería), *Anuarios de Estadísticas Agropecuarias* 2001-02 to 2022-23 — corn yield by department and season, used to validate the index (some tables transcribed from images of the yearbooks).
- NOAA Climate Prediction Center — Oceanic Niño Index (ONI), to classify El Niño, La Niña and neutral years. https://www.cpc.ncep.noaa.gov
- Open-Meteo — 7-day weather forecast API (CC BY 4.0, non-commercial use). https://open-meteo.com
- ISRIC SoilGrids — soil texture, carbon and nitrogen (client built; values pending while the service was unavailable). https://soilgrids.org
- OpenStreetMap — base map tiles, © OpenStreetMap contributors (ODbL). https://www.openstreetmap.org/copyright

**Methods and references**
- RUSLE (Revised Universal Soil Loss Equation) for erosion; FAO-56 Hargreaves method for reference evapotranspiration; Wilson score intervals and gamma distribution for probabilities; bootstrap resampling for the index range.
- **[Team: add the full title and author of the soil-moisture alerts reference document in `docs/references/`.]**

**Software and libraries (all open source unless noted)**
- Python, FastAPI, Uvicorn, Pydantic, Starlette, PyYAML, httpx.
- Leaflet 1.9.4 (BSD-2-Clause) for maps.
- Google Fonts: Atkinson Hyperlegible (Braille Institute, SIL Open Font License) and Public Sans (SIL OFL).
- Render (hosting), GitHub (code), Hostinger (domain and DNS).
- Demo video: Google Chrome (headless), Pillow, FFmpeg (via imageio-ffmpeg).

**SI tools (see the SI section):** Anthropic Claude (Claude Code), ElevenLabs, Google Gemini (optional, in the app).

**Images:** the AgroRadar logo and design system were created by the team **[confirm, see SI section]**; the illustrations in the app and video were drawn for this project; app screenshots are our own; satellite imagery is NASA (GIBS, Blue Marble).
