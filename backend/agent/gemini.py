"""Explainer agent with Gemini (REST, no SDK) and a checker for its rules."""
import json
import os
import re
import urllib.request
from pathlib import Path

from backend.i18n import lang_of, t

PROMPTS = {lang: (Path(__file__).parent / f"prompt_{lang}.md").read_text(encoding="utf-8") for lang in ("es", "en")}


def explain(payload, api_key, model=None, lang="es"):
    model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    body = {"system_instruction": {"parts": [{"text": PROMPTS[lang_of(lang)]}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.2}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]


def _numbers(o, acc):
    if isinstance(o, bool):
        return acc
    if isinstance(o, (int, float)):
        acc |= {round(o, 2), round(o), round(o * 100)} if 0 <= o <= 1 else {round(o, 2), round(o)}
    elif isinstance(o, dict):
        for v in o.values():
            _numbers(v, acc)
    elif isinstance(o, list):
        for v in o:
            _numbers(v, acc)
    elif isinstance(o, str):
        acc |= {float(n) for n in re.findall(r"\d+(?:\.\d+)?", o)}
    return acc


def verify(text, payload, lang="es"):
    """List of rules the agent's answer breaks (empty = complies). Works for Spanish and English answers."""
    fails = []
    if len(text.split()) >= 200:
        fails.append(t(lang, "too_long", n=len(text.split())))
    if re.search(r"quintal|bushel", text, re.I):
        fails.append(t(lang, "quintals"))
    if text.count("?") < 3:
        fails.append(t(lang, "missing_questions"))
    if (any(p.get("index_publishable") is False for p in payload.get("plots", []))
            and re.search(r"(?:[íi]ndice|index)[^.?!]{0,40}\d", text, re.I)):
        fails.append(t(lang, "unpublished_index"))
    allowed = _numbers(payload, {1.0, 2.0, 3.0})
    for n in re.findall(r"\d+(?:[.,]\d+)?", text):
        if float(n.replace(",", ".")) not in allowed:
            fails.append(t(lang, "number_not_in_json", n=n))
    return fails
