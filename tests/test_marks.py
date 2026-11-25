"""Measurements survive series switches, and individual marks can be picked and deleted."""
import numpy as np
import pytest
from pydicom.uid import generate_uid
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from lumen.app import MainWindow
from lumen.model import scan_paths, load_series, demo_volume
from lumen.slice_view import Mark
from test_imaging import write_image


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    viewer = MainWindow(settings_path=tmp_path / "settings.ini")
    viewer.show()
    app.processEvents()
    yield viewer
    viewer.close()
    app.processEvents()


@pytest.fixture
def study(tmp_path):
    uid = generate_uid()
    folder = tmp_path / "study"
    folder.mkdir()
    for i in range(3):
        write_image(folder / f"file_{i}.dcm", np.full((64, 80), i * 50), position=(0, 0, i * 4),
                    series_uid=uid, instance=i + 1, spacing=(1, 1))
    series = scan_paths([folder]).series[0]
    return series, load_series(series, reconstruct=False)


def open_data(window, app, data):
    if data.series not in window.series:
        window.series.append(data.series)
        window.populate_series()
    window.set_data(data)
    app.processEvents()


def test_marks_are_restored_when_returning_to_a_series(window, study, app):
    series, data = study
    open_data(window, app, data)
    view = window.views["Source"]
    window.slider_changed(1)
    length = Mark("Length", [QPointF(5, 5), QPointF(40, 30)], view.key)
    view.marks.append(length)
    demo = demo_volume()
    open_data(window, app, demo)
    assert window.views["Source"].marks == []
    open_data(window, app, load_series(series, reconstruct=False))  # a fresh load of the same series
    view = window.views["Source"]
    assert view.marks == [length]
    window.slider_changed(1)
    assert view.visible_marks() == [length]
    window.slider_changed(0)
    assert view.visible_marks() == []


def test_clear_marks_also_forgets_the_saved_copy(window, study, app):
    series, data = study
    open_data(window, app, data)
    view = window.views["Source"]
    view.marks.append(Mark("Length", [QPointF(5, 5), QPointF(40, 30)], view.key))
    window.clear_marks()
    open_data(window, app, demo_volume())
    open_data(window, app, data)
    assert window.views["Source"].marks == []


def test_source_marks_follow_file_frame_not_stack_position(window, study, app):
    _, data = study
    open_data(window, app, data)
    window.slider_changed(2)
    view = window.views["Source"]
    reference = data.reference(2)
    assert view.key == ("Source", reference.path, reference.frame)


def test_click_selects_a_mark_and_delete_removes_only_that_one(window, study, app):
    _, data = study
    open_data(window, app, data)
    view = window.views["Source"]
    first = Mark("Length", [QPointF(5, 5), QPointF(60, 5)], view.key)
    second = Mark("Length", [QPointF(5, 40), QPointF(60, 40)], view.key)
    view.marks.extend([first, second])
    view.repaint()
    on_first = view.screen_at(QPointF(30, 5))
    assert view.mark_at(on_first) is first
    assert view.mark_at(view.screen_at(QPointF(30, 22))) is None
    window.select_tool("Pan")
    view.mousePressEvent(_mouse(Qt.MouseButton.LeftButton, on_first))
    view.mouseReleaseEvent(_mouse(Qt.MouseButton.LeftButton, on_first, release=True))
    assert view.selected is first
    view.keyPressEvent(_key(Qt.Key.Key_Delete))
    assert view.marks == [second] and view.selected is None
    # With nothing selected, Delete keeps its old meaning: remove the newest mark on this image.
    view.marks.append(first)
    view.keyPressEvent(_key(Qt.Key.Key_Delete))
    assert view.marks == [second]


def test_drawing_tools_do_not_select_and_menu_deletes_the_clicked_mark(window, study, app):
    _, data = study
    open_data(window, app, data)
    view = window.views["Source"]
    roi = Mark("Rectangle", [QPointF(10, 10), QPointF(40, 30)], view.key)
    arrow = Mark("Arrow", [QPointF(50, 50), QPointF(70, 60)], view.key)
    view.marks.extend([roi, arrow])
    view.repaint()
    window.select_tool("Length")
    edge = view.screen_at(QPointF(10, 20))
    view.mousePressEvent(_mouse(Qt.MouseButton.LeftButton, edge))
    assert view.selected is None
    view.mouseReleaseEvent(_mouse(Qt.MouseButton.LeftButton, edge, release=True))
    view.marks = [roi, arrow]
    assert view.mark_at(edge) is roi
    assert view.mark_at(view.screen_at(QPointF(25, 20))) is None  # ROI interior is not its outline
    menu = view.mark_menu(arrow)
    assert [a.text() for a in menu.actions()] == ["Delete arrow", "Delete all marks on this image"]
    menu.actions()[0].trigger()
    assert view.marks == [roi]


def test_selection_highlight_is_not_exported(window, study, app):
    _, data = study
    open_data(window, app, data)
    view = window.views["Source"]
    mark = Mark("Length", [QPointF(5, 5), QPointF(60, 40)], view.key)
    view.marks.append(mark)
    plain = view.render_image(annotated=True, include_colorbar=False)
    view.selected = mark
    selected = view.render_image(annotated=True, include_colorbar=False)
    assert plain == selected


def _mouse(button, point, release=False):
    from PySide6.QtCore import QEvent, QPointF as F
    from PySide6.QtGui import QMouseEvent
    kind = QEvent.Type.MouseButtonRelease if release else QEvent.Type.MouseButtonPress
    buttons = Qt.MouseButton.NoButton if release else button
    return QMouseEvent(kind, F(point), F(point), button, buttons, Qt.KeyboardModifier.NoModifier)


def _key(key):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
