import numpy as np
import pytest

from lumen.colorbar import BAR_WIDTH, window_scale
from lumen.slice_view import SliceView
from lumen.export_dialog import ExportDialog
from lumen.app import MainWindow
from test_workflow import app, study, install


@pytest.mark.parametrize("width,level,dicom,expected", [
    (400, 40, True, (-160, 239)), (1, -1024, True, (-1024.5, -1024.5)),
    (.01, .005, False, (0, .01)), (.002, -.001, False, (-.002, 0)),
])
def test_scale_labels_match_display_window_boundaries(width, level, dicom, expected):
    scale = window_scale(width, level, "Grayscale", dicom=dicom)
    assert (scale.lower, scale.upper) == pytest.approx(expected)
    assert scale.threshold == (dicom and width == 1)


@pytest.mark.parametrize("colormap,inverted", [("Viridis", False), ("Magma", True), ("Grayscale", True)])
def test_colorbar_end_colors_match_rendered_voxels(app, colormap, inverted):
    view = SliceView("Source")
    view.show()
    try:
        pixels = np.tile(np.linspace(0, .01, 256, dtype=np.float32), (32, 1))
        view.set_image(pixels, (1, 1), (0,), .01, .005, colormap, inverted, True,
                       units="magnitude", dicom_window=False)
        image = view.item.pixmap().toImage()
        gradient = view.colorbar.gradient
        assert gradient.pixelColor(0, 0) == image.pixelColor(255, 0)
        assert gradient.pixelColor(0, 255) == image.pixelColor(0, 0)
        assert view.colorbar.scale.units == "magnitude"
        assert view.viewportMargins().right() == BAR_WIDTH
    finally:
        view.close()


def test_threshold_scale_has_only_two_colors_and_rgb_has_no_scalar_legend(app):
    view = SliceView("Source")
    view.set_image(np.array([[0., 1.]]), (1, 1), (0,), 1, .5, "Grayscale", False, True)
    gradient = view.colorbar.gradient
    assert {gradient.pixelColor(0, y).rgb() for y in range(gradient.height())} == {0xff000000, 0xffffffff}
    view.set_image(np.ones((12, 16, 3), np.uint8) * 100, (1, 1), (1,), 1, 0, "Grayscale", False, False)
    assert view.colorbar.isHidden() and view.viewportMargins().right() == 0
    assert view.render_image(True).width() == 16
    view.close()


def test_colorbar_toggle_and_export_keep_image_pixels_and_orientation(app, study, tmp_path):
    window = MainWindow(settings_path=tmp_path / "settings.ini")
    window.show()
    install(window, study, app)
    try:
        view = window.active_view
        assert window.colorbar_action.isChecked() and view.colorbar.isVisible()
        view.rotate()
        rotated = window.image_capture(False)
        window.colorbar_action.trigger()
        assert view.colorbar.isHidden()
        assert window.image_capture(False) == rotated
        window.colorbar_checkbox.setChecked(True)
        assert window.volume_colorbar_checkbox.isChecked()
        assert window.image_capture(False, include_colorbar=True) == rotated
        with_bar = window.image_capture(True, include_colorbar=True)
        assert with_bar.width() == rotated.width() + BAR_WIDTH
        assert with_bar.height() == rotated.height()
        assert with_bar.copy(0, 0, rotated.width(), rotated.height()) == rotated
        # Explicit export is still available when the on-screen legend is hidden.
        window.colorbar_action.setChecked(False)
        window.change_window(80, 40)
        assert window.image_capture(True, include_colorbar=True).width() == rotated.width() + BAR_WIDTH
        assert window.active_view.colorbar.scale.upper == 79
    finally:
        window.close()


def test_clean_export_disables_colorbar_option(app):
    dialog = ExportDialog(colorbar_visible=True)
    assert dialog.include_colorbar
    dialog.content.setCurrentIndex(1)
    assert not dialog.include_colorbar and not dialog.colorbar.isEnabled()
    dialog.close()
