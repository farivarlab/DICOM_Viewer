"""A bounded synthetic navigation benchmark; no clinical data or packaging."""
from pathlib import Path
import sys
import time
import json
import numpy as np
from pydicom.dataset import Dataset
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lumen.app import MainWindow
from lumen.model import ImageVolume, Series
from lumen.theme import STYLE

app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = MainWindow()
window.show()
app.processEvents()
pixels = np.random.default_rng(7).normal(40, 250, (96, 512, 512)).astype(np.float32)
ds = Dataset()
ds.PatientName = "Synthetic^Benchmark"
ds.WindowWidth, ds.WindowCenter = 400, 40
ds.PixelSpacing = [1, 1]
series = Series("benchmark", "512-pixel navigation", "Synthetic benchmark", "Performance check", "CT", "", frames=96)
data = ImageVolume(pixels, ds, series, (1, 1, 1), np.eye(4), 400, 40, False, True, units="HU")
window.series = [series]
window.populate_series()
window.set_data(data)
app.processEvents()
durations = []
for i in range(96):
    start = time.perf_counter()
    window.slider_changed(i)
    app.processEvents()
    durations.append((time.perf_counter() - start) * 1000)
result = {"dimensions": [96, 512, 512], "median_ms_per_frame": round(float(np.median(durations)), 2),
          "p95_ms_per_frame": round(float(np.percentile(durations, 95)), 2), "mpr_built": data.mpr_ready}
Path("artifacts/navigation-performance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
window.close()
app.processEvents()
print(json.dumps(result))
