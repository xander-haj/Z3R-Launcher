from __future__ import annotations

from pathlib import Path


def write_windows_update_script(path: Path) -> None:
    path.write_text(r'''
param(
  [Parameter(Mandatory = $true)][int]$LauncherPid,
  [Parameter(Mandatory = $true)][string]$Downloaded,
  [Parameter(Mandatory = $true)][string]$Target,
  [Parameter(Mandatory = $true)][string]$Relaunch,
  [Parameter(Mandatory = $true)][string]$Log
)
$ErrorActionPreference = "Stop"
function Write-UpdateLog([string]$Message) {
  $stamp = Get-Date -Format o
  Add-Content -LiteralPath $Log -Value "$stamp $Message"
}
function Move-WithRetry([string]$Source, [string]$Destination) {
  for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
      Move-Item -LiteralPath $Source -Destination $Destination -Force
      return
    } catch {
      if ($attempt -eq 20) {
        throw
      }
      Start-Sleep -Milliseconds 250
    }
  }
}
try {
  Write-UpdateLog "Waiting for launcher process $LauncherPid to close."
  Wait-Process -Id $LauncherPid -ErrorAction SilentlyContinue
  if (!(Test-Path -LiteralPath $Downloaded)) {
    throw "Downloaded launcher exe was not found: $Downloaded"
  }
  $targetDirectory = Split-Path -Parent $Target
  if ($targetDirectory -and !(Test-Path -LiteralPath $targetDirectory)) {
    New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
  }
  $temporaryTarget = "$Target.new"
  Remove-Item -LiteralPath $temporaryTarget -Force -ErrorAction SilentlyContinue
  Write-UpdateLog "Moving downloaded launcher exe into place."
  Move-WithRetry -Source $Downloaded -Destination $temporaryTarget
  Move-WithRetry -Source $temporaryTarget -Destination $Target
  if (Test-Path -LiteralPath $Relaunch) {
    Write-UpdateLog "Relaunching updated launcher."
    Start-Process -FilePath $Relaunch
  }
} catch {
  Write-UpdateLog $_.Exception.Message
  exit 1
}
'''.lstrip(), encoding="utf-8")


def write_macos_update_script(path: Path) -> None:
    path.write_text(r'''#!/bin/sh
set -eu
pid="$1"
dmg="$2"
mount="$3"
target="$4"
app_name="$5"
log="$6"
exec > "$log" 2>&1
while kill -0 "$pid" 2>/dev/null; do
  sleep 1
done
rm -rf "$mount"
mkdir -p "$mount"
hdiutil attach -nobrowse -quiet -mountpoint "$mount" "$dmg"
trap 'hdiutil detach "$mount" -quiet >/dev/null 2>&1 || true; rm -rf "$mount"' EXIT
source_app="$mount/$app_name"
if [ ! -d "$source_app" ]; then
  source_app="$(find "$mount" -maxdepth 2 -name '*.app' -type d | head -n 1)"
fi
if [ -z "$source_app" ] || [ ! -d "$source_app" ]; then
  echo "No app bundle was found in the mounted DMG."
  exit 2
fi
rm -rf "$target"
ditto "$source_app" "$target"
xattr -dr com.apple.quarantine "$target" >/dev/null 2>&1 || true
open "$target"
''', encoding="utf-8")


def write_appimage_update_script(path: Path) -> None:
    path.write_text(r'''#!/bin/sh
set -eu
pid="$1"
downloaded="$2"
target="$3"
log="$4"
exec > "$log" 2>&1
while kill -0 "$pid" 2>/dev/null; do
  sleep 1
done
chmod +x "$downloaded"
tmp="${target}.updating"
mv "$downloaded" "$tmp"
mv "$tmp" "$target"
chmod +x "$target"
"$target" >/dev/null 2>&1 &
''', encoding="utf-8")
