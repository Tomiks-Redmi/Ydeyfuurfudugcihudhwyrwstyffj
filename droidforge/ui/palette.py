"""Command palette (Ctrl+K): fuzzy search over pages, tools, commands and actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QDialog, QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .widgets import label


@dataclass
class PaletteItem:
    icon: str
    title: str
    group: str
    action: Callable[[], None]
    hint: str = ""

    @property
    def haystack(self) -> str:
        return f"{self.title} {self.group} {self.hint}".lower()


class CommandPalette(QDialog):
    def __init__(self, parent, items_provider: Callable[[], list[PaletteItem]]):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.items_provider = items_provider
        self.items: list[PaletteItem] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(objectName="palette")
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        self.input = QLineEdit(objectName="paletteInput")
        self.input.setPlaceholderText("🔎  Что сделать?  Страница, инструмент, команда, перезагрузка…")
        self.input.textChanged.connect(self._refresh)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)
        self.list = QListWidget(objectName="paletteList")
        self.list.itemActivated.connect(self._run)
        self.list.itemClicked.connect(self._run)
        lay.addWidget(self.list, 1)
        self.footer = label("↑↓ выбор   ·   Enter выполнить   ·   Esc закрыть", "muted")
        self.footer.setContentsMargins(16, 4, 16, 0)
        self.footer.setStyleSheet("font-size: 8.5pt;")
        lay.addWidget(self.footer)

    def open(self) -> None:  # noqa: A003 - Qt naming
        self.items = self.items_provider()
        parent = self.parentWidget()
        w = min(680, parent.width() - 80)
        self.resize(w, min(500, parent.height() - 120))
        top_left = parent.mapToGlobal(parent.rect().topLeft())
        self.move(top_left.x() + (parent.width() - w) // 2, top_left.y() + 70)
        self.input.clear()
        self._refresh("")
        self.show()
        self.activateWindow()
        self.input.setFocus()

    def _refresh(self, text: str) -> None:
        words = text.lower().split()
        self.list.clear()
        shown = 0
        for item in self.items:
            if all(w in item.haystack for w in words):
                it = QListWidgetItem(f"{item.icon}   {item.title}      ·  {item.group}")
                it.setToolTip(item.hint or item.group)
                it.setData(Qt.ItemDataRole.UserRole, item)
                self.list.addItem(it)
                shown += 1
                if shown >= 60:
                    break
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.list.addItem(QListWidgetItem("Ничего не найдено"))

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.list.currentItem():
                    self._run(self.list.currentItem())
                return True
            if key == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def _run(self, it: QListWidgetItem) -> None:
        item = it.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item, PaletteItem):
            return
        self.close()
        item.action()
