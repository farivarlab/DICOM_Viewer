from pathlib import Path
import zipfile
import numpy as np
import nibabel as nib
import pytest
from pydicom.uid import generate_uid

from lumen.importer import import_paths
from lumen.model import load_series, scan_paths
from lumen.nifti import scan_nifti, load_nifti, export_nifti, scan_inputs
from test_imaging import write_image


def write_nifti(path, values=None, affine=None, units="mm"):
    values = np.arange(7 * 9 * 5, dtype=np.float32).reshape(7, 9, 5) if values is None else values
    affine = np.diag([-2., -3., 4., 1.]) if affine is None else np.asarray(affine, float)
    image = nib.Nifti1Image(values, affine)
    image.header.set_xyzt_units(units, "sec")
    nib.save(image, path)
    return values, affine


def test_nifti_3d_voxels_lps_geometry_and_mpr(tmp_path):
    path = tmp_path / "volume.nii.gz"
    values, affine = write_nifti(path)
    data = load_nifti(scan_nifti(path)[0])
    np.testing.assert_array_equal(data.source, values.transpose(2, 1, 0))
    np.testing.assert_allclose(data.affine, np.diag([-1., -1., 1., 1.]) @ affine)
    assert data.frame_spacing(0) == (2, 3)
    assert data.frame_calibrated(0)
    assert data.mpr_available and not data.mpr_ready
    data.prepare_mpr()
    np.testing.assert_array_equal(data.canonical, data.source)
    assert data.canonical_spacing == (2, 3, 4)
    assert data.series.source_format == "NIfTI"


def test_nifti_4d_volumes_load_independently(tmp_path):
    path = tmp_path / "time.nii"
    values = np.arange(7 * 9 * 5 * 3, dtype=np.float32).reshape(7, 9, 5, 3)
    write_nifti(path, values)
    series = scan_nifti(path)
    assert len(series) == 3
    assert len({s.uid for s in series}) == 3
    assert len({s.study_uid for s in series}) == 1
    data = load_nifti(series[2])
    np.testing.assert_array_equal(data.source, values[:, :, :, 2].transpose(2, 1, 0))
    assert data.format_metadata["selected_volume"] == 3


def test_nifti_2d_does_not_invent_volume(tmp_path):
    path = tmp_path / "plane.nii"
    write_nifti(path, np.ones((8, 12), np.float32))
    data = load_nifti(scan_nifti(path)[0])
    assert data.source.shape == (1, 12, 8)
    assert not data.mpr_available


def test_nifti_units_are_converted_without_claiming_unknown_mm(tmp_path):
    path = tmp_path / "meters.nii"
    write_nifti(path, affine=np.diag([.002, .003, .004, 1]), units="meter")
    data = load_nifti(scan_nifti(path)[0])
    np.testing.assert_allclose(data.spacing, [2, 3, 4], rtol=1e-6)
    assert data.calibrated
    unknown = tmp_path / "unknown.nii"
    write_nifti(unknown, units="unknown")
    data = load_nifti(scan_nifti(unknown)[0])
    assert not data.frame_calibrated(0)
    assert data.geometry_unit == "units"


def test_complex_nifti_displays_magnitude_but_export_keeps_complex(tmp_path):
    source, target = tmp_path / "complex.nii", tmp_path / "copy.nii.gz"
    values = np.arange(7 * 9 * 5, dtype=np.float32).reshape(7, 9, 5).astype(np.complex64) * (1 + 2j)
    _, affine = write_nifti(source, values)
    data = load_nifti(scan_nifti(source)[0])
    np.testing.assert_allclose(data.source, np.abs(values).transpose(2, 1, 0))
    assert data.frame_units(0) == "magnitude"
    export_nifti(data, target)
    image = nib.load(target)
    np.testing.assert_array_equal(np.asanyarray(image.dataobj), values)
    np.testing.assert_array_equal(image.affine, affine)


def test_nifti_export_selected_4d_volume_preserves_values_and_affine(tmp_path):
    source, target = tmp_path / "input.nii", tmp_path / "selected.nii.gz"
    values = np.arange(7 * 9 * 5 * 2, dtype=np.int16).reshape(7, 9, 5, 2)
    _, affine = write_nifti(source, values)
    data = load_nifti(scan_nifti(source)[1])
    export_nifti(data, target)
    exported = nib.load(target)
    assert exported.shape == (7, 9, 5)
    np.testing.assert_array_equal(np.asanyarray(exported.dataobj), values[:, :, :, 1])
    np.testing.assert_array_equal(exported.affine, affine)


def test_import_zip_keeps_nii_gz_extension(tmp_path):
    source = tmp_path / "input.nii.gz"
    values, _ = write_nifti(source)
    archive = tmp_path / "images.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.write(source, "subdir/input.nii.gz")
    scan, folders = import_paths([archive])
    try:
        assert len(scan.series) == 1
        assert scan.series[0].source_format == "NIfTI"
        data = load_nifti(scan.series[0])
        np.testing.assert_array_equal(data.source, values.transpose(2, 1, 0))
    finally:
        for folder in folders:
            folder.cleanup()


def test_unsupported_dimensions_are_explicit(tmp_path):
    path = tmp_path / "vector.nii.gz"
    write_nifti(path, np.zeros((7, 9, 5, 2, 3), np.float32))
    with pytest.raises(ValueError, match="2D, 3D, and 4D scalar"):
        scan_nifti(path)


def test_existing_export_is_not_overwritten_by_default(tmp_path):
    source, target = tmp_path / "input.nii", tmp_path / "existing.nii.gz"
    write_nifti(source)
    target.write_bytes(b"keep existing file")
    with pytest.raises(FileExistsError):
        export_nifti(load_nifti(scan_nifti(source)[0]), target)
    assert target.read_bytes() == b"keep existing file"


def test_dcm2niix_conversion_preserves_calibrated_voxel_landmarks(tmp_path):
    folder = tmp_path / "dicom"
    folder.mkdir()
    uid, study_uid = generate_uid(), generate_uid()
    for z in range(4):
        values = np.arange(12 * 16).reshape(12, 16) + z * 500
        write_image(folder / f"{z}.dcm", values, (10, 20, z * 4), series_uid=uid,
                    spacing=(2, 3), instance=z + 1, slope=2, intercept=-1000,
                    StudyInstanceUID=study_uid, StudyDate="20260101", StudyTime="120000",
                    StudyID="1", SeriesNumber=1, PatientID="SYNTHETIC", SliceThickness=4)
    original = load_series(scan_paths([folder]).series[0])
    output = tmp_path / "converted.nii.gz"
    files = export_nifti(original, output)
    assert output in files
    assert output.with_name("converted.json") in files
    converted = load_nifti(scan_nifti(output)[0])
    converted.prepare_mpr()
    np.testing.assert_array_equal(converted.canonical, original.canonical)
    np.testing.assert_allclose(converted.canonical_origin, original.canonical_origin, atol=1e-5)
    np.testing.assert_allclose(converted.canonical_spacing, original.canonical_spacing)


def test_nifti_publication_rolls_back_if_commit_fails(tmp_path, monkeypatch):
    from lumen import nifti
    source, target = tmp_path / "input.nii", tmp_path / "existing.nii.gz"
    write_nifti(source)
    target.write_bytes(b"original")
    replace = nifti.os.replace

    def fail_on_write(src, dst):
        if Path(src).name.startswith(".lumen-export-"):
            raise OSError("Simulated write failure")
        return replace(src, dst)
    monkeypatch.setattr(nifti.os, "replace", fail_on_write)
    with pytest.raises(OSError, match="Simulated"):
        export_nifti(load_nifti(scan_nifti(source)[0]), target, overwrite=True)
    assert target.read_bytes() == b"original"


def test_failed_rollback_retains_original_backup(tmp_path, monkeypatch):
    from lumen import nifti
    source, target = tmp_path / "input.nii", tmp_path / "existing.nii.gz"
    write_nifti(source)
    target.write_bytes(b"original")
    replace = nifti.os.replace

    def fail_after_backup(src, dst):
        if Path(src).name.startswith((".lumen-export-", ".lumen-backup-")):
            raise OSError("Simulated locked destination")
        return replace(src, dst)
    monkeypatch.setattr(nifti.os, "replace", fail_after_backup)
    with pytest.raises(OSError, match="Original file retained"):
        export_nifti(load_nifti(scan_nifti(source)[0]), target, overwrite=True)
    backups = list(tmp_path.glob(".lumen-backup-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"original"


def test_new_export_does_not_replace_an_unrelated_sidecar(tmp_path):
    from lumen.nifti import _publish
    output = tmp_path / "staged"
    output.mkdir()
    for name in ("volume.nii.gz", "volume.json"):
        (output / name).write_bytes(b"new")
    sidecar = tmp_path / "volume.json"
    sidecar.write_bytes(b"unrelated existing JSON")
    with pytest.raises(FileExistsError):
        _publish(sorted(output.iterdir()), tmp_path / "volume.nii.gz", overwrite=True)
    assert sidecar.read_bytes() == b"unrelated existing JSON"
    assert not (tmp_path / "volume.nii.gz").exists()
