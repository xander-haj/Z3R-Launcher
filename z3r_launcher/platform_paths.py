from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from .constants import APP_IDENTIFIER, APP_NAME, FLATPAK_INFO_PATH
from .errors import LauncherError


def display_path(path: Path | str) -> str:
    return str(Path(path))


def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return platform.system().lower() or sys.platform


def is_windows() -> bool:
    return os_name() == "windows"


def is_macos() -> bool:
    return os_name() == "macos"


def is_linux() -> bool:
    return os_name() == "linux"


def is_flatpak_runtime() -> bool:
    return is_linux() and FLATPAK_INFO_PATH.is_file()


def is_appimage_runtime() -> bool:
    return is_linux() and bool(os.environ.get("APPIMAGE"))


def uses_downloaded_linux_game_executable() -> bool:
    return is_linux() and (is_appimage_runtime() or is_flatpak_runtime())


def launcher_root() -> Path:
    override = os.environ.get("Z3R_LAUNCHER_ROOT")
    if override:
        return Path(override).resolve()

    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root).resolve()
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def resources_dir() -> Path:
    return launcher_root() / "resources"


def static_dir() -> Path:
    return launcher_root() / "src"


def link_sprite_devtools_dir() -> Path:
    return launcher_root() / "dev_tools" / "link_sprite_editor"


def bundled_tools_dir() -> Path:
    return launcher_root() / "bundled-tools"


def current_executable_path() -> Path:
    return Path(sys.executable).resolve()


def bundled_tools_candidates() -> list[Path]:
    candidates: list[Path] = []
    if is_windows() and getattr(sys, "frozen", False):
        candidates.append(current_executable_path().parent / "bundled-tools")
    candidates.append(bundled_tools_dir())
    return candidates


def windows_tools_dir() -> Path:
    for root in bundled_tools_candidates():
        candidate = root / "windows"
        if candidate.is_dir():
            return candidate
    return bundled_tools_candidates()[0] / "windows"


def hidden_subprocess_kwargs() -> dict[str, int]:
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0) if is_windows() else 0
    return {"creationflags": flag} if flag else {}


def app_data_dir() -> Path:
    override = os.environ.get("Z3R_LAUNCHER_DATA_DIR")
    if override:
        return Path(override)

    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME
    if is_macos():
        return Path.home() / "Library" / "Application Support" / APP_IDENTIFIER

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "z3r-launcher"
    return Path.home() / ".local" / "share" / "z3r-launcher"


def update_work_dir() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME / "updates"
    if is_macos():
        return Path.home() / "Library" / "Caches" / APP_NAME / "updates"
    cache = os.environ.get("XDG_CACHE_HOME")
    if cache:
        return Path(cache) / "z3r-launcher" / "updates"
    if Path.home():
        return Path.home() / ".cache" / "z3r-launcher" / "updates"
    return Path(tempfile.gettempdir()) / "z3r-launcher-updates"


def default_scan_root() -> Path:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return Path(appimage).resolve().parent

    if getattr(sys, "frozen", False):
        exe_dir = current_executable_path().parent
        if is_macos():
            bundle_parent = macos_bundle_parent(exe_dir)
            if bundle_parent:
                return bundle_parent
        return exe_dir

    return launcher_root().parent


def macos_bundle_parent(exe_dir: Path) -> Path | None:
    contents_dir = exe_dir.parent
    app_dir = contents_dir.parent
    if exe_dir.name == "MacOS" and contents_dir.name == "Contents" and app_dir.suffix == ".app":
        return app_dir.parent
    return None


def resolve_scan_root(scan_root: str | None = None) -> Path:
    if scan_root:
        path = Path(scan_root)
        if path.is_dir():
            return path
        raise LauncherError(f"Selected scan folder does not exist: {display_path(path)}")
    return default_scan_root()


def current_macos_bundle_path() -> Path:
    executable = current_executable_path()
    app_bundle = executable.parent.parent.parent
    if app_bundle.suffix == ".app":
        return app_bundle
    raise LauncherError("macOS self-update requires running from the packaged .app bundle.")


def current_appimage_path() -> Path:
    appimage = os.environ.get("APPIMAGE")
    if not appimage:
        raise LauncherError("Linux self-update requires running the AppImage or Flatpak package.")
    path = Path(appimage)
    if not path.is_file():
        raise LauncherError(f"The APPIMAGE path does not exist anymore: {display_path(path)}")
    return path
