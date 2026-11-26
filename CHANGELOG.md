# Changelog

## Unreleased

### Changed

- **New application logo.** The window, taskbar, splash, dialogs, shortcuts and executables use the new artwork.
- **The logo is built in.** It can no longer be replaced through a `logo.svg` beside the program, and View → Appearance no longer has *Open logo folder*; *Reload appearance assets* now reloads themes and glyphs only. The installer removes the `logo.svg` left by earlier versions.

## 0.4.0 — 2026-11-26

### Added

- **Overlays.** Fuse another opened series or NIfTI volume over the 2D and MPR panes, for example a statistical or label map on an anatomical scan. Images are aligned by their patient coordinates, so they may differ in size, spacing and orientation. Choose the colormap, opacity, value range and sampling in the Display panel's new Overlay section. Label maps keep their labels with nearest sampling. The probe shows the overlay value, and PNG export and copies include the overlay.
- **Saved annotations.** Marks are saved automatically per series and return when the series is opened again, also in later sessions. They are stored in `.lumen-annotations` beside the preferences file, without patient demographics, and follow their images across moved folders and ZIP re-extraction. Clear marks removes the saved copy too.
- **Angled MPR.** Tilt and rotate the MPR planes about the crosshair, with slabs along the angled normal.
- **Side-by-side comparison.** Show another opened series beside the 2D image, aligned by patient position, with scrolling, zoom, pan, rotation and flips linked.
- **4D NIfTI time axis.** Step or play through the volumes of a 4D NIfTI while keeping the view, and plot a voxel's values over time.
- **De-identified DICOM export.** Copy the open series into a new folder without patient identifiers, private tags or overlays, with replaced UIDs and optional dates and demographics.
- **Movie export.** Save slices, 4D time points or a 3D turn as an animated GIF.
- **Measurement export.** File → Export measurements… writes every mark of the open series to CSV, with length, angle, ROI area, mean, SD, minimum, maximum and units.

## 0.3.2 — 2026-11-26

### Fixed

- **Folder import with an unreadable NIfTI file.** A corrupt or unsupported `.nii` / `.nii.gz` inside a folder or ZIP is now skipped and counted with the other unreadable files, instead of cancelling the whole import. A NIfTI file opened on its own still explains why it cannot be shown.
- **Re-exporting NIfTI to the same name.** Confirming an overwrite now replaces every file of the earlier export, including extra images dcm2niix writes for multi-echo or split series (for example `volume_e2.nii.gz`). Unrelated existing files are still never replaced.
- **3D appearance preset.** The 3D view now always uses the preset shown in the Appearance list. It previously switched non-CT series to Scalar without updating the list.
- **MPR of almost-orthogonal stacks.** Stacks whose orientation differs from the patient axes by less than a tenth of a voxel across the whole volume are reoriented without resampling. Before, tiny residual obliquities written by scanners triggered a slow, memory-heavy isotropic resampling that could lower in-plane detail.
- **Cancelling an oblique MPR reconstruction.** Resampling now runs in slabs and reports progress, so Cancel and closing the window take effect during long reconstructions. Results are unchanged.
- **Importing the same images twice.** Instances already in a series (same SOP Instance UID) are no longer added again when imported through another path, such as a second copy of a ZIP. File lists and image counts stay correct.
- **Metadata CSV export.** Plain numbers such as `-1024` are written unchanged. Text that a spreadsheet could run as a formula is still prefixed with an apostrophe, now including values starting with a tab or carriage return.

### Build

- Release builds stop when the runtime sources have uncommitted changes, so the source archive always matches the binaries. `BUILD-INFO.json` records the commit, and finalizing a release checks that it is still `HEAD`.
- The installer's file properties now show its version. Setup.exe previously had a blank file version in Windows' Details tab.
- `tests/colorbar_smoke.py` starts from default settings on every run. Its saved settings previously left the colorbar off, so the script failed on every run after the first.

## 0.3.1 — 2026-11-26

- Select and delete individual marks: click a mark or its label with a non-drawing tool and press Delete, or right-click it for a delete menu.
- Indexing, decoding and conversion run as cancellable background jobs.
- Streamlined third-party notices bundled with the application.

## 0.3.0 — 2026-11-10

- Windows per-user installer with an uninstaller, Start menu shortcuts and an optional desktop shortcut.
- Study browser and Display panels can detach, move, close and redock.
- Diagnostic-use notice on the splash and About dialog.
