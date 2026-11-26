# Lumen DICOM Viewer

A local Windows desktop viewer built with Python, Qt (PySide6), NumPy/SciPy, pydicom, and VTK. It includes native 3D volume rendering and linked patient-coordinate MPR. All processing happens on this computer; there are no servers, accounts, or uploads. Original DICOM files are opened read only.

**Status:** development release 0.4.1, including overlays, saved annotations, angled MPR, series comparison, 4D NIfTI and de-identified export. Tested on Windows with generated fixtures and a supplied 299-slice MRI series. Portable builds include the native NIfTI converter and do not require Python to be installed.

## Windows installer

Published downloads are listed on the **[GitHub Releases page](https://github.com/farivarlab/DICOM_Viewer/releases)**. In a release's **Assets**, choose `Lumen-<version>-Setup-win64.exe` for the installer, or the portable EXE/ZIP if you prefer to run without installation. Installers appear there after a release is published; building locally does not upload them.

The installer includes Python, Qt/VTK, image codecs and the NIfTI converter. It installs for your Windows account under `%LOCALAPPDATA%\Programs\Lumen`, without an administrator prompt. It creates Start menu entries and offers an optional desktop shortcut. The installer works offline and does not take over DICOM/NIfTI file associations.

To update, close Lumen and run the newer installer. It reuses the installation folder and preserves your preferences and saved annotations. To remove it, use **Windows Settings → Apps → Installed apps → Lumen DICOM Viewer → Uninstall**, or **Uninstall Lumen** in its Start menu folder. The uninstaller removes the installed program, shortcuts, its preferences and generated icon cache. It leaves image files, exports and saved annotations (`.lumen-annotations`) alone, including files you put inside the installation folder.

To build the installer on Windows, install [Inno Setup 6](https://jrsoftware.org/isinfo.php) and run:

```powershell
.\Build-Installer.ps1
```

This first builds the current portable release, then creates `dist/Lumen-0.4.1-Setup-win64.exe` and adds it to `dist/SHA256SUMS.txt`. To compile the installer again without rebuilding the runtime, use `-SkipPortableBuild`; the build checks that its payload still matches the current runtime sources. Use `-CompilerPath 'C:\Path\To\ISCC.exe'` for a nonstandard Inno Setup location. The uninstaller is generated and installed by Setup; it is not a separate download.

## Screenshots

These screenshots use the built-in synthetic thorax phantom; no patient data is shown. Not For Diagnostic Use.

**2D viewing · light theme.** Slice browsing, distance measurement, image annotations and a calibrated colorbar.

![Light theme with the study browser, a 2D phantom slice, distance measurement and HU colorbar](docs/screenshots/stack-light.png)

**Multiplanar reconstruction · dark theme.** Linked axial, coronal and sagittal views with crosshairs.

![Dark theme showing linked axial, coronal and sagittal reconstructions of the synthetic phantom](docs/screenshots/mpr-dark.png)

**3D volume rendering.** Native VTK rendering with the CT bone preset, opacity and cutaway controls, and an orientation cube.

![Light theme with a 3D rendering of the synthetic phantom and volume-rendering controls](docs/screenshots/volume-light.png)

## Run from source

The development environment in this workspace is already prepared. Double-click **`Lumen DICOM Viewer.lnk`** to launch without a terminal. `Run-Lumen.cmd` remains available, or run:

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

## Command-line tools

`tools/` holds two standalone pydicom scripts that are not part of the viewer:

- `tools/extract_dicom_metadata.py` writes every non-pixel element of a DICOM file, including private tags and nested sequences, to JSON.
- `tools/get_transmit_voltage.py` prints the transmitter reference voltage stored by Siemens XA MR scanners.

Run them with any Python that has pydicom, for example `.\.venv\Scripts\python.exe tools\extract_dicom_metadata.py image.dcm -o metadata.json`.

## Included

| Area | Features |
| --- | --- |
| Import | DICOM files, scalar NIfTI `.nii` / `.nii.gz` (2D, 3D, 4D), recursive folders, DICOMDIR references, ZIP archives, drag and drop; patient → case/study → series → file/frame browser with search, scrolling and paged expansion; cancellable background indexing and decoding |
| 2D | Default view when opening a series or file; centered first image; linked browser selection; wheel/slider, previous/next, direct image-number and keyboard navigation; per-file/per-frame window and calibration defaults; window/level and presets; auto contrast; zoom, pan, rotate, flip; MONOCHROME1 inversion; RGB and palette-color display |
| Tools | Distance, three-point angle, rectangular and elliptical ROI with area/mean/SD/min/max, arrows, text; density probing; select and delete individual marks, or clear all; marks saved between sessions; measurement CSV |
| Colormaps | Grayscale, bone, hot iron, viridis, magma, cool, rainbow; invert any map; labeled colorbars for 2D/MPR and the actual 3D transfer colors |
| Playback | Cine loop, 1–60 fps, single-frame and multi-frame sequences |
| MPR | Axial, coronal, sagittal views in patient LPS coordinates; linked crosshairs; planes tilted and rotated about the crosshair; MIP, MinIP, average slabs; physical spacing; resampling of oblique acquisitions and uniformly tilted stacks |
| 3D | VTK adaptive GPU/CPU volume mapper; orbit/pan/zoom; CT tissue/bone/lung and scalar transfer presets; opacity; composite/MIP/MinIP; posterior cutaway; anatomical orientation cube |
| DICOM annotations | Current file's patient name/ID, birth date/age/sex, study/series, institution, date/time, acquisition settings and accession in the image frame when present; stored 60xx Overlay Data with origin and frame handling; separate visibility controls |
| Compare | A second series beside the 2D image, resampled to its patient position, with linked scrolling, zoom, pan, rotation and flips |
| 4D NIfTI | Volume selector and cine through time points, keeping position, zoom, layout and contrast; voxel time-course plot |
| Overlays | Fuse another opened series or NIfTI volume over 2D and MPR panes, aligned in patient coordinates; colormap, opacity, value range, linear or nearest sampling; overlay value in the probe |
| Metadata/export | Searchable read-only DICOM tags or NIfTI header pane, hidden by default and toggled with Ctrl+I; metadata CSV; annotated/unannotated PNG export; NIfTI series/volume export; de-identified DICOM copies; animated GIF of slices, time points or a 3D turn; clipboard; actual VTK framebuffer capture in the 3D-only layout |
| Interface | RAWDATA_Viewer's modern/classic light and dark palettes, typography and square window controls; dark image panes; Microsoft Fluent System Icons (MIT) for common commands and original specialist-tool glyphs; maximized startup with a small loading splash; one editable SVG for application identity |

Measurements use millimeters only when pixel spacing is present; otherwise they use pixels. ROI statistics include the pixels whose centers fall inside the outline. Marks belong to their view, image and projection. They are saved automatically and return when the series is opened again, also in later sessions; **Clear marks** removes them, including the saved copy.

Saved marks live in `.lumen-annotations` beside the preferences file (next to `Lumen.exe`, or the project root when running from source), one JSON file per series. Image files are never written. The files hold image identifiers (SOP Instance UIDs and frame numbers), mark coordinates and annotation text, but no patient name, ID or dates. Marks on acquired images follow their instance, so they survive moved folders and ZIP re-extraction. Marks on reconstructed MPR planes return only when the series has exactly the same frames.

**File → Export measurements…** writes every mark of the open series to CSV: the image it was drawn on, length, angle, ROI area, mean, SD, minimum and maximum, with value and spatial units (areas are in spatial unit²). MPR marks get values once MPR has been built in the session.

To delete one mark, click it or its label with a non-drawing tool (Window, Pan, Zoom or Scroll) and press **Delete**, or right-click it for a delete menu. With nothing selected, **Delete** removes the newest mark on the current image.

Choose **View → Appearance → Modern light / Modern dark / Classic light / Classic dark**. These are independent local copies of RAWDATA_Viewer's JSON palettes, QSS styles and window controls; this viewer does not depend on that project's installation. Modern uses Segoe UI and Classic uses Tahoma. Modern light is the initial default. Existing light/dark preferences migrate to the matching modern preset. The moon button switches light/dark within the current family. Preferences stay in `.lumen-settings.ini`, without registry changes. Switching themes leaves image contrast, colormaps, and exports unchanged.

The application logo is built in (`lumen/resources/lumen.svg`) and is not user-editable; it supplies the window, title bar, taskbar, dialogs, About box and splash. Windows ICOs for shortcuts are generated from it at multiple sizes under `.cache/icons`; changed artwork gets a new icon filename so Explorer refreshes its cached image.

The Windows launch shortcut is **`Lumen DICOM Viewer.lnk`**. It points directly to `.venv/Scripts/pythonw.exe -m lumen` with this project as its working directory. After moving the project, recreate the shortcut with **`Create-Shortcut.ps1`**. Its icon refresh preserves existing launch options. Editable theme files live in `lumen/resources/themes`; **Open theme folder** and **Reload appearance assets** use the same workflow as RAWDATA_Viewer. Changes to these assets do not rebuild the existing EXE.

Lumen starts maximized, keeping the Windows title bar and taskbar visible. **F11** enters full screen; pressing it again returns to the maximized window. A small splash appears before the imaging libraries load and closes when the main window is ready, without a minimum display delay. The splash follows the selected light/dark theme.

The study browser shows the DICOM series number before the modality and description, for example **12 · MR · NoiseCovariance**, and orders series numerically within each study. Image and file counts are in the tooltip. Missing series numbers are left out; the viewer does not invent them. Series numbers are searchable.

Common command icons use Microsoft's [Fluent System Icons](https://github.com/microsoft/fluentui-system-icons), distributed under the [MIT license](https://github.com/microsoft/fluentui-system-icons/blob/main/LICENSE). The subset and its license/copyright notices are included under `lumen/resources/fluent/`; each original SVG is recorded in a pinned-source checksum manifest. Help → Third-party notices links to the license. Windows font files and extracted system icons are not redistributed.

The **Colorbar** checkbox or **View → Colorbar** toggles scalar legends in the viewing panes, and remembers the choice. The scale sits beside the image, follows its colormap, inversion and window/level, and labels modality values/units (for example HU); fractional NIfTI values retain their scale. DICOM width-one windows show a two-color threshold instead of a continuous ramp. RGB images have no scalar colorbar. In 3D, the legend follows the rendering preset's color transfer function; opacity and lighting also affect the final appearance.

**Export PNG → Include colorbar** adds the scale in a separate right margin, keeping the image pixels and measurements clear. It can be selected for annotated images and 3D captures. Unannotated 2D output always excludes the colorbar. The color scale does not rotate or flip with the image.

The **Study browser** and **Display** panels can be detached by dragging their title bars or double-clicking them, just like the DICOM tags pane. Drag a panel back to either side to dock it, or double-click its floating title bar. Closed panels can be reopened from **View → Panels**.

## Overlays

Use **Overlay → Image** in the Display panel to fuse another opened series over the current one, for example a statistical or label map on an anatomical scan, or a second sequence. Any series or NIfTI volume in the study browser can be chosen. Both images are aligned by their recorded patient coordinates, so they may differ in size, spacing and orientation; no registration is performed. When two DICOM series come from different frames of reference, the status bar says so.

Set the colormap, opacity and the value range: values below **From** are transparent (unless **Hide values below range** is cleared) and values above **To** use the top color. Label maps (integer values) start with their full label range, nearest sampling and the Cool colormap, so labels are never blended and stay visible on bright anatomy; continuous maps start with Hot iron from their median non-zero value. Colormaps that begin at black start a quarter of the way in, so the lowest shown values do not disappear. The pixel probe adds the overlay value under the cursor. Overlays appear in 2D and MPR panes, and in PNG export and copies, whether annotated or not. On MIP, MinIP and average slabs the overlay shows the central plane. 3D rendering does not show overlays.

## Angled MPR

In MPR layouts, **Tilt** turns all three planes about the left-right axis and **Rotate** about the superior-inferior axis, both through the crosshair; **Reset plane angles** straightens them. Angled planes are resampled from the patient-coordinate volume with linear interpolation, keep the straight planes' pixel spacing, and support MIP, MinIP and average slabs along their normal. Clicking with the crosshair tool moves to the patient position under the cursor. Scrolling still steps through the volume's axial, coronal or sagittal index, moving the angled plane with it. Marks on an angled plane belong to its angles and crosshair position. Opening another series resets the angles.

## Comparing two series

Choose **Compare → Beside** in the Display panel to show another opened series next to the 2D image. Like overlays, it is aligned through patient coordinates: each displayed pixel shows the comparison value at the same patient position, so both panes share one pixel grid. Scrolling, zoom, pan, rotation and flips are linked in both directions, while window/level (right-drag in the comparison pane) is separate. The comparison is shown in the 2D stack layout, holds no marks, and is not included in PNG export.

## 4D NIfTI

A 4D NIfTI shows a **Volume** selector in the navigation bar. Stepping keeps the image position, zoom, layout and contrast. **Load all volumes** reads every time point once (up to 100 million samples), after which stepping is immediate and hovering over the image plots that voxel's values over time in the **Time course** section. **Cine through volumes** makes cine play time points instead of slices.

## De-identified DICOM export

**File → Export de-identified DICOM…** copies the open DICOM series into a new folder. Patient name and ID become a pseudonym; other identifiers, every person name, institutions, accession and study IDs are emptied; private tags, overlay planes and free-text comments are removed; dates and times are emptied unless kept; non-standard UIDs are replaced consistently, so the copy still forms one study and series. Age, sex, height and weight are kept unless you clear that option. The original files are only read. This is a conservative subset in the spirit of the DICOM Basic Application Level Confidentiality Profile, not a certified de-identification: text burned into pixels stays, and series that declare or commonly carry burned-in text (for example ultrasound and screen captures) are reported after export. Review the copies before sharing them.

## Movie export

**File → Export movie…** saves an animated, looping GIF at the cine frame rate: every slice of the active pane, every time point of a 4D NIfTI when **Cine through volumes** is ticked, or a full 3D turn in the 3D volume layout. Frames look as the pane shows them, with marks but without patient information or colorbar. Long sequences are sampled to 600 frames.

## NIfTI import and conversion

Open or drop `.nii` / `.nii.gz` files through the same browser as DICOM. Each time point in a 4D image appears as a separate selectable volume, with ordinary 2D viewing first and MPR/3D available on request. NIfTI RAS geometry is mapped into the viewer's LPS coordinates. Meter and micron units are converted to millimeters; unspecified units are labeled **units**, rather than claiming millimeter calibration. Complex images display magnitude. Unsupported vector/tensor or higher-dimensional images produce an explanatory error.

Use **File → Export NIfTI…**, the arrow beside **Export PNG**, or **Ctrl+Shift+S**. DICOM conversion uses the native [dcm2niix](https://github.com/rordenlab/dcm2niix) workflow and produces `.nii.gz` (default) or `.nii`, plus JSON and diffusion `.bval` / `.bvec` sidecars when the converter provides them. Only files belonging to the selected series are passed to the converter. All output stays local. Conversion runs in the background and can be cancelled before files are saved. Converter-generated additional volumes are retained and reported instead of silently discarded.

Exporting an opened NIfTI saves the selected 3D volume with its source geometry and scaled values, retaining complex values when present. Display windowing, colormaps, rotations, and annotations are presentation settings and are not baked into NIfTI data. Original images are read only. NIfTI export is available for scalar images; RGB NIfTI, Analyze pairs, and ISMRMRD are outside the current scope. [NiBabel](https://nipy.org/nibabel/nifti_images.html) handles NIfTI reading and writing.

NIfTI uses continuous scalar windowing, including fractional widths below one. Its value readout and ROI statistics preserve useful precision for probability and quantitative maps. DICOM retains its LINEAR windowing rules, including the width-one threshold.

## Image display and PNG export

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
| Esc / Delete | Cancel drawing / remove the selected mark (or the newest on the current image) |
| Right-click a mark | Delete it, or all marks on the image |
| Ctrl+I / Ctrl+S / Ctrl+C | Toggle metadata pane / export PNG / copy image |
| Ctrl+Shift+S | Export selected DICOM series / NIfTI volume as NIfTI |
| Ctrl+Shift+R | Reload edited themes and glyphs |
| F11 / F1 | Full screen / help |

In 3D, drag to orbit, middle drag to pan, and use the wheel to zoom. Display windowing and colormaps apply to 2D views; 3D uses its separate transfer presets. For 3D image export, select **3D volume** in the layout menu.

## Portable Windows executable

The portable release includes the current viewing tools, themes, colorbars, NIfTI reader/writer, and native dcm2niix converter. Older versioned artifacts can be kept alongside it.

The application does not depend on its working directory, a database, installed Python, registry registration, or a service at runtime once bundled. ZIP scratch space uses the operating system's temporary directory. The source launcher locates the development environment relative to itself.

The build includes Python, Qt platform/image/SVG libraries, VTK rendering modules, NumPy/SciPy, pydicom and codecs. The output directory contains:

- `dist/Lumen-0.4.1-win64.exe`: single portable executable, with temporary runtime extraction at startup.
- `dist/Lumen-0.4.1-portable-win64.zip`: extract the complete folder and run `Lumen.exe`; starts faster and keeps shared libraries replaceable.
- `dist/Lumen-0.4.1-source.zip`: corresponding application source, build scripts and license.
- `dist/SHA256SUMS.txt`: checksums for the release files.

Build from 64-bit Python 3.12 on Windows with `Build-Portable.ps1`. It creates an isolated `.build-venv`, installs `requirements-build.txt`, generates icons/notices, and runs `Lumen.spec`. Source files and build scripts are in Git; studies, image exports, environments and binaries are ignored. The notice collector verifies pinned upstream notice checksums and does not use the network during the build. The build environment's DLL search path excludes unrelated local tools.

Both executable forms support an opt-in self-test, for example:

```powershell
.\Lumen.exe --self-test --input 'C:\Scans\Study' --report 'C:\Temp\LumenCheck\report.json'
```

The checks exercise bundled Qt/resources, metadata, calibration, image export, colorbars, MPR, native VTK rendering, codecs, DICOM-to-NIfTI conversion, and 4D NIfTI loading. Reports include `frozen: true` when run from a package. A clean environment/path launch is checked locally; testing on a separate clean Windows machine with representative GPU drivers is still recommended. Releases are unsigned development builds. Help → Third-party notices opens the included library notices and source links. The application uses the MIT license in [LICENSE](LICENSE); dependencies retain their own licenses.

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
.\.venv\Scripts\python.exe tests\theme_smoke.py
.\.venv\Scripts\python.exe tests\startup_smoke.py
.\.venv\Scripts\python.exe tests\colorbar_smoke.py
```

The tests cover spatial ordering, per-frame physical calibration/units/windowing, LPS axis permutations and reversals, malformed/irregular/missing/repeated geometry, enhanced multi-frame rescale, temporal cine handling, signed RLE decoding, duplicate instances, dimensions, archive path isolation, DICOM window boundaries, crosshair correspondence, edge slabs, anisotropic angles, and off-image ROI clipping. Workflow tests also cover default 2D centering, lazy MPR, cancellation/closing, file/stack navigation, bounded browser expansion/search, virtual metadata filtering, current-file annotations, stored DICOM overlays, Fit preserving orientation, custom window state, avoiding redundant pixel rendering, and clean/annotated PNG content and transforms. The GUI smoke script checks Qt/VTK rendering and captures default, compact, and MPR views. The optional performance script measures navigation through 96 synthetic 512×512 images and saves timings to `artifacts/navigation-performance.json`; it is a local synthetic benchmark, not a clinical performance guarantee.

An opt-in local-study check is available for user-provided files:

```powershell
.\.venv\Scripts\python.exe tests\validate_local_study.py 'C:\Scans\Study\image.dcm'
```

It reads the named file and neighboring `.dcm` files, compares decoded pixels and exported transformations, checks calibration/navigation/MPR/slabs/3D, verifies input-file hashes, and saves a technical JSON report plus image exports without identifying DICOM text under `artifacts/local-study-validation/`. These artifacts remain local and ignored by version control. A supplied 299-slice, 299×299 MR series at 0.75 mm spacing passed these checks; this establishes compatibility with that study, not general clinical readiness.

Primary references: [MicroDicom feature list](https://www.microdicom.com/), [pydicom pixel processing](https://pydicom.github.io/pydicom/stable/guides/user/working_with_pixel_data.html), [VTK adaptive volume mapper](https://vtk.org/doc/nightly/html/classvtkSmartVolumeMapper.html), [Qt for Python](https://www.qt.io/development/qt-framework/python-bindings).

NIfTI tests cover source values and LPS geometry, units, 2D/4D handling, complex-value preservation, fractional contrast, archive import, dcm2niix conversion with calibrated voxel landmarks, and export collision/rollback handling. Theme tests cover preference persistence, icon changes, and unchanged image exports. The supplied MRI was also converted to NIfTI, reopened through the UI, and checked in MPR and native 3D: canonical voxel values, 0.75 mm spacing, and spatial origin matched the DICOM source. Local numerical results are under `artifacts/nifti-validation/`; they are excluded from Git.
