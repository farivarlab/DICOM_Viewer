"""A scalar legend shared by image panes, volume rendering and PNG exports."""
from dataclasses import dataclass
import math

import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget, QSizePolicy

from .colors import lookup_table

BAR_WIDTH = 90


@dataclass
class ColorScale:
    colors: np.ndarray  # low-to-high RGB, using the renderer's actual mapping
    lower: float
    upper: float
    units: str = "value"
    threshold: bool = False


def window_scale(width, level, colormap, inverted=False, units="value", dicom=True):
    width = max(float(width), 1. if dicom else 1e-6)
    center = float(level) - (.5 if dicom else 0.)
    half_range = (width - 1. if dicom else width) / 2
    return ColorScale(lookup_table(colormap, inverted), center - half_range, center + half_range,
                      units, dicom and width == 1.)


def _gradient(scale):
    colors = scale.colors
    if scale.threshold:
        colors = np.vstack((np.repeat(colors[:1], 128, axis=0), np.repeat(colors[-1:], 128, axis=0)))
    pixels = np.ascontiguousarray(colors[::-1, None, :], dtype=np.uint8)
    return QImage(pixels.data, 1, len(pixels), pixels.strides[0], QImage.Format.Format_RGB888).copy()


def draw_colorbar(painter, rect, scale, gradient=None):
    painter.save()
    painter.setClipRect(rect)
    painter.fillRect(rect, QColor("#101010"))
    painter.translate(rect.topLeft())
    width, height = rect.width(), rect.height()
    font = QFont(painter.font())
    font.setPointSize(8 if height >= 100 else 6)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QColor("#dddddd"))
    metrics = painter.fontMetrics()
    line = metrics.height()
    title_height = line + 6 if height >= 45 else 0
    top, bottom = 6 + title_height + line / 2, height - 6 - line / 2
    bar_height = min(240., max(1., bottom - top))
    top += max(0., bottom - top - bar_height) / 2
    bar = QRectF(7, top, 12, bar_height)
    if title_height:
        title = {"value": "Value", "magnitude": "Magnitude"}.get(scale.units, scale.units)
        painter.drawText(QRectF(5, top - line - 13, width - 10, line), Qt.AlignmentFlag.AlignCenter,
                         metrics.elidedText(title, Qt.TextElideMode.ElideRight, int(width - 10)))
    painter.drawImage(bar, gradient if gradient is not None else _gradient(scale))
    painter.setPen(QPen(QColor("#808080"), 1))
    painter.drawRect(bar)
    count = 2 if scale.threshold or bar_height < 65 else (3 if bar_height < 140 else 5)
    for fraction in np.linspace(0, 1, count):
        value = scale.lower + fraction * (scale.upper - scale.lower)
        prefix = ("≤" if fraction == 0 else ">") if scale.threshold else ""
        for precision in (6, 5, 4, 3):
            text = prefix + f"{value:.{precision}g}"
            if metrics.horizontalAdvance(text) <= width - 28:
                break
        y = bar.bottom() - fraction * bar.height()
        painter.setPen(QColor("#b8b8b8"))
        painter.drawLine(QRectF(bar.right(), y, 4, 0).topLeft(), QRectF(bar.right(), y, 4, 0).topRight())
        painter.setPen(QColor("#dddddd"))
        painter.drawText(QRectF(25, y - line / 2, width - 28, line),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         text)
    painter.restore()


def append_colorbar(image, scale, pixel_scale=1.):
    extra = math.ceil(BAR_WIDTH * pixel_scale)
    if (image.width() + extra) * image.height() > 100_000_000:
        raise ValueError("The image and colorbar exceed the PNG export size limit.")
    output = QImage(image.width() + extra, image.height(), QImage.Format.Format_RGB888)
    painter = QPainter(output)
    painter.drawImage(0, 0, image)
    painter.translate(image.width(), 0)
    painter.scale(pixel_scale, pixel_scale)
    draw_colorbar(painter, QRectF(0, 0, extra / pixel_scale, image.height() / pixel_scale), scale)
    painter.end()
    return output


class ColorBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(BAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.scale = None
        self.gradient = None
        self._window_key = None

    def set_window(self, width, level, colormap, inverted, units, dicom):
        key = (width, level, colormap, inverted, units, dicom)
        if key != self._window_key:
            self._window_key = key
            self.set_scale(window_scale(*key))

    def set_scale(self, scale):
        self.scale = scale
        self.gradient = _gradient(scale)
        self.update()

    def paintEvent(self, event):
        if self.scale is not None:
            painter = QPainter(self)
            draw_colorbar(painter, QRectF(self.rect()), self.scale, self.gradient)
            painter.end()

    def mousePressEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()
