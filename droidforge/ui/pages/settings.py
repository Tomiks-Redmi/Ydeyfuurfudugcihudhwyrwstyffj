"""Settings: tool paths, platform-tools downloader, behaviour options."""
from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QProgressBar, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from ...core.config import APP_DIR, CONFIG_FILE
from ...core.logfile import LOG_DIR
from ...core.tools import EXE, PlatformToolsDownloader, platform_tools_url
from .. import theme
from ..widgets import FilePicker, button, card, hbox, label, page_header


class SettingsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.downloader: PlatformToolsDownloader | None = None

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
        lay.addLayout(page_header("⚙️ Настройки", "Пути к инструментам и поведение приложения."))

        # ---- tools
        c1, l1 = card("🧰 Android platform-tools",
                      "Оставьте поля пустыми для автоопределения (PATH, Android SDK, ~/.droidforge/platform-tools).")
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        filt = f"Исполняемые файлы (*{EXE})" if EXE else "Все файлы (*)"
        self.adb_path = FilePicker("автоопределение", filt, config=app.config, key="tools")
        self.adb_path.setPath(app.config.get("adb_path"))
        self.fb_path = FilePicker("автоопределение", filt, config=app.config, key="tools")
        self.fb_path.setPath(app.config.get("fastboot_path"))
        form.addRow("adb", self.adb_path)
        form.addRow("fastboot", self.fb_path)
        l1.addLayout(form)
        self.detected = label("", "muted", wrap=True)
        l1.addWidget(self.detected)
        l1.addLayout(hbox(button("💾 Применить", self.apply, "accent"),
                          button("🔄 Автоопределение", self.autodetect),
                          button("ℹ Версии", self.versions), None))
        lay.addWidget(c1)

        # ---- download
        c2, l2 = card("⬇ Скачать официальные platform-tools",
                      f"Загрузка последней версии с серверов Google:<br><code>{platform_tools_url()}</code>")
        self.dl_progress = QProgressBar()
        self.dl_progress.hide()
        self.dl_btn = button("⬇ Скачать и установить", self.download, "accent")
        l2.addWidget(self.dl_progress)
        l2.addLayout(hbox(self.dl_btn, button("🌐 Страница загрузки", lambda: QDesktopServices.openUrl(
            QUrl("https://developer.android.com/tools/releases/platform-tools"))), None))
        lay.addWidget(c2)

        # ---- behaviour
        c3, l3 = card("🎛 Поведение")
        self.poll = QSpinBox()
        self.poll.setRange(500, 30000)
        self.poll.setSingleStep(500)
        self.poll.setSuffix(" мс")
        self.poll.setValue(int(app.config.get("poll_interval")))
        self.poll.valueChanged.connect(self._poll_changed)
        self.stop_err = QCheckBox("Останавливать очередь команд при первой ошибке")
        self.stop_err.setChecked(bool(app.config.get("stop_on_error")))
        self.stop_err.toggled.connect(lambda v: app.config.set("stop_on_error", v))
        l3.addLayout(hbox(label("Интервал опроса устройств:", "muted"), self.poll, None))
        l3.addWidget(self.stop_err)
        self.tray = QCheckBox("Уведомление в трее, когда долгая операция завершилась, а окно свёрнуто")
        self.tray.setChecked(bool(app.config.get("tray_notify", True)))
        self.tray.toggled.connect(lambda v: app.config.set("tray_notify", v))
        l3.addWidget(self.tray)
        self.accent = QComboBox()
        for name, (c1_, _c2) in theme.ACCENTS.items():
            self.accent.addItem(self._swatch(c1_), name)
        self.accent.setCurrentText(app.config.get("accent", "Фиолетовый"))
        self.accent.currentTextChanged.connect(self._accent_changed)
        l3.addLayout(hbox(label("Цвет оформления:", "muted"), self.accent, None))
        l3.addWidget(label(f"Файл настроек: <code>{CONFIG_FILE}</code>", "muted"))
        l3.addWidget(label("Весь вывод консоли сохраняется в журнал сессии — пригодится, если прошивка пошла не так.",
                           "muted", wrap=True))
        l3.addLayout(hbox(button("📂 Открыть папку журналов", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR)))),
                          button("📂 Папка программы", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_DIR)))),
                          None))
        lay.addWidget(c3)

        # ---- shortcuts
        c4, l4 = card("⌨ Горячие клавиши")
        l4.addWidget(label(
            "<b>Ctrl+1…7</b> — разделы &nbsp;·&nbsp; <b>F5</b> — обновить устройства &nbsp;·&nbsp; "
            "<b>Ctrl+L</b> — консоль &nbsp;·&nbsp; <b>Esc</b> — остановить выполнение &nbsp;·&nbsp; "
            "<b>↑ / ↓</b> — история команд", "muted", wrap=True))
        lay.addWidget(c4)
        lay.addStretch(1)
        self._show_detected()

    @staticmethod
    def _swatch(color: str) -> QIcon:
        pm = QPixmap(16, 16)
        pm.fill(QColor(color))
        return QIcon(pm)

    def _accent_changed(self, name: str) -> None:
        self.app.config.set("accent", name)
        self.app.apply_accent(name)

    def _show_detected(self) -> None:
        t = self.app.tools
        mark = lambda ok: "✅" if ok else "❌ не найден"  # noqa: E731
        self.detected.setText(f"Используется adb: <code>{t.adb}</code> {mark(t.adb_found)}<br>"
                              f"Используется fastboot: <code>{t.fastboot}</code> {mark(t.fastboot_found)}")

    def apply(self) -> None:
        self.app.config.set("adb_path", self.adb_path.path())
        self.app.config.set("fastboot_path", self.fb_path.path())
        self.app.tools_changed()
        self._show_detected()
        self.app.notify("Настройки применены", "ok")

    def autodetect(self) -> None:
        self.adb_path.setPath("")
        self.fb_path.setPath("")
        self.apply()

    def versions(self) -> None:
        self.app.run([self.app.adb_job("version", serial=False, allow_fail=True),
                      self.app.fb_job("--version", serial=False, allow_fail=True)], stop_on_error=False)

    def _poll_changed(self, v: int) -> None:
        self.app.config.set("poll_interval", v)
        self.app.monitor.set_interval(v)

    def download(self) -> None:
        if self.downloader and self.downloader.isRunning():
            return
        self.dl_btn.setEnabled(False)
        self.dl_progress.show()
        self.dl_progress.setRange(0, 0)
        self.downloader = PlatformToolsDownloader(self)
        self.downloader.progress.connect(self._dl_progress)
        self.downloader.finishedOk.connect(self._dl_ok)
        self.downloader.failed.connect(self._dl_fail)
        self.downloader.start()
        self.app.console.write("⬇ Загрузка platform-tools…", "info")

    def _dl_progress(self, got: int, total: int) -> None:
        if total:
            self.dl_progress.setRange(0, total)
            self.dl_progress.setValue(got)
            self.dl_progress.setFormat(f"{got / 1048576:.1f} / {total / 1048576:.1f} МБ")

    def _dl_ok(self, path: str) -> None:
        self.dl_btn.setEnabled(True)
        self.dl_progress.hide()
        self.app.console.write(f"✔ platform-tools установлены в {path}", "ok")
        self.app.notify("✅ platform-tools установлены", "ok")
        self.autodetect()

    def _dl_fail(self, err: str) -> None:
        self.dl_btn.setEnabled(True)
        self.dl_progress.hide()
        self.app.console.write(f"✖ Ошибка загрузки: {err}", "fail")
        self.app.notify("Не удалось скачать platform-tools", "error")

    def shutdown(self) -> None:
        if self.downloader and self.downloader.isRunning():
            self.downloader.wait(2000)
