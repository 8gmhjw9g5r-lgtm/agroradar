"""Fuentes externas no NASA: Open-Meteo (pronóstico), SoilGrids (suelo) y ONI de NOAA (ENSO).

Todas fallan en silencio devolviendo None: el reporte lo dice y baja la evidencia.
"""
import json
import time
import urllib.request

from backend import DATA

CACHE = DATA / "cache"


def _get(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


def pronostico(lat, lon, get=_get):
    """Open-Meteo, 7 días. Verificado el 2026-11-15."""
    try:
        d = json.loads(get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                           "&daily=precipitation_sum,temperature_2m_max&forecast_days=7&timezone=auto"))["daily"]
        return {"fuente": "open_meteo", "diario": [{"fecha": f, "lluvia_mm": p, "t_max_c": t} for f, p, t in
                                                    zip(d["time"], d["precipitation_sum"], d["temperature_2m_max"])]}
    except Exception:
        return None


_suelo_caido = 0.0


def suelo(lat, lon, get=_get, cache=CACHE / "soilgrids"):
    """SoilGrids 0-5 cm. De memoria: no respondió el 2026-11-15; unidades a confirmar."""
    global _suelo_caido
    archivo = cache / f"{lat:.2f}_{lon:.2f}.json"
    if archivo.exists():
        return json.loads(archivo.read_text(encoding="utf-8"))
    if time.time() - _suelo_caido < 3600:  # si falló hace menos de 1 h, no esperar otro timeout
        return None
    try:
        raw = json.loads(get(f"https://rest.isric.org/soilgrids/v2.0/properties/query?lon={lon}&lat={lat}"
                             "&property=clay&property=sand&property=silt&property=soc&property=nitrogen"
                             "&depth=0-5cm&value=mean", timeout=8))
        v = {l["name"]: l["depths"][0]["values"]["mean"] for l in raw["properties"]["layers"]}
        out = {"fuente": "soilgrids", "arcilla": v["clay"] / 10, "arena": v["sand"] / 10, "limo": v["silt"] / 10,
               "oc_pct": v["soc"] / 100, "n_g_kg": v["nitrogen"] / 100}
    except Exception:
        _suelo_caido = time.time()
        return None
    cache.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(out), encoding="utf-8")
    return out


def oni(get=_get, cache=CACHE / "oni.txt"):
    """ONI de NOAA CPC por año (estación JJA, la de la canícula). Verificado el 2026-11-15."""
    try:
        if not cache.exists():
            texto = get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(texto, encoding="utf-8")  # ponytail: no expira; borrar para actualizar
        filas = [l.split() for l in cache.read_text(encoding="utf-8").splitlines()[1:]]
        return {"jja": {int(f[1]): float(f[3]) for f in filas if f[0] == "JJA"},
                "ultimo": {"estacion": filas[-1][0], "anio": int(filas[-1][1]), "oni": float(filas[-1][3])}}
    except Exception:
        return None
