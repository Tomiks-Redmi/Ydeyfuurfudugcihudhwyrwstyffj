"""Reusable widgets and small helpers."""
from __future__ import annotations

import re

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import icons, theme

# Leading emoji / pictographs / dingbats (plus keycaps, ZWJ, variation selectors) are stripped from UI
# text for the minimal look. Text that consists only of such symbols is left untouched.
_EMOJI = (r"[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u2460-\u24FF\u25A0-\u27FF\u2900-\u297F"
          r"\u2B00-\u2BFF\uFE0F\u200D\u20E3]|[0-9#*]\uFE0F?\u20E3")
_LEAD = re.compile(rf"^(?:{_EMOJI}|\s)+")
_GLYPH_ICONS = {
    "⟳": "refresh", "🔄": "refresh", "🕘": "history", "☀": "sun", "🌙": "moon", "📋": "copy", "🧹": "trash",
    "▾": "chevron-down", "▴": "chevron-up", "←": "arrow-left", "✖": "x", "⬆": "chevron-up", "💾": "save",
    "🗑": "trash", "🏠": "home", "◀": "chevron-left", "▢": "square", "⏻": "power", "🔉": "vol-down",
    "🔊": "vol-up", "🔇": "mute", "🔓": "unlock", "📷": "camera", "⏯": "playpause", "»": "chevron-right",
}


def clean(text: str) -> str:
    """Strip leading emoji for the minimal style (keeps symbol-only strings)."""
    if not text:
        return text
    rest = _LEAD.sub("", text)
    return rest if rest.strip() else text


def strip_all(text: str) -> str:
    """Remove emoji anywhere in a short UI string (used for tabs, checkboxes, combo items)."""
    out = re.sub(_EMOJI, "", text)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out or text


def button(text: str, slot: Callable | None = None, kind: str | None = None,
           tip: str | None = None, icon: str | None = None) -> QPushButton:
    glyph = text.strip()
    if icon is None and glyph in _GLYPH_ICONS:
        icon, text = _GLYPH_ICONS[glyph], ""
        kind = kind if kind in ("icon", "key", "danger") else "icon"
    b = QPushButton(clean(text))
    if icon:
        icons.bind(b, icon, "white" if kind == "accent" else "danger" if kind == "danger" else "muted", 17)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        b.setProperty("kind", kind)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(lambda _=False: slot())
    return b


_CLEAN_NAMES = {"h1", "h2", "cardTitle", "category", "toolTitle", "tileTitle", "crumb", "devName"}


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(clean(text) if name in _CLEAN_NAMES else text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def card(title: str | None = None, subtitle: str | None = None,
         name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    if title:
        lay.addWidget(label(title, "cardTitle"))
    if subtitle:
        lay.addWidget(label(subtitle, "muted", wrap=True))
    return frame, lay


def hbox(*widgets, spacing: int = 8, stretch_end: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    if stretch_end:
        lay.addStretch(1)
    return lay


def page_header(title: str, subtitle: str) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(2)
    lay.addWidget(label(title, "h1"))
    lay.addWidget(label(subtitle, "muted", wrap=True))
    return lay


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def _dropped_paths(event: QDropEvent | QDragEnterEvent) -> list[str]:
    md = event.mimeData()
    if not md.hasUrls():
        return []
    return [u.toLocalFile() for u in md.urls() if u.isLocalFile()]


class DropLineEdit(QLineEdit):
    """Line edit that accepts dropped files/folders."""

    fileDropped = pyqtSignal(str)

    def __init__(self, exts: tuple[str, ...] = (), dirs: bool = False, parent=None):
        super().__init__(parent)
        self.exts = tuple(e.lower() for e in exts)
        self.dirs = dirs
        self.setAcceptDrops(True)

    def _accepts(self, path: str) -> bool:
        p = Path(path)
        if self.dirs:
            return p.is_dir()
        return p.is_file() and (not self.exts or p.suffix.lower() in self.exts)

    def _set_drop(self, on: bool) -> None:
        self.setProperty("drop", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        paths = _dropped_paths(e)
        if paths and self._accepts(paths[0]):
            self._set_drop(True)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:
        self._set_drop(False)

    def dropEvent(self, e: QDropEvent) -> None:
        self._set_drop(False)
        paths = _dropped_paths(e)
        if paths and self._accepts(paths[0]):
            self.setText(paths[0])
            self.fileDropped.emit(paths[0])


class FilePicker(QWidget):
    """Path field + browse button. mode: open | dir | save."""

    changed = pyqtSignal(str)

    def __init__(self, placeholder: str = "", filt: str = "Все файлы (*)", mode: str = "open",
                 exts: tuple[str, ...] = (), config=None, key: str = "files", parent=None):
        super().__init__(parent)
        self.filt, self.mode, self.config, self.key = filt, mode, config, key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.edit = DropLineEdit(exts, dirs=(mode == "dir"))
        self.edit.setPlaceholderText(placeholder or "Перетащите файл сюда или нажмите «Обзор»")
        self.edit.fileDropped.connect(self._emit)
        self.edit.editingFinished.connect(lambda: self.changed.emit(self.path()))
        lay.addWidget(self.edit, 1)
        lay.addWidget(button("📂 Обзор", self.browse))

    def _start_dir(self) -> str:
        cur = self.path()
        if cur and Path(cur).exists():
            return cur
        return self.config.last_dir(self.key) if self.config else str(Path.home())

    def browse(self) -> None:
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "Выберите папку", self._start_dir())
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить как", self._start_dir(), self.filt)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Выберите файл", self._start_dir(), self.filt)
        if path:
            self.edit.setText(path)
            self._emit(path)

    def _emit(self, path: str) -> None:
        if self.config:
            self.config.remember_dir(self.key, path)
        self.changed.emit(path)

    def path(self) -> str:
        return self.edit.text().strip().strip('"')

    def setPath(self, path: str) -> None:
        self.edit.setText(path)


class DropListWidget(QListWidget):
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if _dropped_paths(e):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        paths = _dropped_paths(e)
        if paths:
            self.filesDropped.emit(paths)
            e.acceptProposedAction()


class Tile(QFrame):
    """Clickable card with a title and a monospace subtitle."""

    clicked = pyqtSignal()
    rightClicked = pyqtSignal()

    def __init__(self, title: str, sub: str, tip: str = "", danger: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.setProperty("danger", danger)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(tip)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)
        t = label(("⚠ " if danger else "") + title, "tileTitle")
        s = label(sub, "tileCmd")
        s.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        metrics = s.fontMetrics()
        s.setText(metrics.elidedText(sub, Qt.TextElideMode.ElideRight, 260))
        lay.addWidget(t)
        lay.addWidget(s)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        elif e.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()


class Toast(QLabel):
    """Floating notification in the top-right corner of the window."""

    COLORS = {
        "info": (theme.ACCENT, "rgba(124,92,255,0.18)"),
        "ok": (theme.SUCCESS, "rgba(46,230,166,0.16)"),
        "warn": (theme.WARN, "rgba(255,181,71,0.16)"),
        "error": (theme.DANGER, "rgba(255,77,109,0.18)"),
    }

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, kind: str = "info", ms: int = 3200) -> None:
        border, bg = self.COLORS.get(kind, self.COLORS["info"])
        self.setStyleSheet(
            f"QLabel#toast {{ background: {theme.SURFACE}; border: 1px solid {theme.BORDER};"
            f" border-left: 3px solid {border}; color: {theme.TEXT}; }}")
        self.setText(clean(text))
        self.adjustSize()
        parent = self.parentWidget()
        self.move(parent.width() - self.width() - 24, 76)
        self.show()
        self.raise_()
        try:
            self._anim.finished.disconnect()
        except TypeError:
            pass
        self._anim.stop()
        self._anim.setDuration(220)
        self._anim.setStartValue(self._effect.opacity() if self.isVisible() else 0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(ms)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(450)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)
        self._anim.start()


class ToolCard(QFrame):
    """Large clickable card: icon badge, title and description."""

    clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("toolcard")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(96)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(14)
        ic = label("", "toolIcon")
        ic.setFixedSize(44, 44)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icons.has(icon):
            icons.bind(ic, icon, "accent", 22)
        else:
            ic.setText(icon)
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label(title, "toolTitle"))
        d = label(desc, "toolDesc", wrap=True)
        col.addWidget(d)
        col.addStretch(1)
        lay.addLayout(col, 1)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


def fade_in(widget: QWidget, ms: int = 200) -> None:
    """Short opacity animation; the effect is removed afterwards to keep rendering cheap."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
