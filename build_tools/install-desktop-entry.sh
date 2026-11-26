#!/bin/sh
# Add Lumen to the desktop application menu for the current user, pointing at this folder.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
applications="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
mkdir -p "$applications" "$icons"
cp "$here/lumen.png" "$icons/lumen-dicom.png"
cat > "$applications/lumen-dicom.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Lumen DICOM Viewer
Comment=Offline DICOM and NIfTI viewer (not for diagnostic use)
Exec="$here/Lumen" %F
Icon=lumen-dicom
Terminal=false
Categories=Graphics;MedicalSoftware;Science;
DESKTOP
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$applications" || true
echo "Added Lumen to the application menu ($applications/lumen-dicom.desktop)."
