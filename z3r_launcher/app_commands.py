from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any

from .constants import STORED_ROM_NAME
from .errors import LauncherError
from .github_urls import normalize_launcher_update_api_url
from .pickers import pick_file, pick_folder
from .platform_paths import app_data_dir, display_path, is_appimage_runtime, is_flatpak_runtime, is_macos, os_name, resolve_scan_root, uses_downloaded_linux_game_executable
from .processes import action_result, open_external_url as open_external_url_process, open_path
from .project_files import rom_status, rom_storage_dir, rom_target_dir
from .settings import (
    dev_settings_snapshot,
    normalize_repo_clone_path,
    normalize_repo_scan_paths,
    repo_settings_snapshot,
    write_dev_settings,
    write_repo_settings,
)


def read_repo_settings() -> dict[str, Any]:
    return repo_settings_snapshot()


def save_repo_settings(scan_paths: list[str] | None = None, clone_path: str | None = None) -> dict[str, Any]:
    normalized_scan_paths = normalize_repo_scan_paths(scan_paths or [])
    normalized_clone_path = normalize_repo_clone_path(clone_path, normalized_scan_paths)
    write_repo_settings(normalized_scan_paths, normalized_clone_path)
    return repo_settings_snapshot()


def read_dev_settings() -> dict[str, Any]:
    return dev_settings_snapshot(normalize_launcher_update_api_url)


def save_dev_settings(launcher_update_api_url: str | None = None) -> dict[str, Any]:
    url = normalize_launcher_update_api_url(launcher_update_api_url or "")
    write_dev_settings(url)
    snapshot = read_dev_settings()
    snapshot["message"] = "Dev update path saved." if url else "Dev update path reset."
    return snapshot


def launcher_release_api_url() -> str:
    return read_dev_settings()["effective_launcher_update_api_url"]


def app_runtime_info() -> dict[str, Any]:
    default_root = resolve_scan_root(None)
    requires_scan_path = default_clone_requires_scan_path()
    return {
        "os": os_name(),
        "default_scan_root": display_path(default_root),
        "appimage": is_appimage_runtime(),
        "flatpak": is_flatpak_runtime(),
        "packaged_macos": is_packaged_macos(),
        "downloaded_linux_game_executable": uses_downloaded_linux_game_executable(),
        "default_clone_requires_scan_path": requires_scan_path,
        "default_clone_warning": default_clone_warning(requires_scan_path),
    }


def default_clone_requires_scan_path() -> bool:
    return is_flatpak_runtime() or is_packaged_macos()


def is_packaged_macos() -> bool:
    import sys

    return is_macos() and getattr(sys, "frozen", False)


def default_clone_warning(required: bool) -> str | None:
    if not required:
        return None
    return (
        "Flatpak and macOS DMG/app-bundle releases cannot clone into the default app location. "
        "Add a repo scan path, select it as the clone destination, then clone."
    )


def ensure_clone_scan_root(scan_root: str | None) -> None:
    if scan_root is None and default_clone_requires_scan_path():
        raise LauncherError(default_clone_warning(True) or "Choose a repo scan path before cloning from this packaged launcher.")


def choose_scan_root() -> str | None:
    return pick_folder("Select repo scan folder")


def open_external_url(url: str) -> None:
    open_external_url_process(url)
    return None


def stored_rom_status() -> dict[str, Any]:
    return rom_status()


def choose_and_store_rom() -> dict[str, Any] | None:
    selected_rom = pick_file("Select SFC ROM", [("SNES ROM", "*.sfc")])
    if not selected_rom:
        return None
    source_path = Path(selected_rom)
    if source_path.suffix.lower() != ".sfc":
        raise LauncherError("Select a .sfc ROM file.")
    storage = app_data_dir() / "roms"
    storage.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, storage / STORED_ROM_NAME)
    return rom_status(force_current=True)


def store_rom_upload(file_name: str, data_base64: str) -> dict[str, Any]:
    if not file_name.lower().endswith(".sfc"):
        raise LauncherError("Select a .sfc ROM file.")
    try:
        data = base64.b64decode(data_base64, validate=True)
    except ValueError as error:
        raise LauncherError(f"Could not read uploaded ROM data: {error}") from error
    if not data:
        raise LauncherError("The selected SFC file was empty.")
    storage = app_data_dir() / "roms"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / STORED_ROM_NAME).write_bytes(data)
    return rom_status(force_current=True)


def open_stored_rom_folder() -> dict[str, Any]:
    storage = rom_storage_dir()
    storage.mkdir(parents=True, exist_ok=True)
    open_path(storage, "ROM storage folder")
    return action_result(True, f"Opened ROM storage folder: {display_path(storage)}")


def sync_stored_rom_to_projects(project_paths: list[str]) -> dict[str, Any]:
    source_path = rom_storage_dir() / STORED_ROM_NAME
    if not source_path.is_file():
        return action_result(True, "No uploaded SFC is available to sync.")
    copied: list[str] = []
    for item in project_paths:
        project = Path(item)
        destination = rom_target_dir(project) / STORED_ROM_NAME
        if destination.is_file():
            continue
        shutil.copy2(source_path, destination)
        copied.append(display_path(destination))
    return action_result(True, f"SFC sync complete. {len(copied)} repo(s) updated.", "\n".join(copied))
