"""Extra ADB tabs: live process manager, port forwarding, on-device text file editor."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QHeaderView, QLineEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..widgets import button, hbox, label
from .adb_tools import sh_quote


class _NumItem(QTableWidgetItem):
    """Table item that sorts numerically."""

    def __lt__(self, other) -> bool:
        try:
            return float(self.data(Qt.ItemDataRole.UserRole)) < float(other.data(Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return super().__lt__(other)


def _num(value: float, text: str) -> _NumItem:
    it = _NumItem(text)
    it.setData(Qt.ItemDataRole.UserRole, value)
    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it


# =========================================================================
class ProcessesTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Фильтр по имени процесса или пользователю")
        self.filter.textChanged.connect(self._apply_filter)
        self.only_apps = QCheckBox("Только приложения")
        self.only_apps.setChecked(True)
        self.only_apps.toggled.connect(self._apply_filter)
        self.auto = QCheckBox("Автообновление")
        self.auto.toggled.connect(lambda on: self.timer.start() if on else self.timer.stop())
        self.count = label("", "muted")
        row = hbox(self.filter, self.only_apps, self.auto, self.count, button("Обновить", self.refresh))
        row.setStretch(0, 1)
        lay.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["PID", "Пользователь", "CPU %", "Память", "Процесс"])
        hh = self.table.horizontalHeader()
        for i in range(4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table, 1)
        lay.addLayout(hbox(label("Сортировка — клик по заголовку столбца.", "muted"), None,
                           button("Остановить приложение", self.force_stop),
                           button("Завершить (kill)", lambda: self.kill(False)),
                           button("Завершить через root", lambda: self.kill(True), "danger")))
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(lambda: self.isVisible() and self.refresh())

    def refresh(self) -> None:
        dev = self.app.device
        if not dev or not dev.has_shell:
            if not self.auto.isChecked():
                self.app.require_device(shell=True)
            return
        if self._busy:
            return
        self._busy = True
        self.app.capture_adb(["shell", "ps -A -o PID,USER,%CPU,RSS,NAME 2>/dev/null || ps -A"], self._on_ps)

    def _on_ps(self, code: int, out: str) -> None:
        self._busy = False
        lines = [l.split(None, 4) for l in out.splitlines()[1:] if l.strip()]
        rows = []
        for parts in lines:
            if len(parts) < 5:
                continue
            pid, user, cpu, rss, name = parts
            if not pid.isdigit():
                continue
            try:
                cpu_f = float(cpu.rstrip("%"))
            except ValueError:  # fallback "ps -A" layout: USER PID PPID VSZ RSS ... NAME
                user, pid = parts[0], parts[1]
                cpu_f, rss, name = 0.0, parts[4].split()[0] if parts[4].split() else "0", parts[4].split()[-1]
            rows.append((int(pid), user, cpu_f, int(rss) if rss.isdigit() else 0, name))
        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, (pid, user, cpu, rss, name) in enumerate(rows):
            self.table.setItem(r, 0, _num(pid, str(pid)))
            self.table.setItem(r, 1, QTableWidgetItem(user))
            self.table.setItem(r, 2, _num(cpu, f"{cpu:.1f}"))
            self.table.setItem(r, 3, _num(rss, f"{rss / 1024:.0f} МБ" if rss >= 1024 else f"{rss} КБ"))
            self.table.setItem(r, 4, QTableWidgetItem(name))
        self.table.setSortingEnabled(True)
        if self.table.property("sorted"):
            self.table.sortItems(sort_col, sort_order)
        else:
            self.table.sortItems(2, Qt.SortOrder.DescendingOrder)
            self.table.setProperty("sorted", True)
        self._apply_filter()

    def _apply_filter(self, *_):
        text = self.filter.text().lower()
        apps_only = self.only_apps.isChecked()
        shown = 0
        for r in range(self.table.rowCount()):
            user = self.table.item(r, 1).text()
            name = self.table.item(r, 4).text()
            hide = (bool(text) and text not in name.lower() and text not in user.lower()) or \
                   (apps_only and not (user.startswith("u0_") or "." in name))
            self.table.setRowHidden(r, hide)
            shown += not hide
        self.count.setText(f"{shown} / {self.table.rowCount()}")

    def _selected(self) -> list[tuple[str, str]]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [(self.table.item(r, 0).text(), self.table.item(r, 4).text()) for r in rows]

    def force_stop(self) -> None:
        sel = [name.split(":")[0] for _, name in self._selected() if "." in name]
        if sel and self.app.require_device(shell=True):
            self.app.run([self.app.adb_job("shell", "am", "force-stop", n) for n in sel], stop_on_error=False)
            QTimer.singleShot(800, self.refresh)

    def kill(self, root: bool) -> None:
        sel = self._selected()
        if not sel or not self.app.require_device(shell=True):
            return
        if root and not self.app.confirm("Завершить процессы", "Принудительно завершить через root: "
                                         + ", ".join(n for _, n in sel) + "?"):
            return
        jobs = [self.app.adb_job("shell", f"su -c 'kill -9 {pid}'" if root else f"kill {pid}", allow_fail=True)
                for pid, _ in sel]
        self.app.run(jobs, stop_on_error=False)
        QTimer.singleShot(800, self.refresh)


# =========================================================================
class PortsTab(QWidget):
    PRESETS = [
        ("Chrome DevTools (отладка вкладок)", "forward", "tcp:9222", "localabstract:chrome_devtools_remote"),
        ("Metro / React Native (8081)", "reverse", "tcp:8081", "tcp:8081"),
        ("Локальный сервер ПК → телефон (3000)", "reverse", "tcp:3000", "tcp:3000"),
        ("Flutter / Dart VM (8181)", "forward", "tcp:8181", "tcp:8181"),
    ]

    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        lay.addWidget(label("<b>forward</b> — порт ПК ведёт на телефон, <b>reverse</b> — порт телефона ведёт на ПК "
                            "(удобно для локального сервера разработки).", "muted", wrap=True))
        self.kind = QComboBox()
        self.kind.addItems(["forward", "reverse"])
        self.local = QLineEdit("tcp:8080")
        self.remote = QLineEdit("tcp:8080")
        lay.addLayout(hbox(self.kind, label("ПК / слушает:", "muted"), self.local, label("→", "muted"), self.remote,
                           button("Добавить", self.add, "accent")))
        self.preset = QComboBox()
        self.preset.addItem("Готовые варианты…")
        for name, *_ in self.PRESETS:
            self.preset.addItem(name)
        self.preset.activated.connect(self._preset)
        lay.addLayout(hbox(self.preset, None, button("Обновить", self.refresh)))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Тип", "Откуда", "Куда"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table, 1)
        lay.addLayout(hbox(None, button("Удалить выбранное", self.remove), button("Удалить все", self.remove_all, "danger")))

    def _preset(self, idx: int) -> None:
        if idx <= 0:
            return
        _name, kind, local, remote = self.PRESETS[idx - 1]
        self.kind.setCurrentText(kind)
        self.local.setText(local)
        self.remote.setText(remote)
        self.preset.setCurrentIndex(0)

    def refresh(self) -> None:
        if not self.app.require_device(adb=True):
            return
        self.app.capture_adb(["forward", "--list"], lambda c, out: self._on_list("forward", out))

    def _on_list(self, kind: str, out: str) -> None:
        serial = self.app.device.serial if self.app.device else ""
        rows = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3 and (kind == "reverse" or parts[0] == serial):
                rows.append((kind, parts[1], parts[2]))
            elif len(parts) == 2 and kind == "reverse":
                rows.append((kind, parts[0], parts[1]))
        if kind == "forward":
            self._forward = rows
            self.app.capture_adb(["reverse", "--list"], lambda c, o: self._on_list("reverse", o))
            return
        allrows = self._forward + rows
        self.table.setRowCount(len(allrows))
        for r, row in enumerate(allrows):
            for c, v in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def add(self) -> None:
        local, remote = self.local.text().strip(), self.remote.text().strip()
        if not local or not remote or not self.app.require_device(adb=True):
            return
        self.app.run([self.app.adb_job(self.kind.currentText(), local, remote)])
        self.app.after_queue(self.refresh)

    def remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        jobs = [self.app.adb_job(self.table.item(r, 0).text(), "--remove", self.table.item(r, 1).text(), allow_fail=True)
                for r in rows]
        if jobs:
            self.app.run(jobs, stop_on_error=False)
            self.app.after_queue(self.refresh)

    def remove_all(self) -> None:
        if self.app.require_device(adb=True):
            self.app.run([self.app.adb_job("forward", "--remove-all", allow_fail=True),
                          self.app.adb_job("reverse", "--remove-all", allow_fail=True)], stop_on_error=False)
            self.app.after_queue(self.refresh)


# =========================================================================
class TextEditorDialog(QDialog):
    """Edit a text file on the device: cat → edit → push back (optionally via root)."""

    MAX = 2 * 1024 * 1024

    def __init__(self, app, remote: str, parent=None):
        super().__init__(parent)
        self.app, self.remote = app, remote
        self.setWindowTitle(f"Редактор · {remote}")
        self.resize(820, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(label(remote, "cardTitle"))
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("console")
        f = QFont("JetBrains Mono, Consolas, DejaVu Sans Mono, monospace")
        f.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(f)
        self.editor.setPlaceholderText("Загрузка…")
        lay.addWidget(self.editor, 1)
        self.root = QCheckBox("Записать через root (для системных файлов)")
        self.status = label("", "muted")
        lay.addLayout(hbox(self.root, self.status, None, button("Отмена", self.reject, "ghost"),
                           button("Сохранить на устройство", self.save, "accent")))
        app.capture_adb(["shell", f"cat {sh_quote(remote)} 2>&1 | head -c {self.MAX}"], self._loaded)

    def _loaded(self, code: int, out: str) -> None:
        if "Permission denied" in out[:200] or "No such file" in out[:200]:
            self.status.setText(out.strip()[:120])
            self.root.setChecked(True)
            self.app.capture_adb(["shell", f"su -c 'cat {sh_quote(self.remote)}'"], self._loaded_root)
            return
        self.editor.setPlainText(out)
        self.status.setText(f"{len(out.splitlines())} строк")

    def _loaded_root(self, code: int, out: str) -> None:
        if code == 0:
            self.editor.setPlainText(out)
            self.status.setText("Открыто через root")
        else:
            self.status.setText("Нет доступа к файлу")

    def save(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="droidforge-edit-")) / Path(self.remote).name
        tmp.write_text(self.editor.toPlainText(), encoding="utf-8", newline="\n")
        if self.root.isChecked():
            stage = f"/data/local/tmp/{tmp.name}"
            jobs = [self.app.adb_job("push", str(tmp), stage, label=f"Сохранение {self.remote}"),
                    self.app.adb_job("shell", f"su -c 'cat {sh_quote(stage)} > {sh_quote(self.remote)}' && rm {sh_quote(stage)}")]
        else:
            jobs = [self.app.adb_job("push", str(tmp), self.remote, label=f"Сохранение {self.remote}")]
        self.app.run(jobs)
        self.accept()

