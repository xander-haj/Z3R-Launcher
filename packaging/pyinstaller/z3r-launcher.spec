# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller packaging recipe for the standalone Z3R Launcher desktop executable."""

import os
from pathlib import Path
import sys

import certifi
from PyInstaller.utils.hooks import collect_submodules


root = Path.cwd()
linux = sys.platform.startswith("linux")
REEXEC_ENV = "Z3R_LAUNCHER_PYINSTALLER_REEXEC"
SPEC_PATH = root / "packaging" / "pyinstaller" / "z3r-launcher.spec"
LINUX_PACKAGING_PYTHON = root / ".packaging-venv" / "bin" / "python"

LINUX_QT_EXCLUDES = [
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "webview.platforms.qt",
]
LINUX_BINARY_BASENAME_PREFIX_EXCLUDES = (
    "libgcc_s.so",
    "libstdc++.so",
)


def reexec_with_linux_packaging_python():
    """Restart PyInstaller with the system-Python venv when an older workflow uses hosted Python."""
    if not linux or os.environ.get(REEXEC_ENV):
        return

    try:
        current_python = Path(sys.executable).resolve()
    except OSError:
        current_python = Path(sys.executable)

    if not LINUX_PACKAGING_PYTHON.is_file():
        if "/hostedtoolcache/" in str(current_python):
            message = (
                "Linux AppImage packaging must run from .packaging-venv/bin/python. "
                "This workflow run is still using hosted-toolcache Python and did not create the system-Python "
                "packaging venv first; rerun from the updated release workflow."
            )
            raise SystemExit(message)
        return

    try:
        packaging_python = LINUX_PACKAGING_PYTHON.resolve()
    except OSError:
        packaging_python = LINUX_PACKAGING_PYTHON

    if current_python == packaging_python:
        return

    os.environ[REEXEC_ENV] = "1"
    os.execv(
        str(packaging_python),
        [str(packaging_python), "-m", "PyInstaller", "--clean", str(SPEC_PATH)],
    )


def binary_entry_names(entry):
    """Return path basenames PyInstaller may use to identify a collected binary."""
    names = []
    for value in entry[:2]:
        if value:
            names.append(Path(str(value)).name)
    return names


def should_exclude_linux_binary(entry):
    """Return True for Linux runtime libraries that must come from the host system."""
    for name in binary_entry_names(entry):
        for prefix in LINUX_BINARY_BASENAME_PREFIX_EXCLUDES:
            if name == prefix or name.startswith(f"{prefix}."):
                return True
    return False


hiddenimports = ["tkinter", "tkinter.filedialog", "certifi"]
if not linux:
    hiddenimports += collect_submodules("webview")
binaries = []
datas = [
    (str(root / "src"), "src"),
    (str(root / "dev_tools" / "link_sprite_editor"), "dev_tools/link_sprite_editor"),
    (str(root / "resources"), "resources"),
    (certifi.where(), "certifi"),
]
excludes = []

if linux:
    reexec_with_linux_packaging_python()
    excludes += LINUX_QT_EXCLUDES

hiddenimports = list(dict.fromkeys(hiddenimports))
excludes = list(dict.fromkeys(excludes))

if sys.platform == "darwin":
    icon = root / "resources" / "icons" / "icon.icns"
elif sys.platform == "win32":
    icon = root / "resources" / "icons" / "icon.ico"
else:
    icon = None

a = Analysis(
    [str(root / "packaging" / "pyinstaller" / "z3r_launcher_entry.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

if linux:
    a.binaries = [entry for entry in a.binaries if not should_exclude_linux_binary(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="z3r-launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon and icon.is_file() else None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Z3R Launcher.app",
        icon=str(icon) if icon and icon.is_file() else None,
        bundle_identifier="io.github.xander_haj.Z3RLauncher",
    )
