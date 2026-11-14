"""Locating and downloading Android platform-tools (adb / fastboot)."""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .config import APP_DIR, Config

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
EXE = ".exe" if IS_WIN else ""
PROJECT_DIR = Path(__file__).resolve().parents[2]
BUNDLED_DIR = APP_DIR / "platform-tools"


def _candidate_dirs() -> list[Path]:
    dirs = [BUNDLED_DIR, PROJECT_DIR / "platform-tools", Path.cwd() / "platform-tools"]
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(env):
            dirs.append(Path(os.environ[env]) / "platform-tools")
    home = Path.home()
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Android" / "Sdk" / "platform-tools")
        dirs += [Path("C:/platform-tools"), Path("C:/adb")]
    elif IS_MAC:
        dirs += [home / "Library/Android/sdk/platform-tools", Path("/opt/homebrew/bin")]
    else:
        dirs += [home / "Android/Sdk/platform-tools", Path("/usr/lib/android-sdk/platform-tools")]
    return dirs


def find_tool(name: str, configured: str = "") -> tuple[str, bool]:
    """Return (path, found). If not found, returns the bare name."""
    if configured and Path(configured).is_file():
        return configured, True
    for d in _candidate_dirs():
        p = d / f"{name}{EXE}"
        if p.is_file():
            return str(p), True
    found = shutil.which(name)
    if found:
        return found, True
    return name, False


class Tools:
    """Holds resolved paths to adb and fastboot."""

    def __init__(self, config: Config):
        self.config = config
        self.adb = "adb"
        self.fastboot = "fastboot"
        self.adb_found = False
        self.fastboot_found = False
        self.refresh()

    def refresh(self) -> None:
        self.adb, self.adb_found = find_tool("adb", self.config.get("adb_path"))
        self.fastboot, self.fastboot_found = find_tool("fastboot", self.config.get("fastboot_path"))


def platform_tools_url() -> str:
    osname = "windows" if IS_WIN else "darwin" if IS_MAC else "linux"
    return f"https://dl.google.com/android/repository/platform-tools-latest-{osname}.zip"


class PlatformToolsDownloader(QThread):
    """Downloads the latest official platform-tools into ~/.droidforge/platform-tools."""

    progress = pyqtSignal(int, int)      # received, total
    finishedOk = pyqtSignal(str)         # install dir
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            url = platform_tools_url()
            tmp_dir = Path(tempfile.mkdtemp(prefix="droidforge-"))
            archive = tmp_dir / "platform-tools.zip"
            with urllib.request.urlopen(url, timeout=30) as resp, open(archive, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            APP_DIR.mkdir(parents=True, exist_ok=True)
            if BUNDLED_DIR.exists():
                shutil.rmtree(BUNDLED_DIR, ignore_errors=True)
            with zipfile.ZipFile(archive) as zf:
                root = APP_DIR.resolve()
                for member in zf.namelist():
                    target = (APP_DIR / member).resolve()
                    if not str(target).startswith(str(root)):
                        raise RuntimeError(f"Подозрительный путь в архиве: {member}")
                zf.extractall(APP_DIR)
            if not IS_WIN:
                for f in BUNDLED_DIR.iterdir():
                    if f.is_file():
                        f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.finishedOk.emit(str(BUNDLED_DIR))
        except Exception as exc:  # noqa: BLE001 - report anything to the UI
            self.failed.emit(str(exc))
