"""Validación histórica (dejar un año fuera) y calibración del índice contra el MAG.

    python -m backend.validar        -> data/validacion.json
    python -m backend.validar mag    -> data/calibracion.json (necesita data/mag_rendimientos.csv)
"""
import csv
import json
import sys
from datetime import date
from statistics import median

from backend import DATA, cfg
from backend import models as M
from backend.api import analizar_parcela, eventos


def parcela_tipo(nombre, z, epoca="primera"):
    md = "08-25" if epoca == "postrera" else "05-25"
    return {"parcela_id": nombre, "geometria": {"lat": z["lat"], "lon": z["lon"]}, "cultivo_planeado": "maiz",
            "fecha_siembra": f"{date.today().year}-{md}", "epoca": epoca, "prioridades": []}


def loo(hoy=None):
    c, hoy = cfg(), hoy or date.today()
    out, mejora = {"zonas": {}}, []
    for nombre, z in c["satelite"]["zonas_piloto"].items():
        feats = [f for f in analizar_parcela(parcela_tipo(nombre, z), c, hoy, None, None)["_feats"] if f["anio"] <= 2025]
        ev = eventos(feats, c)
        res = {}
        for k, o in ev.items():
            n = len(o)
            base = [(sum(o) - o[i]) / (n - 1) for i in range(n)]
            res[k] = {"brier_base": round(M.brier(base, o), 4), "n": n}
        # modelo 2 (análogos al 15 de julio) contra la frecuencia sin ajuste, para la canícula
        o = ev["canicula_larga"]
        aj = []
        for i, f in enumerate(feats):
            sel = M.analogos(feats[:i] + feats[i + 1:], f, c)
            aj.append(sum(s["racha_canicula"] > c["canicula"]["umbral_dias"] for s in sel) / len(sel) if sel else
                      (sum(o) - o[i]) / (len(o) - 1))
        res["canicula_larga"]["brier_ajuste_analogos"] = round(M.brier(aj, o), 4)
        mejora.append(res["canicula_larga"]["brier_ajuste_analogos"] < res["canicula_larga"]["brier_base"])
        doys = {f["anio"]: f["inicio_lluvias"].timetuple().tm_yday if f["inicio_lluvias"] else None for f in feats}
        med = median(d for d in doys.values() if d)
        res["inicio_2025"] = {"dia_del_anio": doys.get(2025), "mediana_historica": med,
                              "mas_tardio_que_mediana": doys.get(2025) is None or doys[2025] > med}
        out["zonas"][nombre] = res
    out["ajuste_temporada_activo"] = all(mejora)
    if not out["ajuste_temporada_activo"]:
        out["aviso"] = "El ajuste por años análogos no supera a la frecuencia histórica; queda desactivado."
    (DATA / "validacion.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def calibrar_mag(archivo=DATA / "mag_rendimientos.csv", hoy=None):
    """CSV: departamento,anio,rendimiento. Éxito = rendimiento sobre el percentil 25 del departamento."""
    c, hoy = cfg(), hoy or date.today()
    with open(archivo, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    scores, labels, por_serie, por_epoca = [], [], {}, {}
    for nombre, z in c["satelite"]["zonas_piloto"].items():
        for cal in z["calibracion"]:
            rend = {int(f["anio"]): float(f["rendimiento"]) for f in filas
                    if f["departamento"] == z["departamento"] and f.get("epoca", "total") == cal["serie"]}
            if len(rend) < 8:
                continue
            p25 = M.percentil(list(rend.values()), 0.25)
            S = analizar_parcela(parcela_tipo(nombre, z, cal["epoca"]), c, hoy, None, None)["_puntajes_base"]
            s_d, l_d = [S[a] for a in rend if a in S], [rend[a] > p25 for a in rend if a in S]
            scores += s_d
            labels += l_d
            e = por_epoca.setdefault(cal["epoca"], ([], []))
            e[0].extend(s_d)
            e[1].extend(l_d)
            por_serie[f"{z['departamento']} / {cal['serie']}"] = {"auc": round(M.auc(s_d, l_d), 3), "n": len(s_d),
                                                                  "fracasos": l_d.count(False)}
    if len(scores) < 10 or len(set(labels)) < 2:
        raise SystemExit("Datos del MAG insuficientes para calibrar (mínimo 10 años con éxitos y fracasos).")
    auc = M.auc(scores, labels)
    out = {"auc": round(auc, 3), "ic80": M.auc_ic80(scores, labels), "n": len(scores), "por_serie": por_serie,
           "auc_medio_por_serie": round(sum(v["auc"] for v in por_serie.values()) / len(por_serie), 3),
           # el índice se publica por época: primera y postrera usan ventanas distintas y se calibran aparte
           "por_epoca": {ep: {"auc": round(M.auc(s, l), 3), "ic80": M.auc_ic80(s, l), "n": len(s),
                              "nivel": M.publicable(M.auc(s, l), c)[1]} for ep, (s, l) in por_epoca.items()},
           "tabla": M.tabla_calibracion(scores, labels), "nivel": M.publicable(auc, c)[1],
           "fuente": "MAG, Anuarios de Estadísticas Agropecuarias 2001-02 a 2022-23 (sin 2007-08 y 2008-09); rendimiento de maíz por departamento, total o por época (2013-2022)"}
    (DATA / "calibracion.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(json.dumps(calibrar_mag() if sys.argv[1:] == ["mag"] else loo(), indent=1, ensure_ascii=False))
