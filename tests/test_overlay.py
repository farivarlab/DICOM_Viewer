"""Registered overlays: patient-coordinate sampling, colouring and the viewer controls."""
from dataclasses import replace

import numpy as np
import pytest

from lumen import overlay
from lumen.model import demo_volume, load_series
from test_workflow import app, window, study, install


def test_overlay_of_the_same_volume_reproduces_every_plane():
    base, other = demo_volume(), demo_volume()
    cursor = [40, 60, 30]
    for plane in ("Axial", "Coronal", "Sagittal"):
        image, _ = base.plane(plane, cursor)
        values = overlay.sample(other, overlay.plane_points(base, plane, cursor, image.shape), image.shape)
        np.testing.assert_allclose(values, image, atol=1e-3)


def test_source_images_sample_through_the_affine(study):
    _, data = study
    for index in range(len(data.source)):
        shape = data.source[index].shape
        values = overlay.sample(data, overlay.source_points(data, index, shape), shape)
        np.testing.assert_array_equal(values, data.source[index])


def test_shifted_overlay_moves_by_its_patient_offset(study):
    _, data = study
    shifted = data.affine.copy()
    shifted[:3, 3] += data.affine[:3, 0]  # one column further along the row direction
    other = replace(data, affine=shifted)
    shape = data.source[1].shape
    values = overlay.sample(other, overlay.source_points(data, 1, shape), shape)
    np.testing.assert_array_equal(values[:, 1:], data.source[1][:, :-1])
    assert np.isnan(values[:, 0]).all()


def test_colorize_hides_outside_and_below_range():
    values = np.array([[np.nan, 0., 5., 10.]], np.float32)
    rgba = overlay.colorize(values, 5, 10, "Viridis", .5)
    assert rgba[0, :, 3].tolist() == [0, 0, 128, 128]
    assert rgba[0, 2, :3].tolist() == [68, 1, 84] and rgba[0, 3, :3].tolist() == [253, 231, 37]
    assert overlay.colorize(values, 5, 10, "Viridis", 1, hide_below=False)[0, 1, 3] == 255


def test_maps_starting_at_black_keep_the_lowest_shown_value_visible():
    for name in ("Hot iron", "Grayscale", "Magma"):
        lowest = overlay.colorize(np.array([[1.]], np.float32), 1, 2, name, 1)[0, 0, :3]
        assert lowest.max() >= 60, name


def test_default_range_recognises_label_maps(study):
    _, data = study
    labels = replace(data, source=np.repeat([0., 1., 2., 7.], 60).reshape(4, 3, 20).astype(np.float32))
    assert overlay.default_range(labels) == (1., 7., True)
    low, high, is_labels = overlay.default_range(demo_volume())
    assert not is_labels and low < high


def test_overlay_is_drawn_probed_exported_and_removed(window, study, app):
    data = install(window, study, app)
    view = window.active_view
    plain = view.render_image(annotated=False)
    assert window.overlay_series.isEnabled()
    window.series.append(demo_volume().series)
    window.populate_series()
    assert window.overlay_series.findData("demo") > 0
    assert window.overlay_series.findData(data.series.uid) == -1  # never fused over itself
    window.set_overlay(demo_volume())
    app.processEvents()
    assert view.fusion_item.isVisible()
    assert np.isfinite(view.fusion_values).any()
    assert window.overlay_series.currentData() == "demo"
    assert window.overlay_cmap.isEnabled()
    fused = view.render_image(annotated=False)
    assert fused.size() == plain.size() and fused != plain
    window.overlay_opacity.setValue(0)
    assert view.render_image(annotated=False) == plain
    window.set_overlay(None)
    assert not view.fusion_item.isVisible()
    assert window.overlay_series.currentData() is None


def test_overlay_needs_matching_spatial_units(window, study, app):
    install(window, study, app)
    other = demo_volume()
    other.geometry_unit = "units"
    with pytest.raises(ValueError, match="spatial units"):
        window.set_overlay(other)
    assert window.overlay_volume is None


def test_choosing_an_overlay_loads_it_in_the_background(window, study, app):
    from test_app_audit import wait_for_idle
    install(window, study, app)
    window.series.append(demo_volume().series)
    window.populate_series()
    window.overlay_series.setCurrentIndex(window.overlay_series.findData("demo"))
    wait_for_idle(window, app)
    assert window.overlay_volume is not None and window.overlay_volume.series.uid == "demo"
    assert window.views["Source"].fusion_item.isVisible()
    window.overlay_series.setCurrentIndex(0)
    assert window.overlay_volume is None
