"""Opt-in checks executed by the packaged application itself; no patient text is logged."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time


def run_selftest(input_path: str | None, report_path: str) -> int:
    """Exercise bundled Qt, image/export, reconstruction, VTK and codec dependencies."""
    import numpy as np
    import io
    from PIL import Image
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.pixels import get_decoder, get_encoder
    from pydicom.uid import ExplicitVRLittleEndian, RLELossless, JPEG2000Lossless, JPEGBaseline8Bit, JPEGLSLossless, JPEGLosslessSV1
    from pydicom.encaps import encapsulate
    from .app import MainWindow
    from .colors import lookup_table, window_pixels
    from .model import demo_volume, functional
    from .slice_view import Mark
    from .theme import STYLE

    destination = Path(report_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "checks": {}, "codecs": {}, "input": "provided" if input_path else "generated",
              "frozen": bool(getattr(sys, "frozen", False))}
    started = time.perf_counter()
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    errors = []

    def fail_job(message):
        errors.append(type(message).__name__)
        window.end_job()

    window.fail_job = fail_job  # self-tests report failure rather than waiting in a modal dialog
    window.show()
    app.processEvents()

    def check(name, condition):
        report["checks"][name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    def wait_idle():
        deadline = time.monotonic() + 120
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        app.processEvents()
        check("worker_finished", not window.busy and not errors)

    def rgb(image):
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        return np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4].reshape(image.height(), image.width(), 4)[:, :, :3].copy()

    try:
        resources = Path(__file__).resolve().parent / "resources"
        check("qt_svg_resources", all((resources / name).is_file() for name in ("check.svg", "chevron-down.svg", "chevron-up.svg", "more.svg")))
        if input_path:
            window.open_paths([str(Path(input_path).resolve(strict=True))])
            wait_idle()
        else:
            data = demo_volume()
            window.series = [data.series]
            window.populate_series()
            window.set_data(data)
            app.processEvents()
        data, view = window.data, window.active_view
        check("default_2d", window.mode == "2D stack" and view.plane == "Source")
        check("metadata_hidden", not window.metadata_dock.isVisible())
        center = view.mapFromScene(view.item.sceneBoundingRect().center())
        check("image_centered", (center - view.viewport().rect().center()).manhattanLength() <= 2)
        report["shape_zyx"] = list(data.source.shape[:3])
        report["spacing_xy_mm"] = list(data.frame_spacing(0)) if data.frame_calibrated(0) else None
        window.slider_changed(len(data.source) // 2)
        check("source_calibration", view.calibrated == data.frame_calibrated(window.source_index) and np.allclose(view.spacing, data.frame_spacing(window.source_index)))
        missing = [i for i in range(len(data.source)) if functional(data.header(i), data.reference(i).frame, "FrameVOILUTSequence", "WindowWidth") is None and functional(data.header(i), data.reference(i).frame, "FrameVOILUTSequence", "WindowCenter") is None]
        check("stable_missing_window_defaults", all(data.frame_window(i) == data.series_window() for i in missing))
        clean = window.image_capture(False)
        expected = data.source[window.source_index] if data.is_color else lookup_table(window.cmap.currentText(), window.invert_action.isChecked())[window_pixels(data.source[window.source_index], view.width, view.level)]
        if view.spacing[0] == view.spacing[1]:
            check("display_pixels_match", np.array_equal(rgb(clean), expected))
        else:
            check("display_pixels_present", not clean.isNull() and rgb(clean).size > 0)
        check("clean_png_export", clean.save(str(destination.parent / "selftest-clean.png"), "PNG"))
        view.marks.append(Mark("Length", [QPointF(10, 10), QPointF(35, 25)], view.key))
        check("annotated_export", not np.array_equal(rgb(window.image_capture(True, False)), rgb(clean)))
        check("clean_export_excludes_marks", np.array_equal(rgb(window.image_capture(False)), rgb(clean)))
        window.tags_action.trigger()
        app.processEvents()
        check("metadata_opens", window.metadata_dock.isVisible() and window.metadata_pane.dataset is data.header(window.source_index))
        window.tags_action.trigger()

        if data.mpr_available:
            window.mode_combo.setCurrentText("MPR")
            wait_idle()
            check("mpr_constructed", data.mpr_ready and all(window.views[name].image is not None for name in ("Axial", "Coronal", "Sagittal")))
            window.mode_combo.setCurrentText("3D volume")
            app.processEvents()
            volume = window.volume_view
            foreground = volume.capture()
            volume.volume.VisibilityOff()
            background = volume.capture()
            volume.volume.VisibilityOn()
            difference = np.max(np.abs(rgb(foreground).astype(np.int16) - rgb(background).astype(np.int16)), axis=2)
            h, w = difference.shape
            foreground_pixels = int(np.count_nonzero(difference[h//8:h*7//8, w//8:w*7//8] > 10))
            report["volume_foreground_pixels"] = foreground_pixels
            check("vtk_volume_visible", foreground_pixels > 100)
            check("vtk_dimensions", tuple(volume.mapper.GetInput().GetDimensions()) == tuple(data.canonical.shape[::-1]))
            check("volume_png_export", foreground.save(str(destination.parent / "selftest-volume.png"), "PNG"))
            window.mode_combo.setCurrentText("2D stack")
            check("return_to_2d", window.mode == "2D stack")
        else:
            report["mpr"] = "unavailable_for_input_geometry"

        samples = (np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 1024).copy()
        for name, uid in (("rle", RLELossless), ("jpeg2000", JPEG2000Lossless), ("jpegls", JPEGLSLossless)):
            decoder, encoder = get_decoder(uid), get_encoder(uid)
            report["codecs"][name] = {"decoder_plugins": list(decoder.available_plugins), "encoder_plugins": list(encoder.available_plugins)}
            check(f"{name}_decoder_available", decoder.is_available)
            if encoder.is_available:
                ds = Dataset()
                ds.file_meta = FileMetaDataset()
                ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
                ds.Rows, ds.Columns, ds.SamplesPerPixel = 64, 64, 1
                ds.PhotometricInterpretation = "MONOCHROME2"
                ds.BitsAllocated = ds.BitsStored = 16
                ds.HighBit, ds.PixelRepresentation = 15, 0
                ds.PixelData = samples.tobytes()
                ds.compress(uid)
                check(f"{name}_lossless_roundtrip", np.array_equal(ds.pixel_array, samples))
        check("jpeg_decoder_available", get_decoder(JPEGBaseline8Bit).is_available)
        check("jpeg_lossless_decoder_available", get_decoder(JPEGLosslessSV1).is_available)
        stored = (samples % 256).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(stored).save(buffer, format="JPEG", quality=100, subsampling=0)
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = JPEGBaseline8Bit
        ds.Rows, ds.Columns, ds.SamplesPerPixel = 64, 64, 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 8
        ds.HighBit, ds.PixelRepresentation = 7, 0
        ds.PixelData = encapsulate([buffer.getvalue()])
        decoded = ds.pixel_array
        check("jpeg_baseline_decodes", decoded.shape == stored.shape and float(np.abs(decoded.astype(float) - stored).mean()) < 2)
        window.close()
        app.processEvents()
        check("clean_shutdown", not window.isVisible() and not window.busy)
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
    finally:
        if window.busy:
            window.cancel_job()
            deadline = time.monotonic() + 120
            while window.busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
        if not window.busy and window.isVisible():
            window.close()
            app.processEvents()
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["status"] == "passed" else 1
