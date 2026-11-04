# Lumen DICOM Viewer

A local Windows desktop viewer built with Python, Qt (PySide6), NumPy/SciPy, pydicom, and VTK. It includes native 3D volume rendering and linked patient-coordinate MPR. All processing happens on this computer; there are no servers, accounts, or uploads. Original DICOM files are opened read only.

**Status:** development release 0.1.0. Tested on Windows with generated fixtures and a supplied 299-slice MRI series. Portable Windows builds are produced locally; no release is uploaded automatically.

## Run from source

The development environment in this workspace is already prepared. Double-click `Run-Lumen.cmd`, or run:

```powershell
.\.venv\Scripts\python.exe -m lumen
.\.venv\Scripts\python.exe -m lumen --demo
.\.venv\Scripts\python.exe -m lumen 'C:\Scans\Study'
```

For a fresh checkout, use 64-bit Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m lumen
```

## Included

| Area | Features |
| --- | --- |
| Import | Files, recursive folders, DICOMDIR references, ZIP archives, drag and drop; patient → case/study → series → file/frame browser with search, scrolling and paged expansion; cancellable background indexing and decoding |
| 2D | Default view when opening a series or file; centered first image; linked browser selection; wheel/slider, previous/next, direct image-number and keyboard navigation; per-file/per-frame window and calibration defaults; window/level and presets; auto contrast; zoom, pan, rotate, flip; MONOCHROME1 inversion; RGB and palette-color display |
| Tools | Distance, three-point angle, rectangular and elliptical ROI with area/mean/SD/min/max, arrows, text; density probing; undo last mark and clear marks |
| Colormaps | Grayscale, bone, hot iron, viridis, magma, cool, rainbow; invert any map |
| Playback | Cine loop, 1–60 fps, single-frame and multi-frame sequences |
| MPR | Axial, coronal, sagittal views in patient LPS coordinates; linked crosshairs; MIP, MinIP, average slabs; physical spacing; resampling of oblique acquisitions and uniformly tilted stacks |
| 3D | VTK adaptive GPU/CPU volume mapper; orbit/pan/zoom; CT tissue/bone/lung and scalar transfer presets; opacity; composite/MIP/MinIP; posterior cutaway; anatomical orientation cube |
| DICOM annotations | Current file's patient name/ID, birth date/age/sex, study/series, institution, date/time, acquisition settings and accession in the image frame when present; stored 60xx Overlay Data with origin and frame handling; separate visibility controls |
| Metadata/export | Searchable read-only DICOM metadata pane with virtual table rendering, hidden by default and toggled with DICOM tags / Ctrl+I; follows the selected file; metadata CSV; annotated/unannotated PNG export; clipboard; actual VTK framebuffer capture in the 3D-only layout |
| Interface | Light workspace with dark image panes; original vector glyphs for all commands; square buttons, fields, cards, panels, and slider handles; full-screen mode |

Measurements use millimeters only when pixel spacing is present; otherwise they use pixels. Areas count included pixel centers. User annotations remain in memory, belong to their view/slice/projection, and are cleared when changing series.

**Export PNG** offers annotated or unannotated output, plus optional patient/acquisition information for annotated output. The PNG contains the full image with current contrast, colormap, physical aspect ratio, rotation and flips, independently of viewport zoom/pan. Viewing borders, crosshairs, and pending drawings are excluded. Annotated output includes saved measurements/text/arrows and stored DICOM overlay layers. Unannotated output excludes these layers and information text; text already burned into the pixel data remains. Exports do not anonymize the source pixels. Use **3D volume** for PNG export of the current 3D camera view.

MPR uses patient geometry instead of filename or instance order and is constructed only when requested. Orthogonal stacks share their source array; oblique/tilted scans use resampling. The loader handles per-frame rescale and spatial functional groups in enhanced multi-frame images. Missing/irregular positions, repeated spatial locations, mixed units/orientations/spacing, and malformed/nonfinite geometry disable MPR with an explanation; their 2D stacks remain available with individual frame calibration. Temporal cine frames are never silently treated as spatial slices. Compatible dimensions are required within a series. Explicit file/frame window settings are respected; missing settings share one sampled series-wide fallback so scrolling does not pump contrast. **Auto contrast** fits the active image when explicitly selected.

Compressed image support uses pydicom with GDCM, CharLS, OpenJPEG, and Pillow. The packaged self-test exercises native RLE, JPEG-LS and JPEG 2000 lossless roundtrips and baseline JPEG decoding. JPEG lossless decoding is available through GDCM. True 12-bit Extended JPEG is not supported by this bundled codec set. Unsupported pixel decoding produces an error. Archive extraction is temporary, flattened to generated filenames, and capped at 4 GB / 50,000 files. Temporary files are cleaned up on normal exit.

## Controls

| Control | Action |
| --- | --- |
| Ctrl+O / Ctrl+Shift+O | Open files / folder |
| Wheel / arrow keys | Browse slices in the active pane |
| Down / Up | Next / previous image |
| Page Down / Page Up / Home / End | Forward 10 / back 10 / first / last image |
| Ctrl+wheel | Zoom |
| Right drag / middle drag | Window and level / pan |
| W / P / Z / S | Window / pan / zoom / scroll tool |
| C / D / E / A / T | Crosshair / distance / ellipse / angle / text |
| Space | Play/pause cine |
| F / R / I / H / V / ] | Fit / reset / invert / horizontal flip / vertical flip / rotate 90° |
| Esc / Delete | Cancel drawing / remove last mark on the current slice |
| Ctrl+I / Ctrl+S / Ctrl+C | Toggle metadata pane / export PNG / copy image |
| F11 / F1 | Full screen / help |

In 3D, drag to orbit, middle drag to pan, and use the wheel to zoom. Display windowing and colormaps apply to 2D views; 3D uses its separate transfer presets. For 3D image export, select **3D volume** in the layout menu.

## Portable Windows executable

The application does not depend on its working directory, a database, installed Python, registry registration, or a service at runtime once bundled. ZIP scratch space uses the operating system's temporary directory. The source launcher locates the development environment relative to itself.

The build includes Python, Qt platform/image/SVG libraries, VTK rendering modules, NumPy/SciPy, pydicom and codecs. The output directory contains:

- `dist/Lumen-0.1.0-win64.exe`: single portable executable, with temporary runtime extraction at startup.
- `dist/Lumen-0.1.0-portable-win64.zip`: extract the complete folder and run `Lumen.exe`; starts faster and keeps shared libraries replaceable.
- `dist/SHA256SUMS.txt`: checksums for the release files.

Build from 64-bit Python 3.12 on Windows with `Build-Portable.ps1`. It creates an isolated `.build-venv`, installs `requirements-build.txt`, generates icons/notices, and runs `Lumen.spec`. Source files and build scripts are in Git; studies, image exports, environments and binaries are ignored. The notice collector verifies pinned upstream notice checksums and does not use the network during the build. The build environment's DLL search path excludes unrelated local tools.

Both executable forms support an opt-in self-test, for example:

```powershell
.\Lumen.exe --self-test --input 'C:\Scans\Study' --report 'C:\Temp\LumenCheck\report.json'
```

The checks exercise bundled Qt/resources, metadata, calibration, image export, MPR, native VTK rendering and codecs. Reports include `frozen: true` when run from a package. A clean environment/path launch is checked locally; testing on a separate clean Windows machine with representative GPU drivers is still recommended. Releases are unsigned development builds. Help → Third-party notices opens the included library notices and source links. No application license is assigned automatically.

Python is a practical starting point because VTK performs rendering in native code and the interface can evolve quickly. Its Qt/VTK distribution will be considerably larger than MicroDicom. If a very small download or minimal startup time becomes a strict requirement, C++ with Qt/VTK and a native DICOM decoder is the better long-term direction; VTK itself still adds size. No claim of a MicroDicom-sized executable is made.

## Scope and limits

This is a first version of the requested local viewing tools, not complete MicroDicom feature parity. It does not yet include PACS/DICOMweb, a persistent study database, PET-CT fusion/SUV, DICOM editing/anonymization, printing, reports/PDF/video playback, external presentation states/GSPS, retired overlays embedded in unused pixel bits, arbitrary oblique-plane controls, segmentation, surface/STL export, video export, or independent multi-series comparison. Stored 60xx Overlay Data is supported in the source 2D view. VOI LUT tables, SIGMOID/LINEAR_EXACT window functions, and real-world-value mappings are not applied; current grayscale display uses DICOM LINEAR windowing after the modality transform. Only the first default window is selected; custom window/level remains available. Color data is viewed in 2D; 16-bit color is scaled for 8-bit display.

Large source stacks are held in memory. Source loading is capped at 200 million samples and canonical reconstruction at approximately 100 million voxels; reconstruction may downsample to fit this limit. Cancellation is cooperative: a pixel decoder or resampling operation already in progress finishes before cancellation takes effect. Closing during import requests cancellation and closes automatically when the worker stops. Enhanced temporal/multi-echo stacks are browsed in 2D rather than separated into independent volumes. Duplicate SOP instance paths resolve to the displayed original; equal SOP instance UIDs are assumed to identify identical content. Performance and codec compatibility still need testing with representative real studies. This software is for research and education and has not been validated for diagnostic use.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests\gui_smoke.py
.\.venv\Scripts\python.exe tests\performance_smoke.py
```

The tests cover spatial ordering, per-frame physical calibration/units/windowing, LPS axis permutations and reversals, malformed/irregular/missing/repeated geometry, enhanced multi-frame rescale, temporal cine handling, signed RLE decoding, duplicate instances, dimensions, archive path isolation, DICOM window boundaries, crosshair correspondence, edge slabs, anisotropic angles, and off-image ROI clipping. Workflow tests also cover default 2D centering, lazy MPR, cancellation/closing, file/stack navigation, bounded browser expansion/search, virtual metadata filtering, current-file annotations, stored DICOM overlays, Fit preserving orientation, custom window state, avoiding redundant pixel rendering, and clean/annotated PNG content and transforms. The GUI smoke script checks Qt/VTK rendering and captures default, compact, and MPR views. The optional performance script measures navigation through 96 synthetic 512×512 images and saves timings to `artifacts/navigation-performance.json`; it is a local synthetic benchmark, not a clinical performance guarantee.

An opt-in local-study check is available for user-provided files:

```powershell
.\.venv\Scripts\python.exe tests\validate_local_study.py 'C:\Scans\Study\image.dcm'
```

It reads the named file and neighboring `.dcm` files, compares decoded pixels and exported transformations, checks calibration/navigation/MPR/slabs/3D, verifies input-file hashes, and saves a technical JSON report plus image exports without identifying DICOM text under `artifacts/local-study-validation/`. These artifacts remain local and ignored by version control. A supplied 299-slice, 299×299 MR series at 0.75 mm spacing passed these checks; this establishes compatibility with that study, not general clinical readiness.

Primary references: [MicroDicom feature list](https://www.microdicom.com/), [pydicom pixel processing](https://pydicom.github.io/pydicom/stable/guides/user/working_with_pixel_data.html), [VTK adaptive volume mapper](https://vtk.org/doc/nightly/html/classvtkSmartVolumeMapper.html), [Qt for Python](https://www.qt.io/development/qt-framework/python-bindings).
