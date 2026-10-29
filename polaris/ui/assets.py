import sys
from pathlib import Path


def path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name if (base / "assets" / name).exists() else Path(__file__).resolve().parent.parent / "assets" / name
