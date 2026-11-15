"""Agroclimatic and erosion features. Formulas and sources in docs/DECISIONS.md."""
import math
from datetime import date, timedelta
from statistics import mean


def e_s(t):
    """Saturation vapour pressure in kPa (T in °C)."""
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def vpd(t, rh):
    return e_s(t) * (1 - rh / 100)


def longest_dry_run(rains, threshold=1.0):
    mx = cur = 0
    for mm in rains:
        cur = cur + 1 if mm < threshold else 0
        mx = max(mx, cur)
    return mx


def date_range(d0, d1):
    return [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]


def rain_onset(rain, year, c):
    """First day from 1 May with >=20 mm in 3 days and no 7-day dry spell in the following 21."""
    ro = c["rain_onset"]
    for d in date_range(date(year, *ro["from"]), date(year, *ro["to"])):
        if sum(rain.get(d + timedelta(i), 0) for i in range(3)) >= ro["mm_3_days"]:
            following = [rain.get(d + timedelta(3 + i), 0) for i in range(ro["window_days"])]
            if longest_dry_run(following, c["dry_day_mm"]) < ro["dry_spell_days"]:
                return d
    return None


def ra_mm(lat, doy):
    """Extraterrestrial radiation (FAO-56 eq. 21) in equivalent mm/day."""
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    dl = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(-math.tan(phi) * math.tan(dl))
    ra = 24 * 60 / math.pi * 0.082 * dr * (ws * math.sin(phi) * math.sin(dl) + math.cos(phi) * math.cos(dl) * math.sin(ws))
    return 0.408 * ra


def et0_hargreaves(tmax, tmin, lat, doy):
    return 0.0023 * ((tmax + tmin) / 2 + 17.8) * math.sqrt(max(tmax - tmin, 0)) * ra_mm(lat, doy)


def by_date(series):
    return {date.fromisoformat(r["date"]): r for r in series["daily"]}


def year_features(days, year, planting_md, crop, season, lat, c):
    """Features for one year and a planting date (month, day). None if the cycle lacks complete data."""
    planting = date(year, *planting_md)
    cr = c["crops"][crop]
    harvest = planting + timedelta(cr["cycle_days"] - 1)
    if planting not in days or harvest not in days:
        return None
    rain = {d: r["rain_mm"] for d, r in days.items() if d.year == year}
    cycle = date_range(planting, harvest)
    if season == "primera":
        w0, w1 = c["dry_spell"]["window"]
        window, sensitive = date_range(date(year, *w0), date(year, *w1)), cycle
    else:
        # in postrera the canícula has already passed and the end of the cycle falls in the expected dry season:
        # the dry spell and stress are measured from planting to the end of flowering (the sensitive stage)
        window = sensitive = date_range(planting, planting + timedelta(cr["flowering"][1]))
    flowering = date_range(planting + timedelta(cr["flowering"][0]), planting + timedelta(cr["flowering"][1]))
    bl = c["water_stress"]["block_days"]
    blocks = [sensitive[i:i + bl] for i in range(0, len(sensitive) - bl + 1, bl)]
    stress = [sum(days[d]["rain_mm"] for d in b) /
              sum(et0_hargreaves(days[d]["t_max_c"], days[d]["t_min_c"], lat, d.timetuple().tm_yday) for d in b)
              for b in blocks]
    year_end = date(year, 12, 31)
    return {
        "year": year,
        "rain_onset": rain_onset(rain, year, c),
        "dry_spell_days": longest_dry_run([days[d]["rain_mm"] for d in window if d in days], c["dry_day_mm"]),
        "cycle_rain_mm": sum(days[d]["rain_mm"] for d in cycle),
        "rain_to_cutoff_mm": sum(days[d]["rain_mm"] for d in date_range(date(year, 5, 1), date(year, *c["dry_spell"]["window"][0]))),
        "heat_days": sum(days[d]["t_max_c"] > c["heat"]["t_max_c"] for d in flowering),
        "flowering_vpd_kpa": mean(vpd((days[d]["t_max_c"] + days[d]["t_min_c"]) / 2, days[d]["rh_pct"]) for d in flowering),
        "stress_fraction": sum(x < c["water_stress"]["risk_ratio"] for x in stress) / len(stress),
        "annual_rain_mm": sum(rain.values()) if year_end in days else None,
    }


# --- RUSLE as a relative index: A = R·K·LS·C·P ---

def rusle_R(p_annual):
    """Annual erosivity (MJ·mm/ha/h/yr) from annual rainfall. Renard and Freimund (1994)."""
    return 0.0483 * p_annual ** 1.61 if p_annual < 850 else 587.8 - 1.219 * p_annual + 0.004105 * p_annual ** 2


def rusle_K(sand, silt, clay, oc):
    """Erodibility (t·ha·h/ha/MJ/mm) from texture (%) and organic carbon (%). Williams (1995), EPIC."""
    sn1 = 1 - sand / 100
    f = ((0.2 + 0.3 * math.exp(-0.0256 * sand * (1 - silt / 100)))
         * (silt / (clay + silt)) ** 0.3
         * (1 - 0.25 * oc / (oc + math.exp(3.72 - 2.95 * oc)))
         * (1 - 0.7 * sn1 / (sn1 + math.exp(-5.51 + 22.9 * sn1))))
    return 0.1317 * f


def rusle_LS(slope_pct):
    """Slope factor from McCool et al. (1987) with a 22.13 m length (L = 1, assumption)."""
    s = math.sin(math.atan(slope_pct / 100))
    return 10.8 * s + 0.03 if slope_pct < 9 else 16.8 * s - 0.5


def rusle_C(ndvi):
    """Cover from NDVI. Van der Knijff et al. (2000): C = exp(-2·NDVI/(1-NDVI))."""
    return math.exp(-2 * ndvi / (1 - ndvi)) if ndvi < 1 else 0.0


def erosion(R, K, LS, C, P=1.0):
    return R * K * LS * C * P
