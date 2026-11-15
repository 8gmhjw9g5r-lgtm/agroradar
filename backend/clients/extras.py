"""Non-NASA external sources: Open-Meteo (forecast), SoilGrids (soil) and NOAA ONI (ENSO).

All of them fail silently by returning None: the report says so and the evidence grade drops.
"""
import json
import time
import urllib.request

from backend import DATA

CACHE = DATA / "cache"


def _get(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def forecast(lat, lon, get=_get):
    """Open-Meteo, 7 days. Verified on 2026-11-15."""
    try:
        d = json.loads(get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                           "&daily=precipitation_sum,temperature_2m_max&forecast_days=7&timezone=auto"))["daily"]
        return {"source": "open_meteo", "daily": [{"date": f, "rain_mm": p, "t_max_c": t} for f, p, t in
                                                  zip(d["time"], d["precipitation_sum"], d["temperature_2m_max"])]}
    except Exception:
        return None


_soil_down_since = 0.0


def soil(lat, lon, get=_get, cache=CACHE / "soilgrids"):
    """SoilGrids 0-5 cm. Written from memory: it did not respond on 2026-11-15; units to be confirmed."""
    global _soil_down_since
    file = cache / f"{lat:.2f}_{lon:.2f}.json"
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    if time.time() - _soil_down_since < 3600:  # if it failed less than 1 h ago, don't wait for another timeout
        return None
    try:
        raw = json.loads(get(f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={lon}&lat={lat}"
                             "&property=clay&property=sand&property=silt&property=soc&property=nitrogen"
                             "&depth=0-5cm&value=mean", timeout=8))
        v = {l["name"]: l["depths"][0]["values"]["mean"] for l in raw["properties"]["layers"]}
        out = {"source": "soilgrids", "clay": v["clay"] / 10, "sand": v["sand"] / 10, "silt": v["silt"] / 10,
               "oc_pct": v["soc"] / 100, "n_g_kg": v["nitrogen"] / 100}
    except Exception:
        _soil_down_since = time.time()
        return None
    cache.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(out), encoding="utf-8")
    return out


def oni(get=_get, cache=CACHE / "oni.txt"):
    """NOAA CPC ONI per year (JJA season, the canícula's). Verified on 2026-11-15."""
    try:
        if not cache.exists():
            text = get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")  # never expires; delete to update
        rows = [l.split() for l in cache.read_text(encoding="utf-8").splitlines()[1:]]
        return {"jja": {int(f[1]): float(f[3]) for f in rows if f[0] == "JJA"},
                "latest": {"season": rows[-1][0], "year": int(rows[-1][1]), "oni": float(rows[-1][3])}}
    except Exception:
        return None
