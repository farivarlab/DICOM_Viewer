"""Render both themes from source without rebuilding a release."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from lumen.app import MainWindow
from lumen.model import demo_volume
from lumen.theme import THEME_CHOICES

app = QApplication([])
app.setStyle("Fusion")
output = Path("artifacts/themes")
output.mkdir(parents=True, exist_ok=True)
window = MainWindow(settings_path=output / "preview.ini")
window.show()
data = demo_volume()
window.series = [data.series]
window.populate_series()
window.set_data(data)
window.slider_changed(55)
for name, _ in THEME_CHOICES:
    window.set_theme(name, persist=False)
    app.processEvents()
    assert window.grab().save(str(output / f"{name}.png"))
    window.resize(1120, 740)
    app.processEvents()
    assert window.grab().save(str(output / f"{name}-compact.png"))
    window.resize(1520, 960)
    app.processEvents()
window.set_theme("light", persist=False)
window.close()
app.processEvents()
print("PASS: four modern/classic themes at normal and compact sizes")
