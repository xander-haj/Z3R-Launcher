from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Callable

from .constants import APP_ID
from .errors import LauncherError
from .platform_paths import (
    current_appimage_path,
    current_executable_path,
    current_macos_bundle_path,
    display_path,
    hidden_subprocess_kwargs,
    is_flatpak_runtime,
    is_linux,
    is_macos,
    is_windows,
    update_work_dir,
)
from .processes import action_result, command_env, decode_output, run_process
from .project_files import make_executable
from .update_downloads import (
    compare_versions,
    current_update_version,
    download_release_asset,
    exact_asset,
    fetch_latest_release,
    first_release_asset,
)
from .update_scripts import write_appimage_update_script, write_macos_update_script, write_windows_update_script


def install_launcher_update(schedule_exit: Callable[[], None], allow_downgrade: bool = False) -> dict[str, Any]:
    current_version = current_update_version()
    update_dir = update_work_dir()
    update_dir.mkdir(parents=True, exist_ok=True)
    release = fetch_latest_release(update_dir)
    ordering = compare_versions(release["tag_name"], current_version)
    dev_update_source = is_dev_update_source(release)
    if ordering < 0:
        if dev_update_source and not allow_downgrade:
            return downgrade_confirmation_result(current_version, release["tag_name"])
        if not dev_update_source:
            return action_result(
                True,
                public_up_to_date_message(current_version, release["tag_name"]),
            )
    if ordering == 0:
        return action_result(True, f"Launcher is already up to date ({current_version}).")
    if is_flatpak_runtime():
        return install_flatpak_update(release, update_dir, schedule_exit)
    if is_windows():
        return install_windows_update(release, update_dir, schedule_exit)
    if is_macos():
        return install_macos_update(release, update_dir, schedule_exit)
    if is_linux():
        return install_appimage_update(release, update_dir, schedule_exit)
    raise LauncherError("Launcher updates are not packaged for this operating system yet.")


def downgrade_confirmation_result(current_version: str, release_version: str) -> dict[str, Any]:
    message = (
        f"Launcher {current_version} is newer than the selected update release {release_version}."
    )
    result = action_result(False, message)
    result.update({
        "confirmation_required": True,
        "confirmation_prompt": (
            f"{message}\n\nDownload and install {release_version} anyway?"
        ),
        "current_version": current_version,
        "release_version": release_version,
    })
    return result


def is_dev_update_source(release: dict[str, Any]) -> bool:
    source = release.get("_launcher_update_source")
    return isinstance(source, dict) and bool(source.get("dev_override"))


def public_up_to_date_message(current_version: str, release_version: str) -> str:
    return (
        f"Launcher is already up to date ({current_version}). "
        f"Latest public release is {release_version}."
    )


def install_windows_update(
    release: dict[str, Any],
    update_dir: Path,
    schedule_exit: Callable[[], None],
) -> dict[str, Any]:
    asset = exact_asset(release, "Z3R-Launcher-windows-x64.exe")
    downloaded_exe = download_release_asset(asset, update_dir)
    script_path = update_dir / "apply-windows-update.ps1"
    log_path = update_dir / "apply-windows-update.log"
    target_path = current_executable_path()
    write_windows_update_script(script_path)
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path),
            "-LauncherPid", str(os.getpid()), "-Downloaded", str(downloaded_exe),
            "-Target", str(target_path), "-Relaunch", str(target_path), "-Log", str(log_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=command_env(),
        **hidden_subprocess_kwargs(),
    )
    schedule_exit()
    return action_result(
        True,
        f"Launcher update {release['tag_name']} downloaded. The launcher will close so the exe can be replaced.",
        f"Executable: {display_path(downloaded_exe)}\nUpdater log: {display_path(log_path)}",
    )


def install_macos_update(
    release: dict[str, Any],
    update_dir: Path,
    schedule_exit: Callable[[], None],
) -> dict[str, Any]:
    bundle_path = current_macos_bundle_path()
    asset = first_release_asset(release, [macos_update_asset_name(), "Z3R-Launcher-macos-universal.dmg"])
    dmg_path = download_release_asset(asset, update_dir)
    script_path = update_dir / "apply-macos-update.sh"
    mount_path = update_dir / "macos-dmg-mount"
    log_path = update_dir / "apply-macos-update.log"
    app_name = bundle_path.name
    write_macos_update_script(script_path)
    make_executable(script_path)
    subprocess.Popen(
        [
            "/bin/sh", str(script_path), str(os.getpid()), str(dmg_path), str(mount_path),
            str(bundle_path), app_name, str(log_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=command_env(),
        **hidden_subprocess_kwargs(),
    )
    schedule_exit()
    return action_result(
        True,
        f"Launcher update {release['tag_name']} downloaded. "
        "The launcher will close, replace the app bundle, and reopen.",
        f"Updater log: {display_path(log_path)}",
    )


def install_flatpak_update(
    release: dict[str, Any],
    update_dir: Path,
    schedule_exit: Callable[[], None],
) -> dict[str, Any]:
    asset = exact_asset(release, "Z3R-Launcher-linux.flatpak")
    bundle = download_release_asset(asset, update_dir)
    output = run_process(
        "flatpak-spawn",
        [
            "--host", "flatpak", "install", flatpak_install_scope_arg(), "--or-update",
            "--assumeyes", "--noninteractive", display_path(bundle),
        ],
        capture=True,
    )
    if output.returncode != 0:
        detail = decode_output(output.stderr).strip() or decode_output(output.stdout).strip()
        raise LauncherError(detail or f"Flatpak launcher install exited with status {output.returncode}")
    spawn_flatpak_relaunch()
    schedule_exit()
    return action_result(
        True,
        f"Launcher update {release['tag_name']} installed through Flatpak. The launcher will close and reopen.",
        decode_output(output.stdout).strip(),
        decode_output(output.stderr).strip(),
    )


def install_appimage_update(
    release: dict[str, Any],
    update_dir: Path,
    schedule_exit: Callable[[], None],
) -> dict[str, Any]:
    current_appimage = current_appimage_path()
    asset = exact_asset(release, "Z3R-Launcher-linux-x64.AppImage")
    downloaded_appimage = download_release_asset(asset, update_dir)
    script_path = update_dir / "apply-appimage-update.sh"
    log_path = update_dir / "apply-appimage-update.log"
    write_appimage_update_script(script_path)
    make_executable(script_path)
    subprocess.Popen(
        [
            "/bin/sh", str(script_path), str(os.getpid()), str(downloaded_appimage),
            str(current_appimage), str(log_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=command_env(),
        **hidden_subprocess_kwargs(),
    )
    schedule_exit()
    return action_result(
        True,
        f"Launcher update {release['tag_name']} downloaded. "
        "The launcher will close, replace the AppImage, and reopen.",
        f"Updater log: {display_path(log_path)}",
    )


def macos_update_asset_name() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "Z3R-Launcher-macos-apple-silicon.dmg"
    return "Z3R-Launcher-macos-intel.dmg"


def flatpak_install_scope_arg() -> str:
    try:
        flatpak_info = Path("/.flatpak-info").read_text(encoding="utf-8")
    except OSError:
        return "--user"
    for line in flatpak_info.splitlines():
        if not line.startswith("app-path="):
            continue
        app_path = line.removeprefix("app-path=")
        if "/.local/share/flatpak/" in app_path:
            return "--user"
        if "/var/lib/flatpak/" in app_path:
            return "--system"
    return "--user"


def spawn_flatpak_relaunch() -> None:
    subprocess.Popen(
        [
            "flatpak-spawn", "--host", "sh", "-c",
            'while kill -0 "$1" 2>/dev/null; do sleep 1; done; flatpak run "$2"',
            "z3r-launcher-flatpak-relaunch", str(os.getpid()), APP_ID,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=command_env(),
        **hidden_subprocess_kwargs(),
    )
