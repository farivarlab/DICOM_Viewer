"""Side-by-side comparison: a second series on the 2D image's grid, with linked views."""
import numpy as np
from pydicom.uid import generate_uid

from lumen.model import load_series, scan_paths
from test_imaging import write_image
from test_workflow import app, window, study, install


def second_series(tmp_path):
    folder = tmp_path / "second"
    folder.mkdir()
    uid = generate_uid()
    for i in range(3):
        write_image(folder / f"{i}.dcm", np.full((64, 80), 1000 + i * 10), position=(0, 0, i * 4),
                    series_uid=uid, instance=i + 1, spacing=(1, 1))
    return load_series(scan_paths([folder]).series[0])


def test_comparison_follows_position_zoom_and_pan(window, study, app, tmp_path):
    install(window, study, app)
    other = second_series(tmp_path)
    window.series.append(other.series)
    window.populate_series()
    assert window.compare_series.findData(other.series.uid) > 0
    window.set_compare(other)
    app.processEvents()
    compare = window.compare_view
    assert compare.isVisible() and window.mode == "2D stack"
    for index in range(3):
        window.slider_changed(index)
        app.processEvents()
        np.testing.assert_array_equal(compare.image, other.source[index])
    source = window.views["Source"]
    source.zoom_by(2)
    source.horizontalScrollBar().setValue(source.horizontalScrollBar().value() + 25)
    source.viewport().repaint()
    app.processEvents()
    assert compare.view_state() == source.view_state()
    compare.zoom_by(1.5)
    compare.viewport().repaint()
    app.processEvents()
    assert source.view_state() == compare.view_state()
    window.compare_view.scrolled.emit("Compare", -1)
    assert window.source_index == 1
    window.set_compare(None)
    assert not compare.isVisible()


def test_comparison_window_and_tools_are_its_own(window, study, app, tmp_path):
    install(window, study, app)
    other = second_series(tmp_path)
    window.series.append(other.series)
    window.set_compare(other)
    window.change_compare_window(50, 1010)
    assert window.compare_view.width == 50 and window.width_spin.value() != 50
    window.select_tool("Length")
    assert window.compare_view.tool == "Window" and window.views["Source"].tool == "Length"


def test_opening_the_compared_series_drops_the_comparison(window, study, app, tmp_path):
    install(window, study, app)
    other = second_series(tmp_path)
    window.series.append(other.series)
    window.set_compare(other)
    window.set_data(other)
    assert window.compare_volume is None and not window.compare_view.isVisible()
