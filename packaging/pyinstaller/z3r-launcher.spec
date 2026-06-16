# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

import certifi


root = Path.cwd()
datas = [
    (str(root / "src"), "src"),
    (str(root / "resources"), "resources"),
    (certifi.where(), "certifi"),
]
if sys.platform == "darwin":
    icon = root / "resources" / "icons" / "icon.icns"
elif sys.platform == "win32":
    icon = root / "resources" / "icons" / "icon.ico"
else:
    icon = None

a = Analysis(
    [str(root / "packaging" / "pyinstaller" / "z3r_launcher_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinter", "tkinter.filedialog", "certifi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
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
