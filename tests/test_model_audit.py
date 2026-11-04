"""Regression cases found while auditing patient geometry and memory ownership."""
import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

from lumen.model import scan_paths, load_series, functional
from test_imaging import write_image


def stack(tmp_path, **kwargs):
    uid = generate_uid()
    for index in range(3):
        write_image(tmp_path / f"{index}.dcm", np.full((8, 12), index * 100),
                    position=(0, 0, index * 4), series_uid=uid, **kwargs)
    return scan_paths([tmp_path]).series[0]


def test_lazy_reconstruction_preserves_native_volume(tmp_path):
    data = load_series(stack(tmp_path), reconstruct=False)
    assert data.mpr_available
    assert not data.mpr_ready
    assert data.prepare_mpr() is data
    assert data.mpr_ready
    np.testing.assert_array_equal(data.canonical, data.source)
    assert np.shares_memory(data.canonical, data.source)
    existing = data.canonical
    data.prepare_mpr()
    assert data.canonical is existing


def test_no_pixel_stream_or_decode_cache_is_retained(tmp_path):
    data = load_series(stack(tmp_path), reconstruct=False)
    assert "PixelData" not in data.dataset
    assert getattr(data.dataset, "_pixel_array", None) is None
    assert all("PixelData" not in header for header in data.headers.values())


def test_mixed_spacing_stays_available_in_native_frame_measurements(tmp_path):
    uid = generate_uid()
    for index, spacing in enumerate(((1, 2), (3, 4), None)):
        write_image(tmp_path / f"{index}.dcm", np.zeros((8, 12)),
                    position=(0, 0, index * 4), spacing=spacing,
                    instance=index, series_uid=uid)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    assert not data.mpr_available
    assert data.frame_spacing(0) == (2., 1.)
    assert data.frame_spacing(1) == (4., 3.)
    assert data.frame_spacing(2) == (1., 1.)
    assert data.frame_calibrated(0)
    assert not data.frame_calibrated(2)
    assert data.plane("Source", [0, 0, 0], 1)[1] == (4., 3.)


@pytest.mark.parametrize("attribute,value", [
    ("ImageOrientationPatient", [1, 0, 0]),
    ("ImageOrientationPatient", [2, 0, 0, 0, .5, 0]),
    ("ImageOrientationPatient", [1, 0, 0, 0, float("nan"), 0]),
    ("ImagePositionPatient", [0, float("inf"), 0]),
    ("PixelSpacing", [1]),
    ("PixelSpacing", [1, float("inf")]),
    ("PixelSpacing", [1, -1]),
])
def test_malformed_geometry_disables_mpr_without_losing_2d(tmp_path, attribute, value):
    uid = generate_uid()
    for index in range(2):
        options = dict(position=(0, 0, index * 4), series_uid=uid)
        options[attribute] = value
        write_image(tmp_path / f"{index}.dcm", np.zeros((8, 12)), **options)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert len(data.source) == 2
    assert not data.mpr_available
    assert not data.mpr_ready
    with pytest.raises(ValueError, match="MPR"):
        data.prepare_mpr()


def test_current_frame_default_window_and_units(tmp_path):
    uid = generate_uid()
    write_image(tmp_path / "a.dcm", np.zeros((8, 12)), instance=0, series_uid=uid,
                RescaleType="HU", WindowWidth=400, WindowCenter=40)
    write_image(tmp_path / "b.dcm", np.zeros((8, 12)), instance=1, series_uid=uid,
                RescaleType="OD", WindowWidth=220, WindowCenter=80,
                PhotometricInterpretation="MONOCHROME1")
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    assert data.frame_units(0) == "HU"
    assert data.frame_units(1) == "OD"
    assert data.frame_window(0) == (400., 40.)
    assert data.frame_window(1) == (220., 80.)
    assert not data.frame_inverted(0)
    assert data.frame_inverted(1)


def test_enhanced_per_frame_measurements_and_window(tmp_path):
    groups = []
    for index in range(2):
        group = Dataset()
        measures = Dataset()
        measures.PixelSpacing = [index + 1, index + 2]
        group.PixelMeasuresSequence = [measures]
        voi = Dataset()
        voi.WindowWidth, voi.WindowCenter = (index + 1) * 100, index * 10
        group.FrameVOILUTSequence = [voi]
        rescale = Dataset()
        rescale.RescaleSlope = 1
        rescale.RescaleIntercept = 0
        rescale.RescaleType = "HU" if index == 0 else "OD"
        group.PixelValueTransformationSequence = [rescale]
        groups.append(group)
    write_image(tmp_path / "enhanced.dcm", np.zeros((2, 8, 12)),
                PerFrameFunctionalGroupsSequence=groups)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    assert data.frame_spacing(0) == (2., 1.)
    assert data.frame_spacing(1) == (3., 2.)
    assert data.frame_window(1) == (200., 10.)
    assert data.frame_units(1) == "OD"


def test_duplicate_sop_path_alias_points_to_displayed_image(tmp_path):
    uid = generate_uid()
    ds = write_image(tmp_path / "a.dcm", np.zeros((8, 12)), series_uid=uid)
    ds.save_as(tmp_path / "copy.dcm", enforce_file_format=True)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    assert len(data.source) == 1
    assert data.path_aliases[tmp_path / "copy.dcm"] == tmp_path / "a.dcm"


def test_sorted_first_image_supplies_default_window(tmp_path):
    uid = generate_uid()
    write_image(tmp_path / "a.dcm", np.zeros((8, 12)), (0, 0, 4), series_uid=uid,
                WindowWidth=800, WindowCenter=120)
    write_image(tmp_path / "b.dcm", np.zeros((8, 12)), (0, 0, 0), series_uid=uid,
                WindowWidth=200, WindowCenter=30)
    data = load_series(scan_paths([tmp_path]).series[0], reconstruct=False)
    assert (data.width, data.level) == (200, 30)
    assert data.reference(0).path.name == "b.dcm"


def test_missing_per_frame_group_does_not_reuse_previous_transform():
    ds = Dataset()
    ds.RescaleSlope = 1
    group = Dataset()
    rescale = Dataset()
    rescale.RescaleSlope = 10
    group.PixelValueTransformationSequence = [rescale]
    ds.PerFrameFunctionalGroupsSequence = [group]
    assert functional(ds, 0, "PixelValueTransformationSequence", "RescaleSlope") == 10
    assert functional(ds, 1, "PixelValueTransformationSequence", "RescaleSlope") == 1


def test_mixed_physical_units_cannot_form_one_volume(tmp_path):
    uid = generate_uid()
    for index, unit in enumerate(("HU", "OD")):
        write_image(tmp_path / f"{index}.dcm", np.zeros((8, 12)),
                    (0, 0, index * 4), series_uid=uid, RescaleType=unit)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert not data.mpr_available
    assert "Mixed physical value units" in data.geometry_note
