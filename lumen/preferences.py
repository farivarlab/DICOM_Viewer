"""Portable preferences shared by startup and the main window."""
from pathlib import Path
import sys
from PySide6.QtCore import QSettings


def open_settings(path=None):
    if path is None:
        root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        path = root / ".lumen-settings.ini"
    return QSettings(str(path), QSettings.Format.IniFormat)


def saved_theme(settings):
    from .theme import THEME_NAMES
    name = settings.value("appearance/theme", "modern-light")
    if settings.value("appearance/version", 0, type=int) < 2:
        name = {"light": "modern-light", "dark": "cockpit"}.get(name, name)
        settings.setValue("appearance/theme", name)
        settings.setValue("appearance/version", 2)
        settings.sync()
    return name if name in THEME_NAMES else "modern-light"
