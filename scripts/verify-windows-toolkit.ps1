# Verifies that the Windows toolkit exists before packaging the Windows installer.
# This prevents release assets from being published when bundled-tools/windows only
# contains the committed placeholder file.
param(
  [string]$ToolkitRoot = "bundled-tools/windows",
  [int64]$MinimumBytes = 50000000
)

$ErrorActionPreference = "Stop"

# Resolve relative to the repository root so CI and local shells behave the same.
$repoRoot = Split-Path -Parent $PSScriptRoot
$toolRoot = Join-Path $repoRoot $ToolkitRoot

if (!(Test-Path $toolRoot)) {
  throw "Windows toolkit folder does not exist: $toolRoot"
}

$requiredFiles = @(
  "git/cmd/git.exe",
  "python/tools/python.exe",
  "tcc/tcc.exe",
  "sdl2/include/SDL.h",
  "sdl2/lib/x64/SDL2.dll"
)

foreach ($file in $requiredFiles) {
  $path = Join-Path $toolRoot $file

  if (!(Test-Path $path)) {
    throw "Windows toolkit is missing required file: $file"
  }
}

$files = Get-ChildItem -Path $toolRoot -Recurse -File
$totalBytes = ($files | Measure-Object -Property Length -Sum).Sum

if ($totalBytes -lt $MinimumBytes) {
  throw "Windows toolkit is too small ($totalBytes bytes). It was probably not downloaded."
}

Write-Host "Windows toolkit file count: $($files.Count)"
Write-Host "Windows toolkit total bytes: $totalBytes"
Write-Host "Windows toolkit sample:"
$files |
  Select-Object -First 40 |
  ForEach-Object {
    $relativePath = $_.FullName.Substring($toolRoot.Length + 1)
    Write-Host " - $relativePath"
  }
