"""User-facing messages in Spanish (default, for farmers) and English.

Codes and field names in the API are always English; only these texts change with `lang`.
"""
LANGS = ("es", "en")
DEFAULT = "es"

MESSAGES = {
    "es": {
        "no_plots": "La finca no trae parcelas.",
        "too_many_plots": "Máximo {max} parcelas por finca en el MVP.",
        "outside_pilot": "La parcela {plot_id} está fuera de la zona piloto de El Salvador; no se calcula.",
        "planting_date_range": "La fecha de siembra de {plot_id} debe estar dentro de 12 meses alrededor de hoy.",
        "bad_crop": "planned_crop de {plot_id} debe ser maize, bean o green_manure.",
        "success_definition": "rendimiento sobre el percentil 25 histórico de la zona",
        "few_analogs": "menos de {n} años análogos; se usa la probabilidad sin ajuste",
        "not_calibrated": "El índice de éxito no está calibrado contra los rendimientos del MAG; solo se muestran riesgos por variable.",
        "low_confidence": ("Confianza baja en {season}: el índice distingue los años buenos de los malos solo en parte "
                           "(AUC {auc}, rango {lo}–{hi}, contra rendimientos del MAG). Úselo para comparar rotaciones, no como promesa."),
        "not_published": "En {season} el índice no pasó la calibración contra el MAG (AUC {auc}); solo se muestran riesgos por variable.",
        "no_oni": "No se pudo leer el índice ONI de NOAA; sin análisis de El Niño.",
        "agent_failed": "El agente no respondió: {error}",
        "no_gemini_key": "Sin GEMINI_API_KEY en .env: no hay explicación en texto.",
        "too_long": "respuesta de {n} palabras (máximo 199)",
        "quintals": "menciona quintales",
        "missing_questions": "faltan las 3 preguntas de campo",
        "unpublished_index": "menciona un índice no publicable",
        "number_not_in_json": "cifra {n} no está en el JSON",
    },
    "en": {
        "no_plots": "The farm has no plots.",
        "too_many_plots": "At most {max} plots per farm in the MVP.",
        "outside_pilot": "Plot {plot_id} is outside the El Salvador pilot area; it is not computed.",
        "planting_date_range": "The planting date of {plot_id} must be within 12 months of today.",
        "bad_crop": "planned_crop of {plot_id} must be maize, bean or green_manure.",
        "success_definition": "yield above the zone's historical 25th percentile",
        "few_analogs": "fewer than {n} analog years; the unadjusted probability is used",
        "not_calibrated": "The success index is not calibrated against MAG yields; only per-variable risks are shown.",
        "low_confidence": ("Low confidence in {season}: the index only partly separates good years from bad ones "
                           "(AUC {auc}, range {lo}–{hi}, against MAG yields). Use it to compare rotations, not as a promise."),
        "not_published": "In {season} the index did not pass calibration against MAG (AUC {auc}); only per-variable risks are shown.",
        "no_oni": "Could not read the NOAA ONI index; no El Niño analysis.",
        "agent_failed": "The agent did not respond: {error}",
        "no_gemini_key": "No GEMINI_API_KEY in .env: no text explanation.",
        "too_long": "answer has {n} words (maximum 199)",
        "quintals": "mentions quintals",
        "missing_questions": "the 3 field questions are missing",
        "unpublished_index": "mentions an unpublished index",
        "number_not_in_json": "number {n} is not in the JSON",
    },
}


def lang_of(x):
    return x if x in LANGS else DEFAULT


def t(lang, key, **kw):
    return MESSAGES[lang_of(lang)][key].format(**kw)
