"""Synthetic regressions for stable series contrast when DICOM VOI is absent."""
import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

import lumen.model as model
from lumen.model import ImageVolume, Series, scan_paths, load_series
from test_imaging import write_image


def no_window_image(path, pixels, uid, instance, **kwargs):
    ds = write_image(path, pixels, position=(0, 0, instance), series_uid=uid,
                     instance=instance, intercept=0, **kwargs)
    del ds.WindowWidth
    del ds.WindowCenter
    ds.save_as(path, enforce_file_format=True)
    return ds


def test_blank_end_slices_share_one_nontrivial_series_window(tmp_path):
    uid = generate_uid()
    gradient = np.arange(64 * 64, dtype=np.int16).reshape(64, 64)
    for index, pixels in enumerate((np.zeros_like(gradient), gradient,
                                    gradient // 2, np.zeros_like(gradient))):
        no_window_image(tmp_path / f"{index}.dcm", pixels, uid, index)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    windows = [data.frame_window(i) for i in range(4)]
    assert all(window == windows[0] for window in windows)
    assert windows[0][0] > 1000
    assert (data.width, data.level) == windows[0]


def test_explicit_and_partial_frame_windows_preserve_supplied_components(tmp_path):
    uid = generate_uid()
    gradient = np.arange(32 * 32).reshape(32, 32)
    no_window_image(tmp_path / "0.dcm", gradient, uid, 0)
    partial = no_window_image(tmp_path / "1.dcm", gradient // 2, uid, 1)
    partial.WindowCenter = 123
    partial.save_as(tmp_path / "1.dcm", enforce_file_format=True)
    write_image(tmp_path / "2.dcm", gradient, position=(0, 0, 2), series_uid=uid,
                instance=2, intercept=0, WindowWidth=80, WindowCenter=40)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    fallback = data.series_window()
    assert data.frame_window(0) == fallback
    assert data.frame_window(1) == (fallback[0], 123)
    assert data.frame_window(2) == (80, 40)


def test_enhanced_per_frame_voi_overrides_stable_fallback(tmp_path):
    uid = generate_uid()
    raw = np.arange(4 * 16 * 16).reshape(4, 16, 16)
    groups = [Dataset() for _ in range(4)]
    voi = Dataset()
    voi.WindowWidth, voi.WindowCenter = 60, 30
    groups[2].FrameVOILUTSequence = [voi]
    no_window_image(tmp_path / "frames.dcm", raw, uid, 0,
                    PerFrameFunctionalGroupsSequence=groups)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    assert data.frame_window(0) == data.frame_window(1) == data.frame_window(3)
    assert data.frame_window(2) == (60, 30)


def test_series_auto_window_is_calculated_only_once(monkeypatch):
    source = np.arange(4 * 8 * 8, dtype=np.float32).reshape(4, 8, 8)
    data = ImageVolume(source, Dataset(), Series("synthetic", "", "", "", "MR", ""),
                       (1, 1, 1), np.eye(4), 1, 0, False, True)
    calls = []
    original = model._auto_window

    def measured(pixels):
        calls.append(pixels.shape)
        return original(pixels)

    monkeypatch.setattr(model, "_auto_window", measured)
    windows = [data.frame_window(i) for i in range(4)]
    assert len(set(windows)) == 1
    assert calls == [(4, 8, 8)]
    assert data.series_window() == windows[0]
    assert len(calls) == 1


@pytest.mark.parametrize("noncontiguous", [False, True])
def test_auto_window_sampling_is_bounded(monkeypatch, noncontiguous):
    source = np.arange(3_000_000, dtype=np.float32).reshape(100, 200, 150)
    if noncontiguous:
        source = source.transpose(1, 0, 2)
    counts = []
    original = np.percentile

    def measured(values, *args, **kwargs):
        counts.append(values.size)
        return original(values, *args, **kwargs)

    monkeypatch.setattr(np, "percentile", measured)
    width, level = model._auto_window(source)
    assert width > 1 and level > 0
    assert counts and max(counts) <= model.MAX_WINDOW_SAMPLES


def test_rare_foreground_does_not_collapse_to_threshold_window():
    source = np.zeros((100, 32, 32), dtype=np.float32)
    source[50, 8:16, 8:16] = 500
    assert model._auto_window(source) == (500, 250)
