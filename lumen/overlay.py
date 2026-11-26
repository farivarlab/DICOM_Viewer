"""Registered overlays: a second volume sampled on the displayed pixel grid.

Both images are aligned through patient LPS coordinates, never through array
indices, so an overlay may have its own size, spacing and orientation. Pixel
(row, column) of a displayed image is sampled at its centre, which is the
voxel index itself in the volume's affine.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import map_coordinates

from .colors import lookup_table

MAX_RANGE_SAMPLES = 2_000_000


def has_geometry(data) -> bool:
    """True when every source voxel has a known patient position."""
    if data is None or data.is_color:
        return False
    return data.mpr_available or data.series.source_format == "NIfTI"


def source_points(data, index: int, shape) -> np.ndarray:
    """Patient coordinates (3, rows * columns) of source image *index*."""
    rows, columns = shape
    y, x = np.mgrid[:rows, :columns]
    voxels = np.stack([x.ravel(), y.ravel(), np.full(x.size, index)]).astype(float)
    return data.affine[:3, :3] @ voxels + data.affine[:3, 3:4]


def plane_points(data, plane: str, cursor, shape) -> np.ndarray:
    """Patient coordinates (3, rows * columns) of a reconstructed plane, as ImageVolume.plane lays it out."""
    nz = data.canonical.shape[0]
    rows, columns = shape
    r, c = np.mgrid[:rows, :columns]
    x, y, z = cursor
    if plane == "Axial":
        grid = (c, r, np.full_like(r, z))
    elif plane == "Coronal":
        grid = (c, np.full_like(r, y), nz - 1 - r)
    else:
        grid = (np.full_like(r, x), c, nz - 1 - r)
    voxels = np.stack([axis.ravel() for axis in grid]).astype(float)
    return np.asarray(data.canonical_origin, float)[:, None] + voxels * np.asarray(data.canonical_spacing, float)[:, None]


def sample(overlay, world: np.ndarray, shape, nearest=False) -> np.ndarray:
    """Overlay values at patient coordinates; NaN outside the overlay."""
    inverse = np.linalg.inv(overlay.affine)
    index = (inverse[:3, :3] @ world + inverse[:3, 3:4])[::-1]  # (slice, row, column)
    # Each voxel covers half a voxel around its centre, like a displayed pixel, so edge
    # voxels survive rounding error; anything further out is outside the overlay.
    limits = np.asarray(overlay.source.shape, float)[:, None] - .5
    outside = np.any((index < -.5) | (index > limits), axis=0)
    values = map_coordinates(overlay.source, index, order=0 if nearest else 1, mode="nearest",
                             output=np.float32, prefilter=False)
    values[outside] = np.nan
    return values.reshape(shape)


def default_range(overlay) -> tuple[float, float, bool]:
    """(low, high, is_label_map) for a first display of *overlay*.

    Label maps show every label. Continuous maps start at their median non-zero
    value, so a statistical map or a second scan does not cover the whole image.
    """
    values = np.asarray(overlay.source).reshape(-1)
    values = values[::max(1, values.size // MAX_RANGE_SAMPLES)]
    values = values[np.isfinite(values) & (values != 0)]
    if values.size == 0:
        return 0., 1., False
    labels = bool(np.all(values == np.round(values))) and np.unique(values).size <= 256
    if labels:
        low, high = float(values.min()), float(values.max())
    else:
        low, high = (float(v) for v in np.percentile(values, (50, 99)))
    return low, max(high, low + 1e-6), labels


def colorize(values: np.ndarray, low: float, high: float, colormap: str,
             opacity: float, hide_below=True) -> np.ndarray:
    """RGBA pixels; values outside the overlay, and below *low* when hidden, are transparent."""
    lut = lookup_table(colormap)
    # A map that starts at black would hide the lowest shown values against the
    # image, so overlays begin a quarter of the way into such maps.
    start = 64 if int(lut[0].max()) < 40 else 0
    scaled = np.clip((values - low) / max(high - low, 1e-12), 0, 1)
    index = np.nan_to_num(start + scaled * (255 - start), nan=0).astype(np.uint8)
    rgba = np.empty((*values.shape, 4), np.uint8)
    rgba[..., :3] = lut[index]
    visible = np.isfinite(values)
    if hide_below:
        visible &= values >= low
    rgba[..., 3] = np.where(visible, round(float(np.clip(opacity, 0, 1)) * 255), 0)
    return rgba
