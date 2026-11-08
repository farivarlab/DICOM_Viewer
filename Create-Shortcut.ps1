$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$viewerPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $viewerPython)) {
    throw 'Set up the development environment first. See README.md.'
}
& $viewerPython -m lumen.branding --create-shortcut
if ($LASTEXITCODE -ne 0) { throw 'The Windows launch shortcut could not be created.' }
