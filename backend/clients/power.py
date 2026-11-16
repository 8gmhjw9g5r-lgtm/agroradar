"""NASA POWER client (daily, per point) with an on-disk cache per grid cell.

Parameter names and URL verified with a real call on 2026-11-15.
"""
import json
import urllib.request
from datetime import date, timedelta

from backend import DATA

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = {"PRECTOTCORR": "rain_mm", "T2M_MAX": "t_max_c", "T2M_MIN": "t_min_c", "RH2M": "rh_pct"}
START = "19910101"
SCHEMA = "v2"  # bump when the cached field names change; old files are simply ignored
CACHE = DATA / "cache" / "power"
requests_made = 0  # counter of real requests (cache test)


def cell(lat, lon):
    return round(round(lat / 0.5) * 0.5, 3), round(round(lon / 0.625) * 0.625, 3)


def _http(lat, lon, end):
    q = (f"{URL}?parameters={','.join(PARAMS)}&community=AG&latitude={lat}&longitude={lon}"
         f"&start={START}&end={end}&format=JSON")
    with urllib.request.urlopen(q, timeout=120) as r:
        return json.load(r)


def parse(raw, lat, lon):
    """Turns the raw response into the catalogue schema; fails with a clear message."""
    try:
        coords = raw["geometry"]["coordinates"]
        par = raw["properties"]["parameter"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"POWER: response missing field {e}") from None
    if abs(coords[0] - lon) > 1e-6 or abs(coords[1] - lat) > 1e-6:
        raise ValueError(f"POWER: returned cell {coords[1]},{coords[0]} does not match {lat},{lon}")
    missing = [p for p in PARAMS if p not in par]
    if missing:
        raise ValueError(f"POWER: missing parameters {missing}")
    fill = raw.get("header", {}).get("fill_value", -999.0)
    days = sorted(par["PRECTOTCORR"])
    ok = lambda f: all(par[p].get(f) not in (None, fill) for p in PARAMS)
    # The newest days are often not processed yet (fill value): drop them from the end.
    # A gap anywhere else is still an error.
    while days and not ok(days[-1]):
        days.pop()
    if not days:
        raise ValueError("POWER: no complete days in the response")
    daily = []
    for f in days:
        row = {"date": f"{f[:4]}-{f[4:6]}-{f[6:]}"}
        for p, name in PARAMS.items():
            v = par[p].get(f)
            if v is None or v == fill:
                raise ValueError(f"POWER: missing value ({fill}) in {p} on {row['date']}")
            row[name] = v
        daily.append(row)
    return {"source": "nasa_power", "cell": {"lat": lat, "lon": lon},
            "start": daily[0]["date"], "end": daily[-1]["date"], "daily": daily}


def fetch(lat, lon, http=_http, cache=CACHE):
    """One real request per cell; after that everything comes from disk."""
    global requests_made
    lat, lon = cell(lat, lon)
    file = cache / f"{lat}_{lon}_{'-'.join(PARAMS)}_{SCHEMA}.json"
    if file.exists():
        return json.loads(file.read_text(encoding="utf-8"))
    # the cache never expires; delete the file to pull new days.
    end = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
    requests_made += 1
    data = parse(http(lat, lon, end), lat, lon)
    cache.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data), encoding="utf-8")
    return data
