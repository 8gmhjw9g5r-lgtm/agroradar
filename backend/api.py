"""Farm endpoint: validates, fetches data (cached), runs the models and asks the agent for an explanation."""
import json
import os
from datetime import date, timedelta
from statistics import mean, median, pstdev

from backend import DATA, ROOT, cfg, graph
from backend import features as F
from backend import models as M
from backend import satellite
from backend.agent import gemini
from backend.clients import extras, power
from backend.i18n import lang_of, t

CROPS = ("maize", "bean", "green_manure")


def _env():
    f = ROOT / ".env"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def centroid(g):
    if "lat" in g:
        return g["lat"], g["lon"]
    if g["type"] == "Point":
        return g["coordinates"][1], g["coordinates"][0]
    ring = g["coordinates"][0][:-1] if g["coordinates"][0][0] == g["coordinates"][0][-1] else g["coordinates"][0]
    return mean(p[1] for p in ring), mean(p[0] for p in ring)


def validate_farm(farm, c, today, lang="es"):
    v = c["validation"]
    ps = farm.get("plots") or []
    if not ps:
        raise ValueError(t(lang, "no_plots"))
    if len(ps) > v["max_plots"]:
        raise ValueError(t(lang, "too_many_plots", max=v["max_plots"]))
    for p in ps:
        lat, lon = centroid(p["geometry"])
        if not (v["lat"][0] <= lat <= v["lat"][1] and v["lon"][0] <= lon <= v["lon"][1]):
            raise ValueError(t(lang, "outside_pilot", plot_id=p["plot_id"]))
        if abs((date.fromisoformat(p["planting_date"]) - today).days) > 366:
            raise ValueError(t(lang, "planting_date_range", plot_id=p["plot_id"]))
        if p.get("planned_crop") not in CROPS:
            raise ValueError(t(lang, "bad_crop", plot_id=p["plot_id"]))


def _calibration():
    f = DATA / "calibration.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _validation():
    f = DATA / "validation.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def events(feats, c):
    """Risk events per year (model 1)."""
    doys = [f["rain_onset"].timetuple().tm_yday for f in feats if f["rain_onset"]]
    med = median(doys)
    p25 = M.percentile([f["cycle_rain_mm"] for f in feats], 0.25)
    norm = [f["cycle_rain_mm"] for f in feats if c["normal_period"][0] <= f["year"] <= c["normal_period"][1]]
    mu, sd = mean(norm), pstdev(norm)
    return {
        "long_dry_spell": [f["dry_spell_days"] > c["dry_spell"]["threshold_days"] for f in feats],
        "late_onset": [not f["rain_onset"] or f["rain_onset"].timetuple().tm_yday > med + c["late_onset_days"] for f in feats],
        "flowering_heat": [f["heat_days"] > c["heat"]["threshold_days"] for f in feats],
        "rain_deficit": [f["cycle_rain_mm"] < p25 for f in feats],
        "rain_anomaly": [(f["cycle_rain_mm"] - mu) / sd < c["rain_anomaly_sd"] for f in feats],
    }


def analyze_plot(p, c, today, oni, phase, lang="es"):
    assumptions, missing = [], []
    lat, lon = centroid(p["geometry"])
    series = power.fetch(lat, lon)
    days = F.by_date(series)
    pd = date.fromisoformat(p["planting_date"])
    md = (pd.month, pd.day)
    season = p.get("season")
    if not season:
        season = "primera" if pd.month in c["season_by_month"]["primera"] else "postrera"
        assumptions.append(f"season_inferred_{season}")
    crop = p["planned_crop"] if p["planned_crop"] in ("maize", "bean") else "maize"
    cr = c["crops"][crop]
    assumptions += [f"cycle_{crop}_{cr['cycle_days']}_days", f"flowering_{crop}_{cr['flowering'][0]}_{cr['flowering'][1]}_days",
                    f"dry_spell_threshold_{c['dry_spell']['threshold_days']}_days",
                    f"heat_{c['heat']['t_max_c']}C_over_{c['heat']['threshold_days']}_days",
                    "rotation_effects_unsourced", f"erosion_ref_{c['rusle']['erosion_ref']}", "LS_length_22m"]
    feats = [f for a in range(1991, today.year + 1) if (f := F.year_features(days, a, md, crop, season, lat, c))]
    years = [f["year"] for f in feats]
    n = len(feats)

    # --- satellite, slope and soil ---
    zone = satellite.zone_of(lat, lon, c)
    sat = satellite.read(zone, md, cr["cycle_days"], c)
    if not sat:
        satellite.enqueue({"plot_id": p["plot_id"], "lat": lat, "lon": lon})
        missing.append("satellite_data_pending")
    if p.get("slope_pct") is not None:
        slope, slope_src = p["slope_pct"], "user"
    elif sat and sat["slope_pct"] is not None:
        slope, slope_src = sat["slope_pct"], "nasa_appeears"
    else:
        slope, slope_src = c["rusle"]["default_slope_pct"], "assumed"
        assumptions.append(f"default_slope_{slope}pct")
        missing.append("slope_pct")
    soil = extras.soil(lat, lon)
    if soil:
        K = F.rusle_K(soil["sand"], soil["silt"], soil["clay"], soil["oc_pct"])
    else:
        K = c["rusle"]["K_default"]
        assumptions.append(f"K_default_{K}")
        missing.append("soilgrids_no_response")
    LS = F.rusle_LS(slope)
    ndvi = sat["ndvi_by_year"] if sat and sat["evidence"] == "B" else {}
    C_dec = c["rusle"]["C_by_cover"].get(p.get("current_cover"), c["rusle"]["C_default"])
    if len(ndvi) < n:
        assumptions.append(f"C_cover_{C_dec}")
    R_mean = mean(F.rusle_R(f["annual_rain_mm"]) for f in feats if f["annual_rain_mm"])
    eros = [F.erosion(F.rusle_R(f["annual_rain_mm"]) if f["annual_rain_mm"] else R_mean, K, LS,
                      F.rusle_C(ndvi[f["year"]]) if f["year"] in ndvi else C_dec) for f in feats]

    # --- risks normalized 0-1 per year ---
    if len(ndvi) >= 5:
        mu_v, sd_v = mean(ndvi.values()), pstdev(ndvi.values()) or 1
        greenness = [min(1, max(0, 0.5 + (mu_v - ndvi[a]) / sd_v / 4)) if a in ndvi else 0.5 for a in years]
    else:
        greenness = [0.5] * n
        assumptions.append("greenness_neutral_no_satellite")
    an = p.get("soil_analysis") or {}
    if an.get("nitrogen_pct") is not None:
        n_g_kg, ev_n, src_n = an["nitrogen_pct"] * 10, "B", "user"
    else:
        n_g_kg, ev_n, src_n = (soil["n_g_kg"], "C", "soilgrids") if soil else (None, "C", "assumed")
        missing.append("soil_analysis")
    rn = 0.5 if n_g_kg is None else min(1, max(0, 1 - n_g_kg / c["nitrogen"]["N_ref_g_kg"]))
    R = {"dry_spell": [min(1, f["dry_spell_days"] / (2 * c["dry_spell"]["threshold_days"])) for f in feats],
         "heat": [min(1, f["heat_days"] / (2 * c["heat"]["threshold_days"])) for f in feats],
         "moisture": [f["stress_fraction"] for f in feats],
         "erosion": [min(1, e / c["rusle"]["erosion_ref"]) for e in eros],
         "greenness": greenness,
         "nitrogen": [rn] * n}

    # --- models 1 to 4 ---
    ev = events(feats, c)
    risks = [{"event": k, **M.prob(v, c["model"]["z80"]), "source": "nasa_power", "evidence": "A"} for k, v in ev.items()]
    val = _validation()
    current = next((f for f in feats if f["year"] == today.year), None)
    adjustment = None
    if (val.get("season_adjustment_active") and pd.year == today.year and current
            and date(today.year, *c["dry_spell"]["window"][0]) <= today <= date(today.year, *c["dry_spell"]["window"][1])):
        sel = M.analogs([f for f in feats if f["year"] != today.year], current, c)
        adjustment = ({"long_dry_spell": M.prob([f["dry_spell_days"] > c["dry_spell"]["threshold_days"] for f in sel]),
                       "n_analogs": len(sel)}
                      if sel else {"warning": t(lang, "few_analogs", n=c["model"]["min_analogs"])})
    phase_by_year = {a: M.enso_phase(v, c["model"]["enso_oni_threshold"]) for a, v in oni["jja"].items()} if oni else {}
    enso = M.enso_effect(dict(zip(years, ev["long_dry_spell"])), phase_by_year)

    # --- model 5: index per rotation ---
    w = M.weights(p.get("priorities") or [], c, bool(an))
    S_base = M.scores(R, {}, w)
    u = M.threshold(S_base)
    sel = [i for i, a in enumerate(years) if not phase or phase_by_year.get(a) == phase]
    if len(sel) < 5:  # too few years in that phase: no filtering
        sel, phase = list(range(n)), None
    rotations = []
    for rid, rot in c["rotations"].items():
        S = M.scores(R, rot["effects"], w)
        idx, rg = M.index([S[i] for i in sel], u, c["model"]["bootstrap"], c["model"]["seed"])
        bal = sum(c["nitrogen"]["fixation_kg_ha"][k] - c["nitrogen"]["uptake_kg_ha"][k] for k in rot["crops"])
        th = c["nitrogen"]["direction_threshold_kg_ha"]
        rotations.append({"id": rid, "index": idx, "range_80": rg, "is_base": bool(rot.get("base")),
                          "nitrogen": "up" if bal > th else "down" if bal < -th else "stable"})
    idx_base = next(r["index"] for r in rotations if r["is_base"])
    ap = M.contributions({v: [R[v][i] for i in sel] for v in R}, w, u, idx_base)
    meta = {"dry_spell": ("A", "nasa_power", n), "heat": ("A", "nasa_power", n), "moisture": ("B", "nasa_power", n),
            "erosion": ("B" if ndvi and slope_src != "assumed" else "C", "nasa_appeears" if ndvi else "nasa_power", n),
            "greenness": (sat["evidence"] if sat else "C", "nasa_appeears" if sat else "assumed", len(ndvi)),
            "nitrogen": (ev_n, src_n, 1)}
    contrib = sorted(({"variable": v, "index_contribution": ap[v], "evidence": meta[v][0], "source": meta[v][1],
                       "n_years": meta[v][2]} for v in w), key=lambda x: x["index_contribution"])
    g = graph()
    chains = [g["chains"][x["variable"]] for x in contrib[:3] if x["index_contribution"] < 0 and x["variable"] in g["chains"]]
    last = [e for f, e in zip(feats, eros) if f["annual_rain_mm"]][-10:]
    # the ranking only uses variables with data: an assumed neutral risk does not order plots
    with_data = {v: w[v] for v in w if meta[v][1] != "assumed"}
    wd = {v: x / sum(with_data.values()) for v, x in with_data.items()}
    mean_risk = {v: mean(R[v]) for v in wd}
    return {
        "plot_id": p["plot_id"], "area_mz": p.get("area_mz"), "lat": lat, "lon": lon, "season": season,
        "success_definition": t(lang, "success_definition"), "rotations": rotations, "contributions": contrib, "chains": chains,
        "risks": risks, "season_adjustment": adjustment, "cycle_rain_gamma": M.prob_low_rain([f["cycle_rain_mm"] for f in feats]),
        "enso": enso, "enso_phase_filter": phase, "n_years_index": len(sel),
        "erosion_trend": M.trend(last) if len(last) >= 4 else None,
        "plot_priority": round(M.priority(mean_risk, wd), 3),
        "top_variables": [v for v, _ in sorted(((v, wd[v] * mean_risk[v]) for v in wd), key=lambda x: -x[1])[:2]],
        "terrain_profile": {
            "climate": {"source": "nasa_power", "cell": series["cell"], "years": f"{years[0]}-{years[-1]}",
                        "mean_annual_rain_mm": round(mean(f["annual_rain_mm"] for f in feats if f["annual_rain_mm"])),
                        "median_rain_onset": (date(2001, 1, 1) + timedelta(round(median(
                            f["rain_onset"].timetuple().tm_yday for f in feats if f["rain_onset"])) - 1)).strftime("%m-%d"),
                        "flowering_vpd_kpa": round(mean(f["flowering_vpd_kpa"] for f in feats), 2)},
            "slope_pct": slope, "slope_source": slope_src, "mean_erosion_index": round(mean(eros), 1),
            "soil_moisture_anomaly_sd": sat.get("soil_moisture_anomaly_sd") if sat else None,
            "greenness": {"mean_ndvi": round(mean(ndvi.values()), 2) if ndvi else None,
                          "trend_10_years": sat.get("greenness_trend") if sat else None,
                          "bare_soil_days": sat["bare_soil_days"] if sat else None},
            "soil": soil, "satellite_valid_frac": sat["valid_frac"] if sat else None,
        },
        "missing_data": missing, "assumptions_used": assumptions,
        "_feats": feats, "_base_scores": dict(zip(years, S_base)),  # internal: validation and calibration
    }


def analyze_farm(farm, today=None, with_agent=True):
    _env()
    c, today = cfg(), today or date.today()
    lang = lang_of(farm.get("lang"))
    validate_farm(farm, c, today, lang)
    oni = extras.oni()
    phase = farm.get("enso_phase")
    if phase and not oni:
        phase = None
    cal = _calibration()
    plots = [analyze_plot(p, c, today, oni, phase, lang) for p in farm["plots"]]
    warnings = []
    for x in plots:
        x.pop("_feats"), x.pop("_base_scores")
        # each season has its own calibration; if there is none, the global one is used
        ce = (cal.get("by_season", {}).get(x["season"]) or cal) if cal else None
        auc = ce["auc"] if ce else None
        ok, level = M.publishable(auc, c)
        x |= {"index_publishable": ok, "confidence_level": level, "calibration_auc": auc,
              "auc_ci80": ce.get("ci80") if ce else None}
        if not cal:
            msg = t(lang, "not_calibrated")
        elif level == "low_confidence":
            msg = t(lang, "low_confidence", season=x["season"], auc=auc, lo=ce["ci80"][0], hi=ce["ci80"][1])
        elif not ok:
            msg = t(lang, "not_published", season=x["season"], auc=auc)
        else:
            msg = None
        if msg and msg not in warnings:
            warnings.append(msg)
        if not ok:  # without calibration the number is not published
            for r in x["rotations"]:
                r["index"] = r["range_80"] = None
            for k in x["contributions"]:
                k.pop("index_contribution")
    ranking = [{"position": i + 1, "plot_id": x["plot_id"], "priority": x["plot_priority"],
                "why": x["top_variables"]}
               for i, x in enumerate(sorted(plots, key=lambda x: -x["plot_priority"]))]
    if not oni:
        warnings.append(t(lang, "no_oni"))
    out = {"farm_id": farm.get("farm_id"), "lang": lang, "plots": plots, "ranking": ranking, "warnings": warnings,
           "current_enso": oni["latest"] | {"phase": M.enso_phase(oni["latest"]["oni"])} if oni else None,
           "forecast_7d": extras.forecast(plots[0]["lat"], plots[0]["lon"]),
           "explanation": None, "agent_warnings": []}
    key = os.environ.get("GEMINI_API_KEY")
    if with_agent and key:
        payload = {"plots": plots, "ranking": ranking, "graph": graph()["edges"]}
        try:
            out["explanation"] = gemini.explain(payload, key, lang=lang)
            out["agent_warnings"] = gemini.verify(out["explanation"], payload, lang)
        except Exception as e:
            out["agent_warnings"] = [t(lang, "agent_failed", error=e)]
    elif with_agent:
        out["agent_warnings"] = [t(lang, "no_gemini_key")]
    return out


# --- web server ---
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

app = FastAPI(title="Dry Corridor crop risk")


@app.post("/api/farm")
def api_farm(farm: dict):
    try:
        return analyze_farm(farm)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, {"warning": str(e)})


@app.get("/")
def home():
    return FileResponse(ROOT / "frontend" / "index.html")
