"""Marks saved between sessions and measurement export."""
import csv
import shutil

import numpy as np
from PySide6.QtCore import QPointF

from lumen import annotation_store
from lumen.app import MainWindow
from lumen.model import load_series, scan_paths
from lumen.slice_view import Mark
from test_workflow import app, window, study, install


def marks_for(data):
    source = Mark("Length", [QPointF(10, 10), QPointF(13, 14)], ("Source", data.reference(1).path, 0))
    note = Mark("Text", [QPointF(5, 6)], ("Source", data.reference(2).path, 0), "lesion")
    plane = Mark("Rectangle", [QPointF(2, 2), QPointF(6, 5)], ("Axial", 1, "Slice", 10.))
    return {"Source": [source, note], "Axial": [plane]}


def describe(marks):
    return {view: [(m.tool, m.key, [(p.x(), p.y()) for p in m.points], m.label) for m in items]
            for view, items in marks.items()}


def test_marks_round_trip_into_a_freshly_loaded_series(study, tmp_path):
    series, data = study
    annotation_store.save(tmp_path / "store", data, marks_for(data))
    again = load_series(scan_paths([series.paths[0].parent]).series[0])
    assert describe(annotation_store.load(tmp_path / "store", again)) == describe(marks_for(data))


def test_marks_follow_instances_to_new_paths_but_planes_need_the_same_frames(study, tmp_path):
    series, data = study
    annotation_store.save(tmp_path / "store", data, marks_for(data))
    moved = tmp_path / "moved"
    moved.mkdir()
    for path in series.paths:
        shutil.copy(path, moved / ("renamed_" + path.name))
    again = load_series(scan_paths([moved]).series[0])
    restored = annotation_store.load(tmp_path / "store", again)
    assert [m.key[1].parent for m in restored["Source"]] == [moved, moved]
    assert "Axial" in restored
    (moved / ("renamed_" + series.paths[0].name)).unlink()  # one frame fewer: plane indices change
    fewer = load_series(scan_paths([moved]).series[0])
    restored = annotation_store.load(tmp_path / "store", fewer)
    assert "Axial" not in restored


def test_unreadable_store_and_empty_save(study, tmp_path):
    _, data = study
    path = annotation_store.store_path(tmp_path, data)
    path.write_text("{not json", encoding="utf-8")
    assert annotation_store.load(tmp_path, data) == {}
    annotation_store.save(tmp_path, data, {})
    assert not path.exists()


def test_saved_file_holds_no_patient_demographics(study, tmp_path):
    _, data = study
    annotation_store.save(tmp_path, data, marks_for(data))
    text = annotation_store.store_path(tmp_path, data).read_text(encoding="utf-8")
    assert "SYNTHETIC-123" not in text and "Phantom" not in text and "19800101" not in text


def test_viewer_restores_marks_in_a_new_session_and_exports_measurements(window, study, app, tmp_path, monkeypatch):
    data = install(window, study, app)
    view = window.views["Source"]
    view.marks.append(Mark("Length", [QPointF(10, 10), QPointF(13, 14)], view.key))
    view.marks.append(Mark("Rectangle", [QPointF(0, 0), QPointF(4, 2)], view.key))
    view.marks_changed.emit()
    assert window._mark_save_timer.isActive()
    output = tmp_path / "measurements.csv"
    monkeypatch.setattr("lumen.app.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(output), "CSV (*.csv)"))
    window.export_measurements()
    with output.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["tool"] for row in rows] == ["Length", "Rectangle"]
    assert float(rows[0]["length"]) == 5 and rows[0]["spatial_unit"] == "mm"
    assert float(rows[1]["area"]) == 8 and float(rows[1]["mean"]) == data.source[0][:2, :4].mean()
    window.close()  # saves pending marks
    app.processEvents()

    second = MainWindow(settings_path=tmp_path / "settings.ini")
    second.show()
    try:
        series = scan_paths([study[0].paths[0].parent]).series[0]
        install(second, (series, load_series(series)), app)
        restored = second.views["Source"].marks
        assert [m.tool for m in restored] == ["Length", "Rectangle"]
        second.clear_marks()
        assert not annotation_store.store_path(second.annotation_directory, second.data).exists()
    finally:
        second.close()
        app.processEvents()
