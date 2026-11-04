import time
import numpy as np
import pytest
from PySide6.QtCore import QPointF
from pydicom.uid import generate_uid

from lumen.browser import ROLE, Target
from lumen.model import load_series, scan_paths
from lumen.slice_view import roi_statistics
from test_imaging import write_image
from test_workflow import app, window, study, install


def wait_for_idle(window, app):
    deadline = time.monotonic() + 10
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert not window.busy


def test_default_import_defers_mpr_until_requested(window, study, app):
    series, _ = study
    window.open_paths([str(series.paths[0].parent)])
    wait_for_idle(window, app)
    assert window.data.mpr_available and not window.data.mpr_ready
    assert window.mode == "2D stack"
    window.mode_combo.setCurrentText("MPR")
    assert window.busy
    wait_for_idle(window, app)
    assert window.mode == "MPR" and window.data.mpr_ready
    assert window.views["Axial"].image is not None


def test_cancel_restores_active_file_and_controls(window, study, app):
    data = install(window, study, app)
    window.slider_changed(1)
    callbacks = []

    def slow_job(progress):
        for _ in range(100):
            progress("Working")
            time.sleep(.005)
        return 123

    window.start_job(slow_job, callbacks.append)
    assert not window.mode_combo.isEnabled()
    window.cancel_job()
    wait_for_idle(window, app)
    assert callbacks == []
    assert window.data is data
    assert window.browser.currentItem().data(0, ROLE).path == data.reference(1).path
    assert window.mode_combo.isEnabled()
    assert not window.cancel_button.isVisible()


def test_closing_during_work_cancels_and_closes_without_second_attempt(window, study, app):
    install(window, study, app)

    def slow_job(progress):
        for _ in range(100):
            progress("Working")
            time.sleep(.005)

    window.start_job(slow_job, lambda result: pytest.fail("Cancelled result should not be displayed"))
    window.close()
    wait_for_idle(window, app)
    assert not window.isVisible()


def test_fit_preserves_rotation_and_flip_but_reset_clears_them(window, study, app):
    install(window, study, app)
    view = window.active_view
    view.rotate()
    view.flip(True)
    before = view.transform()
    view.fit_image()
    fitted = view.transform()
    assert fitted.determinant() < 0
    assert abs(fitted.m11()) < 1e-6
    assert abs(fitted.m12()) > .1
    view.reset()
    assert view.transform().determinant() > 0
    assert abs(view.transform().m12()) < 1e-6


def test_off_image_rois_are_empty():
    for p, q in ((QPointF(-10, 0), QPointF(-5, 10)),
                 (QPointF(0, -10), QPointF(10, -5)),
                 (QPointF(150, 0), QPointF(160, 10))):
        assert roi_statistics(np.zeros((144, 144)), p, q, False, (1, 1)) == "Empty ROI"


def test_manual_window_has_honest_custom_label_and_survives_scroll(window, study, app):
    install(window, study, app)
    window.change_window(123, -321)
    assert window.preset.currentText() == "Custom"
    window.slider_changed(2)
    assert window.active_view.width == 123
    assert window.active_view.level == -321


def test_each_source_frame_uses_its_calibration_and_default_window(window, app, tmp_path):
    uid = generate_uid()
    write_image(tmp_path / "a.dcm", np.zeros((64, 80)), series_uid=uid,
                spacing=(2, 3), instance=1, WindowWidth=500, WindowCenter=100)
    write_image(tmp_path / "b.dcm", np.zeros((64, 80)), series_uid=uid,
                spacing=None, instance=2, WindowWidth=1200, WindowCenter=-500)
    series = scan_paths([tmp_path]).series[0]
    install(window, (series, load_series(series)), app)
    assert window.active_view.spacing == (3, 2)
    assert window.active_view.calibrated
    window.slider_changed(1)
    assert window.active_view.spacing == (1, 1)
    assert not window.active_view.calibrated
    assert (window.active_view.width, window.active_view.level) == (1200, -500)


def test_unchanged_pixels_and_overlays_are_not_regenerated(window, study, app, monkeypatch):
    install(window, study, app)
    view = window.active_view
    pixel_calls = []
    monkeypatch.setattr(view, "refresh_pixels", lambda: pixel_calls.append(True))
    window.refresh_views()
    assert pixel_calls == []
    window.change_window(1000, 30)
    assert pixel_calls == [True]


def test_duplicate_file_alias_selects_correct_source_frame(window, app, tmp_path):
    uid = generate_uid()
    write_image(tmp_path / "a.dcm", np.zeros((64, 80)), (0, 0, 0), series_uid=uid)
    ds = write_image(tmp_path / "b.dcm", np.ones((64, 80)), (0, 0, 4), series_uid=uid)
    ds.save_as(tmp_path / "duplicate.dcm", enforce_file_format=True)
    series = scan_paths([tmp_path]).series[0]
    data = install(window, (series, load_series(series)), app)
    window.open_target(Target(series.uid, "file", tmp_path / "duplicate.dcm"))
    assert window.source_index == 1
