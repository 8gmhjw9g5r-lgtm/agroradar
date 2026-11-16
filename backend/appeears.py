"""Downloads the pilot-zone satellite series from NASA AppEEARS. Run by us, never by the app.

    python -m backend.appeears submit     -> sends 3 point requests (NDVI, elevation, SMAP); saves the task ids
    python -m backend.appeears status     -> shows whether AppEEARS has finished (minutes to hours)
    python -m backend.appeears download   -> downloads the results to data/appeears/raw/ and converts them
    python -m backend.appeears convert    -> converts again from data/appeears/raw/ (no login needed)

Needs a free NASA Earthdata account, with EARTHDATA_USERNAME and EARTHDATA_PASSWORD in .env.
Products and layers were checked against the public AppEEARS catalogue on 2026-11-15.

Output: one CSV per pilot zone in the format of data/appeears/README.md (date,layer,value,quality_ok), with
layers ndvi, slope, smap (surface, 0-5 cm) and smap_rz (root zone, 0-100 cm).
Each zone is sampled at its centre and 8 points 5 km away, so values describe the zone, not a single plot.
"""
import base64
import csv
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from statistics import mean

from backend import DATA, ROOT, cfg

API = "https://appeears.earthdatacloud.nasa.gov/api"
DIR = DATA / "appeears"
RAW = DIR / "raw"
TASKS_FILE = DIR / "tasks.json"
RING_KM = 5
DEM_STEP_DEG = 2 / 3600  # 2 arc-seconds (~62 m): NASADEM pixels are 1 arc-second
M_PER_DEG = 111_320

TASKS = {
    "ndvi": {"product": "MOD13Q1.061", "layers": ["_250m_16_days_NDVI", "_250m_16_days_pixel_reliability"],
             "start": "02-18-2000", "points": "samples"},
    "dem": {"product": "NASADEM_NC.001", "layers": ["NASADEM_HGT"], "start": "02-11-2000", "end": "02-21-2000",
            "points": "stencils"},
    "smap": {"product": "SPL4SMGP.008", "layers": ["Geophysical_Data_sm_surface", "Geophysical_Data_sm_rootzone"],
             "start": "03-31-2015", "points": "centres"},
}


# --- points ---

def samples(zones):
    """Centre plus 8 points on a 5 km ring, per zone: [(zone, k, lat, lon)]."""
    out = []
    for name, z in zones.items():
        out.append((name, 0, z["lat"], z["lon"]))
        for k in range(8):
            a = math.radians(45 * k)
            dlat = RING_KM * 1000 * math.cos(a) / M_PER_DEG
            dlon = RING_KM * 1000 * math.sin(a) / (M_PER_DEG * math.cos(math.radians(z["lat"])))
            out.append((name, k + 1, round(z["lat"] + dlat, 5), round(z["lon"] + dlon, 5)))
    return out


def coordinates(kind, zones):
    pts = samples(zones)
    if TASKS[kind]["points"] == "centres":
        pts = [p for p in pts if p[1] == 0]
    if TASKS[kind]["points"] != "stencils":
        return [{"id": f"{z}-{k}", "category": z, "latitude": la, "longitude": lo} for z, k, la, lo in pts]
    out = []  # each sample plus its 4 neighbours, to compute slope by central differences
    for z, k, la, lo in pts:
        for nb, (dla, dlo) in {"c": (0, 0), "n": (1, 0), "s": (-1, 0), "e": (0, 1), "w": (0, -1)}.items():
            out.append({"id": f"{z}-{k}-{nb}", "category": z,
                        "latitude": round(la + dla * DEM_STEP_DEG, 6), "longitude": round(lo + dlo * DEM_STEP_DEG, 6)})
    return out


def task_body(kind, zones, today=None):
    t = TASKS[kind]
    end = t.get("end") or (today or date.today()).strftime("%m-%d-%Y")
    return {"task_type": "point", "task_name": f"agroradar_{kind}",
            "params": {"dates": [{"startDate": t["start"], "endDate": end}],
                       "layers": [{"product": t["product"], "layer": l} for l in t["layers"]],
                       "coordinates": coordinates(kind, zones)}}


# --- conversion (no network) ---

def _col(header, layer):
    cols = [h for h in header if h.endswith(layer)]
    if not cols:
        raise ValueError(f"column for layer {layer} not found; columns: {header}")
    return cols[0]


def _rows(path):
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def convert_ndvi(path):
    header, rows = _rows(path)
    c_ndvi, c_rel = _col(header, "_250m_16_days_NDVI"), _col(header, "_250m_16_days_pixel_reliability")
    out = defaultdict(list)
    for r in rows:
        v, rel = _num(r[c_ndvi]), _num(r[c_rel])
        if v is None:
            continue
        if abs(v) > 1.5:  # raw integers: apply the 0.0001 scale factor
            v *= 0.0001
        if v < -0.2:  # fill value
            continue
        ok = rel is not None and rel in (0, 1)  # 0 good, 1 marginal; 2 snow/ice, 3 cloudy
        out[r["ID"].rsplit("-", 1)[0]].append((r["Date"][:10], "ndvi", round(v, 4), int(ok)))
    return out


def convert_smap(path):
    header, rows = _rows(path)
    cols = {"smap": _col(header, "sm_surface"), "smap_rz": _col(header, "sm_rootzone")}
    acc = defaultdict(list)  # 3-hourly values -> daily mean
    for r in rows:
        zone = r["ID"].rsplit("-", 1)[0]
        for layer, c in cols.items():
            v = _num(r[c])
            if v is not None and 0 <= v <= 0.9:
                acc[(zone, r["Date"][:10], layer)].append(v)
    out = defaultdict(list)
    for (zone, d, layer), vs in sorted(acc.items()):
        out[zone].append((d, layer, round(mean(vs), 4), 1))
    return out


def convert_dem(path):
    header, rows = _rows(path)
    c = _col(header, "NASADEM_HGT")
    z = {}
    for r in rows:
        v = _num(r[c])
        if v is not None and v > -1000:
            z[r["ID"]] = (v, float(r["Latitude"]))
    out = defaultdict(list)
    for pid in [p[:-2] for p in z if p.endswith("-c")]:
        if not all(f"{pid}-{nb}" in z for nb in "nsew"):
            continue
        if z[f"{pid}-c"][0] <= 0:
            continue  # centre on the sea surface (NASADEM gives 0 m): not land
        lat = z[f"{pid}-c"][1]
        dy = 2 * DEM_STEP_DEG * M_PER_DEG
        dx = dy * math.cos(math.radians(lat))
        gy = (z[f"{pid}-n"][0] - z[f"{pid}-s"][0]) / dy
        gx = (z[f"{pid}-e"][0] - z[f"{pid}-w"][0]) / dx
        out[pid.rsplit("-", 1)[0]].append(("2000-02-11", "slope", round(100 * math.hypot(gx, gy), 1), 1))
    return out


def convert(raw=RAW, out_dir=DIR):
    """Turns whatever raw files exist into one normalized CSV per zone. Returns rows written per zone and layer."""
    parts = {"ndvi": convert_ndvi, "smap": convert_smap, "dem": convert_dem}
    by_zone = defaultdict(list)
    for kind, fn in parts.items():
        for f in sorted(raw.glob(f"agroradar_{kind}*.csv")):
            for zone, rows in fn(f).items():
                by_zone[zone].extend(rows)
    summary = {}
    for zone, rows in by_zone.items():
        rows.sort()
        with open(out_dir / f"{zone}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["date", "layer", "value", "quality_ok"])
            w.writerows(rows)
        summary[zone] = {layer: sum(r[1] == layer for r in rows) for layer in ("ndvi", "slope", "smap", "smap_rz")}
    return summary


# --- AppEEARS API (needs the Earthdata login) ---

class _NoAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Downloads redirect to cloud storage, which rejects a second Authorization header."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.headers.pop("Authorization", None)
        return new


_opener = urllib.request.build_opener(_NoAuthOnRedirect)


def _call(path, token=None, body=None, method=None, basic=None, raw=False):
    req = urllib.request.Request(f"{API}/{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None))
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if basic:
        req.add_header("Authorization", "Basic " + base64.b64encode(basic.encode()).decode())
    with _opener.open(req, timeout=300) as r:
        data = r.read()
    return data if raw else json.loads(data)


def login():
    from backend.api import _env
    _env()
    user, pw = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not user or not pw:
        raise SystemExit("Add EARTHDATA_USERNAME and EARTHDATA_PASSWORD to .env first (see .env.example).")
    return _call("login", method="POST", basic=f"{user}:{pw}")["token"]


def submit():
    token, zones = login(), cfg()["satellite"]["pilot_zones"]
    tasks = {kind: _call("task", token, task_body(kind, zones), method="POST")["task_id"] for kind in TASKS}
    DIR.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=1), encoding="utf-8")
    return tasks


def _tasks():
    if not TASKS_FILE.exists():
        raise SystemExit("No requests yet: run `python -m backend.appeears submit` first.")
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def status():
    token = login()
    return {kind: _call(f"task/{tid}", token)["status"] for kind, tid in _tasks().items()}


def download():
    token, st = login(), {}
    RAW.mkdir(parents=True, exist_ok=True)
    for kind, tid in _tasks().items():
        s = _call(f"task/{tid}", token)["status"]
        st[kind] = s
        if s != "done":
            continue
        for f in _call(f"bundle/{tid}", token)["files"]:
            if f["file_name"].endswith("-results.csv"):
                (RAW / f"agroradar_{kind}-results.csv").write_bytes(_call(f"bundle/{tid}/{f['file_id']}", token, raw=True))
    return st, convert()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "submit":
        print("Requests sent:", submit(), "\nAppEEARS takes minutes to hours. Check with: python -m backend.appeears status")
    elif cmd == "status":
        print(status())
    elif cmd == "download":
        st, summary = download()
        print("Status:", st)
        print("Rows written per zone:", json.dumps(summary, indent=1))
        if any(s != "done" for s in st.values()):
            print("Some requests are not finished yet: run download again later.")
    elif cmd == "convert":
        print(json.dumps(convert(), indent=1))
    else:
        print(__doc__)
