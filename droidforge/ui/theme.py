"""Dark neon theme."""
from pathlib import Path

_ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()

ACCENT = "#7c5cff"
ACCENT_2 = "#22d3ee"
ACCENT_3 = "#5b8cff"
BG = "#0b0e15"
SURFACE = "#131824"
SURFACE_2 = "#1b2130"
INPUT = "#0e121b"
BORDER = "#252d3f"
TEXT = "#e6e9f2"
MUTED = "#8a93a8"
DANGER = "#ff4d6d"
SUCCESS = "#2ee6a6"
WARN = "#ffb547"

MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", "DejaVu Sans Mono", "Menlo", monospace'

def rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' -> 'rgba(r,g,b,a)' (Qt reads 8-digit hex as #AARRGGBB, so avoid it)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


ACCENTS = {
    "Фиолетовый": ("#7c5cff", "#5b8cff"),
    "Синий": ("#3b82f6", "#06b6d4"),
    "Бирюзовый": ("#14b8a6", "#22d3ee"),
    "Изумрудный": ("#10b981", "#84cc16"),
    "Оранжевый": ("#f97316", "#facc15"),
    "Розовый": ("#ec4899", "#a855f7"),
    "Красный": ("#ef4444", "#f97316"),
}


def build_qss(ACCENT: str = ACCENT, ACCENT_3: str = ACCENT_3) -> str:  # noqa: N803 - names reused in the template
    SEL = rgba(ACCENT, 0.38)  # noqa: N806
    HOV = rgba(ACCENT, 0.12)  # noqa: N806
    return f"""
* {{
    color: {TEXT};
    font-family: "Segoe UI", "Inter", "SF Pro Text", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QWidget#root, QWidget#content, QStackedWidget {{ background: {BG}; }}
QDialog, QMessageBox, QInputDialog {{ background: {SURFACE}; }}

/* ---------- navigation ---------- */
QFrame#sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QLabel#logo {{ font-size: 17pt; font-weight: 800; padding: 6px 4px; }}
QLabel#version {{ color: {MUTED}; font-size: 8pt; padding-left: 6px; }}
QListWidget#nav {{ background: transparent; border: none; outline: 0; }}
QListWidget#nav::item {{
    padding: 11px 12px; border-radius: 10px; margin: 2px 0; color: {MUTED};
}}
QListWidget#nav::item:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QListWidget#nav::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_3});
    color: white;
}}

QFrame#header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QLabel#badge {{ border-radius: 9px; padding: 3px 10px; font-weight: 700; font-size: 8.5pt; }}

/* ---------- cards ---------- */
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#hero {{
    border: 1px solid {BORDER}; border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {rgba(ACCENT, 0.28)}, stop:0.55 {SURFACE}, stop:1 rgba(34,211,238,0.16));
}}
QLabel#cardTitle {{ font-size: 11pt; font-weight: 700; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 800; }}
QLabel#h2 {{ font-size: 14pt; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#value {{ font-weight: 600; }}
QLabel#hint {{
    color: {WARN}; background: rgba(255,181,71,0.08); border: 1px solid rgba(255,181,71,0.35);
    border-radius: 10px; padding: 8px 12px;
}}
QLabel#bigIcon {{ font-size: 40pt; }}

QFrame#tile {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#tile:hover {{ border: 1px solid {ACCENT}; background: #222a3d; }}
QFrame#tile[danger="true"]:hover {{ border: 1px solid {DANGER}; }}
QLabel#tileTitle {{ font-weight: 600; background: transparent; }}
QLabel#tileCmd {{ color: {MUTED}; font-family: {MONO}; font-size: 8pt; background: transparent; }}
QLabel#category {{ font-size: 12pt; font-weight: 700; padding-top: 6px; }}

/* ---------- buttons ---------- */
QPushButton, QToolButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 14px;
}}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; background: #232a3c; }}
QPushButton:pressed, QToolButton:pressed {{ background: #2b3449; }}
QPushButton:disabled {{ color: #505869; border-color: #1d2331; background: #151a25; }}
QPushButton[kind="accent"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_3});
    border: none; color: white; font-weight: 700; padding: 8px 18px;
}}
QPushButton[kind="accent"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_3}, stop:1 {ACCENT});
}}
QPushButton[kind="accent"]:disabled {{ background: #2a2f45; color: #6d7488; }}
QPushButton[kind="danger"] {{
    background: rgba(255,77,109,0.10); border: 1px solid rgba(255,77,109,0.45); color: #ff8fa3;
}}
QPushButton[kind="danger"]:hover {{ background: rgba(255,77,109,0.24); border-color: {DANGER}; }}
QPushButton[kind="danger"]:disabled {{ background: transparent; border-color: #1d2331; color: #505869; }}
QPushButton[kind="ghost"] {{ background: transparent; border: none; color: {MUTED}; padding: 4px 8px; }}
QPushButton[kind="ghost"]:hover {{ color: {TEXT}; background: {SURFACE_2}; }}
QPushButton[kind="key"] {{ font-size: 13pt; min-width: 54px; min-height: 40px; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit[drop="true"] {{ border: 1px dashed {ACCENT_2}; background: rgba(34,211,238,0.06); }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({_ASSETS}/arrow.svg); width: 12px; height: 12px; margin-right: 8px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; outline: 0; padding: 4px;
    selection-background-color: {ACCENT};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 5px; border: 1px solid {BORDER}; background: {INPUT};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked, QTableWidget::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT}; image: url({_ASSETS}/check.svg);
}}
QTableWidget::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {BORDER}; background: {INPUT}; }}
QCheckBox:disabled {{ color: #505869; }}

/* ---------- lists / tables ---------- */
QListWidget, QTableWidget, QTreeWidget {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: {BORDER}; alternate-background-color: #111621; outline: 0;
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:hover, QTableWidget::item:hover {{ background: {HOV}; }}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: {SEL}; color: white;
}}
QHeaderView::section {{
    background: {SURFACE_2}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 8px; color: {MUTED}; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_2}; border: none; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 12px; background: {SURFACE}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 16px; margin-right: 4px;
    border-top-left-radius: 9px; border-top-right-radius: 9px; border: 1px solid transparent;
}}
QTabBar::tab:selected {{ color: white; background: {SURFACE}; border: 1px solid {BORDER}; border-bottom: none; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QProgressBar {{
    background: {INPUT}; border: 1px solid {BORDER}; border-radius: 6px;
    text-align: center; color: {TEXT}; font-size: 8pt; min-height: 14px; max-height: 14px;
}}
QProgressBar::chunk {{
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
}}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: #2a3245; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QSplitter::handle {{ background: {BG}; }}
QSplitter::handle:vertical {{ height: 6px; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 6px; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {ACCENT}; padding: 6px; border-radius: 6px; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

QFrame#consoleFrame {{ background: {SURFACE}; border-top: 1px solid {BORDER}; }}
QPlainTextEdit#console, QPlainTextEdit#logcat {{
    font-family: {MONO}; font-size: 9.5pt; background: #080b11; border-radius: 10px;
}}
QLineEdit#consoleInput {{ font-family: {MONO}; background: #080b11; padding: 8px 10px; }}
QLabel#prompt {{ color: {ACCENT_2}; font-family: {MONO}; font-weight: 800; font-size: 12pt; }}
QLabel#toast {{ border-radius: 12px; padding: 12px 18px; font-weight: 600; }}
QLabel#screen {{ background: #080b11; border: 1px solid {BORDER}; border-radius: 12px; color: {MUTED}; }}
"""


QSS = build_qss()
