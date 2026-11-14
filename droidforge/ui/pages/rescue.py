"""Rescue center: bootloop fixes, restore from backups, A/B slots, custom recovery, settings/app restore."""
from __future__ import annotations

import json
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHeaderView, QScrollArea, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .. import theme
from ..widgets import FilePicker, button, card, hbox, human_size, label, page_header
from .adb_tools import sh_quote

CRITICAL = {"persist", "modemst1", "modemst2", "fsg", "fsc", "efs", "sec_efs", "nvdata", "nvram", "nvcfg",
            "protect1", "protect2"}
# settings keys that are device-specific or dangerous to copy between devices / restore blindly
SKIP_KEYS = {"android_id", "bluetooth_address", "bluetooth_name", "device_name", "adb_enabled", "development_settings_enabled",
             "device_provisioned", "user_setup_complete", "boot_count", "wifi_on", "airplane_mode_on",
             "lock_screen_owner_info", "enabled_accessibility_services", "default_input_method", "enabled_input_methods"}


def _scroll(w: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    s.setWidget(w)
    return s


def _base(name: str) -> str:
    return name[:-2] if name.endswith(("_a", "_b")) else name


class RescuePage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(14)
        lay.addLayout(page_header("🚑 Восстановление", "Телефон не загружается, нужно откатиться или восстановить "
                                                         "бэкап — здесь всё для спасения устройства."))
        self.tabs = QTabWidget()
        self.tabs.addTab(_scroll(self._tab_bootloop()), "🩹 Не загружается")
        self.tabs.addTab(self._tab_restore(), "♻ Восстановить разделы")
        self.tabs.addTab(_scroll(self._tab_slots()), "🅰🅱 Слоты")
        self.tabs.addTab(_scroll(self._tab_recovery()), "🛟 Кастомный recovery")
        self.tabs.addTab(_scroll(self._tab_settings()), "⚙ Настройки и приложения")
        lay.addWidget(self.tabs, 1)

    # ------------------------------------------------------------ helpers
    def _fastboot_jobs(self, *jobs_args, labels=None, confirm: str | None = None) -> None:
        if confirm and not self.app.confirm("Подтверждение", confirm):
            return
        pre = self.app.page_flash._prepare_fastboot()
        if pre is None:
            return
        jobs = list(pre)
        for i, args in enumerate(jobs_args):
            jobs.append(self.app.fb_job(*args, label=(labels or [""] * len(jobs_args))[i]))
        self.app.run(jobs)

    # ============================================================ bootloop
    def _tab_bootloop(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        lay.addWidget(label("Пробуйте шаги по порядку — от самого безопасного к радикальному. "
                            "Большинство бутлупов после обновления или установки модулей лечатся первыми тремя.",
                            "muted", wrap=True))
        grid = QGridLayout()
        grid.setSpacing(14)

        c1, l1 = card("1️⃣  Переключить слот A ↔ B",
                      "На A/B устройствах во втором слоте обычно лежит прошлая рабочая система. "
                      "Помогает после неудачного обновления. Данные не удаляются.")
        l1.addLayout(hbox(button("🔁 Переключить слот и перезагрузить", self.switch_slot, "accent"), None))
        grid.addWidget(c1, 0, 0)

        c2, l2 = card("2️⃣  Отключить модули Magisk",
                      "Если бутлуп начался после установки модуля. Подключите телефон и включите — команда "
                      "сработает, как только во время загрузки поднимется adb.")
        l2.addLayout(hbox(button("🧩 Удалить все модули Magisk", self.remove_magisk_modules, "accent"),
                          button("⏳ Ждать устройство", lambda: self.app.run([self.app.adb_job("wait-for-device", label="Ожидание adb…")])),
                          None))
        grid.addWidget(c2, 0, 1)

        c3, l3 = card("3️⃣  Вернуть стоковые образы",
                      "Отменяет root/кастомное ядро: прошейте оригинальные boot / init_boot / vbmeta от вашей версии прошивки.")
        self.stock_boot = FilePicker("boot.img или init_boot.img (сток)", "Образы (*.img)", exts=(".img",),
                                     config=self.app.config, key="img")
        self.stock_vbmeta = FilePicker("vbmeta.img (сток, необязательно)", "Образы (*.img)", exts=(".img",),
                                       config=self.app.config, key="img")
        self.stock_both = QCheckBox("В оба слота")
        self.stock_both.setChecked(True)
        l3.addWidget(self.stock_boot)
        l3.addWidget(self.stock_vbmeta)
        l3.addLayout(hbox(self.stock_both, None, button("📦 Прошить сток", self.flash_stock, "accent")))
        grid.addWidget(c3, 1, 0)

        c4, l4 = card("4️⃣  Очистка и сброс", "Сброс удаляет все данные пользователя — последний шаг перед перепрошивкой.")
        l4.addLayout(hbox(button("🛠 Загрузить recovery", lambda: self.app.reboot("recovery")),
                          button("🧹 Стереть cache", lambda: self._fastboot_jobs(["erase", "cache"],
                                 confirm="Стереть раздел cache? (есть не на всех устройствах)"))))
        l4.addLayout(hbox(button("🧨 Сброс данных (fastboot -w)", lambda: self._fastboot_jobs(
            ["-w"], ["reboot"], labels=["Сброс данных", ""],
            confirm="ВСЕ данные пользователя (фото, приложения, аккаунты) будут удалены."), "danger"), None))
        grid.addWidget(c4, 1, 1)

        c5, l5 = card("5️⃣  Полная перепрошивка",
                      "Скачайте официальную прошивку для своей модели и прошейте её целиком из папки.")
        l5.addLayout(hbox(button("📁 Открыть «Прошивка из папки»", lambda: (self.app.show_page(self.app.page_flash),
                                                                          self.app.page_flash.tabs.setCurrentIndex(1)), "accent"),
                          button("📦 Извлечь образы из OTA", lambda: self.app.page_toolbox.show_tab(self.app.page_toolbox.payload_tab)),
                          None))
        grid.addWidget(c5, 2, 0)

        c6, l6 = card("🚨 Не входит даже в fastboot?",
                      "Это «hard brick» — нужен аварийный режим производителя:")
        l6.addWidget(label(
            "• <b>Qualcomm</b> — EDL (9008): MiFlash, QFIL<br>"
            "• <b>MediaTek</b> — BROM/Preloader: SP Flash Tool, mtkclient<br>"
            "• <b>Samsung</b> — Download mode: Odin / Heimdall<br>"
            "• Сначала попробуйте зажать <b>Питание + Громкость −</b> на 15–30 секунд.", "muted", wrap=True))
        grid.addWidget(c6, 2, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        return w

    def switch_slot(self) -> None:
        dev = self.app.device
        if not self.app.require_device():
            return
        if dev.is_fastboot:
            self.app.capture_fb(["getvar", "current-slot"], self._on_slot)
        elif dev.has_shell:
            self.app.capture_adb(["shell", "getprop ro.boot.slot_suffix"], self._on_slot)
        else:
            self.app.notify("Нужен режим ADB или Fastboot", "warn")

    def _on_slot(self, code: int, out: str) -> None:
        text = out.lower()
        cur = "b" if ("current-slot: b" in text or text.strip().endswith("_b") or text.strip() == "b") else \
              "a" if ("current-slot: a" in text or text.strip().endswith("_a") or text.strip() == "a") else ""
        if not cur:
            self.app.notify("Устройство не поддерживает A/B слоты (или слот не определён)", "warn")
            self.app.console.write(out.strip()[:300], "warn")
            return
        other = "a" if cur == "b" else "b"
        self._fastboot_jobs(["set_active", other], ["reboot"], labels=[f"Слот {cur.upper()} → {other.upper()}", ""],
                            confirm=f"Текущий слот: <b>{cur.upper()}</b>. Сделать активным <b>{other.upper()}</b> и перезагрузить?")

    def remove_magisk_modules(self) -> None:
        self.app.run([self.app.adb_job("wait-for-device", label="Ожидание adb (включите телефон)…"),
                      self.app.adb_job("shell", "magisk --remove-modules || su -c 'magisk --remove-modules'",
                                       label="Удаление модулей Magisk")])
        self.app.notify("Ожидание устройства… Модули удалятся, как только появится adb", "info")

    def flash_stock(self) -> None:
        boot, vbmeta = self.stock_boot.path(), self.stock_vbmeta.path()
        if not Path(boot).is_file():
            self.app.notify("Выберите стоковый boot / init_boot", "warn")
            return
        part = "init_boot" if "init_boot" in Path(boot).name else "boot"
        slot = ["--slot=all"] if self.stock_both.isChecked() else []
        jobs = [slot + ["flash", part, boot]]
        labels = [f"Сток {part}"]
        if vbmeta and Path(vbmeta).is_file():
            jobs.append(slot + ["flash", "vbmeta", vbmeta])
            labels.append("Сток vbmeta")
        jobs.append(["reboot"])
        labels.append("")
        self._fastboot_jobs(*jobs, labels=labels, confirm=f"Прошить стоковый <b>{part}</b>"
                            + (" и <b>vbmeta</b>" if len(jobs) > 2 else "") + "?")

    # ============================================================ restore
    def _tab_restore(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Восстановление образов разделов из бэкапа (например, сделанного в «Инструменты → Резервные копии»). "
                            "Имя файла = имя раздела: <code>boot_a.img</code>, <code>modemst1.img</code>…", "muted", wrap=True))
        self.r_dir = FilePicker("Папка с бэкапом (*.img)", mode="dir", config=self.app.config, key="backup")
        self.r_dir.changed.connect(self.scan_backup)
        lay.addWidget(self.r_dir)
        self.r_table = QTableWidget(0, 4)
        self.r_table.setHorizontalHeaderLabels(["", "Раздел", "Размер", "Пометка"])
        hh = self.r_table.horizontalHeader()
        for i in range(4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.r_table.verticalHeader().hide()
        self.r_table.setAlternatingRowColors(True)
        self.r_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.r_table, 1)
        self.r_method = QComboBox()
        self.r_method.addItem("⚡ Через fastboot (загрузчик должен быть разблокирован)", "fastboot")
        self.r_method.addItem("🔑 Через root dd (из работающей системы)", "dd")
        self.r_status = label("Папка не выбрана", "muted")
        lay.addLayout(hbox(self.r_status, None, label("Способ:", "muted"), self.r_method))
        lay.addLayout(hbox(None, button("♻ Восстановить выбранные", self.restore, "accent")))
        return w

    def scan_backup(self, folder: str) -> None:
        root = Path(folder)
        if not root.is_dir():
            return
        imgs = sorted(root.glob("*.img"))
        self.r_table.setRowCount(len(imgs))
        for r, p in enumerate(imgs):
            name = p.stem
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.r_table.setItem(r, 0, chk)
            it = QTableWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, str(p))
            self.r_table.setItem(r, 1, it)
            self.r_table.setItem(r, 2, QTableWidgetItem(human_size(p.stat().st_size)))
            note = QTableWidgetItem("🛡 IMEI / калибровки" if _base(name) in CRITICAL else "")
            if _base(name) in CRITICAL:
                note.setForeground(QColor(theme.WARN))
            self.r_table.setItem(r, 3, note)
        self.r_status.setText(f"Образов: {len(imgs)} — отметьте нужные")

    def restore(self) -> None:
        items = [(self.r_table.item(r, 1).text(), self.r_table.item(r, 1).data(Qt.ItemDataRole.UserRole))
                 for r in range(self.r_table.rowCount())
                 if self.r_table.item(r, 0).checkState() == Qt.CheckState.Checked]
        if not items:
            self.app.notify("Отметьте разделы для восстановления", "warn")
            return
        names = ", ".join(n for n, _ in items)
        if not self.app.confirm("Восстановление разделов",
                                f"Записать на устройство: <b>{names}</b>?<br><br>Образы должны быть сняты с ЭТОГО же "
                                "устройства. Чужой EFS/modem может лишить телефон связи."):
            return
        if self.r_method.currentData() == "fastboot":
            self._fastboot_jobs(*[["flash", n, p] for n, p in items], labels=[f"Восстановление {n}" for n, _ in items])
            return
        if not self.app.require_device(shell=True):
            return
        tmp = "/sdcard/droidforge_restore"
        jobs = [self.app.adb_job("shell", f"mkdir -p {tmp}")]
        for n, p in items:
            remote = f"{tmp}/{n}.img"
            jobs.append(self.app.adb_job("push", p, remote, label=f"Загрузка {n}"))
            jobs.append(self.app.adb_job("shell", f"su -c 'dd if={remote} of=/dev/block/by-name/{n} bs=4M && sync'",
                                         label=f"Запись {n}"))
            jobs.append(self.app.adb_job("shell", f"rm -f {remote}", allow_fail=True))
        jobs.append(self.app.adb_job("shell", f"rmdir {tmp}", allow_fail=True))
        self.app.run(jobs, stop_on_error=True)

    # ============================================================ slots
    def _tab_slots(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        c, cl = card("🅰🅱 Состояние слотов", "Нужен режим Fastboot. «Неудачный» слот (unbootable) загрузчик пропускает.")
        self.slot_table = QTableWidget(0, 3)
        self.slot_table.setHorizontalHeaderLabels(["Параметр", "Слот A", "Слот B"])
        self.slot_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.slot_table.verticalHeader().hide()
        self.slot_table.setMinimumHeight(190)
        self.slot_label = label("Нажмите «Прочитать»", "h2")
        cl.addLayout(hbox(self.slot_label, None, button("🔍 Прочитать", self.read_slots, "accent")))
        cl.addWidget(self.slot_table)
        cl.addLayout(hbox(button("Сделать активным A", lambda: self._fastboot_jobs(["set_active", "a"], confirm="Активировать слот A?")),
                          button("Сделать активным B", lambda: self._fastboot_jobs(["set_active", "b"], confirm="Активировать слот B?")),
                          None, button("🔁 Перезагрузить", lambda: self.app.reboot("system"))))
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def read_slots(self) -> None:
        if self.app.require_device(fastboot=True):
            self.app.capture_fb(["getvar", "all"], self._on_slots, timeout=15000)

    def _on_slots(self, code: int, out: str) -> None:
        vals: dict[str, str] = {}
        for line in out.splitlines():
            line = line.replace("(bootloader)", "").strip()
            key, sep, value = line.partition(": ")
            if sep:
                vals[key.strip()] = value.strip()
        cur = vals.get("current-slot", "?")
        self.slot_label.setText(f"Текущий слот: {cur.upper()}" if cur != "?" else "A/B не обнаружены")
        rows = [("Успешно загружался", "slot-successful"), ("Помечен неудачным", "slot-unbootable"),
                ("Осталось попыток", "slot-retry-count")]
        self.slot_table.setRowCount(len(rows))
        for r, (title, key) in enumerate(rows):
            self.slot_table.setItem(r, 0, QTableWidgetItem(title))
            for c, slot in enumerate(("a", "b"), 1):
                v = vals.get(f"{key}:{slot}") or vals.get(f"{key}:_{slot}") or "—"
                item = QTableWidgetItem(v)
                bad = (key == "slot-unbootable" and v == "yes") or (key == "slot-successful" and v == "no")
                if bad:
                    item.setForeground(QColor(theme.DANGER))
                self.slot_table.setItem(r, c, item)

    # ============================================================ custom recovery
    def _tab_recovery(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        c, cl = card("🛟 TWRP / OrangeFox / другой recovery",
                     "Совет: сначала «Загрузить временно» — если recovery работает, установите его из самого recovery "
                     "(на A/B устройствах это правильный способ).")
        self.rec_img = FilePicker("Перетащите образ recovery (.img)", "Образы (*.img)", exts=(".img",),
                                  config=self.app.config, key="recovery")
        cl.addWidget(self.rec_img)
        cl.addLayout(hbox(button("🧪 Загрузить временно", self.boot_recovery, "accent"),
                          button("💾 Прошить в recovery", self.flash_recovery),
                          button("💾 В vendor_boot", self.flash_vendor_boot, tip="Для некоторых устройств с Android 13+"),
                          None))
        cl.addLayout(hbox(button("🛠 Перезагрузить в recovery", lambda: self.app.reboot("recovery")),
                          button("📦 ADB Sideload", lambda: (self.app.show_page(self.app.page_flash),
                                                           self.app.page_flash.tabs.setCurrentIndex(3))),
                          button("🌐 TWRP", lambda: QDesktopServices.openUrl(QUrl("https://twrp.me/Devices/"))),
                          button("🌐 OrangeFox", lambda: QDesktopServices.openUrl(QUrl("https://orangefox.download/"))),
                          None))
        lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _rec_path(self) -> str | None:
        p = self.rec_img.path()
        if not Path(p).is_file():
            self.app.notify("Выберите образ recovery", "warn")
            return None
        return p

    def boot_recovery(self) -> None:
        p = self._rec_path()
        if p:
            self._fastboot_jobs(["boot", p], labels=["Временная загрузка recovery"])

    def flash_recovery(self) -> None:
        p = self._rec_path()
        if p:
            self._fastboot_jobs(["flash", "recovery", p], ["reboot", "recovery"], labels=["Прошивка recovery", ""],
                                confirm="Прошить образ в раздел recovery?")

    def flash_vendor_boot(self) -> None:
        p = self._rec_path()
        if p:
            self._fastboot_jobs(["flash", "vendor_boot", p], labels=["Прошивка vendor_boot"],
                                confirm="Прошивать recovery в vendor_boot можно ТОЛЬКО если так указано в инструкции для "
                                        "вашего устройства. Продолжить?")

    # ============================================================ settings / apps
    def _tab_settings(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)
        c1, l1 = card("⚙ Бэкап настроек Android",
                      "Сохраняет базы settings (system / secure / global) в JSON — после сброса или на новом телефоне "
                      "можно вернуть яркость, анимации, DNS, тайм‑ауты и многое другое.")
        self.ns_boxes = {ns: QCheckBox(ns) for ns in ("system", "secure", "global")}
        for b in self.ns_boxes.values():
            b.setChecked(True)
        l1.addLayout(hbox(*self.ns_boxes.values(), None,
                          button("💾 Сохранить в файл", self.backup_settings, "accent"),
                          button("♻ Восстановить из файла", self.restore_settings)))
        l1.addWidget(label(f"При восстановлении пропускаются ключи, привязанные к устройству ({len(SKIP_KEYS)} шт.: android_id, "
                           "Bluetooth‑адрес, отладка, способы ввода…).", "muted", wrap=True))
        lay.addWidget(c1)

        c2, l2 = card("📲 Восстановление приложений",
                      "Установит все APK из папки — например, из бэкапа «Инструменты → Резервные копии».")
        l2.addLayout(hbox(button("📂 Установить все APK из папки", self.restore_apps, "accent"),
                          button("♻ Вернуть удалённые системные", lambda: self.app.page_toolbox.show_tab(self.app.page_toolbox.debloat_tab)),
                          None))
        lay.addWidget(c2)
        lay.addStretch(1)
        return w

    def backup_settings(self) -> None:
        namespaces = [ns for ns, b in self.ns_boxes.items() if b.isChecked()]
        if not namespaces or not self.app.require_device(shell=True):
            return
        dev = self.app.device
        name = f"settings_{dev.serial.replace(':', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить настройки",
                                              str(Path(self.app.config.last_dir("backup")) / name), "JSON (*.json)")
        if not path:
            return
        self.app.config.remember_dir("backup", path)
        cmd = "; ".join(f"echo '@@{ns}'; settings list {ns}" for ns in namespaces)
        self.app.capture_adb(["shell", cmd], lambda c, out: self._save_settings(out, path, dev), timeout=30000)

    def _save_settings(self, out: str, path: str, dev) -> None:
        data: dict[str, dict[str, str]] = {}
        ns = None
        for line in out.splitlines():
            if line.startswith("@@"):
                ns = line[2:].strip()
                data[ns] = {}
            elif ns and "=" in line:
                k, _, v = line.partition("=")
                data[ns][k.strip()] = v.strip()
        payload = {"droidforge": 1, "device": dev.title, "date": time.strftime("%Y-%m-%d %H:%M"), "settings": data}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        total = sum(len(v) for v in data.values())
        self.app.notify(f"💾 Сохранено настроек: {total}", "ok")

    def restore_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Файл настроек", self.app.config.last_dir("backup"), "JSON (*.json)")
        if not path or not self.app.require_device(shell=True):
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            data = payload["settings"]
        except (OSError, ValueError, KeyError):
            self.app.notify("Это не файл настроек DroidForge", "error")
            return
        namespaces = [ns for ns, b in self.ns_boxes.items() if b.isChecked() and ns in data]
        items = [(ns, k, v) for ns in namespaces for k, v in data[ns].items() if k not in SKIP_KEYS and v != "null"]
        if not self.app.confirm("Восстановление настроек",
                                f"Из файла ({payload.get('device', '?')}, {payload.get('date', '')}) будет записано "
                                f"<b>{len(items)}</b> значений в {', '.join(namespaces)}. Продолжить?"):
            return
        jobs, chunk = [], []
        for ns, k, v in items:
            chunk.append(f"settings put {ns} {sh_quote(k)} {sh_quote(v)} 2>/dev/null")
            if len(chunk) >= 40:
                jobs.append(self.app.adb_job("shell", "; ".join(chunk) + "; true", label="Восстановление настроек"))
                chunk = []
        if chunk:
            jobs.append(self.app.adb_job("shell", "; ".join(chunk) + "; true", label="Восстановление настроек"))
        self.app.console.write(f"♻ Восстановление {len(items)} настроек пакетами по 40…", "info")
        self.app.run(jobs, stop_on_error=False)

    def restore_apps(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка с APK", self.app.config.last_dir("apk_out"))
        if not folder:
            return
        apks = sorted(str(p) for p in Path(folder).rglob("*.apk"))
        if not apks:
            self.app.notify("В папке нет APK", "warn")
            return
        if self.app.confirm("Восстановление приложений", f"Установить приложений: <b>{len(apks)}</b>?", danger=False):
            tab = self.app.page_adb.apk_tab
            tab.list.clear()
            tab.install_paths(apks)

