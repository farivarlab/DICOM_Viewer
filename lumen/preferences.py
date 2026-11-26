"""Portable preferences shared by startup and the main window."""
import os
from pathlib import Path
import sys
from PySide6.QtCore import QSettings


def data_root() -> Path:
    """Where preferences and saved annotations live.

    From source and in the portable Windows build this is beside the program, so the
    folder carries its own settings. A macOS app bundle must not be modified (that breaks
    its signature) and a Linux install folder may be read only, so packaged builds there
    use the per-user application-data folder.
    """
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    if sys.platform == "win32":
        return Path(sys.executable).parent
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "Lumen DICOM"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "lumen-dicom"
    root.mkdir(parents=True, exist_ok=True)
    return root


def open_settings(path=None):
    if path is None:
        path = data_root() / ".lumen-settings.ini"
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
