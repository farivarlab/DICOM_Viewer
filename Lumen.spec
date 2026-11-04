# Reproducible Windows x64 one-file and one-folder builds, from an isolated environment.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH)
VERSION = "0.1.0"
material = ROOT / "build" / "release_materials"
hidden = ["gdcm", "_gdcm.gdcmswig", "_gdcm._gdcmswig", "jpeg_ls", "_CharLS"]
hidden += collect_submodules("openjpeg")
hidden += ["vtkmodules.vtkRenderingOpenGL2", "vtkmodules.vtkRenderingVolumeOpenGL2"]
data = collect_data_files("lumen", includes=["resources/*.svg"])
data += collect_data_files("_gdcm", includes=["XML/*"])
for package in ("pylibjpeg", "pylibjpeg-openjpeg", "pyjpegls", "python-gdcm", "pydicom"):
    data += copy_metadata(package)
data += [(str(material / "THIRD_PARTY"), "THIRD_PARTY")]

a = Analysis(
    [str(ROOT / "launch_lumen.py")], pathex=[str(ROOT)],
    binaries=[], datas=data, hiddenimports=hidden, hookspath=[], runtime_hooks=[],
    excludes=["matplotlib", "IPython", "pytest", "tkinter", "PyQt5", "PyQt6", "PySide2", "libjpeg"],
    noarchive=False,
)
pyz = PYZ(a.pure)
settings = dict(debug=False, strip=False, upx=False, console=False,
    icon=str(material / "lumen.ico"), version=str(material / "version_info.txt"),
    uac_admin=False, disable_windowed_traceback=False)

standalone = EXE(pyz, a.scripts, a.binaries, a.datas, [],
    name=f"Lumen-{VERSION}-win64", **settings)
portable_exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Lumen", **settings)
portable = COLLECT(portable_exe, a.binaries, a.datas,
    strip=False, upx=False, name=f"Lumen-{VERSION}-portable-win64")
