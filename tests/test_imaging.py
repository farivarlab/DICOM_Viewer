from pathlib import Path
import zipfile

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, CTImageStorage, generate_uid, RLELossless
from pydicom.fileset import FileSet
from PySide6.QtCore import QPointF

from lumen.colors import window_pixels, lookup_table
from lumen.importer import import_paths
from lumen.model import scan_paths, load_series, demo_volume
from lumen.slice_view import angle_degrees, roi_statistics


def write_image(path, pixels, position=None, orientation=(1, 0, 0, 0, 1, 0),
                series_uid=None, instance=1, slope=1, intercept=-1024, spacing=(2, 3), **kwargs):
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = series_uid or generate_uid()
    ds.Modality = "CT"
    ds.PatientName = "Test^Phantom"
    ds.SeriesDescription = "Geometry fixture"
    ds.InstanceNumber = instance
    pixels = np.asarray(pixels, dtype=np.int16)
    if pixels.ndim == 3:
        ds.NumberOfFrames = pixels.shape[0]
    ds.Rows, ds.Columns = pixels.shape[-2:]
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1
    ds.RescaleSlope = slope
    ds.RescaleIntercept = intercept
    ds.RescaleType = "HU"
    ds.WindowWidth, ds.WindowCenter = 400, 40
    if spacing is not None:
        ds.PixelSpacing = list(spacing)
    if position is not None:
        ds.ImagePositionPatient = list(position)
    if orientation is not None:
        ds.ImageOrientationPatient = list(orientation)
    for key, value in kwargs.items():
        setattr(ds, key, value)
    ds.PixelData = pixels.tobytes()
    ds.save_as(path, enforce_file_format=True)
    return ds


def make_stack(tmp_path, positions=(0, 4, 8), orientation=(1, 0, 0, 0, 1, 0)):
    uid = generate_uid()
    for i, z in enumerate(positions):
        write_image(tmp_path / f"{len(positions) - i}.dcm", np.full((4, 5), i * 100),
                    position=(0, 0, z), orientation=orientation, series_uid=uid,
                    instance=99 - i)
    return scan_paths([tmp_path]).series[0]


def test_patient_geometry_sorting_and_modality_rescale(tmp_path):
    series = make_stack(tmp_path)
    data = load_series(series)
    assert data.mpr_ready
    assert data.source[:, 0, 0].tolist() == [-1024, -924, -824]
    assert data.spacing == (3, 2, 4)
    assert data.canonical_spacing == (3, 2, 4)
    np.testing.assert_array_equal(data.canonical, data.source)
    assert data.units == "HU"


def test_negative_orientation_reorients_in_patient_space(tmp_path):
    uid = generate_uid()
    raw = np.arange(20).reshape(4, 5)
    for z in (0, 4):
        write_image(tmp_path / f"{z}.dcm", raw + z * 100, (12, 6, z),
                    orientation=(-1, 0, 0, 0, -1, 0), series_uid=uid, intercept=0)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert data.canonical_origin == (0, 0, 0)
    np.testing.assert_array_equal(data.canonical[0], raw[::-1, ::-1])


def test_sagittal_acquisition_reorients_axes(tmp_path):
    uid = generate_uid()
    for i in range(3):
        write_image(tmp_path / f"{i}.dcm", np.full((4, 5), 100 * i), (i * 4, 0, 0),
                    orientation=(0, 1, 0, 0, 0, 1), series_uid=uid, intercept=0)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert data.canonical.shape == (4, 5, 3)
    assert data.canonical_spacing == (4, 3, 2)
    assert data.canonical[0, 0].tolist() == [0, 100, 200]


@pytest.mark.parametrize("positions", [(0, 4, 12), (0, 0, 4)])
def test_irregular_or_repeated_positions_disable_mpr(tmp_path, positions):
    data = load_series(make_stack(tmp_path, positions))
    assert not data.mpr_ready
    assert len(data.source) == 3
    assert any(word in data.geometry_note for word in ("Irregular", "Repeated"))


def test_mixed_orientations_disable_mpr(tmp_path):
    uid = generate_uid()
    write_image(tmp_path / "a.dcm", np.zeros((4, 5)), (0, 0, 0), series_uid=uid)
    write_image(tmp_path / "b.dcm", np.zeros((4, 5)), (0, 0, 4),
                orientation=(1, 0, 0, 0, 0, 1), series_uid=uid)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert not data.mpr_ready
    assert "Mixed" in data.geometry_note


def test_missing_geometry_and_spacing_uses_pixels(tmp_path):
    write_image(tmp_path / "a.dcm", np.zeros((4, 5)), spacing=None)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert not data.mpr_ready
    assert not data.calibrated
    assert data.spacing[:2] == (1, 1)


def test_enhanced_multiframe_rescale_and_positions(tmp_path):
    groups = []
    for i in range(3):
        group = Dataset()
        position = Dataset()
        position.ImagePositionPatient = [0, 0, i * 4]
        group.PlanePositionSequence = [position]
        rescale = Dataset()
        rescale.RescaleSlope, rescale.RescaleIntercept = i + 1, -100
        group.PixelValueTransformationSequence = [rescale]
        groups.append(group)
    write_image(tmp_path / "enhanced.dcm", np.full((3, 4, 5), 10), (0, 0, 0),
                PerFrameFunctionalGroupsSequence=groups)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert data.mpr_ready
    assert data.source[:, 0, 0].tolist() == [-90, -80, -70]


def test_enhanced_default_window(tmp_path):
    shared = Dataset()
    voi = Dataset()
    voi.WindowWidth, voi.WindowCenter = 1500, -600
    shared.FrameVOILUTSequence = [voi]
    write_image(tmp_path / "window.dcm", np.zeros((2, 4, 5)), SharedFunctionalGroupsSequence=[shared])
    data = load_series(scan_paths([tmp_path]).series[0])
    assert (data.width, data.level) == (1500, -600)


@pytest.mark.parametrize("tilt", [False, True])
def test_oblique_and_gantry_tilt_resample_affine(tmp_path, tilt):
    uid = generate_uid()
    c = 2 ** -.5
    orientation = (1, 0, 0, 0, 1, 0) if tilt else (c, c, 0, -c, c, 0)
    yy, xx = np.mgrid[:8, :8]
    for i in range(4):
        write_image(tmp_path / f"{i}.dcm", xx + 10 * yy + 100 * i,
                    position=(i * .4 if tilt else 0, 0, i * 2), orientation=orientation,
                    series_uid=uid, intercept=0, spacing=(1, 1))
    data = load_series(scan_paths([tmp_path]).series[0])
    assert data.mpr_ready
    target = np.array(data.canonical.shape[::-1]) // 2
    world = np.asarray(data.canonical_origin) + target * data.canonical_spacing
    native = np.linalg.inv(data.affine) @ np.r_[world, 1]
    expected = native[0] + 10 * native[1] + 100 * native[2]
    assert data.canonical[tuple(target[::-1])] == pytest.approx(expected, abs=1e-4)


def test_dicomdir_resolves_referenced_images(tmp_path):
    ds = write_image(tmp_path / "source.dcm", np.zeros((4, 5)), PatientID="SYNTHETIC",
                     StudyDate="20260101", StudyTime="120000", StudyID="1", SeriesNumber=1)
    file_set = FileSet()
    file_set.add(ds)
    file_set.write(tmp_path / "disc")
    scan = scan_paths([tmp_path / "disc" / "DICOMDIR"])
    assert len(scan.series) == 1
    assert scan.series[0].frames == 1
    assert load_series(scan.series[0]).source.shape == (1, 4, 5)


def test_color_frames_remain_rgb_and_do_not_make_mpr(tmp_path):
    ds = write_image(tmp_path / "rgb.dcm", np.zeros((4, 5)), intercept=0)
    rgb = np.zeros((4, 5, 3), np.uint8)
    rgb[:, :, 0] = 230
    rgb[:, :, 1] = 70
    ds.PhotometricInterpretation = "RGB"
    ds.SamplesPerPixel = 3
    ds.PlanarConfiguration = 0
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = rgb.tobytes()
    ds.save_as(tmp_path / "rgb.dcm", enforce_file_format=True)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert data.is_color
    assert not data.mpr_ready
    np.testing.assert_array_equal(data.source[0], rgb)


def test_multiframe_cine_does_not_invent_spatial_geometry(tmp_path):
    write_image(tmp_path / "cine.dcm", np.zeros((5, 4, 5)), (0, 0, 0))
    data = load_series(scan_paths([tmp_path]).series[0])
    assert len(data.source) == 5
    assert not data.mpr_ready


def test_rle_lossless_decodes_signed_pixels(tmp_path):
    path = tmp_path / "compressed.dcm"
    raw = np.arange(-10, 10).reshape(4, 5)
    ds = write_image(path, raw, intercept=0)
    ds.compress(RLELossless)
    ds.save_as(path, enforce_file_format=True)
    data = load_series(scan_paths([tmp_path]).series[0])
    np.testing.assert_array_equal(data.source[0], raw)


def test_duplicate_sop_instances_are_not_stacked_twice(tmp_path):
    uid = generate_uid()
    ds = write_image(tmp_path / "a.dcm", np.zeros((4, 5)), (0, 0, 0), series_uid=uid)
    ds.save_as(tmp_path / "copy.dcm", enforce_file_format=True)
    write_image(tmp_path / "b.dcm", np.ones((4, 5)), (0, 0, 4), series_uid=uid)
    data = load_series(scan_paths([tmp_path]).series[0])
    assert len(data.source) == 2
    assert data.mpr_ready


def test_stack_dimension_mismatch_is_explicit(tmp_path):
    uid = generate_uid()
    write_image(tmp_path / "a.dcm", np.zeros((4, 5)), series_uid=uid)
    write_image(tmp_path / "b.dcm", np.zeros((5, 5)), series_uid=uid)
    with pytest.raises(ValueError, match="different image dimensions"):
        load_series(scan_paths([tmp_path]).series[0])


def test_zip_cannot_write_archive_paths(tmp_path):
    source = tmp_path / "image.dcm"
    write_image(source, np.zeros((4, 5)))
    archive = tmp_path / "study.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.write(source, "../../escape.dcm")
    result, folders = import_paths([archive])
    try:
        assert len(result.series) == 1
        assert result.series[0].paths[0].parent == Path(folders[0].name)
        assert not (tmp_path.parent / "escape.dcm").exists()
    finally:
        for folder in folders:
            folder.cleanup()


def test_windows_follow_dicom_linear_boundary():
    assert window_pixels(np.array([-1, 0, 1, 2]), 2, 1).tolist() == [0, 0, 255, 255]
    assert window_pixels(np.array([39.4, 39.5, 39.6]), 1, 40).tolist() == [0, 0, 255]


def test_colormap_and_inverse():
    lut = lookup_table("Viridis")
    assert lut.shape == (256, 3)
    np.testing.assert_array_equal(lookup_table("Viridis", True), lut[::-1])


def test_mpr_planes_and_crosshairs_share_one_voxel():
    data = demo_volume()
    cursor = [41, 72, 55]
    for name, point in (("Axial", (41, 72)), ("Coronal", (41, 56)), ("Sagittal", (72, 56))):
        plane, spacing = data.plane(name, cursor)
        assert plane[point[1], point[0]] == data.canonical[55, 72, 41]
        assert data.pixel_to_cursor(name, *point, [0, 0, 0])[{"Axial": 0, "Coronal": 0, "Sagittal": 1}[name]] == point[0]
        assert data.pixel_to_cursor(name, *point, cursor) == cursor


def test_slab_projections_at_volume_edge():
    data = demo_volume()
    cursor = [0, 0, 0]
    for mode, reducer in (("MIP", np.max), ("MinIP", np.min), ("Average", np.mean)):
        image, _ = data.plane("Axial", cursor, slab_mode=mode, slab_mm=12)
        np.testing.assert_array_equal(image, reducer(data.canonical[:3], axis=0))


def test_anisotropic_angle_uses_physical_spacing():
    points = [QPointF(0, 1), QPointF(0, 0), QPointF(1, 1)]
    assert angle_degrees(points, (2, 1)) == pytest.approx(63.4349488)


def test_roi_statistics_clips_to_image_and_preserves_units():
    image = np.arange(16).reshape(4, 4)
    text = roi_statistics(image, QPointF(-5, -5), QPointF(1, 1), False, (2, 3))
    assert "Area 24.0" in text
    assert "mean 2.5" in text
    assert "max 5.0" in text
