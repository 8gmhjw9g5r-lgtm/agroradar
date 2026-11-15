"""The 12 layers of the test plan. Run: python -m unittest -v tests.test_mvp

Layers 5, 6 and 8 use real POWER data (or its cache in data/cache); layer 7 needs GEMINI_API_KEY.
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

from backend import ROOT, api, cfg, graph
from backend import features as F
from backend import models as M
from backend import satellite
from backend.agent import gemini
from backend.clients import power
from backend.i18n import MESSAGES

FIX = Path(__file__).parent / "fixtures"
C = cfg()
PLOT = {"plot_id": "p1", "geometry": {"type": "Polygon", "coordinates": [[[-88.19, 13.47], [-88.17, 13.47], [-88.17, 13.49], [-88.19, 13.49], [-88.19, 13.47]]]},
        "area_mz": 2, "current_crop": "maize", "planned_crop": "maize", "planting_date": "2026-05-25",
        "priorities": ["water", "erosion"], "current_cover": "bare_soil"}
FARM = {"farm_id": "f1", "plots": [PLOT, dict(PLOT, plot_id="p2", geometry={"type": "Point", "coordinates": [-88.94, 14.04]},
                                              planned_crop="bean", planting_date="2026-08-25", season="postrera", priorities=["nitrogen"])]}


def synthetic_series(years=35, droughts=(), spell=14):
    """Rain of 8 mm/day from May to October; in the years in `droughts`, a dry spell from 20 July."""
    daily = []
    for a in range(1991, 1991 + years):
        d = date(a, 1, 1)
        while d.year == a:
            rain = 8.0 if 5 <= d.month <= 10 else 0.0
            if a in droughts and date(a, 7, 20) <= d < date(a, 7, 20) + timedelta(spell):
                rain = 0.0
            daily.append({"date": d.isoformat(), "rain_mm": rain, "t_max_c": 32.0, "t_min_c": 22.0, "rh_pct": 75.0})
            d += timedelta(1)
    return {"daily": daily}


class Layer1Unit(unittest.TestCase):
    def test_vpd(self):
        self.assertAlmostEqual(F.vpd(30, 50), 2.12, places=2)

    def test_wilson(self):
        lo, hi = M.wilson(13, 35, 1.28)
        self.assertTrue(lo < 13 / 35 < hi)
        self.assertAlmostEqual(lo, 0.275, places=2)  # the spec rounds to 0.28-0.47; the exact calculation gives 0.275-0.480
        self.assertAlmostEqual(hi, 0.480, places=2)

    def test_dry_run(self):
        self.assertEqual(F.longest_dry_run([5, 0, 0, 0.5, 3, 0, 0]), 3)

    def test_rain_onset(self):
        rain = {date(2020, 5, 1) + timedelta(i): 0.0 for i in range(120)}
        for i in range(20, 120):
            rain[date(2020, 5, 1) + timedelta(i)] = 8.0
        self.assertEqual(F.rain_onset(rain, 2020, C), date(2020, 5, 21))

    def test_rusle(self):
        self.assertAlmostEqual(F.rusle_R(849.9), 587.8 - 1.219 * 850 + 0.004105 * 850 ** 2, delta=60)  # approximate continuity
        self.assertLess(F.rusle_LS(5), F.rusle_LS(20))
        self.assertGreater(F.rusle_C(0.2), F.rusle_C(0.8))
        self.assertTrue(0.01 < F.rusle_K(40, 40, 20, 1.5) < 0.07)

    def test_weights_sum_to_1(self):
        for pr in ([], ["water"], ["water", "erosion", "nitrogen", "market"]):
            self.assertAlmostEqual(sum(M.weights(pr, C).values()), 1.0)


class Layer2Contract(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((FIX / "power_sample.json").read_text())

    def test_schema(self):
        d = power.parse(self.raw, 13.5, -88.125)
        self.assertEqual(d["source"], "nasa_power")
        self.assertEqual(set(d["daily"][0]), {"date", "rain_mm", "t_max_c", "t_min_c", "rh_pct"})
        self.assertEqual(len(d["daily"]), 10)

    def test_missing_field(self):
        del self.raw["properties"]["parameter"]["RH2M"]
        with self.assertRaisesRegex(ValueError, "missing parameters"):
            power.parse(self.raw, 13.5, -88.125)

    def test_value_999(self):
        p = self.raw["properties"]["parameter"]["T2M_MAX"]
        p[next(iter(p))] = -999.0
        with self.assertRaisesRegex(ValueError, "missing value"):
            power.parse(self.raw, 13.5, -88.125)

    def test_cell_mismatch(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            power.parse(self.raw, 14.0, -88.125)


class Layer3Cache(unittest.TestCase):
    def test_single_request(self):
        raw = json.loads((FIX / "power_sample.json").read_text())
        calls = []
        http = lambda lat, lon, end: calls.append(1) or raw
        with tempfile.TemporaryDirectory() as d:
            before = power.requests_made
            a = power.fetch(13.48, -88.18, http=http, cache=Path(d))
            b = power.fetch(13.52, -88.10, http=http, cache=Path(d))  # same cell
            self.assertEqual(a, b)
            self.assertEqual(len(calls), 1)
            self.assertEqual(power.requests_made - before, 1)


class Layer4Synthetic(unittest.TestCase):
    def test_planted_dry_spell(self):
        normal, dry = F.by_date(synthetic_series(5)), F.by_date(synthetic_series(5, droughts=range(1991, 1996)))
        fn = F.year_features(normal, 1993, (5, 25), "maize", "primera", 13.5, C)
        fd = F.year_features(dry, 1993, (5, 25), "maize", "primera", 13.5, C)
        self.assertEqual(fd["dry_spell_days"], 14)
        p_n = M.prob([F.year_features(normal, a, (5, 25), "maize", "primera", 13.5, C)["dry_spell_days"] > 10 for a in range(1991, 1996)])
        p_d = M.prob([F.year_features(dry, a, (5, 25), "maize", "primera", 13.5, C)["dry_spell_days"] > 10 for a in range(1991, 1996)])
        self.assertGreater(p_d["p"], p_n["p"])
        self.assertEqual(fn["dry_spell_days"], 0)

    def test_postrera_ignores_dry_season(self):
        # the synthetic series stops raining on 1 November: in postrera the spell is measured only to the end of flowering
        f = F.year_features(F.by_date(synthetic_series(5)), 1993, (8, 25), "maize", "postrera", 13.5, C)
        self.assertLess(f["dry_spell_days"], C["dry_spell"]["threshold_days"])


class Layer5and6Historical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.validate import loo
        cls.res = loo()

    def test_brier_reported_and_compared(self):
        for z, r in self.res["zones"].items():
            for ev in ("long_dry_spell", "late_onset", "flowering_heat", "rain_deficit"):
                self.assertIn("brier_base", r[ev])
            self.assertIn("brier_analog_adjustment", r["long_dry_spell"])
        better = all(r["long_dry_spell"]["brier_analog_adjustment"] < r["long_dry_spell"]["brier_base"] for r in self.res["zones"].values())
        self.assertEqual(self.res["season_adjustment_active"], better)

    def test_case_2025(self):
        for z, r in self.res["zones"].items():
            i = r["onset_2025"]
            print(f"\n  2025 in {z}: day {i['day_of_year']} vs median {i['historical_median']} -> later: {i['later_than_median']}")
            self.assertIsInstance(i["later_than_median"], bool)  # reported, not forced


EXAMPLE = {"plot_id": "p1", "index_publishable": True, "calibration_auc": 0.72,
           "success_definition": "yield above the zone's historical 25th percentile",
           "rotations": [{"id": "maize_maize", "index": 75, "range_80": [66, 83], "is_base": True},
                         {"id": "maize_bean", "index": 81, "range_80": [70, 89], "is_base": False},
                         {"id": "maize_green_manure", "index": 84, "range_80": [72, 91], "is_base": False}],
           "contributions": [{"variable": "dry_spell", "index_contribution": -9, "evidence": "A", "source": "nasa_power", "n_years": 35},
                             {"variable": "erosion", "index_contribution": -6, "evidence": "B", "source": "nasa_appeears", "n_years": 10}],
           "chains": [["low_rain", "low_soil_moisture", "water_stress"]],
           "erosion_trend": {"years": 5, "direction": "up", "band_80": [1.1, 1.6]},
           "plot_priority": 0.62, "missing_data": ["soil_analysis"], "assumptions_used": ["dry_spell_threshold_10_days"]}


class Layer7Agent(unittest.TestCase):
    def test_offline_checker(self):
        good = "Maíz con frijol: 81, entre 70 y 89. ¿Ve grietas? ¿Hay rastrojo? ¿Llovió en mayo?"
        self.assertEqual(gemini.verify(good, EXAMPLE), [])
        bad = "Le prometo 40 quintales y 97% de éxito."
        f = gemini.verify(bad, EXAMPLE)
        self.assertTrue(any("quintales" in x for x in f) and any("97" in x for x in f) and any("preguntas" in x for x in f))

    def test_offline_checker_english(self):
        good = "Maize with beans: 81, between 70 and 89. Cracks? Stubble? Rain in May?"
        self.assertEqual(gemini.verify(good, EXAMPLE, "en"), [])
        f = gemini.verify("I promise 40 bushels and 97% success.", EXAMPLE, "en")
        self.assertTrue(any("quintals" in x for x in f) and any("97" in x for x in f) and any("questions" in x for x in f))

    def test_both_prompts_exist(self):
        self.assertIn("usted conoce su tierra", gemini.PROMPTS["es"])
        self.assertIn("you know your land", gemini.PROMPTS["en"])

    @unittest.skipUnless(os.environ.get("GEMINI_API_KEY"), "no GEMINI_API_KEY")
    def test_real_gemini(self):
        payload = {"plots": [EXAMPLE], "ranking": [{"position": 1, "plot_id": "p1", "why": ["dry_spell", "erosion"]}],
                   "graph": graph()["edges"]}
        for lang in ("es", "en"):
            text = gemini.explain(payload, os.environ["GEMINI_API_KEY"], lang=lang)
            print("\n" + text)
            self.assertEqual(gemini.verify(text, payload, lang), [])


class Layer8EndToEnd(unittest.TestCase):
    def test_endpoint(self):
        from fastapi.testclient import TestClient
        cli = TestClient(api.app)
        cli.post("/api/farm", json=FARM)  # warms the cache
        t = time.time()
        r = cli.post("/api/farm", json=FARM)
        self.assertLess(time.time() - t, 30)
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertEqual(len(out["ranking"]), 2)
        self.assertIn("<html", cli.get("/").text.lower())
        outside = copy.deepcopy(FARM)
        outside["plots"][0]["geometry"] = {"lat": 10.0, "lon": -85.0}
        self.assertEqual(cli.post("/api/farm", json=outside).status_code, 422)

    def test_honesty(self):
        out = api.analyze_farm(FARM, with_agent=False)
        for p in out["plots"]:
            for r in p["risks"]:
                self.assertTrue(r["ci80"] and r["n"] > 0)
            self.assertIn("dry_spell_threshold_10_days", p["assumptions_used"])
            for k in p["contributions"]:
                self.assertIn(k["evidence"], "ABC")

    def test_language(self):
        es = api.analyze_farm(FARM, with_agent=False)
        en = api.analyze_farm(dict(FARM, lang="en"), with_agent=False)
        self.assertEqual((es["lang"], en["lang"]), ("es", "en"))  # Spanish is the default
        self.assertEqual(en["plots"][0]["success_definition"], MESSAGES["en"]["success_definition"])
        self.assertTrue(any("postrera" in w and "calibration" in w for w in en["warnings"]))
        # only texts change with the language, never the numbers
        strip = lambda o: [{k: v for k, v in p.items() if k != "success_definition"} for p in o["plots"]]
        self.assertEqual(strip(es), strip(en))


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "layer", "value", "quality_ok"])
        w.writerows(rows)


class Layer9Satellite(unittest.TestCase):
    def test_reader(self):
        rows = [["2020-01-01", "slope", 12.0, 1], ["2020-01-01", "slope", 18.0, 1]]
        for a in range(2014, 2025):
            for m in range(1, 13):
                rows.append([f"{a}-{m:02d}-15", "ndvi", 0.6 if 6 <= m <= 9 else 0.25, 1])
            rows.append([f"{a}-07-01", "ndvi", 0.99, 0])  # cloud: dropped
        with tempfile.TemporaryDirectory() as d:
            write_csv(Path(d) / "z.csv", rows)
            s = satellite.read("z", (5, 25), 120, C, d=Path(d))
        self.assertEqual(s["slope_pct"], 15.0)
        self.assertAlmostEqual(s["ndvi_by_year"][2020], 0.6)  # the 0.99 cloud is not counted
        self.assertEqual(s["evidence"], "B")
        self.assertGreater(s["bare_soil_days"][2020], 0)

    def test_few_valid_drops_to_C(self):
        rows = [[f"2020-{m:02d}-15", "ndvi", 0.5, 1 if m <= 2 else 0] for m in range(1, 13)]
        with tempfile.TemporaryDirectory() as d:
            write_csv(Path(d) / "z.csv", rows)
            s = satellite.read("z", (5, 25), 120, C, d=Path(d))
        self.assertEqual(s["evidence"], "C")


class Layer10Index(unittest.TestCase):
    def test_drought_rotation_and_range(self):
        import random
        rnd = random.Random(1)
        base = {v: [rnd.uniform(0.1, 0.4) for _ in range(35)] for v in M.VARIABLES}
        dry = copy.deepcopy(base)
        for a in range(0, 35, 4)[:8]:  # 8 drought years
            dry["dry_spell"][a] = dry["moisture"][a] = 1.0
        w = M.weights(["water"], C)
        u = M.threshold(M.scores(base, {}, w))
        i_n, _ = M.index(M.scores(base, {}, w), u)
        i_d, rg = M.index(M.scores(dry, {}, w), u)
        i_r, _ = M.index(M.scores(dry, {"dry_spell": 0.5, "moisture": 0.5}, w), u)
        self.assertLess(i_d, i_n)
        self.assertTrue(rg[0] <= i_d <= rg[1])
        self.assertGreater(i_r, i_d)


class Layer11Calibration(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(M.auc([1, 2, 3, 4], [0, 0, 1, 1]), 1.0)
        self.assertEqual(M.auc([1, 2, 3, 4], [1, 1, 0, 0]), 0.0)
        lo, hi = M.auc_ci80([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [0, 0, 1, 0, 1, 0, 1, 1, 1, 1])
        self.assertLessEqual(lo, hi)
        self.assertEqual(len(M.calibration_table(list(range(20)), [i > 5 for i in range(20)])), 4)

    def test_cutoffs(self):
        self.assertEqual(M.publishable(0.75, C), (True, "normal"))
        self.assertEqual(M.publishable(0.65, C), (True, "low_confidence"))
        self.assertEqual(M.publishable(0.55, C), (False, "not_publishable"))
        self.assertEqual(M.publishable(None, C), (False, "not_publishable"))

    def test_unpublishable_hides_number(self):
        with mock.patch.object(api, "_calibration", return_value={"auc": 0.55, "ci80": [0.4, 0.7]}):
            out = api.analyze_farm(FARM, with_agent=False)
        for p in out["plots"]:
            self.assertFalse(p["index_publishable"])
            self.assertTrue(all(r["index"] is None and r["range_80"] is None for r in p["rotations"]))
            self.assertTrue(all("index_contribution" not in k for k in p["contributions"]))
        # if the agent invented the index, the checker catches it, in either language
        self.assertTrue(gemini.verify("Su índice es 75. ¿a? ¿b? ¿c?", {"plots": out["plots"]}))
        self.assertTrue(gemini.verify("Your index is 75. a? b? c?", {"plots": out["plots"]}, "en"))

    def test_calibration_by_season(self):
        cal = {"auc": 0.67, "ci80": [0.54, 0.79], "by_season": {"primera": {"auc": 0.9, "ci80": [0.8, 0.99]},
                                                               "postrera": {"auc": 0.33, "ci80": [0.12, 0.57]}}}
        with mock.patch.object(api, "_calibration", return_value=cal):
            out = api.analyze_farm(FARM, with_agent=False)
        p1, p2 = out["plots"]  # p1 primera, p2 postrera
        self.assertTrue(p1["index_publishable"] and p1["confidence_level"] == "normal")
        self.assertIsNotNone(p1["rotations"][0]["index"])
        self.assertFalse(p2["index_publishable"])
        self.assertIsNone(p2["rotations"][0]["index"])
        self.assertTrue(any("postrera" in a for a in out["warnings"]))

    def test_publishable_shows_number(self):
        with mock.patch.object(api, "_calibration", return_value={"auc": 0.74, "ci80": [0.6, 0.85]}):
            out = api.analyze_farm(FARM, with_agent=False)
        base = next(r for r in out["plots"][0]["rotations"] if r["is_base"])
        self.assertTrue(70 <= base["index"] <= 80)  # ~75 by construction
        self.assertTrue(base["range_80"][0] <= base["index"] <= base["range_80"][1])


class Layer12Graph(unittest.TestCase):
    def test_chains_in_graph(self):
        g = graph()
        edges = {(a["cause"], a["effect"]) for a in g["edges"]}
        for ch in g["chains"].values():
            for pair in zip(ch, ch[1:]):
                self.assertIn(pair, edges)
        self.assertTrue(set(g["chains"]) <= set(M.VARIABLES))
        with mock.patch.object(api, "_calibration", return_value={"auc": 0.74, "ci80": [0.6, 0.85]}):
            out = api.analyze_farm(FARM, with_agent=False)
        for p in out["plots"]:
            for ch in p["chains"]:
                for pair in zip(ch, ch[1:]):
                    self.assertIn(pair, edges)

    def test_length(self):
        self.assertTrue(any("palabras" in x for x in gemini.verify("palabra " * 210, {})))
        self.assertTrue(any("words" in x for x in gemini.verify("word " * 210, {}, "en")))


class SatelliteViews(unittest.TestCase):
    def test_rules(self):
        from backend.views import choose_views
        farm = lambda pr, cover=None: {"plots": [{"priorities": pr, "current_cover": cover}]}
        water = choose_views(farm(["water"]), [{"top_variables": ["dry_spell", "heat"]}])
        self.assertEqual(water[0], {"view": "soil_moisture", "reasons": ["top_water", "priority_water"]})
        self.assertEqual(water[1]["view"], "ground_heat")  # a top risk beats a ticked priority

        heat = choose_views(farm([]), [{"top_variables": ["heat"]}])
        self.assertEqual(heat[0]["view"], "ground_heat")
        erosion = choose_views(farm(["erosion"], "bare_soil"), [{"top_variables": []}])
        self.assertEqual(erosion[0]["view"], "satellite_photo")
        self.assertEqual(choose_views(farm([]), [{"top_variables": []}])[0]["reasons"], ["default"])

    def test_in_api(self):
        out = api.analyze_farm(FARM, with_agent=False)
        self.assertTrue(1 <= len(out["satellite_views"]) <= 2)
        from backend.views import VIEWS
        self.assertTrue(all(v["view"] in VIEWS and v["reasons"] for v in out["satellite_views"]))


class NoKeys(unittest.TestCase):
    def test_repo_has_no_keys(self):
        pattern = re.compile(r"AIza[0-9A-Za-z_\-]{35}|sk-[A-Za-z0-9]{20,}|GEMINI_API_KEY[ \t]*=[ \t]*\S+")
        for f in ROOT.rglob("*"):
            if (f.is_file() and f.name != ".env" and not {"cache", ".git", "__pycache__", ".venv"} & set(f.parts)
                    and f.stat().st_size < 2_000_000):
                text = f.read_text(encoding="utf-8", errors="ignore")
                found = [m for m in pattern.findall(text) if "os.environ" not in m]
                self.assertEqual(found, [], f"possible key in {f}")


if __name__ == "__main__":
    unittest.main()
