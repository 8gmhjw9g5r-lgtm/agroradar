from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"


def cfg():
    return yaml.safe_load((RAIZ / "config" / "umbrales.yaml").read_text(encoding="utf-8"))


def grafo():
    return yaml.safe_load((RAIZ / "config" / "grafo.yaml").read_text(encoding="utf-8"))
