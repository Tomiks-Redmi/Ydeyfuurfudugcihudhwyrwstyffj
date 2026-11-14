"""Writes every console line to ~/.droidforge/logs/<timestamp>.log (handy after a failed flash)."""
from __future__ import annotations

import time
from pathlib import Path

from .config import APP_DIR

LOG_DIR = APP_DIR / "logs"
KEEP = 30


class SessionLog:
    def __init__(self):
        self.path: Path | None = None
        self._fh = None
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            for old in sorted(LOG_DIR.glob("*.log"))[:-KEEP + 1]:
                old.unlink(missing_ok=True)
            self.path = LOG_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}.log"
            self._fh = open(self.path, "a", encoding="utf-8", buffering=1)
        except OSError:
            self._fh = None

    def write(self, text: str, kind: str = "out") -> None:
        if self._fh:
            try:
                self._fh.write(f"{time.strftime('%H:%M:%S')} [{kind:>4}] {text}\n")
            except OSError:
                pass

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
