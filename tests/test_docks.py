"""Panels retain their live controls when floated, moved, hidden and redocked."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QDockWidget
from lumen.app import MainWindow
from lumen.model import demo_volume


@pytest.mark.parametrize("panel,area", [
    ("browser_dock", Qt.DockWidgetArea.LeftDockWidgetArea),
    ("display_dock", Qt.DockWidgetArea.RightDockWidgetArea),
])
def test_detachable_panels(tmp_path, panel, area):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "settings.ini")
    window.show()
    try:
        data = demo_volume()
        window.series = [data.series]
        window.populate_series()
        window.set_data(data)
        app.processEvents()
        dock = getattr(window, panel)
        assert window.dockWidgetArea(dock) == area
        assert dock.isVisible() and not dock.isFloating()
        assert not window.metadata_dock.isVisible()
        assert dock.features() & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert dock.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        content = dock.widget()
        dock.setFloating(True)
        app.processEvents()
        assert dock.isFloating() and dock.isWindow()
        assert dock.floating_title_bar.isVisible()
        dock.move(QPoint(100, 100))
        app.processEvents()
        assert dock.pos() == QPoint(100, 100)
        window.slider_changed(45)
        window.width_spin.setValue(700)
        assert window.source_index == 45 and window.active_view.width == 700
        assert window.browser.isVisible() and window.width_spin.isVisible()
        assert window.set_theme("cockpit", persist=False)
        dock.close()
        app.processEvents()
        assert not dock.isVisible() and not dock.toggleViewAction().isChecked()
        dock.toggleViewAction().trigger()
        app.processEvents()
        assert dock.isVisible() and dock.isFloating()
        dock.setFloating(False)
        opposite = Qt.DockWidgetArea.RightDockWidgetArea if area == Qt.DockWidgetArea.LeftDockWidgetArea else Qt.DockWidgetArea.LeftDockWidgetArea
        window.addDockWidget(opposite, dock)
        app.processEvents()
        assert not dock.isFloating() and window.dockWidgetArea(dock) == opposite
        assert dock.widget() is content and window.data is data
        assert window.active_view.width == 700
    finally:
        window.close()
        app.processEvents()
