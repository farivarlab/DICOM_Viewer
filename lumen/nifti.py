"""NIfTI viewing with NiBabel and DICOM conversion with dcm2niix.

Viewer geometry is LPS; NIfTI world geometry is RAS+. No presentation annotations
or window/level operations are baked into exported volume data.
"""
from pathlib import Path
import hashlib
from contextlib import suppress
import os
import shutil
import subprocess
import tempfile
import time

import nibabel as nib
import numpy as np
from pydicom.dataset import Dataset

from .model import (Series, FileInfo, FrameReference, ImageVolume, ScanResult,
                    MAX_VOXELS, scan_paths)

RAS_LPS = np.diag([-1., -1., 1., 1.])


def is_nifti(path):
    return str(path).lower().endswith((".nii", ".nii.gz"))


def _key(path):
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]


def _shape(image):
    shape = image.shape
    if not 2 <= len(shape) <= 4 or any(n < 1 for n in shape):
        raise ValueError("NIfTI viewing supports 2D, 3D, and 4D scalar images.")
    if np.prod(shape[:3], dtype=float) > MAX_VOXELS * 2:
        raise ValueError("This NIfTI volume exceeds the 200-million-sample memory limit.")
    if image.get_data_dtype().fields or image.get_data_dtype().kind not in "fiuc":
        raise ValueError("This NIfTI data type is not a supported scalar image.")
    return tuple(shape[:3]) + ((1,) if len(shape) == 2 else ())


def scan_nifti(path):
    image = nib.load(str(path))
    shape = _shape(image)
    count = image.shape[3] if len(image.shape) == 4 else 1
    if count > 4096:
        raise ValueError("This NIfTI contains more than 4,096 volumes. Open a smaller time-series subset.")
    key = _key(path)
    result = []
    for index in range(count):
        title = path.name + (f" · volume {index + 1}/{count}" if count > 1 else "")
        series = Series(f"nifti:{key}:{index}", title, "NIfTI images", path.name,
                        "NIfTI", "", [path], shape[2], study_uid=f"nifti:{key}",
                        files={path: FileInfo(path, shape[2])}, source_format="NIfTI",
                        source_path=path, volume_index=index)
        result.append(series)
    return result


def scan_inputs(paths, progress=lambda _: None):
    candidates = set()
    for path in map(Path, paths):
        if path.is_dir():
            for i, item in enumerate(path.rglob("*")):
                if i % 128 == 0:
                    progress(f"Scanning folder · {len(candidates):,} files found")
                if item.is_file():
                    candidates.add(item)
        elif path.is_file():
            candidates.add(path)
    nifti_paths = sorted(p for p in candidates if is_nifti(p))
    result = scan_paths(sorted(candidates - set(nifti_paths)), progress)
    for path in nifti_paths:
        progress(f"Indexing NIfTI · {path.name}")
        result.series.extend(scan_nifti(path))
    return result


def _native_data(image, index):
    data = np.asanyarray(image.dataobj[..., index] if len(image.shape) == 4 else image.dataobj)
    return data[:, :, None] if data.ndim == 2 else data


def load_nifti(series, progress=lambda _: None):
    path = series.source_path
    progress(f"Reading NIfTI · {path.name}")
    image = nib.load(str(path))
    _shape(image)
    affine = np.asarray(image.affine, dtype=float)
    if affine.shape != (4, 4) or not np.isfinite(affine).all() or abs(np.linalg.det(affine[:3, :3])) < 1e-12:
        raise ValueError("The NIfTI affine is invalid; image orientation cannot be determined.")
    spatial, temporal = image.header.get_xyzt_units()
    factor = {"mm": 1., "meter": 1000., "micron": .001}.get(spatial, 1.)
    world = affine.copy()
    world[:3] *= factor
    lps = RAS_LPS @ world
    spacing = np.linalg.norm(lps[:3, :3], axis=0)
    values = _native_data(image, series.volume_index)
    complex_data = np.iscomplexobj(values)
    source = np.asarray(np.abs(values) if complex_data else values, dtype=np.float32).transpose(2, 1, 0)
    source = np.nan_to_num(source, copy=True, nan=0., posinf=0., neginf=0.)
    ds = Dataset()  # display adapter only; the metadata pane uses the real NIfTI header below
    ds.ImageOrientationPatient = list(lps[:3, 0] / spacing[0]) + list(lps[:3, 1] / spacing[1])
    ds.ImagePositionPatient = list(lps[:3, 3])
    ds.PixelSpacing = [float(spacing[1]), float(spacing[0])]
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.SeriesDescription = series.description
    geometry_unit = "mm" if spatial in ("mm", "meter", "micron") else "units"
    def value(item):
        result = item.tolist()
        return result.decode("utf-8", errors="replace").rstrip("\0") if isinstance(result, bytes) else result
    metadata = {key: value(image.header[key]) for key in image.header.keys()}
    metadata.update({"affine_RAS": affine.tolist(), "spatial_units": spatial, "time_units": temporal,
        "selected_volume": series.volume_index + 1, "volume_count": image.shape[3] if len(image.shape) == 4 else 1,
        "display": "magnitude; original complex values retained for NIfTI export" if complex_data else "scaled scalar values"})
    note = "NIfTI RAS geometry converted to viewer LPS coordinates"
    if geometry_unit != "mm":
        note += " · spatial units unspecified; measurements use header units"
    data = ImageVolume(source, ds, series, tuple(float(v) for v in spacing), lps, 1, 0, False,
        geometry_unit == "mm", geometry_note=note, units="magnitude" if complex_data else "value",
        references=[FrameReference(path, z) for z in range(len(source))], headers={path: ds},
        _mpr_valid=len(source) > 1, format_metadata=metadata, geometry_unit=geometry_unit)
    data.width, data.level = data.series_window()
    progress("NIfTI volume ready")
    return data


def load_input_series(series, progress=lambda _: None):
    if series.source_format == "NIfTI":
        return load_nifti(series, progress)
    from .model import load_series
    return load_series(series, progress, reconstruct=False)


def converter_path():
    try:
        import dcm2niix
        root = Path(dcm2niix.__file__).resolve().parent
        for path in (*root.rglob("dcm2niix.exe"), *root.rglob("dcm2niix")):
            if path.is_file():
                return path
    except ImportError:
        pass
    found = shutil.which("dcm2niix")
    if found:
        return Path(found)
    raise ValueError("dcm2niix is required for DICOM conversion. Install the project's requirements.txt first.")


def _publish(files, destination, overwrite):
    targets = [destination.parent / source.name for source in files]
    stem = destination.name[:-7] if destination.name.lower().endswith(".nii.gz") else destination.stem
    approved = {destination.name}
    if destination.exists():
        approved.update(stem + extension for extension in (".json", ".bval", ".bvec"))
    for target in targets:
        if target.exists() and (not overwrite or target.name not in approved):
            raise FileExistsError(f"Export already exists: {target.name}")
    staged, backups, written = [], {}, []
    committed = False
    try:
        for source, target in zip(files, targets):
            fd, temporary = tempfile.mkstemp(prefix=".lumen-export-", dir=destination.parent)
            os.close(fd)
            temporary = Path(temporary)
            staged.append((temporary, target))
            shutil.copyfile(source, temporary)
        for temporary, target in staged:
            if target.exists():
                fd, backup = tempfile.mkstemp(prefix=".lumen-backup-", dir=destination.parent)
                os.close(fd)
                backup = Path(backup)
                try:
                    os.replace(target, backup)
                except BaseException:
                    backup.unlink(missing_ok=True)
                    raise
                backups[target] = backup
            os.replace(temporary, target)
            written.append(target)
        committed = True
    except BaseException as error:
        recovery = []
        for target in written:
            if target not in backups:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    recovery.append(f"Remove incomplete output: {target}")
        for target, backup in backups.items():
            try:
                os.replace(backup, target)
            except OSError:
                recovery.append(f"Original file retained at {backup}; restore to {target}")
        if recovery:
            raise OSError("Export failed; some files need recovery.\n" + "\n".join(recovery)) from error
        raise
    finally:
        for temporary, _ in staged:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        if committed:
            for backup in backups.values():
                with suppress(OSError):
                    backup.unlink(missing_ok=True)
    return targets


def export_nifti(data, destination, progress=lambda _: None, overwrite=False):
    destination = Path(destination)
    if not is_nifti(destination):
        destination = Path(str(destination) + ".nii.gz")
    if not destination.parent.is_dir():
        raise ValueError("Choose an existing output directory.")
    if any(destination.resolve() == path.resolve() for path in data.series.paths):
        raise ValueError("Choose an export destination different from the source image.")
    if "%" in destination.name:
        raise ValueError("Choose an export filename without percent signs.")
    with tempfile.TemporaryDirectory(prefix="lumen-nifti-") as temporary:
        root = Path(temporary)
        output = root / "output"
        output.mkdir()
        if data.series.source_format == "NIfTI":
            progress("Exporting the selected NIfTI volume…")
            original = nib.load(str(data.series.source_path))
            values = _native_data(original, data.series.volume_index)
            header = original.header.copy()
            header.set_data_dtype(values.dtype)
            image = type(original)(values, original.affine, header)
            nib.save(image, str(output / destination.name))
        else:
            if not data.series.paths:
                raise ValueError("Open a DICOM series before using dcm2niix conversion.")
            inputs = root / "input"
            inputs.mkdir()
            paths = list(dict.fromkeys(ref.path for ref in data.references if ref.path is not None)) or data.series.paths
            for i, path in enumerate(paths):
                progress(f"Preparing conversion · {i + 1} / {len(paths)}")
                staged = inputs / f"image_{i:06d}.dcm"
                try:
                    os.link(path, staged)
                except OSError:
                    shutil.copyfile(path, staged)
            compressed = destination.name.lower().endswith(".nii.gz")
            stem = destination.name[:-7] if compressed else destination.name[:-4]
            command = [str(converter_path()), "-z", "y" if compressed else "n", "-b", "y", "-ba", "y",
                       "-f", stem, "-o", str(output), str(inputs)]
            process = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            started = time.monotonic()
            try:
                while True:
                    progress("Converting the selected series with dcm2niix…")
                    try:
                        log, _ = process.communicate(timeout=.1)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() - started > 300:
                            raise TimeoutError("dcm2niix conversion exceeded five minutes.")
            except BaseException:
                process.kill()
                process.communicate()
                raise
            if process.returncode:
                raise ValueError("dcm2niix could not convert this series.\n" + log.decode(errors="replace")[-1200:])
        files = sorted(path for path in output.iterdir() if path.is_file() and
                       (is_nifti(path) or path.suffix.lower() in (".json", ".bval", ".bvec")))
        images = [path for path in files if is_nifti(path)]
        if not images:
            raise ValueError("The converter produced no NIfTI images for this series.")
        for path in images:
            image = nib.load(str(path))
            if not np.isfinite(image.affine).all():
                raise ValueError("The converted image has invalid spatial geometry.")
        progress("Saving NIfTI export…")
        return _publish(files, destination, overwrite)
