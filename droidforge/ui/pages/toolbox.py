"""Toolbox: payload dumper, Magisk root wizard, backups, debloater, checksums."""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHeaderView,
    QLineEdit, QProgressBar, QScrollArea, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from ...core.payload import Payload, PayloadError
from ...core.workers import HashWorker, PayloadWorker
from .. import theme
from ..widgets import FilePicker, button, card, hbox, human_size, label, page_header


def _scroll(w: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setWidget(w)
    return s


def _check_item(checked: bool) -> QTableWidgetItem:
    it = QTableWidgetItem()
    it.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
    it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    return it


def _ro_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide()
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    hh = t.horizontalHeader()
    for i in range(len(headers)):
        hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    hh.setStretchLastSection(True)
    return t


def _set_all(table: QTableWidget, on: bool) -> None:
    state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
    for r in range(table.rowCount()):
        if not table.isRowHidden(r):
            table.item(r, 0).setCheckState(state)


def _checked_rows(table: QTableWidget) -> list[int]:
    return [r for r in range(table.rowCount())
            if table.item(r, 0).checkState() == Qt.CheckState.Checked and not table.isRowHidden(r)]


class ToolboxPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(14)
        lay.addLayout(page_header("🧰 Инструменты", "Распаковка OTA, root через Magisk, резервные копии, "
                                                    "удаление мусорных приложений и проверка контрольных сумм."))
        self.tabs = QTabWidget()
        self.payload_tab = PayloadTab(app)
        self.magisk_tab = MagiskTab(app)
        self.backup_tab = BackupTab(app)
        self.debloat_tab = DebloatTab(app)
        self.hash_tab = HashTab(app)
        self.tabs.addTab(self.payload_tab, "📦 Payload Dumper")
        self.tabs.addTab(_scroll(self.magisk_tab), "🪄 Root (Magisk)")
        self.tabs.addTab(_scroll(self.backup_tab), "💾 Бэкап")
        self.tabs.addTab(self.debloat_tab, "🧹 Debloat")
        self.tabs.addTab(_scroll(self.hash_tab), "🔐 Контрольные суммы")
        lay.addWidget(self.tabs, 1)

    def show_tab(self, widget: QWidget) -> None:
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if w is widget or (isinstance(w, QScrollArea) and w.widget() is widget):
                self.tabs.setCurrentIndex(i)
        self.app.show_page(self)

    def shutdown(self) -> None:
        self.payload_tab.shutdown()
        self.hash_tab.shutdown()


# =========================================================================
class PayloadTab(QWidget):
    DEFAULT = {"boot", "init_boot", "vendor_boot", "vbmeta", "vbmeta_system", "vbmeta_vendor", "dtbo", "recovery"}

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.worker: PayloadWorker | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Извлекает образы разделов (boot.img, init_boot.img, vbmeta.img…) из официальной "
                            "OTA‑прошивки — ZIP с <b>payload.bin</b> внутри или сам payload.bin. "
                            "Работает без сторонних утилит.", "muted", wrap=True))
        self.src = FilePicker("Перетащите OTA .zip или payload.bin", "OTA (*.zip *.bin);;Все файлы (*)",
                              exts=(".zip", ".bin"), config=app.config, key="ota")
        self.src.changed.connect(self.load)
        lay.addWidget(self.src)
        self.info = label("Файл не выбран", "muted")
        lay.addWidget(self.info)

        self.table = _table(["", "Раздел", "Размер", "Операций"])
        lay.addWidget(self.table, 1)
        self.out = FilePicker("Папка для образов (по умолчанию — рядом с прошивкой)", mode="dir",
                              config=app.config, key="ota_out")
        lay.addLayout(hbox(label("Сохранить в:", "muted"), self.out))
        self.verify = QCheckBox("Проверять SHA‑256")
        self.verify.setChecked(True)
        self.progress = QProgressBar()
        self.progress.hide()
        lay.addWidget(self.progress)
        self.go = button("📦 Извлечь выбранные", self.extract, "accent")
        self.cancel_btn = button("✖ Отмена", self.cancel, "danger")
        self.cancel_btn.hide()
        lay.addLayout(hbox(button("☑ Все", lambda: _set_all(self.table, True), "ghost"),
                           button("☐ Ничего", lambda: _set_all(self.table, False), "ghost"),
                           self.verify, None, self.cancel_btn, self.go))

    def load(self, path: str) -> None:
        self.table.setRowCount(0)
        if not path or not Path(path).is_file():
            return
        try:
            payload = Payload(path)
        except (PayloadError, OSError) as exc:
            self.info.setText(f"✖ {exc}")
            self.app.notify(str(exc), "error")
            return
        parts = payload.partitions
        payload.close()
        self.table.setRowCount(len(parts))
        for r, p in enumerate(parts):
            self.table.setItem(r, 0, _check_item(p.name in self.DEFAULT))
            name = _ro_item(p.name + ("  (delta)" if p.is_delta else ""))
            name.setData(Qt.ItemDataRole.UserRole, p.name)
            self.table.setItem(r, 1, name)
            self.table.setItem(r, 2, _ro_item(human_size(p.size)))
            self.table.setItem(r, 3, _ro_item(str(len(p.operations))))
        total = sum(p.size for p in parts)
        kind = "⚠ инкрементальная (delta) — извлечение невозможно" if any(p.is_delta for p in parts) else "✅ полная OTA"
        self.info.setText(f"Разделов: {len(parts)}  ·  всего {human_size(total)}  ·  {kind}")

    def extract(self) -> None:
        names = [self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in _checked_rows(self.table)]
        if not names:
            self.app.notify("Выберите разделы", "warn")
            return
        src = self.src.path()
        out = self.out.path() or str(Path(src).with_suffix("")) + "_images"
        self.worker = PayloadWorker(src, names, out, self.verify.isChecked(), self)
        self.worker.log.connect(self.app.console.write)
        self.worker.progress.connect(self._progress)
        self.worker.finishedAll.connect(self._done)
        self.progress.setValue(0)
        self.progress.show()
        self.go.setEnabled(False)
        self.cancel_btn.show()
        self.worker.start()

    def _progress(self, done: int, total: int, name: str) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress.setFormat(f"{name} · %p%")

    def _done(self, ok: bool, out: str) -> None:
        self.progress.hide()
        self.go.setEnabled(True)
        self.cancel_btn.hide()
        self.out.setPath(out)
        if ok:
            self.app.notify("📦 Образы извлечены", "ok")
            QDesktopServices.openUrl(QUrl.fromLocalFile(out))
        else:
            self.app.notify("Извлечение завершилось с ошибками — см. консоль", "error")

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel()

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)


# =========================================================================
class MagiskTab(QWidget):
    PKG = "com.topjohnwu.magisk"
    REMOTE_DIR = "/sdcard/Download/"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.patched: str = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        c0, l0 = card("🪄 Root через Magisk — мастер",
                      "Пять шагов от стоковой прошивки до root. Нужен разблокированный загрузчик и "
                      "boot.img (или init_boot.img для устройств, вышедших с Android 13+) от ТОЧНО вашей версии прошивки.")
        lay.addWidget(c0)

        c1, l1 = card("1️⃣  Стоковый образ")
        self.img = FilePicker("Перетащите boot.img / init_boot.img", "Образы (*.img)", exts=(".img",),
                              config=app.config, key="img")
        l1.addWidget(self.img)
        l1.addLayout(hbox(label("Нет образа? Извлеките его из OTA‑прошивки:", "muted"),
                          button("📦 Payload Dumper", lambda: app.page_toolbox.show_tab(app.page_toolbox.payload_tab)), None))
        lay.addWidget(c1)

        c2, l2 = card("2️⃣  Magisk на телефоне", "Установите официальный Magisk APK (github.com/topjohnwu/Magisk).")
        l2.addLayout(hbox(button("📥 Установить Magisk APK…", self.install_apk),
                          button("🌐 Скачать Magisk", lambda: QDesktopServices.openUrl(
                              QUrl("https://github.com/topjohnwu/Magisk/releases"))),
                          button("🔍 Проверить", self.check_magisk), None))
        lay.addWidget(c2)

        c3, l3 = card("3️⃣  Отправить образ и пропатчить",
                      "Образ попадёт в «Загрузки». В Magisk: Установка → «Выбрать и пропатчить файл» → выберите его.")
        l3.addLayout(hbox(button("📤 Отправить на телефон", self.push, "accent"),
                          button("🪄 Открыть Magisk", self.open_magisk), None))
        lay.addWidget(c3)

        c4, l4 = card("4️⃣  Забрать пропатченный образ")
        self.patched_lbl = label("Пока не получен", "muted")
        l4.addLayout(hbox(button("📥 Забрать magisk_patched", self.pull_patched, "accent"), self.patched_lbl, None))
        lay.addWidget(c4)

        c5, l5 = card("5️⃣  Прошить", "Устройство будет перезагружено в bootloader, образ прошит, затем — перезагрузка.")
        self.part = QComboBox()
        self.part.addItems(["boot", "init_boot"])
        self.both = QCheckBox("Прошить в оба слота (--slot=all)")
        l5.addLayout(hbox(label("Раздел:", "muted"), self.part, self.both, None,
                          button("⚡ Прошить пропатченный образ", self.flash, "accent")))
        lay.addWidget(c5)
        lay.addStretch(1)
        self.img.changed.connect(lambda p: self.part.setCurrentText("init_boot" if "init_boot" in Path(p).name else "boot"))

    def install_apk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Magisk APK", self.app.config.last_dir("apk"), "APK (*.apk)")
        if path and self.app.require_device(adb=True):
            self.app.run([self.app.adb_job("install", "-r", path, label="Установка Magisk")])

    def check_magisk(self) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", f"dumpsys package {self.PKG} | grep versionName || echo 'Magisk не установлен'"),
                          self.app.adb_job("shell", "su -c 'magisk -c' 2>/dev/null || echo 'root не активен'", allow_fail=True)],
                         stop_on_error=False)

    def push(self) -> None:
        path = self.img.path()
        if not Path(path).is_file():
            self.app.notify("Выберите стоковый образ (шаг 1)", "warn")
            return
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("push", path, self.REMOTE_DIR, label="Отправка образа в Загрузки")])

    def open_magisk(self) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", "monkey", "-p", self.PKG, "-c", "android.intent.category.LAUNCHER", "1")])

    def pull_patched(self) -> None:
        if self.app.require_device(shell=True):
            self.app.capture_adb(["shell", f"ls -t {self.REMOTE_DIR}magisk_patched*.img 2>/dev/null | head -n 1"], self._on_found)

    def _on_found(self, code: int, out: str) -> None:
        remote = out.strip().splitlines()[0].strip() if out.strip() else ""
        if not remote.endswith(".img"):
            self.app.notify("magisk_patched*.img не найден — сначала пропатчите образ в Magisk", "warn")
            return
        src = self.img.path()
        folder = Path(src).parent if src else Path(self.app.config.last_dir("img"))
        local = str(folder / Path(remote).name)
        self.patched = local
        self.patched_lbl.setText(f"✅ {Path(local).name}")
        self.app.run([self.app.adb_job("pull", remote, local, label="Скачивание пропатченного образа")])

    def flash(self) -> None:
        if not self.patched or not Path(self.patched).is_file():
            self.app.notify("Сначала заберите пропатченный образ (шаг 4)", "warn")
            return
        part = self.part.currentText()
        if not self.app.confirm("Прошивка Magisk", f"Прошить <b>{part}</b> файлом <code>{Path(self.patched).name}</code>?<br>"
                                "Если устройство не загрузится — прошейте обратно стоковый образ."):
            return
        dev = self.app.device
        jobs = []
        if dev and dev.is_adb:
            jobs.append(self.app.adb_job("reboot", "bootloader", label="Перезагрузка в Bootloader"))
        args = ["--slot=all"] if self.both.isChecked() else []
        jobs += [self.app.fb_job(*args, "flash", part, self.patched, label=f"Прошивка {part} (Magisk)"),
                 self.app.fb_job("reboot")]
        self.app.run(jobs)


# =========================================================================
class BackupTab(QWidget):
    IMPORTANT = {"boot", "init_boot", "vendor_boot", "dtbo", "vbmeta", "vbmeta_system", "recovery",
                 "persist", "modem", "modemst1", "modemst2", "fsg", "fsc", "efs", "sec_efs", "nvdata",
                 "nvram", "nvcfg", "protect1", "protect2", "devinfo", "oem", "param"}
    CRITICAL = {"persist", "modemst1", "modemst2", "fsg", "fsc", "efs", "sec_efs", "nvdata", "nvram",
                "nvcfg", "protect1", "protect2"}
    HUGE = {"userdata", "super", "system", "vendor", "product", "system_ext", "cache", "metadata"}
    FOLDERS = ["DCIM", "Pictures", "Download", "Documents", "Music", "Movies", "Telegram", "WhatsApp/Media"]

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        c1, l1 = card("🧬 Бэкап разделов (нужен root)",
                      "Сохраняет образы разделов через dd. <b style='color:#ffb547'>Обязательно сохраните EFS / modemst / "
                      "persist / nvdata</b> перед экспериментами — там IMEI и калибровки, их не восстановить без бэкапа.")
        self.parts = _table(["", "Раздел", "Пометка"])
        self.parts.setMinimumHeight(300)
        l1.addWidget(self.parts, 1)
        self.parts_filter = QLineEdit()
        self.parts_filter.setPlaceholderText("🔎 Фильтр…")
        self.parts_filter.textChanged.connect(self._filter_parts)
        l1.addLayout(hbox(button("🔍 Загрузить список разделов", self.load_parts), self.parts_filter,
                          button("☑ Все", lambda: _set_all(self.parts, True), "ghost"),
                          button("☐ Ничего", lambda: _set_all(self.parts, False), "ghost"), None,
                          button("💾 Сохранить выбранные", self.backup_parts, "accent")))
        lay.addWidget(c1, 3)

        c2, l2 = card("📁 Бэкап файлов и приложений (без root)")
        grid = QGridLayout()
        self.folder_boxes = []
        for i, name in enumerate(self.FOLDERS):
            box = QCheckBox(name)
            box.setChecked(name in ("DCIM", "Pictures", "Download", "Documents"))
            self.folder_boxes.append(box)
            grid.addWidget(box, i // 4, i % 4)
        l2.addLayout(grid)
        l2.addLayout(hbox(button("📁 Скачать папки с /sdcard", self.backup_folders, "accent"),
                          button("📦 Скачать APK всех пользовательских приложений", self.backup_apks),
                          button("⬆ Восстановить папку на телефон", self.restore_folder), None))
        lay.addWidget(c2, 2)

    # ----------------------------------------------------- partitions
    def load_parts(self) -> None:
        if not self.app.require_device(shell=True):
            return
        cmd = "su -c 'ls /dev/block/by-name 2>/dev/null || ls /dev/block/bootdevice/by-name'"
        self.app.capture_adb(["shell", cmd], self._on_parts)

    def _on_parts(self, code: int, out: str) -> None:
        names = sorted({n.strip() for n in out.split() if n.strip() and "/" not in n and ":" not in n})
        if code != 0 or not names or "denied" in out or "not found" in out:
            self.app.notify("Не удалось получить список — нужен root (Magisk) и разрешение для Shell", "error")
            self.app.console.write(out.strip()[:500], "fail")
            return
        self.parts.setRowCount(len(names))
        for r, name in enumerate(names):
            base = name[:-2] if name.endswith(("_a", "_b")) else name
            self.parts.setItem(r, 0, _check_item(base in self.IMPORTANT and not name.endswith("_b")))
            self.parts.setItem(r, 1, _ro_item(name))
            note = "🛡 IMEI / калибровки" if base in self.CRITICAL else "🐘 большой" if base in self.HUGE else \
                   "⭐ важный" if base in self.IMPORTANT else ""
            item = _ro_item(note)
            if base in self.CRITICAL:
                item.setForeground(QColor(theme.WARN))
            self.parts.setItem(r, 2, item)

    def _filter_parts(self, text: str) -> None:
        text = text.lower()
        for r in range(self.parts.rowCount()):
            self.parts.setRowHidden(r, bool(text) and text not in self.parts.item(r, 1).text().lower())

    def backup_parts(self) -> None:
        names = [self.parts.item(r, 1).text() for r in _checked_rows(self.parts)]
        if not names or not self.app.require_device(shell=True):
            return
        big = [n for n in names if (n[:-2] if n.endswith(("_a", "_b")) else n) in self.HUGE]
        if big and not self.app.confirm("Большие разделы", f"{', '.join(big)} могут занимать гигабайты, а на телефоне "
                                        "должно хватать места для временной копии. Продолжить?", danger=False):
            return
        folder = QFileDialog.getExistingDirectory(self, "Куда сохранить бэкап", self.app.config.last_dir("backup"))
        if not folder:
            return
        self.app.config.remember_dir("backup", folder)
        dest = Path(folder) / f"backup_{self.app.device.serial}_{time.strftime('%Y%m%d_%H%M%S')}"
        dest.mkdir(parents=True, exist_ok=True)
        tmp = "/sdcard/droidforge_backup"
        jobs = [self.app.adb_job("shell", f"mkdir -p {tmp}")]
        for n in names:
            src = f"/dev/block/by-name/{n}"
            remote = f"{tmp}/{n}.img"
            jobs.append(self.app.adb_job("shell", f"su -c 'dd if={src} of={remote} bs=4M 2>&1 || dd if=/dev/block/bootdevice/by-name/{n} of={remote} bs=4M'",
                                         label=f"Чтение {n}"))
            jobs.append(self.app.adb_job("pull", remote, str(dest / f"{n}.img")))
            jobs.append(self.app.adb_job("shell", f"rm -f {remote}", allow_fail=True))
        jobs.append(self.app.adb_job("shell", f"rmdir {tmp}", allow_fail=True))
        self.app.run(jobs, stop_on_error=False)
        self.app.after_queue(lambda: self.app.notify(f"💾 Бэкап: {dest.name}", "ok"))

    # ----------------------------------------------------- files
    def backup_folders(self) -> None:
        names = [b.text() for b in self.folder_boxes if b.isChecked()]
        if not names or not self.app.require_device(adb=True):
            return
        folder = QFileDialog.getExistingDirectory(self, "Куда сохранить", self.app.config.last_dir("backup"))
        if not folder:
            return
        self.app.config.remember_dir("backup", folder)
        dest = Path(folder) / f"sdcard_{time.strftime('%Y%m%d_%H%M%S')}"
        jobs = []
        for n in names:
            target = dest / n
            target.parent.mkdir(parents=True, exist_ok=True)
            jobs.append(self.app.adb_job("pull", f"/sdcard/{n}", str(target.parent), label=f"Копирование {n}", allow_fail=True))
        self.app.run(jobs, stop_on_error=False)

    def backup_apks(self) -> None:
        if not self.app.require_device(shell=True):
            return
        folder = QFileDialog.getExistingDirectory(self, "Куда сохранить APK", self.app.config.last_dir("apk_out"))
        if not folder:
            return
        self.app.config.remember_dir("apk_out", folder)
        dest = Path(folder) / f"apps_{time.strftime('%Y%m%d_%H%M%S')}"
        dest.mkdir(parents=True, exist_ok=True)
        self.app.capture_adb(["shell", "pm list packages -3 -f"], lambda c, out: self._on_apk_list(out, dest), timeout=30000)

    def _on_apk_list(self, out: str, dest: Path) -> None:
        jobs = []
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("package:") or "=" not in line:
                continue
            path, _, pkg = line[8:].rpartition("=")
            jobs.append(self.app.adb_job("pull", path, str(dest / f"{pkg}.apk"), label=pkg, allow_fail=True))
        if not jobs:
            self.app.notify("Пользовательские приложения не найдены", "warn")
            return
        self.app.console.write(f"📦 Приложений: {len(jobs)} (split‑части сохраняются только базовые)", "info")
        self.app.run(jobs, stop_on_error=False)

    def restore_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка для загрузки в /sdcard", self.app.config.last_dir("backup"))
        if folder and self.app.require_device(adb=True):
            self.app.run([self.app.adb_job("push", folder, "/sdcard/", label=f"Восстановление {Path(folder).name}")])


# =========================================================================
DEBLOAT: dict[str, list[tuple[str, str]]] = {
    "Xiaomi / MIUI / HyperOS": [
        ("com.miui.msa.global", "MSA — рекламный сервис"),
        ("com.miui.analytics", "Аналитика MIUI"),
        ("com.miui.daemon", "Сбор статистики"),
        ("com.xiaomi.mipicks", "GetApps (магазин)"),
        ("com.miui.hybrid", "Быстрые приложения"),
        ("com.miui.videoplayer", "Mi Видео"),
        ("com.miui.player", "Mi Музыка"),
        ("com.mi.globalbrowser", "Mi Браузер"),
        ("com.miui.bugreport", "Отчёты об ошибках"),
        ("com.xiaomi.glgm", "Игры Xiaomi"),
        ("com.miui.yellowpage", "Жёлтые страницы"),
    ],
    "Samsung One UI": [
        ("com.samsung.android.bixby.agent", "Bixby Voice"),
        ("com.samsung.android.bixby.wakeup", "Bixby — активация голосом"),
        ("com.samsung.android.visionintelligence", "Bixby Vision"),
        ("com.samsung.android.app.spage", "Samsung Free"),
        ("com.samsung.android.arzone", "AR Zone"),
        ("com.samsung.android.ardrawing", "AR Doodle"),
        ("com.samsung.android.app.tips", "Советы"),
    ],
    "Facebook (предустановка)": [
        ("com.facebook.appmanager", "Facebook App Manager"),
        ("com.facebook.services", "Facebook Services"),
        ("com.facebook.system", "Facebook App Installer"),
        ("com.facebook.katana", "Facebook"),
    ],
    "Google (необязательные)": [
        ("com.google.android.apps.tachyon", "Google Meet (Duo)"),
        ("com.google.android.videos", "Google TV / Play Фильмы"),
        ("com.google.android.apps.youtube.music", "YouTube Music"),
        ("com.google.android.apps.podcasts", "Google Подкасты"),
        ("com.google.android.apps.magazines", "Google Новости"),
        ("com.google.android.apps.wellbeing", "Цифровое благополучие"),
    ],
}


class DebloatTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.installed: set[str] = set()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Удаление предустановленного мусора для текущего пользователя "
                            "(<code>pm uninstall -k --user 0</code>). Приложения остаются в системном разделе — "
                            "их можно <b>вернуть</b> кнопкой «Восстановить» или сбросом настроек.", "muted", wrap=True))
        self.table = _table(["", "Пакет", "Описание", "Группа", "Статус"])
        lay.addWidget(self.table, 1)
        self._fill()
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("Свой пакет, например com.example.app")
        lay.addLayout(hbox(button("🔍 Проверить установленные", self.scan), None,
                           self.custom, button("➕ В список", self.add_custom)))
        lay.addLayout(hbox(button("☑ Только установленные", self.check_installed, "ghost"),
                           button("☐ Снять все", lambda: _set_all(self.table, False), "ghost"), None,
                           button("🚫 Отключить", lambda: self.apply("disable")),
                           button("♻ Восстановить", lambda: self.apply("restore")),
                           button("🗑 Удалить выбранные", lambda: self.apply("remove"), "danger")))

    def _fill(self) -> None:
        rows = [(pkg, desc, group) for group, items in DEBLOAT.items() for pkg, desc in items]
        self.table.setRowCount(len(rows))
        for r, (pkg, desc, group) in enumerate(rows):
            self._set_row(r, pkg, desc, group)

    def _set_row(self, r: int, pkg: str, desc: str, group: str) -> None:
        self.table.setItem(r, 0, _check_item(False))
        self.table.setItem(r, 1, _ro_item(pkg))
        self.table.setItem(r, 2, _ro_item(desc))
        self.table.setItem(r, 3, _ro_item(group))
        self.table.setItem(r, 4, _ro_item("—"))

    def add_custom(self) -> None:
        pkg = self.custom.text().strip()
        if not pkg:
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._set_row(r, pkg, "Добавлено вручную", "Мои")
        self.table.item(r, 0).setCheckState(Qt.CheckState.Checked)
        self.custom.clear()
        self._update_status()

    def scan(self) -> None:
        if self.app.require_device(shell=True):
            self.app.capture_adb(["shell", "pm list packages"], self._on_scan, timeout=30000)

    def _on_scan(self, code: int, out: str) -> None:
        self.installed = {l[8:].strip() for l in out.splitlines() if l.startswith("package:")}
        self._update_status()
        self.app.notify(f"Найдено установленных из списка: {sum(self._is_installed(r) for r in range(self.table.rowCount()))}", "info")

    def _is_installed(self, r: int) -> bool:
        return self.table.item(r, 1).text() in self.installed

    def _update_status(self) -> None:
        if not self.installed:
            return
        for r in range(self.table.rowCount()):
            inst = self._is_installed(r)
            item = self.table.item(r, 4)
            item.setText("✅ установлено" if inst else "— нет")
            item.setForeground(QColor(theme.SUCCESS if inst else theme.MUTED))

    def check_installed(self) -> None:
        if not self.installed:
            self.app.notify("Сначала нажмите «Проверить установленные»", "warn")
            return
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.CheckState.Checked if self._is_installed(r) else Qt.CheckState.Unchecked)

    def apply(self, action: str) -> None:
        pkgs = [self.table.item(r, 1).text() for r in _checked_rows(self.table)]
        if not pkgs or not self.app.require_device(shell=True):
            if not pkgs:
                self.app.notify("Отметьте пакеты", "warn")
            return
        if action == "remove":
            if not self.app.confirm("Debloat", f"Удалить для пользователя {len(pkgs)} прил.?<br><small>{', '.join(pkgs)}</small>"):
                return
            jobs = [self.app.adb_job("shell", "pm", "uninstall", "-k", "--user", "0", p, allow_fail=True) for p in pkgs]
        elif action == "disable":
            jobs = [self.app.adb_job("shell", "pm", "disable-user", "--user", "0", p, allow_fail=True) for p in pkgs]
        else:
            jobs = []
            for p in pkgs:
                jobs.append(self.app.adb_job("shell", "cmd", "package", "install-existing", p, allow_fail=True))
                jobs.append(self.app.adb_job("shell", "pm", "enable", p, allow_fail=True))
        self.app.run(jobs, stop_on_error=False)
        self.app.after_queue(self.scan)


# =========================================================================
class HashTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.worker: HashWorker | None = None
        self.result: dict[str, str] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        c, cl = card("🔐 Проверка целостности файла",
                     "Сравните контрольную сумму скачанной прошивки с указанной на сайте — "
                     "повреждённый образ может «окирпичить» устройство.")
        self.file = FilePicker("Перетащите любой файл", config=app.config, key="hash")
        self.file.changed.connect(lambda _p: self.compute())
        cl.addWidget(self.file)
        self.expected = QLineEdit()
        self.expected.setPlaceholderText("Ожидаемая сумма (MD5 / SHA‑1 / SHA‑256) — вставьте для сравнения")
        self.expected.textChanged.connect(self._compare)
        cl.addWidget(self.expected)
        self.progress = QProgressBar()
        self.progress.hide()
        cl.addWidget(self.progress)
        self.rows: dict[str, QLineEdit] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        for i, algo in enumerate(("md5", "sha1", "sha256")):
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setStyleSheet(f"font-family: {theme.MONO};")
            self.rows[algo] = edit
            grid.addWidget(label(algo.upper(), "muted"), i, 0)
            grid.addWidget(edit, i, 1)
            grid.addWidget(button("📋", lambda a=algo: self.app.clipboard_set(self.rows[a].text()), "ghost", "Копировать"), i, 2)
        cl.addLayout(grid)
        self.verdict = label("", "h2")
        cl.addLayout(hbox(button("🔄 Посчитать", self.compute, "accent"), self.verdict, None))
        lay.addWidget(c)
        lay.addStretch(1)

    def compute(self) -> None:
        path = self.file.path()
        if not Path(path).is_file():
            self.app.notify("Выберите файл", "warn")
            return
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        for e in self.rows.values():
            e.clear()
        self.verdict.setText("")
        self.progress.setValue(0)
        self.progress.show()
        self.worker = HashWorker(path, self)
        self.worker.progress.connect(lambda d, t: (self.progress.setMaximum(max(t, 1)), self.progress.setValue(d)))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(lambda e: (self.progress.hide(), self.app.notify(e, "error")))
        self.worker.start()

    def _done(self, result: dict) -> None:
        self.progress.hide()
        self.result = result
        for k, v in result.items():
            self.rows[k].setText(v)
        self._compare()

    def _compare(self, *_):
        exp = self.expected.text().strip().lower()
        if not exp or not self.result:
            self.verdict.setText("")
            return
        if exp in self.result.values():
            self.verdict.setText("✅ Совпадает")
            self.verdict.setStyleSheet(f"color: {theme.SUCCESS};")
        else:
            self.verdict.setText("❌ НЕ совпадает")
            self.verdict.setStyleSheet(f"color: {theme.DANGER};")

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)

