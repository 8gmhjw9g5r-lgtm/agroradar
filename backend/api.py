"""Endpoint de la finca: valida, trae datos (con caché), corre los modelos y pide la explicación al agente."""
import json
import os
from datetime import date, timedelta
from statistics import mean, median, pstdev

from backend import DATA, RAIZ, cfg, grafo
from backend import features as F
from backend import models as M
from backend import satelite
from backend.agent import gemini
from backend.clients import extras, power

DEFINICION_EXITO = "rendimiento sobre el percentil 25 historico de la zona"


def _env():
    f = RAIZ / ".env"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def centroide(g):
    if "lat" in g:
        return g["lat"], g["lon"]
    if g["type"] == "Point":
        return g["coordinates"][1], g["coordinates"][0]
    anillo = g["coordinates"][0][:-1] if g["coordinates"][0][0] == g["coordinates"][0][-1] else g["coordinates"][0]
    return mean(p[1] for p in anillo), mean(p[0] for p in anillo)


def validar(finca, c, hoy):
    v = c["validacion"]
    ps = finca.get("parcelas") or []
    if not ps:
        raise ValueError("La finca no trae parcelas.")
    if len(ps) > v["max_parcelas"]:
        raise ValueError(f"Máximo {v['max_parcelas']} parcelas por finca en el MVP.")
    for p in ps:
        lat, lon = centroide(p["geometria"])
        if not (v["lat"][0] <= lat <= v["lat"][1] and v["lon"][0] <= lon <= v["lon"][1]):
            raise ValueError(f"La parcela {p['parcela_id']} está fuera de la zona piloto de El Salvador; no se calcula.")
        if abs((date.fromisoformat(p["fecha_siembra"]) - hoy).days) > 366:
            raise ValueError(f"La fecha de siembra de {p['parcela_id']} debe estar dentro de 12 meses alrededor de hoy.")
        if p.get("cultivo_planeado") not in ("maiz", "frijol", "abono_verde"):
            raise ValueError(f"cultivo_planeado de {p['parcela_id']} debe ser maiz, frijol o abono_verde.")


def _calibracion():
    f = DATA / "calibracion.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _validacion():
    f = DATA / "validacion.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def eventos(feats, c):
    """Eventos de riesgo por año (modelo 1)."""
    doys = [f["inicio_lluvias"].timetuple().tm_yday for f in feats if f["inicio_lluvias"]]
    med = median(doys)
    p25 = M.percentil([f["lluvia_ciclo"] for f in feats], 0.25)
    norm = [f["lluvia_ciclo"] for f in feats if c["normal"][0] <= f["anio"] <= c["normal"][1]]
    mu, sd = mean(norm), pstdev(norm)
    return {
        "canicula_larga": [f["racha_canicula"] > c["canicula"]["umbral_dias"] for f in feats],
        "inicio_tardio": [not f["inicio_lluvias"] or f["inicio_lluvias"].timetuple().tm_yday > med + c["inicio_tardio_dias"] for f in feats],
        "calor_floracion": [f["dias_calor"] > c["calor"]["umbral_dias"] for f in feats],
        "deficit_lluvia": [f["lluvia_ciclo"] < p25 for f in feats],
        "anomalia_lluvia": [(f["lluvia_ciclo"] - mu) / sd < c["anomalia_lluvia_sd"] for f in feats],
    }


def analizar_parcela(p, c, hoy, oni, fase):
    supuestos, faltan = [], []
    lat, lon = centroide(p["geometria"])
    serie = power.obtener(lat, lon)
    dias = F.por_fecha(serie)
    fs = date.fromisoformat(p["fecha_siembra"])
    md = (fs.month, fs.day)
    epoca = p.get("epoca")
    if not epoca:
        epoca = "primera" if fs.month in c["epoca_por_mes"]["primera"] else "postrera"
        supuestos.append(f"epoca_deducida_{epoca}")
    cultivo = p["cultivo_planeado"] if p["cultivo_planeado"] in ("maiz", "frijol") else "maiz"
    cu = c["cultivos"][cultivo]
    supuestos += [f"ciclo_{cultivo}_{cu['ciclo_dias']}_dias", f"floracion_{cultivo}_{cu['floracion'][0]}_{cu['floracion'][1]}_dias",
                  f"umbral_canicula_{c['canicula']['umbral_dias']}_dias", f"calor_{c['calor']['t_max_c']}C_mas_de_{c['calor']['umbral_dias']}_dias",
                  "efectos_rotacion_sin_fuente", f"erosion_ref_{c['rusle']['erosion_ref']}", "LS_longitud_22m"]
    feats = [f for a in range(1991, hoy.year + 1) if (f := F.features_anio(dias, a, md, cultivo, epoca, lat, c))]
    anios = [f["anio"] for f in feats]
    n = len(feats)

    # --- satélite, pendiente y suelo ---
    zona = satelite.zona_de(lat, lon, c)
    sat = satelite.leer(zona, md, cu["ciclo_dias"], c)
    if not sat:
        satelite.encolar({"parcela_id": p["parcela_id"], "lat": lat, "lon": lon})
        faltan.append("datos_satelitales_pendientes")
    if p.get("pendiente_pct") is not None:
        pend, fuente_pend = p["pendiente_pct"], "usuario"
    elif sat and sat["pendiente_pct"] is not None:
        pend, fuente_pend = sat["pendiente_pct"], "nasa_appeears"
    else:
        pend, fuente_pend = c["rusle"]["pendiente_defecto_pct"], "supuesto"
        supuestos.append(f"pendiente_defecto_{pend}pct")
        faltan.append("pendiente_pct")
    suelo = extras.suelo(lat, lon)
    if suelo:
        K = F.rusle_K(suelo["arena"], suelo["limo"], suelo["arcilla"], suelo["oc_pct"])
    else:
        K = c["rusle"]["K_defecto"]
        supuestos.append(f"K_defecto_{K}")
        faltan.append("suelo_soilgrids_no_respondio")
    LS = F.rusle_LS(pend)
    ndvi = sat["ndvi_por_anio"] if sat and sat["evidencia"] == "B" else {}
    C_dec = c["rusle"]["C_por_cobertura"].get(p.get("cobertura_actual"), c["rusle"]["C_defecto"])
    if len(ndvi) < n:
        supuestos.append(f"C_cobertura_{C_dec}")
    R_med = mean(F.rusle_R(f["lluvia_anual"]) for f in feats if f["lluvia_anual"])
    eros = [F.erosion(F.rusle_R(f["lluvia_anual"]) if f["lluvia_anual"] else R_med, K, LS,
                      F.rusle_C(ndvi[f["anio"]]) if f["anio"] in ndvi else C_dec) for f in feats]

    # --- riesgos normalizados 0-1 por año ---
    if len(ndvi) >= 5:
        mu_v, sd_v = mean(ndvi.values()), pstdev(ndvi.values()) or 1
        verdor = [min(1, max(0, 0.5 + (mu_v - ndvi[a]) / sd_v / 4)) if a in ndvi else 0.5 for a in anios]
    else:
        verdor = [0.5] * n
        supuestos.append("verdor_neutral_sin_satelite")
    an = p.get("analisis_suelo") or {}
    if an.get("nitrogeno_pct") is not None:
        n_g_kg, ev_n, fu_n = an["nitrogeno_pct"] * 10, "B", "usuario"
    else:
        n_g_kg, ev_n, fu_n = (suelo["n_g_kg"], "C", "soilgrids") if suelo else (None, "C", "supuesto")
        faltan.append("analisis_suelo")
    rn = 0.5 if n_g_kg is None else min(1, max(0, 1 - n_g_kg / c["nitrogeno"]["N_ref_g_kg"]))
    R = {"canicula": [min(1, f["racha_canicula"] / (2 * c["canicula"]["umbral_dias"])) for f in feats],
         "calor": [min(1, f["dias_calor"] / (2 * c["calor"]["umbral_dias"])) for f in feats],
         "humedad": [f["frac_estres"] for f in feats],
         "erosion": [min(1, e / c["rusle"]["erosion_ref"]) for e in eros],
         "verdor": verdor,
         "nitrogeno": [rn] * n}

    # --- modelos 1 a 4 ---
    ev = eventos(feats, c)
    riesgos = [{"evento": k, **M.prob(v, c["modelo"]["z80"]), "fuente": "nasa_power", "evidencia": "A"} for k, v in ev.items()]
    val = _validacion()
    actual = next((f for f in feats if f["anio"] == hoy.year), None)
    ajuste = None
    if (val.get("ajuste_temporada_activo") and fs.year == hoy.year and actual
            and date(hoy.year, *c["canicula"]["ventana"][0]) <= hoy <= date(hoy.year, *c["canicula"]["ventana"][1])):
        sel = M.analogos([f for f in feats if f["anio"] != hoy.year], actual, c)
        ajuste = ({"canicula_larga": M.prob([f["racha_canicula"] > c["canicula"]["umbral_dias"] for f in sel]), "n_analogos": len(sel)}
                  if sel else {"aviso": "menos de 8 años análogos; se usa la probabilidad sin ajuste"})
    fase_por_anio = {a: M.fase_enso(v, c["modelo"]["enso_umbral_oni"]) for a, v in oni["jja"].items()} if oni else {}
    enso = M.efecto_enso(dict(zip(anios, ev["canicula_larga"])), fase_por_anio)

    # --- modelo 5: índice por rotación ---
    w = M.pesos(p.get("prioridades") or [], c, bool(an))
    S_base = M.puntajes(R, {}, w)
    u = M.umbral(S_base)
    sel = [i for i, a in enumerate(anios) if not fase or fase_por_anio.get(a) == fase]
    if len(sel) < 5:  # muy pocos años en esa fase: no se filtra
        sel, fase = list(range(n)), None
    rotaciones = []
    for rid, rot in c["rotaciones"].items():
        S = M.puntajes(R, rot["efectos"], w)
        idx, rg = M.indice([S[i] for i in sel], u, c["modelo"]["bootstrap"], c["modelo"]["semilla"])
        bal = sum(c["nitrogeno"]["fijacion_kg_ha"][k] - c["nitrogeno"]["extraccion_kg_ha"][k] for k in rot["cultivos"])
        um = c["nitrogeno"]["umbral_direccion_kg_ha"]
        rotaciones.append({"id": rid, "indice": idx, "rango_80": rg, "es_base": bool(rot.get("base")),
                           "nitrogeno": "sube" if bal > um else "baja" if bal < -um else "se mantiene"})
    idx_base = next(r["indice"] for r in rotaciones if r["es_base"])
    ap = M.aportes({v: [R[v][i] for i in sel] for v in R}, w, u, idx_base)
    meta = {"canicula": ("A", "nasa_power", n), "calor": ("A", "nasa_power", n), "humedad": ("B", "nasa_power", n),
            "erosion": ("B" if ndvi and fuente_pend != "supuesto" else "C", "nasa_appeears" if ndvi else "nasa_power", n),
            "verdor": (sat["evidencia"] if sat else "C", "nasa_appeears" if sat else "supuesto", len(ndvi)),
            "nitrogeno": (ev_n, fu_n, 1)}
    contrib = sorted(({"variable": v, "aporte_al_indice": ap[v], "evidencia": meta[v][0], "fuente": meta[v][1],
                       "n_anios": meta[v][2]} for v in w), key=lambda x: x["aporte_al_indice"])
    g = grafo()
    cadenas = [g["cadenas"][x["variable"]] for x in contrib[:3] if x["aporte_al_indice"] < 0 and x["variable"] in g["cadenas"]]
    ult = [e for f, e in zip(feats, eros) if f["lluvia_anual"]][-10:]
    # el ranking solo usa variables con datos: un riesgo neutral supuesto no ordena parcelas
    con_datos = {v: w[v] for v in w if meta[v][1] != "supuesto"}
    wd = {v: x / sum(con_datos.values()) for v, x in con_datos.items()}
    riesgo_medio = {v: mean(R[v]) for v in wd}
    return {
        "parcela_id": p["parcela_id"], "area_mz": p.get("area_mz"), "lat": lat, "lon": lon, "epoca": epoca,
        "definicion_exito": DEFINICION_EXITO, "rotaciones": rotaciones, "contribuciones": contrib, "cadenas": cadenas,
        "riesgos": riesgos, "ajuste_temporada": ajuste, "lluvia_ciclo_gamma": M.prob_lluvia_baja([f["lluvia_ciclo"] for f in feats]),
        "enso": enso, "fase_enso_filtrada": fase, "n_anios_indice": len(sel),
        "tendencia_erosion": M.tendencia(ult) if len(ult) >= 4 else None,
        "prioridad_parcela": round(M.prioridad(riesgo_medio, wd), 3),
        "variables_que_mas_pesan": [v for v, _ in sorted(((v, wd[v] * riesgo_medio[v]) for v in wd), key=lambda x: -x[1])[:2]],
        "perfil_terreno": {
            "clima": {"fuente": "nasa_power", "celda": serie["celda"], "anios": f"{anios[0]}-{anios[-1]}",
                      "lluvia_anual_media_mm": round(mean(f["lluvia_anual"] for f in feats if f["lluvia_anual"])),
                      "inicio_lluvias_mediano": (date(2001, 1, 1) + timedelta(round(median(
                          f["inicio_lluvias"].timetuple().tm_yday for f in feats if f["inicio_lluvias"])) - 1)).strftime("%d/%m"),
                      "vpd_floracion_kpa": round(mean(f["vpd_floracion"] for f in feats), 2)},
            "pendiente_pct": pend, "pendiente_fuente": fuente_pend, "erosion_indice_medio": round(mean(eros), 1),
            "humedad_suelo_anomalia_sd": sat.get("humedad_anomalia_sd") if sat else None,
            "verdor": {"ndvi_medio": round(mean(ndvi.values()), 2) if ndvi else None,
                       "tendencia_10_anios": sat.get("tendencia_verdor") if sat else None,
                       "suelo_desnudo_dias": sat["suelo_desnudo_dias"] if sat else None},
            "suelo": suelo, "satelite_frac_validas": sat["frac_validas"] if sat else None,
        },
        "datos_faltantes": faltan, "supuestos_usados": supuestos,
        "_feats": feats, "_puntajes_base": dict(zip(anios, S_base)),  # internos: validación y calibración
    }


def analizar_finca(finca, hoy=None, con_agente=True):
    _env()
    c, hoy = cfg(), hoy or date.today()
    validar(finca, c, hoy)
    oni = extras.oni()
    fase = finca.get("fase_enso")
    if fase and not oni:
        fase = None
    cal = _calibracion()
    parcelas = [analizar_parcela(p, c, hoy, oni, fase) for p in finca["parcelas"]]
    avisos = []
    for x in parcelas:
        x.pop("_feats"), x.pop("_puntajes_base")
        # cada época tiene su propia calibración; si no la hay, se usa la global
        ce = (cal.get("por_epoca", {}).get(x["epoca"]) or cal) if cal else None
        auc = ce["auc"] if ce else None
        ok, nivel = M.publicable(auc, c)
        x |= {"indice_publicable": ok, "nivel_confianza": nivel, "auc_calibracion": auc,
              "auc_ic80": ce.get("ic80") if ce else None}
        if not cal:
            aviso = "El índice de éxito no está calibrado contra los rendimientos del MAG; solo se muestran riesgos por variable."
        elif nivel == "confianza_baja":
            aviso = (f"Confianza baja en {x['epoca']}: el índice distingue los años buenos de los malos solo en parte "
                     f"(AUC {auc}, rango {ce['ic80'][0]}–{ce['ic80'][1]}, contra rendimientos del MAG). "
                     "Úselo para comparar rotaciones, no como promesa.")
        elif not ok:
            aviso = (f"En {x['epoca']} el índice no pasó la calibración contra el MAG (AUC {auc}); "
                     "solo se muestran riesgos por variable.")
        else:
            aviso = None
        if aviso and aviso not in avisos:
            avisos.append(aviso)
        if not ok:  # sin calibración no se publica el número
            for r in x["rotaciones"]:
                r["indice"] = r["rango_80"] = None
            for k in x["contribuciones"]:
                k.pop("aporte_al_indice")
    ranking = [{"posicion": i + 1, "parcela_id": x["parcela_id"], "prioridad": x["prioridad_parcela"],
                "por_que": x["variables_que_mas_pesan"]}
               for i, x in enumerate(sorted(parcelas, key=lambda x: -x["prioridad_parcela"]))]
    if not oni:
        avisos.append("No se pudo leer el índice ONI de NOAA; sin análisis de El Niño.")
    out = {"finca_id": finca.get("finca_id"), "parcelas": parcelas, "ranking": ranking, "avisos": avisos,
           "enso_actual": oni["ultimo"] | {"fase": M.fase_enso(oni["ultimo"]["oni"])} if oni else None,
           "pronostico_7d": extras.pronostico(parcelas[0]["lat"], parcelas[0]["lon"]),
           "explicacion": None, "avisos_agente": []}
    key = os.environ.get("GEMINI_API_KEY")
    if con_agente and key:
        payload = {"parcelas": parcelas, "ranking": ranking, "grafo": grafo()["aristas"]}
        try:
            out["explicacion"] = gemini.explicar(payload, key)
            out["avisos_agente"] = gemini.verificar(out["explicacion"], payload)
        except Exception as e:
            out["avisos_agente"] = [f"El agente no respondió: {e}"]
    elif con_agente:
        out["avisos_agente"] = ["Sin GEMINI_API_KEY en .env: no hay explicación en texto."]
    return out


# --- servidor web ---
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

app = FastAPI(title="Riesgo agrícola Corredor Seco")


@app.post("/api/finca")
def api_finca(finca: dict):
    try:
        return analizar_finca(finca)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, {"aviso": str(e)})


@app.get("/")
def inicio():
    return FileResponse(RAIZ / "frontend" / "index.html")
