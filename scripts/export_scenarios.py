"""Copy the backend's scenario JSON to the web folder (single source of truth)."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = root / "backend/src/echo_move/data/scenarios.json"
dst = root / "web/data/scenarios.json"
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dst)
print(f"{src} -> {dst}")
