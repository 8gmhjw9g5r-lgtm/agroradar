"""Agente explicador con Gemini (REST, sin SDK) y verificador de sus reglas."""
import json
import os
import re
import urllib.request
from pathlib import Path

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def explicar(payload, api_key, modelo=None):
    modelo = modelo or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    cuerpo = {"system_instruction": {"parts": [{"text": PROMPT}]},
              "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
              "generationConfig": {"temperature": 0.2}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
        data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]


def _numeros(o, acc):
    if isinstance(o, bool):
        return acc
    if isinstance(o, (int, float)):
        acc |= {round(o, 2), round(o), round(o * 100)} if 0 <= o <= 1 else {round(o, 2), round(o)}
    elif isinstance(o, dict):
        for v in o.values():
            _numeros(v, acc)
    elif isinstance(o, list):
        for v in o:
            _numeros(v, acc)
    elif isinstance(o, str):
        acc |= {float(n) for n in re.findall(r"\d+(?:\.\d+)?", o)}
    return acc


def verificar(texto, payload):
    """Lista de reglas incumplidas por la respuesta del agente (vacía = cumple)."""
    fallas = []
    if len(texto.split()) >= 200:
        fallas.append(f"respuesta de {len(texto.split())} palabras (máximo 199)")
    if re.search(r"quintal", texto, re.I):
        fallas.append("menciona quintales")
    if texto.count("?") < 3:
        fallas.append("faltan las 3 preguntas de campo")
    if any(p.get("indice_publicable") is False for p in payload.get("parcelas", [])) and re.search(r"[íi]ndice[^.?!]{0,40}\d", texto, re.I):
        fallas.append("menciona un índice no publicable")
    permitidos = _numeros(payload, {1.0, 2.0, 3.0})
    for n in re.findall(r"\d+(?:[.,]\d+)?", texto):
        if float(n.replace(",", ".")) not in permitidos:
            fallas.append(f"cifra {n} no está en el JSON")
    return fallas
