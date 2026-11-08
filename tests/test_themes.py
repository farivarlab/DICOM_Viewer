import numpy as np
from PySide6.QtGui import QPalette

from lumen.app import MainWindow
from lumen.theme import apply_theme
from test_workflow import app, study, install


def test_theme_switch_keeps_image_values_selection_and_marks(app, study, tmp_path):
    window = MainWindow(settings_path=tmp_path / "settings.ini")
    window.show()
    install(window, study, app)
    before = window.image_capture(False)
    original = bytes(before.bits())
    old_icon = window.open_action.icon().cacheKey()
    try:
        window.set_theme("dark", persist=False)
        app.processEvents()
        assert window.theme_name == "dark"
        assert window.theme_actions["dark"].isChecked()
        assert window.theme_toggle.isChecked()
        assert app.palette().color(QPalette.ColorRole.Base).lightness() < 60
        assert window.open_action.icon().cacheKey() != old_icon
        assert bytes(window.image_capture(False).bits()) == original
        assert window.mode == "2D stack"
        window.theme_actions["light"].trigger()
        assert window.theme_name == "light"
        assert app.palette().color(QPalette.ColorRole.Base).lightness() > 230
    finally:
        window.close()
        apply_theme(app, "light")


def test_theme_preference_uses_portable_ini(app, tmp_path):
    settings = tmp_path / "portable.ini"
    first = MainWindow(settings_path=settings)
    first.set_theme("dark")
    first.close()
    second = MainWindow(settings_path=settings)
    try:
        assert settings.is_file()
        assert second.theme_name == "dark"
        assert second.theme_actions["dark"].isChecked()
    finally:
        second.close()
        apply_theme(app, "light")
