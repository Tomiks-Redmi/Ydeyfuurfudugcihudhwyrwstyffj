"""More toolbox tabs: system tweaks + settings editor, diagnostics, scripts."""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QGridLayout, QHeaderView, QInputDialog, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..widgets import button, card, hbox, label
from .adb_tools import sh_quote


def _mono(widget: QWidget) -> None:
    f = QFont("JetBrains Mono, Cascadia Code, Consolas, DejaVu Sans Mono, monospace")
    f.setStyleHint(QFont.StyleHint.Monospace)
    widget.setFont(f)


# =========================================================================
class TweaksTab(QWidget):
    DNS = [("Выключен", ""), ("Автоматически", "opportunistic"),
           ("AdGuard (блок рекламы)", "dns.adguard-dns.com"), ("AdGuard Family", "family.adguard-dns.com"),
           ("Cloudflare", "one.one.one.one"), ("Cloudflare + защита", "security.cloudflare-dns.com"),
           ("Google", "dns.google"), ("Quad9", "dns.quad9.net"), ("Свой…", "custom")]
    TIMEOUTS = [("15 сек", 15), ("30 сек", 30), ("1 мин", 60), ("2 мин", 120), ("5 мин", 300),
                ("10 мин", 600), ("30 мин", 1800)]

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        grid = QGridLayout()
        grid.setSpacing(14)

        # display
        c1, l1 = card("🖼 Экран", "Изменения применяются мгновенно, «Сброс» возвращает заводские значения.")
        self.dpi = QSpinBox()
        self.dpi.setRange(120, 800)
        self.dpi.setValue(420)
        self.dpi.setSuffix(" dpi")
        l1.addLayout(hbox(label("Плотность:", "muted"), self.dpi, None,
                          button("Применить", lambda: self._sh(f"wm density {self.dpi.value()}")),
                          button("Сброс", lambda: self._sh("wm density reset"), "ghost")))
        self.res = QLineEdit()
        self.res.setPlaceholderText("1080x2400")
        self.res.setFixedWidth(130)
        l1.addLayout(hbox(label("Разрешение:", "muted"), self.res, None,
                          button("Применить", self._apply_res),
                          button("Сброс", lambda: self._sh("wm size reset"), "ghost")))
        self.hz = QComboBox()
        self.hz.addItems(["60", "90", "120", "144"])
        l1.addLayout(hbox(label("Частота обновления:", "muted"), self.hz, label("Гц", "muted"), None,
                          button("Применить", lambda: self._sh(
                              f"settings put system peak_refresh_rate {self.hz.currentText()}.0; "
                              f"settings put system min_refresh_rate {self.hz.currentText()}.0")),
                          button("Сброс", lambda: self._sh(
                              "settings delete system peak_refresh_rate; settings delete system min_refresh_rate"), "ghost")))
        self.timeout = QComboBox()
        for name, _ in self.TIMEOUTS:
            self.timeout.addItem(name)
        l1.addLayout(hbox(label("Тайм‑аут экрана:", "muted"), self.timeout, None,
                          button("Применить", lambda: self._sh(
                              f"settings put system screen_off_timeout {self.TIMEOUTS[self.timeout.currentIndex()][1] * 1000}"))))
        l1.addLayout(hbox(button("🔍 Прочитать текущие", self.read_current), None))
        grid.addWidget(c1, 0, 0)

        # interface
        c2, l2 = card("✨ Интерфейс")
        self.font_scale = QComboBox()
        self.font_scale.addItems(["0.85", "1.0", "1.15", "1.3", "1.5"])
        self.font_scale.setCurrentText("1.0")
        l2.addLayout(hbox(label("Масштаб шрифта:", "muted"), self.font_scale, None,
                          button("Применить", lambda: self._sh(f"settings put system font_scale {self.font_scale.currentText()}"))))
        self.anim = QComboBox()
        self.anim.addItems(["0 (выкл)", "0.5", "0.75", "1", "1.5"])
        self.anim.setCurrentText("0.5")
        l2.addLayout(hbox(label("Скорость анимаций:", "muted"), self.anim, None, button("Применить", self._apply_anim)))
        l2.addLayout(hbox(button("🌙 Тёмная тема", lambda: self._sh("cmd uimode night yes")),
                          button("☀ Светлая", lambda: self._sh("cmd uimode night no")), None))
        l2.addLayout(hbox(button("👆 Показ касаний", lambda: self._sh("settings put system show_touches 1")),
                          button("✖", lambda: self._sh("settings put system show_touches 0"), "ghost"),
                          button("📍 Координаты", lambda: self._sh("settings put system pointer_location 1")),
                          button("✖", lambda: self._sh("settings put system pointer_location 0"), "ghost"), None))
        l2.addLayout(hbox(button("🔋 Не гасить при зарядке", lambda: self._sh("svc power stayon usb")),
                          button("✖", lambda: self._sh("svc power stayon false"), "ghost"), None))
        grid.addWidget(c2, 0, 1)

        # network
        c3, l3 = card("🛡 Private DNS", "Шифрованный DNS для всего телефона. AdGuard режет рекламу и трекеры во всех приложениях.")
        self.dns = QComboBox()
        for name, _ in self.DNS:
            self.dns.addItem(name)
        self.dns.setCurrentIndex(2)
        l3.addLayout(hbox(self.dns, None, button("Применить", self._apply_dns, "accent"),
                          button("🔍 Текущий", lambda: self._sh("echo mode=$(settings get global private_dns_mode) "
                                                              "host=$(settings get global private_dns_specifier)"))))
        grid.addWidget(c3, 1, 0)

        c4, l4 = card("📶 Сеть и связь")
        net = QGridLayout()
        net.setSpacing(8)
        for i, (on_txt, off_txt, cmd_on, cmd_off) in enumerate([
            ("📶 Wi‑Fi вкл", "Wi‑Fi выкл", "svc wifi enable", "svc wifi disable"),
            ("📱 Моб. данные вкл", "Данные выкл", "svc data enable", "svc data disable"),
            ("✈ Авиарежим вкл", "Авиарежим выкл", "cmd connectivity airplane-mode enable", "cmd connectivity airplane-mode disable"),
            ("🔵 Bluetooth вкл", "Bluetooth выкл", "svc bluetooth enable", "svc bluetooth disable"),
        ]):
            net.addWidget(button(on_txt, lambda c=cmd_on: self._sh(c)), i, 0)
            net.addWidget(button(off_txt, lambda c=cmd_off: self._sh(c)), i, 1)
        l4.addLayout(net)
        grid.addWidget(c4, 1, 1)
        lay.addLayout(grid)

        # settings DB editor
        c5, l5 = card("🗄 Редактор настроек Android", "Прямое редактирование базы settings. Двойной клик по значению — изменить.")
        self.ns = QComboBox()
        self.ns.addItems(["system", "secure", "global"])
        self.ns.currentIndexChanged.connect(self.load_settings)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("🔎 Поиск ключа или значения…")
        self.filter.textChanged.connect(self._filter)
        row = hbox(self.ns, self.filter, button("⟳ Загрузить", self.load_settings),
                   button("➕ Добавить", self.add_setting), button("🗑 Удалить", self.delete_setting, "danger"))
        row.setStretch(1, 1)
        l5.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Ключ", "Значение"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(280)
        self.table.cellDoubleClicked.connect(self.edit_setting)
        l5.addWidget(self.table)
        lay.addWidget(c5)
        lay.addStretch(1)

    def _sh(self, cmd: str) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", cmd)])

    def _apply_res(self) -> None:
        txt = self.res.text().strip().lower().replace("×", "x")
        parts = txt.split("x")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            self.app.notify("Формат: ШИРИНАxВЫСОТА, например 1080x2400", "warn")
            return
        if self.app.confirm("Разрешение экрана", f"Установить {txt}? Если интерфейс станет неудобным — нажмите «Сброс»."):
            self._sh(f"wm size {txt}")

    def _apply_anim(self) -> None:
        v = self.anim.currentText().split()[0]
        self._sh("; ".join(f"settings put global {k} {v}" for k in
                           ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")))

    def _apply_dns(self) -> None:
        name, host = self.DNS[self.dns.currentIndex()]
        if host == "custom":
            host, ok = QInputDialog.getText(self, "Свой DNS", "Хост DNS‑over‑TLS (например dns.example.com):")
            if not ok or not host.strip():
                return
            host = host.strip()
        if not host:
            self._sh("settings put global private_dns_mode off")
        elif host == "opportunistic":
            self._sh("settings put global private_dns_mode opportunistic")
        else:
            self._sh(f"settings put global private_dns_mode hostname; settings put global private_dns_specifier {host}")
        self.app.notify(f"🛡 Private DNS: {name}", "ok")

    def read_current(self) -> None:
        if self.app.require_device(shell=True):
            self.app.capture_adb(["shell", "wm density; echo @@; wm size; echo @@; settings get system peak_refresh_rate; "
                                           "echo @@; settings get system font_scale"], self._on_current)

    def _on_current(self, code: int, out: str) -> None:
        parts = [p.strip() for p in out.split("@@")]
        if len(parts) < 4:
            return
        dens = [l.split(":")[-1].strip() for l in parts[0].splitlines() if ":" in l]
        if dens and dens[-1].isdigit():
            self.dpi.setValue(int(dens[-1]))
        sizes = [l.split(":")[-1].strip() for l in parts[1].splitlines() if ":" in l]
        if sizes:
            self.res.setText(sizes[-1])
        hz = parts[2].split(".")[0]
        if hz.isdigit():
            self.hz.setCurrentText(hz)
        if parts[3] not in ("null", ""):
            self.font_scale.setCurrentText(parts[3])
        self.app.notify(f"Плотность {self.dpi.value()} · {self.res.text()} · {parts[2]} Гц", "info")

    # ---------------------------------------------------- settings DB
    def load_settings(self) -> None:
        if self.app.require_device(shell=True):
            self.app.capture_adb(["shell", f"settings list {self.ns.currentText()}"], self._on_settings)

    def _on_settings(self, code: int, out: str) -> None:
        rows = []
        for line in out.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                rows.append((k.strip(), v.strip()))
        rows.sort()
        self.table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(k))
            self.table.setItem(r, 1, QTableWidgetItem(v))
        self._filter(self.filter.text())

    def _filter(self, text: str) -> None:
        text = text.lower()
        for r in range(self.table.rowCount()):
            k, v = self.table.item(r, 0).text().lower(), self.table.item(r, 1).text().lower()
            self.table.setRowHidden(r, bool(text) and text not in k and text not in v)

    def _put(self, key: str, value: str) -> None:
        ns = self.ns.currentText()
        self.app.run([self.app.adb_job("shell", f"settings put {ns} {sh_quote(key)} {sh_quote(value)}")])
        self.app.after_queue(self.load_settings)

    def edit_setting(self, row: int, _col: int) -> None:
        key, value = self.table.item(row, 0).text(), self.table.item(row, 1).text()
        new, ok = QInputDialog.getText(self, "Изменить настройку", f"{self.ns.currentText()} / {key}", text=value)
        if ok and new != value and self.app.require_device(shell=True):
            self._put(key, new)

    def add_setting(self) -> None:
        if not self.app.require_device(shell=True):
            return
        key, ok = QInputDialog.getText(self, "Новая настройка", "Ключ:")
        if not ok or not key.strip():
            return
        value, ok = QInputDialog.getText(self, "Новая настройка", f"Значение для {key.strip()}:")
        if ok:
            self._put(key.strip(), value)

    def delete_setting(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        if not rows or not self.app.require_device(shell=True):
            return
        keys = [self.table.item(r, 0).text() for r in rows]
        if not self.app.confirm("Удалить настройки", f"{self.ns.currentText()}: {', '.join(keys)}"):
            return
        ns = self.ns.currentText()
        self.app.run([self.app.adb_job("shell", f"settings delete {ns} {sh_quote(k)}") for k in keys])
        self.app.after_queue(self.load_settings)


# =========================================================================
HIDDEN = [
    ("🛠 Для разработчиков", "-a android.settings.APPLICATION_DEVELOPMENT_SETTINGS"),
    ("ℹ О телефоне", "-a android.settings.DEVICE_INFO_SETTINGS"),
    ("📶 Wi‑Fi", "-a android.settings.WIFI_SETTINGS"),
    ("🔵 Bluetooth", "-a android.settings.BLUETOOTH_SETTINGS"),
    ("🔋 Батарея", "-a android.intent.action.POWER_USAGE_SUMMARY"),
    ("💾 Хранилище", "-a android.settings.INTERNAL_STORAGE_SETTINGS"),
    ("🧩 Приложения", "-a android.settings.MANAGE_ALL_APPLICATIONS_SETTINGS"),
    ("♿ Спец. возможности", "-a android.settings.ACCESSIBILITY_SETTINGS"),
    ("🕒 Дата и время", "-a android.settings.DATE_SETTINGS"),
    ("🌐 Язык", "-a android.settings.LOCALE_SETTINGS"),
    ("📡 Тест сети (*#*#4636#*#*)", "-n com.android.phone/.settings.RadioInfo"),
    ("🔐 Безопасность", "-a android.settings.SECURITY_SETTINGS"),
]


class DiagnosticsTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.services: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        top = QGridLayout()
        top.setSpacing(14)
        c1, l1 = card("🩺 Отчёты и логи")
        l1.addLayout(hbox(button("🐞 Bugreport (zip)", self.bugreport, "accent",
                                 "Полный отчёт системы для разработчиков, занимает 1–3 минуты"),
                          button("💥 Журнал сбоев", lambda: self._run_view("logcat -b crash -d", "Журнал сбоев")),
                          None))
        l1.addLayout(hbox(button("⏱ Время работы", lambda: self._run_view("uptime", "Uptime")),
                          button("🌡 Температуры", lambda: self._run_view(
                              "for z in /sys/class/thermal/thermal_zone*; do echo \"$(cat $z/type 2>/dev/null): "
                              "$(( $(cat $z/temp 2>/dev/null || echo 0) / 1000 ))°C\"; done", "Температурные датчики")),
                          button("📦 Топ процессов", lambda: self._run_view("top -b -n 1 -m 25", "Процессы")), None))
        l1.addLayout(hbox(button("🔋 Здоровье батареи", self.battery_health),
                          button("💽 Что занимает место", lambda: self._run_view(
                              "echo '== /sdcard =='; du -sh /sdcard/* 2>/dev/null | sort -rh | head -25; "
                              "echo; echo '== Разделы =='; df -h /data /system 2>/dev/null", "Занятое место")),
                          button("🌐 Проверка сети", lambda: self._run_view(
                              "ping -c 4 -W 2 8.8.8.8 2>&1; echo; ping -c 2 -W 2 google.com 2>&1 | tail -3", "Проверка интернета")),
                          None))
        top.addWidget(c1, 0, 0)

        c2, l2 = card("🔗 Открыть на телефоне")
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://… или tel:+7…, market://…, geo:55.75,37.61")
        self.url.returnPressed.connect(self.open_url)
        l2.addLayout(hbox(self.url, button("↗ Открыть", self.open_url, "accent")))
        menu_row = QGridLayout()
        menu_row.setSpacing(6)
        for i, (name, intent) in enumerate(HIDDEN):
            menu_row.addWidget(button(name, lambda it=intent: self._start(it)), i // 4, i % 4)
        l2.addLayout(menu_row)
        top.addWidget(c2, 0, 1)
        top.setColumnStretch(1, 2)
        lay.addLayout(top)

        c3, l3 = card("🔬 Обозреватель dumpsys", "Состояние любого системного сервиса: battery, wifi, meminfo, activity…")
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.svc_filter = QLineEdit()
        self.svc_filter.setPlaceholderText("🔎 сервис…")
        self.svc_filter.textChanged.connect(self._filter_services)
        self.svc_list = QListWidget()
        self.svc_list.itemClicked.connect(lambda it: self._dumpsys(it.text()))
        ll.addLayout(hbox(self.svc_filter, button("⟳", self.load_services, tip="Загрузить список сервисов")))
        ll.addWidget(self.svc_list, 1)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.view_title = label("Выберите сервис или действие выше", "cardTitle")
        self.find = QLineEdit()
        self.find.setPlaceholderText("Найти в тексте (Enter — следующее)")
        self.find.returnPressed.connect(self._find_next)
        self.find.setFixedWidth(260)
        rl.addLayout(hbox(self.view_title, None, self.find, button("💾", self.save_view, "ghost", "Сохранить в файл"),
                          button("📋", lambda: self.app.clipboard_set(self.view.toPlainText()), "ghost", "Копировать")))
        self.view = QPlainTextEdit()
        self.view.setObjectName("logcat")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        rl.addWidget(self.view, 1)
        split.addWidget(right)
        split.setSizes([220, 700])
        split.setMinimumHeight(340)
        l3.addWidget(split, 1)
        lay.addWidget(c3, 1)

    def battery_health(self) -> None:
        cmd = ("dumpsys battery; echo @@; B=/sys/class/power_supply/battery; "
               "for f in cycle_count charge_full charge_full_design health voltage_now current_now temp; do "
               "[ -r $B/$f ] && echo \"$f=$(cat $B/$f)\"; done")
        if self.app.require_device(shell=True):
            self.view_title.setText("⏳ Батарея…")
            self.app.capture_adb(["shell", cmd], self._on_battery)

    def _on_battery(self, code: int, out: str) -> None:
        dump, _, sysfs = out.partition("@@")
        vals = dict(l.strip().split("=", 1) for l in sysfs.splitlines() if "=" in l)
        lines = ["🔋 СОСТОЯНИЕ БАТАРЕИ", ""]
        try:
            full, design = int(vals.get("charge_full", 0)), int(vals.get("charge_full_design", 0))
            if full and design:
                pct = full / design * 100
                verdict = "отличное" if pct >= 90 else "хорошее" if pct >= 80 else "среднее" if pct >= 70 else "пора менять"
                lines.append(f"Здоровье (ёмкость):  {pct:.0f}%  — {verdict}")
                lines.append(f"Текущая ёмкость:     {full // 1000} мА·ч из {design // 1000} мА·ч")
        except ValueError:
            pass
        if vals.get("cycle_count"):
            lines.append(f"Циклов зарядки:      {vals['cycle_count']}")
        if vals.get("health"):
            lines.append(f"Статус (ядро):       {vals['health']}")
        if not vals:
            lines.append("Подробные данные (sysfs) недоступны без root на этом устройстве.")
        lines += ["", "─" * 50, dump.strip()]
        self._show("Здоровье батареи", "\n".join(lines))

    def _start(self, intent: str) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", f"am start {intent}")])

    def open_url(self) -> None:
        url = self.url.text().strip()
        if not url:
            return
        if "://" not in url and ":" not in url:
            url = "https://" + url
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", f"am start -a android.intent.action.VIEW -d {sh_quote(url)}")])

    def bugreport(self) -> None:
        if not self.app.require_device(adb=True):
            return
        folder = QFileDialog.getExistingDirectory(self, "Куда сохранить bugreport", self.app.config.last_dir("reports"))
        if folder:
            self.app.config.remember_dir("reports", folder)
            self.app.notify("🐞 Bugreport собирается 1–3 минуты…", "info")
            self.app.run([self.app.adb_job("bugreport", folder, label="Сбор bugreport")])

    def _run_view(self, cmd: str, title: str) -> None:
        if not self.app.require_device(shell=True):
            return
        self.view_title.setText(f"⏳ {title}…")
        self.app.capture_adb(["shell", cmd], lambda c, out: self._show(title, out), timeout=60000)

    def _show(self, title: str, text: str) -> None:
        self.view_title.setText(title)
        self.view.setPlainText(text)

    def load_services(self) -> None:
        if self.app.require_device(shell=True):
            self.app.capture_adb(["shell", "dumpsys -l"], self._on_services)

    def _on_services(self, code: int, out: str) -> None:
        self.services = sorted(l.strip() for l in out.splitlines()[1:] if l.strip() and " " not in l.strip())
        self.svc_list.clear()
        self.svc_list.addItems(self.services)
        self._filter_services(self.svc_filter.text())

    def _filter_services(self, text: str) -> None:
        for i in range(self.svc_list.count()):
            it = self.svc_list.item(i)
            it.setHidden(bool(text) and text.lower() not in it.text().lower())

    def _dumpsys(self, svc: str) -> None:
        self._run_view(f"dumpsys {svc}", f"dumpsys {svc}")

    def _find_next(self) -> None:
        text = self.find.text()
        if text and not self.view.find(text):
            cursor = self.view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.view.setTextCursor(cursor)
            if not self.view.find(text):
                self.app.notify("Не найдено", "warn")

    def save_view(self) -> None:
        if not self.view.toPlainText():
            return
        name = self.view_title.text().replace(" ", "_").replace("/", "_")[:40] + f"_{time.strftime('%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить", str(Path(self.app.config.last_dir("reports")) / name),
                                              "Текст (*.txt)")
        if path:
            Path(path).write_text(self.view.toPlainText(), encoding="utf-8")
            self.app.notify("💾 Сохранено", "ok")


# =========================================================================
EXAMPLES = [
    {"name": "Пример: подготовка к прошивке", "body":
        "# Проверка устройства и переход в загрузчик\n"
        "echo Проверяю устройство…\n"
        "adb shell getprop ro.product.model\n"
        "adb shell getprop ro.build.display.id\n"
        "adb reboot bootloader\n"
        "sleep 8\n"
        "fastboot getvar unlocked\n"
        "fastboot getvar current-slot\n"},
    {"name": "Пример: быстрый интерфейс", "body":
        "# Анимации 0.5x, тёмная тема, касания\n"
        "adb shell settings put global window_animation_scale 0.5\n"
        "adb shell settings put global transition_animation_scale 0.5\n"
        "adb shell settings put global animator_duration_scale 0.5\n"
        "adb shell cmd uimode night yes\n"
        "echo Готово ✨\n"},
]


class ScriptsTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        if not app.config.get("scripts"):
            app.config.set("scripts", list(EXAMPLES))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Сценарии из нескольких команд: по одной на строку, <code># комментарий</code>, "
                            "<code>sleep 5</code> — пауза, <code>echo текст</code> — сообщение. "
                            "Можно запускать сразу на всех подключённых устройствах.", "muted", wrap=True))
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        ll.addWidget(self.list, 1)
        ll.addLayout(hbox(button("➕ Новый", self.new), button("🗑", self.delete, "danger", "Удалить")))
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Название сценария")
        rl.addWidget(self.name)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("console")
        self.editor.setPlaceholderText("adb shell getprop ro.product.model\nsleep 2\nadb reboot bootloader")
        self.editor.setTabStopDistance(28)
        _mono(self.editor)
        rl.addWidget(self.editor, 1)
        rl.addLayout(hbox(button("💾 Сохранить", self.save), button("📂 Импорт", self.import_file, "ghost"),
                          button("📤 Экспорт", self.export_file, "ghost"), None,
                          button("📡 На всех устройствах", lambda: self.run(True)),
                          button("▶ Запустить", lambda: self.run(False), "accent")))
        split.addWidget(right)
        split.setSizes([240, 700])
        lay.addWidget(split, 1)
        self._reload()

    def _scripts(self) -> list[dict]:
        return list(self.app.config.get("scripts", []))

    def _reload(self, select: int = 0) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for sc in self._scripts():
            self.list.addItem(QListWidgetItem(f"📜  {sc['name']}"))
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(min(select, self.list.count() - 1))
            self._select(self.list.currentRow())

    def _select(self, row: int) -> None:
        scripts = self._scripts()
        if 0 <= row < len(scripts):
            self.name.setText(scripts[row]["name"])
            self.editor.setPlainText(scripts[row]["body"])

    def new(self) -> None:
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.name.setText("Новый сценарий")
        self.editor.setPlainText("# Мой сценарий\n")
        self.editor.setFocus()

    def save(self) -> None:
        name = self.name.text().strip() or "Без названия"
        scripts = self._scripts()
        row = self.list.currentRow()
        entry = {"name": name, "body": self.editor.toPlainText()}
        if 0 <= row < len(scripts):
            scripts[row] = entry
        else:
            scripts.append(entry)
            row = len(scripts) - 1
        self.app.config.set("scripts", scripts)
        self._reload(row)
        self.app.notify("💾 Сценарий сохранён", "ok")

    def delete(self) -> None:
        row = self.list.currentRow()
        scripts = self._scripts()
        if 0 <= row < len(scripts) and self.app.confirm("Удалить сценарий", scripts[row]["name"], danger=False):
            del scripts[row]
            self.app.config.set("scripts", scripts)
            self._reload(max(0, row - 1))

    def run(self, broadcast: bool) -> None:
        body = self.editor.toPlainText()
        try:
            jobs = self.app.broadcast_jobs(body, script=True) if broadcast else self.app.parse_script(body)
        except ValueError as exc:
            self.app.console.write(f"✖ Ошибка в сценарии, {exc}", "fail")
            return
        if not jobs:
            self.app.notify("Нечего выполнять" if not broadcast else "Нет подходящих устройств", "warn")
            return
        self.app.console.write(f"📜 Сценарий «{self.name.text()}» — команд: {len(jobs)}", "info")
        self.app.run(jobs, stop_on_error=not broadcast and bool(self.app.config.get("stop_on_error")))

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт сценария", self.app.config.last_dir("scripts"),
                                              "Сценарии (*.txt *.sh *.bat *.cmd);;Все файлы (*)")
        if path:
            self.app.config.remember_dir("scripts", path)
            self.list.setCurrentRow(-1)
            self.name.setText(Path(path).stem)
            self.editor.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace"))

    def export_file(self) -> None:
        name = (self.name.text().strip() or "script") + ".txt"
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт сценария", str(Path(self.app.config.last_dir("scripts")) / name),
                                              "Текст (*.txt)")
        if path:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
            self.app.notify("📤 Экспортировано", "ok")

