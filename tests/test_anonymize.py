"""De-identified DICOM export."""
import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid

from lumen.anonymize import export_deidentified
from lumen.model import scan_paths
from test_imaging import write_image


def identified_series(folder, modality="CT"):
    folder.mkdir()
    series_uid, frame_uid = generate_uid(), generate_uid()
    for i in range(2):
        path = folder / f"{i}.dcm"
        write_image(path, np.full((6, 8), i * 7), position=(0, 0, i * 3), series_uid=series_uid, instance=i + 1,
                    PatientID="MRN-0042", PatientBirthDate="19700101", InstitutionName="General Hospital",
                    ReferringPhysicianName="Doe^Jane", AccessionNumber="ACC-9", StudyDate="20240102",
                    FrameOfReferenceUID=frame_uid, ImageComments="call Jane at 555-0100", Modality=modality)
        ds = pydicom.dcmread(path)
        ds.add_new(0x00091010, "LO", "vendor secret")
        item = Dataset()
        item.PerformingPhysicianName = "Roe^Richard"
        item.ProcedureCodeSequence = []
        ds.PerformedProtocolCodeSequence = [item]
        ds.save_as(path)
    return folder


def test_identifiers_are_removed_and_relationships_kept(tmp_path):
    source = identified_series(tmp_path / "source")
    originals = [pydicom.dcmread(p) for p in sorted(source.iterdir())]
    files, burned = export_deidentified(sorted(source.iterdir()), tmp_path / "out", "SUBJ-01")
    assert burned == 0 and [f.name for f in files] == ["image_000001.dcm", "image_000002.dcm"]
    copies = [pydicom.dcmread(f) for f in files]
    text = b"".join(f.read_bytes() for f in files)
    for secret in (b"MRN-0042", b"19700101", b"General Hospital", b"Doe^Jane", b"ACC-9", b"Roe^Richard",
                   b"vendor secret", b"555-0100", b"Test^Phantom", b"20240102"):
        assert secret not in text, secret
    for copy, original in zip(copies, originals):
        assert str(copy.PatientName) == "SUBJ-01" and copy.PatientID == "SUBJ-01"
        assert copy.PatientIdentityRemoved == "YES" and copy.PatientBirthDate == ""
        assert copy.SOPClassUID == original.SOPClassUID
        assert copy.SOPInstanceUID != original.SOPInstanceUID
        assert copy.file_meta.MediaStorageSOPInstanceUID == copy.SOPInstanceUID
        np.testing.assert_array_equal(copy.pixel_array, original.pixel_array)
    assert copies[0].SeriesInstanceUID == copies[1].SeriesInstanceUID != originals[0].SeriesInstanceUID
    assert copies[0].FrameOfReferenceUID == copies[1].FrameOfReferenceUID != originals[0].FrameOfReferenceUID
    rescanned = scan_paths([tmp_path / "out"])
    assert len(rescanned.series) == 1 and rescanned.series[0].frames == 2
    for original in sorted(source.iterdir()):  # the source files are untouched
        assert pydicom.dcmread(original).PatientID == "MRN-0042"


def test_options_keep_dates_or_drop_demographics(tmp_path):
    source = identified_series(tmp_path / "source")
    files, _ = export_deidentified(sorted(source.iterdir()), tmp_path / "dated", keep_dates=True,
                                   keep_demographics=False)
    copy = pydicom.dcmread(files[0])
    assert copy.StudyDate == "20240102" and copy.PatientBirthDate == ""


def test_existing_folder_is_refused_and_burned_in_risk_reported(tmp_path):
    source = identified_series(tmp_path / "source", modality="US")
    (tmp_path / "taken").mkdir()
    with pytest.raises(FileExistsError):
        export_deidentified(sorted(source.iterdir()), tmp_path / "taken")
    _, burned = export_deidentified(sorted(source.iterdir()), tmp_path / "out")
    assert burned == 2
    assert not list(tmp_path.glob(".lumen-deidentify-*"))
