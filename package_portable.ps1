# Assemble a portable copy of the runtime files, ready to move to another Windows machine.
# Runtime set = run.cmd + run.ps1 + rightmenu\ (source only; no __pycache__, no tests).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File package_portable.ps1
#   powershell -ExecutionPolicy Bypass -File package_portable.ps1 -Destination D:\RMM -Zip
#
# ASCII-only on purpose: PowerShell 5.1 parses BOM-less non-ASCII .ps1 as ANSI and breaks.

param(
    [string]$Destination = (Join-Path $PSScriptRoot 'release'),
    [switch]$Zip
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$runtimeFiles = @('run.cmd', 'run.ps1', 'README.md')
$runtimeDirs = @('rightmenu')

if (Test-Path -LiteralPath $Destination) {
    Remove-Item -LiteralPath $Destination -Recurse -Force
}
New-Item -ItemType Directory -Path $Destination | Out-Null

foreach ($file in $runtimeFiles) {
    $source = Join-Path $root $file
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $Destination
    }
}

foreach ($dir in $runtimeDirs) {
    $sourceRoot = Join-Path $root $dir
    $targetRoot = Join-Path $Destination $dir
    Get-ChildItem -LiteralPath $sourceRoot -Recurse -File |
        Where-Object { $_.Extension -eq '.py' -and $_.FullName -notmatch '\\__pycache__\\' } |
        ForEach-Object {
            $relative = $_.FullName.Substring($sourceRoot.Length).TrimStart('\')
            $target = Join-Path $targetRoot $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target
        }
}

# Stamp the release with version + build date, read from rightmenu\__init__.py.
$initText = Get-Content -LiteralPath (Join-Path $root 'rightmenu\__init__.py') -Raw
$version = 'unknown'
if ($initText -match '__version__\s*=\s*"([^"]+)"') { $version = $Matches[1] }
$stamp = @(
    "rightmenu release $version"
    "built: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    "requires: Windows 10/11 + Python 3.13+ with tkinter"
    "run: double-click run.cmd"
)
Set-Content -LiteralPath (Join-Path $Destination 'VERSION.txt') -Value $stamp -Encoding UTF8

$staged = Get-ChildItem -LiteralPath $Destination -Recurse -File
Write-Host ("Portable bundle ready: {0}" -f $Destination)
Write-Host ("Files staged: {0}" -f $staged.Count)
$staged | ForEach-Object { Write-Host ("  " + $_.FullName.Substring($Destination.Length).TrimStart('\')) }

if ($Zip) {
    $zipPath = "$Destination.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $Destination '*') -DestinationPath $zipPath
    Write-Host ("Archive: {0}" -f $zipPath)
}

Write-Host ''
Write-Host 'On the target machine: install Python 3.13+ (with tkinter), then double-click run.cmd.'
Write-Host 'Do NOT copy %APPDATA%\RightMenuManager (journal.json / aliases.json): it is per-machine state.'