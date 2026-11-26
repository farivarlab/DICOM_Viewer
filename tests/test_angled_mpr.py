"""Angled MPR: planes tilted/rotated about the crosshair, in patient coordinates."""
from dataclasses import replace

import numpy as np
import pytest
from PySide6.QtCore import QPointF

from lumen import annotation_store
from lumen.model import demo_volume
from lumen.slice_view import Mark
from test_workflow import app, window, study, install


def linear_volume():
    """The demo geometry with values equal to each voxel's LPS x and z in millimetres."""
    data = demo_volume()
    nz, ny, nx = data.canonical.shape
    z, y, x = np.mgrid[:nz, :ny, :nx].astype(np.float32)
    world_x = data.canonical_origin[0] + x * data.canonical_spacing[0]
    world_z = data.canonical_origin[2] + z * data.canonical_spacing[2]
    values = (world_x + 1000 * world_z).astype(np.float32)
    return replace(data, source=values, canonical=values)


def test_zero_angles_match_the_orthogonal_planes():
    data = demo_volume()
    cursor = [70, 60, 50]
    for name in ("Axial", "Coronal", "Sagittal"):
        straight, spacing = data.plane(name, cursor)
        sampled, oblique_spacing = data._oblique_plane(name, cursor, "Slice", 1, (0, 0))
        np.testing.assert_array_equal(sampled, straight)
        assert oblique_spacing == spacing


@pytest.mark.parametrize("angles", [(20, 0), (0, 35), (-15, 50)])
def test_angled_planes_sample_the_patient_position_of_each_pixel(angles):
    data = linear_volume()
    cursor = [72, 70, 56]
    for name in ("Axial", "Coronal", "Sagittal"):
        image, _ = data.plane(name, cursor, angles=angles)
        world = data.plane_points(name, cursor, image.shape, angles)
        expected = (world[0] + 1000 * world[2]).reshape(image.shape)
        inside = np.all((data.world_to_canonical(world) >= 0) &
                        (data.world_to_canonical(world) <= np.array(data.canonical.shape[::-1])[:, None] - 1), axis=0)
        np.testing.assert_allclose(image.reshape(-1)[inside], expected.reshape(-1)[inside], rtol=0, atol=.05)
        # The plane passes through the crosshair, at the unrotated cursor pixel.
        _, _, (c0, r0) = data._plane_layout(name, cursor)
        assert data.pixel_to_cursor(name, c0 + .5, r0 + .5, cursor, angles) == cursor


def test_pixel_spacing_is_preserved_when_rotated():
    data = demo_volume()
    points = data.plane_points("Axial", [70, 60, 50], (3, 3), (25, 40))
    columns = np.linalg.norm(points[:, 1] - points[:, 0])
    rows = np.linalg.norm(points[:, 3] - points[:, 0])
    assert columns == pytest.approx(data.canonical_spacing[0]) and rows == pytest.approx(data.canonical_spacing[1])
    assert np.dot(points[:, 1] - points[:, 0], points[:, 3] - points[:, 0]) == pytest.approx(0, abs=1e-9)


def test_angled_slab_is_a_projection_along_the_normal():
    data = demo_volume()
    cursor = [72, 70, 56]
    single, _ = data.plane("Axial", cursor, slab_mode="Slice", angles=(15, 10))
    mip, _ = data.plane("Axial", cursor, slab_mode="MIP", slab_mm=12, angles=(15, 10))
    minip, _ = data.plane("Axial", cursor, slab_mode="MinIP", slab_mm=12, angles=(15, 10))
    assert np.all(mip >= single - 1e-3) and np.all(minip <= single + 1e-3) and (mip > single).any()


def test_viewer_angles_drive_planes_marks_and_storage(window, study, app, tmp_path):
    install(window, study, app)
    data = demo_volume()
    window.series.append(data.series)
    window.populate_series()
    window.set_data(data)
    window.mode_combo.setCurrentText("MPR")
    app.processEvents()
    window.plane_tilt.setValue(20)
    view = window.views["Axial"]
    assert len(view.key) == 6 and view.key[4] == (20., 0.)
    assert "20° / 0°" in view.subtitle
    view.marks.append(Mark("Length", [QPointF(10, 10), QPointF(20, 10)], view.key))
    records = annotation_store.to_records(data, {"Axial": view.marks})
    restored = annotation_store.from_records(data, records)["Axial"][0]
    assert restored.key == view.key
    before = list(window.cursor)
    window.move_crosshair("Axial", 30.5, 40.5)
    expected = data.pixel_to_cursor("Axial", 30.5, 40.5, before, (20., 0.))
    assert window.cursor == expected != before
    window.set_data(data)
    assert window.plane_angles() == (0, 0)  # a new series starts straight
