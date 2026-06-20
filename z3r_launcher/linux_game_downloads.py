from __future__ import annotations

import json
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from .constants import LINUX_GAME_ARCHIVE_SUFFIXES, LINUX_GAME_EXECUTABLE_NAMES, PROJECT_RELEASES
from .errors import LauncherError
from .platform_paths import display_path, update_work_dir
from .processes import action_result, decode_output, git_program, run_process
from .project_files import make_executable
from .update_downloads import download_release_asset, download_url_to_file


def install_prebuilt_linux_game_executable(project: Path) -> dict[str, Any]:
    spec = project_release_spec(project)
    download_dir = update_work_dir() / "game-executables" / str(spec["id"])
    download_dir.mkdir(parents=True, exist_ok=True)
    release = fetch_project_latest_release(spec, download_dir)
    asset = project_linux_executable_asset(release, spec)
    downloaded = download_release_asset(asset, download_dir)
    installed = install_linux_game_executable_asset(downloaded, project)
    asset_name = asset.get("name") or downloaded.name
    return action_result(
        True,
        f"{spec['label']} executable {release['tag_name']} downloaded.",
        f"Asset: {asset_name}\nExecutable: {display_path(installed)}",
    )


def project_release_spec(project: Path) -> dict[str, Any]:
    remote = project_remote_origin(project)
    slug = github_slug_from_remote(remote) if remote else None
    supported = ", ".join(spec["label"] for spec in PROJECT_RELEASES.values())
    if slug:
        if slug in PROJECT_RELEASES:
            return PROJECT_RELEASES[slug]
        raise LauncherError(f"Prebuilt Linux executable downloads are only configured for {supported}. Remote origin is {remote}.")
    if remote:
        raise LauncherError(f"Prebuilt Linux executable downloads are only configured for {supported}. Remote origin is {remote}.")

    folder_slug = f"xander-haj/{project.name.lower()}"
    if folder_slug in PROJECT_RELEASES:
        return PROJECT_RELEASES[folder_slug]
    raise LauncherError(f"Prebuilt Linux executable downloads are only configured for {supported}. Could not read this project's GitHub remote.")


def project_remote_origin(project: Path) -> str | None:
    if not (project / ".git").exists():
        return None
    try:
        output = run_process(git_program(), ["config", "--get", "remote.origin.url"], cwd=project, capture=True)
    except OSError:
        return None
    if output.returncode != 0:
        return None
    remote = decode_output(output.stdout).strip()
    return remote or None


def github_slug_from_remote(remote: str) -> str | None:
    value = remote.strip()
    lowered = value.lower()
    if lowered.startswith("https://github.com/"):
        repo_part = value[len("https://github.com/"):]
    elif lowered.startswith("git@github.com:"):
        repo_part = value[len("git@github.com:"):]
    elif lowered.startswith("ssh://git@github.com/"):
        repo_part = value[len("ssh://git@github.com/"):]
    else:
        return None

    repo_part = repo_part.split("?", 1)[0].split("#", 1)[0].strip("/")
    parts = repo_part.split("/")
    if len(parts) < 2:
        return None
    owner = parts[0].lower()
    repo = parts[1].removesuffix(".git").lower()
    return f"{owner}/{repo}" if owner and repo else None


def fetch_project_latest_release(spec: dict[str, Any], update_dir: Path) -> dict[str, Any]:
    release_json = update_dir / "latest-release.json"
    download_url_to_file(str(spec["api_url"]), release_json, github_api=True)
    try:
        release = json.loads(release_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LauncherError(f"Could not parse {spec['label']} release metadata: {error}") from error
    if not release.get("tag_name"):
        raise LauncherError(f"GitHub returned a {spec['label']} release without a tag name.")
    return release


def project_linux_executable_asset(release: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    assets = release.get("assets", [])
    for expected_name in spec["preferred_assets"]:
        for asset in assets:
            if asset.get("name") == expected_name:
                return asset

    candidates = [
        asset
        for asset in assets
        if is_linux_game_executable_asset_name(str(asset.get("name") or ""))
    ]
    if candidates:
        candidates.sort(
            key=lambda asset: linux_game_executable_asset_score(str(asset.get("name") or ""), spec),
            reverse=True,
        )
        return candidates[0]

    available = ", ".join(str(asset.get("name") or "") for asset in assets)
    expected = ", ".join(spec["preferred_assets"])
    raise LauncherError(
        f"Release {release.get('tag_name')} does not include a Linux executable archive for {spec['label']}. "
        f"Expected {expected}, or a linux x64 tar/zip asset that is not an AppImage/Flatpak. Available assets: {available}."
    )


def is_linux_game_executable_asset_name(name: str) -> bool:
    lower = name.lower()
    if lower in LINUX_GAME_EXECUTABLE_NAMES:
        return True
    if not any(lower.endswith(suffix) for suffix in LINUX_GAME_ARCHIVE_SUFFIXES):
        return False
    if "linux" not in lower or not any(token in lower for token in ("x64", "x86_64", "amd64")):
        return False
    blocked = ("appimage", "flatpak", "windows", "macos", "darwin", "apple", "silicon", "arm64", "aarch64")
    return not any(token in lower for token in blocked)


def linux_game_executable_asset_score(name: str, spec: dict[str, Any]) -> int:
    lower = name.lower()
    score = 100 if lower in LINUX_GAME_EXECUTABLE_NAMES else 0
    score += {".tar.gz": 40, ".tgz": 35, ".tar": 30, ".zip": 20}.get(next((s for s in LINUX_GAME_ARCHIVE_SUFFIXES if lower.endswith(s)), ""), 0)
    return score + (10 if str(spec["label"]).lower() in lower else 0)


def install_linux_game_executable_asset(asset_path: Path, project: Path) -> Path:
    destination = project / "zelda3"
    temporary = project / ".zelda3.download"
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass

    try:
        if is_tar_archive(asset_path):
            extract_linux_game_executable_from_tar(asset_path, temporary)
        elif asset_path.suffix.lower() == ".zip":
            extract_linux_game_executable_from_zip(asset_path, temporary)
        elif asset_path.name.lower() in LINUX_GAME_EXECUTABLE_NAMES:
            shutil.copy2(asset_path, temporary)
        else:
            raise LauncherError(f"Downloaded asset is not a supported Linux executable archive: {asset_path.name}")

        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise LauncherError("Downloaded game executable was empty.")
        make_executable(temporary)
        temporary.replace(destination)
        make_executable(destination)
        return destination
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise LauncherError(f"Could not install downloaded game executable: {error}") from error
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def is_tar_archive(path: Path) -> bool:
    return path.name.lower().endswith((".tar.gz", ".tgz", ".tar"))


def extract_linux_game_executable_from_tar(asset_path: Path, destination: Path) -> None:
    with tarfile.open(asset_path, "r:*") as archive:
        member = first_tar_executable_member(archive.getmembers())
        if not member:
            raise LauncherError(f"{asset_path.name} does not contain zelda3 or zelda3.real.")
        source = archive.extractfile(member)
        if source is None:
            raise LauncherError(f"Could not read {member.name} from {asset_path.name}.")
        with source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


def first_tar_executable_member(members: list[tarfile.TarInfo]) -> tarfile.TarInfo | None:
    for executable_name in LINUX_GAME_EXECUTABLE_NAMES:
        for member in members:
            if member.isfile() and Path(member.name).name == executable_name:
                return member
    return None


def extract_linux_game_executable_from_zip(asset_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(asset_path) as archive:
        info = first_zip_executable_member(archive.infolist())
        if not info:
            raise LauncherError(f"{asset_path.name} does not contain zelda3 or zelda3.real.")
        with archive.open(info, "r") as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


def first_zip_executable_member(members: list[zipfile.ZipInfo]) -> zipfile.ZipInfo | None:
    for executable_name in LINUX_GAME_EXECUTABLE_NAMES:
        for member in members:
            if not member.is_dir() and Path(member.filename).name == executable_name:
                return member
    return None
