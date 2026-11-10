param(
    [switch]$SkipPortableBuild,
    [string]$CompilerPath
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $SkipPortableBuild) {
    & "$PSScriptRoot\Build-Portable.ps1"
}
$installerPython = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $installerPython)) { throw 'Run Build-Portable.ps1 first.' }
$installerArguments = @('build_tools\installer.py')
if ($CompilerPath) { $installerArguments += @('--compiler', $CompilerPath) }
& $installerPython @installerArguments
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
