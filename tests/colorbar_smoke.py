"""Capture scalar legends and verify native 3D transfer colors and clean PNGs."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from lumen.app import MainWindow
from lumen.model import demo_volume


def pixels(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()*4].copy()


app = QApplication([])
app.setStyle("Fusion")
output = Path("artifacts/colorbar")
output.mkdir(parents=True, exist_ok=True)
window = MainWindow(settings_path=output / "preview.ini")
window.set_theme("cockpit", persist=False)
window.show()
data = demo_volume()
original = data.source.copy()
window.series = [data.series]
window.populate_series()
window.set_data(data)
window.slider_changed(55)
window.cmap.setCurrentText("Viridis")
app.processEvents()
assert window.grab().save(str(output / "2d.png"))
assert window.image_capture(False).save(str(output / "clean.png"))
assert window.image_capture(True).save(str(output / "annotated.png"))
window.mode_combo.setCurrentText("MPR + 3D")
app.processEvents()
screen = window.grab()
frame = window.volume_view.capture()
frame.setDevicePixelRatio(window.volume_view.vtk_widget.devicePixelRatioF())
painter = QPainter(screen)
origin = window.volume_view.vtk_widget.mapTo(window, window.volume_view.vtk_widget.rect().topLeft())
painter.drawImage(origin, frame)
painter.end()
assert screen.save(str(output / "mpr-volume.png"))
window.mode_combo.setCurrentText("3D volume")
window.volume_preset.setCurrentText("CT bone")
app.processEvents()
volume = window.volume_view
scale = volume.colorbar.scale
assert (scale.lower, scale.upper, scale.units) == (-1000, 2500, "HU")
transfer = volume.prop.GetRGBTransferFunction()
for index in (0, 64, 128, 255):
    value = scale.lower + index / 255 * (scale.upper - scale.lower)
    np.testing.assert_array_equal(scale.colors[index], np.round(np.array(transfer.GetColor(value)) * 255).astype(np.uint8))
clean = window.image_capture(False)
annotated = window.image_capture(True)
assert annotated.width() > clean.width() and annotated.height() == clean.height()
np.testing.assert_array_equal(pixels(annotated.copy(0, 0, clean.width(), clean.height())), pixels(clean))
assert annotated.save(str(output / "volume-colorbar.png"))
window.colorbar_action.setChecked(False)
assert volume.colorbar.isHidden()
assert volume.capture().width() == window.image_capture(False).width()
np.testing.assert_array_equal(data.source, original)
window.close()
app.processEvents()
print("PASS: 2D/MPR legends, actual VTK transfer colors, clean camera pixels, export and visibility")
