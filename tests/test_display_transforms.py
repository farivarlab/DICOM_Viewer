import numpy as np
from PySide6.QtGui import QImage
from lumen.slice_view import SliceView
from test_workflow import app


def rgb(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4].reshape(image.height(), image.width(), 4).copy()


def test_rotate_and_flip_follow_screen_axes_in_every_order(app):
    view = SliceView("Source")
    view.show()
    image = np.arange(35, dtype=np.float32).reshape(5, 7)
    view.set_image(image, (1, 1), ("Source", 0), 35, 17.5, "Grayscale", False, True)
    app.processEvents()
    original = rgb(view.render_image(False))
    expected = original
    for operation in ("H", "R", "V", "R", "H", "H", "R", "V", "R"):
        if operation == "R":
            view.rotate()
            expected = np.rot90(expected, -1)
        else:
            view.flip(operation == "H")
            expected = expected[:, ::-1] if operation == "H" else expected[::-1]
        np.testing.assert_array_equal(rgb(view.render_image(False)), expected)
        view.fit_image()
        np.testing.assert_array_equal(rgb(view.render_image(False)), expected)
    view.reset()
    np.testing.assert_array_equal(rgb(view.render_image(False)), original)
    view.close()
