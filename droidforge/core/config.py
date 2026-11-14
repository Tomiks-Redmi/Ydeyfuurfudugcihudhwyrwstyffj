"""Persistent JSON configuration stored in ~/.droidforge/config.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_DIR = Path.home() / ".droidforge"
CONFIG_FILE = APP_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "adb_path": "",
    "fastboot_path": "",
    "poll_interval": 2000,
    "stop_on_error": True,
    "custom_commands": [],   # [{"title": str, "command": str}]
    "history": [],           # console history
    "last_dirs": {},         # remembered folders for file dialogs
}


class Config:
    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            tmp.replace(self.path)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()

    # remembered directories for dialogs
    def last_dir(self, key: str) -> str:
        d = self.get("last_dirs", {}).get(key, "")
        return d if d and Path(d).exists() else str(Path.home())

    def remember_dir(self, key: str, path: str) -> None:
        p = Path(path)
        folder = str(p if p.is_dir() else p.parent)
        dirs = dict(self.get("last_dirs", {}))
        dirs[key] = folder
        self.set("last_dirs", dirs)
