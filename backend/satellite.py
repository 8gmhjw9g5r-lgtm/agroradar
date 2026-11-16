"""Reader for the AppEEARS series preloaded per pilot zone.

Normalized format (see data/appeears/README.md): date,layer,value,quality_ok
with layer in {ndvi, smap, smap_rz, slope}. The raw AppEEARS files are converted to this format by
`python -m backend.appeears` (see backend/appeears.py).
"""
import csv
import json
import math
from datetime import date, timedelta
from statistics import mean, pstdev

from backend import DATA
from backend.models import trend

DIR = DATA / "appeears"


def zone_of(lat, lon, c):
    for name, z in c["satellite"]["pilot_zones"].items():
        km = 111 * math.hypot(lat - z["lat"], (lon - z["lon"]) * math.cos(math.radians(lat)))
        if km <= z["radius_km"]:
            return name
    return None


def enqueue(plot):
    DIR.mkdir(parents=True, exist_ok=True)
    with open(DIR / "queue.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(plot) + "\n")


def read(zone, planting_md, cycle_days, c, d=DIR, today=None):
    file = d / f"{zone}.csv"
    if not zone or not file.exists():
        return None
    with open(file, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    today = today or date.today()
    by_layer = {}
    for r in rows:
        by_layer.setdefault(r["layer"], []).append((date.fromisoformat(r["date"]), float(r["value"]), r["quality_ok"] == "1"))
    ndvi = by_layer.get("ndvi", [])
    valid = [(f, v) for f, v, ok in ndvi if ok]  # drops cloudy pixels
    frac = len(valid) / len(ndvi) if ndvi else 0.0
    out = {"source": "nasa_appeears", "valid_frac": round(frac, 2),
           "evidence": "B" if frac >= c["satellite"]["min_valid"] else "C", "ndvi_by_year": {}, "bare_soil_days": {}}
    slope = [v for _, v, ok in by_layer.get("slope", []) if ok]
    out["slope_pct"] = round(mean(slope), 1) if slope else None
    out["slope_max_pct"] = round(max(slope), 1) if slope else None
    for a in sorted({f.year for f, _ in valid}):
        s = date(a, *planting_md)
        season = [v for f, v in valid if s <= f <= s + timedelta(cycle_days)]
        if season:
            out["ndvi_by_year"][a] = mean(season)
        year = [v for f, v in valid if f.year == a]
        out["bare_soil_days"][a] = round(365 * sum(v < c["satellite"]["bare_soil_ndvi"] for v in year) / len(year))
    peaks = [max(v for f, v in valid if f.year == a) for a in sorted({f.year for f, _ in valid})][-10:]
    out["greenness_trend"] = trend(peaks)["direction"] if len(peaks) >= 4 else None
    # current season (90 days) against the same window in earlier years; surface (smap) and root zone (smap_rz)
    window = lambda f: 0 <= today.timetuple().tm_yday - f.timetuple().tm_yday < 90  # does not cross the year
    for layer, key in (("smap", "soil_moisture_anomaly_sd"), ("smap_rz", "rootzone_moisture_anomaly_sd")):
        series = [(f, v) for f, v, ok in by_layer.get(layer, []) if ok]
        hist = [v for f, v in series if window(f) and f.year < today.year]
        cur = [v for f, v in series if window(f) and f.year == today.year]
        if len(hist) > 1 and cur and pstdev(hist) > 0:
            out[key] = round((mean(cur) - mean(hist)) / pstdev(hist), 2)
    return out
