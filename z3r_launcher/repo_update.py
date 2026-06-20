from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import LauncherError
from .platform_paths import display_path
from .processes import action_result, decode_output, git_program, run_process


def preview_repo_update(project_path: str) -> dict[str, Any]:
    project = repo_project_path(project_path)
    ensure_git_repo(project)
    git_output(project, ["fetch", "--prune"])
    upstream = upstream_ref(project)
    behind = behind_count(project, upstream)
    changes = upstream_changes(project, upstream)
    return {
        "project_path": display_path(project),
        "upstream": upstream,
        "behind_count": behind,
        "changes": changes,
        "warnings": update_warnings(changes),
        "can_apply": bool(changes),
    }


def apply_repo_update(project_path: str, selected_files: list[str]) -> dict[str, Any]:
    project = repo_project_path(project_path)
    ensure_git_repo(project)
    git_output(project, ["fetch", "--prune"])
    upstream = upstream_ref(project)
    changes = upstream_changes(project, upstream)
    changes_by_path = {change["path"]: change for change in changes}
    selected = [path for path in selected_files if path.strip()]
    if not selected:
        return action_result(False, "No repo update files were selected.")
    for path in selected:
        if not is_safe_repo_path(path):
            raise LauncherError(f"Unsafe repo update path was rejected: {path}")
        if path not in changes_by_path:
            raise LauncherError(f"Selected file is not in the update preview: {path}")
    applied: list[str] = []
    for path in selected:
        apply_change(project, upstream, changes_by_path[path])
        applied.append(path)
    return action_result(True, "Selected repo changes applied.", "\n".join(applied))


def repo_project_path(project_path: str) -> Path:
    project = Path(project_path)
    if not project.is_dir():
        raise LauncherError(f"Project folder does not exist: {display_path(project)}")
    return project


def ensure_git_repo(project: Path) -> None:
    if not (project / ".git").exists():
        raise LauncherError("This project is not a Git repo clone.")


def git_output(project: Path, args: list[str]) -> str:
    try:
        output = run_process(git_program(), args, cwd=project, capture=True)
    except OSError as error:
        raise LauncherError(f"Could not run git in {display_path(project)}: {error}") from error
    if output.returncode != 0:
        detail = decode_output(output.stderr).strip()
        raise LauncherError(detail or f"git exited with status {output.returncode}")
    return decode_output(output.stdout)


def git_success(project: Path, args: list[str]) -> bool:
    try:
        return run_process(git_program(), args, cwd=project, capture=True).returncode == 0
    except OSError:
        return False


def upstream_ref(project: Path) -> str:
    try:
        upstream = git_output(project, ["rev-parse", "--abbrev-ref", "@{upstream}"]).strip()
        if upstream:
            return upstream
    except LauncherError:
        pass
    try:
        branch = git_output(project, ["branch", "--show-current"]).strip()
    except LauncherError:
        branch = ""
    candidates = [f"origin/{branch}"] if branch else []
    candidates.extend(["origin/main", "origin/master"])
    for candidate in candidates:
        if git_success(project, ["rev-parse", "--verify", "--quiet", candidate]):
            return candidate
    raise LauncherError("No upstream branch was found for this repo.")


def behind_count(project: Path, upstream: str) -> int:
    count = git_output(project, ["rev-list", "--count", f"HEAD..{upstream}"])
    try:
        return int(count.strip())
    except ValueError as error:
        raise LauncherError(f"Could not read repo update count: {error}") from error


def upstream_changes(project: Path, upstream: str) -> list[dict[str, Any]]:
    output = git_output(project, ["diff", "--name-status", f"HEAD..{upstream}", "--"])
    changes = [change for line in output.splitlines() if (change := parse_name_status_line(line))]
    return [change for change in changes if not change_matches_upstream(project, upstream, change)]


def parse_name_status_line(line: str) -> dict[str, Any] | None:
    parts = line.split("\t")
    if not parts or not parts[0].strip():
        return None
    status_value = parts[0].strip()
    if status_value.startswith(("R", "C")):
        if len(parts) < 3:
            return None
        return {"path": parts[2].strip(), "old_path": parts[1].strip(), "status": status_value, "label": change_label(status_value)}
    if len(parts) < 2:
        return None
    return {"path": parts[1].strip(), "old_path": None, "status": status_value, "label": change_label(status_value)}


def change_label(status_value: str) -> str:
    labels = {"A": "Added", "C": "Copied", "D": "Deleted", "M": "Modified", "R": "Renamed", "T": "Type changed"}
    return labels.get(status_value[:1], "Changed")


def update_warnings(changes: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for change in changes:
        if change.get("old_path"):
            paths.append(change["old_path"])
        paths.append(change["path"])
    warnings: list[str] = []
    if any(is_zelda_ini_path(path) for path in paths):
        warnings.append("zelda3.ini changes are included. Back up your ini file before applying this update.")
    if any(repo_path_in_folder(path, "assets") for path in paths):
        warnings.append("Assets changed. Build a fresh zelda3_assets.dat after applying this update.")
    if any(repo_path_in_folder(path, "src/snes") for path in paths):
        warnings.append("src/snes changed. Rebuild the game after applying this update.")
    return warnings


def apply_change(project: Path, upstream: str, change: dict[str, Any]) -> None:
    if change["status"].startswith("D"):
        git_output(project, ["rm", "--force", "--quiet", "--ignore-unmatch", "--", change["path"]])
        return
    if change["status"].startswith("R") and change.get("old_path") and change["old_path"] != change["path"]:
        git_output(project, ["rm", "--force", "--quiet", "--ignore-unmatch", "--", change["old_path"]])
    git_output(project, ["checkout", "--force", upstream, "--", change["path"]])


def change_matches_upstream(project: Path, upstream: str, change: dict[str, Any]) -> bool:
    new_path_matches = git_success(project, ["diff", "--quiet", upstream, "--", change["path"]])
    if not new_path_matches:
        return False
    old_path = change.get("old_path")
    return git_success(project, ["diff", "--quiet", upstream, "--", old_path]) if old_path else True


def is_zelda_ini_path(path: str) -> bool:
    return path == "zelda3.ini" or path.endswith("/zelda3.ini")


def repo_path_in_folder(path: str, folder: str) -> bool:
    return path == folder or path.startswith(f"{folder}/")


def is_safe_repo_path(path: str) -> bool:
    if not path or "\0" in path or "\\" in path:
        return False
    parts = Path(path).parts
    return not any(part in ("..", ".", "") for part in parts) and not Path(path).is_absolute()
