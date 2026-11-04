"""DICOM indexing, pixel decoding and patient-coordinate volume geometry.

Array convention: [slice, row, column]. Patient coordinates: DICOM LPS, mm.
No image is uploaded, and input datasets are never modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import math

import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.fileset import FileSet
from pydicom.pixels import apply_modality_lut, apply_color_lut
from scipy.ndimage import affine_transform

Progress = Callable[[str], None]
MAX_VOXELS = 100_000_000
MAX_WINDOW_SAMPLES = 2_000_000


def first_number(value, fallback: float) -> float:
    try:
        if not isinstance(value, (str, bytes)) and hasattr(value, "__len__"):
            value = value[0]
        result = float(value)
        return result if math.isfinite(result) else fallback
    except (TypeError, ValueError, IndexError):
        return fallback


def functional(ds: Dataset, frame: int, sequence: str, attribute: str, default=None):
    for group, index in ((getattr(ds, "PerFrameFunctionalGroupsSequence", []), frame),
                         (getattr(ds, "SharedFunctionalGroupsSequence", []), 0)):
        if 0 <= index < len(group):
            item = group[index]
            items = getattr(item, sequence, [])
            if items and hasattr(items[0], attribute):
                return getattr(items[0], attribute)
    return getattr(ds, attribute, default)


def _vector(value, length):
    try:
        result = np.asarray(value, dtype=float)
        return result if result.shape == (length,) and np.isfinite(result).all() else None
    except (TypeError, ValueError):
        return None


def _pixel_spacing(value):
    result = _vector(value, 2)
    return result if result is not None and np.all(result > 0) else None


def _auto_window(pixels):
    array = np.asarray(pixels)
    stride = max(1, math.ceil(array.size / MAX_WINDOW_SAMPLES))
    # Do not flatten-copy an entire non-contiguous volume just to sample it.
    sample = array.reshape(-1)[::stride] if array.flags.c_contiguous else array.flat[::stride]
    finite = sample[np.isfinite(sample)]
    if finite.size == 0:
        return 1., 0.
    lo, hi = np.percentile(finite, (1, 99))
    if hi <= lo:
        # A small foreground can occupy less than one percent of a mostly blank stack.
        # Avoid a threshold window when the sampled series still has a real range.
        lo, hi = finite.min(), finite.max()
    return max(1., float(hi - lo)), float((lo + hi) / 2)


def _units(ds, frame):
    unit = str(functional(ds, frame, "PixelValueTransformationSequence", "RescaleType", "")).strip()
    if unit:
        return unit
    if str(getattr(ds, "Modality", "")) == "CT" and functional(
            ds, frame, "PixelValueTransformationSequence", "RescaleIntercept") is not None:
        return "HU"
    return "value"


@dataclass
class FileInfo:
    path: Path
    frames: int = 1
    instance: int = 0


@dataclass(frozen=True)
class FrameReference:
    path: Path | None
    frame: int = 0


@dataclass
class Series:
    uid: str
    description: str
    patient: str
    study: str
    modality: str
    date: str
    paths: list[Path] = field(default_factory=list)
    frames: int = 0
    patient_id: str = ""
    patient_issuer: str = ""
    study_uid: str = ""
    accession: str = ""
    files: dict[Path, FileInfo] = field(default_factory=dict)

    @property
    def title(self):
        return f"{self.modality}  ·  {self.description}"


@dataclass
class ScanResult:
    series: list[Series]
    skipped: int


def scan_paths(paths: list[Path], progress: Progress = lambda _: None) -> ScanResult:
    candidates: set[Path] = set()
    for path in paths:
        if path.is_dir():
            for i, item in enumerate(path.rglob("*")):
                if i % 128 == 0:
                    progress(f"Scanning folder · {len(candidates):,} files found")
                if item.is_file():
                    candidates.add(item)
        elif path.name.upper() == "DICOMDIR":
            candidates.update(Path(instance.path) for instance in FileSet(path))
        elif path.is_file():
            candidates.add(path)
    groups: dict[str, Series] = {}
    skipped = 0
    for index, path in enumerate(sorted(candidates)):
        if index % 25 == 0:
            progress(f"Indexing files · {index + 1:,} / {len(candidates):,}")
        try:
            # force allows older datasets without the Part 10 preamble; require image tags below.
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
            if not all(hasattr(ds, tag) for tag in ("Rows", "Columns", "SOPClassUID", "SeriesInstanceUID")):
                skipped += 1
                continue
            uid = str(ds.SeriesInstanceUID)
            if uid not in groups:
                groups[uid] = Series(uid, str(getattr(ds, "SeriesDescription", "Untitled series")),
                    str(getattr(ds, "PatientName", "Unknown patient")).replace("^", " "),
                    str(getattr(ds, "StudyDescription", "DICOM study")),
                    str(getattr(ds, "Modality", "OT")), str(getattr(ds, "StudyDate", "")))
                groups[uid].patient_id = str(getattr(ds, "PatientID", ""))
                groups[uid].patient_issuer = str(getattr(ds, "IssuerOfPatientID", ""))
                groups[uid].study_uid = str(getattr(ds, "StudyInstanceUID", ""))
                groups[uid].accession = str(getattr(ds, "AccessionNumber", ""))
            groups[uid].paths.append(path)
            count = int(getattr(ds, "NumberOfFrames", 1))
            groups[uid].frames += count
            groups[uid].files[path] = FileInfo(path, count, int(first_number(getattr(ds, "InstanceNumber", 0), 0)))
        except (OSError, ValueError, EOFError, AttributeError, TypeError):
            skipped += 1
    return ScanResult(sorted(groups.values(), key=lambda s: (s.patient, s.date, s.description)), skipped)


@dataclass
class ImageVolume:
    source: np.ndarray
    dataset: Dataset
    series: Series
    spacing: tuple[float, float, float]  # native column, row, slice spacing
    affine: np.ndarray
    width: float
    level: float
    inverted: bool
    calibrated: bool
    canonical: np.ndarray | None = None
    canonical_spacing: tuple[float, float, float] = (1, 1, 1)
    canonical_origin: tuple[float, float, float] = (0, 0, 0)
    geometry_note: str = ""
    is_color: bool = False
    units: str = "value"
    references: list[FrameReference] = field(default_factory=list)
    headers: dict[Path, Dataset] = field(default_factory=dict)
    dicom_overlays: dict[Path, list[tuple[int, int, int, np.ndarray]]] = field(default_factory=dict)
    path_aliases: dict[Path, Path] = field(default_factory=dict)
    _mpr_valid: bool = False
    _window_cache: dict[int, tuple[float, float]] = field(default_factory=dict, repr=False)
    _series_window: tuple[float, float] | None = field(default=None, repr=False)

    def reference(self, index: int) -> FrameReference:
        return self.references[index] if self.references else FrameReference(None, index)

    def header(self, index: int) -> Dataset:
        return self.headers.get(self.reference(index).path, self.dataset)

    def frame_calibrated(self, index: int) -> bool:
        ref = self.reference(index)
        spacing = functional(self.header(index), ref.frame, "PixelMeasuresSequence", "PixelSpacing")
        return _pixel_spacing(spacing) is not None

    def frame_spacing(self, index: int) -> tuple[float, float]:
        ref = self.reference(index)
        spacing = _pixel_spacing(functional(self.header(index), ref.frame, "PixelMeasuresSequence", "PixelSpacing"))
        return (float(spacing[1]), float(spacing[0])) if spacing is not None else (1., 1.)

    def frame_units(self, index: int) -> str:
        if self.is_color:
            return "RGB"
        if not self.references:
            return self.units
        return _units(self.header(index), self.reference(index).frame)

    def frame_window(self, index: int) -> tuple[float, float]:
        if index not in self._window_cache:
            ref, ds = self.reference(index), self.header(index)
            width = first_number(functional(ds, ref.frame, "FrameVOILUTSequence", "WindowWidth"), float("nan"))
            level = first_number(functional(ds, ref.frame, "FrameVOILUTSequence", "WindowCenter"), float("nan"))
            if not math.isfinite(width) or not math.isfinite(level):
                auto_width, auto_level = self.series_window()
                width = width if math.isfinite(width) else auto_width
                level = level if math.isfinite(level) else auto_level
            self._window_cache[index] = (max(1., width), level)
        return self._window_cache[index]

    def series_window(self) -> tuple[float, float]:
        """A stable fallback for images without DICOM window settings."""
        if self._series_window is None:
            self._series_window = _auto_window(self.source)
        return self._series_window

    def frame_inverted(self, index: int) -> bool:
        return str(getattr(self.header(index), "PhotometricInterpretation", "")) == "MONOCHROME1"

    def overlay_layers(self, index: int):
        ref = self.reference(index)
        layers = []
        for row, column, first_frame, pixels in self.dicom_overlays.get(ref.path, []):
            frame = ref.frame + 1 - first_frame
            if pixels.ndim == 2 and frame == 0:
                layers.append((row, column, pixels))
            elif pixels.ndim == 3 and 0 <= frame < len(pixels):
                layers.append((row, column, pixels[frame]))
        return layers

    @property
    def mpr_ready(self) -> bool:
        return self.canonical is not None

    @property
    def mpr_available(self) -> bool:
        return self.mpr_ready or self._mpr_valid

    def prepare_mpr(self, progress: Progress = lambda _: None) -> ImageVolume:
        if self.mpr_ready:
            return self
        if not self.mpr_available:
            raise ValueError(self.geometry_note)
        canonical, spacing, origin = _canonicalize(self.source, self.affine, progress)
        self.canonical, self.canonical_spacing, self.canonical_origin = canonical, spacing, origin
        return self

    def plane(self, name: str, cursor: list[int], source_index: int = 0,
              slab_mode: str = "Slice", slab_mm: float = 1) -> tuple[np.ndarray, tuple[float, float]]:
        if name == "Source":
            return self.source[source_index], self.frame_spacing(source_index)
        a = self.canonical
        if a is None:
            raise ValueError(self.geometry_note)
        x, y, z = cursor
        axis, index = {"Axial": (0, z), "Coronal": (1, y), "Sagittal": (2, x)}[name]
        spacing = self.canonical_spacing[2 - axis]
        if slab_mode != "Slice":
            radius = max(0, round((slab_mm / spacing - 1) / 2))
            selection = [slice(None)] * 3
            selection[axis] = slice(max(0, index - radius), min(a.shape[axis], index + radius + 1))
            reducer = {"MIP": np.max, "MinIP": np.min, "Average": np.mean}[slab_mode]
            image = reducer(a[tuple(selection)], axis=axis)
        else:
            image = np.take(a, index, axis=axis)
        sx, sy, sz = self.canonical_spacing
        if name == "Axial":
            return image, (sx, sy)
        return image[::-1], (sx if name == "Coronal" else sy, sz)

    def pixel_to_cursor(self, plane: str, u: float, v: float, cursor: list[int]) -> list[int]:
        result = cursor.copy()
        nz, ny, nx = self.canonical.shape
        u, v = int(round(u)), int(round(v))
        if plane == "Axial":
            result[0], result[1] = np.clip(u, 0, nx - 1), np.clip(v, 0, ny - 1)
        elif plane == "Coronal":
            result[0], result[2] = np.clip(u, 0, nx - 1), np.clip(nz - 1 - v, 0, nz - 1)
        else:
            result[1], result[2] = np.clip(u, 0, ny - 1), np.clip(nz - 1 - v, 0, nz - 1)
        return [int(i) for i in result]


def _canonicalize(source: np.ndarray, affine: np.ndarray, progress: Progress):
    shape_xyz = np.array(source.shape[::-1])
    corners = np.array([[x, y, z, 1] for x in (0, shape_xyz[0] - 1)
                       for y in (0, shape_xyz[1] - 1) for z in (0, shape_xyz[2] - 1)])
    world = (affine @ corners.T).T[:, :3]
    low, high = world.min(axis=0), world.max(axis=0)
    # Preserve native anisotropic spacing for aligned scans; use the finest spacing for oblique scans.
    basis = affine[:3, :3]
    norms = np.linalg.norm(basis, axis=0)
    direction = basis / norms
    axes = np.argmax(np.abs(direction), axis=0)
    aligned = len(set(axes)) == 3 and np.allclose(np.abs(direction), np.eye(3)[:, axes], atol=1e-6, rtol=0)
    spacing = np.full(3, norms.min())
    if aligned:
        for i in range(3):
            spacing[np.argmax(np.abs(direction[:, i]))] = norms[i]
    shape = np.maximum(1, np.ceil((high - low) / spacing - 1e-5).astype(int) + 1)
    if aligned and np.prod(shape.astype(float)) <= MAX_VOXELS:
        # Ordinary orthogonal stacks need only axis permutation/reversal, not a second volume.
        input_axes = [2 - int(np.flatnonzero(axes == world_axis)[0]) for world_axis in (2, 1, 0)]
        output = source.transpose(input_axes)
        slices = tuple(slice(None, None, -1) if direction[world_axis, 2 - input_axis] < 0 else slice(None)
                       for world_axis, input_axis in zip((2, 1, 0), input_axes))
        return output[slices], tuple(spacing), tuple(low)
    if np.prod(shape.astype(float)) > MAX_VOXELS:
        spacing *= (np.prod(shape.astype(float)) / MAX_VOXELS) ** (1 / 3) * 1.01
        shape = np.maximum(1, np.ceil((high - low) / spacing).astype(int) + 1)
    target = np.eye(4)
    target[:3, :3] = np.diag(spacing)
    target[:3, 3] = low
    mapping = np.linalg.inv(affine) @ target
    reverse = np.eye(3)[::-1]
    progress("Reconstructing patient-coordinate volume…")
    minimum = float(np.nanmin(source))
    output = affine_transform(source, reverse @ mapping[:3, :3] @ reverse,
        reverse @ mapping[:3, 3], output_shape=tuple(int(n) for n in shape[::-1]),
        output=np.float32, order=1, mode="constant", cval=minimum if math.isfinite(minimum) else 0., prefilter=False)
    return output, tuple(spacing), tuple(low)


def load_series(series: Series, progress: Progress = lambda _: None, reconstruct: bool = True) -> ImageVolume:
    frames = []
    first = None
    seen = {}
    expected = None
    estimated = 0
    headers, overlays, aliases = {}, {}, {}
    for file_index, path in enumerate(series.paths):
        progress(f"Decoding images · {file_index + 1} / {len(series.paths)}")
        ds = pydicom.dcmread(path, force=True, defer_size=1024 * 1024)
        uid = str(getattr(ds, "SOPInstanceUID", path))
        if uid in seen:
            aliases[path] = seen[uid]
            continue
        seen[uid] = path
        count = int(getattr(ds, "NumberOfFrames", 1))
        if count < 1 or int(ds.Rows) < 1 or int(ds.Columns) < 1:
            raise ValueError(f"{path.name} declares invalid image dimensions or frame count.")
        estimated += int(ds.Rows) * int(ds.Columns) * count * int(getattr(ds, "SamplesPerPixel", 1))
        if estimated > MAX_VOXELS * 2:
            raise ValueError("This series exceeds the 200-million-sample memory limit. Open a smaller series.")
        # Keep per-file metadata without retaining a second copy of the pixel stream.
        headers[path] = Dataset({tag: ds[tag] for tag in ds.keys()
            if tag not in ((0x7FE0, 0x0010), (0x7FE0, 0x0008), (0x7FE0, 0x0009))
            and not (0x6000 <= tag.group <= 0x601E and tag.element == 0x3000)})
        if hasattr(ds, "file_meta"):
            headers[path].file_meta = ds.file_meta
        layers = []
        for group in range(0x6000, 0x6020, 2):
            if (group, 0x3000) in ds:
                try:
                    origin = ds.get((group, 0x0050))
                    row, column = [int(v) - 1 for v in origin.value] if origin else (0, 0)
                    first_frame = ds.get((group, 0x0051))
                    layers.append((row, column, int(first_frame.value) if first_frame else 1, ds.overlay_array(group)))
                except (ValueError, AttributeError, NotImplementedError):
                    pass
        overlays[path] = layers
        try:
            decoded = ds.pixel_array
            if str(getattr(ds, "PhotometricInterpretation", "")) == "PALETTE COLOR":
                decoded = apply_color_lut(decoded, ds)
                if decoded.dtype == np.uint16:
                    decoded = (decoded / 257).astype(np.uint8)
        except Exception as exc:
            raise ValueError(f"Could not decode {path.name}. The transfer syntax may require an additional codec.\n{exc}") from exc
        color = decoded.ndim == (4 if count > 1 else 3)
        if count == 1:
            decoded = decoded[None]
        for i, raw in enumerate(decoded):
            if expected is None:
                expected = raw.shape
            if raw.shape != expected:
                raise ValueError("The series contains different image dimensions. Split it into consistent stacks first.")
            if color:
                if raw.dtype.itemsize > 1:
                    maximum = 2 ** int(getattr(ds, "BitsStored", 16)) - 1
                    pixels = np.round(np.clip(raw.astype(np.float32) / maximum, 0, 1) * 255).astype(np.uint8)
                else:
                    pixels = np.asarray(raw, dtype=np.uint8)
            elif hasattr(ds, "ModalityLUTSequence"):
                pixels = apply_modality_lut(raw, ds).astype(np.float32)
            else:
                slope = first_number(functional(ds, i, "PixelValueTransformationSequence", "RescaleSlope", 1), 1)
                intercept = first_number(functional(ds, i, "PixelValueTransformationSequence", "RescaleIntercept", 0), 0)
                pixels = np.multiply(raw, slope, dtype=np.float32)
                np.add(pixels, intercept, out=pixels)
            position = functional(ds, i, "PlanePositionSequence", "ImagePositionPatient")
            orientation = functional(ds, i, "PlaneOrientationSequence", "ImageOrientationPatient")
            spacing = functional(ds, i, "PixelMeasuresSequence", "PixelSpacing")
            # A top-level position on a multi-frame cine is not per-frame spatial geometry.
            if count > 1 and not getattr(ds, "PerFrameFunctionalGroupsSequence", None):
                position = None
            frames.append((pixels, position, orientation, spacing,
                           first_number(getattr(ds, "InstanceNumber", file_index), file_index), i,
                           FrameReference(path, i)))
    if not frames:
        raise ValueError("No decodable images were found.")
    orientations = [_vector(frame[2], 6) for frame in frames]
    positions_valid = [_vector(frame[1], 3) for frame in frames]
    spacings = [_pixel_spacing(frame[3]) for frame in frames]
    orientation = orientations[0]
    affine = np.eye(4)
    note = "MPR requires at least two spatial slices with consistent patient geometry."
    spatial = len(frames) > 1 and all(value is not None for value in (*orientations, *positions_valid, *spacings))
    if len(frames) > 1 and not spatial and any(frame[1] is not None for frame in frames):
        note = "Missing or invalid patient geometry; MPR is unavailable."
    if spatial:
        direction = orientation
        row, column = direction[:3], direction[3:]
        normal = np.cross(row, column)
        if not np.isclose(np.linalg.norm(row), 1, atol=1e-3) or not np.isclose(np.linalg.norm(column), 1, atol=1e-3) or not np.isclose(np.dot(row, column), 0, atol=1e-3):
            spatial, note = False, "Invalid image orientation; MPR is unavailable."
        elif not all(np.allclose(value, direction, atol=1e-4) for value in orientations) or not all(np.allclose(value, spacings[0], atol=1e-4) for value in spacings):
            spatial, note = False, "Mixed orientations or pixel spacing; MPR is unavailable for this series."
        else:
            frames.sort(key=lambda f: np.dot(f[1], normal))
            positions = np.asarray([f[1] for f in frames], float)
            steps = np.diff(positions, axis=0)
            step = np.median(steps, axis=0)
            distance = float(np.dot(step, normal))
            if distance < 1e-4:
                spatial, note = False, "Repeated slice positions (possibly temporal or multi-echo data); MPR is unavailable."
            elif not np.allclose(steps, step, atol=max(0.05, distance * 0.02), rtol=0):
                spatial, note = False, "Irregular slice spacing or missing slices; MPR is unavailable."
            else:
                affine[:3, 0] = row * float(frames[0][3][1])
                affine[:3, 1] = column * float(frames[0][3][0])
                affine[:3, 2] = step  # includes gantry tilt
                affine[:3, 3] = positions[0]
    if not spatial:
        frames.sort(key=lambda f: (f[4], f[5]))
    if spatial and len({_units(headers[f[6].path], f[6].frame) for f in frames}) > 1:
        spatial, note = False, "Mixed physical value units; MPR is unavailable for this series."
    first_reference = frames[0][6]
    first = headers[first_reference.path]
    pixel_spacing = _pixel_spacing(frames[0][3])
    calibrated = pixel_spacing is not None
    sx, sy = (float(pixel_spacing[1]), float(pixel_spacing[0])) if calibrated else (1, 1)
    sz = float(np.linalg.norm(affine[:3, 2])) if spatial else max(0.001, first_number(getattr(first, "SliceThickness", 1), 1))
    source = np.stack([f[0] for f in frames]) if len(frames) > 1 else frames[0][0][None]
    is_color = source.ndim == 4
    units = _units(first, first_reference.frame)
    result = ImageVolume(source, first, series, (sx, sy, sz), affine, 1., 0.,
        str(getattr(first, "PhotometricInterpretation", "")) == "MONOCHROME1", calibrated,
        geometry_note=note, is_color=is_color, units=units,
        references=[f[6] for f in frames], headers=headers, dicom_overlays=overlays,
        path_aliases=aliases, _mpr_valid=spatial and not is_color)
    result.width, result.level = result.frame_window(0)
    if spatial and not is_color:
        result.geometry_note = "Patient LPS coordinates · orthogonal MPR"
        if reconstruct:
            result.prepare_mpr(progress)
    elif is_color:
        result.geometry_note = "Color images support 2D viewing; MPR and volume rendering require a scalar volume."
    return result


def demo_volume() -> ImageVolume:
    """Generated phantom, deliberately asymmetric to make orientation mistakes visible."""
    nz, ny, nx = 112, 144, 144
    z, y, x = np.mgrid[-1:1:complex(nz), -1:1:complex(ny), -1:1:complex(nx)]
    body = (x / 0.78) ** 2 + (y / 0.64) ** 2 + (z / 1.35) ** 2 < 1
    a = np.full((nz, ny, nx), -1000, np.float32)
    a[body] = 35 + 15 * np.sin(x[body] * 16) * np.cos(z[body] * 13)
    for side in (-1, 1):
        lung = ((x - side * .3) / .23) ** 2 + ((y + .07) / .37) ** 2 + ((z - .12) / .72) ** 2 < 1
        a[lung] = -780 + 70 * np.sin(y[lung] * 25)
        ribs = (np.abs(np.sin(z * 30)) > .86) & (np.abs(((x - side * .27) / .36) ** 2 + (y / .47) ** 2 - 1) < .12) & body
        a[ribs] = 950
    spine = (x / .09) ** 2 + ((y - .35) / .1) ** 2 < 1
    a[spine & body] = 1100
    heart = ((x + .1) / .22) ** 2 + ((y - .02) / .22) ** 2 + ((z + .3) / .38) ** 2 < 1
    a[heart] = 95
    vessel = ((x - .14) / .045) ** 2 + ((y - .2) / .045) ** 2 < 1
    a[vessel & body] = 330
    series = Series("demo", "Thorax phantom", "Synthetic phantom", "Generated demonstration", "CT", "", frames=nz)
    ds = Dataset()
    ds.PatientName = "Synthetic^Phantom"
    ds.SeriesDescription = series.description
    ds.Modality = "CT"
    ds.WindowWidth, ds.WindowCenter = 400, 40
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [1.8, 1.8]
    affine = np.diag([1.8, 1.8, 2.4, 1.])
    affine[:3, 3] = (-129, -129, -134)
    return ImageVolume(a, ds, series, (1.8, 1.8, 2.4), affine, 400, 40, False, True,
        a, (1.8, 1.8, 2.4), (-129, -129, -134), "Generated phantom · no patient data", units="HU")
