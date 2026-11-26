"""Animated GIF export of rendered frames, using Pillow only."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
from PySide6.QtGui import QImage

MAX_FRAMES = 600


def movie_positions(count: int) -> list[int]:
    """Every position, or MAX_FRAMES evenly spaced ones for very long sequences."""
    if count <= MAX_FRAMES:
        return list(range(count))
    return sorted(set(np.linspace(0, count - 1, MAX_FRAMES).round().astype(int).tolist()))


def qimage_array(image: QImage) -> np.ndarray:
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    return rows[:, :image.width() * 3].reshape(image.height(), image.width(), 3).copy()


def save_gif(frames: list[np.ndarray], path: Path, fps: float):
    """Write *frames* (RGB arrays) as a looping GIF; smaller frames are centred on black."""
    if not frames:
        raise ValueError("There are no frames to save.")
    height = max(frame.shape[0] for frame in frames)
    width = max(frame.shape[1] for frame in frames)
    canvases = []
    for frame in frames:
        canvas = np.zeros((height, width, 3), np.uint8)
        top, left = (height - frame.shape[0]) // 2, (width - frame.shape[1]) // 2
        canvas[top:top + frame.shape[0], left:left + frame.shape[1]] = frame
        canvases.append(canvas)
    # One palette for the whole movie keeps colours steady between frames; per-frame
    # palettes also let the GIF writer mistake differently coloured frames for repeats.
    stride = max(1, len(canvases) // 32)
    sample = np.concatenate([c[::4, ::4] for c in canvases[::stride]], axis=0)
    palette = Image.fromarray(sample).quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    images = [Image.fromarray(c).quantize(palette=palette, dither=Image.Dither.NONE) for c in canvases]
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".lumen-movie-", suffix=".gif", dir=path.parent)
    os.close(fd)
    try:
        images[0].save(temporary, format="GIF", save_all=True, append_images=images[1:],
                       duration=max(20, round(1000 / max(fps, 1))), loop=0)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
