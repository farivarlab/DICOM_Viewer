"""De-identified copies of a DICOM series.

A conservative subset in the spirit of the DICOM PS3.15 Basic Application Level
Confidentiality Profile, not a certified implementation:

- identifying attributes and every person name are emptied (kept present, so required
  attributes stay valid); the patient name and ID become a pseudonym;
- private tags, overlay planes and free-text comments are removed;
- dates and times are emptied unless kept;
- every non-standard UID is replaced, consistently across the exported files, so
  study/series/frame-of-reference relationships survive;
- pixel data is copied unchanged, so text burned into the image remains. Files that
  declare or commonly carry burned-in text are reported.

Source files are only read. The copy is written to a new folder that appears only when
every file has been written.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

import pydicom
from pydicom.uid import UID, generate_uid

METHOD = "Lumen basic profile: IDs, names, private tags, UIDs replaced"  # LO: at most 64 characters
IDENTIFYING = frozenset({
    "AccessionNumber", "AdditionalPatientHistory", "AdmissionID", "BranchOfService", "ContentCreatorName",
    "CountryOfResidence", "CurrentPatientLocation", "DeviceSerialNumber", "EthnicGroup", "InstitutionAddress",
    "InstitutionCodeSequence", "InstitutionName", "InstitutionalDepartmentName", "IssuerOfPatientID",
    "MedicalRecordLocator", "MilitaryRank", "Occupation", "OtherPatientIDs", "OtherPatientIDsSequence",
    "OtherPatientNames", "PatientAddress", "PatientBirthDate", "PatientBirthName", "PatientBirthTime",
    "PatientInsurancePlanCodeSequence", "PatientMotherBirthName", "PatientReligiousPreference",
    "PatientTelephoneNumbers", "PerformedProcedureStepID", "PerformedStationName", "PhysiciansOfRecord",
    "ReferringPhysicianAddress", "ReferringPhysicianTelephoneNumbers", "RegionOfResidence",
    "RequestAttributesSequence", "RequestedProcedureID", "ResponsibleOrganization", "ResponsiblePerson",
    "ScheduledProcedureStepID", "StationName", "StudyID",
})
DEMOGRAPHICS = frozenset({"PatientAge", "PatientSex", "PatientSize", "PatientWeight"})
TEXT_VRS = frozenset({"LO", "LT", "SH", "ST", "UT"})
BURNED_IN_MODALITIES = frozenset({"US", "SC", "XC", "OT", "ES", "GM", "SM", "DOC"})


def _registered(value) -> bool:
    """Standard UIDs (SOP classes, transfer syntaxes, coding schemes) name nothing about a patient."""
    uid = UID(str(value))
    return uid.name != str(uid)


class Deidentifier:
    def __init__(self, pseudonym="ANONYMOUS", keep_dates=False, keep_demographics=True):
        self.pseudonym = pseudonym.strip() or "ANONYMOUS"
        self.keep_dates, self.keep_demographics = keep_dates, keep_demographics
        self.uids: dict[str, str] = {}

    def uid(self, value) -> str:
        value = str(value)
        if value not in self.uids:
            self.uids[value] = generate_uid()
        return self.uids[value]

    def _clean(self, dataset):
        for element in list(dataset):
            tag, keyword, vr = element.tag, element.keyword, element.VR
            if tag.is_private or 0x6000 <= tag.group <= 0x60FF or 0x5000 <= tag.group <= 0x50FF:
                del dataset[tag]  # private data, overlay planes and curves can carry identifying text
            elif keyword in IDENTIFYING or vr == "PN" or (keyword in DEMOGRAPHICS and not self.keep_demographics):
                element.value = [] if vr == "SQ" else ""
            elif vr in TEXT_VRS and "Comment" in keyword:
                del dataset[tag]
            elif vr in ("DA", "DT", "TM") and not self.keep_dates:
                element.value = ""
            elif vr == "UI" and element.value:
                values = element.value if element.VM > 1 else [element.value]
                mapped = [v if _registered(v) else self.uid(v) for v in values]
                element.value = mapped if element.VM > 1 else mapped[0]
            elif vr == "SQ":
                for item in element.value:
                    self._clean(item)

    def apply(self, dataset):
        self._clean(dataset)
        dataset.PatientName = self.pseudonym
        dataset.PatientID = self.pseudonym
        dataset.PatientIdentityRemoved = "YES"
        dataset.DeidentificationMethod = METHOD
        meta = getattr(dataset, "file_meta", None)
        if meta is not None and "SOPInstanceUID" in dataset:
            meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        return dataset


def burned_in_risk(dataset) -> bool:
    return (str(getattr(dataset, "BurnedInAnnotation", "")).upper() == "YES"
            or str(getattr(dataset, "Modality", "")).upper() in BURNED_IN_MODALITIES)


def export_deidentified(paths, destination, pseudonym="ANONYMOUS", keep_dates=False, keep_demographics=True,
                        progress=lambda _: None):
    """Write de-identified copies of *paths* into the new folder *destination*.

    Returns (written files, number of files that may contain burned-in text).
    """
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Choose a new folder; {destination.name} already exists.")
    if not destination.parent.is_dir():
        raise ValueError("Choose a folder inside an existing directory.")
    paths = list(dict.fromkeys(Path(p) for p in paths))
    if not paths:
        raise ValueError("The series has no DICOM files to export.")
    deidentifier = Deidentifier(pseudonym, keep_dates, keep_demographics)
    staging = Path(tempfile.mkdtemp(prefix=".lumen-deidentify-", dir=destination.parent))
    burned = 0
    try:
        written = []
        for index, path in enumerate(paths):
            progress(f"De-identifying · {index + 1} / {len(paths)}")
            dataset = pydicom.dcmread(path, force=True)
            burned += burned_in_risk(dataset)
            deidentifier.apply(dataset)
            target = staging / f"image_{index + 1:06d}.dcm"
            meta = getattr(dataset, "file_meta", None)
            dataset.save_as(target, enforce_file_format=bool(meta is not None and "TransferSyntaxUID" in meta))
            written.append(destination / target.name)
        os.replace(staging, destination)
        return written, burned
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
