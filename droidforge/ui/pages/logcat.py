"""Live logcat viewer with level/text/package filters."""
from __future__ import annotations

import re
import time
from collections import deque

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from .. import theme
from ..widgets import button, hbox, label, page_header

LEVELS = "VDIWEF"
LEVEL_COLORS = {"V": "#6b7387", "D": "#8fb3ff", "I": "#c9cfdd", "W": theme.WARN, "E": theme.DANGER, "F": "#ff3df2"}
LINE_RE = re.compile(r"^\S+\s+\S+\s+\d+\s+\d+\s+([VDIWEFS])\s")
MAX_LINES = 30000


class LogcatPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.proc: QProcess | None = None
        self.lines: deque[tuple[str, str]] = deque(maxlen=MAX_LINES)
        self.pending: list[tuple[str, str]] = []
        self._partial = ""
        self._formats = {lv: self._fmt(c) for lv, c in LEVEL_COLORS.items()}
        self._formats["?"] = self._fmt("#aeb6c8")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(12)
        lay.addLayout(page_header("📜 Logcat", "Живой журнал устройства с цветовой подсветкой и фильтрами."))

        self.start_btn = button("▶ Старт", self.toggle, "accent")
        self.level = QComboBox()
        for lv, name in zip(LEVELS, ["Verbose", "Debug", "Info", "Warning", "Error", "Fatal"]):
            self.level.addItem(f"{lv} · {name}", lv)
        self.level.currentIndexChanged.connect(self.rerender)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("🔎 Фильтр (текст или regex)…")
        self.filter.textChanged.connect(lambda _: self._filter_timer.start())
        self.regex = QCheckBox("Regex")
        self.regex.toggled.connect(self.rerender)
        self.package = QLineEdit()
        self.package.setPlaceholderText("пакет (опц.)")
        self.package.setFixedWidth(190)
        self.package.setToolTip("Показывать только логи процесса этого приложения (по PID, применяется при старте)")
        self.autoscroll = QCheckBox("Автопрокрутка")
        self.autoscroll.setChecked(True)
        self.crash_btn = button("Только сбои", self.crash_filter, "ghost",
                                "Показать только падения приложений, ANR и нативные сбои")
        top = hbox(self.start_btn, self.level, self.filter, self.regex, self.package, self.crash_btn)
        top.setStretch(2, 1)
        lay.addLayout(top)

        self.view = QPlainTextEdit()
        self.view.setObjectName("logcat")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(10000)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.view, 1)

        self.stats = label("Остановлено", "muted")
        lay.addLayout(hbox(self.stats, None, self.autoscroll,
                           button("🧹 Очистить", self.clear), button("🗑 Очистить буфер устройства", self.clear_device, "ghost"),
                           button("💾 Сохранить", self.save)))

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(120)
        self._flush_timer.timeout.connect(self.flush)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self.rerender)

    @staticmethod
    def _fmt(color: str) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        return f

    # ------------------------------------------------------------------
    def toggle(self) -> None:
        if self.proc:
            self.stop()
            return
        if not self.app.require_device(adb=True):
            return
        pkg = self.package.text().strip()
        if pkg:
            self.app.capture_adb(["shell", "pidof", pkg], lambda c, out: self._start(out.split()[0] if out.split() and out.split()[0].isdigit() else None, pkg))
        else:
            self._start(None, "")

    def _start(self, pid: str | None, pkg: str) -> None:
        if pkg and not pid:
            self.app.notify(f"Процесс {pkg} не запущен", "warn")
            return
        args = self.app._serial_args() + ["logcat", "-v", "threadtime"]
        if pid:
            args.append(f"--pid={pid}")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._on_finished)
        self.proc.start(self.app.tools.adb, args)
        self._flush_timer.start()
        self.start_btn.setText("Стоп")
        self.start_btn.setProperty("kind", "danger")
        self._repolish()
        self.stats.setText("● Запись…" + (f"  (PID {pid})" if pid else ""))

    def stop(self) -> None:
        if self.proc:
            self.proc.finished.disconnect()
            self.proc.kill()
            self.proc.waitForFinished(1000)
            self.proc.deleteLater()
            self.proc = None
        self._on_finished()

    def _on_finished(self, *_):
        if self.proc:
            self.proc.deleteLater()
            self.proc = None
        self.flush()
        self._flush_timer.stop()
        self.start_btn.setText("Старт")
        self.start_btn.setProperty("kind", "accent")
        self._repolish()
        self.stats.setText(f"Остановлено · строк в буфере: {len(self.lines)}")

    def crash_filter(self) -> None:
        if self.regex.isChecked() and "FATAL" in self.filter.text():
            self.filter.clear()
            self.regex.setChecked(False)
            return
        self.level.setCurrentIndex(0)
        self.regex.setChecked(True)
        self.filter.setText(r"FATAL EXCEPTION|AndroidRuntime|ANR in|Fatal signal|DEBUG\s*:|Process: ")

    def _repolish(self) -> None:
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def _read(self) -> None:
        data = self._partial + bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        parts = data.split("\n")
        self._partial = parts.pop()
        for line in parts:
            line = line.rstrip("\r")
            if not line:
                continue
            m = LINE_RE.match(line)
            lv = m.group(1) if m else "?"
            entry = (lv, line)
            self.lines.append(entry)
            self.pending.append(entry)

    # ------------------------------------------------------------------
    def _matcher(self):
        min_level = LEVELS.index(self.level.currentData())
        text = self.filter.text()
        rx = None
        if text and self.regex.isChecked():
            try:
                rx = re.compile(text, re.IGNORECASE)
            except re.error:
                rx = None
        low = text.lower()

        def match(lv: str, line: str) -> bool:
            if lv in LEVELS and LEVELS.index(lv) < min_level:
                return False
            if not text:
                return True
            return bool(rx.search(line)) if rx else low in line.lower()
        return match

    def _append(self, entries) -> None:
        if not entries:
            return
        match = self._matcher()
        sb = self.view.verticalScrollBar()
        cursor = QTextCursor(self.view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.beginEditBlock()
        for lv, line in entries:
            if match(lv, line):
                if not self.view.document().isEmpty():
                    cursor.insertBlock()
                cursor.insertText(line, self._formats.get(lv, self._formats["?"]))
        cursor.endEditBlock()
        if self.autoscroll.isChecked():
            sb.setValue(sb.maximum())

    def flush(self) -> None:
        entries, self.pending = self.pending, []
        self._append(entries[-5000:])
        if self.proc:
            self.stats.setText(f"● Запись…  строк: {len(self.lines)}")

    def rerender(self, *_):
        self.view.clear()
        self.pending.clear()
        self._append(list(self.lines)[-10000:])

    def clear(self) -> None:
        self.lines.clear()
        self.pending.clear()
        self.view.clear()

    def clear_device(self) -> None:
        if self.app.require_device(adb=True):
            self.app.run([self.app.adb_job("logcat", "-c")])
            self.clear()

    def save(self) -> None:
        name = f"logcat_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить лог", name, "Текст (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(line for _lv, line in self.lines))
            self.app.notify("💾 Лог сохранён", "ok")

    def shutdown(self) -> None:
        if self.proc:
            self.stop()
