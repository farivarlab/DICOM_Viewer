from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location("release_info", Path(__file__).resolve().parents[1] / "build_tools/release_info.py")
release_info = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_info)


def test_runtime_fingerprint_tracks_assets_and_ignores_bytecode(tmp_path):
    for name in ("launch_lumen.py", "Lumen.spec", "logo.svg", "requirements.txt", "requirements-build.txt", "lumen/app.py", "lumen/resources/theme.qss", "build_tools/installer.iss"):
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("original")
    before = release_info.runtime_digest(tmp_path)
    cache = tmp_path / "lumen/__pycache__/app.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"generated")
    assert release_info.runtime_digest(tmp_path) == before
    (tmp_path / "lumen/resources/theme.qss").write_text("changed")
    assert release_info.runtime_digest(tmp_path) != before
    (tmp_path / "lumen/resources/theme.qss").write_text("original")
    assert release_info.runtime_digest(tmp_path) == before
    (tmp_path / "lumen/app.py").write_text("changed")
    assert release_info.runtime_digest(tmp_path) != before
