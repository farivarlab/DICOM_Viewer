"""Measurements and annotations kept between sessions.

Marks are stored per series under the portable settings folder, never beside the
images, which stay read only. Files hold image identifiers, mark geometry and
annotation text; no patient demographics are written. Acquired images are named
by SOP Instance UID and frame, so marks survive moved files and ZIP extraction
paths. Reconstructed-plane marks are kept only for the same set of frames,
because plane indices depend on it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QPointF

from .slice_view import DRAWING_TOOLS, Mark, measure

DIRECTORY = ".lumen-annotations"
FORMAT = "lumen-annotations"
VERSION = 1
PLANES = ("Axial", "Coronal", "Sagittal")
MEASUREMENT_COLUMNS = ("series", "view", "image", "tool", "label", "length", "angle_deg", "area",
                       "mean", "sd", "min", "max", "value_unit", "spatial_unit")


def store_path(directory, data) -> Path:
    return Path(directory) / f"{hashlib.sha256(data.series.uid.encode()).hexdigest()[:32]}.json"


def _instance(data, path):
    uid = getattr(data.headers.get(path), "SOPInstanceUID", None) if path is not None else None
    return str(uid) if uid else None


def frame_signature(data) -> str:
    """Identifies the exact frame set that reconstructed planes are indexed by."""
    parts = [f"{_instance(data, ref.path) or ''}:{ref.frame}" for ref in data.references] or [str(len(data.source))]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32]


def to_records(data, marks_by_view) -> list[dict]:
    records = []
    for view, marks in marks_by_view.items():
        for mark in marks:
            record = {"view": view, "tool": mark.tool, "points": [[p.x(), p.y()] for p in mark.points]}
            if mark.label:
                record["label"] = mark.label
            if view == "Source":
                _, path, frame = mark.key
                record.update(instance=_instance(data, path), frame=frame)
            else:
                _, index, slab, slab_mm, *placement = mark.key
                record.update(index=index, slab=slab, slab_mm=slab_mm)
                if placement:  # an angled plane: its angles and the crosshair it passes through
                    angles, cursor = placement
                    record.update(angles=list(angles), cursor=list(cursor))
            records.append(record)
    return records


def from_records(data, records) -> dict[str, list[Mark]]:
    paths = {}
    for ref in data.references:
        uid = _instance(data, ref.path)
        if uid:
            paths[(uid, ref.frame)] = ref.path
    unnamed = data.references[0].path if data.references else None  # NIfTI and generated volumes
    marks: dict[str, list[Mark]] = {}
    for record in records if isinstance(records, list) else []:
        try:
            view, tool = record["view"], record["tool"]
            points = [QPointF(float(x), float(y)) for x, y in record["points"]]
            if tool not in DRAWING_TOOLS or not points:
                continue
            if view == "Source":
                frame = int(record.get("frame", 0))
                instance = record.get("instance")
                if instance:
                    path = paths.get((instance, frame))
                    if path is None:
                        continue  # that instance is not part of the opened series
                elif data.series.source_format == "DICOM" and data.references:
                    continue
                else:
                    path = unnamed
                key = ("Source", path, frame)
            elif view in PLANES:
                key = (view, int(record["index"]), str(record["slab"]), float(record["slab_mm"]))
                if "angles" in record:
                    tilt, turn = (float(a) for a in record["angles"])
                    key += ((tilt, turn), tuple(int(c) for c in record["cursor"]))
            else:
                continue
            marks.setdefault(view, []).append(Mark(tool, points, key, str(record.get("label", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    return marks


def save(directory, data, marks_by_view):
    """Write the series' marks, or remove its file when there are none."""
    path = store_path(directory, data)
    records = to_records(data, marks_by_view)
    if not records:
        path.unlink(missing_ok=True)
        return
    payload = {"format": FORMAT, "version": VERSION, "series": data.series.uid,
               "frames": frame_signature(data), "marks": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".annotations-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=1)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def load(directory, data) -> dict[str, list[Mark]]:
    """Marks saved for *data*'s series; unreadable or foreign files give none."""
    try:
        payload = json.loads(store_path(directory, data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("format") != FORMAT or payload.get("series") != data.series.uid:
        return {}
    marks = from_records(data, payload.get("marks"))
    if payload.get("frames") != frame_signature(data):
        marks = {view: items for view, items in marks.items() if view == "Source"}
    return marks


def measurement_rows(data, marks_by_view, resolve) -> list[dict]:
    """One row per mark. *resolve(view, key)* gives (image, spacing, value_unit, length_unit, image_label) or None."""
    rows = []
    for view, marks in marks_by_view.items():
        for mark in marks:
            row = dict.fromkeys(MEASUREMENT_COLUMNS, "")
            row.update(series=data.series.title, view=view, tool=mark.tool, label=mark.label)
            context = resolve(view, mark.key)
            if context is not None:
                image, spacing, value_unit, length_unit, image_label = context
                row["image"] = image_label
                values = measure(mark, image, spacing)
                for name, column in (("length", "length"), ("angle", "angle_deg"), ("area", "area"),
                                     ("mean", "mean"), ("sd", "sd"), ("min", "min"), ("max", "max")):
                    if name in values:
                        row[column] = f"{values[name]:.6g}"
                if "length" in values or "area" in values:
                    row["spatial_unit"] = length_unit  # area is in spatial_unit²
                if "mean" in values:
                    row["value_unit"] = value_unit
                if "rgb_mean" in values:
                    row["mean"] = " ".join(f"{v:.6g}" for v in values["rgb_mean"])
                    row["value_unit"] = "RGB"
            rows.append(row)
    return rows
