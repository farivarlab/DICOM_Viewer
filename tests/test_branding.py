from pathlib import Path
import json
import subprocess
import sys

import pytest

from PySide6.QtWidgets import QApplication
from PIL import Image

from lumen import branding
from lumen.app import MainWindow
from lumen.export_dialog import ExportDialog
from lumen.startup import create_splash
from lumen.windows_shortcut import create_project_shortcut
from test_workflow import app, study, install


def write_logo(path, color):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="{color}"/></svg>')


def icon_color(icon):
    return icon.pixmap(32, 32).toImage().pixelColor(16, 16).name()


def test_built_in_logo_identifies_every_surface_and_cannot_be_replaced(app, study, tmp_path, monkeypatch):
    # A logo.svg beside the program no longer overrides the built-in one.
    monkeypatch.setattr(branding, "PROJECT_ROOT", tmp_path)
    write_logo(tmp_path / "logo.svg", "#bb3355")
    assert branding.logo_file() == Path(branding.__file__).with_name("resources") / "lumen.svg"
    window = MainWindow(settings_path=tmp_path / "settings.ini")
    window.show()
    install(window, study, app)
    image = window.image_capture(False)
    dialog = ExportDialog(window)
    dialog.show()
    splash = create_splash(app, window.theme_name)
    app.processEvents()
    try:
        expected = icon_color(branding.application_icon())
        assert expected != "#bb3355"
        menu_texts = {action.text() for action in window.findChildren(type(window.export_action))}
        assert "Open logo folder" not in menu_texts
        assert window.reload_appearance_assets()  # still reloads themes and glyphs
        for icon in (app.windowIcon(), window.windowIcon(), dialog.windowIcon(), splash.windowIcon(),
                     window.title_bar.system_button.icon()):
            assert icon_color(icon) == expected
        assert window.image_capture(False) == image
        assert dialog.title_bar.system_button.icon().isNull() is False
    finally:
        splash.close()
        dialog.close()
        window.close()
        app.processEvents()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts and ICO files")
def test_windows_shortcut_follows_changed_logo_without_changing_launch_options(app, tmp_path, monkeypatch):
    logo = tmp_path / "logo.svg"
    monkeypatch.setattr(branding, "LOGO_FILE", logo)
    monkeypatch.setattr(branding, "PROJECT_ROOT", tmp_path)
    target = tmp_path / ".venv/Scripts/pythonw.exe"
    target.parent.mkdir(parents=True)
    target.touch()
    write_logo(logo, "#bb3355")
    first = branding.update_windows_icon(branding.application_icon())
    shortcut = create_project_shortcut(tmp_path, first)
    write_logo(logo, "#3377aa")
    second = branding.update_windows_icon(branding.application_icon())
    assert first != second and first.exists()
    before = second.stat().st_mtime_ns
    assert branding.update_windows_icon(branding.application_icon()) == second
    assert second.stat().st_mtime_ns == before
    with Image.open(second) as image:
        assert image.ico.sizes() == {(n, n) for n in branding.ICON_SIZES}
    command = r"""
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($env:LUMEN_TEST_SHORTCUT)
@{Target=$link.TargetPath; Arguments=$link.Arguments; Icon=$link.IconLocation; WorkingDirectory=$link.WorkingDirectory} | ConvertTo-Json -Compress
"""
    import os
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            env=dict(os.environ, LUMEN_TEST_SHORTCUT=str(shortcut)),
                            creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, check=True, timeout=15)
    details = json.loads(result.stdout)
    assert Path(details["Target"]) == target
    assert details["Arguments"] == "-m lumen"
    assert details["Icon"] == str(second) + ",0"
    assert Path(details["WorkingDirectory"]) == tmp_path
