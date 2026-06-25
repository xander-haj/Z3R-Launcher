from __future__ import annotations

import shutil
from pathlib import Path

from .platform_paths import display_path, is_linux
from .project_files import make_executable


APPIMAGE_SUPPORT_DIR = ".launcher-linux-game"
APPIMAGE_DATA_HOME = ".launcher-appimage-data"
APPIMAGE_DATA_APP_DIR = "Z3R"
APPIMAGE_FILE_NAME = "game.AppImage"
APPIMAGE_WRAPPER_NAME = "zelda3"
APPIMAGE_MAGIC_OFFSETS = (8,)
APPIMAGE_MAGIC_VALUES = (b"AI\x01", b"AI\x02")
ASSET_CANDIDATE_RELATIVE_PATHS = (
    "zelda3_assets.dat",
    "tables/zelda3_assets.dat",
    "bin/x64-Release/zelda3_assets.dat",
    "bin/x64-ReleaseDeploy/zelda3_assets.dat",
    "bin/Win32-Release/zelda3_assets.dat",
    "bin/Win32-ReleaseDeploy/zelda3_assets.dat",
)
CONFIG_CANDIDATE_NAMES = ("zelda3.user.ini", "zelda3.ini")


def install_appimage_game_asset(asset_path: Path, project: Path) -> Path:
    """Install a downloaded game AppImage behind the repo-local zelda3 launcher.

    The packaged game AppImage looks for zelda3_assets.dat under XDG_DATA_HOME/Z3R,
    so the visible repo executable must be a small wrapper that prepares that data
    bridge before delegating to the real AppImage.
    """
    support_dir = appimage_support_dir(project)
    support_dir.mkdir(parents=True, exist_ok=True)
    appimage = support_dir / APPIMAGE_FILE_NAME
    temporary = support_dir / f".{APPIMAGE_FILE_NAME}.download"
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    shutil.copy2(asset_path, temporary)
    make_executable(temporary)
    temporary.replace(appimage)
    make_executable(appimage)
    return write_appimage_game_wrapper(project)


def write_appimage_game_wrapper(project: Path) -> Path:
    """Write the repo-root executable that launches the stored game AppImage."""
    wrapper = project / APPIMAGE_WRAPPER_NAME
    temporary = project / f".{APPIMAGE_WRAPPER_NAME}.wrapper"
    temporary.write_text(appimage_game_wrapper_script(), encoding="utf-8")
    make_executable(temporary)
    temporary.replace(wrapper)
    make_executable(wrapper)
    return wrapper


def appimage_game_wrapper_script() -> str:
    """Return the POSIX shell wrapper used for repo-local AppImage launches."""
    return """#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
appimage="${project_dir}/.launcher-linux-game/game.AppImage"
data_home="${project_dir}/.launcher-appimage-data"
data_dir="${data_home}/Z3R"

bridge_file() {
  source_file=$1
  target_file=$2
  if [ ! -f "$source_file" ]; then
    return 0
  fi
  mkdir -p "$(dirname -- "$target_file")"
  rm -f "$target_file"
  ln -s "$source_file" "$target_file" 2>/dev/null || cp "$source_file" "$target_file"
}

mkdir -p "$data_dir"
for assets_file in \\
  "${project_dir}/zelda3_assets.dat" \\
  "${project_dir}/tables/zelda3_assets.dat" \\
  "${project_dir}/bin/x64-Release/zelda3_assets.dat" \\
  "${project_dir}/bin/x64-ReleaseDeploy/zelda3_assets.dat" \\
  "${project_dir}/bin/Win32-Release/zelda3_assets.dat" \\
  "${project_dir}/bin/Win32-ReleaseDeploy/zelda3_assets.dat"; do
  if [ -f "$assets_file" ]; then
    bridge_file "$assets_file" "${data_dir}/zelda3_assets.dat"
    break
  fi
done

if [ -f "${project_dir}/zelda3.user.ini" ]; then
  bridge_file "${project_dir}/zelda3.user.ini" "${data_dir}/zelda3.ini"
else
  bridge_file "${project_dir}/zelda3.ini" "${data_dir}/zelda3.ini"
fi

export XDG_DATA_HOME="$data_home"
exec "$appimage" "$@"
"""


def launch_env_for_game(executable: Path, working_dir: Path, env: dict[str, str]) -> dict[str, str]:
    """Return the child environment for launching a game from the selected repo."""
    if should_prepare_appimage_bridge(executable, working_dir):
        env = env.copy()
        env["XDG_DATA_HOME"] = display_path(prepare_appimage_data_bridge(working_dir))
    return env


def should_prepare_appimage_bridge(executable: Path, project: Path) -> bool:
    """Detect launcher-installed or legacy raw AppImage game executables."""
    if not is_linux():
        return False
    if (appimage_support_dir(project) / APPIMAGE_FILE_NAME).is_file():
        return True
    return executable_looks_like_appimage(executable)


def prepare_appimage_data_bridge(project: Path) -> Path:
    """Mirror the selected repo's assets/config into the game AppImage data root."""
    data_home = project / APPIMAGE_DATA_HOME
    data_dir = data_home / APPIMAGE_DATA_APP_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    asset_source = first_existing_project_file(project, ASSET_CANDIDATE_RELATIVE_PATHS)
    if asset_source:
        bridge_file(asset_source, data_dir / "zelda3_assets.dat")
    config_source = first_existing_project_file(project, CONFIG_CANDIDATE_NAMES)
    if config_source:
        bridge_file(config_source, data_dir / "zelda3.ini")
    return data_home


def first_existing_project_file(project: Path, relative_paths: tuple[str, ...]) -> Path | None:
    """Find the first repo-local file from an ordered list of relative paths."""
    for relative_path in relative_paths:
        candidate = project / relative_path
        if candidate.is_file():
            return candidate
    return None


def bridge_file(source: Path, target: Path) -> None:
    """Expose one repo file at the AppImage data path using symlink or copy fallback."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    try:
        target.symlink_to(source)
    except OSError:
        shutil.copy2(source, target)


def executable_looks_like_appimage(executable: Path) -> bool:
    """Check the AppImage magic bytes without executing the downloaded file."""
    if executable.name.lower().endswith(".appimage"):
        return True
    try:
        with executable.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return False
    for offset in APPIMAGE_MAGIC_OFFSETS:
        value = header[offset:offset + 3]
        if value in APPIMAGE_MAGIC_VALUES:
            return True
    return False


def appimage_support_dir(project: Path) -> Path:
    """Return the hidden repo-local folder that stores the real game AppImage."""
    return project / APPIMAGE_SUPPORT_DIR
