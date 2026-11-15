"""Las 12 capas del plan de pruebas. Correr: python -m unittest -v tests.test_mvp

Capas 5, 6 y 8 usan POWER real (o su caché en data/cache); la 7 necesita GEMINI_API_KEY.
"""
import copy
import csv
import json
import os
import re
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from backend import RAIZ, api, cfg, grafo
from backend import features as F
from backend import models as M
from backend import satelite
from backend.agent import gemini
from backend.clients import power

FIX = Path(__file__).parent / "fixtures"
C = cfg()
PARCELA = {"parcela_id": "p1", "geometria": {"type": "Polygon", "coordinates": [[[-88.19, 13.47], [-88.17, 13.47], [-88.17, 13.49], [-88.19, 13.49], [-88.19, 13.47]]]},
           "area_mz": 2, "cultivo_actual": "maiz", "cultivo_planeado": "maiz", "fecha_siembra": "2026-05-25",
           "prioridades": ["agua", "erosion"], "cobertura_actual": "suelo_desnudo"}
FINCA = {"finca_id": "f1", "parcelas": [PARCELA, dict(PARCELA, parcela_id="p2", geometria={"type": "Point", "coordinates": [-88.94, 14.04]},
                                                      cultivo_planeado="frijol", fecha_siembra="2026-08-25", epoca="postrera", prioridades=["nitrogeno"])]}


def serie_sintetica(anios=35, sequias=(), racha=14):
    """Lluvia 8 mm/día de mayo a octubre; en los años de `sequias`, una racha seca desde el 20 de julio."""
    diario = []
    for a in range(1991, 1991 + anios):
        d = date(a, 1, 1)
        while d.year == a:
            lluvia = 8.0 if 5 <= d.month <= 10 else 0.0
            if a in sequias and date(a, 7, 20) <= d < date(a, 7, 20) + timedelta(racha):
                lluvia = 0.0
            diario.append({"fecha": d.isoformat(), "lluvia_mm": lluvia, "t_max_c": 32.0, "t_min_c": 22.0, "hr_pct": 75.0})
            d += timedelta(1)
    return {"diario": diario}


class Capa1Unitarias(unittest.TestCase):
    def test_vpd(self):
        self.assertAlmostEqual(F.vpd(30, 50), 2.12, places=2)

    def test_wilson(self):
        lo, hi = M.wilson(13, 35, 1.28)
        self.assertTrue(lo < 13 / 35 < hi)
        self.assertAlmostEqual(lo, 0.275, places=2)  # la spec redondea a 0.28-0.47; el cálculo exacto da 0.275-0.480
        self.assertAlmostEqual(hi, 0.480, places=2)

    def test_racha_seca(self):
        self.assertEqual(F.racha_seca([5, 0, 0, 0.5, 3, 0, 0]), 3)

    def test_inicio_lluvias(self):
        lluvia = {date(2020, 5, 1) + timedelta(i): 0.0 for i in range(120)}
        for i in range(20, 120):
            lluvia[date(2020, 5, 1) + timedelta(i)] = 8.0
        self.assertEqual(F.inicio_lluvias(lluvia, 2020, C), date(2020, 5, 21))

    def test_rusle(self):
        self.assertAlmostEqual(F.rusle_R(849.9), 587.8 - 1.219 * 850 + 0.004105 * 850 ** 2, delta=60)  # continuidad aproximada
        self.assertLess(F.rusle_LS(5), F.rusle_LS(20))
        self.assertGreater(F.rusle_C(0.2), F.rusle_C(0.8))
        self.assertTrue(0.01 < F.rusle_K(40, 40, 20, 1.5) < 0.07)

    def test_pesos_suman_1(self):
        for pr in ([], ["agua"], ["agua", "erosion", "nitrogeno", "mercado"]):
            self.assertAlmostEqual(sum(M.pesos(pr, C).values()), 1.0)


class Capa2Contrato(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((FIX / "power_muestra.json").read_text())

    def test_esquema(self):
        d = power.parsear(self.raw, 13.5, -88.125)
        self.assertEqual(d["fuente"], "nasa_power")
        self.assertEqual(set(d["diario"][0]), {"fecha", "lluvia_mm", "t_max_c", "t_min_c", "hr_pct"})
        self.assertEqual(len(d["diario"]), 10)

    def test_falta_campo(self):
        del self.raw["properties"]["parameter"]["RH2M"]
        with self.assertRaisesRegex(ValueError, "faltan parámetros"):
            power.parsear(self.raw, 13.5, -88.125)

    def test_valor_999(self):
        p = self.raw["properties"]["parameter"]["T2M_MAX"]
        p[next(iter(p))] = -999.0
        with self.assertRaisesRegex(ValueError, "dato faltante"):
            power.parsear(self.raw, 13.5, -88.125)

    def test_celda_no_coincide(self):
        with self.assertRaisesRegex(ValueError, "no coincide"):
            power.parsear(self.raw, 14.0, -88.125)


class Capa3Cache(unittest.TestCase):
    def test_una_sola_solicitud(self):
        raw = json.loads((FIX / "power_muestra.json").read_text())
        llamadas = []
        http = lambda lat, lon, fin: llamadas.append(1) or raw
        with tempfile.TemporaryDirectory() as d:
            antes = power.solicitudes
            a = power.obtener(13.48, -88.18, http=http, cache=Path(d))
            b = power.obtener(13.52, -88.10, http=http, cache=Path(d))  # misma celda
            self.assertEqual(a, b)
            self.assertEqual(len(llamadas), 1)
            self.assertEqual(power.solicitudes - antes, 1)


class Capa4Sintetica(unittest.TestCase):
    def test_racha_sembrada(self):
        normal, seca = F.por_fecha(serie_sintetica(5)), F.por_fecha(serie_sintetica(5, sequias=range(1991, 1996)))
        fn = F.features_anio(normal, 1993, (5, 25), "maiz", "primera", 13.5, C)
        fs = F.features_anio(seca, 1993, (5, 25), "maiz", "primera", 13.5, C)
        self.assertEqual(fs["racha_canicula"], 14)
        p_n = M.prob([F.features_anio(normal, a, (5, 25), "maiz", "primera", 13.5, C)["racha_canicula"] > 10 for a in range(1991, 1996)])
        p_s = M.prob([F.features_anio(seca, a, (5, 25), "maiz", "primera", 13.5, C)["racha_canicula"] > 10 for a in range(1991, 1996)])
        self.assertGreater(p_s["p"], p_n["p"])
        self.assertEqual(fn["racha_canicula"], 0)

    def test_postrera_no_cuenta_la_estacion_seca(self):
        # la serie sintética deja de llover el 1 de noviembre: en postrera la racha se mide solo hasta fin de floración
        f = F.features_anio(F.por_fecha(serie_sintetica(5)), 1993, (8, 25), "maiz", "postrera", 13.5, C)
        self.assertLess(f["racha_canicula"], C["canicula"]["umbral_dias"])


class Capa5y6Historica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.validar import loo
        cls.res = loo()

    def test_brier_reportado_y_comparado(self):
        for z, r in self.res["zonas"].items():
            for ev in ("canicula_larga", "inicio_tardio", "calor_floracion", "deficit_lluvia"):
                self.assertIn("brier_base", r[ev])
            self.assertIn("brier_ajuste_analogos", r["canicula_larga"])
        mejora = all(r["canicula_larga"]["brier_ajuste_analogos"] < r["canicula_larga"]["brier_base"] for r in self.res["zonas"].values())
        self.assertEqual(self.res["ajuste_temporada_activo"], mejora)

    def test_caso_2025(self):
        for z, r in self.res["zonas"].items():
            i = r["inicio_2025"]
            print(f"\n  2025 en {z}: día {i['dia_del_anio']} vs mediana {i['mediana_historica']} -> más tardío: {i['mas_tardio_que_mediana']}")
            self.assertIsInstance(i["mas_tardio_que_mediana"], bool)  # se reporta, no se fuerza


EJEMPLO = {"parcela_id": "p1", "indice_publicable": True, "auc_calibracion": 0.72,
           "definicion_exito": "rendimiento sobre el percentil 25 historico de la zona",
           "rotaciones": [{"id": "maiz_maiz", "indice": 75, "rango_80": [66, 83], "es_base": True},
                          {"id": "maiz_frijol", "indice": 81, "rango_80": [70, 89], "es_base": False},
                          {"id": "maiz_abono_verde", "indice": 84, "rango_80": [72, 91], "es_base": False}],
           "contribuciones": [{"variable": "canicula_larga", "aporte_al_indice": -9, "evidencia": "A", "fuente": "nasa_power", "n_anios": 35},
                              {"variable": "erosion", "aporte_al_indice": -6, "evidencia": "B", "fuente": "nasa_appeears", "n_anios": 10}],
           "cadenas": [["lluvia_baja", "humedad_suelo_baja", "estres_hidrico"]],
           "tendencia_erosion": {"anios": 5, "direccion": "sube", "banda_80": [1.1, 1.6]},
           "prioridad_parcela": 0.62, "datos_faltantes": ["analisis_suelo"], "supuestos_usados": ["umbral_canicula_10_dias"]}


class Capa7Agente(unittest.TestCase):
    def test_verificador_offline(self):
        bueno = "Maíz con frijol: 81, entre 70 y 89. ¿Ve grietas? ¿Hay rastrojo? ¿Llovió en mayo?"
        self.assertEqual(gemini.verificar(bueno, EJEMPLO), [])
        malo = "Le prometo 40 quintales y 97% de éxito."
        f = gemini.verificar(malo, EJEMPLO)
        self.assertTrue(any("quintales" in x for x in f) and any("97" in x for x in f) and any("preguntas" in x for x in f))

    @unittest.skipUnless(os.environ.get("GEMINI_API_KEY"), "sin GEMINI_API_KEY")
    def test_gemini_real(self):
        payload = {"parcelas": [EJEMPLO], "ranking": [{"posicion": 1, "parcela_id": "p1", "por_que": ["canicula", "erosion"]}],
                   "grafo": grafo()["aristas"]}
        texto = gemini.explicar(payload, os.environ["GEMINI_API_KEY"])
        print("\n" + texto)
        self.assertEqual(gemini.verificar(texto, payload), [])


class Capa8ExtremoAExtremo(unittest.TestCase):
    def test_endpoint(self):
        from fastapi.testclient import TestClient
        cli = TestClient(api.app)
        cli.post("/api/finca", json=FINCA)  # calienta la caché
        t = time.time()
        r = cli.post("/api/finca", json=FINCA)
        self.assertLess(time.time() - t, 30)
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertEqual(len(out["ranking"]), 2)
        self.assertIn("<html", cli.get("/").text.lower())
        fuera = copy.deepcopy(FINCA)
        fuera["parcelas"][0]["geometria"] = {"lat": 10.0, "lon": -85.0}
        self.assertEqual(cli.post("/api/finca", json=fuera).status_code, 422)

    def test_honestidad(self):
        out = api.analizar_finca(FINCA, con_agente=False)
        for p in out["parcelas"]:
            for r in p["riesgos"]:
                self.assertTrue(r["ic80"] and r["n"] > 0)
            self.assertIn("umbral_canicula_10_dias", p["supuestos_usados"])
            for k in p["contribuciones"]:
                self.assertIn(k["evidencia"], "ABC")


def escribir_csv(ruta, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "capa", "valor", "calidad_ok"])
        w.writerows(filas)


class Capa9Satelite(unittest.TestCase):
    def test_lector(self):
        filas = [["2020-01-01", "pendiente", 12.0, 1], ["2020-01-01", "pendiente", 18.0, 1]]
        for a in range(2014, 2025):
            for m in range(1, 13):
                filas.append([f"{a}-{m:02d}-15", "ndvi", 0.6 if 6 <= m <= 9 else 0.25, 1])
            filas.append([f"{a}-07-01", "ndvi", 0.99, 0])  # nube: se descarta
        with tempfile.TemporaryDirectory() as d:
            escribir_csv(Path(d) / "z.csv", filas)
            s = satelite.leer("z", (5, 25), 120, C, d=Path(d))
        self.assertEqual(s["pendiente_pct"], 15.0)
        self.assertAlmostEqual(s["ndvi_por_anio"][2020], 0.6)  # la nube de 0.99 no entra
        self.assertEqual(s["evidencia"], "B")
        self.assertGreater(s["suelo_desnudo_dias"][2020], 0)

    def test_pocas_validas_baja_a_C(self):
        filas = [[f"2020-{m:02d}-15", "ndvi", 0.5, 1 if m <= 2 else 0] for m in range(1, 13)]
        with tempfile.TemporaryDirectory() as d:
            escribir_csv(Path(d) / "z.csv", filas)
            s = satelite.leer("z", (5, 25), 120, C, d=Path(d))
        self.assertEqual(s["evidencia"], "C")


class Capa10Indice(unittest.TestCase):
    def test_sequia_rotacion_y_rango(self):
        import random
        rnd = random.Random(1)
        base = {v: [rnd.uniform(0.1, 0.4) for _ in range(35)] for v in M.VARIABLES}
        seca = copy.deepcopy(base)
        for a in range(0, 35, 4)[:8]:  # 8 años de sequía
            seca["canicula"][a] = seca["humedad"][a] = 1.0
        w = M.pesos(["agua"], C)
        u = M.umbral(M.puntajes(base, {}, w))
        i_n, _ = M.indice(M.puntajes(base, {}, w), u)
        i_s, rg = M.indice(M.puntajes(seca, {}, w), u)
        i_r, _ = M.indice(M.puntajes(seca, {"canicula": 0.5, "humedad": 0.5}, w), u)
        self.assertLess(i_s, i_n)
        self.assertTrue(rg[0] <= i_s <= rg[1])
        self.assertGreater(i_r, i_s)


class Capa11Calibracion(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(M.auc([1, 2, 3, 4], [0, 0, 1, 1]), 1.0)
        self.assertEqual(M.auc([1, 2, 3, 4], [1, 1, 0, 0]), 0.0)
        lo, hi = M.auc_ic80([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [0, 0, 1, 0, 1, 0, 1, 1, 1, 1])
        self.assertLessEqual(lo, hi)
        self.assertEqual(len(M.tabla_calibracion(list(range(20)), [i > 5 for i in range(20)])), 4)

    def test_cortes(self):
        self.assertEqual(M.publicable(0.75, C), (True, "normal"))
        self.assertEqual(M.publicable(0.65, C), (True, "confianza_baja"))
        self.assertEqual(M.publicable(0.55, C), (False, "no_publicable"))
        self.assertEqual(M.publicable(None, C), (False, "no_publicable"))

    def test_no_publicable_oculta_numero(self):
        with mock.patch.object(api, "_calibracion", return_value={"auc": 0.55, "ic80": [0.4, 0.7]}):
            out = api.analizar_finca(FINCA, con_agente=False)
        for p in out["parcelas"]:
            self.assertFalse(p["indice_publicable"])
            self.assertTrue(all(r["indice"] is None and r["rango_80"] is None for r in p["rotaciones"]))
            self.assertTrue(all("aporte_al_indice" not in k for k in p["contribuciones"]))
        # si el agente inventara el índice, el verificador lo detecta
        self.assertTrue(gemini.verificar("Su índice es 75. ¿a? ¿b? ¿c?", {"parcelas": out["parcelas"]}))

    def test_calibracion_por_epoca(self):
        cal = {"auc": 0.67, "ic80": [0.54, 0.79], "por_epoca": {"primera": {"auc": 0.9, "ic80": [0.8, 0.99]},
                                                              "postrera": {"auc": 0.33, "ic80": [0.12, 0.57]}}}
        with mock.patch.object(api, "_calibracion", return_value=cal):
            out = api.analizar_finca(FINCA, con_agente=False)
        p1, p2 = out["parcelas"]  # p1 primera, p2 postrera
        self.assertTrue(p1["indice_publicable"] and p1["nivel_confianza"] == "normal")
        self.assertIsNotNone(p1["rotaciones"][0]["indice"])
        self.assertFalse(p2["indice_publicable"])
        self.assertIsNone(p2["rotaciones"][0]["indice"])
        self.assertTrue(any("postrera" in a for a in out["avisos"]))

    def test_publicable_muestra_numero(self):
        with mock.patch.object(api, "_calibracion", return_value={"auc": 0.74, "ic80": [0.6, 0.85]}):
            out = api.analizar_finca(FINCA, con_agente=False)
        base = next(r for r in out["parcelas"][0]["rotaciones"] if r["es_base"])
        self.assertTrue(70 <= base["indice"] <= 80)  # ~75 por construcción
        self.assertTrue(base["rango_80"][0] <= base["indice"] <= base["rango_80"][1])


class Capa12Grafo(unittest.TestCase):
    def test_cadenas_en_grafo(self):
        g = grafo()
        aristas = {(a["causa"], a["efecto"]) for a in g["aristas"]}
        for cad in g["cadenas"].values():
            for par in zip(cad, cad[1:]):
                self.assertIn(par, aristas)
        with mock.patch.object(api, "_calibracion", return_value={"auc": 0.74, "ic80": [0.6, 0.85]}):
            out = api.analizar_finca(FINCA, con_agente=False)
        for p in out["parcelas"]:
            for cad in p["cadenas"]:
                for par in zip(cad, cad[1:]):
                    self.assertIn(par, aristas)

    def test_largo(self):
        self.assertTrue(any("palabras" in x for x in gemini.verificar("palabra " * 210, {})))


class SinLlaves(unittest.TestCase):
    def test_repo_sin_llaves(self):
        patron = re.compile(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|GEMINI_API_KEY[ \t]*=[ \t]*\S+")
        for f in RAIZ.rglob("*"):
            if f.is_file() and f.name != ".env" and not {"cache", ".git", "__pycache__"} & set(f.parts) and f.stat().st_size < 2_000_000:
                texto = f.read_text(encoding="utf-8", errors="ignore")
                hall = [m for m in patron.findall(texto) if "os.environ" not in m]
                self.assertEqual(hall, [], f"posible llave en {f}")


if __name__ == "__main__":
    unittest.main()
