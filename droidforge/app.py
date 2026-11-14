"""Main window: navigation, device selector, console and shared helpers for pages."""
from __future__ import annotations

import sys

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut, QColor, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import __app_name__, __version__
from .core.commands import NO_SERIAL, all_completions, split_command
from .core.config import Config
from .core.devices import Device, DeviceMonitor
from .core.runner import CommandRunner, Job, capture
from .core.tools import Tools
from .ui import theme
from .ui.console import Console
from .ui.widgets import Toast, button, label

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

        # ---- sidebar
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(230)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(6)
        logo = QLabel(f'<span style="color:{theme.ACCENT}">⚡</span> Droid'
                      f'<span style="color:{theme.ACCENT_2}">Forge</span>')
        logo.setObjectName("logo")
        sl.addWidget(logo)
        sl.addWidget(label(f"ADB & Fastboot Studio · v{__version__}", "version"))
        sl.addSpacing(14)
        self.nav = QListWidget(objectName="nav")
        self.nav.setIconSize(QSize(20, 20))
        sl.addWidget(self.nav, 1)
        self.tools_label = label("", "muted", wrap=True)
        self.tools_label.setStyleSheet("font-size: 8pt;")
        sl.addWidget(self.tools_label)
        outer.addWidget(sidebar)

        # ---- content
        content = QWidget(objectName="content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.console = Console(self.config.get("history"), all_completions())
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.stack)
        splitter.addWidget(self.console)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([660, 210])
        splitter.setChildrenCollapsible(False)
        cl.addWidget(splitter, 1)
        outer.addWidget(content, 1)

        from .ui.pages.adb_tools import AdbToolsPage
        from .ui.pages.dashboard import DashboardPage
        from .ui.pages.flash import FlashPage
        from .ui.pages.logcat import LogcatPage
        from .ui.pages.quick import QuickPage
        from .ui.pages.settings import SettingsPage

        self.pages = [
            ("🏠", "Обзор", DashboardPage(self)),
            ("⚡", "Прошивка", FlashPage(self)),
            ("📱", "ADB инструменты", AdbToolsPage(self)),
            ("🚀", "Быстрые команды", QuickPage(self)),
            ("📜", "Logcat", LogcatPage(self)),
            ("⚙️", "Настройки", SettingsPage(self)),
        ]
        for i, (icon, name, page) in enumerate(self.pages):
            item = QListWidgetItem(f"  {icon}   {name}")
            item.setToolTip(f"{name}  (Ctrl+{i + 1})")
            self.nav.addItem(item)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.toast = Toast(self)

    def _build_header(self) -> QFrame:
        header = QFrame(objectName="header")
        header.setFixedHeight(62)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 10, 20, 10)
        hl.setSpacing(10)
        hl.addWidget(label("Устройство:", "muted"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(360)
        self.device_combo.currentIndexChanged.connect(self._on_combo)
        hl.addWidget(self.device_combo)
        self.badge = QLabel("—", objectName="badge")
        hl.addWidget(self.badge)
        hl.addWidget(button("⟳", lambda: self.monitor.poll(force=True), tip="Обновить список (F5)"))
        hl.addStretch(1)

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

    def _wire(self) -> None:
        self.runner.output.connect(self.console.write)
        self.runner.busyChanged.connect(self.console.set_busy)
        self.runner.progress.connect(self.console.set_progress)
        self.runner.queueFinished.connect(self._on_queue_finished)
        self.console.commandEntered.connect(self.run_text)
        self.console.stopRequested.connect(self.runner.stop)

    def _shortcuts(self) -> None:
        for i in range(len(self.pages)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self.nav.setCurrentRow(i))
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.monitor.poll(force=True))
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.console.focus_input)
        QShortcut(QKeySequence("Esc"), self, activated=self.runner.stop)

    def _report_tools(self) -> None:
        t = self.tools
        ok = lambda f: "✅" if f else "❌"  # noqa: E731
        self.tools_label.setText(f"{ok(t.adb_found)} adb   {ok(t.fastboot_found)} fastboot")
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
        if dev is None:
            self.badge.setText("НЕТ УСТРОЙСТВА")
            self.badge.setStyleSheet(f"background: {theme.SURFACE_2}; color: {theme.MUTED};")
        else:
            self.badge.setText(dev.mode_name.upper())
            self.badge.setStyleSheet(f"background: {theme.rgba(dev.color, 0.14)}; color: {dev.color};"
                                     f" border: 1px solid {theme.rgba(dev.color, 0.45)};")
        if changed:
            if dev and (old is None or old.serial != dev.serial or old.mode != dev.mode):
                self.toast.show_message(f"🔗 {dev.title}\nРежим: {dev.mode_name}", "ok")
                if dev.mode == "unauthorized":
                    self.toast.show_message("🔐 Подтвердите отладку по USB на экране телефона", "warn", 6000)
            elif dev is None and old is not None:
                self.toast.show_message("🔌 Устройство отключено", "warn")
            self.deviceChanged.emit(dev)

    # ==================================================== job helpers
    def _serial_args(self) -> list[str]:
        return ["-s", self.device.serial] if self.device else []

    def adb_job(self, *args: str, label: str = "", allow_fail: bool = False,
                serial: bool = True) -> Job:
        pre = self._serial_args() if serial else []
        return Job(self.tools.adb, pre + list(args), label, allow_fail)

    def fb_job(self, *args: str, label: str = "", allow_fail: bool = False,
               serial: bool = True) -> Job:
        pre = self._serial_args() if serial else []
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

    def parse_jobs(self, text: str) -> list[Job]:
        jobs: list[Job] = []
        for tokens in split_command(text):
            first = tokens[0].lower()
            if first in ("adb", "adb.exe"):
                tool, args = "adb", tokens[1:]
            elif first in ("fastboot", "fastboot.exe"):
                tool, args = "fastboot", tokens[1:]
            else:  # shorthand: "shell ls", "getvar all" ...
                tool = "fastboot" if (self.device and self.device.is_fastboot) else "adb"
                args = tokens
            if tool == "adb" and args == ["shell"]:
                raise ValueError("Интерактивный shell не поддерживается — укажите команду: adb shell ls /sdcard")
            need_serial = bool(args) and args[0] not in NO_SERIAL[tool] and "-s" not in args
            maker = self.adb_job if tool == "adb" else self.fb_job
            jobs.append(maker(*args, serial=need_serial))
        return jobs

    def run_text(self, text: str) -> None:
        try:
            jobs = self.parse_jobs(text)
        except ValueError as exc:
            self.console.write(f"✖ {exc}", "fail")
            return
        self.config.set("history", self.console.input.history[-200:])
        self.run(jobs)

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
        if not self.isActiveWindow():
            QApplication.alert(self)
        self.monitor.poll()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.move(self.width() - self.toast.width() - 24, 76)

    def closeEvent(self, e) -> None:
        self.config.set("history", self.console.input.history[-200:])
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
