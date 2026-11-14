"""ADB tools: apps, file manager, APK installer, screen & remote control, Wi‑Fi ADB."""
from __future__ import annotations

import posixpath
import re
import shutil
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QProcess, QProcessEnvironment, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..widgets import DropListWidget, button, card, hbox, label, page_header


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


class AdbToolsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(14)
        lay.addLayout(page_header("📱 ADB инструменты", "Приложения, файлы, установка APK, скриншоты, "
                                                        "управление и ADB по Wi‑Fi."))
        self.tabs = QTabWidget()
        self.apps_tab = AppsTab(app)
        self.files_tab = FilesTab(app)
        self.apk_tab = ApkTab(app)
        self.screen_tab = ScreenTab(app)
        self.wifi_tab = WifiTab(app)
        self.tabs.addTab(self.apps_tab, "🧩 Приложения")
        self.tabs.addTab(self.files_tab, "🗂 Файлы")
        self.tabs.addTab(self.apk_tab, "📥 Установка APK")
        self.tabs.addTab(self.screen_tab, "🖼 Экран и управление")
        self.tabs.addTab(self.wifi_tab, "📶 ADB по Wi‑Fi")
        from .adb_extra import PortsTab, ProcessesTab
        self.proc_tab = ProcessesTab(app)
        self.ports_tab = PortsTab(app)
        self.tabs.addTab(self.proc_tab, "Процессы")
        self.tabs.addTab(self.ports_tab, "Порты")
        lay.addWidget(self.tabs, 1)


# =========================================================================
class AppsTab(QWidget):
    FILTERS = [("Пользовательские", ["-3"]), ("Системные", ["-s"]), ("Все", []),
               ("Отключённые", ["-d"])]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.packages: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        self.kind = QComboBox()
        for name, _ in self.FILTERS:
            self.kind.addItem(name)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 Поиск пакета…")
        self.search.textChanged.connect(self._apply_filter)
        self.count = label("", "muted")
        lay.addLayout(hbox(self.kind, self.search, self.count, button("⟳ Загрузить", self.refresh)))
        lay.itemAt(0).layout().setStretch(1, 1)

        self.list = DropListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(lambda _: self.launch())
        self.list.filesDropped.connect(lambda paths: app.page_adb.apk_tab.install_paths(paths))
        lay.addWidget(self.list, 1)

        lay.addLayout(hbox(
            button("▶ Запустить", self.launch),
            button("⏹ Остановить", lambda: self._each("shell", "am", "force-stop")),
            button("📤 Извлечь APK", self.extract),
            button("ℹ Инфо", self.info),
            button("🔑 Разрешения", self.permissions),
            None,
            button("🚫 Отключить", lambda: self._each("shell", "pm", "disable-user", "--user", "0", confirm="Отключить выбранные приложения?")),
            button("✅ Включить", lambda: self._each("shell", "pm", "enable")),
            button("🧽 Очистить данные", lambda: self._each("shell", "pm", "clear", confirm="Все данные выбранных приложений будут удалены."), "danger"),
            button("🗑 Удалить", self.uninstall, "danger"),
        ))
        lay.addWidget(label("💡 Перетащите APK в список, чтобы установить. Двойной клик — запуск приложения.", "muted"))

    def selected(self) -> list[str]:
        return [i.text() for i in self.list.selectedItems()]

    def refresh(self) -> None:
        if not self.app.require_device(shell=True):
            return
        args = ["shell", "pm", "list", "packages"] + self.FILTERS[self.kind.currentIndex()][1]
        self.count.setText("загрузка…")
        self.app.capture_adb(args, self._on_list)

    def _on_list(self, code: int, out: str) -> None:
        self.packages = sorted(l[8:].strip() for l in out.splitlines() if l.startswith("package:"))
        self.list.clear()
        for p in self.packages:
            self.list.addItem(QListWidgetItem(p))
        self._apply_filter(self.search.text())

    def _apply_filter(self, text: str) -> None:
        text = text.lower()
        shown = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            hide = bool(text) and text not in item.text().lower()
            item.setHidden(hide)
            shown += not hide
        self.count.setText(f"{shown} / {self.list.count()}")

    def _each(self, *args: str, confirm: str | None = None) -> None:
        pkgs = self.selected()
        if not pkgs:
            self.app.notify("Выберите приложение(я)", "warn")
            return
        if not self.app.require_device(shell=True):
            return
        if confirm and not self.app.confirm("Подтверждение", f"{confirm}<br><small>{', '.join(pkgs)}</small>"):
            return
        self.app.run([self.app.adb_job(*args, p) for p in pkgs], stop_on_error=False)

    def launch(self) -> None:
        pkgs = self.selected()
        if pkgs and self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", "monkey", "-p", pkgs[0], "-c",
                                           "android.intent.category.LAUNCHER", "1")])

    def info(self) -> None:
        pkgs = self.selected()
        if pkgs and self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", f"dumpsys package {pkgs[0]} | grep -E 'versionName|versionCode|firstInstallTime|lastUpdateTime|targetSdk'")])

    def _intent(self, action: str, data: str) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", "am", "start", "-a", action, "-d", data)])

    def permissions(self) -> None:
        pkgs = self.selected()
        if not pkgs or not self.app.require_device(shell=True):
            return
        PermissionsDialog(self.app, pkgs[0], self).exec()

    def uninstall(self) -> None:
        pkgs = self.selected()
        if not pkgs or not self.app.require_device(shell=True):
            return
        system = self.kind.currentIndex() in (1, 2)
        text = "Удалить выбранные приложения?"
        if system:
            text += ("<br><br>Для системных используется <code>pm uninstall -k --user 0</code> — приложение "
                     "удаляется для текущего пользователя и восстанавливается сбросом настроек.")
        if not self.app.confirm("Удаление", f"{text}<br><small>{', '.join(pkgs)}</small>"):
            return
        jobs = []
        for p in pkgs:
            jobs.append(self.app.adb_job("shell", "pm", "uninstall", "-k", "--user", "0", p) if system
                        else self.app.adb_job("uninstall", p))
        self.app.run(jobs, stop_on_error=False)
        self.app.after_queue(self.refresh)

    def extract(self) -> None:
        pkgs = self.selected()
        if not pkgs or not self.app.require_device(shell=True):
            return
        folder = QFileDialog.getExistingDirectory(self, "Куда сохранить APK", self.app.config.last_dir("apk_out"))
        if not folder:
            return
        self.app.config.remember_dir("apk_out", folder)
        for pkg in pkgs:
            self.app.capture_adb(["shell", "pm", "path", pkg],
                                 lambda c, out, pkg=pkg: self._on_paths(pkg, folder, out))

    def _on_paths(self, pkg: str, folder: str, out: str) -> None:
        paths = [l[8:].strip() for l in out.splitlines() if l.startswith("package:")]
        jobs = []
        for remote in paths:
            name = f"{pkg}.apk" if len(paths) == 1 else f"{pkg}__{posixpath.basename(remote)}"
            jobs.append(self.app.adb_job("pull", remote, str(Path(folder) / name), label=f"Извлечение {pkg}"))
        self.app.run(jobs)

    def _menu(self, pos) -> None:
        if not self.selected():
            return
        m = QMenu(self)
        m.addAction("▶ Запустить", self.launch)
        m.addAction("⏹ Остановить", lambda: self._each("shell", "am", "force-stop"))
        m.addAction("📤 Извлечь APK", self.extract)
        m.addAction("ℹ Информация", self.info)
        m.addAction("🔑 Разрешения", self.permissions)
        m.addAction("⚙ Открыть настройки приложения", lambda: self._intent(
            "android.settings.APPLICATION_DETAILS_SETTINGS", f"package:{self.selected()[0]}"))
        m.addAction("🛒 Открыть в Play Маркете", lambda: self._intent(
            "android.intent.action.VIEW", f"market://details?id={self.selected()[0]}"))
        m.addAction("📋 Копировать имя", lambda: self.app.clipboard_set("\n".join(self.selected())))
        m.addSeparator()
        m.addAction("🗑 Удалить", self.uninstall)
        m.exec(self.list.mapToGlobal(pos))


# =========================================================================
class FilesTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cwd = "/sdcard/"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        self.path = QLineEdit(self.cwd)
        self.path.returnPressed.connect(lambda: self.open_dir(self.path.text()))
        bookmarks = QComboBox()
        bookmarks.addItems(["📌 Быстрый переход", "/sdcard/", "/sdcard/Download/", "/sdcard/DCIM/",
                            "/sdcard/Pictures/", "/sdcard/Android/data/", "/data/local/tmp/", "/"])
        bookmarks.activated.connect(lambda i: i and self.open_dir(bookmarks.itemText(i)))
        lay.addLayout(hbox(button("⬆", self.up, tip="Вверх"), self.path, bookmarks,
                           button("⟳", self.refresh, tip="Обновить")))
        lay.itemAt(0).layout().setStretch(1, 1)

        self.list = DropListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemDoubleClicked.connect(self._activate)
        self.list.filesDropped.connect(self.push_paths)
        lay.addWidget(self.list, 1)

        lay.addLayout(hbox(
            button("⬇ Скачать (pull)", self.pull, "accent"),
            button("⬆ Загрузить файлы", self.push_files),
            button("📁 Загрузить папку", self.push_folder),
            button("➕ Новая папка", self.mkdir),
            None,
            button("Редактировать", self.edit_file, tip="Открыть текстовый файл во встроенном редакторе"),
            button("✏ Переименовать", self.rename),
            button("🗑 Удалить", self.delete, "danger"),
        ))
        lay.addWidget(label("💡 Перетащите файлы с компьютера в список — они загрузятся в текущую папку.", "muted"))
        app.deviceChanged.connect(lambda d: d and d.has_shell and self.refresh())

    def _remote(self, name: str) -> str:
        return posixpath.join(self.cwd, name)

    def open_dir(self, path: str) -> None:
        path = path.strip() or "/"
        if not path.endswith("/"):
            path += "/"
        self.cwd = posixpath.normpath(path) + ("/" if path != "/" else "")
        self.cwd = self.cwd.replace("//", "/")
        self.path.setText(self.cwd)
        self.refresh()

    def up(self) -> None:
        parent = posixpath.dirname(self.cwd.rstrip("/")) or "/"
        self.open_dir(parent)

    def refresh(self) -> None:
        if not self.app.device or not self.app.device.has_shell:
            return
        self.app.capture_adb(["shell", f"ls -1pA {sh_quote(self.cwd)}"], self._on_ls)

    def _on_ls(self, code: int, out: str) -> None:
        self.list.clear()
        lines = [l for l in out.splitlines() if l.strip()]
        if code != 0 and lines:
            self.list.addItem(QListWidgetItem(f"⚠ {lines[0]}"))
            return
        dirs = sorted((l for l in lines if l.endswith("/")), key=str.lower)
        files = sorted((l for l in lines if not l.endswith("/")), key=str.lower)
        for d in dirs:
            it = QListWidgetItem(f"📁  {d.rstrip('/')}")
            it.setData(Qt.ItemDataRole.UserRole, (d.rstrip("/"), True))
            self.list.addItem(it)
        for f in files:
            icon = "🖼" if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) else \
                   "🎬" if f.lower().endswith((".mp4", ".mkv", ".webm")) else \
                   "📦" if f.lower().endswith((".apk", ".zip", ".img")) else "📄"
            it = QListWidgetItem(f"{icon}  {f}")
            it.setData(Qt.ItemDataRole.UserRole, (f, False))
            self.list.addItem(it)

    def _selected(self) -> list[tuple[str, bool]]:
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems()
                if i.data(Qt.ItemDataRole.UserRole)]

    def _activate(self, item) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data[1]:
            self.open_dir(self._remote(data[0]))

    def _after(self) -> None:
        self.app.after_queue(self.refresh)

    def pull(self) -> None:
        sel = self._selected()
        if not sel or not self.app.require_device(adb=True):
            return
        folder = QFileDialog.getExistingDirectory(self, "Куда сохранить", self.app.config.last_dir("pull"))
        if not folder:
            return
        self.app.config.remember_dir("pull", folder)
        self.app.run([self.app.adb_job("pull", self._remote(n), folder) for n, _ in sel])

    def push_paths(self, paths: list[str]) -> None:
        if not paths or not self.app.require_device(adb=True):
            return
        self.app.run([self.app.adb_job("push", p, self.cwd) for p in paths])
        self._after()

    def push_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Файлы для загрузки", self.app.config.last_dir("push"))
        if paths:
            self.app.config.remember_dir("push", paths[0])
            self.push_paths(paths)

    def push_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка для загрузки", self.app.config.last_dir("push"))
        if folder:
            self.push_paths([folder])

    def edit_file(self) -> None:
        sel = [n for n, is_dir in self._selected() if not is_dir]
        if len(sel) != 1 or not self.app.require_device(shell=True):
            self.app.notify("Выберите один файл", "warn")
            return
        from .adb_extra import TextEditorDialog
        TextEditorDialog(self.app, self._remote(sel[0]), self).exec()
        self.app.after_queue(self.refresh)

    def mkdir(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая папка", "Имя папки:")
        if ok and name.strip() and self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", f"mkdir -p {sh_quote(self._remote(name.strip()))}")])
            self._after()

    def rename(self) -> None:
        sel = self._selected()
        if len(sel) != 1 or not self.app.require_device(shell=True):
            return
        old = sel[0][0]
        new, ok = QInputDialog.getText(self, "Переименовать", "Новое имя:", text=old)
        if ok and new.strip() and new != old:
            self.app.run([self.app.adb_job("shell", f"mv {sh_quote(self._remote(old))} {sh_quote(self._remote(new.strip()))}")])
            self._after()

    def delete(self) -> None:
        sel = self._selected()
        if not sel or not self.app.require_device(shell=True):
            return
        names = ", ".join(n for n, _ in sel)
        if not self.app.confirm("Удаление", f"Удалить с устройства:<br><small>{names}</small>"):
            return
        self.app.run([self.app.adb_job("shell", f"rm -rf {sh_quote(self._remote(n))}") for n, _ in sel])
        self._after()


# =========================================================================
class ApkTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(label("Перетащите сюда один или несколько APK файлов (или папку) и нажмите «Установить».", "muted"))
        self.list = DropListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.filesDropped.connect(self.add_paths)
        lay.addWidget(self.list, 1)
        self.o_replace = QCheckBox("Переустановить (-r)")
        self.o_replace.setChecked(True)
        self.o_down = QCheckBox("Разрешить даунгрейд (-d)")
        self.o_grant = QCheckBox("Выдать все разрешения (-g)")
        self.o_test = QCheckBox("Тестовые APK (-t)")
        self.o_split = QCheckBox("Как split APK одного приложения (install-multiple)")
        grid = QGridLayout()
        for i, w in enumerate([self.o_replace, self.o_down, self.o_grant, self.o_test]):
            grid.addWidget(w, 0, i)
        grid.addWidget(self.o_split, 1, 0, 1, 4)
        lay.addLayout(grid)
        lay.addLayout(hbox(
            button("➕ Добавить APK", self.browse),
            button("По ссылке…", self.from_url, tip="Скачать APK по прямой ссылке и установить"),
            button("➖ Убрать", self.remove_selected, "ghost"),
            button("🧹 Очистить", self.list.clear, "ghost"),
            None,
            button("📥 Установить", self.install, "accent"),
        ))

    def add_paths(self, paths: list[str]) -> None:
        existing = {self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())}
        for p in paths:
            pp = Path(p)
            files = sorted(x for x in pp.rglob("*") if x.suffix.lower() in (".apk",) + (".xapk", ".apks", ".apkm")) if pp.is_dir() else [pp]
            for f in files:
                if f.suffix.lower() in (".apk",) + (".xapk", ".apks", ".apkm") and str(f) not in existing:
                    kind = "  ·  бандл" if f.suffix.lower() != ".apk" else ""
                    it = QListWidgetItem(f"{f.name}   ·   {f.stat().st_size / 1048576:.1f} МБ{kind}")
                    it.setData(Qt.ItemDataRole.UserRole, str(f))
                    it.setToolTip(str(f))
                    self.list.addItem(it)
                    existing.add(str(f))

    def browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите APK", self.app.config.last_dir("apk"),
                                                "Приложения (*.apk *.xapk *.apks *.apkm)")
        if paths:
            self.app.config.remember_dir("apk", paths[0])
            self.add_paths(paths)

    def remove_selected(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def _flags(self) -> list[str]:
        f = []
        for box, flag in ((self.o_replace, "-r"), (self.o_down, "-d"), (self.o_grant, "-g"), (self.o_test, "-t")):
            if box.isChecked():
                f.append(flag)
        return f

    def install_paths(self, paths: list[str]) -> None:
        self.add_paths(paths)
        self.app.show_page(self.app.page_adb)
        self.app.page_adb.tabs.setCurrentWidget(self)
        self.install()

    def install(self) -> None:
        files = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        if not files:
            self.app.notify("Добавьте APK файлы", "warn")
            return
        if not self.app.require_device(adb=True):
            return
        bundles = [f for f in files if f.lower().endswith((".xapk", ".apks", ".apkm"))]
        files = [f for f in files if f not in bundles]
        if self.o_split.isChecked() and len(files) > 1:
            jobs = [self.app.adb_job("install-multiple", *self._flags(), *files, label="Установка split APK")]
        else:
            jobs = [self.app.adb_job("install", *self._flags(), f, label=f"Установка {Path(f).name}") for f in files]
        if jobs:
            self.app.run(jobs, stop_on_error=False)
        for b in bundles:
            self._install_bundle(b)

    def _install_bundle(self, path: str) -> None:
        from ...core.workers import BundleWorker
        worker = BundleWorker(path, self)
        self._workers = getattr(self, "_workers", []) + [worker]
        self.app.console.write(f"📦 Распаковка бандла {Path(path).name}…", "info")

        def done(apks: list, obbs: list, pkg: str) -> None:
            jobs = [self.app.adb_job("install-multiple", *self._flags(), *apks,
                                     label=f"Установка {Path(path).name} ({len(apks)} APK)")]
            for local, remote in obbs:
                jobs.append(self.app.adb_job("shell", f"mkdir -p {sh_quote(posixpath.dirname(remote))}"))
                jobs.append(self.app.adb_job("push", local, remote, label="Копирование OBB"))
            self.app.run(jobs, stop_on_error=True)

        worker.done.connect(done)
        worker.failed.connect(lambda e: (self.app.console.write(f"✖ {Path(path).name}: {e}", "fail"),
                                         self.app.notify("Не удалось распаковать бандл", "error")))
        worker.start()

    def from_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Установка по ссылке", "Прямая ссылка на .apk / .xapk / .apks:")
        url = url.strip()
        if not ok or not url.startswith(("http://", "https://")):
            return
        import tempfile
        from ...core.workers import DownloadWorker
        name = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "download.apk"
        if not name.lower().endswith((".apk",) + (".xapk", ".apks", ".apkm")):
            name += ".apk"
        dest = str(Path(tempfile.mkdtemp(prefix="droidforge-dl-")) / name)
        worker = DownloadWorker(url, dest, self)
        self._workers = getattr(self, "_workers", []) + [worker]
        self.app.console.write(f"⬇ Загрузка {name}…", "info")
        worker.done.connect(lambda p: (self.app.console.write(f"✔ Скачано: {name}", "ok"), self.install_paths([p])))
        worker.failed.connect(lambda e: (self.app.console.write(f"✖ Загрузка: {e}", "fail"),
                                         self.app.notify("Не удалось скачать файл", "error")))
        worker.start()


# =========================================================================
class TouchScreen(QLabel):
    """Shows the device screenshot; clicks become taps, drags become swipes, holds become long presses."""

    gesture = pyqtSignal(str, float, float, float, float, int)  # kind, x1, y1, x2, y2 (0..1), ms

    def __init__(self, text: str = ""):
        super().__init__(text)
        self._press: tuple[QPointF, float] | None = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def _frac(self, pos: QPointF) -> tuple[float, float] | None:
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return None
        w, h = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
        ox, oy = (self.width() - w) / 2, (self.height() - h) / 2
        x, y = (pos.x() - ox) / w, (pos.y() - oy) / h
        if not (0 <= x <= 1 and 0 <= y <= 1):
            return None
        return x, y

    KEYMAP = {Qt.Key.Key_Backspace: 67, Qt.Key.Key_Return: 66, Qt.Key.Key_Enter: 66, Qt.Key.Key_Tab: 61,
              Qt.Key.Key_Escape: 4, Qt.Key.Key_Left: 21, Qt.Key.Key_Right: 22, Qt.Key.Key_Up: 19, Qt.Key.Key_Down: 20,
              Qt.Key.Key_Delete: 112, Qt.Key.Key_Home: 3, Qt.Key.Key_PageUp: 92, Qt.Key.Key_PageDown: 93}
    typed = pyqtSignal(str, int)   # text chunk, or keycode

    def keyPressEvent(self, e) -> None:
        if e.key() in self.KEYMAP:
            self.typed.emit("", self.KEYMAP[e.key()])
        elif e.text() and e.text().isprintable():
            self.typed.emit(e.text(), 0)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._press = (e.position(), time.monotonic())

    def mouseReleaseEvent(self, e) -> None:
        if not self._press or e.button() != Qt.MouseButton.LeftButton:
            return
        start, t0 = self._press
        self._press = None
        a, b = self._frac(start), self._frac(e.position())
        if not a or not b:
            return
        ms = int((time.monotonic() - t0) * 1000)
        moved = (e.position() - start).manhattanLength() > 12
        if moved:
            self.gesture.emit("swipe", a[0], a[1], b[0], b[1], max(120, min(ms, 2000)))
        elif ms > 550:
            self.gesture.emit("swipe", a[0], a[1], a[0], a[1], 900)  # long press
        else:
            self.gesture.emit("tap", a[0], a[1], a[0], a[1], 0)


class ScreenTab(QWidget):
    KEYS = [("🏠", 3, "Домой"), ("◀", 4, "Назад"), ("▢", 187, "Недавние"), ("⏻", 26, "Питание"),
            ("🔉", 25, "Громкость −"), ("🔊", 24, "Громкость +"), ("🔇", 164, "Без звука"),
            ("🔓", 82, "Меню / разблокировка"), ("📷", 27, "Камера"), ("⏯", 85, "Play/Pause")]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.pixmap: QPixmap | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(16)

        left = QVBoxLayout()
        self.screen = TouchScreen("Нажмите «Скриншот» или включите Live.\n\nКлик — тап, перетаскивание — свайп,\nудержание — долгое нажатие.\nПосле клика можно печатать с клавиатуры ПК.")
        self.screen.gesture.connect(self._gesture)
        self.screen.typed.connect(self._typed)
        self._type_buf = ""
        self._type_timer = QTimer(self)
        self._type_timer.setSingleShot(True)
        self._type_timer.setInterval(180)
        self._type_timer.timeout.connect(self._flush_typed)
        self.live_timer = QTimer(self)
        self.live_timer.setSingleShot(True)
        self.live_timer.timeout.connect(lambda: self.take_screenshot(silent=True))
        self._shot_busy = False
        self.screen.setObjectName("screen")
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen.setMinimumSize(260, 360)
        left.addWidget(self.screen, 1)
        self.live = QCheckBox("🔴 Live")
        self.live.setToolTip("Автообновление экрана (~1 кадр/с) — управление телефоном без scrcpy")
        self.live.toggled.connect(self._toggle_live)
        left.addLayout(hbox(button("📸 Скриншот", self.take_screenshot, "accent"), self.live,
                            button("💾 Сохранить", self.save_screenshot)))
        lay.addLayout(left, 2)

        right_w = QWidget()
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 6, 0)
        right.setSpacing(14)
        c1, l1 = card("🎮 Пульт управления")
        g = QGridLayout()
        g.setSpacing(8)
        for i, (icon, code, tip) in enumerate(self.KEYS):
            g.addWidget(button(icon, lambda c=code: self.key(c), "key", tip), i // 5, i % 5)
        l1.addLayout(g)
        self.text = QLineEdit()
        self.text.setPlaceholderText("Ввести текст на устройстве…")
        self.text.returnPressed.connect(self.send_text)
        l1.addLayout(hbox(self.text, button("⌨ Отправить", self.send_text)))
        l1.addLayout(hbox(button("☀ Разбудить экран", lambda: self.key(224)),
                          button("🌙 Погасить экран", lambda: self.key(223))))
        right.addWidget(c1)

        c2, l2 = card("🎬 Запись экрана", "Видео сохраняется на устройство и автоматически скачивается.")
        self.rec_time = QSpinBox()
        self.rec_time.setRange(3, 180)
        self.rec_time.setValue(15)
        self.rec_time.setSuffix(" сек")
        l2.addLayout(hbox(label("Длительность:", "muted"), self.rec_time, None,
                          button("⏺ Записать", self.record, "danger")))
        right.addWidget(c2)

        c3, l3 = card("🖥 Зеркало экрана (scrcpy)",
                      "Управление телефоном мышью и клавиатурой в реальном времени. Нужен установленный scrcpy.")
        self.sc_off = QCheckBox("Погасить экран телефона")
        self.sc_awake = QCheckBox("Не засыпать")
        self.sc_awake.setChecked(True)
        self.sc_audio = QCheckBox("Без звука")
        self.sc_size = QComboBox()
        self.sc_size.addItems(["Оригинал", "1920", "1280", "1024", "800"])
        l3.addLayout(hbox(self.sc_off, self.sc_awake, self.sc_audio, None))
        l3.addLayout(hbox(label("Макс. размер:", "muted"), self.sc_size, None,
                          button("🌐 Скачать", lambda: QDesktopServices.openUrl(QUrl("https://github.com/Genymobile/scrcpy/releases"))),
                          button("🖥 Запустить scrcpy", self.scrcpy, "accent")))
        right.addWidget(c3)
        right.addStretch(1)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidget(right_w)
        lay.addWidget(right_scroll, 3)

    def scrcpy(self) -> None:
        exe = shutil.which("scrcpy") or self.app.config.get("scrcpy_path") or ""
        if not exe or not Path(exe).exists():
            path, _ = QFileDialog.getOpenFileName(self, "Где находится scrcpy?", str(Path.home()))
            if not path:
                self.app.notify("scrcpy не найден — скачайте его с GitHub", "warn")
                return
            exe = path
            self.app.config.set("scrcpy_path", exe)
        if not self.app.require_device(shell=True):
            return
        args = ["-s", self.app.device.serial, "--window-title", f"DroidForge · {self.app.device.title}"]
        if self.sc_off.isChecked():
            args.append("--turn-screen-off")
        if self.sc_awake.isChecked():
            args.append("--stay-awake")
        if self.sc_audio.isChecked():
            args.append("--no-audio")
        if self.sc_size.currentIndex() > 0:
            args += ["--max-size", self.sc_size.currentText()]
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("ADB", self.app.tools.adb)
        proc.setProcessEnvironment(env)
        proc.setProgram(exe)
        proc.setArguments(args)
        ok, _pid = proc.startDetached()
        self.app.console.write(f"❯ scrcpy {' '.join(args)}", "cmd")
        self.app.notify("🖥 scrcpy запущен" if ok else "Не удалось запустить scrcpy", "ok" if ok else "error")

    def key(self, code: int) -> None:
        if self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", "input", "keyevent", str(code))])

    def send_text(self) -> None:
        text = self.text.text()
        if not text or not self.app.require_device(shell=True):
            return
        escaped = re.sub(r"([\\\"'`$&|;<>()*?#~!\[\]{}])", r"\\\1", text).replace(" ", "%s")
        self.app.run([self.app.adb_job("shell", "input", "text", escaped)])
        self.text.clear()

    def take_screenshot(self, silent: bool = False) -> None:
        dev = self.app.device
        if not dev or not dev.has_shell:
            if not silent:
                self.app.require_device(shell=True)
            self.live.setChecked(False)
            return
        if self._shot_busy:
            return
        self._shot_busy = True
        if not silent and not self.pixmap:
            self.screen.setText("Получение скриншота…")
        self.app.capture_adb(["exec-out", "screencap", "-p"],
                             lambda c, d: self._on_shot(c, d, silent), merge=False, raw=True)

    def _on_shot(self, code: int, data: bytes, silent: bool = False) -> None:
        self._shot_busy = False
        pm = QPixmap()
        if code == 0 and pm.loadFromData(data, "PNG"):
            self.pixmap = pm
            self._show()
            if not silent:
                self.app.notify("📸 Скриншот получен", "ok")
        elif not silent:
            self.screen.setText("✖ Не удалось получить скриншот")
        if self.live.isChecked() and self.isVisible():
            self.live_timer.start(700)

    def _toggle_live(self, on: bool) -> None:
        if on:
            self.take_screenshot(silent=True)
        else:
            self.live_timer.stop()

    def _typed(self, text: str, code: int) -> None:
        """Keyboard focus on the screenshot: printable text is batched, special keys sent at once."""
        if not self.app.device or not self.app.device.has_shell:
            return
        if code:
            self._flush_typed()
            self.app.capture_adb(["shell", "input", "keyevent", str(code)],
                                 lambda c, o: self.live.isChecked() or QTimer.singleShot(250, lambda: self.take_screenshot(silent=True)))
        else:
            self._type_buf += text
            self._type_timer.start()

    def _flush_typed(self) -> None:
        if not self._type_buf:
            return
        txt, self._type_buf = self._type_buf, ""
        escaped = re.sub(r"([\\\"'`$&|;<>()*?#~!\[\]{}])", r"\\\1", txt).replace(" ", "%s")
        self.app.capture_adb(["shell", "input", "text", escaped], lambda c, o: None)

    def _gesture(self, kind: str, x1: float, y1: float, x2: float, y2: float, ms: int) -> None:
        if not self.pixmap or not self.app.device or not self.app.device.has_shell:
            return
        w, h = self.pixmap.width(), self.pixmap.height()
        p = [str(int(x1 * w)), str(int(y1 * h)), str(int(x2 * w)), str(int(y2 * h))]
        args = ["shell", "input", "tap", p[0], p[1]] if kind == "tap" else ["shell", "input", "swipe", *p, str(ms)]
        self.app.capture_adb(args, lambda c, o: self.live.isChecked() or QTimer.singleShot(350, lambda: self.take_screenshot(silent=True)))

    def _show(self) -> None:
        if self.pixmap:
            self.screen.setPixmap(self.pixmap.scaled(self.screen.size() * 0.97, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._show()

    def save_screenshot(self) -> None:
        if not self.pixmap:
            self.app.notify("Сначала сделайте скриншот", "warn")
            return
        name = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить скриншот",
                                              str(Path(self.app.config.last_dir("shots")) / name), "PNG (*.png)")
        if path:
            self.app.config.remember_dir("shots", path)
            self.pixmap.save(path, "PNG")
            self.app.notify(f"💾 Сохранено: {Path(path).name}", "ok")

    def record(self) -> None:
        if not self.app.require_device(shell=True):
            return
        name = f"screenrecord_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить видео",
                                              str(Path(self.app.config.last_dir("shots")) / name), "MP4 (*.mp4)")
        if not path:
            return
        self.app.config.remember_dir("shots", path)
        remote = "/sdcard/droidforge_rec.mp4"
        secs = str(self.rec_time.value())
        self.app.notify(f"⏺ Запись {secs} сек…", "info")
        self.app.run([
            self.app.adb_job("shell", "screenrecord", "--time-limit", secs, remote, label=f"Запись экрана {secs} сек"),
            self.app.adb_job("pull", remote, path, label="Скачивание видео"),
            self.app.adb_job("shell", "rm", remote, allow_fail=True),
        ])


# =========================================================================
class WifiTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        c1, l1 = card("🔗 Классический способ (через USB)",
                      "1) Подключите по USB  2) «Включить TCP/IP»  3) Отключите кабель  4) «Подключить».")
        self.ip = QLineEdit()
        self.ip.setPlaceholderText("192.168.1.42")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(5555)
        l1.addLayout(hbox(label("IP:", "muted"), self.ip, label("Порт:", "muted"), self.port,
                          button("🔍 Определить IP", self.detect_ip)))
        l1.addLayout(hbox(button("📡 Включить TCP/IP", self.tcpip), button("🔗 Подключить", self.connect, "accent"),
                          button("✂ Отключить", self.disconnect), None))
        lay.addWidget(c1)

        c2, l2 = card("📲 Беспроводная отладка (Android 11+)",
                      "Параметры разработчика → Беспроводная отладка → «Подключить по коду». "
                      "Введите адрес и код из окна сопряжения, затем подключитесь по адресу из главного экрана.")
        self.pair_addr = QLineEdit()
        self.pair_addr.setPlaceholderText("192.168.1.42:37123")
        self.pair_code = QLineEdit()
        self.pair_code.setPlaceholderText("123456")
        self.pair_code.setMaxLength(6)
        self.pair_code.setFixedWidth(110)
        l2.addLayout(hbox(label("Адрес:", "muted"), self.pair_addr, label("Код:", "muted"), self.pair_code,
                          button("🤝 Сопрячь", self.pair, "accent")))
        self.conn_addr = QLineEdit()
        self.conn_addr.setPlaceholderText("192.168.1.42:41567")
        l2.addLayout(hbox(label("Подключение:", "muted"), self.conn_addr,
                          button("🔗 Подключить", lambda: self._connect_addr(self.conn_addr.text().strip()))))
        lay.addWidget(c2)
        lay.addStretch(1)

    def detect_ip(self) -> None:
        if self.app.require_device(shell=True):
            self.app.capture_adb(["shell", "ip -f inet addr show wlan0"], self._on_ip)

    def _on_ip(self, code: int, out: str) -> None:
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
        if m:
            self.ip.setText(m.group(1))
            self.app.notify(f"IP: {m.group(1)}", "ok")
        else:
            self.app.notify("Не удалось определить IP (Wi‑Fi включён?)", "warn")

    def tcpip(self) -> None:
        if self.app.require_device(adb=True):
            self.app.run([self.app.adb_job("tcpip", str(self.port.value()))])

    def connect(self) -> None:
        ip = self.ip.text().strip()
        if not ip:
            self.app.notify("Введите IP адрес", "warn")
            return
        self._connect_addr(f"{ip}:{self.port.value()}")

    def _connect_addr(self, addr: str) -> None:
        if addr:
            self.app.run([self.app.adb_job("connect", addr, serial=False)])

    def disconnect(self) -> None:
        ip = self.ip.text().strip()
        args = ["disconnect"] + ([f"{ip}:{self.port.value()}"] if ip else [])
        self.app.run([self.app.adb_job(*args, serial=False)])

    def pair(self) -> None:
        addr, code = self.pair_addr.text().strip(), self.pair_code.text().strip()
        if not addr or not code:
            self.app.notify("Введите адрес и код сопряжения", "warn")
            return
        self.app.run([self.app.adb_job("pair", addr, code, serial=False)])


# =========================================================================
class PermissionsDialog(QDialog):
    """Runtime permissions of one app: checkbox = granted, toggling calls pm grant / revoke."""

    PERM_RE = re.compile(r"^\s*([\w.]+\.permission\.[\w.]+): granted=(true|false)")

    def __init__(self, app, pkg: str, parent=None):
        super().__init__(parent)
        self.app, self.pkg = app, pkg
        self.setWindowTitle(f"Разрешения · {pkg}")
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"🔑 {pkg}", "h2"))
        lay.addWidget(label("Отметка = разрешение выдано. Изменения применяются сразу.", "muted"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 Фильтр…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._toggled)
        lay.addWidget(self.list, 1)
        self.status = label("Загрузка…", "muted")
        lay.addLayout(hbox(self.status, None,
                           button("✅ Выдать все", lambda: self._all(True)),
                           button("🚫 Отозвать все", lambda: self._all(False), "danger"),
                           button("↺ Сбросить", self._reset, tip="pm reset-permissions — вернуть по умолчанию"),
                           button("Закрыть", self.accept)))
        self._loading = True
        self.load()

    def load(self) -> None:
        self.app.capture_adb(["shell", f"dumpsys package {self.pkg}"], self._on_dump, timeout=20000)

    def _on_dump(self, code: int, out: str) -> None:
        perms: dict[str, bool] = {}
        section = False
        for line in out.splitlines():
            if "runtime permissions:" in line:
                section = True
                continue
            if section:
                m = self.PERM_RE.match(line)
                if m:
                    perms[m.group(1)] = m.group(2) == "true"
                elif line.strip() and not line.startswith(" " * 6):
                    section = False
        self._loading = True
        self.list.clear()
        for name, granted in sorted(perms.items()):
            short = name.split(".permission.")[-1]
            it = QListWidgetItem(f"{short}    ·    {name}")
            it.setData(Qt.ItemDataRole.UserRole, name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if granted else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        self._loading = False
        granted = sum(perms.values())
        self.status.setText(f"Выдано {granted} из {len(perms)}" if perms else "Нет runtime‑разрешений")
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        text = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(text) and text not in it.text().lower())

    def _toggled(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        verb = "grant" if item.checkState() == Qt.CheckState.Checked else "revoke"
        perm = item.data(Qt.ItemDataRole.UserRole)
        self.app.capture_adb(["shell", "pm", verb, self.pkg, perm], self._after_change)

    def _after_change(self, code: int, out: str) -> None:
        if code != 0 or "Exception" in out:
            self.app.notify(f"Не удалось изменить: {out.strip()[:120]}", "error")
            self.load()

    def _all(self, grant: bool) -> None:
        verb = "grant" if grant else "revoke"
        cmds = [f"pm {verb} {self.pkg} {self.list.item(i).data(Qt.ItemDataRole.UserRole)}"
                for i in range(self.list.count())]
        if cmds:
            self.app.capture_adb(["shell", "; ".join(cmds)], lambda c, o: self.load(), timeout=30000)

    def _reset(self) -> None:
        self.app.capture_adb(["shell", "pm", "reset-permissions", "-p", self.pkg], lambda c, o: self.load())
