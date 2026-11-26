"""Bind installer inputs to the runtime sources and executable that were built."""
import hashlib
import platform
import sys


def platform_tag():
    """Release-asset platform name: win64, macos-arm64, macos-x86_64, linux-x86_64, …"""
    if sys.platform == "win32":
        return "win64"
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"{'macos' if sys.platform == 'darwin' else 'linux'}-{arch}"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def runtime_digest(root):
    files = [root / name for name in ("launch_lumen.py", "Lumen.spec", "requirements.txt", "requirements-build.txt")]
    files += [path for directory in ("lumen", "build_tools") for path in (root / directory).rglob("*")
              if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()
