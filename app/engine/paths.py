import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).parent / "data"
else:
    DATA_DIR = Path(__file__).parent.parent.parent / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
