"""Monochrome line icons (24×24, stroke based) rendered from inline SVG.

Icons are recolored per theme: widgets registered with `bind()` are re-rendered by `refresh_all()`.
"""
from __future__ import annotations

import weakref

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_SPEAKER = '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/>'

ICONS: dict[str, str] = {
    "home": '<path d="M3.5 11 12 4l8.5 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-5h4v5"/>',
    "bolt": '<path d="M13 2.5 4.5 14H11l-1 7.5L19.5 10H13z"/>',
    "lifebuoy": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.8"/>'
                '<path d="m5.6 5.6 3.7 3.7M14.7 14.7l3.7 3.7M14.7 9.3l3.7-3.7M5.6 18.4l3.7-3.7"/>',
    "phone": '<rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/><path d="M10.5 18.5h3"/>',
    "wrench": '<path d="M14.5 5.5a4.5 4.5 0 0 0-5.8 5.8L3.5 16.5l4 4 5.2-5.2a4.5 4.5 0 0 0 5.8-5.8l-2.7 2.7-2.8-.4-.4-2.8z"/>',
    "list": '<rect x="4" y="3" width="16" height="18" rx="2.5"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "terminal": '<rect x="2.5" y="4" width="19" height="16" rx="2.5"/><path d="m7 9.5 3 2.5-3 2.5M12.5 15h4.5"/>',
    "sliders": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
    "history": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2'
           'M4.6 19.4 6 18M18 6l1.4-1.4"/>',
    "moon": '<path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z"/>',
    "power": '<path d="M12 3v8"/><path d="M6.6 6.6a7.5 7.5 0 1 0 10.8 0"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.4-4.4"/>',
    "copy": '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/><path d="M15.5 8.5V5a1.5 1.5 0 0 0-1.5-1.5H5A1.5 1.5 0 0 0 3.5 5v9A1.5 1.5 0 0 0 5 15.5h3.5"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6"/><path d="m6 7 1 13h10l1-13M9 7V4h6v3"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m6 15 6-6 6 6"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "arrow-left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "square": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "vol-down": _SPEAKER + '<path d="M16 12h5"/>',
    "vol-up": _SPEAKER + '<path d="M16 12h5M18.5 9.5v5"/>',
    "mute": _SPEAKER + '<path d="m16 9.5 5 5M21 9.5l-5 5"/>',
    "unlock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7.5a4 4 0 0 1 7.6-1.8"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "playpause": '<path d="M4.5 6v12l8-6zM16 6v12M20 6v12"/>',
    "play": '<path d="M7 5l12 7-12 7z"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "upload": '<path d="M12 16V4M6.5 9.5 12 4l5.5 5.5"/><path d="M4 16v4h16v-4"/>',
    "download": '<path d="M12 4v12M6.5 10.5 12 16l5.5-5.5"/><path d="M4 16v4h16v-4"/>',
    "package": '<path d="M3.5 7.5 12 3.5l8.5 4v9L12 20.5l-8.5-4z"/><path d="M3.5 7.5 12 11.5l8.5-4M12 11.5v9"/>',
    "shield": '<path d="M12 3 19.5 6v6c0 4.8-3.3 7.8-7.5 9-4.2-1.2-7.5-4.2-7.5-9V6z"/>',
    "magic": '<path d="m4 20 10-10M14 6V3M14 13v-2M19 8h3M18 4.5l-1.5 1.5M18 11.5 16.5 10"/>',
    "save": '<path d="M5 3.5h11l3.5 3.5v13.5H5z"/><path d="M8 3.5v5h7M8 20.5v-6h8v6"/>',
    "activity": '<path d="M3 12h4l3-7.5 4 15 3-7.5h4"/>',
    "hash": '<path d="M5 9h14M5 15h14M10 4 8 20M16 4l-2 16"/>',
    "code": '<path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4"/>',
    "folder": '<path d="M3 6.5a1.5 1.5 0 0 1 1.5-1.5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
    "file": '<path d="M6 3h8.5L18 6.5V21H6z"/><path d="M14 3v4h4"/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/>'
            '<rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    "wifi": '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.8 16a5 5 0 0 1 6.4 0"/><circle cx="12" cy="19.2" r=".9"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "cpu": '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5"/><path d="M9.5 3v3.5M14.5 3v3.5M9.5 17.5V21M14.5 17.5V21'
           'M3 9.5h3.5M3 14.5h3.5M17.5 9.5H21M17.5 14.5H21"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6.5 10h1M10.5 10h1M14.5 10h1M7 14h10"/>',
    "star": '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.9z"/>',
    "layers": '<path d="m12 3.5 9 5-9 5-9-5z"/><path d="m3 13.5 9 5 9-5"/>',
    "battery": '<rect x="2.5" y="7" width="16.5" height="10" rx="2"/><path d="M21.5 10.5v3"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m21 16-5-5-9 9"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10.5 5-3v9l-5-3z"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    "bell": '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5z"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.2"/>',
    "alert": '<path d="M12 3.5 21.5 20h-19z"/><path d="M12 10v4.5M12 17.3v.2"/>',
    "usb": '<path d="M12 3v14M9 6l3-3 3 3"/><circle cx="12" cy="19" r="2"/><path d="M12 13 7 10V8M12 15l5-3v-2"/>',
}

_cache: dict[tuple, QIcon] = {}
_bound: list[tuple[weakref.ref, str, str, int]] = []
_colors: dict[str, str] = {"muted": "#8b8d94", "text": "#ececee", "accent": "#7c5cff", "white": "#ffffff", "danger": "#ef4444"}


def set_colors(**colors: str) -> None:
    _colors.update(colors)
    _cache.clear()


def has(name: str) -> bool:
    return name in ICONS


def pixmap(name: str, color: str = "muted", size: int = 18) -> QPixmap:
    col = _colors.get(color, color)
    dpr = QGuiApplication.instance().devicePixelRatio() if QGuiApplication.instance() else 1.0
    dpr = max(dpr, 2.0)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{col}" '
           f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS.get(name, "")}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = "muted", size: int = 18) -> QIcon:
    key = (name, _colors.get(color, color), size)
    if key not in _cache:
        _cache[key] = QIcon(pixmap(name, color, size))
    return _cache[key]


def bind(widget, name: str, color: str = "muted", size: int = 18) -> None:
    """Set an icon on a button/label and keep it in sync with theme changes."""
    _apply(widget, name, color, size)
    _bound[:] = [b for b in _bound if b[0]() is not None and b[0]() is not widget]
    _bound.append((weakref.ref(widget), name, color, size))


def _apply(widget, name: str, color: str, size: int) -> None:
    try:
        if hasattr(widget, "setIcon"):
            widget.setIcon(icon(name, color, size))
            widget.setIconSize(QSize(size, size))
        else:
            widget.setPixmap(pixmap(name, color, size))
    except RuntimeError:
        pass  # widget already deleted


def refresh_all() -> None:
    alive = []
    for ref, name, color, size in _bound:
        w = ref()
        if w is None:
            continue
        _apply(w, name, color, size)
        alive.append((ref, name, color, size))
    _bound[:] = alive
