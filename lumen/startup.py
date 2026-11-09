"""Show a small startup window before loading the imaging libraries."""
import sys
import traceback

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor
from PySide6.QtWidgets import QApplication, QSplashScreen, QMessageBox

from . import __version__
from .preferences import open_settings, saved_theme
from .branding import application_icon, set_process_identity, update_windows_icon


def create_splash(app, theme):
    from .theme import load_theme
    assets = load_theme(theme)
    colors = assets.colors
    scale = app.primaryScreen().devicePixelRatio() if app.primaryScreen() else 1.
    pixmap = QPixmap(round(360 * scale), round(132 * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(QColor(colors["window"]))
    painter = QPainter(pixmap)
    painter.setPen(QColor(colors["border"]))
    painter.drawRect(QRectF(.5, .5, 359, 131))
    application_icon().paint(painter, 20, 25, 40, 40)
    painter.setPen(QColor(colors["text"]))
    painter.setFont(QFont(assets.font_family, assets.font_size + 3, QFont.Weight.DemiBold))
    painter.drawText(76, 43, "Lumen DICOM Viewer")
    painter.setFont(QFont(assets.font_family, assets.font_size))
    painter.setPen(QColor(colors["muted"]))
    painter.drawText(76, 65, "Starting viewer…")
    painter.setPen(QColor(colors["text"]))
    painter.setFont(QFont(assets.font_family, assets.font_size, QFont.Weight.DemiBold))
    painter.drawText(QRectF(20, 103, 270, 20), Qt.AlignmentFlag.AlignLeft, "Not For Diagnostic Use")
    painter.setFont(QFont(assets.font_family, assets.font_size))
    painter.setPen(QColor(colors["muted"]))
    painter.drawText(QRectF(20, 103, 320, 20), Qt.AlignmentFlag.AlignRight, __version__)
    painter.end()
    splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
    splash.setWindowIcon(application_icon())
    return splash


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if any(arg in ("-h", "--help") for arg in arguments):
        from .app import main as viewer_main
        return viewer_main(arguments)
    set_process_identity()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    splash = None
    try:
        from .theme import apply_theme
        app.setWindowIcon(application_icon())
        app.setStyle("Fusion")
        theme = saved_theme(open_settings())
        apply_theme(app, theme)
        splash = create_splash(app, theme)
        splash.show()
        app.processEvents()
        update_windows_icon(application_icon())
        from .app import main as viewer_main
        return viewer_main(arguments, splash=splash)
    except Exception as error:
        if splash is not None:
            splash.hide()
        traceback.print_exc()
        QMessageBox.critical(None, "Unable to start Lumen", str(error))
        return 1
    finally:
        if splash is not None:
            splash.close()
