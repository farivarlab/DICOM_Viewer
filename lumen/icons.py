"""Fluent System Icons (MIT) and original glyphs for specialist imaging tools."""
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

GLYPHS = {
    "colorbar": '<path d="M5 3h8v18H5Z M5 7h8 M5 12h8 M5 17h8 M16 3h5 M16 12h3 M16 21h5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2"/>',
    "moon": '<path d="M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12Z"/>',
    "open": '<path d="M14 3H5v18h14V8Z M14 3v5h5 M8 14h8 m-3-3 3 3-3 3"/>',
    "folder": '<path d="M3 7V5h7l2 2h9v13H3Z M3 10h18"/>',
    "demo": '<path d="m12 2 9 5v10l-9 5-9-5V7Z M3 7l9 5 9-5 M12 12v10"/><path d="m8 5 9 5"/>',
    "window": '<circle cx="12" cy="12" r="6"/><path d="M12 6v12 M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1.5 1.5 M17.5 17.5 19 19 M5 19l1.5-1.5 M17.5 6.5 19 5"/><path d="M12 6a6 6 0 0 1 0 12Z" fill="currentColor" stroke="none"/>',
    "pan": '<path d="M12 3v18 M3 12h18 M9 6l3-3 3 3 M9 18l3 3 3-3 M6 9l-3 3 3 3 M18 9l3 3-3 3"/>',
    "zoom": '<circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6 M10 7v6 M7 10h6"/>',
    "scroll": '<path d="M4 5h9 M4 9h9 M4 13h9 M4 17h9 M18 3v18 M15 6l3-3 3 3 M15 18l3 3 3-3"/>',
    "crosshair": '<circle cx="12" cy="12" r="6"/><path d="M12 2v7 M12 15v7 M2 12h7 M15 12h7"/>',
    "length": '<path d="m4 17 13-13 4 4L8 21Z M7 14l2 2 M10 11l3 3 M13 8l2 2 M16 5l3 3"/>',
    "rectangle": '<rect x="4" y="5" width="16" height="14"/><path d="M2 5h4 M4 3v4 M18 19h4 M20 17v4"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="6"/><path d="M12 3v3 M12 18v3 M1 12h3 M20 12h3"/>',
    "angle": '<path d="m5 3 2 16h15 M7 19 19 6 M7 12a7 7 0 0 1 5 2"/><path d="M5 18h4v3H5Z" fill="currentColor" stroke="none"/>',
    "arrow": '<path d="M4 20 20 4 M9 4h11v11"/>',
    "text": '<path d="M4 4h16 M12 4v16 M8 20h8 M4 4v4 M20 4v4"/>',
    "fit": '<path d="M3 9V3h6 M15 3h6v6 M21 15v6h-6 M9 21H3v-6 M7 7l3 3 M17 7l-3 3 M7 17l3-3 M17 17l-3-3"/>',
    "reset": '<path d="M4 10a8 8 0 1 1 1 8 M4 4v6h6"/>',
    "rotate": '<path d="M4 8a8 8 0 0 1 13-3l3 3 M20 2v6h-6 M5 12h8v8H5Z"/>',
    "flip_h": '<path d="M12 2v3 M12 8v3 M12 14v3 M12 20v2 M3 6l6 6-6 6Z M21 6l-6 6 6 6Z"/>',
    "flip_v": '<path d="M2 12h3 M8 12h3 M14 12h3 M20 12h2 M6 3l6 6 6-6Z M6 21l6-6 6 6Z"/>',
    "invert": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18Z" fill="currentColor" stroke="none"/><path d="M12 3v18"/>',
    "clear": '<path d="m4 15 9-11 8 7-8 10H9Z M9 9l8 7 M13 21h9"/>',
    "play": '<path d="m7 3 14 9-14 9Z"/>',
    "pause": '<path d="M6 4h4v16H6Z M15 4h4v16h-4Z" fill="currentColor" stroke="none"/>',
    "save": '<rect x="3" y="3" width="18" height="18"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7 M14 21h7"/>',
    "copy": '<path d="M8 8h13v13H8Z M16 5V2H2v14h3"/>',
    "tags": '<path d="M4 3h16v18H4Z M7 7h2 M12 7h5 M7 12h2 M12 12h5 M7 17h2 M12 17h5"/>',
    "fullscreen": '<path d="M3 9V3h6 M15 3h6v6 M21 15v6h-6 M9 21H3v-6"/>',
    "camera": '<path d="M3 7h4l2-3h6l2 3h4v14H3Z"/><circle cx="12" cy="13" r="4"/><path d="M12 10v3l2 1"/>',
    "help": '<path d="M8 8a4 4 0 1 1 6 3.5c-2 1-2 2-2 3 M12 18v1"/><circle cx="12" cy="12" r="10"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 10v7 M12 6v1"/>',
    "exit": '<path d="M10 3H3v18h7 M8 12h13 M16 7l5 5-5 5"/>',
    "close": '<path d="m5 5 14 14 M5 19 19 5"/>',
    "export": '<path d="M3 3h11v18H3Z M6 7h5 M6 11h5 M6 15h5 M15 11h7 M19 8l3 3-3 3"/>',
    "patient": '<circle cx="12" cy="7" r="4"/><path d="M4 22v-3a8 8 0 0 1 16 0v3"/>',
    "case": '<path d="M3 7h18v14H3Z M8 7V3h8v4 M9 13h6 M12 10v6"/>',
    "series": '<path d="M3 3h14v3 M7 7h14v14H7Z M3 7v10h3 M10 17l3-4 3 3 2-2 3 3"/>',
    "image": '<rect x="3" y="3" width="18" height="18"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    "previous": '<path d="m15 4-8 8 8 8"/>',
    "next": '<path d="m9 4 8 8-8 8"/>',
}


_theme = "light"
_palette = ("#323232", "#527f80", "#999999", "#18393a")
_icon_specs = {}
FLUENT_ROOT = Path(__file__).resolve().parent / "resources" / "fluent"
FLUENT_GLYPHS = frozenset((
    "open", "folder", "demo", "sun", "moon", "pan", "zoom", "fit", "reset", "rotate",
    "clear", "play", "pause", "save", "copy", "tags", "fullscreen", "camera", "help",
    "info", "exit", "close", "export", "patient", "case", "series", "image", "previous", "next",
))


@lru_cache(maxsize=40)
def _fluent_svg(name):
    return (FLUENT_ROOT / f"{name}.svg").read_text(encoding="utf-8")


def _svg(name, ink):
    if name in FLUENT_GLYPHS:
        return _fluent_svg(name).replace('fill="#212121"', f'fill="{ink}"').replace('fill="currentColor"', f'fill="{ink}"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
            f'fill="none" stroke="{ink}" color="{ink}" stroke-width="1.6" '
            f'stroke-linecap="square" stroke-linejoin="miter">{GLYPHS[name]}</svg>')


def set_icon_theme(name, colors=None):
    global _theme, _palette
    _theme = name
    if colors:
        _palette = (colors["glyph_foreground"], colors["accent"], colors["glyph_disabled"], colors["selected_text"])


def icon(name: str, size: int = 20, color: str | None = None) -> QIcon:
    result = _render_icon(name, size, color, _palette)
    _icon_specs[result.cacheKey()] = (name, size, color)
    return result


def retheme_icon(current):
    spec = _icon_specs.get(current.cacheKey())
    return icon(*spec) if spec else current


@lru_cache(maxsize=256)
def _render_icon(name, size, color, palette):
    if name not in GLYPHS:
        raise KeyError(f"Unknown glyph: {name}")
    result = QIcon()
    normal, accent, disabled, selected = palette
    for mode, mode_color in ((QIcon.Mode.Normal, normal), (QIcon.Mode.Active, accent),
                        (QIcon.Mode.Selected, selected), (QIcon.Mode.Disabled, disabled)):
        ink = color if color and mode != QIcon.Mode.Disabled else mode_color
        svg = _svg(name, ink)
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        result.addPixmap(pixmap, mode)
        # Checked tools retain the selection color even without mouse hover.
        if mode != QIcon.Mode.Disabled:
            checked = svg.replace(ink, color or accent)
            checked_renderer = QSvgRenderer(QByteArray(checked.encode()))
            checked_pixmap = QPixmap(size * 2, size * 2)
            checked_pixmap.fill(Qt.GlobalColor.transparent)
            checked_painter = QPainter(checked_pixmap)
            checked_renderer.render(checked_painter)
            checked_painter.end()
            checked_pixmap.setDevicePixelRatio(2)
            result.addPixmap(checked_pixmap, mode, QIcon.State.On)
    return result


def clear_icon_cache():
    _fluent_svg.cache_clear()
    _render_icon.cache_clear()


ACTION_ICONS = {
    "Open files…": "open", "Open folder…": "folder", "Load demo": "demo",
    "Save image…": "save", "Copy image": "copy", "DICOM tags": "tags",
    "Fit": "fit", "Reset": "reset", "Rotate 90°": "rotate", "Flip H": "flip_h",
    "Flip V": "flip_v", "Clear marks": "clear", "Play cine": "play", "Invert": "invert",
    "Full screen": "fullscreen", "Window": "window", "Pan": "pan", "Zoom": "zoom",
    "Scroll": "scroll", "Crosshair": "crosshair", "Length": "length", "Rectangle": "rectangle",
    "Ellipse": "ellipse", "Angle": "angle", "Arrow": "arrow", "Text": "text", "Exit": "exit",
    "Controls": "help", "About Lumen": "info",
    "Third-party notices": "info",
    "Light theme": "sun", "Dark theme": "moon",
    "Export NIfTI…": "export",
    "Colorbar": "colorbar",
    "Modern dark": "moon", "Modern light": "sun", "Classic light": "sun", "Classic dark": "moon",
    "Reload appearance assets": "reset", "Open logo folder": "folder", "Open theme folder": "folder",
}
