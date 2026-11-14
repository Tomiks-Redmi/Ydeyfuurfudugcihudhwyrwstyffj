"""Quick command library with search and user-defined commands."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLineEdit, QMenu, QScrollArea,
    QVBoxLayout, QWidget,
)

from ...core.commands import PRESETS
from ..widgets import Tile, button, hbox, label, page_header

COLUMNS = 3


class CommandDialog(QDialog):
    def __init__(self, parent=None, title: str = "", command: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Своя команда")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(title)
        self.title.setPlaceholderText("Например: Мой бэкап")
        self.command = QLineEdit(command)
        self.command.setPlaceholderText("adb shell ...  (несколько команд — через &&)")
        form.addRow("Название", self.title)
        form.addRow("Команда", self.command)
        lay.addLayout(form)
        lay.addWidget(label("Команды начинаются с <b>adb</b> или <b>fastboot</b>. Серийный номер выбранного "
                            "устройства подставится автоматически.", "muted", wrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class QuickPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 12)
        lay.setSpacing(12)
        lay.addLayout(page_header("🚀 Быстрые команды", "Клик — выполнить. Правый клик — скопировать, "
                                                         "вставить в консоль или удалить свою команду."))
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 Поиск команд…")
        self.search.textChanged.connect(self.rebuild)
        lay.addLayout(hbox(self.search, button("➕ Своя команда", self.add_custom, "accent")))
        lay.itemAt(1).layout().setStretch(0, 1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        lay.addWidget(self.scroll, 1)
        self.rebuild()

    def _all(self):
        custom = [(c["title"], c["command"], "Своя команда", False)
                  for c in self.app.config.get("custom_commands", [])]
        groups = []
        if custom:
            groups.append(("⭐ Мои команды", custom, True))
        groups += [(name, items, False) for name, items in PRESETS.items()]
        return groups

    def rebuild(self) -> None:
        query = self.search.text().strip().lower()
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(10)
        found = 0
        for name, items, is_custom in self._all():
            matched = [it for it in items if not query or query in it[0].lower() or query in it[1].lower()
                       or query in it[2].lower()]
            if not matched:
                continue
            lay.addWidget(label(name, "category"))
            grid = QGridLayout()
            grid.setSpacing(10)
            for i, (title, cmd, desc, danger) in enumerate(matched):
                tile = Tile(title, cmd, f"<b>{title}</b><br>{desc}<br><code>{cmd}</code>", danger)
                tile.clicked.connect(lambda t=title, c=cmd, d=danger: self.execute(t, c, d))
                tile.rightClicked.connect(lambda t=title, c=cmd, cu=is_custom: self.menu(t, c, cu))
                grid.addWidget(tile, i // COLUMNS, i % COLUMNS)
                found += 1
            for c in range(COLUMNS):
                grid.setColumnStretch(c, 1)
            lay.addLayout(grid)
        if not found:
            lay.addWidget(label("Ничего не найдено 🤷", "muted"))
        lay.addStretch(1)
        self.scroll.setWidget(body)

    def execute(self, title: str, cmd: str, danger: bool) -> None:
        if danger and not self.app.confirm(title, f"Выполнить потенциально опасную команду?<br><code>{cmd}</code>"):
            return
        self.app.run_text(cmd)

    def menu(self, title: str, cmd: str, custom: bool) -> None:
        from PyQt6.QtGui import QCursor
        m = QMenu(self)
        m.addAction("▶ Выполнить", lambda: self.app.run_text(cmd))
        m.addAction("⌨ Вставить в консоль", lambda: self.app.console.focus_input(cmd))
        m.addAction("📋 Копировать", lambda: self.app.clipboard_set(cmd))
        if custom:
            m.addSeparator()
            m.addAction("✏ Изменить", lambda: self.edit_custom(title, cmd))
            m.addAction("🗑 Удалить", lambda: self.delete_custom(title, cmd))
        else:
            m.addAction("⭐ Добавить в мои", lambda: self._save_custom(title, cmd))
        m.exec(QCursor.pos())

    def _save_custom(self, title: str, cmd: str, replace: tuple[str, str] | None = None) -> None:
        items = list(self.app.config.get("custom_commands", []))
        if replace:
            items = [c for c in items if (c["title"], c["command"]) != replace]
        items.append({"title": title, "command": cmd})
        self.app.config.set("custom_commands", items)
        self.rebuild()
        self.app.page_dashboard.refresh_favorites()

    def add_custom(self) -> None:
        dlg = CommandDialog(self)
        if dlg.exec() and dlg.command.text().strip():
            self._save_custom(dlg.title.text().strip() or dlg.command.text().strip()[:30], dlg.command.text().strip())

    def edit_custom(self, title: str, cmd: str) -> None:
        dlg = CommandDialog(self, title, cmd)
        if dlg.exec() and dlg.command.text().strip():
            self._save_custom(dlg.title.text().strip() or title, dlg.command.text().strip(), replace=(title, cmd))

    def delete_custom(self, title: str, cmd: str) -> None:
        items = [c for c in self.app.config.get("custom_commands", []) if (c["title"], c["command"]) != (title, cmd)]
        self.app.config.set("custom_commands", items)
        self.rebuild()
        self.app.page_dashboard.refresh_favorites()
