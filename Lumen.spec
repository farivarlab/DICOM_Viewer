# Reproducible builds from an isolated environment: Windows x64 one-file and one-folder
# executables, a macOS Lumen.app bundle, or a Linux one-folder build.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "build_tools"))
from lumen import __version__ as VERSION
from release_info import platform_tag
import dcm2niix

WINDOWS, MACOS = sys.platform == "win32", sys.platform == "darwin"
TAG = platform_tag()
converter = Path(dcm2niix.__file__).resolve().parent / ("dcm2niix.exe" if WINDOWS else "dcm2niix")
if not converter.is_file():
    raise RuntimeError(f"The dcm2niix converter is missing from the build environment: {converter}")
material = ROOT / "build" / "release_materials"
hidden = ["gdcm", "_gdcm.gdcmswig", "_gdcm._gdcmswig", "jpeg_ls", "_CharLS"]
hidden += collect_submodules("openjpeg")
hidden += ["vtkmodules.vtkRenderingOpenGL2", "vtkmodules.vtkRenderingVolumeOpenGL2"]
data = collect_data_files("lumen", includes=["resources/*.svg", "resources/fluent/*.svg", "resources/fluent/*.txt", "resources/fluent/*.json"])
data += collect_data_files("lumen", includes=["resources/themes/*.json", "resources/themes/*.qss", "resources/glyphs/*.svg"])
data += collect_data_files("_gdcm", includes=["XML/*"])
for package in ("pylibjpeg", "pylibjpeg-openjpeg", "pyjpegls", "python-gdcm", "pydicom", "nibabel", "dcm2niix"):
    data += copy_metadata(package)
data += [(str(material / "THIRD_PARTY"), "THIRD_PARTY")]

a = Analysis(
    [str(ROOT / "launch_lumen.py")], pathex=[str(ROOT)],
    binaries=[(str(converter), "dcm2niix")], datas=data, hiddenimports=hidden, hookspath=[], runtime_hooks=[],
    excludes=["matplotlib", "IPython", "pytest", "tkinter", "PyQt5", "PyQt6", "PySide2", "libjpeg"],
    noarchive=False,
)
pyz = PYZ(a.pure)
settings = dict(debug=False, strip=False, upx=False, console=False, disable_windowed_traceback=False)
if WINDOWS:
    settings.update(icon=str(material / "lumen.ico"), version=str(material / "version_info.txt"), uac_admin=False)
elif MACOS:
    settings.update(icon=str(material / "lumen.png"))  # PyInstaller converts it to .icns

if WINDOWS:
    standalone = EXE(pyz, a.scripts, a.binaries, a.datas, [],
        name=f"Lumen-{VERSION}-win64", **settings)
    portable_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Lumen", **settings)
    portable = COLLECT(portable_exe, a.binaries, a.datas,
        strip=False, upx=False, name=f"Lumen-{VERSION}-portable-win64")
else:
    executable = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Lumen", **settings)
    folder = COLLECT(executable, a.binaries, a.datas, strip=False, upx=False, name=f"Lumen-{VERSION}-{TAG}")
    if MACOS:
        app = BUNDLE(folder, name="Lumen.app", icon=str(material / "lumen.png"),
            bundle_identifier="org.farivarlab.lumen", version=VERSION,
            info_plist={
                "CFBundleName": "Lumen",
                "CFBundleDisplayName": "Lumen DICOM Viewer",
                "CFBundleShortVersionString": VERSION,
                "CFBundleVersion": VERSION,
                "LSMinimumSystemVersion": "12.0",
                "NSHighResolutionCapable": True,
                "NSHumanReadableCopyright": "Not For Diagnostic Use. Research and education software.",
            })
