from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import LauncherError
from .platform_paths import display_path, is_windows, resolve_scan_root
from .project_files import (
    has_snesrev_makefile_patch,
    has_snesrev_solution_patch,
    is_snesrev_zelda3_project,
)
from .processes import first_existing


def scan_siblings(scan_roots: list[str] | None = None) -> dict[str, Any]:
    default_root = resolve_scan_root(None)
    roots = ordered_scan_roots(default_root, scan_roots or [])
    groups: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for index, root in enumerate(roots):
        group_candidates = scan_root(root)
        candidates.extend(group_candidates)
        groups.append({
            "label": scan_root_label(root),
            "path": display_path(root),
            "is_default": index == 0,
            "candidates": group_candidates,
        })

    return {"launcher_parent": display_path(default_root), "candidates": candidates, "groups": groups}


def ordered_scan_roots(default_root: Path, added_roots: list[str]) -> list[Path]:
    roots = [default_root]
    for root in added_roots:
        path = Path(root)
        if path not in roots:
            roots.append(path)
    return roots


def scan_root_label(path: Path) -> str:
    return path.name or display_path(path)


def scan_root(parent: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not parent.is_dir():
        return candidates
    try:
        entries = list(parent.iterdir())
    except OSError as error:
        raise LauncherError(f"Could not scan {display_path(parent)}: {error}") from error
    for path in entries:
        if not path.is_dir():
            continue
        candidate = inspect_candidate(path, None)
        if candidate:
            candidates.append(candidate)
            continue
        scan_owner_folder(path, candidates)
    candidates.sort(key=lambda candidate: candidate["name"])
    return candidates


def scan_owner_folder(owner_path: Path, candidates: list[dict[str, Any]]) -> None:
    owner_name = owner_path.name
    if not owner_name or owner_name.startswith("."):
        return
    try:
        entries = owner_path.iterdir()
    except OSError:
        return
    for nested_path in entries:
        if nested_path.is_dir():
            candidate = inspect_candidate(nested_path, owner_name)
            if candidate:
                candidates.append(candidate)


def inspect_candidate(path: Path, owner: str | None) -> dict[str, Any] | None:
    asset_path = find_asset(path)
    executable_path = find_executable(path)
    has_makefile = (path / "Makefile").exists()
    has_solution = (path / "Zelda3.sln").exists()
    has_source = has_makefile or has_solution or (path / "run_with_tcc.bat").exists()
    if not asset_path and not executable_path and not has_source:
        return None

    status, notes = candidate_status(asset_path, executable_path)
    is_snesrev = is_discovered_snesrev_zelda3(path, owner)
    makefile_applied = is_snesrev and has_snesrev_makefile_patch(path)
    solution_applied = is_snesrev and has_solution and has_snesrev_solution_patch(path)
    return {
        "name": path.name or display_path(path),
        "owner": owner,
        "path": display_path(path),
        "asset_path": display_path(asset_path) if asset_path else None,
        "executable_path": display_path(executable_path) if executable_path else None,
        "git_repo": (path / ".git").exists(),
        "snesrev_makefile_patch_applied": makefile_applied,
        "snesrev_solution_patch_applied": solution_applied,
        "source_patch_needed": source_patch_for_platform(is_snesrev, has_solution, makefile_applied, solution_applied),
        "link_sprite_editor_available": (path / "assets" / "sprite_sheets.py").is_file(),
        "status": status,
        "notes": notes,
    }


def candidate_status(asset_path: Path | None, executable_path: Path | None) -> tuple[str, list[str]]:
    notes: list[str] = []
    if asset_path and executable_path:
        if executable_path.parent == asset_path.parent or is_windows_runtime_output(executable_path):
            return "ready", notes
        notes.append("Executable and zelda3_assets.dat are not beside each other; use a deploy build or copy assets beside the executable.")
        return "needs-deploy-copy", notes
    if asset_path:
        return "assets-ready", notes
    if executable_path:
        return "missing-assets", notes
    return "source-only", notes


def is_discovered_snesrev_zelda3(path: Path, owner: str | None) -> bool:
    if is_windows():
        return is_snesrev_zelda3_project(path, owner)
    return bool(owner and owner.lower() == "snesrev" and path.name.lower() == "zelda3")


def source_patch_for_platform(is_snesrev: bool, has_solution: bool, makefile_applied: bool, solution_applied: bool) -> str | None:
    if is_windows():
        return "solution" if is_snesrev and has_solution and not solution_applied else None
    return "makefile" if is_snesrev and not makefile_applied else None


def find_asset(project_path: Path) -> Path | None:
    candidates = [
        project_path / "zelda3_assets.dat",
        project_path / "tables" / "zelda3_assets.dat",
        project_path / "bin" / "x64-Release" / "zelda3_assets.dat",
        project_path / "bin" / "x64-ReleaseDeploy" / "zelda3_assets.dat",
        project_path / "bin" / "Win32-Release" / "zelda3_assets.dat",
        project_path / "bin" / "Win32-ReleaseDeploy" / "zelda3_assets.dat",
    ]
    return first_existing(candidates)


def is_windows_runtime_output(executable: Path) -> bool:
    return is_windows() and (executable.parent / "SDL2.dll").is_file()


def find_executable(project_path: Path) -> Path | None:
    names = ["zelda3.exe"] if is_windows() else ["zelda3"]
    folders = [
        project_path,
        project_path / "bin" / "x64-Release",
        project_path / "bin" / "x64-ReleaseDeploy",
        project_path / "bin" / "Win32-Release",
        project_path / "bin" / "Win32-ReleaseDeploy",
    ]
    for folder in folders:
        for name in names:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None
