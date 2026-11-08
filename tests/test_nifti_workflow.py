import time
import nibabel as nib
import numpy as np
from lumen.app import MainWindow
from lumen.colors import window_pixels
from lumen.slice_view import roi_statistics
from PySide6.QtCore import QPointF
from test_workflow import app


def wait_idle(window, app):
    deadline = time.monotonic() + 15
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert not window.busy


def test_nifti_import_metadata_navigation_and_mpr(app, tmp_path):
    path = tmp_path / "fmri.nii.gz"
    values = np.arange(16 * 20 * 12 * 2, dtype=np.float32).reshape(16, 20, 12, 2)
    image = nib.Nifti1Image(values, np.diag([-1., -2., 3., 1.]))
    image.header.set_xyzt_units("mm", "sec")
    nib.save(image, path)
    window = MainWindow(settings_path=tmp_path / "settings.ini")
    window.show()
    errors = []
    def fail(message):
        errors.append(message)
        window.end_job()
    window.fail_job = fail
    try:
        window.open_paths([str(path)])
        wait_idle(window, app)
        assert not errors
        assert len(window.series) == 2
        assert window.data.series.source_format == "NIfTI"
        assert window.mode == "2D stack"
        assert window.preset.currentText() == "Volume default"
        assert window.active_view.distance_unit == "mm"
        assert window.export_nifti_action.isEnabled()
        window.tags_action.trigger()
        assert "NIfTI" in window.metadata_dock.windowTitle()
        assert any(row[0] == "affine_RAS" for row in window.metadata_pane.rows)
        window.slice_spin.setValue(5)
        assert window.source_index == 4
        window.mode_combo.setCurrentText("MPR")
        wait_idle(window, app)
        assert window.data.mpr_ready
        assert window.views["Coronal"].image is not None
    finally:
        window.close()
        app.processEvents()


def test_fractional_nifti_values_keep_contrast_and_precision(app, tmp_path):
    path = tmp_path / "probability.nii"
    values = np.linspace(0, .01, 16 * 20 * 4, dtype=np.float32).reshape(16, 20, 4)
    image = nib.Nifti1Image(values, np.eye(4))
    image.header.set_xyzt_units("mm")
    nib.save(image, path)
    window = MainWindow(settings_path=tmp_path / "settings.ini")
    window.show()
    try:
        window.open_paths([str(path)])
        wait_idle(window, app)
        assert 0 < window.data.width < .01
        assert np.isclose(window.width_spin.value(), window.data.width)
        assert not window.active_view.dicom_window
        rendered = window.active_view.item.pixmap().toImage()
        assert len(set(bytes(rendered.bits()))) > 100
        np.testing.assert_array_equal(window_pixels(np.array([0., .0025, .005, .0075, .01]), .01, .005, dicom=False),
                                      [0, 63, 127, 191, 255])
        window.change_window(.0025, .005)
        assert np.isclose(window.active_view.width, .0025)
        window.preset.setCurrentText("Auto contrast")
        assert 0 < window.active_view.width < .01
        text = roi_statistics(np.full((3, 3), .00025), QPointF(0, 0), QPointF(2, 2), False, (1, 1), ".6g")
        assert "mean 0.00025" in text
        window.mode_combo.setCurrentText("MPR")
        wait_idle(window, app)
        assert not window.views["Coronal"].dicom_window
    finally:
        window.close()
        app.processEvents()
