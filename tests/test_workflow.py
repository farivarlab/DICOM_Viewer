from pathlib import Path
import time

import numpy as np
import pytest
from pydicom.uid import generate_uid
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lumen.app import MainWindow
from lumen.browser import Target, ROLE
from lumen.model import scan_paths, load_series, demo_volume
from lumen.slice_view import Mark
from lumen.export_dialog import ExportDialog
from lumen.theme import STYLE
from test_imaging import write_image


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    return application


@pytest.fixture
def window(app):
    viewer = MainWindow()
    viewer.show()
    app.processEvents()
    yield viewer
    viewer.close()
    app.processEvents()


@pytest.fixture
def study(tmp_path):
    uid, study_uid = generate_uid(), generate_uid()
    for i in range(3):
        write_image(tmp_path / f"file_{3-i}.dcm", np.full((64, 80), i * 50),
                    position=(0, 0, i * 4), series_uid=uid, instance=3-i, spacing=(1, 1),
                    PatientID="SYNTHETIC-123", StudyInstanceUID=study_uid,
                    StudyDescription="Test case", PatientBirthDate="19800101",
                    InstitutionName=f"Synthetic site {i}")
    series = scan_paths([tmp_path]).series[0]
    return series, load_series(series)


def install(window, study, app):
    series, data = study
    window.series.append(series)
    window.populate_series()
    window.set_data(data)
    app.processEvents()
    return data


def test_default_is_centered_2d_and_metadata_is_hidden(window, study, app):
    data = install(window, study, app)
    assert window.mode == "2D stack"
    assert window.source_index == 0
    assert window.active_view.plane == "Source"
    assert not window.metadata_dock.isVisible()
    assert not window.tags_action.isChecked()
    assert window.volume_view.vtk_widget is None
    assert not window.mpr_controls.isVisible()
    assert not window.volume_controls.isVisible()
    view = window.active_view
    center = view.mapFromScene(view.item.sceneBoundingRect().center())
    assert (center - view.viewport().rect().center()).manhattanLength() <= 2
    window.resize(1300, 800)
    app.processEvents()
    center = view.mapFromScene(view.item.sceneBoundingRect().center())
    assert (center - view.viewport().rect().center()).manhattanLength() <= 2


def test_browser_hierarchy_file_selection_and_navigation_stay_synced(window, study, app):
    data = install(window, study, app)
    tree = window.browser
    patient = tree.topLevelItem(0)
    assert "SYNTHETIC-123" in patient.text(0)
    case = patient.child(0)
    assert "Test case" in case.text(0)
    series = case.child(0)
    assert series.childCount() == 3
    assert series.child(0).data(0, ROLE).path == data.reference(0).path
    tree.setCurrentItem(series.child(2))
    assert window.source_index == 2
    window.scroll_slice("Source", -1)
    assert window.source_index == 1
    assert tree.currentItem().data(0, ROLE).path == data.reference(1).path
    window.slice_spin.setValue(3)
    assert window.source_index == 2
    window.previous_button.click()
    assert window.source_index == 1
    window.next_button.click()
    assert window.source_index == 2


def test_browser_search_finds_file_and_shows_ancestors(window, study, app):
    install(window, study, app)
    tree = window.browser
    window.search.setText("file_2.dcm")
    root = tree.topLevelItem(0)
    assert not root.isHidden()
    series = root.child(0).child(0)
    visible = [series.child(i).text(0) for i in range(series.childCount()) if not series.child(i).isHidden()]
    assert visible == ["file_2.dcm"]
    window.search.clear()
    assert all(not series.child(i).isHidden() for i in range(series.childCount()))


def test_metadata_and_view_annotations_follow_current_file(window, study, app):
    data = install(window, study, app)
    window.tags_action.trigger()
    app.processEvents()
    assert window.metadata_dock.isVisible()
    assert window.tags_action.isChecked()
    window.slider_changed(2)
    assert data.reference(2).path.name in window.metadata_pane.caption.text()
    assert any("Synthetic site 2" in row[3] for row in window.metadata_pane.rows)
    left, right = window.active_view.file_information
    assert "Test Phantom" in left
    assert "ID: SYNTHETIC-123" in left
    assert "DOB 1980-01-01" in left
    assert "Synthetic site 2" in right
    assert "PixelData" not in data.header(2)
    window.metadata_dock.close()
    app.processEvents()
    assert not window.tags_action.isChecked()


def test_import_worker_opens_first_image_in_simple_view(window, study, app):
    series, _ = study
    window.open_paths([str(series.paths[0].parent)])
    deadline = time.monotonic() + 15
    while (window.busy or window.data is None) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert window.data is not None and not window.busy
    assert window.mode == "2D stack"
    assert window.source_index == 0
    assert window.browser.currentItem().data(0, ROLE).path == window.data.reference(0).path
    assert window.volume_view.vtk_widget is None


def test_opening_another_file_returns_from_mpr_to_2d(window, study, app):
    data = install(window, study, app)
    window.mode_combo.setCurrentText("MPR")
    assert window.mode == "MPR"
    window.open_target(Target(data.series.uid, "file", data.reference(2).path))
    assert window.mode == "2D stack"
    assert window.source_index == 2


def image_bytes(image):
    return np.frombuffer(image.bits(), dtype=np.uint8).copy()


def test_clean_png_export_omits_marks_info_and_guides(window, study, app, tmp_path):
    data = install(window, study, app)
    view = window.active_view
    before = image_bytes(window.image_capture(annotated=False))
    view.marks.append(Mark("Length", [QPointF(10, 12), QPointF(60, 44)], view.key))
    view.marks.append(Mark("Text", [QPointF(5, 25)], view.key, "TEST ANNOTATION"))
    clean = window.image_capture(annotated=False)
    assert clean.size().width() == 80
    assert clean.size().height() == 64
    np.testing.assert_array_equal(image_bytes(clean), before)
    annotated = window.image_capture(annotated=True)
    assert not np.array_equal(image_bytes(annotated), before)
    with_info = window.image_capture(annotated=True, include_information=True)
    assert not np.array_equal(image_bytes(with_info), image_bytes(annotated))
    assert len(view.marks) == 2
    for name, image in (("clean", clean), ("annotated", annotated)):
        path = tmp_path / f"{name}.png"
        assert image.save(str(path), "PNG")
        assert QImage(str(path)).size() == image.size()


def test_export_preserves_rotation_and_flip_independently_of_zoom(window, study, app):
    install(window, study, app)
    view = window.active_view
    base = window.image_capture(False)
    view.scale(2, 2)
    view.centerOn(QPointF(10, 10))
    assert window.image_capture(False).size() == base.size()
    view.rotate()
    rotated = window.image_capture(False)
    assert (rotated.width(), rotated.height()) == (64, 80)
    view.flip(True)
    assert window.image_capture(False).size() == rotated.size()


def test_export_options_enforce_clean_output(app):
    dialog = ExportDialog()
    dialog.information.setChecked(True)
    assert dialog.annotated and dialog.include_information
    dialog.content.setCurrentIndex(1)
    assert not dialog.annotated
    assert not dialog.include_information
    assert not dialog.information.isEnabled()
    dialog.close()


def test_multiframe_browser_selects_exact_frame(window, app, tmp_path):
    path = tmp_path / "cine.dcm"
    write_image(path, np.zeros((4, 64, 80)), PatientID="CINE")
    series = scan_paths([tmp_path]).series[0]
    data = load_series(series)
    install(window, (series, data), app)
    parent = window.browser.series_items[series.uid]
    file = parent.child(0)
    file.setExpanded(True)
    assert file.childCount() == 4
    window.browser.setCurrentItem(file.child(3))
    assert window.source_index == 3
    assert "frame 4" in window.active_view.subtitle


def test_dicom_overlay_origin_and_clean_export(window, app, tmp_path):
    path = tmp_path / "overlay.dcm"
    ds = write_image(path, np.zeros((64, 80)), intercept=0)
    mask = np.ones((8, 10), np.uint8)
    ds.add_new((0x6000, 0x0010), "US", 8)
    ds.add_new((0x6000, 0x0011), "US", 10)
    ds.add_new((0x6000, 0x0040), "CS", "G")
    ds.add_new((0x6000, 0x0050), "SS", [5, 7])
    ds.add_new((0x6000, 0x0100), "US", 1)
    ds.add_new((0x6000, 0x0102), "US", 0)
    ds.add_new((0x6000, 0x3000), "OW", np.packbits(mask.ravel(), bitorder="little").tobytes())
    ds.save_as(path, enforce_file_format=True)
    series = scan_paths([tmp_path]).series[0]
    data = load_series(series)
    install(window, (series, data), app)
    row, column, decoded = data.overlay_layers(0)[0]
    assert (row, column) == (4, 6)
    np.testing.assert_array_equal(decoded, mask)
    assert len(window.active_view.overlay_items) == 1
    clean = window.image_capture(False)
    annotated = window.image_capture(True)
    x = round(7 * data.spacing[0] / min(data.spacing[:2]))
    y = round(5 * data.spacing[1] / min(data.spacing[:2]))
    assert clean.pixelColor(x, y) != annotated.pixelColor(x, y)
    window.embedded_overlays.setChecked(False)
    assert not window.active_view.overlay_items[0].isVisible()
