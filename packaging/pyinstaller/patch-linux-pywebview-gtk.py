"""Patch pywebview's GTK backend for Linux AppImage software rendering."""

from __future__ import annotations

import importlib.util
from pathlib import Path


TARGET_MODULE = "webview.platforms.gtk"
ORIGINAL_SETTINGS_BLOCK = """        webkit_settings.enable_webgl = True
        webkit_settings.javascript_can_access_clipboard = True
"""
PATCHED_SETTINGS_BLOCK = """        webkit_settings.enable_webgl = False
        try:
            webkit_settings.hardware_acceleration_policy = webkit.HardwareAccelerationPolicy.NEVER
        except (AttributeError, TypeError):
            pass
        webkit_settings.javascript_can_access_clipboard = True
"""


def module_source_path(module_name: str) -> Path:
    """Return the installed source path for a module that PyInstaller will freeze."""
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise SystemExit(f"Could not find installed module: {module_name}")
    path = Path(spec.origin)
    if not path.is_file():
        raise SystemExit(f"Installed module is not a file: {path}")
    return path


def patch_pywebview_gtk(path: Path) -> None:
    """Disable WebKitGTK GPU features in pywebview's installed GTK backend source."""
    source = path.read_text(encoding="utf-8")
    if PATCHED_SETTINGS_BLOCK in source:
        return
    if ORIGINAL_SETTINGS_BLOCK not in source:
        message = f"pywebview GTK backend did not match the expected WebKit settings block: {path}"
        raise SystemExit(message)
    path.write_text(source.replace(ORIGINAL_SETTINGS_BLOCK, PATCHED_SETTINGS_BLOCK, 1), encoding="utf-8")


def main() -> None:
    """Patch the installed pywebview GTK backend used by the Linux PyInstaller build."""
    patch_pywebview_gtk(module_source_path(TARGET_MODULE))


if __name__ == "__main__":
    main()
