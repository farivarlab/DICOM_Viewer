"""Build portable Windows releases without reading studies or local validation artifacts."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lumen import __version__
from notices import generate_notices


def icon_file(material):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PIL import Image
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    from lumen.branding import logo_file
    QSvgRenderer(str(logo_file())).render(painter)
    painter.end()
    image.save(str(material / "lumen.png"))
    with Image.open(material / "lumen.png") as png:
        png.save(material / "lumen.ico", sizes=[(v, v) for v in (16, 24, 32, 48, 64, 128, 256)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize-only", action="store_true", help="Archive and checksum already-built binaries")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Build this Windows release on 64-bit Windows with Python 3.12.")
    material = ROOT / "build" / "release_materials"
    material.mkdir(parents=True, exist_ok=True)
    if not args.finalize_only:
        build_binaries(material)
    finalize_release(material)


def build_binaries(material):
    icon_file(material)
    generate_notices(material / "THIRD_PARTY")
    version = tuple(int(n) for n in __version__.split(".")) + (0,)
    (material / "version_info.txt").write_text(
        f"VSVersionInfo(ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), "
        "kids=[StringFileInfo([StringTable('040904B0', ["
        f"StringStruct('FileDescription','Lumen DICOM Viewer'), StringStruct('FileVersion','{__version__}'), "
        f"StringStruct('ProductName','Lumen DICOM'), StringStruct('ProductVersion','{__version__}'), "
        "StringStruct('OriginalFilename','Lumen.exe')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])", encoding="utf-8")
    # Dependency discovery must not collect similarly named DLLs from unrelated tools.
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    clean_path = os.pathsep.join((str(system_root / "System32"), str(system_root), str(Path(sys.executable).parent)))
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / "build" / "pyinstaller-cache"), PATH=clean_path)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "Lumen.spec")],
                   cwd=ROOT, env=env, check=True)


def finalize_release(material):
    dist = ROOT / "dist"
    folder = dist / f"Lumen-{__version__}-portable-win64"
    shutil.copy2(ROOT / "PORTABLE.txt", folder / "READ-ME.txt")
    shutil.copy2(ROOT / "logo.svg", folder / "logo.svg")
    if (ROOT / "LICENSE").is_file():
        shutil.copy2(ROOT / "LICENSE", folder / "LICENSE.txt")
    shutil.copytree(material / "THIRD_PARTY", folder / "THIRD_PARTY", dirs_exist_ok=True)
    shutil.make_archive(str(folder), "zip", root_dir=dist, base_dir=folder.name)
    source_zip = dist / f"Lumen-{__version__}-source.zip"
    subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), "archive", "--format=zip",
                    f"--output={source_zip}", "HEAD"], check=True)
    shutil.copy2(ROOT / "logo.svg", dist / "logo.svg")
    shutil.copy2(ROOT / "PORTABLE.txt", dist / "READ-ME.txt")
    if (ROOT / "LICENSE").is_file():
        shutil.copy2(ROOT / "LICENSE", dist / "LICENSE.txt")
    files = [dist / f"Lumen-{__version__}-win64.exe", Path(str(folder) + ".zip"), source_zip]
    def sha256(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    checksum = "\n".join(f"{sha256(path)}  {path.name}" for path in files) + "\n"
    (dist / "SHA256SUMS.txt").write_text(checksum, encoding="ascii")
    (dist / f"SHA256SUMS-{__version__}.txt").write_text(checksum, encoding="ascii")
    versions = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    (dist / "BUILD-DEPENDENCIES.txt").write_text(versions, encoding="utf-8")
    (dist / f"BUILD-DEPENDENCIES-{__version__}.txt").write_text(versions, encoding="utf-8")
    print(json.dumps({path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                      for path in files}, indent=2))


if __name__ == "__main__":
    main()
