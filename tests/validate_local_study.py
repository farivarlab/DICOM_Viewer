"""Opt-in validation of a user-supplied DICOM file and its neighboring series.

Reads input files only. Local artifacts omit identifying DICOM text. This is a
software check, not a medical interpretation or clinical validation protocol.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time

import numpy as np
import pydicom
from pydicom.pixels import apply_modality_lut
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lumen.app import MainWindow
from lumen.browser import Target, ROLE
from lumen.colors import lookup_table, window_pixels
from lumen.slice_view import Mark
from lumen.theme import STYLE


def rgb(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return np.frombuffer(image.bits(), np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width() * 4].reshape(image.height(), image.width(), 4)[:, :, :3].copy()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-study-validation"))
    args = parser.parse_args()
    source = args.file.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    inputs = sorted(source.parent.glob("*.dcm"))
    before = {path: digest(path) for path in inputs}
    report = {"input_file": source.name, "neighboring_dicom_files": len(inputs), "checks": {},
              "scope": "Local software validation; no medical interpretation; image exports omit identifying text."}
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    errors = []

    def fail_job(message):
        errors.append(message)
        window.end_job()

    window.fail_job = fail_job
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
        check("worker_completed_without_error", not window.busy and not errors)

    def save(image, name):
        check(f"saved_{name}", image.save(str(output / name), "PNG"))

    try:
        print("Checking the supplied file", flush=True)
        start = time.perf_counter()
        window.open_paths([str(source)])
        wait_idle()
        report["single_file_load_seconds"] = round(time.perf_counter() - start, 3)
        data = window.data
        raw = pydicom.dcmread(source)
        independent = apply_modality_lut(raw.pixel_array, raw).astype(np.float32)
        check("single_file_pixel_values_exact", np.array_equal(data.source[0], independent))
        check("default_2d_and_hidden_metadata", window.mode == "2D stack" and not window.metadata_dock.isVisible())
        check("single_slice_does_not_invent_mpr", not data.mpr_available)
        view = window.active_view
        center = view.mapFromScene(view.item.sceneBoundingRect().center())
        check("initial_image_centered", (center - view.viewport().rect().center()).manhattanLength() <= 2)
        check("calibration_matches_file", view.calibrated and np.allclose(view.spacing, [float(raw.PixelSpacing[1]), float(raw.PixelSpacing[0])]))
        check("source_orientation_labels", [view._orientation(*d) for d in [(-1, 0), (1, 0), (0, -1), (0, 1)]] == ["R", "L", "A", "P"])
        window.tags_action.trigger()
        app.processEvents()
        check("metadata_pane_matches_selected_file", window.metadata_pane.dataset is data.header(0) and source.name in window.metadata_pane.caption.text())
        check("file_annotation_text_present", bool(view.file_information[0]))
        window.tags_action.trigger()
        app.processEvents()
        base = rgb(window.image_capture(False))
        expected = lookup_table("Grayscale")[window_pixels(independent, view.width, view.level)]
        check("clean_png_matches_windowed_pixels_exactly", np.array_equal(base, expected))
        save(window.image_capture(False), "single-file-clean.png")
        view.rotate()
        rotated = rgb(window.image_capture(False))
        check("rotation_pixel_exact", np.array_equal(rotated, np.rot90(base, -1)))
        view.flip(True)
        check("horizontal_flip_after_rotation_pixel_exact", np.array_equal(rgb(window.image_capture(False)), rotated[:, ::-1]))
        view.rotate()
        check("rotation_after_flip_pixel_exact", np.array_equal(rgb(window.image_capture(False)), np.rot90(rotated[:, ::-1], -1)))
        window.reset_views()
        for name in ("Viridis", "Hot iron", "Magma", "Bone", "Cool", "Rainbow"):
            window.cmap.setCurrentText(name)
            expected = lookup_table(name)[window_pixels(independent, view.width, view.level)]
            check(f"colormap_{name.replace(' ', '_')}_pixel_exact", np.array_equal(rgb(window.image_capture(False)), expected))
        window.reset_views()

        print("Checking the neighboring series and navigation", flush=True)
        start = time.perf_counter()
        window.open_paths([str(source.parent)])
        wait_idle()
        report["series_load_seconds"] = round(time.perf_counter() - start, 3)
        data = window.data
        report["series"] = {"modality": data.series.modality, "dimensions_zyx": list(data.source.shape),
            "spacing_xyz_mm": [float(v) for v in data.spacing], "source_memory_mib": round(data.source.nbytes / 1024**2, 2),
            "pixel_range": [float(data.source.min()), float(data.source.max())], "units": data.units}
        check("all_neighboring_images_loaded", len(data.source) == len(inputs))
        check("series_stays_2d_without_mpr_allocation", window.mode == "2D stack" and data.mpr_available and not data.mpr_ready)
        windows = [data.frame_window(i) for i in range(len(data.source))]
        report["series"]["default_window_width_level"] = list(windows[0])
        check("fallback_window_stable_across_series", len(set(windows)) == 1 and windows[0][0] > 1)
        for index in (0, 50, 100, 149, 199, 250, len(data.source) - 1):
            window.slice_spin.setValue(index + 1)
            app.processEvents()
            check(f"navigation_{index + 1}", window.source_index == index and window.browser.currentItem().data(0, ROLE).path == data.reference(index).path)
        window.open_target(Target(data.series.uid, "file", source))
        app.processEvents()
        check("browser_opens_requested_file", data.reference(window.source_index).path == source)
        view = window.active_view
        clean = rgb(window.image_capture(False))
        view.marks.append(Mark("Length", [QPointF(20, 25), QPointF(60, 55)], view.key))
        view.marks.append(Mark("Text", [QPointF(25, 105)], view.key, "Validation annotation"))
        check("known_distance_calibration_37_5mm", np.isclose(np.hypot(40 * view.spacing[0], 30 * view.spacing[1]), 37.5))
        annotated = window.image_capture(True, False)
        check("annotated_png_adds_marks", np.count_nonzero(rgb(annotated) != clean) > 100)
        check("unannotated_png_excludes_marks", np.array_equal(rgb(window.image_capture(False)), clean))
        save(window.image_capture(False), "slice-clean.png")
        save(annotated, "slice-annotated.png")

        print("Checking MPR and slab projections", flush=True)
        start = time.perf_counter()
        window.mode_combo.setCurrentText("MPR")
        wait_idle()
        report["mpr_prepare_seconds"] = round(time.perf_counter() - start, 3)
        check("mpr_dimensions_and_spacing", data.canonical.shape == data.source.shape and np.allclose(data.canonical_spacing, data.spacing))
        check("orthogonal_mpr_pixel_exact_and_shared", np.array_equal(data.canonical, data.source) and np.shares_memory(data.canonical, data.source))
        window.move_crosshair("Axial", 141, 161)
        app.processEvents()
        x, y, z = window.cursor
        planes = {"Axial": data.source[z], "Coronal": data.source[:, y, :][::-1], "Sagittal": data.source[:, :, x][::-1]}
        for name, expected in planes.items():
            check(f"mpr_{name.lower()}_plane_exact", np.array_equal(window.views[name].image, expected))
            save(window.views[name].render_image(False), f"mpr-{name.lower()}.png")
        window.slab_mm.setValue(6.75)  # nine 0.75-mm samples, centered on the selected slice
        for name, reducer in (("MIP", np.max), ("MinIP", np.min), ("Average", np.mean)):
            window.slab_mode.setCurrentText(name)
            expected = reducer(data.source[z - 4:z + 5], axis=0)
            check(f"slab_{name}_exact", np.array_equal(window.views["Axial"].image, expected))
        window.slab_mode.setCurrentText("Slice")

        print("Checking native 3D rendering", flush=True)
        start = time.perf_counter()
        window.mode_combo.setCurrentText("3D volume")
        app.processEvents()
        volume = window.volume_view
        check("mr_uses_scalar_transfer", volume.preset == "Scalar")
        check("vtk_input_dimensions", tuple(volume.mapper.GetInput().GetDimensions()) == tuple(data.source.shape[::-1]))
        foreground = volume.capture()
        volume.volume.VisibilityOff()
        background = volume.capture()
        volume.volume.VisibilityOn()
        visible = np.max(np.abs(rgb(foreground).astype(np.int16) - rgb(background).astype(np.int16)), axis=2)
        height, width = visible.shape
        pixels = int(np.count_nonzero(visible[height//8:height*7//8, width//8:width*7//8] > 10))
        report["volume_foreground_pixels"] = pixels
        check("volume_contributes_visible_foreground", pixels > 1000)
        save(foreground, "volume.png")
        volume.renderer.GetActiveCamera().Azimuth(25)
        changed = volume.capture()
        check("3d_camera_rotation_changes_image", np.count_nonzero(rgb(changed) != rgb(foreground)) > 1000)
        volume.set_crop(.45)
        cropped = volume.capture()
        check("3d_cutaway_changes_image", np.count_nonzero(rgb(cropped) != rgb(changed)) > 1000)
        volume.set_crop(0)
        window.volume_blend.setCurrentText("MIP")
        check("3d_mip_renders", volume.capture() is not None)
        window.volume_blend.setCurrentText("MinIP")
        check("3d_minip_renders", volume.capture() is not None)
        report["volume_validation_seconds"] = round(time.perf_counter() - start, 3)
        window.mode_combo.setCurrentText("2D stack")
        app.processEvents()
        check("return_to_2d", window.active_view.plane == "Source" and window.mode == "2D stack")
        check("original_files_unchanged", all(digest(path) == value for path, value in before.items()))
        report["status"] = "passed"
    except Exception:
        report["status"] = "failed"
        raise
    finally:
        if not window.busy:
            window.close()
            app.processEvents()
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks_passed": sum(report["checks"].values()), "series": report["series"]}, indent=2))


if __name__ == "__main__":
    main()
