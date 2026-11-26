# Changelog

## Unreleased

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
- `tests/colorbar_smoke.py` starts from default settings on every run. Its saved settings previously left the colorbar off, so the script failed on every run after the first.

## 0.3.1 — 2026-11-26

- Select and delete individual marks: click a mark or its label with a non-drawing tool and press Delete, or right-click it for a delete menu.
- Indexing, decoding and conversion run as cancellable background jobs.
- Streamlined third-party notices bundled with the application.

## 0.3.0 — 2026-11-10

- Windows per-user installer with an uninstaller, Start menu shortcuts and an optional desktop shortcut.
- Study browser and Display panels can detach, move, close and redock.
- Diagnostic-use notice on the splash and About dialog.
