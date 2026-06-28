from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .constants import PROJECT_RELEASES
from .errors import LauncherError
from .linux_game_downloads import (
    fetch_project_latest_release,
    github_project_release_spec,
    github_slug_from_remote,
    project_remote_origin,
)
from .platform_paths import update_work_dir


def read_project_release_version(project_path: str) -> dict[str, Any]:
    """Return a display version only when GitHub returns a latest release tag."""
    project = Path(project_path)
    if not project.is_dir() or not (project / ".git").exists():
        return unavailable("Project is not a Git repository.")

    remote = project_remote_origin(project)
    slug = github_slug_from_remote(remote) if remote else None
    if not slug:
        return unavailable("Project remote is not a GitHub repository.")

    spec = PROJECT_RELEASES.get(slug) or github_project_release_spec(slug)
    release_dir = update_work_dir() / "project-release-versions" / str(spec["id"])
    try:
        release_dir.mkdir(parents=True, exist_ok=True)
        release = fetch_project_latest_release(spec, release_dir)
    except (LauncherError, OSError) as error:
        return unavailable(str(error))

    tag = str(release.get("tag_name") or "").strip()
    version = display_release_version(tag)
    if not version:
        return unavailable("Latest release tag did not contain a version number.")
    return {"available": True, "version": version, "tag": tag, "source": str(spec["api_url"])}


def display_release_version(tag: str) -> str:
    """Normalize a release tag into the vxxx shape shown on cards."""
    match = re.search(r"\d+(?:\.\d+)*", tag)
    return f"v{match.group(0)}" if match else ""


def unavailable(detail: str) -> dict[str, Any]:
    return {"available": False, "version": None, "tag": None, "detail": detail}
