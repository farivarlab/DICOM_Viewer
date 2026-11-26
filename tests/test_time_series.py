"""4D NIfTI time axis: stepping between volumes, cine and voxel time courses."""
import nibabel as nib
import numpy as np

from lumen import nifti
from lumen.nifti import load_nifti, scan_nifti
from test_app_audit import wait_for_idle
from test_workflow import app, window


def write_4d(path):
    base = np.arange(7 * 9 * 5, dtype=np.float32).reshape(7, 9, 5)
    values = np.stack([base + 1000 * t for t in range(4)], axis=-1)
    nib.save(nib.Nifti1Image(values, np.diag([2., 2., 3., 1.])), str(path))
    return values


def open_4d(window, app, path):
    series = scan_nifti(path)
    window.series.extend(series)
    window.populate_series()
    window.set_data(load_nifti(series[0]))
    app.processEvents()
    return series


def test_time_series_cache_and_voxel_course(tmp_path, monkeypatch):
    path = tmp_path / "bold.nii.gz"
    values = write_4d(path)
    nifti._TIME_SERIES.clear()
    assert nifti.time_course(path, (1, 2, 3)) is None
    cached = nifti.cache_time_series(path)
    np.testing.assert_array_equal(cached, values)
    np.testing.assert_array_equal(nifti.time_course(path, (1, 2, 3)), values[1, 2, 3])
    assert nifti.time_course(path, (99, 0, 0)) is None
    # Loading a volume uses the cached copy and matches a direct read.
    direct = load_nifti(scan_nifti(path)[2])
    np.testing.assert_array_equal(direct.source, values[..., 2].transpose(2, 1, 0))
    nifti._TIME_SERIES.clear()
    monkeypatch.setattr(nifti, "MAX_VOXELS", 10)
    assert nifti.cache_time_series(path) is None


def test_volume_stepping_keeps_the_view(window, app, tmp_path):
    path = tmp_path / "bold.nii.gz"
    values = write_4d(path)
    nifti._TIME_SERIES.clear()
    open_4d(window, app, path)
    assert window.volume_spin.isVisible() and window.volume_spin.maximum() == 4
    assert window.time_controls.isVisible() and window.time_load.isVisible()
    window.slider_changed(3)
    window.views["Source"].zoom_by(2)
    zoom = window.views["Source"].transform().m11()
    window.volume_spin.setValue(3)  # not cached yet: loads in the background
    wait_for_idle(window, app)
    assert window.data.series.volume_index == 2
    assert window.source_index == 3 and window.views["Source"].transform().m11() == zoom
    np.testing.assert_array_equal(window.views["Source"].image, values[..., 2].transpose(2, 1, 0)[3])
    window.load_time_series()
    wait_for_idle(window, app)
    assert not window.time_load.isVisible()
    window.volume_spin.setValue(4)  # cached: immediate
    assert window.data.series.volume_index == 3 and not window.busy
    window._hovered("Source", 2, 4)
    np.testing.assert_array_equal(window.time_plot.values, values[2, 4, 3])
    assert window.time_plot.current == 3


def test_cine_through_volumes_wraps_around(window, app, tmp_path):
    path = tmp_path / "bold.nii.gz"
    write_4d(path)
    nifti._TIME_SERIES.clear()
    nifti.cache_time_series(path)
    open_4d(window, app, path)
    window.time_cine.setChecked(True)
    for expected in (1, 2, 3, 0):
        window.cine_step()
        assert window.data.series.volume_index == expected
