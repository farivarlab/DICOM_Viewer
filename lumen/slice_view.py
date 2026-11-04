from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QInputDialog

from .colors import lookup_table, window_pixels
from .annotations import file_annotations


@dataclass
class Mark:
    tool: str
    points: list[QPointF]
    key: tuple
    label: str = ""
    cached_label: str | None = None


def angle_degrees(points: list[QPointF], spacing: tuple[float, float]) -> float:
    a, b, c = [np.array([p.x() * spacing[0], p.y() * spacing[1]]) for p in points]
    u, v = a - b, c - b
    denominator = np.linalg.norm(u) * np.linalg.norm(v)
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v) / denominator, -1, 1)))) if denominator else 0


def roi_statistics(image: np.ndarray, p: QPointF, q: QPointF, ellipse: bool, spacing):
    height, width = image.shape[:2]
    x0, x1 = sorted((p.x(), q.x()))
    y0, y1 = sorted((p.y(), q.y()))
    left, right = max(0, min(width, math.ceil(x0))), max(0, min(width, math.floor(x1) + 1))
    top, bottom = max(0, min(height, math.ceil(y0))), max(0, min(height, math.floor(y1) + 1))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return "Empty ROI"
    if ellipse:
        yy, xx = np.mgrid[top:bottom, left:right]
        mask = ((xx - (x0 + x1) / 2) / max(.5, (x1 - x0) / 2)) ** 2 + ((yy - (y0 + y1) / 2) / max(.5, (y1 - y0) / 2)) ** 2 <= 1
        crop = crop[mask]
    if crop.size == 0:
        return "Empty ROI"
    count = crop.shape[0] if ellipse else crop.shape[0] * crop.shape[1]
    area = count * spacing[0] * spacing[1]
    if image.ndim == 3:
        channels = crop.reshape(-1, crop.shape[-1]).mean(axis=0)
        return f"Area {area:.1f} {{area_unit}} · RGB mean " + ", ".join(f"{v:.1f}" for v in channels[:3])
    return (f"Area {area:.1f} {{area_unit}} · mean {crop.mean():.1f} {{unit}}\n"
            f"SD {crop.std():.1f} · min {crop.min():.1f} · max {crop.max():.1f}")


class SliceView(QGraphicsView):
    activated = Signal(object)
    scrolled = Signal(str, int)
    window_changed = Signal(float, float)
    cursor_changed = Signal(str, float, float)
    probed = Signal(str)

    def __init__(self, plane: str, parent=None):
        super().__init__(parent)
        self.plane = plane
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.scene().addItem(self.item)
        self.setBackgroundBrush(QColor("#060a10"))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 160)
        self.image = None
        self.spacing = (1., 1.)
        self.calibrated = False
        self.width, self.level = 400., 40.
        self.colormap, self.inverted = "Grayscale", False
        self.tool = "Window"
        self.active = False
        self.title = plane
        self.subtitle = ""
        self.key = ()
        self.marks: list[Mark] = []
        self.pending: list[QPointF] = []
        self.preview = None
        self.start_pos = None
        self.drag_kind = None
        self.crosshair = None
        self.show_crosshair = True
        self.show_overlays = True
        self.units = "value"
        self.directions = None
        self._needs_fit = True
        self._auto_fit = True
        self._wheel_remainder = 0
        self.file_information = ([], [])
        self.overlay_items = []
        self.overlay_layers = []
        self.show_dicom_overlays = True
        self._render_key = None
        self._annotation_key = None

    def set_file_annotations(self, dataset, layers=(), reconstruction=False):
        layers = list(layers)
        key = (id(dataset), reconstruction, tuple((row, col, mask.__array_interface__["data"][0], mask.shape, mask.strides)
                                                  for row, col, mask in layers))
        if key == self._annotation_key:
            return
        self._annotation_key = key
        self.file_information = file_annotations(dataset, reconstruction=reconstruction)
        for item in self.overlay_items:
            self.scene().removeItem(item)
        self.overlay_items.clear()
        self.overlay_layers = layers
        for row, column, mask in self.overlay_layers:
            rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
            rgba[mask != 0] = (255, 240, 145, 220)
            image = QImage(rgba.data, mask.shape[1], mask.shape[0], rgba.strides[0], QImage.Format.Format_RGBA8888).copy()
            item = QGraphicsPixmapItem(QPixmap.fromImage(image), self.item)
            item.setPos(column, row)
            item.setVisible(self.show_dicom_overlays)
            self.overlay_items.append(item)
        self.viewport().update()

    def set_image(self, image, spacing, key, width, level, colormap, inverted, calibrated,
                  subtitle="", crosshair=None, directions=None, units="value"):
        changed_size = self.image is None or self.image.shape != image.shape or self.spacing != spacing
        if key != self.key:
            self.pending.clear()
            self.preview = None
        self.image, self.spacing, self.key = image, spacing, key
        self.width, self.level = width, level
        self.colormap, self.inverted = colormap, inverted
        self.calibrated, self.subtitle, self.crosshair = calibrated, subtitle, crosshair
        self.directions, self.units = directions, units
        render_key = (id(image), spacing, width, level, colormap, inverted)
        if render_key != self._render_key:
            self.refresh_pixels()
            self._render_key = render_key
        else:
            self.viewport().update()
        if changed_size or self._needs_fit:
            self.fit_image(reset_orientation=self._needs_fit)

    def refresh_pixels(self):
        if self.image is None:
            return
        if self.image.ndim == 3:
            rgb = np.ascontiguousarray(self.image[:, :, :3], dtype=np.uint8)
        else:
            rgb = lookup_table(self.colormap, self.inverted)[window_pixels(self.image, self.width, self.level)]
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.item.setPixmap(QPixmap.fromImage(qimage))
        self.item.setTransform(QTransform.fromScale(*self.spacing))
        bounds = self.item.sceneBoundingRect()
        # Extra scene space lets users pan even when the image is fitted to the pane.
        self.scene().setSceneRect(bounds.adjusted(-bounds.width() * 4, -bounds.height() * 4,
                                                bounds.width() * 4, bounds.height() * 4))
        self.viewport().update()

    def fit_image(self, reset_orientation=False):
        if self.image is not None:
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
            transform = self.transform()
            unit = max(1e-12, math.hypot(transform.m11(), transform.m12()))
            orientation = QTransform() if reset_orientation else QTransform(
                transform.m11() / unit, transform.m12() / unit,
                transform.m21() / unit, transform.m22() / unit, 0, 0)
            self.setTransform(orientation)
            self.fitInView(self.item.sceneBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.scale(.90, .90)
            self.centerOn(self.item.sceneBoundingRect().center())
            error = self.mapFromScene(self.item.sceneBoundingRect().center()) - self.viewport().rect().center()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + error.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + error.y())
            self.setTransformationAnchor(anchor)
            self._needs_fit = False
            self._auto_fit = True

    def reset(self):
        self.pending.clear()
        self.preview = None
        self.fit_image(reset_orientation=True)

    def rotate(self):
        self.rotate_view(90)

    def rotate_view(self, degrees):
        center = self.mapToScene(self.viewport().rect().center())
        transform = self.transform()
        c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        # Compose in display coordinates so clockwise stays clockwise after a flip.
        self.setTransform(QTransform(
            c * transform.m11() - s * transform.m12(), s * transform.m11() + c * transform.m12(),
            c * transform.m21() - s * transform.m22(), s * transform.m21() + c * transform.m22(),
            c * transform.dx() - s * transform.dy(), s * transform.dx() + c * transform.dy()))
        self.centerOn(center)
        self.viewport().update()

    def flip(self, horizontal: bool):
        center = self.mapToScene(self.viewport().rect().center())
        transform = self.transform()
        sx, sy = (-1, 1) if horizontal else (1, -1)
        self.setTransform(QTransform(sx * transform.m11(), sy * transform.m12(),
                                     sx * transform.m21(), sy * transform.m22(),
                                     sx * transform.dx(), sy * transform.dy()))
        self.centerOn(center)
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._needs_fit or self._auto_fit:
            self.fit_image()

    def pixel_at(self, pos):
        return self.item.mapFromScene(self.mapToScene(pos))

    def screen_at(self, point):
        return self.mapFromScene(self.item.mapToScene(point))

    def wheelEvent(self, event):
        self.activated.emit(self)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        else:
            self._wheel_remainder += event.angleDelta().y()
            steps = math.trunc(self._wheel_remainder / 120)
            self._wheel_remainder -= steps * 120
            if steps:
                self.scrolled.emit(self.plane, -steps)
        event.accept()

    def zoom_by(self, factor):
        current = max(1e-12, math.hypot(self.transform().m11(), self.transform().m12()) * min(self.spacing))
        target = min(500., max(.02, current * factor))
        self.scale(target / current, target / current)
        self._auto_fit = False

    def mousePressEvent(self, event):
        self.activated.emit(self)
        self.setFocus()
        if self.image is None:
            return
        self.start_pos = event.position().toPoint()
        self.drag_kind = "Pan" if event.button() == Qt.MouseButton.MiddleButton else (
            "Window" if event.button() == Qt.MouseButton.RightButton else self.tool)
        point = self.pixel_at(self.start_pos)
        if self.drag_kind in ("Length", "Rectangle", "Ellipse", "Arrow"):
            self.pending = [point]
            self.preview = point
        elif self.drag_kind == "Angle":
            self.pending.append(point)
            if len(self.pending) == 3:
                self.marks.append(Mark("Angle", self.pending.copy(), self.key))
                self.pending.clear()
                self.preview = None
        elif self.drag_kind == "Text":
            text, ok = QInputDialog.getText(self, "Add annotation", "Text:")
            if ok and text.strip():
                self.marks.append(Mark("Text", [point], self.key, text.strip()))
        elif self.drag_kind == "Crosshair":
            self.cursor_changed.emit(self.plane, point.x(), point.y())
        self.viewport().update()

    def mouseMoveEvent(self, event):
        if self.image is None:
            return
        pos = event.position().toPoint()
        point = self.pixel_at(pos)
        x, y = int(round(point.x())), int(round(point.y()))
        if 0 <= y < self.image.shape[0] and 0 <= x < self.image.shape[1]:
            value = self.image[y, x]
            value_text = ", ".join(str(int(i)) for i in value) if self.image.ndim == 3 else f"{value:.1f} {self.units}"
            self.probed.emit(f"{self.plane} · pixel {x}, {y} · {value_text}")
        if self.pending:
            self.preview = point
            self.viewport().update()
        if self.start_pos is None or not event.buttons():
            return
        delta = pos - self.start_pos
        if self.drag_kind == "Window" and self.image.ndim == 2:
            sensitivity = max(1, self.width / 250)
            self.window_changed.emit(max(1, self.width + delta.x() * sensitivity), self.level + delta.y() * sensitivity)
        elif self.drag_kind == "Pan":
            self._auto_fit = False
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        elif self.drag_kind == "Zoom":
            self.zoom_by(math.exp(np.clip(-delta.y() / 130, -4, 4)))
        elif self.drag_kind == "Scroll" and abs(delta.y()) >= 6:
            self.scrolled.emit(self.plane, int(delta.y() / 6))
        elif self.drag_kind == "Crosshair":
            self.cursor_changed.emit(self.plane, point.x(), point.y())
        if self.drag_kind != "Scroll" or abs(delta.y()) >= 6:
            self.start_pos = pos

    def mouseReleaseEvent(self, event):
        if self.pending and self.drag_kind in ("Length", "Rectangle", "Ellipse", "Arrow"):
            point = self.pixel_at(event.position().toPoint())
            if (point - self.pending[0]).manhattanLength() > .5:
                self.marks.append(Mark(self.drag_kind, [self.pending[0], point], self.key))
            self.pending.clear()
            self.preview = None
        self.start_pos, self.drag_kind = None, None
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.pending.clear()
            self.preview = None
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for i in range(len(self.marks) - 1, -1, -1):
                if self.marks[i].key == self.key:
                    self.marks.pop(i)
                    break
        elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
                             Qt.Key.Key_Home, Qt.Key.Key_End):
            steps = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1, Qt.Key.Key_PageUp: -10,
                     Qt.Key.Key_PageDown: 10, Qt.Key.Key_Home: -1_000_000, Qt.Key.Key_End: 1_000_000}
            self.scrolled.emit(self.plane, steps[event.key()])
        else:
            super().keyPressEvent(event)
        self.viewport().update()

    def _orientation(self, dx, dy):
        if self.directions is None:
            return ""
        center = self.viewport().rect().center()
        a, b = self.pixel_at(center), self.pixel_at(center + type(center)(dx * 30, dy * 30))
        vector = (b.x() - a.x()) * np.asarray(self.directions[0]) + (b.y() - a.y()) * np.asarray(self.directions[1])
        if not np.isfinite(vector).all() or np.max(np.abs(vector)) == 0:
            return ""
        labels = [("R", "L"), ("A", "P"), ("I", "S")]
        return "".join(labels[i][int(vector[i] > 0)] for i in np.argsort(-np.abs(vector))
                       if abs(vector[i]) > np.max(np.abs(vector)) * .25)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.viewport().width(), self.viewport().height()
        accent = {"Source": "#77cbbc", "Axial": "#7ec8e3", "Coronal": "#80d7ad", "Sagittal": "#e5b677"}[self.plane]
        painter.setPen(QPen(QColor(accent if self.active else "#1b2938"), 2 if self.active else 1))
        painter.drawRect(1, 1, w - 2, h - 2)
        if self.show_overlays:
            font = painter.font()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(accent))
            painter.drawText(16, 26, self.title.upper())
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor("#94a6b9"))
            painter.drawText(16, 46, painter.fontMetrics().elidedText(self.subtitle, Qt.TextElideMode.ElideMiddle, w - 32))
            self._draw_file_information(painter, w, h)
            if self.image is not None:
                painter.drawText(16, h - 16, f"W {self.width:.0f}   L {self.level:.0f}" if self.image.ndim == 2 else "RGB")
                for dx, dy, rect in [(-1, 0, QRectF(7, h / 2 - 10, 35, 24)),
                    (1, 0, QRectF(w - 42, h / 2 - 10, 35, 24)),
                    (0, -1, QRectF(w / 2 - 20, 6, 40, 24)),
                    (0, 1, QRectF(w / 2 - 20, h - 31, 40, 24))]:
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._orientation(dx, dy))
        if self.image is None:
            painter.end()
            return
        if self.crosshair is not None and self.show_crosshair:
            point = self.screen_at(QPointF(*self.crosshair))
            painter.setPen(QPen(QColor(accent), 1, Qt.PenStyle.DashLine))
            painter.drawLine(point.x(), 55, point.x(), h - 35)
            painter.drawLine(45, point.y(), w - 45, point.y())
        self._draw_marks(painter, self.screen_at, include_pending=True)
        painter.end()

    def _draw_file_information(self, painter, width, height, standalone=False):
        painter.save()
        painter.setPen(QColor("#cad7df"))
        margin, line_height = 16, 18
        if standalone:
            font = painter.font()
            font.setPixelSize(max(6, min(12, width // 45)))
            painter.setFont(font)
            margin = max(3, min(16, width // 50))
            line_height = max(9, painter.fontMetrics().height() + 2)
        for side, lines in enumerate(self.file_information):
            available = max(1, width // 2 - margin * 2)
            x = margin if side == 0 else width // 2 + margin
            alignment = Qt.AlignmentFlag.AlignLeft if side == 0 else Qt.AlignmentFlag.AlignRight
            for i, text in enumerate(lines):
                y = (margin if standalone else (58 if side == 0 else 13)) + i * line_height
                if y + line_height > height - (margin if standalone else 55):
                    break
                text = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, available)
                text_width = min(available, painter.fontMetrics().horizontalAdvance(text) + 6)
                background_x = x if side == 0 else x + available - text_width
                painter.fillRect(QRectF(background_x - 2, y, text_width + 4, line_height), QColor(5, 10, 16, 170))
                painter.drawText(QRectF(x, y, available, line_height), alignment | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def _draw_marks(self, painter, map_point, include_pending=False):
        marks = [m for m in self.marks if m.key == self.key]
        if include_pending and self.pending and self.preview:
            marks.append(Mark(self.tool, self.pending + [self.preview], self.key))
        painter.setPen(QPen(QColor("#f5d48b"), 1.6))
        for mark in marks:
            points = [map_point(p) for p in mark.points]
            text = mark.label
            if mark.tool == "Text":
                pass
            elif len(points) >= 2:
                a, b = points[0], points[-1]
                if mark.tool in ("Rectangle", "Ellipse"):
                    rect = QRectF(a, b).normalized()
                    painter.drawEllipse(rect) if mark.tool == "Ellipse" else painter.drawRect(rect)
                    if mark.cached_label is None:
                        mark.cached_label = roi_statistics(self.image, mark.points[0], mark.points[-1], mark.tool == "Ellipse", self.spacing)
                    text = mark.cached_label
                    text = text.format(area_unit="mm²" if self.calibrated else "px²", unit=self.units)
                else:
                    for i in range(len(points) - 1):
                        painter.drawLine(points[i], points[i + 1])
                    if mark.tool == "Length":
                        p, q = mark.points[0], mark.points[-1]
                        length = math.hypot((p.x() - q.x()) * self.spacing[0], (p.y() - q.y()) * self.spacing[1])
                        text = f"{length:.2f} {'mm' if self.calibrated else 'px'}"
                    elif mark.tool == "Angle" and len(mark.points) == 3:
                        text = f"{angle_degrees(mark.points, self.spacing):.1f}°"
                    elif mark.tool == "Arrow":
                        angle = math.atan2(b.y() - a.y(), b.x() - a.x())
                        for offset in (-.5, .5):
                            painter.drawLine(b, b - type(b)(int(11 * math.cos(angle + offset)), int(11 * math.sin(angle + offset))))
            if text:
                anchor = points[-1]
                metrics, bounds = painter.fontMetrics(), painter.viewport()
                available = max(1, bounds.width() - 16)
                lines = [metrics.elidedText(line, Qt.TextElideMode.ElideRight, available) for line in text.splitlines()]
                text = "\n".join(lines)
                width = min(bounds.width(), max(metrics.horizontalAdvance(line) for line in lines) + 10)
                height = min(bounds.height(), metrics.height() * len(lines) + 6)
                x = max(bounds.left() + 2, min(anchor.x() + 8, bounds.right() - width - 2))
                y = max(bounds.top() + 2, min(anchor.y() + 4, bounds.bottom() - height - 2))
                box = QRectF(x, y, width, height)
                painter.fillRect(box, QColor(5, 10, 16, 210))
                painter.drawText(box.adjusted(5, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)

    def render_image(self, annotated=True, include_information=False):
        """Export the entire displayed image, independently of viewport guides and zoom/pan."""
        if self.image is None:
            return QImage()
        origin = self.viewportTransform().map(self.item.mapToScene(QPointF(0, 0)))
        u = self.viewportTransform().map(self.item.mapToScene(QPointF(1, 0))) - origin
        v = self.viewportTransform().map(self.item.mapToScene(QPointF(0, 1))) - origin
        unit = min(math.hypot(u.x(), u.y()), math.hypot(v.x(), v.y()))
        transform = QTransform(u.x() / unit, u.y() / unit, v.x() / unit, v.y() / unit, 0, 0)
        bounds = transform.mapRect(self.item.boundingRect())
        width, height = max(1, math.ceil(bounds.width() - 1e-7)), max(1, math.ceil(bounds.height() - 1e-7))
        if width * height > 100_000_000:
            raise ValueError("This image's physical aspect ratio exceeds the export size limit.")
        transform = QTransform(transform.m11(), transform.m12(), transform.m21(), transform.m22(), -bounds.left(), -bounds.top())
        output = QImage(width, height, QImage.Format.Format_RGB888)
        output.fill(QColor("black"))
        painter = QPainter(output)
        painter.setTransform(transform)
        painter.drawImage(QPointF(0, 0), self.item.pixmap().toImage())
        if annotated:
            for row, column, mask in self.overlay_layers:
                rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
                rgba[mask != 0] = (255, 240, 145, 220)
                layer = QImage(rgba.data, mask.shape[1], mask.shape[0], rgba.strides[0], QImage.Format.Format_RGBA8888).copy()
                painter.drawImage(QPointF(column, row), layer)
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        if annotated:
            self._draw_marks(painter, transform.map)
        if annotated and include_information:
            self._draw_file_information(painter, width, height, standalone=True)
        painter.end()
        return output
