from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import APP_IDENTIFIER, APP_NAME, DEV_SETTINGS_FILE, LAUNCHER_RELEASE_API_URL, REPO_SETTINGS_FILE
from .platform_paths import app_data_dir, is_macos, is_windows


def dev_settings_path() -> Path:
    return app_data_dir() / DEV_SETTINGS_FILE


def read_dev_settings_file() -> dict[str, Any]:
    path = dev_settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return settings if isinstance(settings, dict) else {}


def write_dev_settings(launcher_update_api_url: str, launcher_update_source: str = "default") -> None:
    path = dev_settings_path()
    source = normalize_update_source(launcher_update_source, bool(launcher_update_api_url), legacy=False)
    if not launcher_update_api_url and source == "default":
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "launcher_update_api_url": launcher_update_api_url,
        "launcher_update_source": source,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dev_settings_snapshot(normalize_url) -> dict[str, Any]:
    settings = read_dev_settings_file()
    override = settings.get("launcher_update_api_url")
    override_url = normalize_url(override) if isinstance(override, str) else ""
    source = normalize_update_source(settings.get("launcher_update_source"), bool(override_url), legacy=True)
    effective_url = override_url if source == "dev" else LAUNCHER_RELEASE_API_URL
    return {
        "launcher_update_api_url": override_url,
        "launcher_update_source": source,
        "default_launcher_update_api_url": LAUNCHER_RELEASE_API_URL,
        "effective_launcher_update_api_url": effective_url,
    }


def normalize_update_source(value: Any, has_dev_url: bool, legacy: bool) -> str:
    if value == "dev" and has_dev_url:
        return "dev"
    if value == "default":
        return "default"
    return "dev" if legacy and has_dev_url else "default"


def repo_settings_path() -> Path:
    return app_data_dir() / REPO_SETTINGS_FILE


def read_repo_settings_file() -> dict[str, Any]:
    path = repo_settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return settings if isinstance(settings, dict) else {}


def normalize_repo_scan_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    paths: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        path = item.strip()
        if not path or "\0" in path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def normalize_repo_clone_path(value: Any, scan_paths: list[str]) -> str:
    if not isinstance(value, str):
        return ""

    path = value.strip()
    if not path or "\0" in path:
        return ""
    return path if path in scan_paths else ""


def repo_settings_snapshot() -> dict[str, Any]:
    settings = read_repo_settings_file()
    scan_paths = normalize_repo_scan_paths(settings.get("scan_paths"))
    clone_path = normalize_repo_clone_path(settings.get("clone_path"), scan_paths)
    return {"scan_paths": scan_paths, "clone_path": clone_path or None}


def write_repo_settings(scan_paths: list[str], clone_path: str) -> None:
    path = repo_settings_path()
    if not scan_paths and not clone_path:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"scan_paths": scan_paths}
    if clone_path:
        payload["clone_path"] = clone_path
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def legacy_app_data_dirs() -> list[Path]:
    paths: list[Path] = []
    home = Path.home()

    if is_windows():
        for env_name in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env_name)
            if base:
                paths.append(Path(base) / APP_IDENTIFIER)
                paths.append(Path(base) / APP_NAME)
    elif is_macos():
        paths.append(home / "Library" / "Application Support" / APP_IDENTIFIER)
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            paths.append(Path(xdg) / APP_IDENTIFIER)
        paths.append(home / ".local" / "share" / APP_IDENTIFIER)

    current = app_data_dir()
    return [path for path in paths if path != current]
