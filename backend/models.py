"""Models 1 to 5: frequency with Wilson, analog years, gamma, ENSO, success index, trend and calibration."""
import math
import random
from statistics import mean

# Student's t, 0.90 quantile, df 1..30 (for 80% bands)
T90 = [3.078, 1.886, 1.638, 1.533, 1.476, 1.440, 1.415, 1.397, 1.383, 1.372, 1.363, 1.356, 1.350, 1.345, 1.341,
       1.337, 1.333, 1.330, 1.328, 1.325, 1.323, 1.321, 1.319, 1.318, 1.316, 1.315, 1.314, 1.313, 1.311, 1.310]


def t90(df):
    return T90[df - 1] if df <= 30 else 1.2816


def wilson(k, n, z=1.2816):
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def prob(events, z=1.2816):
    """Model 1: k/n with an 80% Wilson interval."""
    k, n = sum(events), len(events)
    lo, hi = wilson(k, n, z)
    return {"p": round(k / n, 3), "ci80": [round(lo, 3), round(hi, 3)], "k": k, "n": n}


def analogs(hist, current, c):
    """Model 2: years similar to the current one up to today. None if fewer than the minimum remain."""
    m = c["model"]
    sel = [h for h in hist
           if h["rain_onset"] and current["rain_onset"]
           and abs(h["rain_onset"].timetuple().tm_yday - current["rain_onset"].timetuple().tm_yday) < m["analog_onset_days"]
           and abs(h["rain_to_cutoff_mm"] - current["rain_to_cutoff_mm"]) <= m["analog_rain_frac"] * current["rain_to_cutoff_mm"]]
    return sel if len(sel) >= m["min_analogs"] else None


# --- Model 3: gamma (Thom's estimator) ---

def gamma_fit(x):
    x = [v for v in x if v > 0]
    a = math.log(mean(x)) - mean(math.log(v) for v in x)
    shape = (1 + math.sqrt(1 + 4 * a / 3)) / (4 * a)
    return shape, mean(x) / shape


def gamma_cdf(x, shape, scale):
    """Regularized incomplete gamma P(a, x) (Numerical Recipes)."""
    a, x = shape, x / scale
    if x <= 0:
        return 0.0
    if x < a + 1:
        s = term = 1 / a
        for n in range(1, 500):
            term *= x / (a + n)
            s += term
            if abs(term) < abs(s) * 1e-12:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    tiny = 1e-300
    b, c = x + 1 - a, 1 / tiny
    d = h = 1 / b
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return 1 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def percentile(x, q):
    s = sorted(x)
    return s[min(len(s) - 1, int(q * len(s)))]


def prob_low_rain(rains):
    shape, scale = gamma_fit(rains)
    return {f"p_below_p{int(q * 100)}": round(gamma_cdf(percentile(rains, q), shape, scale), 3)
            for q in (0.25, 0.10)} | {"n": len(rains)}


# --- Model 4: ENSO ---

def enso_phase(oni, threshold=0.5):
    return "el_nino" if oni >= threshold else "la_nina" if oni <= -threshold else "neutral"


def enso_effect(events_by_year, phase_by_year):
    nino = [e for a, e in events_by_year.items() if phase_by_year.get(a) == "el_nino"]
    others = [e for a, e in events_by_year.items() if a in phase_by_year and phase_by_year[a] != "el_nino"]
    if not nino or not others:
        return None
    return {"el_nino": prob(nino), "others": prob(others), "note": "small_sample_weak_conclusion"}


# --- Weights, priority and model 5 ---

VARIABLES = ["dry_spell", "heat", "moisture", "erosion", "greenness", "nitrogen"]


def weights(priorities, c, with_analysis=False):
    w = {v: 1.0 for v in VARIABLES}
    for p in priorities:
        for v in c["variables_by_priority"].get(p, []):
            w[v] *= c["model"]["priority_weight"]
    if not with_analysis:
        w["nitrogen"] *= c["model"]["nitrogen_weight_without_analysis"]
    t = sum(w.values())
    return {v: x / t for v, x in w.items()}


def priority(mean_risk, w):
    return sum(w[v] * mean_risk[v] for v in w)


def scores(R, E, w):
    """S_a = sum_i w_i (1 - R_ia · E_i) for each year a."""
    n = len(next(iter(R.values())))
    return [sum(w[v] * (1 - R[v][a] * E.get(v, 1.0)) for v in w) for a in range(n)]


def threshold(S_base):
    """u such that 75% of the base rotation's years are at or above u."""
    return percentile(S_base, 0.25)


def index(S, u, B=1000, seed=42):
    """Index = % of years with S >= u; range = 10-90% of the year bootstrap."""
    rnd = random.Random(seed)
    n = len(S)
    ok = [s >= u for s in S]
    boot = sorted(100 * sum(rnd.choices(ok, k=n)) / n for _ in range(B))
    return round(100 * sum(ok) / n), [round(boot[int(0.1 * B)]), round(boot[int(0.9 * B) - 1])]


def contributions(R, w, u, base_index):
    """How much each variable lowers the base index: counterfactual with its best observed year."""
    n = len(R[next(iter(R))])
    out = {}
    for v in w:
        cf = dict(R, **{v: [min(R[v])] * n})
        out[v] = base_index - round(100 * sum(s >= u for s in scores(cf, {}, w)) / n)
    return out


# --- Erosion trend ---

def trend(y, horizon=5):
    n = len(y)
    x = list(range(n))
    xm, ym = mean(x), mean(y)
    sxx = sum((xi - xm) ** 2 for xi in x)
    b = sum((xi - xm) * (yi - ym) for xi, yi in zip(x, y)) / sxx
    a = ym - b * xm
    s = math.sqrt(sum((yi - a - b * xi) ** 2 for xi, yi in zip(x, y)) / (n - 2))
    t = t90(n - 2)
    x0 = n - 1 + horizon
    yhat = a + b * x0
    se = s * math.sqrt(1 + 1 / n + (x0 - xm) ** 2 / sxx)
    signif = s == 0 or abs(b) / (s / math.sqrt(sxx)) > t
    direction = "no_clear_trend" if not signif or b == 0 else "up" if b > 0 else "down"
    return {"years": horizon, "direction": direction,
            "band_80": [round((yhat - t * se) / ym, 2), round((yhat + t * se) / ym, 2)],
            "note": "relative_trend_extrapolation_not_physical_forecast"}


# --- Validation and calibration ---

def brier(p, o):
    return mean((pi - oi) ** 2 for pi, oi in zip(p, o))


def auc(scores_, labels):
    pos = [s for s, l in zip(scores_, labels) if l]
    neg = [s for s, l in zip(scores_, labels) if not l]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def auc_ci80(scores_, labels, B=1000, seed=42):
    rnd = random.Random(seed)
    pairs = list(zip(scores_, labels))
    vals = []
    for _ in range(B):
        m = rnd.choices(pairs, k=len(pairs))
        if 0 < sum(l for _, l in m) < len(m):
            vals.append(auc(*zip(*m)))
    vals.sort()
    return [round(vals[int(0.1 * len(vals))], 3), round(vals[int(0.9 * len(vals)) - 1], 3)]


def calibration_table(scores_, labels, groups=4):
    order = sorted(zip(scores_, labels))
    t = len(order) // groups
    rows = []
    for g in range(groups):
        part = order[g * t:(g + 1) * t if g < groups - 1 else None]
        rows.append({"mean_score": round(mean(s for s, _ in part), 3),
                     "observed_success": round(mean(l for _, l in part), 3), "n": len(part)})
    return rows


def publishable(auc_value, c):
    m = c["model"]
    if auc_value is None or auc_value < m["auc_minimum"]:
        return False, "not_publishable"
    return True, "normal" if auc_value >= m["auc_publishable"] else "low_confidence"
