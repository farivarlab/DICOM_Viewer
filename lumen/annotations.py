"""Readable image-frame annotations from the selected file's DICOM header."""


def date_text(value):
    text = str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 else text


def file_annotations(ds, reconstruction=False):
    left, right = [], []
    name = str(getattr(ds, "PatientName", "")).replace("^", " ").strip()
    if name:
        left.append(name)
    patient_id = str(getattr(ds, "PatientID", ""))
    if patient_id:
        left.append(f"ID: {patient_id}")
    demographics = []
    birth = date_text(getattr(ds, "PatientBirthDate", ""))
    if birth:
        demographics.append(f"DOB {birth}")
    for tag in ("PatientAge", "PatientSex"):
        value = str(getattr(ds, tag, ""))
        if value:
            demographics.append(value)
    if demographics:
        left.append(" · ".join(demographics))
    for tag in ("StudyDescription", "SeriesDescription"):
        value = str(getattr(ds, tag, ""))
        if value:
            left.append(value)
    institution = str(getattr(ds, "InstitutionName", ""))
    if institution:
        right.append(institution)
    date = date_text(getattr(ds, "AcquisitionDate", getattr(ds, "StudyDate", "")))
    time = str(getattr(ds, "AcquisitionTime", getattr(ds, "StudyTime", ""))).split(".")[0]
    if len(time) >= 6:
        time = f"{time[:2]}:{time[2:4]}:{time[4:6]}"
    if date or time:
        right.append("  ".join(filter(None, (date, time))))
    acquisition = []
    for tag, prefix in (("Modality", ""), ("SeriesNumber", "Series "), ("InstanceNumber", "Instance ")):
        if reconstruction and tag == "InstanceNumber":
            continue
        value = str(getattr(ds, tag, ""))
        if value:
            acquisition.append(prefix + value)
    if acquisition:
        right.append(" · ".join(acquisition))
    technique = []
    for tag, prefix, unit in (("SliceThickness", "", " mm slice"), ("KVP", "", " kVp"),
                               ("RepetitionTime", "TR ", " ms"), ("EchoTime", "TE ", " ms")):
        if reconstruction and tag == "SliceThickness":
            continue
        value = str(getattr(ds, tag, ""))
        if value:
            technique.append(prefix + value + unit)
    if technique:
        right.append(" · ".join(technique))
    accession = str(getattr(ds, "AccessionNumber", ""))
    if accession:
        right.append(f"Accession: {accession}")
    return left, right
