"""Assemble upstream runtime notices using only installed/vendored local files.

Run with the isolated build interpreter. This module does not choose a license
for Lumen and performs no network requests. Vendored notices retain provenance
in build_tools/licenses/upstream_manifest.json.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys


RUNTIME_DISTRIBUTIONS = (
    "numpy", "scipy", "PySide6-Essentials", "shiboken6", "pydicom", "vtk",
    "pylibjpeg", "pylibjpeg-openjpeg", "python-gdcm", "pyjpegls", "Pillow", "nibabel", "dcm2niix",
)
NOTICE_WORDS = ("license", "licence", "copying", "copyright", "notice", "authors")
VENDORED = Path(__file__).resolve().parent / "licenses"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_urls(dist: metadata.Distribution) -> list[dict[str, str]]:
    result = []
    for value in dist.metadata.get_all("Project-URL") or []:
        label, separator, url = value.partition(",")
        result.append({"label": label.strip() if separator else "Project", "url": url.strip() if separator else value})
    homepage = dist.metadata.get("Home-page")
    if homepage and not any(item["url"] == homepage for item in result):
        result.append({"label": "Homepage", "url": homepage})
    return result


def generate_notices(target: Path) -> None:
    """Write the complete THIRD_PARTY directory at *target*.

    Package notice files are selected from installed wheel RECORD inventories;
    sample images, tests, native tools, binaries, and application data are not
    copied. Missing package/Python/vendor notices fail the build explicitly.
    """
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    packages = []
    for name in RUNTIME_DISTRIBUTIONS:
        dist = metadata.distribution(name)
        package_dir = target / name
        package_dir.mkdir(exist_ok=True)
        files = []
        for entry in sorted(dist.files or [], key=str):
            relative = Path(entry)
            if relative.is_absolute() or ".." in relative.parts:
                continue
            if not any(word in relative.name.casefold() for word in NOTICE_WORDS):
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file() or source.suffix.casefold() in {".dll", ".pyd", ".exe", ".lib", ".pyc", ".py", ".h", ".c", ".cpp"}:
                continue
            destination = package_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            files.append({"installed_file": relative.as_posix(), "copied_to": destination.relative_to(target).as_posix(), "sha256": _sha256(destination)})
        if not files:
            raise RuntimeError(f"No installed license/copyright notice found for {name} {dist.version}")
        # Preserve the original metadata, including exact upstream licensing
        # statements and source URLs rather than paraphrasing a license grant.
        original_metadata = dist.read_text("METADATA")
        if original_metadata:
            (package_dir / "PACKAGE-METADATA.txt").write_text(original_metadata, encoding="utf-8")
        expression = dist.metadata.get("License-Expression")
        legacy_license = dist.metadata.get("License", "")
        packages.append({
            "distribution": name,
            "version": dist.version,
            "package_metadata": (package_dir / "PACKAGE-METADATA.txt").relative_to(target).as_posix(),
            "license_expression": expression,
            "license_metadata": legacy_license if len(legacy_license) <= 300 else "See PACKAGE-METADATA.txt and copied license text.",
            "license_classifiers": [value for value in dist.metadata.get_all("Classifier") or [] if value.startswith("License ::")],
            "version_page": f"https://pypi.org/project/{name}/{dist.version}/",
            "upstream_urls": _project_urls(dist),
            "notice_files": files,
        })

    python_license = next((path for path in (
        Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE",
        Path(sys.base_prefix) / "share/doc/python" / "LICENSE",
    ) if path.is_file()), None)
    if python_license is None:
        raise RuntimeError("The build interpreter's Python license could not be located")
    python_dir = target / "Python"
    python_dir.mkdir(exist_ok=True)
    shutil.copyfile(python_license, python_dir / "LICENSE.txt")

    manifest_file = VENDORED / "upstream_manifest.json"
    if not manifest_file.is_file():
        raise RuntimeError("Vendored upstream notice manifest is missing")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    vendor_files = manifest.get("files", [])
    if not vendor_files:
        raise RuntimeError("Vendored upstream notice manifest contains no files")
    for entry in vendor_files:
        relative = Path(entry["local_file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Invalid vendored notice path")
        source = VENDORED / relative
        if not source.is_file() or _sha256(source) != entry["sha256"]:
            raise RuntimeError(f"Vendored notice is missing or changed: {relative}")
        destination = target / "upstream" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(manifest_file, target / "upstream_manifest.json")
    icon_notices = Path(__file__).resolve().parents[1] / "lumen" / "resources" / "fluent"
    icon_target = target / "Fluent-System-Icons"
    icon_target.mkdir(exist_ok=True)
    for name in ("LICENSE.txt", "NOTICE.txt", "README.txt", "manifest.json"):
        shutil.copyfile(icon_notices / name, icon_target / name)
    if not any("LGPL-3.0" in entry["local_file"] for entry in vendor_files):
        raise RuntimeError("Qt's LGPLv3 text is missing from vendored notices")
    if not any(Path(entry["local_file"]).name.startswith("GPL-3.0") for entry in vendor_files):
        raise RuntimeError("Qt's GPLv3 text is missing from vendored notices")
    if not any(entry["component"] == "GDCM" and Path(entry["source_file"]).name == "Copyright.txt" for entry in vendor_files):
        raise RuntimeError("GDCM's upstream copyright is missing from vendored notices")

    index = {
        "purpose": "Third-party runtime licenses and upstream notices. No application license is assigned by this directory.",
        "python": {"version": sys.version.split()[0], "notice_file": "Python/LICENSE.txt", "sha256": _sha256(python_dir / "LICENSE.txt"),
                   "source_url": f"https://www.python.org/downloads/release/python-{sys.version_info.major}{sys.version_info.minor}{sys.version_info.micro}/",
                   "source_repository": "https://github.com/python/cpython"},
        "packages": packages,
        "vendored_provenance": "upstream_manifest.json",
        "vendored_notice_count": len(vendor_files),
        "icon_notices": "Fluent-System-Icons/LICENSE.txt",
    }
    (target / "INDEX.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "THIRD-PARTY RUNTIME NOTICES", "",
        "This directory records notices from the exact installed runtime packages and pinned upstream source trees.",
        "It does not assign a license to the Lumen application. Upstream components retain their respective licenses.",
        "License alternatives appearing in package metadata are upstream alternatives, not a grant of a commercial license.",
        "Upstream source trees contain notices for optional components too; retaining a notice does not imply that component is bundled.",
        "", "Installed runtime packages:",
    ]
    lines.extend(f"- {item['distribution']} {item['version']}: {item['version_page']}" for item in packages)
    lines.extend([
        f"- CPython {sys.version.split()[0]}: Python/LICENSE.txt", "",
        "- Microsoft Fluent System Icons (MIT): Fluent-System-Icons/LICENSE.txt", "",
        "Qt/PySide/Shiboken upstream metadata offers LGPLv3/GPL alternatives. The corresponding license texts and",
        "Qt source notices are retained under upstream/. Qt source repositories and exact refs are in upstream_manifest.json.",
        "Qt shared libraries remain separate runtime binaries in the portable folder; source/rebuild materials are supplied with the release.",
        "", "GDCM's wheel packaging license and its underlying library/dependency notices are retained separately.",
        "The complete paths, file checksums, package metadata and source URLs are listed in INDEX.json and upstream_manifest.json.", "",
    ])
    (target / "README.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    generate_notices(parser.parse_args().target)
