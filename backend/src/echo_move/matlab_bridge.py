"""Reads the newest ``*_iqa.json`` written by the MATLAB engine (mtime-cached)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class MatlabBridge:
    def __init__(self, directory: Path):
        self.directory = directory
        self._mtime = 0.0
        self._data: dict[str, Any] | None = None

    def read(self) -> dict[str, Any] | None:
        try:
            if not self.directory.is_dir():
                return None
            files = list(self.directory.glob("*_iqa.json"))
            if not files:
                return None
            path = max(files, key=lambda p: p.stat().st_mtime)
            mtime = path.stat().st_mtime
            if mtime != self._mtime:
                raw = json.loads(path.read_text(encoding="utf-8"))
                data = raw.get("summary", raw)
                data["_source_file"] = path.name
                self._data, self._mtime = data, mtime
            if self._data is not None:
                self._data["_age_seconds"] = round(time.time() - mtime, 1)
            return self._data
        except (OSError, json.JSONDecodeError):
            # MATLAB may be mid-write; keep serving the last good value.
            log.debug("MATLAB JSON unreadable, using cache", exc_info=True)
            return self._data
