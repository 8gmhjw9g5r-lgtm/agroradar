from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def cfg():
    return yaml.safe_load((ROOT / "config" / "thresholds.yaml").read_text(encoding="utf-8"))


def graph():
    return yaml.safe_load((ROOT / "config" / "graph.yaml").read_text(encoding="utf-8"))
