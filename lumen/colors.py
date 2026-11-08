"""Small lookup tables, without a plotting-library dependency in the viewer."""
import numpy as np
from functools import lru_cache

STOPS = {
    "Grayscale": [(0, 0, 0), (255, 255, 255)],
    "Bone": [(0, 0, 0), (65, 76, 89), (153, 178, 180), (255, 255, 255)],
    "Hot iron": [(0, 0, 0), (130, 0, 20), (240, 75, 0), (255, 210, 40), (255, 255, 255)],
    "Viridis": [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)],
    "Magma": [(0, 0, 4), (81, 18, 124), (183, 55, 121), (252, 137, 97), (252, 253, 191)],
    "Cool": [(0, 255, 255), (255, 0, 255)],
    "Rainbow": [(20, 0, 100), (0, 60, 255), (0, 220, 200), (160, 255, 0), (255, 180, 0), (180, 0, 0)],
}


@lru_cache(maxsize=14)
def lookup_table(name: str, inverted: bool = False) -> np.ndarray:
    stops = np.asarray(STOPS.get(name, STOPS["Grayscale"]), dtype=float)
    points = np.linspace(0, 1, len(stops))
    lut = np.column_stack([np.interp(np.linspace(0, 1, 256), points, stops[:, i]) for i in range(3)])
    lut = np.round(lut).astype(np.uint8)
    return lut[::-1].copy() if inverted else lut


def window_pixels(pixels: np.ndarray, width: float, level: float, dicom: bool = True) -> np.ndarray:
    """DICOM LINEAR windowing, or a continuous scalar window for NIfTI."""
    if not dicom:
        values = (np.asarray(pixels, dtype=np.float32) - level) / max(float(width), 1e-6) + .5
        return (np.clip(values, 0, 1) * 255).astype(np.uint8)
    width = max(float(width), 1.0)
    if width == 1:
        return np.where(pixels > level - 0.5, 255, 0).astype(np.uint8)
    values = (np.asarray(pixels, dtype=np.float32) - (level - 0.5)) / (width - 1) + 0.5
    return (np.clip(values, 0, 1) * 255).astype(np.uint8)
