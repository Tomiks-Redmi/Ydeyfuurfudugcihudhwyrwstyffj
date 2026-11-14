"""Bottom console: colored live output + command line with history and completion."""
from __future__ import annotations

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QCompleter, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QProgressBar, QVBoxLayout,
)

from . import theme
from .widgets import button, label

COLORS = {
    "cmd": theme.ACCENT_2,
    "out": "#c9cfdd",
    "err": "#aeb6c8",
    "ok": theme.SUCCESS,
    "fail": theme.DANGER,
    "info": "#9d8bff",
    "warn": theme.WARN,
}
RE_FAIL = re.compile(r"\b(FAILED|error|Error|ERROR|failed|Failure|denied|not found|cannot)\b")
RE_OK = re.compile(r"\b(OKAY|Success|Finished|Total time|success)\b")
RE_WARN = re.compile(r"(waiting for|WARNING|Warning|unauthorized|offline)")


class HistoryLineEdit(QLineEdit):
    def __init__(self, history: list[str], parent=None):
        super().__init__(parent)
        self.history = history
        self._pos = len(history)

    def add(self, cmd: str) -> None:
        if cmd and (not self.history or self.history[-1] != cmd):
            self.history.append(cmd)
            del self.history[:-200]
        self._pos = len(self.history)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        popup = self.completer().popup() if self.completer() else None
        if popup is not None and popup.isVisible():
            super().keyPressEvent(e)
            return
        if e.key() == Qt.Key.Key_Up and self.history:
            self._pos = max(0, self._pos - 1)
            self.setText(self.history[self._pos])
        elif e.key() == Qt.Key.Key_Down and self.history:
            self._pos = min(len(self.history), self._pos + 1)
            self.setText(self.history[self._pos] if self._pos < len(self.history) else "")
        else:
            super().keyPressEvent(e)


class Console(QFrame):
    commandEntered = pyqtSignal(str)
    lineWritten = pyqtSignal(str, str)
    stopRequested = pyqtSignal()

    def __init__(self, history: list[str], completions: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("consoleFrame")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(8)

        # header
        self.status = label("Готов", "muted")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setFormat("%v / %m")
        self.progress.hide()
        self.stop_btn = button("⏹ Стоп", self.stopRequested.emit, "danger", "Остановить выполнение (Esc)")
        self.stop_btn.setEnabled(False)
        head = QHBoxLayout()
        head.addWidget(label("🖥  Консоль", "cardTitle"))
        head.addSpacing(12)
        head.addWidget(self.status)
        head.addStretch(1)
        head.addWidget(self.progress)
        head.addWidget(self.stop_btn)
        head.addWidget(button("📋", self.copy_all, "ghost", "Копировать всё"))
        head.addWidget(button("🧹", self.clear, "ghost", "Очистить"))
        lay.addLayout(head)

        self.view = QPlainTextEdit()
        self.view.setObjectName("console")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(8000)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        prompt = QLabel("❯")
        prompt.setObjectName("prompt")
        self.input = HistoryLineEdit(history)
        self.input.setObjectName("consoleInput")
        self.input.setPlaceholderText("Введите команду: adb shell getprop ro.product.model   ·   fastboot getvar all   ·   ↑↓ история")
        completer = QCompleter(completions, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.input.setCompleter(completer)
        self.input.returnPressed.connect(self._submit)
        self.broadcast = QCheckBox("📡 На все")
        self.broadcast.setToolTip("Выполнить команду на всех подключённых устройствах в подходящем режиме")
        row.addWidget(prompt)
        row.addWidget(self.input, 1)
        row.addWidget(self.broadcast)
        row.addWidget(button("▶ Выполнить", self._submit, "accent"))
        lay.addLayout(row)

        self._fmt_cache: dict[tuple[str, bool], QTextCharFormat] = {}

    # ------------------------------------------------------------------
    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.add(text)
        self.input.clear()
        self.commandEntered.emit(text)

    def _fmt(self, color: str, bold: bool) -> QTextCharFormat:
        key = (color, bold)
        if key not in self._fmt_cache:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            self._fmt_cache[key] = f
        return self._fmt_cache[key]

    def write(self, text: str, kind: str = "out") -> None:
        self.lineWritten.emit(text, kind)
        if kind in ("out", "err"):
            if RE_FAIL.search(text):
                color = theme.DANGER
            elif RE_OK.search(text):
                color = theme.SUCCESS
            elif RE_WARN.search(text):
                color = theme.WARN
            else:
                color = COLORS[kind]
        else:
            color = COLORS.get(kind, COLORS["out"])
        bold = kind in ("cmd", "ok", "fail")
        sb = self.view.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        cursor = QTextCursor(self.view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.view.document().isEmpty():
            cursor.insertBlock()
            if kind == "cmd":
                cursor.insertBlock()  # visual gap before each new command
        cursor.insertText(text, self._fmt(color, bold))
        if at_bottom:
            sb.setValue(sb.maximum())

    def set_busy(self, busy: bool) -> None:
        self.stop_btn.setEnabled(busy)
        self.status.setText("⏳ Выполняется…" if busy else "Готов")
        if not busy:
            self.progress.hide()

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setVisible(total > 1)
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def clear(self) -> None:
        self.view.clear()

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self.view.toPlainText())

    def focus_input(self, text: str | None = None) -> None:
        if text is not None:
            self.input.setText(text)
        self.input.setFocus()
        self.input.end(False)
