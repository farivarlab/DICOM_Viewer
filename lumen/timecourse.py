"""A compact line plot of one voxel across the volumes of a 4D image."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class TimeCourse(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.values = None
        self.current = 0
        self.caption = "Hover over the image to plot a voxel"

    def set_values(self, values, current, caption):
        self.values = None if values is None else np.asarray(values, float)
        self.current, self.caption = current, caption
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), QColor("#101010"))
        text = QColor("#cfcfcf")
        painter.setPen(text)
        metrics = painter.fontMetrics()
        line = metrics.height()
        painter.drawText(QRectF(6, 3, self.width() - 12, line), Qt.AlignmentFlag.AlignLeft,
                         metrics.elidedText(self.caption, Qt.TextElideMode.ElideRight, self.width() - 12))
        values = self.values
        if values is None or values.size < 2:
            painter.end()
            return
        plot = QRectF(6, line + 8, self.width() - 12, self.height() - 2 * line - 14)
        low, high = float(values.min()), float(values.max())
        span = high - low or 1.
        x = plot.left() + np.arange(values.size) / (values.size - 1) * plot.width()
        y = plot.bottom() - (values - low) / span * plot.height()
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.drawRect(plot)
        if 0 <= self.current < values.size:
            painter.setPen(QPen(palette.highlight().color(), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x[self.current], plot.top()), QPointF(x[self.current], plot.bottom()))
        path = QPainterPath(QPointF(x[0], y[0]))
        for px, py in zip(x[1:], y[1:]):
            path.lineTo(px, py)
        painter.setPen(QPen(QColor("#f5d48b"), 1.4))
        painter.drawPath(path)
        painter.setPen(text)
        painter.drawText(QRectF(6, plot.bottom() + 2, self.width() - 12, line), Qt.AlignmentFlag.AlignLeft,
                         f"{low:.4g} – {high:.4g}")
        painter.drawText(QRectF(6, plot.bottom() + 2, self.width() - 12, line), Qt.AlignmentFlag.AlignRight,
                         f"{values.size} volumes")
        painter.end()
