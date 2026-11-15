"""Cliente de NASA POWER (diario por punto) con caché en disco por celda.

Nombres de parámetros y URL verificados con una llamada real el 2026-11-15.
"""
import json
import urllib.request
from datetime import date, timedelta

from backend import DATA

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = {"PRECTOTCORR": "lluvia_mm", "T2M_MAX": "t_max_c", "T2M_MIN": "t_min_c", "RH2M": "hr_pct"}
INICIO = "19910101"
CACHE = DATA / "cache" / "power"
solicitudes = 0  # contador de solicitudes reales (prueba de caché)


def celda(lat, lon):
    return round(round(lat / 0.5) * 0.5, 3), round(round(lon / 0.625) * 0.625, 3)


def _http(lat, lon, fin):
    q = (f"{URL}?parameters={','.join(PARAMS)}&community=AG&latitude={lat}&longitude={lon}"
         f"&start={INICIO}&end={fin}&format=JSON")
    with urllib.request.urlopen(q, timeout=120) as r:
        return json.load(r)


def parsear(raw, lat, lon):
    """Convierte la respuesta cruda al esquema del catálogo; falla con mensaje claro."""
    try:
        coords = raw["geometry"]["coordinates"]
        par = raw["properties"]["parameter"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"POWER: respuesta sin el campo {e}") from None
    if abs(coords[0] - lon) > 1e-6 or abs(coords[1] - lat) > 1e-6:
        raise ValueError(f"POWER: la celda devuelta {coords[1]},{coords[0]} no coincide con {lat},{lon}")
    faltan = [p for p in PARAMS if p not in par]
    if faltan:
        raise ValueError(f"POWER: faltan parámetros {faltan}")
    fill = raw.get("header", {}).get("fill_value", -999.0)
    diario = []
    for f in sorted(par["PRECTOTCORR"]):
        fila = {"fecha": f"{f[:4]}-{f[4:6]}-{f[6:]}"}
        for p, nombre in PARAMS.items():
            v = par[p].get(f)
            if v is None or v == fill:
                raise ValueError(f"POWER: dato faltante ({fill}) en {p} el {fila['fecha']}")
            fila[nombre] = v
        diario.append(fila)
    return {"fuente": "nasa_power", "celda": {"lat": lat, "lon": lon},
            "inicio": diario[0]["fecha"], "fin": diario[-1]["fecha"], "diario": diario}


def obtener(lat, lon, http=_http, cache=CACHE):
    """Una sola solicitud real por celda; después todo sale de disco."""
    global solicitudes
    lat, lon = celda(lat, lon)
    archivo = cache / f"{lat}_{lon}_{'-'.join(PARAMS)}.json"
    if archivo.exists():
        return json.loads(archivo.read_text(encoding="utf-8"))
    # ponytail: la caché no expira; borrar el archivo para traer días nuevos.
    fin = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
    solicitudes += 1
    datos = parsear(http(lat, lon, fin), lat, lon)
    cache.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(datos), encoding="utf-8")
    return datos
