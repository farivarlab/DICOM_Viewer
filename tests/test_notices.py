"""The vendored notice set contains only license/attribution texts, and matches its manifest."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("lumen_build_notices", ROOT / "build_tools" / "notices.py")
notices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notices)
MANIFEST = json.loads((notices.VENDORED / "upstream_manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", [
    "LICENSE", "LICENSE.txt", "LICENCE.md", "license.txt", "COPYING", "COPYING_QHULL.txt", "LICENSE_DOP",
    "licenses/LicenseRef-Qt-Commercial.txt", "src/3rdparty/freetype/BDF-LICENSE.txt", "Copyright.txt",
    "COPYRIGHT.dcmtk", "AUTHORS", "NOTICE.txt", "LICENSES/MIT.txt", "src/3rdparty/zlib/qt_attribution.json",
])
def test_notice_names_are_selected(name):
    assert notices.is_notice_file(Path(name))


@pytest.mark.parametrize("name", [
    "examples/widgets/dialogs/licensewizard/licensewizard.pro", "doc/src/images/licensewizard-example.png",
    "examples/widgets/doc/src/licensewizard.qdoc", "licenseRule.json", "numpy/license_check.py",
    "LICENSES/README.png",
])
def test_examples_images_and_tooling_are_not_notices(name):
    assert not notices.is_notice_file(Path(name))


def test_every_vendored_file_is_a_notice_with_matching_checksum():
    for entry in MANIFEST["files"]:
        relative = Path(entry["local_file"])
        assert notices.is_notice_file(relative) or notices._spdx_text(relative), relative
        path = notices.VENDORED / relative
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], relative


def test_component_counts_match_listed_files_and_no_unlisted_files_remain():
    counts = Counter(entry["component"] for entry in MANIFEST["files"])
    assert {c["component"]: c["notice_files"] for c in MANIFEST["components"]} == dict(counts)
    listed = {Path(entry["local_file"]).as_posix() for entry in MANIFEST["files"]}
    present = {p.relative_to(notices.VENDORED).as_posix() for p in notices.VENDORED.rglob("*")
               if p.is_file() and p.name != "upstream_manifest.json"}
    assert present == listed
