"""Data locations and environment checks (shared by the CLI, the web UI and the Docker healthcheck)."""
import os
import shutil
from pathlib import Path

DATA_DIR = Path(os.environ.get("AUTOCLIPPER_DATA_DIR") or Path(__file__).resolve().parent.parent).resolve()
WORK = DATA_DIR / "work"
OUT = DATA_DIR / "output"
CACHE = DATA_DIR / "cache"


def missing_binaries() -> list[str]:
    return [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
