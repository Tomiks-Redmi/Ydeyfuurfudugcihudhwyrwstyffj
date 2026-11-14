"""Popup with recent command queues: status, duration, and one-click repeat."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QListWidget, QListWidgetItem, QVBoxLayout

from ..core.runner import ECHO, SLEEP, Job
from . import icons
from .widgets import button, hbox, label

DANGER_WORDS = ("flash", "erase", "-w", "set_active", "unlock", "lock", "dd ", "uninstall", "rm ", "format", "update")


@dataclass
class HistoryEntry:
    started: float
    duration: float
    ok: bool
    jobs: list[Job] = field(default_factory=list)

    @property
    def commands(self) -> list[Job]:
        return [j for j in self.jobs if j.program not in (ECHO, SLEEP)]

    @property
    def title(self) -> str:
        labelled = next((j.label for j in self.jobs if j.label), "")
        cmds = self.commands
        base = labelled or (cmds[0].display() if cmds else "сценарий")
        return base if len(base) < 70 else base[:67] + "…"

    @property
    def dangerous(self) -> bool:
        return any(w in " ".join(j.args) for j in self.jobs for w in DANGER_WORDS)


class HistoryPopup(QDialog):
    def __init__(self, app):
        super().__init__(app, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(objectName="palette")
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.addLayout(hbox(label("История операций", "cardTitle"), None,
                           button("Очистить", self._clear, "ghost")))
        self.list = QListWidget(objectName="paletteList")
        self.list.itemActivated.connect(self._repeat)
        self.list.itemDoubleClicked.connect(self._repeat)
        lay.addWidget(self.list, 1)
        lay.addWidget(label("Двойной клик или Enter — повторить операцию", "muted"))

    def open_at(self, anchor) -> None:
        self.list.clear()
        entries = list(reversed(self.app.history))
        for e in entries:
            when = time.strftime("%H:%M:%S", time.localtime(e.started))
            n = len(e.commands)
            it = QListWidgetItem(f"{e.title}\n{when}  ·  команд: {n}  ·  {e.duration:.1f} с")
            it.setIcon(icons.icon("check" if e.ok else "x", "accent" if e.ok else "danger"))
            it.setData(Qt.ItemDataRole.UserRole, e)
            it.setToolTip("\n".join(j.display() for j in e.commands[:25]))
            self.list.addItem(it)
        if not entries:
            self.list.addItem(QListWidgetItem("Пока пусто — выполненные команды появятся здесь"))
        self.resize(560, 420)
        pos = anchor.mapToGlobal(anchor.rect().bottomRight())
        self.move(pos.x() - self.width(), pos.y() + 6)
        self.show()
        self.list.setFocus()
        if self.list.count():
            self.list.setCurrentRow(0)

    def _repeat(self, item: QListWidgetItem) -> None:
        e = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(e, HistoryEntry):
            return
        self.close()
        if e.dangerous and not self.app.confirm("Повторить операцию",
                                                "Операция содержит прошивку / удаление данных:<br><small>"
                                                + "<br>".join(j.display() for j in e.commands[:8]) + "</small>"):
            return
        self.app.run([Job(j.program, list(j.args), j.label, j.allow_fail) for j in e.jobs])

    def _clear(self) -> None:
        self.app.history.clear()
        self.list.clear()
