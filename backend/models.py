"""Modelos 1 a 5: frecuencia con Wilson, análogos, gamma, ENSO, índice de éxito, tendencia y calibración."""
import math
import random
from statistics import mean

# t de Student, cuantil 0.90, gl 1..30 (para bandas del 80%)
T90 = [3.078, 1.886, 1.638, 1.533, 1.476, 1.440, 1.415, 1.397, 1.383, 1.372, 1.363, 1.356, 1.350, 1.345, 1.341,
       1.337, 1.333, 1.330, 1.328, 1.325, 1.323, 1.321, 1.319, 1.318, 1.316, 1.315, 1.314, 1.313, 1.311, 1.310]


def t90(gl):
    return T90[gl - 1] if gl <= 30 else 1.2816


def wilson(k, n, z=1.2816):
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - medio), min(1.0, centro + medio)


def prob(eventos, z=1.2816):
    """Modelo 1: k/n con intervalo de Wilson al 80%."""
    k, n = sum(eventos), len(eventos)
    lo, hi = wilson(k, n, z)
    return {"p": round(k / n, 3), "ic80": [round(lo, 3), round(hi, 3)], "k": k, "n": n}


def analogos(hist, actual, c):
    """Modelo 2: años parecidos al actual hasta hoy. None si quedan menos del mínimo."""
    m = c["modelo"]
    sel = [h for h in hist
           if h["inicio_lluvias"] and actual["inicio_lluvias"]
           and abs(h["inicio_lluvias"].timetuple().tm_yday - actual["inicio_lluvias"].timetuple().tm_yday) < m["analogos_inicio_dias"]
           and abs(h["lluvia_hasta_corte"] - actual["lluvia_hasta_corte"]) <= m["analogos_lluvia_frac"] * actual["lluvia_hasta_corte"]]
    return sel if len(sel) >= m["min_analogos"] else None


# --- Modelo 3: gamma (estimador de Thom) ---

def gamma_ajuste(x):
    x = [v for v in x if v > 0]
    a = math.log(mean(x)) - mean(math.log(v) for v in x)
    forma = (1 + math.sqrt(1 + 4 * a / 3)) / (4 * a)
    return forma, mean(x) / forma


def gamma_cdf(x, forma, escala):
    """Gamma incompleta regularizada P(a, x) (Numerical Recipes)."""
    a, x = forma, x / escala
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


def percentil(x, q):
    s = sorted(x)
    return s[min(len(s) - 1, int(q * len(s)))]


def prob_lluvia_baja(lluvias):
    forma, escala = gamma_ajuste(lluvias)
    return {f"p_bajo_p{int(q * 100)}": round(gamma_cdf(percentil(lluvias, q), forma, escala), 3)
            for q in (0.25, 0.10)} | {"n": len(lluvias)}


# --- Modelo 4: ENSO ---

def fase_enso(oni, umbral=0.5):
    return "nino" if oni >= umbral else "nina" if oni <= -umbral else "neutral"


def efecto_enso(eventos_por_anio, fase_por_anio):
    nino = [e for a, e in eventos_por_anio.items() if fase_por_anio.get(a) == "nino"]
    otros = [e for a, e in eventos_por_anio.items() if a in fase_por_anio and fase_por_anio[a] != "nino"]
    if not nino or not otros:
        return None
    return {"nino": prob(nino), "otros": prob(otros), "nota": "muestra pequeña; conclusión débil"}


# --- Pesos, prioridad y modelo 5 ---

VARIABLES = ["canicula", "calor", "humedad", "erosion", "verdor", "nitrogeno"]


def pesos(prioridades, c, con_analisis=False):
    w = {v: 1.0 for v in VARIABLES}
    for p in prioridades:
        for v in c["variables_por_prioridad"].get(p, []):
            w[v] *= c["modelo"]["peso_prioridad"]
    if not con_analisis:
        w["nitrogeno"] *= c["modelo"]["peso_nitrogeno_sin_analisis"]
    t = sum(w.values())
    return {v: x / t for v, x in w.items()}


def prioridad(riesgo_medio, w):
    return sum(w[v] * riesgo_medio[v] for v in w)


def puntajes(R, E, w):
    """S_a = sum_i w_i (1 - R_ia · E_i) para cada año a."""
    n = len(next(iter(R.values())))
    return [sum(w[v] * (1 - R[v][a] * E.get(v, 1.0)) for v in w) for a in range(n)]


def umbral(S_base):
    """u tal que el 75% de los años de la rotación base quedan en o sobre u."""
    return percentil(S_base, 0.25)


def indice(S, u, B=1000, semilla=42):
    """Índice = % de años con S >= u; rango = 10-90% del bootstrap de años."""
    rnd = random.Random(semilla)
    n = len(S)
    ok = [s >= u for s in S]
    boot = sorted(100 * sum(rnd.choices(ok, k=n)) / n for _ in range(B))
    return round(100 * sum(ok) / n), [round(boot[int(0.1 * B)]), round(boot[int(0.9 * B) - 1])]


def aportes(R, w, u, idx_base):
    """Cuánto baja el índice base cada variable: contrafactual con su mejor año observado."""
    n = len(R[next(iter(R))])
    out = {}
    for v in w:
        cf = dict(R, **{v: [min(R[v])] * n})
        out[v] = idx_base - round(100 * sum(s >= u for s in puntajes(cf, {}, w)) / n)
    return out


# --- Tendencia de erosión ---

def tendencia(y, horizonte=5):
    n = len(y)
    x = list(range(n))
    xm, ym = mean(x), mean(y)
    sxx = sum((xi - xm) ** 2 for xi in x)
    b = sum((xi - xm) * (yi - ym) for xi, yi in zip(x, y)) / sxx
    a = ym - b * xm
    s = math.sqrt(sum((yi - a - b * xi) ** 2 for xi, yi in zip(x, y)) / (n - 2))
    t = t90(n - 2)
    x0 = n - 1 + horizonte
    yhat = a + b * x0
    se = s * math.sqrt(1 + 1 / n + (x0 - xm) ** 2 / sxx)
    signif = s == 0 or abs(b) / (s / math.sqrt(sxx)) > t
    direccion = "sin tendencia clara" if not signif or b == 0 else "sube" if b > 0 else "baja"
    return {"anios": horizonte, "direccion": direccion,
            "banda_80": [round((yhat - t * se) / ym, 2), round((yhat + t * se) / ym, 2)],
            "nota": "extrapolación de tendencia relativa a la media de los últimos años, no pronóstico físico"}


# --- Validación y calibración ---

def brier(p, o):
    return mean((pi - oi) ** 2 for pi, oi in zip(p, o))


def auc(scores, labels):
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def auc_ic80(scores, labels, B=1000, semilla=42):
    rnd = random.Random(semilla)
    pares = list(zip(scores, labels))
    vals = []
    for _ in range(B):
        m = rnd.choices(pares, k=len(pares))
        if 0 < sum(l for _, l in m) < len(m):
            vals.append(auc(*zip(*m)))
    vals.sort()
    return [round(vals[int(0.1 * len(vals))], 3), round(vals[int(0.9 * len(vals)) - 1], 3)]


def tabla_calibracion(scores, labels, grupos=4):
    orden = sorted(zip(scores, labels))
    t = len(orden) // grupos
    filas = []
    for g in range(grupos):
        parte = orden[g * t:(g + 1) * t if g < grupos - 1 else None]
        filas.append({"puntaje_medio": round(mean(s for s, _ in parte), 3),
                      "exito_observado": round(mean(l for _, l in parte), 3), "n": len(parte)})
    return filas


def publicable(auc_valor, c):
    m = c["modelo"]
    if auc_valor is None or auc_valor < m["auc_minimo"]:
        return False, "no_publicable"
    return True, "normal" if auc_valor >= m["auc_publicable"] else "confianza_baja"
