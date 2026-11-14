"""Theme system: dark / light palettes + accent colors, rendered into one Qt stylesheet.

Module-level color names (BG, SURFACE, TEXT, ACCENT, ...) always hold the *current*
palette, so widgets that read them at paint/show time follow theme switches.
"""
from __future__ import annotations

from pathlib import Path

_ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()

MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", "DejaVu Sans Mono", "Menlo", monospace'

ACCENTS = {
    "Фиолетовый": ("#7c5cff", "#5b8cff"),
    "Синий": ("#3b82f6", "#06b6d4"),
    "Бирюзовый": ("#14b8a6", "#22d3ee"),
    "Изумрудный": ("#10b981", "#84cc16"),
    "Оранжевый": ("#f97316", "#facc15"),
    "Розовый": ("#ec4899", "#a855f7"),
    "Красный": ("#ef4444", "#f97316"),
}

PALETTES = {
    "dark": {
        "BG": "#0a0d14", "SIDEBAR": "#0e121b", "SURFACE": "#121722", "SURFACE_2": "#1a2030",
        "HOVER": "#212839", "PRESSED": "#2a3247", "INPUT": "#0d1119", "BORDER": "#232b3d",
        "BORDER_SOFT": "#1a2131", "TEXT": "#e8ebf3", "MUTED": "#8a93a8", "DISABLED": "#4d5568",
        "ALT": "#0f141e", "SCROLL": "#2a3245", "TERMINAL": "#070a10", "TERMINAL_BORDER": "#1a2131",
        "DANGER": "#ff4d6d", "SUCCESS": "#2ee6a6", "WARN": "#ffb547", "ACCENT_2": "#22d3ee",
    },
    "light": {
        "BG": "#f2f4f9", "SIDEBAR": "#ffffff", "SURFACE": "#ffffff", "SURFACE_2": "#f3f5fa",
        "HOVER": "#eaedf6", "PRESSED": "#dfe4f1", "INPUT": "#ffffff", "BORDER": "#dce1ec",
        "BORDER_SOFT": "#e9ecf4", "TEXT": "#161b2a", "MUTED": "#687086", "DISABLED": "#a8afbf",
        "ALT": "#f7f8fc", "SCROLL": "#c7cedc", "TERMINAL": "#0c1019", "TERMINAL_BORDER": "#1f2636",
        "DANGER": "#e11d48", "SUCCESS": "#059669", "WARN": "#d97706", "ACCENT_2": "#0891b2",
    },
}

MODE = "dark"
ACCENT, ACCENT_3 = ACCENTS["Фиолетовый"]
# current palette values, exported as module globals
BG = SIDEBAR = SURFACE = SURFACE_2 = HOVER = PRESSED = INPUT = BORDER = BORDER_SOFT = ""
TEXT = MUTED = DISABLED = ALT = SCROLL = TERMINAL = TERMINAL_BORDER = DANGER = SUCCESS = WARN = ACCENT_2 = ""


def rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' -> 'rgba(r,g,b,a)' (Qt reads 8-digit hex as #AARRGGBB, so avoid it)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def set_palette(mode: str = "dark", accent: str | None = None) -> None:
    global MODE, ACCENT, ACCENT_3
    MODE = mode if mode in PALETTES else "dark"
    globals().update(PALETTES[MODE])
    if accent:
        ACCENT, ACCENT_3 = ACCENTS.get(accent, ACCENTS["Фиолетовый"])


set_palette("dark")


def build_qss() -> str:
    dark = MODE == "dark"
    SEL = rgba(ACCENT, 0.32 if dark else 0.16)  # noqa: N806
    HOV = rgba(ACCENT, 0.10 if dark else 0.07)  # noqa: N806
    SOFT = rgba(ACCENT, 0.16 if dark else 0.10)  # noqa: N806
    RING = rgba(ACCENT, 0.45)  # noqa: N806
    ON_SEL = "white" if dark else TEXT  # noqa: N806
    return f"""
* {{
    color: {TEXT};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QWidget#root, QWidget#content, QStackedWidget, QWidget#page {{ background: {BG}; }}
QDialog, QMessageBox, QInputDialog {{ background: {SURFACE}; }}

/* ---------- sidebar ---------- */
QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER_SOFT}; }}
QLabel#logo {{ font-size: 17pt; font-weight: 800; padding: 4px 4px; }}
QLabel#version {{ color: {MUTED}; font-size: 8pt; padding-left: 6px; }}
QListWidget#nav {{ background: transparent; border: none; outline: 0; }}
QListWidget#nav::item {{ padding: 10px 12px; border-radius: 10px; margin: 1px 0; color: {MUTED}; }}
QListWidget#nav::item:hover {{ background: {HOVER}; color: {TEXT}; }}
QListWidget#nav::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {rgba(ACCENT, 0.95)}, stop:1 {rgba(ACCENT_3, 0.85)});
    color: white; font-weight: 600;
}}
QListWidget#nav::item:disabled {{
    color: {DISABLED}; font-size: 8pt; font-weight: 700; padding: 14px 12px 4px 12px; background: transparent;
}}
QFrame#devcard {{ background: {SURFACE_2}; border: 1px solid {BORDER_SOFT}; border-radius: 12px; }}
QLabel#devName {{ font-weight: 700; }}
QLabel#devMeta {{ color: {MUTED}; font-size: 8.5pt; }}

/* ---------- header ---------- */
QFrame#header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER_SOFT}; }}
QLabel#badge {{ border-radius: 9px; padding: 3px 10px; font-weight: 700; font-size: 8.5pt; }}
QPushButton#search {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 10px; color: {MUTED};
    text-align: left; padding: 8px 14px; min-width: 260px;
}}
QPushButton#search:hover {{ border-color: {ACCENT}; color: {TEXT}; }}

/* ---------- cards ---------- */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 14px; }}
QFrame#hero {{
    border: 1px solid {BORDER_SOFT}; border-radius: 18px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {rgba(ACCENT, 0.30 if dark else 0.14)}, stop:0.55 {SURFACE}, stop:1 {rgba(ACCENT_2, 0.16 if dark else 0.10)});
}}
QFrame#banner {{
    border-radius: 14px; border: 1px solid {rgba(WARN, 0.45)}; background: {rgba(WARN, 0.10)};
}}
QLabel#cardTitle {{ font-size: 11pt; font-weight: 700; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 800; }}
QLabel#h2 {{ font-size: 14pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#value {{ font-weight: 600; }}
QLabel#hint {{
    color: {WARN}; background: {rgba(WARN, 0.08)}; border: 1px solid {rgba(WARN, 0.35)};
    border-radius: 10px; padding: 8px 12px;
}}
QLabel#bigIcon {{ font-size: 40pt; }}
QLabel#crumb {{ color: {MUTED}; font-weight: 600; }}

QFrame#tile, QFrame#toolcard {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 14px; }}
QFrame#tile {{ background: {SURFACE_2}; border-radius: 12px; }}
QFrame#tile:hover, QFrame#toolcard:hover {{ border: 1px solid {ACCENT}; background: {HOVER}; }}
QFrame#tile[danger="true"]:hover {{ border: 1px solid {DANGER}; }}
QLabel#tileTitle {{ font-weight: 600; background: transparent; }}
QLabel#tileCmd {{ color: {MUTED}; font-family: {MONO}; font-size: 8pt; background: transparent; }}
QLabel#toolIcon {{ font-size: 24pt; background: {SOFT}; border-radius: 14px; padding: 6px; }}
QLabel#toolTitle {{ font-size: 12pt; font-weight: 700; background: transparent; }}
QLabel#toolDesc {{ color: {MUTED}; background: transparent; }}
QLabel#category {{ font-size: 12pt; font-weight: 700; padding-top: 6px; }}

/* ---------- buttons ---------- */
QPushButton, QToolButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 14px;
}}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; background: {HOVER}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled {{ color: {DISABLED}; border-color: {BORDER_SOFT}; background: {SURFACE_2}; }}
QPushButton[kind="accent"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_3});
    border: none; color: white; font-weight: 700; padding: 8px 18px;
}}
QPushButton[kind="accent"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_3}, stop:1 {ACCENT});
}}
QPushButton[kind="accent"]:disabled {{ background: {PRESSED}; color: {DISABLED}; }}
QPushButton[kind="danger"] {{
    background: {rgba(DANGER, 0.10)}; border: 1px solid {rgba(DANGER, 0.45)}; color: {DANGER};
}}
QPushButton[kind="danger"]:hover {{ background: {rgba(DANGER, 0.22)}; border-color: {DANGER}; }}
QPushButton[kind="danger"]:disabled {{ background: transparent; border-color: {BORDER_SOFT}; color: {DISABLED}; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {MUTED}; padding: 4px 8px; }}
QPushButton[kind="ghost"]:hover {{ color: {TEXT}; background: {HOVER}; }}
QPushButton[kind="icon"] {{ background: transparent; border: 1px solid transparent; padding: 6px 9px; font-size: 12pt; }}
QPushButton[kind="icon"]:hover {{ background: {HOVER}; border-color: {BORDER}; }}
QPushButton[kind="key"] {{ font-size: 13pt; min-width: 54px; min-height: 40px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[drop="true"] {{ border: 1px dashed {ACCENT_2}; background: {rgba(ACCENT_2, 0.08)}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({_ASSETS}/arrow.svg); width: 12px; height: 12px; margin-right: 8px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; outline: 0; padding: 4px;
    selection-background-color: {SEL}; selection-color: {ON_SEL};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTableWidget::indicator, QListWidget::indicator {{
    width: 17px; height: 17px; border-radius: 5px; border: 1px solid {BORDER}; background: {INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked, QTableWidget::indicator:checked, QListWidget::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT}; image: url({_ASSETS}/check.svg);
}}
QCheckBox:disabled {{ color: {DISABLED}; }}

/* ---------- lists / tables ---------- */
QListWidget, QTableWidget, QTreeWidget {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: {BORDER_SOFT}; alternate-background-color: {ALT}; outline: 0;
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:hover, QTableWidget::item:hover {{ background: {HOV}; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {SEL}; color: {ON_SEL}; }}
QHeaderView::section {{
    background: {SURFACE_2}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 8px; color: {MUTED}; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_2}; border: none; }}

/* ---------- pill tabs ---------- */
QTabWidget::pane {{ border: 1px solid {BORDER_SOFT}; border-radius: 14px; background: {SURFACE}; top: 8px; }}
QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 7px 15px; margin-right: 6px;
    border-radius: 9px; border: 1px solid transparent;
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: {HOVER}; }}
QTabBar::tab:selected {{ color: {TEXT}; background: {SOFT}; border: 1px solid {RING}; font-weight: 600; }}

QProgressBar {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 6px;
    text-align: center; color: {TEXT}; font-size: 8pt; min-height: 14px; max-height: 14px;
}}
QProgressBar#topProgress {{ border: none; border-radius: 0; background: transparent; min-height: 3px; max-height: 3px; }}
QProgressBar#topProgress::chunk {{ border-radius: 0; }}
QProgressBar::chunk {{
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
}}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {SCROLL}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:vertical {{ height: 5px; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}

QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {ACCENT}; padding: 6px; border-radius: 6px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

/* ---------- console ---------- */
QFrame#consoleFrame {{ background: {SURFACE}; border-top: 1px solid {BORDER_SOFT}; }}
QPlainTextEdit#console, QPlainTextEdit#logcat {{
    font-family: {MONO}; font-size: 9.5pt; background: {TERMINAL}; color: #c9cfdd;
    border: 1px solid {TERMINAL_BORDER}; border-radius: 10px; selection-background-color: {ACCENT};
}}
QLineEdit#consoleInput {{
    font-family: {MONO}; background: {TERMINAL}; color: #e6e9f2; border: 1px solid {TERMINAL_BORDER}; padding: 8px 10px;
}}
QLineEdit#consoleInput:focus {{ border: 1px solid {ACCENT}; }}
QLabel#prompt {{ color: {ACCENT_2}; font-family: {MONO}; font-weight: 800; font-size: 12pt; }}
QLabel#lastLine {{ color: {MUTED}; font-family: {MONO}; font-size: 9pt; }}
QLabel#toast {{ border-radius: 12px; padding: 12px 18px; font-weight: 600; }}
QLabel#screen {{ background: {TERMINAL}; border: 1px solid {BORDER}; border-radius: 12px; color: #8a93a8; }}

/* ---------- command palette ---------- */
QFrame#palette {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 16px; }}
QLineEdit#paletteInput {{
    font-size: 13pt; border: none; border-bottom: 1px solid {BORDER_SOFT}; border-radius: 0;
    background: transparent; padding: 14px 16px;
}}
QListWidget#paletteList {{ background: transparent; border: none; padding: 6px; }}
QListWidget#paletteList::item {{ padding: 9px 12px; border-radius: 9px; }}
QListWidget#paletteList::item:selected {{ background: {SEL}; color: {ON_SEL}; }}
"""


QSS = build_qss()
