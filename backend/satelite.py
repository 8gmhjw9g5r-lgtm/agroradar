"""Lector de las series de AppEEARS precargadas por zona piloto.

Formato normalizado (ver data/appeears/LEEME.md): fecha,capa,valor,calidad_ok
con capa en {ndvi, smap, pendiente}. La conversión desde el CSV crudo de AppEEARS
se hace al bajar los archivos, porque los nombres de capa aún no están verificados.
"""
import csv
import json
import math
from datetime import date, timedelta
from statistics import mean, pstdev

from backend import DATA
from backend.models import tendencia

DIR = DATA / "appeears"


def zona_de(lat, lon, c):
    for nombre, z in c["satelite"]["zonas_piloto"].items():
        km = 111 * math.hypot(lat - z["lat"], (lon - z["lon"]) * math.cos(math.radians(lat)))
        if km <= z["radio_km"]:
            return nombre
    return None


def encolar(parcela):
    DIR.mkdir(parents=True, exist_ok=True)
    with open(DIR / "cola.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(parcela) + "\n")


def leer(zona, siembra_md, ciclo_dias, c, d=DIR, hoy=None):
    archivo = d / f"{zona}.csv"
    if not zona or not archivo.exists():
        return None
    with open(archivo, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    hoy = hoy or date.today()
    por_capa = {}
    for f in filas:
        por_capa.setdefault(f["capa"], []).append((date.fromisoformat(f["fecha"]), float(f["valor"]), f["calidad_ok"] == "1"))
    ndvi = por_capa.get("ndvi", [])
    validos = [(f, v) for f, v, ok in ndvi if ok]  # descarta píxeles con nubes
    frac = len(validos) / len(ndvi) if ndvi else 0.0
    out = {"fuente": "nasa_appeears", "frac_validas": round(frac, 2),
           "evidencia": "B" if frac >= c["satelite"]["min_validas"] else "C", "ndvi_por_anio": {}, "suelo_desnudo_dias": {}}
    pend = [v for _, v, ok in por_capa.get("pendiente", []) if ok]
    out["pendiente_pct"] = round(mean(pend), 1) if pend else None
    out["pendiente_max_pct"] = round(max(pend), 1) if pend else None
    for a in sorted({f.year for f, _ in validos}):
        s = date(a, *siembra_md)
        temp = [v for f, v in validos if s <= f <= s + timedelta(ciclo_dias)]
        if temp:
            out["ndvi_por_anio"][a] = mean(temp)
        anio = [v for f, v in validos if f.year == a]
        out["suelo_desnudo_dias"][a] = round(365 * sum(v < c["satelite"]["ndvi_suelo_desnudo"] for v in anio) / len(anio))
    maximos = [max(v for f, v in validos if f.year == a) for a in sorted({f.year for f, _ in validos})][-10:]
    out["tendencia_verdor"] = tendencia(maximos)["direccion"] if len(maximos) >= 4 else None
    smap = [(f, v) for f, v, ok in por_capa.get("smap", []) if ok]
    if smap:  # temporada actual (90 días) contra la misma ventana de años anteriores
        ventana = lambda f: 0 <= hoy.timetuple().tm_yday - f.timetuple().tm_yday < 90  # ponytail: no cruza el año
        hist = [v for f, v in smap if ventana(f) and f.year < hoy.year]
        act = [v for f, v in smap if ventana(f) and f.year == hoy.year]
        if len(hist) > 1 and act and pstdev(hist) > 0:
            out["humedad_anomalia_sd"] = round((mean(act) - mean(hist)) / pstdev(hist), 2)
    return out
