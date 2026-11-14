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


class DecompressWorker(QThread):
    """Unpack .img.xz / .img.gz / .zip (largest .img inside) next to the source file."""

    progress = pyqtSignal(int, int)
    done = pyqtSignal(str)       # path to the .img
    failed = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    @staticmethod
    def needs(path: str) -> bool:
        return path.lower().endswith((".xz", ".gz", ".zip"))

    def run(self) -> None:
        import gzip
        import lzma
        import zipfile
        src = Path(self.path)
        try:
            low = src.name.lower()
            if low.endswith(".zip"):
                with zipfile.ZipFile(src) as zf:
                    imgs = [i for i in zf.infolist() if i.filename.lower().endswith(".img") and not i.is_dir()]
                    if not imgs:
                        raise OSError("В архиве нет .img")
                    info = max(imgs, key=lambda i: i.file_size)
                    dest = src.with_name(Path(info.filename).name)
                    total = info.file_size
                    with zf.open(info) as fin, open(dest, "wb") as fout:
                        self._copy(fin, fout, total)
            else:
                opener = lzma.open if low.endswith(".xz") else gzip.open
                dest = src.with_suffix("") if src.suffix.lower() in (".xz", ".gz") else src.with_name(src.stem)
                if dest.suffix.lower() != ".img":
                    dest = dest.with_suffix(dest.suffix + ".img") if dest.suffix else dest.with_suffix(".img")
                total = src.stat().st_size
                with open(src, "rb") as raw, opener(raw) as fin, open(dest, "wb") as fout:
                    self._copy(fin, fout, total, raw)
            self.done.emit(str(dest))
        except (OSError, EOFError, lzma.LZMAError, zipfile.BadZipFile) as exc:
            self.failed.emit(str(exc))

    def _copy(self, fin, fout, total: int, raw=None) -> None:
        while True:
            chunk = fin.read(4 << 20)
            if not chunk:
                break
            fout.write(chunk)
            pos = raw.tell() if raw is not None else fout.tell()
            self.progress.emit(min(pos, total), total)


class BundleWorker(QThread):
    """Extract split-APK bundles (.apks / .xapk / .apkm) into a temp folder."""

    done = pyqtSignal(list, list, str)   # apk paths, (obb_local, obb_remote) pairs, package
    failed = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        import json
        import tempfile
        import zipfile
        try:
            out = Path(tempfile.mkdtemp(prefix="droidforge-bundle-"))
            apks, obbs, pkg = [], [], ""
            with zipfile.ZipFile(self.path) as zf:
                root = out.resolve()
                for info in zf.infolist():
                    target = (out / info.filename).resolve()
                    if not str(target).startswith(str(root)) or info.is_dir():
                        continue
                    name = info.filename.lower()
                    if name.endswith(".apk") or name.endswith(".obb") or name == "manifest.json":
                        zf.extract(info, out)
                        if name.endswith(".apk"):
                            apks.append(str(target))
                        elif name.endswith(".obb"):
                            rel = info.filename.split("Android/obb/", 1)[-1]
                            obbs.append((str(target), "/sdcard/Android/obb/" + rel))
                manifest = out / "manifest.json"
                if manifest.exists():
                    try:
                        pkg = json.loads(manifest.read_text(encoding="utf-8")).get("package_name", "")
                    except ValueError:
                        pass
            if not apks:
                raise OSError("В архиве нет APK (возможно, он зашифрован)")
            base = [a for a in apks if Path(a).name.lower() in ("base.apk", f"{pkg}.apk".lower())]
            apks = base + [a for a in apks if a not in base]
            self.done.emit(apks, obbs, pkg)
        except (OSError, zipfile.BadZipFile) as exc:
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, url: str, dest: str, parent=None):
        super().__init__(parent)
        self.url, self.dest = url, dest

    def run(self) -> None:
        import urllib.request
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0 DroidForge"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(self.dest, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            self.done.emit(self.dest)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
