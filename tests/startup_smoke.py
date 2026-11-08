"""Exercise the real splash/bootstrap and maximized launch from source."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplashScreen
from lumen.startup import main

app = QApplication([])
output = Path("artifacts/startup")
output.mkdir(parents=True, exist_ok=True)
started = time.perf_counter()
report, errors = {}, []
deadline = time.monotonic() + 30


def capture_splash():
    visible = [w for w in app.topLevelWidgets() if isinstance(w, QSplashScreen) and w.isVisible()]
    report["splash_before_imaging_import"] = bool(visible) and "lumen.app" not in sys.modules
    if visible:
        visible[0].grab().save(str(output / "splash.png"))


def observe():
    try:
        window = next((w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow"), None)
        if not window or window.busy or window.data is None:
            assert time.monotonic() < deadline, "Startup did not finish"
            return
        timer.stop()
        report["ready_seconds"] = round(time.perf_counter() - started, 3)
        report["started_maximized"] = window.isMaximized() and not window.isFullScreen()
        report["within_desktop_work_area"] = window.screen().availableGeometry().contains(window.geometry())
        report["splash_closed"] = not any(isinstance(w, QSplashScreen) and w.isVisible() for w in app.topLevelWidgets())
        report["initial_2d_view"] = window.mode == "2D stack"
        window.grab().save(str(output / "maximized.png"))
        window.activateWindow()
        QTest.qWait(100)
        QTest.keyClick(window, Qt.Key.Key_F11)
        QTest.qWait(100)
        report["f11_enters_full_screen"] = window.isFullScreen()
        QTest.keyClick(window, Qt.Key.Key_F11)
        QTest.qWait(100)
        report["f11_restores_maximized_window"] = window.isMaximized() and not window.isFullScreen()
        window.close()
    except Exception as error:
        errors.append(str(error))
        timer.stop()
        app.quit()


QTimer.singleShot(0, capture_splash)
timer = QTimer()
timer.setInterval(50)
timer.timeout.connect(observe)
timer.start()
result = main(["--demo"])
(output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
assert result == 0 and not errors, errors
assert report and all(value for key, value in report.items() if key != "ready_seconds"), report
print(json.dumps(report, indent=2))
