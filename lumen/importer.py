from pathlib import Path
import tempfile
import zipfile

from .nifti import scan_inputs

MAX_ARCHIVE_BYTES = 4 * 1024**3


def import_paths(paths, progress=lambda _: None):
    """Flatten ZIP entries into private temporary folders; never trust entry paths."""
    expanded, temporaries = [], []
    try:
        for path in map(Path, paths):
            if path.suffix.lower() != ".zip":
                expanded.append(path)
                continue
            folder = tempfile.TemporaryDirectory(prefix="lumen-dicom-")
            temporaries.append(folder)
            root = Path(folder.name)
            with zipfile.ZipFile(path) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES or len(entries) > 50_000:
                    raise ValueError("ZIP archive exceeds the 4 GB / 50,000-file extraction limit.")
                total = 0
                for i, entry in enumerate(entries):
                    progress(f"Extracting ZIP · {i + 1:,} / {len(entries):,}")
                    if entry.flag_bits & 1:
                        raise ValueError("Password-protected ZIPs are not supported. Extract the archive first.")
                    # No archive-controlled folder paths or symbolic links are created.
                    name = entry.filename.replace("\\", "/")
                    suffix = ".nii.gz" if name.lower().endswith(".nii.gz") else Path(name).suffix[:16]
                    target = root / f"image_{i:06d}{suffix}"
                    with archive.open(entry) as source, target.open("wb") as destination:
                        while chunk := source.read(1024 * 1024):
                            total += len(chunk)
                            if total > MAX_ARCHIVE_BYTES:
                                raise ValueError("ZIP extraction exceeded the 4 GB limit.")
                            destination.write(chunk)
            expanded.append(root)
        return scan_inputs(expanded, progress), temporaries
    except Exception:
        for folder in temporaries:
            folder.cleanup()
        raise
