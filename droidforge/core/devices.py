"""Device discovery: polls `adb devices -l` and `fastboot devices`."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .runner import capture
from .tools import Tools

MODE_NAMES = {
    "device": "ADB",
    "recovery": "Recovery",
    "sideload": "Sideload",
    "rescue": "Rescue",
    "fastboot": "Fastboot",
    "unauthorized": "Не авторизовано",
    "offline": "Offline",
    "no permissions": "Нет прав",
    "authorizing": "Авторизация…",
}

MODE_COLORS = {
    "device": "#2ee6a6",
    "recovery": "#ffb547",
    "sideload": "#ffb547",
    "rescue": "#ffb547",
    "fastboot": "#7c5cff",
}


@dataclass(frozen=True)
class Device:
    serial: str
    mode: str
    model: str = ""
    product: str = ""
    transport: str = "usb"

    @property
    def is_fastboot(self) -> bool:
        return self.mode == "fastboot"

    @property
    def is_adb(self) -> bool:
        return self.mode in ("device", "recovery", "sideload", "rescue")

    @property
    def has_shell(self) -> bool:
        return self.mode in ("device", "recovery")

    @property
    def mode_name(self) -> str:
        return MODE_NAMES.get(self.mode, self.mode)

    @property
    def color(self) -> str:
        return MODE_COLORS.get(self.mode, "#ff4d6d")

    @property
    def title(self) -> str:
        name = self.model.replace("_", " ") if self.model else (self.product or "Устройство")
        return f"{name}  ·  {self.serial}"


def _parse(output: str, fastboot: bool) -> list[Device]:
    devices: list[Device] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith(("*", "List of", "<", "adb server", "error")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, rest = parts[0], parts[1:]
        if fastboot:
            mode = "fastboot" if rest[0] == "fastboot" else " ".join(rest[:2]).rstrip(";")
            devices.append(Device(serial, mode, transport="usb"))
            continue
        state = rest[0]
        if state == "no" and len(rest) > 1:
            state = "no permissions"
        info = dict(p.split(":", 1) for p in rest if ":" in p)
        transport = "wifi" if ":" in serial or serial.startswith("adb-") else "usb"
        devices.append(Device(serial, state, info.get("model", ""), info.get("product", ""), transport))
    return devices


class DeviceMonitor(QObject):
    devicesChanged = pyqtSignal(list)

    def __init__(self, tools: Tools, interval: int = 2000, parent: QObject | None = None):
        super().__init__(parent)
        self.tools = tools
        self.timer = QTimer(self)
        self.timer.setInterval(max(500, interval))
        self.timer.timeout.connect(self.poll)
        self._busy = False
        self._adb: list[Device] = []
        self._last: list[Device] | None = None

    def start(self) -> None:
        self.poll()
        self.timer.start()

    def set_interval(self, ms: int) -> None:
        self.timer.setInterval(max(500, ms))

    def poll(self, force: bool = False) -> None:
        if self._busy:
            return
        if force:
            self._last = None
        self._busy = True
        capture(self.tools.adb, ["devices", "-l"], self._on_adb, timeout=10000)

    def _on_adb(self, code: int, out: str) -> None:
        self._adb = _parse(out, fastboot=False) if code == 0 else []
        capture(self.tools.fastboot, ["devices"], self._on_fastboot, timeout=6000)

    def _on_fastboot(self, code: int, out: str) -> None:
        self._busy = False
        fb = _parse(out, fastboot=True) if code == 0 else []
        known = {d.serial for d in self._adb}
        devices = self._adb + [d for d in fb if d.serial not in known]
        if devices != self._last:
            self._last = devices
            self.devicesChanged.emit(devices)
