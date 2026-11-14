"""Background QThread workers for CPU / IO heavy tasks."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .payload import Payload, PayloadError


class HashWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)       # {"md5": ..., "sha1": ..., "sha256": ...}
    failed = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            total = os.path.getsize(self.path)
            hashes = {"md5": hashlib.md5(), "sha1": hashlib.sha1(), "sha256": hashlib.sha256()}
            got = 0
            with open(self.path, "rb") as fh:
                for chunk in iter(lambda: fh.read(4 << 20), b""):
                    if self._cancel:
                        self.failed.emit("Отменено")
                        return
                    for h in hashes.values():
                        h.update(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            self.done.emit({k: h.hexdigest() for k, h in hashes.items()})
        except OSError as exc:
            self.failed.emit(str(exc))


class PayloadWorker(QThread):
    """Extract selected partitions from a payload into out_dir."""

    log = pyqtSignal(str, str)            # text, kind
    progress = pyqtSignal(int, int, str)  # done ops, total ops, partition
    finishedAll = pyqtSignal(bool, str)   # ok, out_dir

    def __init__(self, path: str, names: list[str], out_dir: str, verify: bool = True, parent=None):
        super().__init__(parent)
        self.path, self.names, self.out_dir, self.verify = path, names, out_dir, verify
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        ok = True
        try:
            payload = Payload(self.path)
        except (PayloadError, OSError) as exc:
            self.log.emit(f"✖ {exc}", "fail")
            self.finishedAll.emit(False, self.out_dir)
            return
        try:
            Path(self.out_dir).mkdir(parents=True, exist_ok=True)
            parts = [p for p in payload.partitions if p.name in self.names]
            total_ops = sum(len(p.operations) for p in parts) or 1
            done_before = 0
            for part in parts:
                out = str(Path(self.out_dir) / f"{part.name}.img")
                self.log.emit(f"📦 Извлечение {part.name} ({part.size / 1048576:.1f} МБ)…", "info")

                def prog(d, _t, base=done_before, name=part.name):
                    self.progress.emit(base + d, total_ops, name)

                try:
                    good = payload.extract(part, out, prog, lambda: self._cancel, self.verify)
                except PayloadError as exc:
                    self.log.emit(f"✖ {exc}", "fail")
                    ok = False
                    if self._cancel:
                        break
                    done_before += len(part.operations)
                    continue
                done_before += len(part.operations)
                if good:
                    self.log.emit(f"✔ {part.name}.img" + (" — SHA‑256 совпадает" if self.verify and part.sha256 else ""), "ok")
                else:
                    ok = False
                    self.log.emit(f"✖ {part.name}.img — контрольная сумма НЕ совпадает!", "fail")
        except OSError as exc:
            ok = False
            self.log.emit(f"✖ {exc}", "fail")
        finally:
            payload.close()
        self.finishedAll.emit(ok, self.out_dir)
