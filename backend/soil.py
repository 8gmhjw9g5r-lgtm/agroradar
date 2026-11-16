"""Soil values per pilot zone, saved in advance so the app never waits on SoilGrids.

    python -m backend.soil      -> fetches SoilGrids for each pilot zone centre and writes data/soil/<zone>.json

Soil barely changes, so this runs once (and again only if the source improves). SoilGrids is often down:
the command reports which zones failed, and you can simply run it again later.
Evidence stays C: SoilGrids is a 250 m global model, not a field analysis.
"""
import json
import sys

from backend import DATA, cfg
from backend.clients import extras

DIR = DATA / "soil"


def saved(zone, d=DIR):
    f = d / f"{zone}.json" if zone else None
    return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None


def prefetch(d=DIR, fetch=extras.soil):
    d.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, z in cfg()["satellite"]["pilot_zones"].items():
        if (d / f"{name}.json").exists():
            report[name] = "already saved"
            continue
        extras._soil_down_since = 0.0  # try every zone, even if the previous one failed
        s = fetch(z["lat"], z["lon"], timeout=90)
        if s:
            (d / f"{name}.json").write_text(json.dumps(s | {"lat": z["lat"], "lon": z["lon"]}, indent=1), encoding="utf-8")
            report[name] = "saved"
        else:
            report[name] = "SoilGrids did not respond; run again later"
    return report


if __name__ == "__main__":
    r = prefetch()
    for k, v in r.items():
        print(f"{k}: {v}")
    sys.exit(0 if all(v != "SoilGrids did not respond; run again later" for v in r.values()) else 1)
