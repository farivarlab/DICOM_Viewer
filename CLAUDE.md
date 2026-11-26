# Lumen DICOM Viewer — notes for Claude and collaborators

Offline Windows desktop viewer for DICOM and NIfTI (Python 3.12, PySide6, NumPy/SciPy,
pydicom, nibabel, VTK). Research/education software, **Not For Diagnostic Use**.
Repository: https://github.com/farivarlab/DICOM_Viewer. User-facing changes go in
`CHANGELOG.md`; this file records how the project works and where in-progress work stands.

## Principles that shape the code

- **Offline and read-only.** No networking, accounts or update checks. Source images are
  never written. Anything persisted lives beside the portable settings file
  (`.lumen-settings.ini`, next to `Lumen.exe` or the project root from source).
- **Patient geometry is authoritative.** Volumes use DICOM LPS millimetres. Arrays are
  `[slice, row, column]`; `ImageVolume.affine` maps `(column, row, slice)` voxel indices to
  LPS. MPR is refused (with an explanation in `geometry_note`) rather than shown wrong.
- **No invented data.** Missing series numbers, calibration or units are reported as missing.
- **No patient demographics in anything Lumen writes** except explicit user exports
  (and PNG export only when "Include patient information" is ticked).

## Layout

| Path | Role |
| --- | --- |
| `lumen/app.py` | `MainWindow`: actions, docks, modes (2D stack / MPR / MPR + 3D / 3D), job handling, overlays, mark persistence |
| `lumen/model.py` | DICOM indexing (`scan_paths`), decoding (`load_series`), `ImageVolume` geometry, MPR reconstruction (`_canonicalize`), plane extraction incl. angled planes |
| `lumen/nifti.py` | NIfTI scan/load (RAS→LPS), dcm2niix conversion, safe export publishing (`_publish`) |
| `lumen/slice_view.py` | `SliceView` (QGraphicsView): window/level, tools, marks (`Mark`), ROI statistics, fused overlay layer, PNG rendering |
| `lumen/overlay.py` | Registered overlays: sample another volume at a pane's patient coordinates, colourise |
| `lumen/annotation_store.py` | Marks saved per series in `.lumen-annotations/` (JSON, keyed by SOP Instance UID + frame), measurement CSV rows |
| `lumen/anonymize.py` | De-identified copies of a DICOM series (`export_deidentified`, `Deidentifier`) |
| `lumen/movie.py` | Animated GIF writing (shared palette) and frame sampling |
| `lumen/timecourse.py` | Small painted line plot for 4D voxel time courses |
| `lumen/volume_view.py` | VTK volume rendering, created lazily |
| `lumen/browser.py` | Patient → study → series → file/frame tree with paging and search |
| `lumen/jobs.py` | Single-worker background jobs; `progress()` is the cancellation point |
| `lumen/importer.py` | ZIP extraction into private temp folders (flattened names, size caps) |
| `lumen/metadata.py` | Tag pane and metadata CSV (`csv_cell` guards spreadsheet formulas) |
| `build_tools/` | PyInstaller build (`build.py`), Inno Setup installer (`installer.iss`, `installer.py`), third-party notices |
| `tests/` | `test_*.py` run by pytest; `*_smoke.py` and `validate_local_study.py` are standalone scripts |

## Conventions

- Match the surrounding style: compact functions, short docstrings that explain *why*,
  comments only for non-obvious reasoning. No new runtime dependencies without a reason;
  the pinned set is in `requirements.txt` and mirrored in `pyproject.toml`.
- Anything slow runs through `MainWindow.start_job(function, callback, error_title=...)`.
  The function receives `progress(message)`; call it regularly so Cancel works. Callbacks
  that raise are reported via `fail_job` and `restore_current_selection`.
- Marks: `Mark.key` is `("Source", path, frame)` for acquired images and
  `(plane, index, slab, slab_mm)` for reconstructed planes (angled planes append
  `angles, cursor`). Persisted records translate paths to SOP Instance UIDs.
- Signals into `SliceView` changes: emit `marks_changed` whenever marks are added/removed so
  the debounced save runs.

## Develop, test, build, release

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt "pytest>=8,<10"
.\.venv\Scripts\python.exe -m pytest -q                 # ~1.5 min, all must pass
.\.venv\Scripts\python.exe tests\gui_smoke.py           # needs a real display (VTK/OpenGL)
.\.venv\Scripts\python.exe tests\colorbar_smoke.py      # likewise; startup/theme/performance smokes too
```

- Run GUI smoke tests on the real desktop: with `QT_QPA_PLATFORM=offscreen` VTK cannot get
  an OpenGL context and the process crashes.
- Release (Windows, needs Inno Setup 6; on this machine it is per-user):
  1. Bump the version in `lumen/__init__.py`, `pyproject.toml`, `PORTABLE.txt` and the
     `README.md` lines that name artifacts; date the `CHANGELOG.md` section.
  2. Run tests, **commit** (the build refuses uncommitted runtime sources so the source zip
     matches the binaries; `BUILD-INFO.json` records the commit).
  3. `.\Build-Installer.ps1 -CompilerPath "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"`.
     Run it via `cmd /c "powershell -File ... > log 2>&1"`; redirecting inside Windows
     PowerShell 5.1 turns pip's stderr notices into fatal errors.
  4. Check `dist\*.exe` version resources and run `Lumen.exe --self-test --report <file>`
     on both the portable folder and the single-file EXE.
  5. Tag `vX.Y.Z`, push `main` and the tag, then
     `gh release create vX.Y.Z --title "Lumen X.Y.Z" --notes-file <notes> dist\Lumen-X.Y.Z-Setup-win64.exe dist\Lumen-X.Y.Z-win64.exe dist\Lumen-X.Y.Z-portable-win64.zip dist\Lumen-X.Y.Z-source.zip dist\SHA256SUMS-X.Y.Z.txt`.

## Status and work log

Released: 0.3.0, 0.3.1, 0.3.2 (see `CHANGELOG.md`).

0.4.0 roadmap (agreed with the maintainer, in this order of value):

| Item | Status |
| --- | --- |
| Overlays / fusion (`overlay.py`) | Done, committed (`5821d4b`) |
| Saved annotations + measurement CSV (`annotation_store.py`) | Done, committed (`5821d4b`) |
| Angled MPR: tilt/rotate planes about the crosshair | Done, tested (`test_angled_mpr.py`), not yet committed |
| Side-by-side comparison with linked views | Done, tested (`test_compare.py`), not yet committed |
| 4D NIfTI time axis and voxel time-course plot | Done, tested (`test_time_series.py`), not yet committed |
| De-identified DICOM export | Done, tested (`test_anonymize.py`), not yet committed |
| Movie export (GIF) of slices, time points or a 3D turn | Done, tested (`test_movie.py`), not yet committed |

Next step: commit, then release 0.4.0 (minor bump: new features). Ideas not yet scheduled:
comparison in MPR layouts, overlays in 3D, overlay colorbar, JSON import/export of
annotations for sharing, MP4 export (needs an encoder dependency).

Not planned here, need the maintainer: code signing (requires buying a certificate),
macOS/Linux packaging (needs those machines or CI), browser thumbnails.

Design decisions so far:

- Overlays are sampled on the displayed pixel grid through both volumes' affines
  (`overlay.sample`), so they need no registration step and work with different sizes and
  orientations. Label maps (integer, ≤256 values) default to nearest sampling and the Cool
  colormap; black-starting colormaps skip their first quarter so low values stay visible.
- Annotations are stored per series UID, keyed by SOP Instance UID + frame so they survive
  moved folders and ZIP re-extraction; reconstructed-plane marks are only restored when the
  frame set (hash in `frames`) is identical.
- Angled MPR: `ImageVolume.plane_points(name, cursor, shape, angles)` is the single
  definition of where each displayed pixel lies in LPS (`model.PLANE_AXES` rotated by
  `plane_rotation((tilt, rotate))`). Plane images, crosshair clicks (`pixel_to_cursor`),
  overlays and the time-course probe all use it. At zero angles the oblique sampler equals
  the fast orthogonal path exactly (tested). An angled plane's mark/cache key appends
  `(angles, cursor)` because the plane depends on the whole crosshair position.
- Comparison reuses overlay sampling: the second series is resampled onto the Source pane's
  pixel grid, so both panes share scene geometry and `SliceView.apply_view_state` can copy
  zoom/pan exactly. Linking runs on `SliceView.view_transformed`, emitted from `paintEvent`
  when the transform or scroll position changed. `compare_view` is deliberately not in
  `MainWindow.views` (never active, no marks, not exported).
- 4D NIfTI: each volume stays its own `Series` (`nifti:<hash>:<index>`); `switch_volume`
  opens a sibling and `replace_volume` swaps data while keeping position, zoom, layout and a
  fixed contrast. `nifti.cache_time_series` holds one 4D file's volumes (≤ `MAX_VOXELS`
  samples) so stepping and `time_course` are immediate.
- De-identification empties identifying elements instead of deleting them (keeps required
  attributes valid), removes private tags, 50xx/60xx groups and `*Comment*` text, empties
  DA/DT/TM unless kept, and remaps every non-registered UID consistently per export. It
  writes into a hidden staging folder and renames it into place only when complete.
  `DeidentificationMethod` is LO (≤ 64 characters).
- Movie frames are rendered on the GUI thread (they need widget state) with a
  `QProgressDialog` for cancel; GIFs use one shared palette, since per-frame palettes made
  Pillow drop differently coloured frames as duplicates.
