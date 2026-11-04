import csv

import pytest
from pydicom.dataset import Dataset
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableView, QTableWidget, QFileDialog

from lumen.metadata import MetadataPane


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_large_enhanced_header_uses_virtual_rows_and_cached_proxy_filter(app):
    dataset = Dataset()
    frames = []
    for index in range(2_000):
        frame = Dataset()
        frame.InstanceNumber = index + 1
        frame.ImageComments = "target-marker" if index == 1_234 else f"Frame {index + 1}"
        frames.append(frame)
    dataset.PerFrameFunctionalGroupsSequence = frames
    pane = MetadataPane()
    pane.set_dataset(dataset, "<b>literal-filename.dcm</b>")
    assert isinstance(pane.table, QTableView)
    assert not isinstance(pane.table, QTableWidget)
    assert not hasattr(pane.table, "setItem")
    assert len(pane.rows) == 4_001
    assert pane.model.rowCount() == 4_001
    assert pane.model.rows is pane.rows
    assert len(pane.model.search_rows) == 4_001
    assert pane.caption.textFormat() == Qt.TextFormat.PlainText
    assert pane.caption.text() == "<b>literal-filename.dcm</b>"
    pane.search.setText("TARGET-MARKER")
    assert pane.proxy.rowCount() == 1
    assert pane.proxy.index(0, 3).data() == "target-marker"
    pane.search.clear()
    assert pane.proxy.rowCount() == 4_001
    pane.set_dataset(dataset, "Another caption")
    assert pane.caption.text() == "Another caption"
    assert pane.model.rows is pane.rows
    pane.close()


def test_metadata_csv_preserves_formula_guarding(app, monkeypatch, tmp_path):
    dataset = Dataset()
    dataset.InstitutionName = "=SUM(1,2)"
    pane = MetadataPane()
    pane.set_dataset(dataset, "file.dcm")
    output = tmp_path / "metadata.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(output), "CSV (*.csv)"))
    pane.export()
    with output.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["Tag", "Name", "VR", "Value"]
    assert rows[1][3] == "'=SUM(1,2)"
    pane.close()
