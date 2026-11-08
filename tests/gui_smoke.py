"""Run directly on Windows: exercises the actual Qt / VTK rendering pipeline."""
import sys
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lumen.app import MainWindow
from lumen.model import demo_volume
from lumen.theme import STYLE


app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow()
window.show()
app.processEvents()
data = demo_volume()
window.series.append(data.series)
window.populate_series()
window.set_data(data)
app.processEvents()
assert window.mode == "2D stack"
assert window.views["Source"].image is not None
assert not window.metadata_dock.isVisible()
assert window.volume_view.vtk_widget is None
window.resize(1120, 740)
app.processEvents()
assert window.grab().save("artifacts/viewer-compact.png")
window.resize(1520, 960)
app.processEvents()
assert window.grab().save("artifacts/viewer-2d.png")
window.mode_combo.setCurrentText("MPR + 3D")
app.processEvents()
assert all(window.views[name].image is not None for name in ("Axial", "Coronal", "Sagittal"))
window.move_crosshair("Axial", 43, 68)
assert window.cursor[:2] == [43, 68]
window.change_window(1500, -600)
assert window.views["Axial"].width == 1500
window.slab_mode.setCurrentText("MIP")
window.cmap.setCurrentText("Viridis")
window.mode_combo.setCurrentText("2D stack")
app.processEvents()
window.scroll_slice("Source", 3)
assert window.source_index == 3
window.toggle_cine(True)
assert window.cine_timer.isActive()
window.cine_step()
window.stop_cine()
window.active_view.rotate()
window.active_view.flip(True)
window.reset_views()
window.mode_combo.setCurrentText("MPR + 3D")
window.slab_mode.setCurrentText("Slice")
window.volume_preset.setCurrentText("CT bone")
app.processEvents()
window.volume_view.render()
frame = window.volume_view.capture()
assert frame is not None and frame.width() > 0
pixels = np.frombuffer(frame.bits(), np.uint8)
assert pixels.std() > 10, "Volume renderer produced a blank framebuffer"
output = Path("artifacts")
output.mkdir(exist_ok=True)
assert frame.save(str(output / "volume-smoke.png"))
screen = window.grab()
# Native VTK surfaces may be absent from QWidget.grab; composite their real framebuffer.
painter = QPainter(screen)
origin = window.volume_view.vtk_widget.mapTo(window, window.volume_view.vtk_widget.rect().topLeft())
frame.setDevicePixelRatio(window.volume_view.vtk_widget.devicePixelRatioF())
painter.drawImage(origin, frame)
painter.end()
assert screen.save(str(output / "viewer-smoke.png"))
window.mode_combo.setCurrentText("3D volume")
app.processEvents()
assert window.image_capture() is not None
window.mode_combo.setCurrentText("MPR")
app.processEvents()
assert not window.volume_view.isVisible()
window.set_data(demo_volume())
app.processEvents()
assert window.mode == "2D stack"
assert window.volume_view._image_ref is None
assert window.volume_view.mapper.GetInput() is None
window.mode_combo.setCurrentText("3D volume")
app.processEvents()
assert window.volume_view.capture() is not None
window.close()
app.processEvents()
print("PASS: Qt views, linked MPR, windowing, slabs, cine, transforms, 3D rendering, image capture, shutdown")
