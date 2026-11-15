"""Features agroclimáticas y de erosión. Fórmulas y fuentes en docs/DECISIONES.md."""
import math
from datetime import date, timedelta
from statistics import mean


def e_s(t):
    """Presión de vapor de saturación en kPa (T en °C)."""
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def vpd(t, hr):
    return e_s(t) * (1 - hr / 100)


def racha_seca(lluvias, umbral=1.0):
    mx = cur = 0
    for mm in lluvias:
        cur = cur + 1 if mm < umbral else 0
        mx = max(mx, cur)
    return mx


def rango(d0, d1):
    return [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]


def inicio_lluvias(lluvia, anio, c):
    """Primer día desde el 1 de mayo con >=20 mm en 3 días y sin racha seca de 7 días en los 21 siguientes."""
    il = c["inicio_lluvias"]
    for d in rango(date(anio, *il["desde"]), date(anio, *il["hasta"])):
        if sum(lluvia.get(d + timedelta(i), 0) for i in range(3)) >= il["mm_3_dias"]:
            sig = [lluvia.get(d + timedelta(3 + i), 0) for i in range(il["ventana_dias"])]
            if racha_seca(sig, c["dia_seco_mm"]) < il["racha_seca_dias"]:
                return d
    return None


def ra_mm(lat, doy):
    """Radiación extraterrestre (FAO-56 ec. 21) en mm/día equivalentes."""
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    dl = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(dl))
    ra = 24 * 60 / math.pi * 0.082 * dr * (ws * math.sin(phi) * math.sin(dl) + math.cos(phi) * math.cos(dl) * math.sin(ws))
    return 0.408 * ra


def et0_hargreaves(tmax, tmin, lat, doy):
    return 0.0023 * ((tmax + tmin) / 2 + 17.8) * math.sqrt(max(tmax - tmin, 0)) * ra_mm(lat, doy)


def por_fecha(serie):
    return {date.fromisoformat(r["fecha"]): r for r in serie["diario"]}


def features_anio(dias, anio, siembra_md, cultivo, epoca, lat, c):
    """Features de un año para una fecha de siembra (mes, día). None si el ciclo no tiene datos completos."""
    siembra = date(anio, *siembra_md)
    cu = c["cultivos"][cultivo]
    cosecha = siembra + timedelta(cu["ciclo_dias"] - 1)
    if siembra not in dias or cosecha not in dias:
        return None
    lluvia = {d: r["lluvia_mm"] for d, r in dias.items() if d.year == anio}
    ciclo = rango(siembra, cosecha)
    if epoca == "primera":
        v0, v1 = c["canicula"]["ventana"]
        ventana, sensible = rango(date(anio, *v0), date(anio, *v1)), ciclo
    else:
        # en postrera la canícula ya pasó y el final del ciclo cae en la estación seca esperada:
        # racha y estrés se miden de la siembra al fin de la floración (etapa sensible)
        ventana = sensible = rango(siembra, siembra + timedelta(cu["floracion"][1]))
    flor = rango(siembra + timedelta(cu["floracion"][0]), siembra + timedelta(cu["floracion"][1]))
    bl = c["estres_hidrico"]["bloque_dias"]
    bloques = [sensible[i:i + bl] for i in range(0, len(sensible) - bl + 1, bl)]
    estres = [sum(dias[d]["lluvia_mm"] for d in b) /
              sum(et0_hargreaves(dias[d]["t_max_c"], dias[d]["t_min_c"], lat, d.timetuple().tm_yday) for d in b)
              for b in bloques]
    fin_anio = date(anio, 12, 31)
    return {
        "anio": anio,
        "inicio_lluvias": inicio_lluvias(lluvia, anio, c),
        "racha_canicula": racha_seca([dias[d]["lluvia_mm"] for d in ventana if d in dias], c["dia_seco_mm"]),
        "lluvia_ciclo": sum(dias[d]["lluvia_mm"] for d in ciclo),
        "lluvia_hasta_corte": sum(dias[d]["lluvia_mm"] for d in rango(date(anio, 5, 1), date(anio, *c["canicula"]["ventana"][0]))),
        "dias_calor": sum(dias[d]["t_max_c"] > c["calor"]["t_max_c"] for d in flor),
        "vpd_floracion": mean(vpd((dias[d]["t_max_c"] + dias[d]["t_min_c"]) / 2, dias[d]["hr_pct"]) for d in flor),
        "frac_estres": sum(x < c["estres_hidrico"]["cociente_riesgo"] for x in estres) / len(estres),
        "lluvia_anual": sum(lluvia.values()) if fin_anio in dias else None,
    }


# --- RUSLE como índice relativo: A = R·K·LS·C·P ---

def rusle_R(p_anual):
    """Erosividad anual (MJ·mm/ha/h/año) desde lluvia anual. Renard y Freimund (1994)."""
    return 0.0483 * p_anual ** 1.61 if p_anual < 850 else 587.8 - 1.219 * p_anual + 0.004105 * p_anual ** 2


def rusle_K(arena, limo, arcilla, oc):
    """Erodabilidad (t·ha·h/ha/MJ/mm) desde textura (%) y carbono orgánico (%). Williams (1995), EPIC."""
    sn1 = 1 - arena / 100
    f = ((0.2 + 0.3 * math.exp(-0.0256 * arena * (1 - limo / 100)))
         * (limo / (arcilla + limo)) ** 0.3
         * (1 - 0.25 * oc / (oc + math.exp(3.72 - 2.95 * oc)))
         * (1 - 0.7 * sn1 / (sn1 + math.exp(-5.51 + 22.9 * sn1))))
    return 0.1317 * f


def rusle_LS(pendiente_pct):
    """Factor de pendiente de McCool et al. (1987) con longitud de 22.13 m (L = 1, supuesto)."""
    s = math.sin(math.atan(pendiente_pct / 100))
    return 10.8 * s + 0.03 if pendiente_pct < 9 else 16.8 * s - 0.5


def rusle_C(ndvi):
    """Cobertura desde NDVI. Van der Knijff et al. (2000): C = exp(-2·NDVI/(1-NDVI))."""
    return math.exp(-2 * ndvi / (1 - ndvi)) if ndvi < 1 else 0.0


def erosion(R, K, LS, C, P=1.0):
    return R * K * LS * C * P
