from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__
from .app_commands import launcher_release_api_url
from .constants import GITHUB_TOKEN_ENV
from .errors import LauncherError
from .platform_paths import display_path, resources_dir


def fetch_latest_release(update_dir: Path) -> dict[str, Any]:
    release_json = update_dir / "latest-release.json"
    download_url_to_file(launcher_release_api_url(), release_json, github_api=True)
    try:
        release = json.loads(release_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError(f"Could not parse GitHub release metadata: {error}") from error
    if not release.get("tag_name"):
        raise LauncherError("GitHub returned a release without a tag name.")
    return release


def download_release_asset(asset: dict[str, Any], update_dir: Path) -> Path:
    file_name = Path(asset["name"]).name
    if not file_name:
        raise LauncherError(f"Release asset has an invalid filename: {asset.get('name')}")
    target = update_dir / file_name
    download_url_to_file(asset["browser_download_url"], target, github_api=False)
    return target


def exact_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset
    available = ", ".join(asset.get("name", "") for asset in release.get("assets", []))
    raise LauncherError(f"Release {release.get('tag_name')} does not include required update asset {name}. Available assets: {available}.")


def first_release_asset(release: dict[str, Any], names: list[str]) -> dict[str, Any]:
    assets = release.get("assets", [])
    for name in names:
        for asset in assets:
            if asset.get("name") == name:
                return asset
    available = ", ".join(asset.get("name", "") for asset in release.get("assets", []))
    expected = ", ".join(names)
    raise LauncherError(f"Release {release.get('tag_name')} does not include a required update asset. Expected one of: {expected}. Available assets: {available}.")


def updater_ssl_context() -> Any:
    try:
        import ssl
    except ImportError as error:
        raise LauncherError("Launcher Python was built without SSL support, so HTTPS updates cannot be downloaded.") from error

    try:
        import certifi

        cafile = Path(certifi.where())
        if cafile.is_file():
            return ssl.create_default_context(cafile=display_path(cafile))
    except Exception:
        pass
    return ssl.create_default_context()


def download_url_to_file(url: str, destination: Path, github_api: bool) -> None:
    partial = destination.with_suffix(destination.suffix + ".download")
    for path in (partial, destination):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    headers = {"User-Agent": "Z3R-Launcher-Updater"}
    if github_api:
        headers["Accept"] = "application/vnd.github+json"
    token = github_update_token(url)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    errors: list[str] = []
    context = updater_ssl_context() if url.lower().startswith("https://") else None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=300, context=context) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            partial.replace(destination)
            return
        except (OSError, urllib.error.URLError) as error:
            errors.append(str(error))
            time.sleep(2 + attempt)
    raise LauncherError(f"Could not download update file: {'; '.join(errors)}")


def github_update_token(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    if host.lower() not in {"api.github.com", "github.com"}:
        return ""
    return os.environ.get(GITHUB_TOKEN_ENV, "").strip()


def current_update_version() -> str:
    env_tag = os.environ.get("LAUNCHER_RELEASE_TAG")
    if env_tag:
        return env_tag
    try:
        build_info = json.loads((resources_dir() / "build-info.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        build_info = {}
    release_tag = str(build_info.get("release_tag") or "").strip()
    return release_tag or __version__


def compare_versions(left: str, right: str) -> int:
    left_parts = version_parts(left)
    right_parts = version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    for index in range(max_len):
        left_value = left_parts[index] if index < len(left_parts) else 0
        right_value = right_parts[index] if index < len(right_parts) else 0
        if left_value < right_value:
            return -1
        if left_value > right_value:
            return 1
    return 0


def version_parts(value: str) -> list[int]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    return parts or [0]
