"""Print the Homebrew cask for a published release, from its macOS checksum files.

    python build_tools/homebrew_cask.py 0.4.2 > ../homebrew-lumen/Casks/lumen.rb

The release must already carry the macOS archives and their SHA256SUMS-<version>-macos-*.txt
files, which the "macOS and Linux builds" workflow attaches. Uses the GitHub CLI (gh).
"""
from pathlib import Path
import subprocess
import sys
import tempfile

REPOSITORY = "farivarlab/DICOM_Viewer"
ARCHITECTURES = {"arm": "arm64", "intel": "x86_64"}


def checksums(version):
    with tempfile.TemporaryDirectory() as folder:
        subprocess.run(["gh", "release", "download", f"v{version}", "--repo", REPOSITORY,
                        "--pattern", f"SHA256SUMS-{version}-macos-*.txt", "--dir", folder], check=True)
        found = {}
        for path in Path(folder).iterdir():
            digest, name = path.read_text(encoding="ascii").split()
            for homebrew, arch in ARCHITECTURES.items():
                if name == f"Lumen-{version}-macos-{arch}.zip":
                    found[homebrew] = digest
        return found


def cask(version, digests):
    if not digests:
        raise SystemExit(f"Release v{version} has no macOS checksum files yet.")
    both = len(digests) == 2
    arch_lines = '  arch arm: "arm64", intel: "x86_64"\n\n' if both else ""
    sha = ("  sha256 arm:   \"{arm}\",\n         intel: \"{intel}\"\n".format(**digests) if both
           else f"  sha256 \"{next(iter(digests.values()))}\"\n")
    asset_arch = "#{arch}" if both else ARCHITECTURES[next(iter(digests))]
    only = "" if both else f"  depends_on arch: :{'arm64' if 'arm' in digests else 'x86_64'}\n"
    return f'''cask "lumen" do
{arch_lines}  version "{version}"
{sha}
  url "https://github.com/{REPOSITORY}/releases/download/v#{{version}}/Lumen-#{{version}}-macos-{asset_arch}.zip"
  name "Lumen DICOM Viewer"
  desc "Offline DICOM and NIfTI viewer with MPR and 3D volume rendering"
  homepage "https://github.com/{REPOSITORY}"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: ">= :monterey"
{only}
  app "Lumen.app"

  zap trash: "~/Library/Application Support/Lumen DICOM"

  caveats <<~EOS
    Lumen is not signed with an Apple Developer ID or notarized. The first time you
    open it, macOS may say it cannot verify the developer: open System Settings >
    Privacy & Security and choose "Open Anyway" for Lumen.

    Not For Diagnostic Use. Research and education software.
  EOS
end
'''


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    version = sys.argv[1].removeprefix("v")
    sys.stdout.write(cask(version, checksums(version)))
