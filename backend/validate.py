"""Historical validation (leave one year out) and calibration of the index against MAG yields.

    python -m backend.validate        -> data/validation.json
    python -m backend.validate mag    -> data/calibration.json (needs data/mag_yields.csv)
"""
import csv
import json
import sys
from datetime import date
from statistics import median

from backend import DATA, cfg
from backend import models as M
from backend.api import analyze_plot, events


def typical_plot(name, z, season="primera"):
    md = "08-25" if season == "postrera" else "05-25"
    return {"plot_id": name, "geometry": {"lat": z["lat"], "lon": z["lon"]}, "planned_crop": "maize",
            "planting_date": f"{date.today().year}-{md}", "season": season, "priorities": []}


def loo(today=None):
    c, today = cfg(), today or date.today()
    out, better = {"zones": {}}, []
    for name, z in c["satellite"]["pilot_zones"].items():
        feats = [f for f in analyze_plot(typical_plot(name, z), c, today, None, None)["_feats"] if f["year"] <= 2025]
        ev = events(feats, c)
        res = {}
        for k, o in ev.items():
            n = len(o)
            base = [(sum(o) - o[i]) / (n - 1) for i in range(n)]
            res[k] = {"brier_base": round(M.brier(base, o), 4), "n": n}
        # model 2 (analogs at 15 July) against the unadjusted frequency, for the long dry spell
        o = ev["long_dry_spell"]
        adj = []
        for i, f in enumerate(feats):
            sel = M.analogs(feats[:i] + feats[i + 1:], f, c)
            adj.append(sum(s["dry_spell_days"] > c["dry_spell"]["threshold_days"] for s in sel) / len(sel) if sel else
                       (sum(o) - o[i]) / (len(o) - 1))
        res["long_dry_spell"]["brier_analog_adjustment"] = round(M.brier(adj, o), 4)
        better.append(res["long_dry_spell"]["brier_analog_adjustment"] < res["long_dry_spell"]["brier_base"])
        doys = {f["year"]: f["rain_onset"].timetuple().tm_yday if f["rain_onset"] else None for f in feats}
        med = median(d for d in doys.values() if d)
        res["onset_2025"] = {"day_of_year": doys.get(2025), "historical_median": med,
                             "later_than_median": doys.get(2025) is None or doys[2025] > med}
        out["zones"][name] = res
    out["season_adjustment_active"] = all(better)
    if not out["season_adjustment_active"]:
        out["warning"] = "The analog-year adjustment does not beat the historical frequency; it is turned off."
    (DATA / "validation.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def calibrate_mag(file=DATA / "mag_yields.csv", today=None):
    """CSV: department,year,season,yield_qq_mz. Success = yield above the department's 25th percentile."""
    c, today = cfg(), today or date.today()
    with open(file, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    scores, labels, by_series, by_season = [], [], {}, {}
    for name, z in c["satellite"]["pilot_zones"].items():
        for cal in z["calibration"]:
            yld = {int(r["year"]): float(r["yield_qq_mz"]) for r in rows
                   if r["department"] == z["department"] and r.get("season", "total") == cal["series"]}
            if len(yld) < 8:
                continue
            p25 = M.percentile(list(yld.values()), 0.25)
            S = analyze_plot(typical_plot(name, z, cal["season"]), c, today, None, None)["_base_scores"]
            s_d, l_d = [S[a] for a in yld if a in S], [yld[a] > p25 for a in yld if a in S]
            scores += s_d
            labels += l_d
            e = by_season.setdefault(cal["season"], ([], []))
            e[0].extend(s_d)
            e[1].extend(l_d)
            by_series[f"{z['department']} / {cal['series']}"] = {"auc": round(M.auc(s_d, l_d), 3), "n": len(s_d),
                                                                 "failures": l_d.count(False)}
    if len(scores) < 10 or len(set(labels)) < 2:
        raise SystemExit("Not enough MAG data to calibrate (at least 10 years with successes and failures).")
    auc = M.auc(scores, labels)
    out = {"auc": round(auc, 3), "ci80": M.auc_ci80(scores, labels), "n": len(scores), "by_series": by_series,
           "mean_auc_by_series": round(sum(v["auc"] for v in by_series.values()) / len(by_series), 3),
           # the index is published per season: primera and postrera use different windows and are calibrated apart
           "by_season": {ep: {"auc": round(M.auc(s, l), 3), "ci80": M.auc_ci80(s, l), "n": len(s),
                              "level": M.publishable(M.auc(s, l), c)[1]} for ep, (s, l) in by_season.items()},
           "table": M.calibration_table(scores, labels), "level": M.publishable(auc, c)[1],
           "source": "MAG, Anuarios de Estadísticas Agropecuarias 2001-02 to 2022-23 (missing 2007-08 and 2008-09); "
                     "maize yield by department, total or by season (2013-2022)"}
    (DATA / "calibration.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(json.dumps(calibrate_mag() if sys.argv[1:] == ["mag"] else loo(), indent=1, ensure_ascii=False))
