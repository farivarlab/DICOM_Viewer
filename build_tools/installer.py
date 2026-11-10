"""Compile the per-user installer from a verified, current portable payload."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lumen import __version__
from release_info import runtime_digest, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    folder = ROOT / "dist" / f"Lumen-{__version__}-portable-win64"
    stamp = json.loads((folder / "BUILD-INFO.json").read_text(encoding="utf-8"))
    if (stamp["version"] != __version__ or stamp["runtime_digest"] != runtime_digest(ROOT)
            or stamp["executable_sha256"] != sha256(folder / "Lumen.exe")):
        raise SystemExit("Portable payload is stale or modified. Run Build-Portable.ps1 first.")
    compiler = args.compiler or shutil.which("ISCC.exe")
    if not compiler:
        compiler = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe"
    if not Path(compiler).is_file():
        raise SystemExit("Install Inno Setup 6, or pass --compiler with its ISCC.exe path.")
    subprocess.run([str(compiler), f"/DAppVersion={__version__}", f"/DProjectRoot={ROOT}",
                    str(ROOT / "build_tools" / "installer.iss")], check=True, cwd=ROOT)
    installer = ROOT / "dist" / f"Lumen-{__version__}-Setup-win64.exe"
    checksum_file = ROOT / "dist" / "SHA256SUMS.txt"
    lines = [line for line in checksum_file.read_text(encoding="ascii").splitlines()
             if not line.endswith("  " + installer.name)]
    lines.append(f"{sha256(installer)}  {installer.name}")
    checksums = "\n".join(lines) + "\n"
    checksum_file.write_text(checksums, encoding="ascii")
    (ROOT / "dist" / f"SHA256SUMS-{__version__}.txt").write_text(checksums, encoding="ascii")
    print(json.dumps({"installer": installer.name, "bytes": installer.stat().st_size,
                      "sha256": sha256(installer)}, indent=2))


if __name__ == "__main__":
    main()
