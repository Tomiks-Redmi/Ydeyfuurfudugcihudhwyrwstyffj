"""Main window: navigation, device selector, console and shared helpers for pages."""
from __future__ import annotations

import sys
import time

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut, QColor, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QStackedWidget, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget,
)

from . import __app_name__, __version__
from .core.commands import NO_SERIAL, all_completions, split_command
from .core.config import Config
from .core.devices import Device, DeviceMonitor
from .core.logfile import SessionLog
from .core.runner import ECHO, SLEEP, CommandRunner, Job, capture
from .core.tools import Tools
from .ui import theme
from .ui.console import Console
from .ui.palette import CommandPalette, PaletteItem
from .ui.widgets import Toast, button, fade_in, label

REBOOT_TARGETS = [
    ("system", "📱  В систему"),
    ("recovery", "🛠  В Recovery"),
    ("bootloader", "⚡  В Bootloader"),
    ("fastbootd", "🧩  В Fastbootd"),
    ("sideload", "📦  В Sideload"),
    ("edl", "🚨  В EDL (Qualcomm)"),
    ("poweroff", "⏻  Выключить"),
]


class MainWindow(QMainWindow):
    deviceChanged = pyqtSignal(object)      # Device | None
    devicesUpdated = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.tools = Tools(self.config)
        self.runner = CommandRunner(self)
        self.monitor = DeviceMonitor(self.tools, self.config.get("poll_interval"), self)
        self.device: Device | None = None
        self.devices: list[Device] = []
        self._after: list = []
        self.session_log = SessionLog()
        self._battery = ""
        self.apply_theme()
        self._queue_t0 = 0.0

        self.setWindowTitle(f"{__app_name__} — ADB & Fastboot Studio")
        self.setWindowIcon(make_icon())
        self.resize(1360, 900)
        self.setMinimumSize(1040, 680)

        self._build_ui()
        self._wire()
        self._shortcuts()

        self.console.write(f"⚡ {__app_name__} {__version__} — добро пожаловать!", "info")
        self._report_tools()
        self.monitor.devicesChanged.connect(self._on_devices)
        self.monitor.start()

    # ================================================================ UI
    def _build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        # ---- content
        content = QWidget(objectName="content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.console = Console(self.config.get("history"), all_completions())
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.console)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([680, 200])
        self.splitter.setChildrenCollapsible(False)
        self._console_h = 200
        cl.addWidget(self.splitter, 1)
        outer.addWidget(content, 1)

        from .ui.pages.adb_tools import AdbToolsPage
        from .ui.pages.dashboard import DashboardPage
        from .ui.pages.flash import FlashPage
        from .ui.pages.logcat import LogcatPage
        from .ui.pages.quick import QuickPage
        from .ui.pages.settings import SettingsPage
        from .ui.pages.toolbox import ToolboxPage

        self.page_dashboard = DashboardPage(self)
        self.page_flash = FlashPage(self)
        self.page_adb = AdbToolsPage(self)
        self.page_toolbox = ToolboxPage(self)
        self.page_quick = QuickPage(self)
        self.page_logcat = LogcatPage(self)
        self.page_settings = SettingsPage(self)
        sections = [
            ("ГЛАВНОЕ", [("🏠", "Обзор", self.page_dashboard), ("⚡", "Прошивка", self.page_flash)]),
            ("УСТРОЙСТВО", [("📱", "ADB инструменты", self.page_adb), ("🧰", "Инструменты", self.page_toolbox),
                            ("📜", "Logcat", self.page_logcat)]),
            ("ЕЩЁ", [("🚀", "Быстрые команды", self.page_quick), ("⚙️", "Настройки", self.page_settings)]),
        ]
        self.pages = []
        for section, items in sections:
            head = QListWidgetItem(section)
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            self.nav.addItem(head)
            for icon, name, page in items:
                idx = self.stack.addWidget(page)
                self.pages.append((icon, name, page))
                item = QListWidgetItem(f"  {icon}   {name}")
                item.setData(Qt.ItemDataRole.UserRole, idx)
                item.setData(Qt.ItemDataRole.UserRole + 1, (icon, name))
                item.setToolTip(f"{name}  (Ctrl+{len(self.pages)})")
                self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._on_nav)
        self.nav.setCurrentRow(1)

        self.toast = Toast(self)
        self.palette = CommandPalette(self, self._palette_items)
        self.setAcceptDrops(True)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip(__app_name__)
            self.tray.activated.connect(lambda _r: (self.showNormal(), self.activateWindow()))
            self.tray.show()
        self.console.toggleRequested.connect(lambda: self.set_console_collapsed(not self.console.collapsed))
        if self.config.get("console_collapsed", False):
            self.set_console_collapsed(True)
        if self.config.get("sidebar_collapsed", False):
            self.set_sidebar_collapsed(True)
        self._refresh_theme_widgets()

    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame(objectName="sidebar")
        self.sidebar.setFixedWidth(236)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(12, 16, 12, 12)
        sl.setSpacing(6)
        self.logo = QLabel(objectName="logo")
        sl.addWidget(self.logo)
        self.version_lbl = label(f"ADB & Fastboot Studio · v{__version__}", "version")
        sl.addWidget(self.version_lbl)
        sl.addSpacing(8)
        self.nav = QListWidget(objectName="nav")
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sl.addWidget(self.nav, 1)

        self.devcard = QFrame(objectName="devcard")
        dl = QVBoxLayout(self.devcard)
        dl.setContentsMargins(12, 10, 12, 10)
        dl.setSpacing(2)
        self.dev_name = label("Нет устройства", "devName")
        self.dev_meta = label("Подключите телефон по USB", "devMeta", wrap=True)
        self.tools_label = label("", "devMeta")
        dl.addWidget(self.dev_name)
        dl.addWidget(self.dev_meta)
        dl.addWidget(self.tools_label)
        sl.addWidget(self.devcard)
        self.collapse_btn = button("«  Свернуть", lambda: self.set_sidebar_collapsed(not self._sidebar_collapsed),
                                   "ghost", "Свернуть / развернуть меню (Ctrl+B)")
        sl.addWidget(self.collapse_btn)
        self._sidebar_collapsed = False
        return self.sidebar

    def _build_header(self) -> QFrame:
        header = QFrame(objectName="header")
        header.setFixedHeight(62)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 10, 18, 10)
        hl.setSpacing(8)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(300)
        self.device_combo.setToolTip("Выбранное устройство")
        self.device_combo.currentIndexChanged.connect(self._on_combo)
        hl.addWidget(self.device_combo)
        self.badge = QLabel("—", objectName="badge")
        hl.addWidget(self.badge)
        hl.addWidget(button("⟳", lambda: self.monitor.poll(force=True), "icon", "Обновить список устройств (F5)"))
        hl.addStretch(1)
        search = QPushButton("🔎   Поиск команд и действий…            Ctrl+K", objectName="search")
        search.setCursor(Qt.CursorShape.PointingHandCursor)
        search.clicked.connect(self.palette_open)
        hl.addWidget(search)
        hl.addStretch(1)
        self.theme_btn = button("🌙", self.toggle_theme, "icon", "Светлая / тёмная тема (Ctrl+T)")
        hl.addWidget(self.theme_btn)

        reboot = QToolButton()
        reboot.setText("⏻  Перезагрузка  ▾")
        reboot.setCursor(Qt.CursorShape.PointingHandCursor)
        reboot.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(reboot)
        for key, text in REBOOT_TARGETS:
            act = QAction(text, menu)
            act.triggered.connect(lambda _=False, k=key: self.reboot(k))
            menu.addAction(act)
        reboot.setMenu(menu)
        hl.addWidget(reboot)
        return header

    # ------------------------------------------------------- layout state
    def _on_nav(self, item, _prev=None) -> None:
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx != self.stack.currentIndex():
            self.stack.setCurrentIndex(idx)
            fade_in(self.stack.currentWidget(), 180)

    def show_page(self, page: QWidget) -> None:
        idx = self.stack.indexOf(page)
        for row in range(self.nav.count()):
            if self.nav.item(row).data(Qt.ItemDataRole.UserRole) == idx:
                self.nav.setCurrentRow(row)
                return

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(78 if collapsed else 236)
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            meta = item.data(Qt.ItemDataRole.UserRole + 1)
            if meta is None:
                item.setHidden(collapsed)
            else:
                item.setText(f" {meta[0]}" if collapsed else f"  {meta[0]}   {meta[1]}")
        self.version_lbl.setVisible(not collapsed)
        self.devcard.setVisible(not collapsed)
        self.collapse_btn.setText("»" if collapsed else "«  Свернуть")
        self._refresh_theme_widgets()
        self.config.set("sidebar_collapsed", collapsed)

    def set_console_collapsed(self, collapsed: bool) -> None:
        if collapsed == self.console.collapsed:
            return
        if collapsed:
            h = self.splitter.sizes()[1]
            if h > 90:
                self._console_h = h
            self.console.set_collapsed(True)
            self.console.setMaximumHeight(58)
            total = sum(self.splitter.sizes())
            self.splitter.setSizes([total - 58, 58])
        else:
            self.console.set_collapsed(False)
            self.console.setMaximumHeight(16777215)
            total = sum(self.splitter.sizes())
            self.splitter.setSizes([max(200, total - self._console_h), self._console_h])
        self.config.set("console_collapsed", collapsed)

    def focus_console(self) -> None:
        self.set_console_collapsed(False)
        self.console.focus_input()

    def palette_open(self) -> None:
        self.palette.open()

    def _wire(self) -> None:
        self.runner.output.connect(self.console.write)
        self.console.lineWritten.connect(self.session_log.write)
        self.runner.busyChanged.connect(self.console.set_busy)
        self.runner.busyChanged.connect(lambda b: b and setattr(self, "_queue_t0", time.monotonic()))
        self.runner.progress.connect(self.console.set_progress)
        self.runner.queueFinished.connect(self._on_queue_finished)
        self.console.commandEntered.connect(self.run_text)
        self.console.stopRequested.connect(self.runner.stop)
        self.runner.output.connect(lambda _t, kind: kind == "fail" and self.console.collapsed
                                   and self.config.get("console_auto_expand", True)
                                   and self.set_console_collapsed(False))

    def _shortcuts(self) -> None:
        for i, (_icon, _name, page) in enumerate(self.pages):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda p=page: self.show_page(p))
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.monitor.poll(force=True))
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_console)
        QShortcut(QKeySequence("Ctrl+J"), self, activated=lambda: self.set_console_collapsed(not self.console.collapsed))
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.palette_open)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self.palette_open)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self.set_sidebar_collapsed(not self._sidebar_collapsed))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.toggle_theme)
        QShortcut(QKeySequence("Esc"), self, activated=self.runner.stop)

    def _report_tools(self) -> None:
        t = self.tools
        ok = lambda f: "✅" if f else "❌"  # noqa: E731
        self.tools_label.setText(f"{ok(t.adb_found)} adb   {ok(t.fastboot_found)} fastboot")
        self.page_dashboard.set_tools_ok(t.adb_found and t.fastboot_found)
        if not (t.adb_found and t.fastboot_found):
            self.console.write("⚠ adb/fastboot не найдены. Откройте «Настройки» → «Скачать platform-tools».", "warn")
        else:
            self.console.write(f"adb: {t.adb}", "info")
            self.console.write(f"fastboot: {t.fastboot}", "info")

    def tools_changed(self) -> None:
        self.tools.refresh()
        self._report_tools()
        self.monitor.poll(force=True)

    # ========================================================== devices
    def _on_devices(self, devices: list[Device]) -> None:
        self.devices = devices
        prev = self.device.serial if self.device else None
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem("🔌  Нет подключённых устройств", None)
        idx = 0
        for i, d in enumerate(devices):
            icon = "📶" if d.transport == "wifi" else "🔗"
            self.device_combo.addItem(f"{icon}  {d.title}", d)
            if d.serial == prev:
                idx = i
        self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)
        self.devicesUpdated.emit(devices)
        self._on_combo(idx)

    def _on_combo(self, _idx: int) -> None:
        dev = self.device_combo.currentData()
        changed = dev != self.device
        old = self.device
        self.device = dev
        self._refresh_badge()
        if changed:
            if dev and (old is None or old.serial != dev.serial or old.mode != dev.mode):
                self.toast.show_message(f"🔗 {dev.title}\nРежим: {dev.mode_name}", "ok")
                if dev.mode == "unauthorized":
                    self.toast.show_message("🔐 Подтвердите отладку по USB на экране телефона", "warn", 6000)
            elif dev is None and old is not None:
                self.toast.show_message("🔌 Устройство отключено", "warn")
            self.deviceChanged.emit(dev)

    # ==================================================== job helpers
    def _serial_args(self, target: Device | None = None) -> list[str]:
        dev = target or self.device
        return ["-s", dev.serial] if dev else []

    def adb_job(self, *args: str, label: str = "", allow_fail: bool = False,
                serial: bool = True, target: Device | None = None) -> Job:
        pre = self._serial_args(target) if serial else []
        return Job(self.tools.adb, pre + list(args), label, allow_fail)

    def fb_job(self, *args: str, label: str = "", allow_fail: bool = False,
               serial: bool = True, target: Device | None = None) -> Job:
        pre = self._serial_args(target) if serial else []
        return Job(self.tools.fastboot, pre + list(args), label, allow_fail)

    def run(self, jobs, stop_on_error: bool | None = None) -> None:
        if stop_on_error is None:
            stop_on_error = bool(self.config.get("stop_on_error"))
        self.runner.enqueue(jobs, stop_on_error)

    def run_adb(self, *args: str, label: str = "") -> None:
        self.run([self.adb_job(*args, label=label)])

    def run_fb(self, *args: str, label: str = "") -> None:
        self.run([self.fb_job(*args, label=label)])

    def capture_adb(self, args: list[str], cb, **kw):
        return capture(self.tools.adb, self._serial_args() + args, cb, **kw)

    def capture_fb(self, args: list[str], cb, **kw):
        return capture(self.tools.fastboot, self._serial_args() + args, cb, **kw)

    def parse_jobs(self, text: str, target: Device | None = None, strict: bool = True) -> list[Job]:
        """Parse a command line. With `target`, commands for the wrong tool are skipped (strict=False)."""
        dev = target or self.device
        jobs: list[Job] = []
        for tokens in split_command(text):
            first = tokens[0].lower()
            if first in ("sleep", "echo"):
                jobs.append(Job(SLEEP if first == "sleep" else ECHO, tokens[1:] or ["1"]))
                continue
            if first in ("adb", "adb.exe"):
                tool, args = "adb", tokens[1:]
            elif first in ("fastboot", "fastboot.exe"):
                tool, args = "fastboot", tokens[1:]
            else:  # shorthand: "shell ls", "getvar all" ...
                tool = "fastboot" if (dev and dev.is_fastboot) else "adb"
                args = tokens
            if tool == "adb" and args == ["shell"]:
                raise ValueError("Интерактивный shell не поддерживается — укажите команду: adb shell ls /sdcard")
            if not strict and dev and ((tool == "adb" and not dev.is_adb) or (tool == "fastboot" and not dev.is_fastboot)):
                continue
            need_serial = bool(args) and args[0] not in NO_SERIAL[tool] and "-s" not in args
            maker = self.adb_job if tool == "adb" else self.fb_job
            jobs.append(maker(*args, serial=need_serial, target=target))
        return jobs

    def parse_script(self, script: str, target: Device | None = None) -> list[Job]:
        """Multi-line script: one command per line, '#' comments, sleep N, echo text."""
        jobs: list[Job] = []
        for n, line in enumerate(script.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                jobs += self.parse_jobs(line, target, strict=target is None)
            except ValueError as exc:
                raise ValueError(f"строка {n}: {exc}") from None
        return jobs

    def broadcast_jobs(self, text: str, script: bool = False) -> list[Job]:
        """Build jobs for every connected device that is in a matching mode."""
        jobs: list[Job] = []
        for dev in self.devices:
            if not (dev.is_adb or dev.is_fastboot):
                continue
            part = self.parse_script(text, dev) if script else self.parse_jobs(text, dev, strict=False)
            if part:
                jobs.append(Job(ECHO, [f"📡 ── {dev.title} ──"]))
                jobs += part
        return jobs

    def run_text(self, text: str) -> None:
        try:
            if self.console.broadcast.isChecked():
                jobs = self.broadcast_jobs(text)
                if not jobs:
                    self.notify("Нет подходящих устройств для этой команды", "warn")
                    return
            else:
                jobs = self.parse_jobs(text)
        except ValueError as exc:
            self.console.write(f"✖ {exc}", "fail")
            return
        self.config.set("history", self.console.input.history[-200:])
        self.run(jobs, stop_on_error=False if self.console.broadcast.isChecked() else None)

    # ========================================================= theming
    def _resolve_mode(self) -> str:
        mode = self.config.get("theme_mode", "dark")
        if mode == "system":
            try:
                scheme = QApplication.styleHints().colorScheme()
                return "light" if scheme == Qt.ColorScheme.Light else "dark"
            except AttributeError:
                return "dark"
        return mode if mode in ("dark", "light") else "dark"

    def apply_theme(self) -> None:
        theme.set_palette(self._resolve_mode(), self.config.get("accent", "Фиолетовый"))
        QApplication.instance().setStyleSheet(theme.build_qss())
        if hasattr(self, "badge"):
            self._refresh_theme_widgets()

    def apply_accent(self, name: str) -> None:
        self.config.set("accent", name)
        self.apply_theme()

    def toggle_theme(self) -> None:
        self.config.set("theme_mode", "light" if theme.MODE == "dark" else "dark")
        self.apply_theme()
        self.notify("☀ Светлая тема" if theme.MODE == "light" else "🌙 Тёмная тема", "info")
        if hasattr(self.page_settings, "sync_theme"):
            self.page_settings.sync_theme()

    def _refresh_theme_widgets(self) -> None:
        if self._sidebar_collapsed:
            self.logo.setText(f'<span style="color:{theme.ACCENT}">⚡</span>')
        else:
            self.logo.setText(f'<span style="color:{theme.ACCENT}">⚡</span> Droid'
                              f'<span style="color:{theme.ACCENT_2}">Forge</span>')
        self.theme_btn.setText("☀" if theme.MODE == "dark" else "🌙")
        self._refresh_badge()

    def _refresh_badge(self) -> None:
        dev = self.device
        if dev is None:
            self.badge.setText("НЕТ УСТРОЙСТВА")
            self.badge.setStyleSheet(f"background: {theme.SURFACE_2}; color: {theme.MUTED};")
            self.dev_name.setText("🔌  Нет устройства")
            self.dev_meta.setText("Подключите телефон по USB")
        else:
            self.badge.setText(dev.mode_name.upper())
            self.badge.setStyleSheet(f"background: {theme.rgba(dev.color, 0.14)}; color: {dev.color};"
                                     f" border: 1px solid {theme.rgba(dev.color, 0.45)};")
            name = dev.model.replace("_", " ") or dev.product or "Устройство"
            self.dev_name.setText(f'<span style="color:{dev.color}">●</span>  {name}')
            meta = f"{dev.mode_name} · {'Wi‑Fi' if dev.transport == 'wifi' else 'USB'}"
            if self._battery and dev.has_shell:
                meta += f" · {self._battery}"
            self.dev_meta.setText(meta)

    def set_battery(self, text: str) -> None:
        self._battery = text
        self._refresh_badge()

    # ===================================================== palette items
    def _palette_items(self) -> list[PaletteItem]:
        from .core.commands import PRESETS
        items: list[PaletteItem] = []
        for icon, name, page in self.pages:
            items.append(PaletteItem(icon, name, "Раздел", lambda p=page: self.show_page(p)))
        for widget, icon, title, desc in self.page_toolbox.tools():
            items.append(PaletteItem(icon, title, "Инструмент", lambda w=widget: self.page_toolbox.show_tab(w), desc))
        for page, group in ((self.page_flash, "Прошивка"), (self.page_adb, "ADB инструменты")):
            for i in range(page.tabs.count()):
                items.append(PaletteItem("›", page.tabs.tabText(i), group,
                                         lambda p=page, i=i: (self.show_page(p), p.tabs.setCurrentIndex(i))))
        aliases = {"system": "систему ребут reboot", "recovery": "рекавери рекaвери recovery", "bootloader": "загрузчик фастбут fastboot",
                   "fastbootd": "фастбутд fastbootd", "sideload": "сайдлоад", "edl": "едл qualcomm", "poweroff": "выключение off"}
        for key, text in REBOOT_TARGETS:
            icon, _, title = text.partition("  ")
            items.append(PaletteItem(icon, f"Перезагрузка: {title.strip()}", "Питание", lambda k=key: self.reboot(k),
                                     aliases.get(key, "")))
        d = self.page_dashboard
        items += [
            PaletteItem("📸", "Скриншот", "Действие", d._screenshot),
            PaletteItem("📈", "Живой мониторинг вкл/выкл", "Действие", lambda: (self.show_page(d), d.toggle_monitor())),
            PaletteItem("📄", "Отчёт об устройстве", "Действие", d.export_report),
            PaletteItem("⟳", "Обновить список устройств", "Действие", lambda: self.monitor.poll(force=True)),
            PaletteItem("🌗", "Сменить тему (светлая / тёмная)", "Оформление", self.toggle_theme),
            PaletteItem("🖥", "Свернуть / развернуть консоль", "Оформление",
                        lambda: self.set_console_collapsed(not self.console.collapsed)),
            PaletteItem("🧹", "Очистить консоль", "Консоль", self.console.clear),
            PaletteItem("⬇", "Скачать platform-tools", "Настройки",
                        lambda: (self.show_page(self.page_settings), self.page_settings.download())),
        ]
        for name in theme.ACCENTS:
            items.append(PaletteItem("🎨", f"Цвет: {name}", "Оформление", lambda n=name: self.apply_accent(n)))
        for sc in self.config.get("scripts", []):
            items.append(PaletteItem("📜", sc["name"], "Сценарий",
                                     lambda b=sc["body"]: self.run(self.parse_script(b)), "запустить сценарий"))
        for c in self.config.get("custom_commands", []):
            items.append(PaletteItem("⭐", c["title"], "Моя команда", lambda cmd=c["command"]: self.run_text(cmd), c["command"]))
        for cat, cmds in PRESETS.items():
            for title, cmd, desc, danger in cmds:
                items.append(PaletteItem("⚠" if danger else "▶", title, cat.split(" ", 1)[-1],
                                         lambda t=title, c=cmd, dg=danger: self.page_quick.execute(t, c, dg),
                                         f"{cmd} {desc}"))
        return items

    # ======================================================= dialogs
    def require_device(self, *, adb: bool = False, fastboot: bool = False, shell: bool = False) -> bool:
        dev = self.device
        if dev is None:
            self.toast.show_message("🔌 Подключите устройство", "warn")
            return False
        if shell and not dev.has_shell:
            self.toast.show_message(f"Нужен режим ADB (сейчас: {dev.mode_name})", "warn")
            return False
        if adb and not dev.is_adb:
            self.toast.show_message(f"Нужен режим ADB (сейчас: {dev.mode_name})", "warn")
            return False
        if fastboot and not dev.is_fastboot:
            self.toast.show_message(f"Нужен режим Fastboot (сейчас: {dev.mode_name})", "warn")
            return False
        return True

    def confirm(self, title: str, text: str, danger: bool = True) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
        box.setText(f"<b>{title}</b>")
        box.setInformativeText(text)
        yes = box.addButton("Продолжить", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        if danger:
            yes.setProperty("kind", "danger")
        box.exec()
        return box.clickedButton() is yes

    def notify(self, text: str, kind: str = "info") -> None:
        self.toast.show_message(text, kind)

    # ---- drag & drop anywhere on the window
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        import zipfile
        from pathlib import Path
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        first = Path(paths[0])
        ext = first.suffix.lower()
        apks = [p for p in paths if p.lower().endswith(".apk")]
        if apks:
            self.page_adb.apk_tab.install_paths(apks)
        elif first.is_dir():
            self.show_page(self.page_flash)
            self.page_flash.tabs.setCurrentIndex(1)
            self.page_flash.f_dir.setPath(str(first))
            self.page_flash.scan_folder(str(first))
        elif ext in (".img", ".bin", ".mbn", ".elf") and first.name != "payload.bin":
            self.show_page(self.page_flash)
            self.page_flash.tabs.setCurrentIndex(0)
            self.page_flash.s_file.setPath(str(first))
            self.page_flash._on_single_file(str(first))
        elif first.name == "payload.bin" or (ext == ".zip" and zipfile.is_zipfile(first)
                                            and "payload.bin" in zipfile.ZipFile(first).namelist()):
            tab = self.page_toolbox.payload_tab
            tab.src.setPath(str(first))
            tab.load(str(first))
            self.page_toolbox.show_tab(tab)
        elif ext == ".zip":
            self.show_page(self.page_flash)
            self.page_flash.tabs.setCurrentIndex(3)
            self.page_flash.z_file.setPath(str(first))
        else:
            self.show_page(self.page_toolbox)
            self.page_toolbox.hash_tab.file.setPath(str(first))
            self.page_toolbox.show_tab(self.page_toolbox.hash_tab)
            self.page_toolbox.hash_tab.compute()
        e.acceptProposedAction()

    def clipboard_set(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.notify("📋 Скопировано", "ok")

    def after_queue(self, callback) -> None:
        """Call `callback` once, when the current command queue finishes."""
        if callback not in self._after:
            self._after.append(callback)

    # ======================================================= actions
    def reboot(self, target: str) -> None:
        dev = self.device
        if not self.require_device():
            return
        if dev.is_fastboot:
            mapping = {
                "system": ["reboot"], "bootloader": ["reboot", "bootloader"],
                "recovery": ["reboot", "recovery"], "fastbootd": ["reboot", "fastboot"],
                "edl": ["oem", "edl"], "poweroff": ["oem", "poweroff"],
            }
            if target not in mapping:
                self.notify("Из fastboot этот режим недоступен", "warn")
                return
            self.run([self.fb_job(*mapping[target])])
        else:
            mapping = {
                "system": ["reboot"], "bootloader": ["reboot", "bootloader"],
                "recovery": ["reboot", "recovery"], "fastbootd": ["reboot", "fastboot"],
                "sideload": ["reboot", "sideload"], "edl": ["reboot", "edl"],
                "poweroff": ["shell", "reboot", "-p"],
            }
            if target == "edl" and not self.confirm("EDL режим", "Выйти из EDL можно только долгим зажатием кнопки питания или через специальный софт. Продолжить?"):
                return
            self.run([self.adb_job(*mapping[target])])

    def _on_queue_finished(self, ok: bool) -> None:
        callbacks, self._after = self._after, []
        for cb in callbacks:
            cb()
        long_run = time.monotonic() - self._queue_t0 > 8
        if not self.isActiveWindow():
            QApplication.alert(self)
            if self.tray and long_run and self.config.get("tray_notify", True):
                icon = QSystemTrayIcon.MessageIcon.Information if ok else QSystemTrayIcon.MessageIcon.Critical
                self.tray.showMessage(__app_name__, "✅ Все команды выполнены" if ok else "❌ Выполнение завершилось с ошибкой",
                                      icon, 6000)
        self.monitor.poll()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.move(self.width() - self.toast.width() - 24, 76)

    def closeEvent(self, e) -> None:
        self.config.set("history", self.console.input.history[-200:])
        self.session_log.close()
        for _icon, _name, page in self.pages:
            if hasattr(page, "shutdown"):
                page.shutdown()
        if self.runner.busy:
            if not self.confirm("Идёт выполнение", "Сейчас выполняются команды (возможно, прошивка). Прерывание может повредить устройство. Всё равно выйти?"):
                e.ignore()
                return
            self.runner.stop()
        super().closeEvent(e)


def make_icon() -> QIcon:
    """Draw the app icon at runtime (no external assets needed)."""
    pm = QPixmap(128, 128)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, 128, 128)
    grad.setColorAt(0, QColor(theme.ACCENT))
    grad.setColorAt(1, QColor(theme.ACCENT_2))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, 120, 120, 30, 30)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPointSize(60)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "⚡")
    p.end()
    return QIcon(pm)


def main() -> int:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("droidforge.app")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.QSS)
    win = MainWindow()
    win.show()
    return app.exec()
