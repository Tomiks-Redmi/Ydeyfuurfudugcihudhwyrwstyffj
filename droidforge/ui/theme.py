"""Minimal theme: neutral palettes, one accent color, flat surfaces, no gradients.

Module-level color names (BG, SURFACE, TEXT, ACCENT, ...) always hold the *current*
palette, so widgets that read them at paint/show time follow theme switches.
"""
from __future__ import annotations

from pathlib import Path

_ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()

MONO = '"JetBrains Mono", "Cascadia Mono", "Consolas", "SF Mono", "DejaVu Sans Mono", monospace'

ACCENTS = {
    "Индиго": ("#6366f1", "#818cf8"),
    "Фиолетовый": ("#8b5cf6", "#a78bfa"),
    "Синий": ("#3b82f6", "#60a5fa"),
    "Бирюзовый": ("#14b8a6", "#2dd4bf"),
    "Изумрудный": ("#10b981", "#34d399"),
    "Оранжевый": ("#f97316", "#fb923c"),
    "Розовый": ("#ec4899", "#f472b6"),
    "Графит": ("#71717a", "#a1a1aa"),
}

PALETTES = {
    "dark": {
        "BG": "#0e0f11", "SIDEBAR": "#0e0f11", "SURFACE": "#141518", "SURFACE_2": "#1a1b1f",
        "HOVER": "#1f2024", "PRESSED": "#26272c", "INPUT": "#121316", "BORDER": "#26272c",
        "BORDER_SOFT": "#1d1e22", "TEXT": "#ececee", "MUTED": "#8b8d94", "DISABLED": "#4a4c52",
        "ALT": "#121316", "SCROLL": "#2c2d33", "TERMINAL": "#0a0b0d", "TERMINAL_BORDER": "#1d1e22",
        "DANGER": "#f05252", "SUCCESS": "#34d399", "WARN": "#f5b44a", "ACCENT_2": "#38bdf8",
    },
    "light": {
        "BG": "#fafafa", "SIDEBAR": "#fafafa", "SURFACE": "#ffffff", "SURFACE_2": "#f4f4f5",
        "HOVER": "#f0f0f2", "PRESSED": "#e6e6e9", "INPUT": "#ffffff", "BORDER": "#e4e4e7",
        "BORDER_SOFT": "#ededf0", "TEXT": "#18181b", "MUTED": "#71717a", "DISABLED": "#b4b4bb",
        "ALT": "#fafafa", "SCROLL": "#d4d4d8", "TERMINAL": "#111214", "TERMINAL_BORDER": "#1d1e22",
        "DANGER": "#dc2626", "SUCCESS": "#059669", "WARN": "#d97706", "ACCENT_2": "#0284c7",
    },
}

MODE = "dark"
ACCENT, ACCENT_3 = ACCENTS["Индиго"]
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
        ACCENT, ACCENT_3 = ACCENTS.get(accent, ACCENTS["Индиго"])
    try:
        from . import icons
        icons.set_colors(muted=MUTED, text=TEXT, accent=ACCENT, danger=DANGER)
    except ImportError:
        pass


set_palette("dark")


def build_qss() -> str:
    dark = MODE == "dark"
    SEL = rgba(ACCENT, 0.22 if dark else 0.12)  # noqa: N806
    SOFT = rgba(ACCENT, 0.12 if dark else 0.08)  # noqa: N806
    return f"""
* {{
    color: {TEXT};
    font-family: "Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QWidget#root, QWidget#content, QStackedWidget, QWidget#page {{ background: {BG}; }}
QDialog, QMessageBox, QInputDialog {{ background: {SURFACE}; }}

/* ---------- sidebar ---------- */
QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER_SOFT}; }}
QLabel#logo {{ font-size: 13pt; font-weight: 700; padding: 2px 6px; }}
QLabel#version {{ color: {MUTED}; font-size: 8pt; padding-left: 6px; }}
QListWidget#nav {{ background: transparent; border: none; outline: 0; }}
QListWidget#nav::item {{ padding: 8px 10px; border-radius: 8px; margin: 1px 0; color: {MUTED}; }}
QListWidget#nav::item:hover {{ background: {HOVER}; color: {TEXT}; }}
QListWidget#nav::item:selected {{ background: {SURFACE_2 if dark else PRESSED}; color: {TEXT}; font-weight: 600; }}
QListWidget#nav::item:disabled {{
    color: {DISABLED}; font-size: 7.5pt; font-weight: 600; padding: 16px 10px 4px 10px; background: transparent;
}}
QFrame#devcard {{ background: transparent; border: none; border-top: 1px solid {BORDER_SOFT}; border-radius: 0; }}
QLabel#devName {{ font-weight: 600; }}
QLabel#devMeta {{ color: {MUTED}; font-size: 8.5pt; }}

/* ---------- header ---------- */
QFrame#header {{ background: {BG}; border-bottom: 1px solid {BORDER_SOFT}; }}
QLabel#badge {{ background: transparent; border: none; padding: 0 4px; font-size: 9pt; color: {MUTED}; }}
QPushButton#search {{
    background: {SURFACE_2}; border: 1px solid transparent; border-radius: 8px; color: {MUTED};
    text-align: left; padding: 7px 12px; min-width: 300px;
}}
QPushButton#search:hover {{ border-color: {BORDER}; color: {TEXT}; }}

/* ---------- surfaces ---------- */
QFrame#card, QFrame#hero {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 12px; }}
QFrame#banner {{ border-radius: 12px; border: 1px solid {rgba(WARN, 0.35)}; background: {rgba(WARN, 0.06)}; }}
QLabel#cardTitle {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 13pt; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#value {{ font-weight: 500; }}
QLabel#hint {{
    color: {TEXT}; background: {rgba(WARN, 0.07)}; border: none; border-left: 3px solid {WARN};
    border-radius: 6px; padding: 8px 12px;
}}
QLabel#bigIcon {{ background: transparent; }}
QLabel#crumb {{ color: {MUTED}; font-size: 9pt; }}

QFrame#tile, QFrame#toolcard {{ background: {SURFACE}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; }}
QFrame#tile:hover, QFrame#toolcard:hover {{ border: 1px solid {BORDER}; background: {HOVER}; }}
QFrame#tile[danger="true"]:hover {{ border: 1px solid {rgba(DANGER, 0.6)}; }}
QLabel#tileTitle {{ font-weight: 500; background: transparent; }}
QLabel#tileCmd {{ color: {MUTED}; font-family: {MONO}; font-size: 8pt; background: transparent; }}
QLabel#toolIcon {{ background: {SOFT}; border-radius: 10px; }}
QLabel#toolTitle {{ font-size: 10.5pt; font-weight: 600; background: transparent; }}
QLabel#toolDesc {{ color: {MUTED}; background: transparent; }}
QLabel#category {{ font-size: 9pt; font-weight: 600; color: {MUTED}; padding-top: 10px; }}

/* ---------- buttons ---------- */
QPushButton, QToolButton {{
    background: transparent; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 13px;
}}
QPushButton:hover, QToolButton:hover {{ background: {HOVER}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled {{ color: {DISABLED}; border-color: {BORDER_SOFT}; }}
QPushButton[kind="accent"] {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; font-weight: 600; padding: 6px 16px; }}
QPushButton[kind="accent"]:hover {{ background: {ACCENT_3}; border-color: {ACCENT_3}; }}
QPushButton[kind="accent"]:disabled {{ background: {PRESSED}; border-color: {PRESSED}; color: {DISABLED}; }}
QPushButton[kind="danger"] {{ border: 1px solid {rgba(DANGER, 0.45)}; color: {DANGER}; }}
QPushButton[kind="danger"]:hover {{ background: {rgba(DANGER, 0.10)}; }}
QPushButton[kind="danger"]:disabled {{ border-color: {BORDER_SOFT}; color: {DISABLED}; }}
QPushButton[kind="ghost"] {{ border: 1px solid transparent; color: {MUTED}; padding: 5px 9px; }}
QPushButton[kind="ghost"]:hover {{ color: {TEXT}; background: {HOVER}; }}
QPushButton[kind="icon"], QToolButton[kind="icon"] {{ border: 1px solid transparent; padding: 6px; border-radius: 8px; }}
QPushButton[kind="icon"]:hover, QToolButton[kind="icon"]:hover {{ background: {HOVER}; }}
QPushButton[kind="key"] {{ min-width: 48px; min-height: 38px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 9px;
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[drop="true"] {{ border: 1px dashed {ACCENT}; background: {SOFT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({_ASSETS}/arrow.svg); width: 12px; height: 12px; margin-right: 8px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; outline: 0; padding: 4px;
    selection-background-color: {SEL}; selection-color: {TEXT};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; background: {TEXT}; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QTableWidget::indicator, QListWidget::indicator {{
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER}; background: {INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {MUTED}; }}
QCheckBox::indicator:checked, QTableWidget::indicator:checked, QListWidget::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT}; image: url({_ASSETS}/check.svg);
}}
QCheckBox:disabled {{ color: {DISABLED}; }}

/* ---------- lists / tables ---------- */
QListWidget, QTableWidget, QTreeWidget {{
    background: {INPUT}; border: 1px solid {BORDER_SOFT}; border-radius: 10px;
    gridline-color: {BORDER_SOFT}; alternate-background-color: {ALT}; outline: 0;
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:hover, QTableWidget::item:hover {{ background: {HOVER}; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {SEL}; color: {TEXT}; }}
QHeaderView {{ background: {INPUT}; border: none; }}
QHeaderView::section {{
    background: {INPUT}; border: none; border-bottom: 1px solid {BORDER_SOFT};
    padding: 6px 8px; color: {MUTED}; font-weight: 500; font-size: 9pt;
}}
QTableCornerButton::section {{ background: {INPUT}; border: none; }}

/* ---------- underline tabs ---------- */
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER_SOFT}; background: transparent; top: -1px; }}
QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 2px; margin-right: 22px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}

QProgressBar {{
    background: {SURFACE_2}; border: none; border-radius: 3px;
    text-align: center; color: {TEXT}; font-size: 8pt; min-height: 6px; max-height: 14px;
}}
QProgressBar#topProgress {{ border-radius: 0; background: transparent; min-height: 2px; max-height: 2px; }}
QProgressBar#topProgress::chunk {{ border-radius: 0; }}
QProgressBar::chunk {{ border-radius: 3px; background: {ACCENT}; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle {{ background: {SCROLL}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:vertical {{ height: 4px; }}
QSplitter::handle:hover {{ background: {BORDER}; }}

QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px 8px; border-radius: 6px; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {HOVER}; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER_SOFT}; margin: 4px 6px; }}

/* ---------- console ---------- */
QFrame#consoleFrame {{ background: {BG}; border-top: 1px solid {BORDER_SOFT}; }}
QPlainTextEdit#console, QPlainTextEdit#logcat {{
    font-family: {MONO}; font-size: 9pt; background: {TERMINAL}; color: #c9cbd1;
    border: 1px solid {TERMINAL_BORDER}; border-radius: 10px; padding: 4px; selection-background-color: {ACCENT};
}}
QLineEdit#consoleInput {{
    font-family: {MONO}; background: {TERMINAL}; color: #ececee; border: 1px solid {TERMINAL_BORDER}; padding: 7px 10px;
}}
QLineEdit#consoleInput:focus {{ border: 1px solid {ACCENT}; }}
QLabel#prompt {{ color: {ACCENT}; font-family: {MONO}; font-weight: 700; font-size: 11pt; }}
QLabel#lastLine {{ color: {MUTED}; font-family: {MONO}; font-size: 8.5pt; }}
QLabel#toast {{ border-radius: 10px; padding: 11px 16px; font-weight: 500; }}
QLabel#screen {{ background: {TERMINAL}; border: 1px solid {BORDER_SOFT}; border-radius: 12px; color: #8b8d94; }}

/* ---------- popups ---------- */
QFrame#palette {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QLineEdit#paletteInput {{
    font-size: 12pt; border: none; border-bottom: 1px solid {BORDER_SOFT}; border-radius: 0;
    background: transparent; padding: 13px 16px;
}}
QListWidget#paletteList {{ background: transparent; border: none; padding: 6px; }}
QListWidget#paletteList::item {{ padding: 8px 10px; border-radius: 8px; }}
QListWidget#paletteList::item:selected {{ background: {HOVER}; color: {TEXT}; }}
"""


QSS = build_qss()
