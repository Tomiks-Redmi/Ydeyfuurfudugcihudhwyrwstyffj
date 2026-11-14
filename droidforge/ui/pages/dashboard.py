"""Dashboard: device overview, key properties and reboot actions."""
from __future__ import annotations

import re
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QProgressBar,
    QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..widgets import button, card, hbox, label

ADB_FIELDS = [
    ("Производитель", "ro.product.manufacturer"),
    ("Модель", "ro.product.model"),
    ("Кодовое имя", "ro.product.device"),
    ("Android", "ro.build.version.release"),
    ("SDK / API", "ro.build.version.sdk"),
    ("Патч безопасности", "ro.build.version.security_patch"),
    ("Сборка", "ro.build.display.id"),
    ("Платформа", "ro.board.platform"),
    ("ABI", "ro.product.cpu.abi"),
    ("Слот A/B", "ro.boot.slot_suffix"),
    ("Verified boot", "ro.boot.verifiedbootstate"),
    ("Загрузчик", "ro.bootloader"),
    ("Baseband", "gsm.version.baseband"),
]
FB_FIELDS = [
    ("Продукт", "product"),
    ("Серийный номер", "serialno"),
    ("Разблокирован", "unlocked"),
    ("Secure", "secure"),
    ("Текущий слот", "current-slot"),
    ("Кол-во слотов", "slot-count"),
    ("Fastbootd", "is-userspace"),
    ("Загрузчик", "version-bootloader"),
    ("Baseband", "version-baseband"),
    ("Ревизия HW", "hw-revision"),
    ("Напряжение батареи", "battery-voltage"),
    ("Max download", "max-download-size"),
]
PROP_RE = re.compile(r"^\[(.+?)\]: \[(.*)\]$")


class DashboardPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.props: dict[str, str] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        # ---- hero
        hero, hl = card(name="hero")
        row = QHBoxLayout()
        row.setSpacing(18)
        self.icon = label("📱", "bigIcon")
        row.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title = label("Устройство не подключено", "h1")
        self.subtitle = label("Подключите телефон по USB и включите «Отладку по USB» в параметрах разработчика.", "muted", wrap=True)
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        row.addLayout(col, 1)
        self.battery = label("", "h2")
        row.addWidget(self.battery)
        row.addWidget(button("⟳ Обновить", self.refresh))
        row.addWidget(button("📄 Отчёт", self.export_report, tip="Сохранить всю информацию об устройстве в файл"))
        hl.addLayout(row)
        self.hint = label("", "hint", wrap=True)
        self.hint.hide()
        hl.addWidget(self.hint)
        lay.addWidget(hero)

        # ---- "tools missing" banner
        self.banner = QFrame(objectName="banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(14)
        bl.addWidget(label("🧰", "h2"))
        btxt = QVBoxLayout()
        btxt.setSpacing(2)
        btxt.addWidget(label("adb / fastboot не найдены", "cardTitle"))
        btxt.addWidget(label("Скачайте официальные platform-tools от Google — это займёт несколько секунд.", "muted", wrap=True))
        bl.addLayout(btxt, 1)
        bl.addWidget(button("⬇ Скачать platform-tools", lambda: (app.show_page(app.page_settings),
                                                               app.page_settings.download()), "accent"))
        bl.addWidget(button("Указать путь…", lambda: app.show_page(app.page_settings)))
        self.banner.hide()
        lay.addWidget(self.banner)

        # ---- live monitor
        mon, ml = card()
        head = QHBoxLayout()
        head.addWidget(label("📈 Живой мониторинг", "cardTitle"))
        head.addStretch(1)
        self.mon_btn = button("▶ Включить", self.toggle_monitor)
        head.addWidget(self.mon_btn)
        ml.addLayout(head)
        mg = QGridLayout()
        mg.setHorizontalSpacing(14)
        mg.setVerticalSpacing(8)
        self.meters: dict[str, tuple[QProgressBar, QLabel]] = {}
        for i, (key, name) in enumerate([("ram", "🧠 ОЗУ"), ("data", "💾 Память /data"),
                                         ("cpu", "⚙ Нагрузка CPU"), ("temp", "🌡 Батарея")]):
            bar = QProgressBar()
            bar.setTextVisible(False)
            val = label("—", "value")
            val.setMinimumWidth(150)
            r, c = divmod(i, 2)
            mg.addWidget(label(name, "muted"), r, c * 3)
            mg.addWidget(bar, r, c * 3 + 1)
            mg.addWidget(val, r, c * 3 + 2)
            self.meters[key] = (bar, val)
        mg.setColumnStretch(1, 1)
        mg.setColumnStretch(4, 1)
        ml.addLayout(mg)
        lay.addWidget(mon)
        self.mon_timer = QTimer(self)
        self.mon_timer.setInterval(2500)
        self.mon_timer.timeout.connect(self._poll_monitor)
        self._mon_busy = False

        # ---- info + actions
        mid = QHBoxLayout()
        mid.setSpacing(16)
        info_card, il = card("📋 Информация")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(8)
        il.addLayout(self.grid)
        il.addStretch(1)
        mid.addWidget(info_card, 3)

        act_card, al = card("⏻ Управление питанием", "Работает и из ADB, и из Fastboot.")
        g = QGridLayout()
        g.setSpacing(8)
        actions = [
            ("📱 Система", "system"), ("🛠 Recovery", "recovery"),
            ("⚡ Bootloader", "bootloader"), ("🧩 Fastbootd", "fastbootd"),
            ("📦 Sideload", "sideload"), ("⏻ Выключить", "poweroff"),
        ]
        for i, (text, key) in enumerate(actions):
            g.addWidget(button(text, lambda k=key: app.reboot(k)), i // 2, i % 2)
        al.addLayout(g)
        al.addSpacing(6)
        al.addWidget(label("Быстрые действия", "cardTitle"))
        al.addLayout(hbox(
            button("📸 Скриншот", self._screenshot),
            button("🔋 Батарея", lambda: app.require_device(shell=True) and app.run_adb("shell", "dumpsys", "battery")),
        ))
        al.addLayout(hbox(
            button("💾 Память", lambda: app.require_device(shell=True) and app.run_adb("shell", "df", "-h")),
            button("🔍 getvar all", lambda: app.require_device(fastboot=True) and app.run_fb("getvar", "all")),
        ))
        al.addStretch(1)
        mid.addWidget(act_card, 2)
        lay.addLayout(mid)

        # ---- all properties
        props_card, pl = card("🧬 Все свойства")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("🔎 Фильтр свойств…")
        self.filter.textChanged.connect(self._apply_filter)
        pl.addWidget(self.filter)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Свойство", "Значение"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(280)
        pl.addWidget(self.table)
        lay.addWidget(props_card)

        app.deviceChanged.connect(self.on_device)
        self._fill_grid([])

    # --------------------------------------------------------------
    def on_device(self, dev) -> None:
        self.props = {}
        self.table.setRowCount(0)
        self.battery.setText("")
        self.hint.hide()
        if dev is None:
            self.icon.setText("📱")
            self.title.setText("Устройство не подключено")
            self.subtitle.setText("Подключите телефон по USB и включите «Отладку по USB» в параметрах разработчика.")
            self._fill_grid([])
            return
        self.icon.setText("⚡" if dev.is_fastboot else "🛠" if dev.mode == "recovery" else "📱")
        self.title.setText(dev.model.replace("_", " ") or dev.product or "Android устройство")
        self.subtitle.setText(f"{dev.serial}   ·   режим: {dev.mode_name}   ·   {'Wi‑Fi' if dev.transport == 'wifi' else 'USB'}")
        if dev.mode == "unauthorized":
            self._show_hint("🔐 Разблокируйте телефон и подтвердите запрос «Разрешить отладку по USB?». "
                            "Отметьте «Всегда разрешать с этого компьютера».")
        elif dev.mode == "offline":
            self._show_hint("Устройство offline — переподключите кабель или перезапустите ADB сервер (Быстрые команды).")
        elif dev.mode == "no permissions":
            self._show_hint("Нет прав на USB устройство. Linux: добавьте udev правила (пакет android-sdk-platform-tools-common).")
        elif dev.mode == "sideload":
            self._show_hint("Режим sideload — перейдите на вкладку «Прошивка → Sideload / ZIP».")
        self.refresh()

    # ---------------------------------------------------------- monitor
    def toggle_monitor(self) -> None:
        if self.mon_timer.isActive():
            self.mon_timer.stop()
            self.mon_btn.setText("▶ Включить")
            return
        if not self.app.require_device(shell=True):
            return
        self.mon_timer.start()
        self.mon_btn.setText("⏸ Выключить")
        self._poll_monitor()

    def _poll_monitor(self) -> None:
        dev = self.app.device
        if not dev or not dev.has_shell:
            self.toggle_monitor()
            return
        if self._mon_busy or not self.isVisible():
            return
        self._mon_busy = True
        cmd = ("cat /proc/meminfo; echo @@; df /data | tail -n 1; echo @@; cat /proc/loadavg; "
               "echo @@; grep -c ^processor /proc/cpuinfo; echo @@; dumpsys battery | grep -E 'level|temperature'")
        self.app.capture_adb(["shell", cmd], self._on_monitor, timeout=8000)

    def _on_monitor(self, code: int, out: str) -> None:
        self._mon_busy = False
        parts = out.split("@@")
        if code != 0 or len(parts) < 5:
            return
        mem = dict(re.findall(r"^(\w+):\s+(\d+)", parts[0], re.M))
        total, avail = int(mem.get("MemTotal", 0)), int(mem.get("MemAvailable", 0))
        if total:
            used = total - avail
            self._meter("ram", used / total, f"{used / 1048576:.1f} / {total / 1048576:.1f} ГБ")
        df = parts[1].split()
        if len(df) >= 4 and df[1].isdigit() and df[2].isdigit():
            size, used = int(df[1]), int(df[2])
            self._meter("data", used / size if size else 0, f"{used / 1048576:.1f} / {size / 1048576:.1f} ГБ")
        try:
            load = float(parts[2].split()[0])
            cores = max(1, int(parts[3].strip() or 1))
            self._meter("cpu", min(1.0, load / cores), f"{load:.2f}  ({cores} ядер)")
        except (ValueError, IndexError):
            pass
        temp = re.search(r"temperature:\s*(\d+)", parts[4])
        level = re.search(r"level:\s*(\d+)", parts[4])
        if temp:
            t = int(temp.group(1)) / 10
            self._meter("temp", min(1.0, t / 50), f"{t:.1f}°C" + (f"  ·  {level.group(1)}%" if level else ""),
                        warn=t >= 42)

    def _meter(self, key: str, frac: float, text: str, warn: bool | None = None) -> None:
        bar, val = self.meters[key]
        bar.setMaximum(1000)
        bar.setValue(int(frac * 1000))
        val.setText(text)
        hot = frac > 0.9 if warn is None else warn
        bar.setStyleSheet("QProgressBar::chunk { background: #ff4d6d; }" if hot else "")

    def export_report(self) -> None:
        dev = self.app.device
        if not dev or not self.props:
            self.app.notify("Нет данных об устройстве", "warn")
            return
        name = f"device_{dev.serial}_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт",
                                              str(Path(self.app.config.last_dir("reports")) / name), "Текст (*.txt)")
        if not path:
            return
        self.app.config.remember_dir("reports", path)
        lines = [f"DroidForge — отчёт об устройстве ({time.strftime('%Y-%m-%d %H:%M')})",
                 f"Устройство: {self.title.text()}", f"Серийный номер: {dev.serial}", f"Режим: {dev.mode_name}",
                 f"Батарея: {self.battery.text() or '—'}", "", "=" * 60]
        lines += [f"{k} = {v}" for k, v in sorted(self.props.items())]
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        self.app.notify("📄 Отчёт сохранён", "ok")

    def set_tools_ok(self, ok: bool) -> None:
        self.banner.setVisible(not ok)

    def _show_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.show()

    def refresh(self) -> None:
        dev = self.app.device
        if dev is None:
            return
        if dev.has_shell:
            self.app.capture_adb(["shell", "getprop"], self._on_getprop)
            self.app.capture_adb(["shell", "dumpsys", "battery"], self._on_battery)
        elif dev.is_fastboot:
            self.app.capture_fb(["getvar", "all"], self._on_getvar, timeout=15000)

    def _on_getprop(self, code: int, out: str) -> None:
        props = {}
        for line in out.splitlines():
            m = PROP_RE.match(line.strip())
            if m:
                props[m.group(1)] = m.group(2)
        self._set_props(props, ADB_FIELDS)
        if props.get("ro.product.model"):
            brand = props.get("ro.product.brand", "").capitalize()
            self.title.setText(f"{brand} {props['ro.product.model']}".strip())

    def _on_getvar(self, code: int, out: str) -> None:
        props = {}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("(bootloader)"):
                line = line[len("(bootloader)"):].strip()
            key, sep, value = line.partition(": ")
            if sep and key and " " not in key and key != "all":
                props[key] = value.strip()
        self._set_props(props, FB_FIELDS)
        if props.get("product"):
            self.title.setText(f"{props['product']} (Fastboot)")
        if props.get("unlocked") == "no":
            self._show_hint("🔒 Загрузчик заблокирован — прошивка разделов невозможна. "
                            "Разблокировка: «Прошивка → Загрузчик» (сотрёт все данные).")

    def _on_battery(self, code: int, out: str) -> None:
        level = re.search(r"level:\s*(\d+)", out)
        temp = re.search(r"temperature:\s*(\d+)", out)
        charging = re.search(r"status:\s*2\b", out)
        if level:
            txt = f"{'⚡' if charging else '🔋'} {level.group(1)}%"
            if temp:
                txt += f"  ·  {int(temp.group(1)) / 10:.1f}°C"
            self.battery.setText(txt)
            self.app.set_battery(txt.split("  ·  ")[0])

    def _set_props(self, props: dict[str, str], fields) -> None:
        self.props = props
        rows = [(name, props.get(key, "")) for name, key in fields if props.get(key)]
        self._fill_grid(rows)
        self.table.setRowCount(len(props))
        for i, (k, v) in enumerate(sorted(props.items())):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(v))
        self._apply_filter(self.filter.text())

    def _fill_grid(self, rows) -> None:
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not rows:
            self.grid.addWidget(label("Нет данных", "muted"), 0, 0)
            return
        half = (len(rows) + 1) // 2
        for i, (name, value) in enumerate(rows):
            r, c = (i, 0) if i < half else (i - half, 2)
            self.grid.addWidget(label(name, "muted"), r, c)
            v = label(value, "value")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.grid.addWidget(v, r, c + 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(3, 1)

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        for r in range(self.table.rowCount()):
            k = self.table.item(r, 0).text().lower()
            v = self.table.item(r, 1).text().lower()
            self.table.setRowHidden(r, bool(text) and text not in k and text not in v)

    def _screenshot(self) -> None:
        page = self.app.page_adb
        self.app.show_page(page)
        page.tabs.setCurrentIndex(3)
        page.screen_tab.take_screenshot()
