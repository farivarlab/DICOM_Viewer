Lumen DICOM Viewer - Linux (x86_64)

Not For Diagnostic Use. Research and education software.

Run:
    ./Lumen

To add Lumen to your desktop's application menu, run once from this folder:
    ./install-desktop-entry.sh

The build needs a 64-bit Linux desktop with glibc 2.35 or newer (for example Ubuntu
22.04, Debian 12, Fedora 36 or later) and OpenGL for 3D rendering. Preferences and saved
annotations are stored in ~/.config/lumen-dicom. All image processing is local; input
files are opened read only. No example patient studies are included.
