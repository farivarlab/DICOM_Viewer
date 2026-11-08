$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    py -3.12 -m venv .build-venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 is required to create the build environment.' }
}
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
& $buildPython build_tools\build.py
if ($LASTEXITCODE -ne 0) { throw 'Portable build failed.' }
