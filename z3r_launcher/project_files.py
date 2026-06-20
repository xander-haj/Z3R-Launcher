from __future__ import annotations

import filecmp
import os
import shutil
import stat
from pathlib import Path

from .constants import STORED_ROM_NAME
from .errors import LauncherError
from .platform_paths import app_data_dir, display_path, is_windows, resources_dir
from .settings import legacy_app_data_dirs


def venv_python(venv_path: Path) -> Path | None:
    python = venv_path / ("Scripts/python.exe" if is_windows() else "bin/python")
    return python if python.is_file() else None


def copy_dir_contents(source: Path, destination: Path, ignored_names: set[str] | None = None) -> int:
    if not source.is_dir():
        raise LauncherError(f"Source folder does not exist: {display_path(source)}")
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    ignored = ignored_names or set()
    for child in source.iterdir():
        if child.name in ignored:
            continue
        target = destination / child.name
        if child.is_dir():
            copied += copy_dir_contents(child, target, ignored)
        elif child.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
            copied += 1
    return copied


def folder_matches_all_files(source: Path, destination: Path, ignored_names: set[str] | None = None) -> bool:
    if not source.is_dir() or not destination.is_dir():
        return False

    ignored = ignored_names or set()
    for child in source.iterdir():
        if child.name in ignored:
            continue
        target = destination / child.name
        if child.is_dir():
            if not folder_matches_all_files(child, target, ignored):
                return False
        elif child.is_file():
            if not target.is_file() or not filecmp.cmp(child, target, shallow=False):
                return False
    return True


def copy_file_with_parents(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def join_stage_output(first: str, second: str) -> str:
    if not first and not second:
        return ""
    if first and not second:
        return first
    if second and not first:
        return second
    return f"{first}\n{second}"


def resource_text(relative_path: str) -> str:
    path = resources_dir() / relative_path
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise LauncherError(f"Could not read launcher resource {relative_path}: {error}") from error


def apply_windows_solution_patch_to_project(project: Path) -> None:
    if not project.is_dir():
        raise LauncherError(f"Project folder does not exist: {display_path(project)}")
    if not is_snesrev_zelda3_project(project, None):
        raise LauncherError("The bundled solution patch only applies to snesrev/zelda3.")
    (project / "Zelda3.sln").write_text(resource_text("patches/windows/Zelda3.sln"), encoding="utf-8")


def is_snesrev_zelda3_project(project: Path, owner: str | None) -> bool:
    is_zelda3 = project.name.lower() == "zelda3"
    owner_is_snesrev = (owner and owner.lower() == "snesrev") or (project.parent.name.lower() == "snesrev")
    return is_zelda3 and bool(owner_is_snesrev)


def has_snesrev_makefile_patch(project_path: Path) -> bool:
    path = project_path / "Makefile"
    try:
        return path.read_text(encoding="utf-8") == resource_text("patches/snesrev-zelda3/Makefile")
    except OSError:
        return False


def has_snesrev_solution_patch(project_path: Path) -> bool:
    path = project_path / "Zelda3.sln"
    try:
        return path.read_text(encoding="utf-8-sig") == resource_text("patches/windows/Zelda3.sln")
    except OSError:
        return False


def rom_storage_dir() -> Path:
    current = app_data_dir() / "roms"
    if current.joinpath(STORED_ROM_NAME).is_file():
        return current

    for legacy in legacy_app_data_dirs():
        candidate = legacy / "roms"
        if candidate.joinpath(STORED_ROM_NAME).is_file():
            return candidate

    return current


def rom_status(force_current: bool = False) -> dict[str, object]:
    storage = app_data_dir() / "roms" if force_current else rom_storage_dir()
    rom_path = storage / STORED_ROM_NAME
    available = rom_path.is_file()
    return {
        "available": available,
        "file_name": STORED_ROM_NAME if available else None,
        "path": display_path(rom_path) if available else None,
        "storage_dir": display_path(storage),
    }


def rom_target_dir(project_path: Path) -> Path:
    for name in ("zelda3.ini", "zelda.ini"):
        ini_path = project_path / name
        if ini_path.is_file():
            return ini_path.parent
    return project_path


def copy_stored_rom_to_project(project_path: Path) -> Path | None:
    source = rom_storage_dir() / STORED_ROM_NAME
    if not source.is_file():
        return None
    destination = rom_target_dir(project_path) / STORED_ROM_NAME
    shutil.copy2(source, destination)
    return destination


def make_executable(path: Path) -> None:
    if os.name == "posix":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
