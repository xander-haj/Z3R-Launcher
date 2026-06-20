from __future__ import annotations

import base64
import filecmp
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .link_sprite_editor import (
    LinkSpritePaletteError,
    read_link_sprite_palette as read_link_sprite_palette_file,
    write_link_sprite_palette as write_link_sprite_palette_file,
)
from .link_sprite_preview import (
    LinkSpritePreviewError,
    read_compiled_link_graphics,
)


APP_ID = "io.github.xander_haj.Z3RLauncher"
APP_NAME = "Z3R Launcher"
APP_IDENTIFIER = "com.xander.z3r-launcher"
Z3R_REPO_URL = "https://github.com/xander-haj/Z3R"
Z3R_BETA_REPO_URL = "https://github.com/xander-haj/Z3R-Beta"
Z3R_RELEASES_URL = "https://github.com/xander-haj/Z3R/releases"
Z3R_BETA_RELEASES_URL = "https://github.com/xander-haj/Z3R-Beta/releases"
Z3R_RELEASE_API_URL = "https://api.github.com/repos/xander-haj/Z3R/releases/latest"
Z3R_BETA_RELEASE_API_URL = "https://api.github.com/repos/xander-haj/Z3R-Beta/releases/latest"
LAUNCHER_RELEASE_API_URL = "https://api.github.com/repos/xander-haj/Z3R-Launcher/releases/latest"
SPRITES_SOURCE_URL = "https://github.com/snesrev/sprites-gfx.git"
SHADERS_SOURCE_URL = "https://github.com/snesrev/glsl-shaders"
MSU_DOWNLOAD_URL = "https://www.zeldix.net/f11-msu1-development"
MSU_DIR = "msu"
SPRITES_DIR = "sprites-gfx"
SHADERS_DIR = "glsl-shaders"
STORED_ROM_NAME = "zelda3.sfc"
DEV_SETTINGS_FILE = "dev-settings.json"
REPO_SETTINGS_FILE = "repo-settings.json"
GITHUB_TOKEN_ENV = "Z3R_LAUNCHER_GITHUB_TOKEN"
FLATPAK_INFO_PATH = Path("/.flatpak-info")
C_COMPILER_CANDIDATES = ("cc", "gcc", "clang")
APPIMAGE_ENV_KEYS = ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "LD_LIBRARY_PATH")
PYTHON_CHILD_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONEXECUTABLE",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
    "VIRTUAL_ENV_PROMPT",
)
PROJECT_RELEASES = {
    "xander-haj/z3r": {
        "id": "z3r",
        "label": "Z3R",
        "releases_url": Z3R_RELEASES_URL,
        "api_url": Z3R_RELEASE_API_URL,
        "preferred_assets": ("Z3R-linux-x64.tar.gz",),
    },
    "xander-haj/z3r-beta": {
        "id": "z3r-beta",
        "label": "Z3R-Beta",
        "releases_url": Z3R_BETA_RELEASES_URL,
        "api_url": Z3R_BETA_RELEASE_API_URL,
        "preferred_assets": ("Z3R-Beta-linux-x64.tar.gz", "Z3R-linux-x64.tar.gz"),
    },
}
LINUX_GAME_EXECUTABLE_NAMES = ("zelda3", "zelda3.real")
LINUX_GAME_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar", ".zip")


class LauncherError(Exception):
    """A user-facing backend error."""


def display_path(path: Path | str) -> str:
    return str(Path(path))


def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return platform.system().lower() or sys.platform


def is_windows() -> bool:
    return os_name() == "windows"


def is_macos() -> bool:
    return os_name() == "macos"


def is_linux() -> bool:
    return os_name() == "linux"


def is_flatpak_runtime() -> bool:
    return is_linux() and FLATPAK_INFO_PATH.is_file()


def is_appimage_runtime() -> bool:
    return is_linux() and bool(os.environ.get("APPIMAGE"))


def uses_downloaded_linux_game_executable() -> bool:
    return is_linux() and (is_appimage_runtime() or is_flatpak_runtime())


def launcher_root() -> Path:
    override = os.environ.get("Z3R_LAUNCHER_ROOT")
    if override:
        return Path(override).resolve()

    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root).resolve()
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def resources_dir() -> Path:
    return launcher_root() / "resources"


def static_dir() -> Path:
    return launcher_root() / "src"


def bundled_tools_dir() -> Path:
    return launcher_root() / "bundled-tools"


def bundled_tools_candidates() -> list[Path]:
    candidates: list[Path] = []
    if is_windows() and getattr(sys, "frozen", False):
        candidates.append(current_executable_path().parent / "bundled-tools")
    candidates.append(bundled_tools_dir())
    return candidates


def windows_tools_dir() -> Path:
    for root in bundled_tools_candidates():
        candidate = root / "windows"
        if candidate.is_dir():
            return candidate
    return bundled_tools_candidates()[0] / "windows"


def hidden_subprocess_kwargs() -> dict[str, int]:
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0) if is_windows() else 0
    return {"creationflags": flag} if flag else {}


def app_data_dir() -> Path:
    override = os.environ.get("Z3R_LAUNCHER_DATA_DIR")
    if override:
        return Path(override)

    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME

    if is_macos():
        return Path.home() / "Library" / "Application Support" / APP_IDENTIFIER

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "z3r-launcher"
    return Path.home() / ".local" / "share" / "z3r-launcher"


def dev_settings_path() -> Path:
    return app_data_dir() / DEV_SETTINGS_FILE


def read_dev_settings_file() -> dict[str, Any]:
    path = dev_settings_path()

    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}

    return settings if isinstance(settings, dict) else {}


def write_dev_settings(launcher_update_api_url: str) -> None:
    path = dev_settings_path()

    if not launcher_update_api_url:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"launcher_update_api_url": launcher_update_api_url}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dev_settings_snapshot() -> dict[str, Any]:
    override = read_dev_settings_file().get("launcher_update_api_url")
    override_url = normalize_launcher_update_api_url(override) if isinstance(override, str) else ""
    effective_url = override_url or LAUNCHER_RELEASE_API_URL
    return {
        "launcher_update_api_url": override_url,
        "default_launcher_update_api_url": LAUNCHER_RELEASE_API_URL,
        "effective_launcher_update_api_url": effective_url,
    }


def launcher_release_api_url() -> str:
    return dev_settings_snapshot()["effective_launcher_update_api_url"]


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


def rom_storage_dir() -> Path:
    current = app_data_dir() / "roms"
    if current.joinpath(STORED_ROM_NAME).is_file():
        return current

    for legacy in legacy_app_data_dirs():
        candidate = legacy / "roms"
        if candidate.joinpath(STORED_ROM_NAME).is_file():
            return candidate

    return current


def update_work_dir() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME / "updates"
    if is_macos():
        return Path.home() / "Library" / "Caches" / APP_NAME / "updates"
    cache = os.environ.get("XDG_CACHE_HOME")
    if cache:
        return Path(cache) / "z3r-launcher" / "updates"
    if Path.home():
        return Path.home() / ".cache" / "z3r-launcher" / "updates"
    return Path(tempfile.gettempdir()) / "z3r-launcher-updates"


def current_executable_path() -> Path:
    return Path(sys.executable).resolve()


def default_scan_root() -> Path:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return Path(appimage).resolve().parent

    if getattr(sys, "frozen", False):
        exe_dir = current_executable_path().parent
        if is_macos():
            bundle_parent = macos_bundle_parent(exe_dir)
            if bundle_parent:
                return bundle_parent
        return exe_dir

    return launcher_root().parent


def macos_bundle_parent(exe_dir: Path) -> Path | None:
    contents_dir = exe_dir.parent
    app_dir = contents_dir.parent
    if exe_dir.name == "MacOS" and contents_dir.name == "Contents" and app_dir.suffix == ".app":
        return app_dir.parent
    return None


def resolve_scan_root(scan_root: str | None = None) -> Path:
    if scan_root:
        path = Path(scan_root)
        if path.is_dir():
            return path
        raise LauncherError(f"Selected scan folder does not exist: {display_path(path)}")
    return default_scan_root()


def venv_python(venv_path: Path) -> Path | None:
    python = venv_path / ("Scripts/python.exe" if is_windows() else "bin/python")
    return python if python.is_file() else None


def macos_search_paths() -> list[Path]:
    paths = [
        Path("/opt/homebrew/bin"),
        Path("/opt/homebrew/opt/sdl2/bin"),
        Path("/usr/local/bin"),
        Path("/usr/local/opt/sdl2/bin"),
        Path("/opt/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
        Path("/usr/sbin"),
        Path("/sbin"),
    ]
    for item in os.environ.get("PATH", "").split(os.pathsep):
        if item:
            paths.append(Path(item))

    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def command_env(remove_appimage: bool | None = None, isolate_python: bool = True) -> dict[str, str]:
    env = os.environ.copy()
    if is_macos():
        env["PATH"] = os.pathsep.join(str(path) for path in macos_search_paths())
    if remove_appimage is None:
        remove_appimage = is_linux()
    if remove_appimage:
        sanitize_appimage_env(env)
    if isolate_python:
        for key in PYTHON_CHILD_ENV_KEYS:
            env.pop(key, None)
    return env


def sanitize_appimage_env(env: dict[str, str]) -> None:
    appdir = env.get("APPDIR")
    original_library_path = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if appdir and env.get("PATH"):
        appdir_path = Path(appdir)
        path_entries = []
        for entry in env["PATH"].split(os.pathsep):
            entry_path = Path(entry)
            if entry_path.is_absolute() and entry_path.is_relative_to(appdir_path):
                continue
            path_entries.append(entry)
        env["PATH"] = os.pathsep.join(path_entries)
    for key in APPIMAGE_ENV_KEYS:
        env.pop(key, None)
    if original_library_path:
        env["LD_LIBRARY_PATH"] = original_library_path


def resolve_program(program: str) -> str:
    if not is_macos() or "/" in program or "\\" in program:
        return program
    for directory in macos_search_paths():
        candidate = directory / program
        if candidate.is_file():
            return str(candidate)
    return program


def run_process(
    program: str,
    args: list[str] | tuple[str, ...] = (),
    cwd: Path | None = None,
    check: bool = False,
    capture: bool = True,
    remove_appimage_env: bool | None = None,
) -> subprocess.CompletedProcess[bytes]:
    command = [resolve_program(program), *map(str, args)]
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=command_env(remove_appimage=remove_appimage_env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if check and completed.returncode != 0:
        detail = decode_output(completed.stderr).strip() or decode_output(completed.stdout).strip()
        raise LauncherError(detail or f"{program} exited with status {completed.returncode}")
    return completed


def decode_output(value: bytes | str) -> str:
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def action_result(ok: bool, message: str, stdout: str = "", stderr: str = "") -> dict[str, Any]:
    return {"ok": ok, "message": message, "stdout": stdout, "stderr": stderr}


def run_command(program: str, args: list[str] | tuple[str, ...], cwd: Path, success_message: str) -> dict[str, Any]:
    try:
        output = run_process(program, args, cwd=cwd, capture=True)
    except OSError as error:
        raise LauncherError(f"Could not run {program}: {error}") from error

    stdout = decode_output(output.stdout)
    stderr = decode_output(output.stderr)
    ok = output.returncode == 0
    message = success_message if ok else f"{program} exited with status {output.returncode}"
    return action_result(ok, message, stdout, stderr)


def open_path(path: Path, label: str) -> None:
    attempts: list[tuple[str, list[str], bool]] = []
    if is_windows():
        attempts.append(("explorer", ["explorer", str(path)], False))
    elif is_macos():
        attempts.append(("open", ["open", str(path)], False))
    else:
        if is_flatpak_runtime():
            attempts.append(("flatpak-spawn", ["flatpak-spawn", "--host", "xdg-open", str(path)], False))
        for program in ("xdg-open", "gio"):
            host = linux_host_program_path(program) or program
            args = [host, str(path)] if program == "xdg-open" else [host, "open", str(path)]
            attempts.append((program, args, True))

    errors: list[str] = []
    for label_name, command, sanitize in attempts:
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=command_env(remove_appimage=sanitize),
                check=False,
                **hidden_subprocess_kwargs(),
            )
            if completed.returncode == 0:
                return
            errors.append(f"{label_name} exited with status {completed.returncode}")
        except OSError as error:
            errors.append(str(error))

    raise LauncherError(f"Could not open {label}: {'; '.join(errors)}")


def linux_host_program_path(program: str) -> str | None:
    for directory in ("/usr/bin", "/bin", "/usr/local/bin"):
        candidate = Path(directory) / program
        if candidate.is_file():
            return str(candidate)
    return None


def open_external_url(url: str) -> None:
    if not (url.startswith("https://") or url.startswith("http://")):
        raise LauncherError("Only http and https documentation links can be opened.")

    if is_windows():
        subprocess.Popen(
            ["rundll32", "url.dll,FileProtocolHandler", url],
            stdin=subprocess.DEVNULL,
            env=command_env(),
            **hidden_subprocess_kwargs(),
        )
        return
    if is_macos():
        subprocess.Popen(["open", url], stdin=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())
        return

    opener = linux_host_program_path("xdg-open") or "xdg-open"
    subprocess.Popen([opener, url], stdin=subprocess.DEVNULL, env=command_env(remove_appimage=True), **hidden_subprocess_kwargs())


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def bundled_git() -> Path | None:
    return first_existing([
        windows_tools_dir() / "git" / "cmd" / "git.exe",
        windows_tools_dir() / "git" / "bin" / "git.exe",
    ])


def bundled_python() -> Path | None:
    return first_existing([
        windows_tools_dir() / "python" / "tools" / "python.exe",
        windows_tools_dir() / "python" / "python.exe",
    ])


def bundled_tcc() -> Path | None:
    return first_existing([windows_tools_dir() / "tcc" / "tcc.exe"])


def bundled_sdl2_dll() -> Path | None:
    return first_existing([windows_tools_dir() / "sdl2" / "lib" / "x64" / "SDL2.dll"])


def bundled_sdl2_root() -> Path | None:
    root = windows_tools_dir() / "sdl2"
    return root if (root / "include").is_dir() else None


def git_program() -> str:
    if is_windows():
        path = bundled_git()
        if path:
            return display_path(path)
    return "git"


def python_program() -> str:
    if is_windows():
        path = bundled_python()
        if path:
            return display_path(path)
        return "py"
    return "python3"


def bundled_detail(label: str, path: Path) -> str:
    return f"Using bundled {label}: {display_path(path)}"


def first_command_stdout_path(program: str, args: list[str]) -> Path | None:
    try:
        output = run_process(program, args)
    except OSError:
        return None
    if output.returncode != 0:
        return None
    for line in decode_output(output.stdout).splitlines():
        candidate = Path(line.strip())
        if candidate.is_file():
            return candidate
    return None


def find_msbuild() -> Path | None:
    path = first_command_stdout_path("where", ["msbuild"]) if is_windows() else None
    if path:
        return path

    path = find_msbuild_with_vswhere()
    if path:
        return path

    return first_existing(common_msbuild_paths())


def find_msbuild_with_vswhere() -> Path | None:
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        return None
    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    return first_command_stdout_path(str(vswhere), [
        "-latest",
        "-products",
        "*",
        "-requires",
        "Microsoft.Component.MSBuild",
        "-find",
        r"MSBuild\**\Bin\MSBuild.exe",
    ])


def common_msbuild_paths() -> list[Path]:
    program_files = os.environ.get("ProgramFiles")
    if not program_files:
        return []
    editions = ["BuildTools", "Community", "Professional", "Enterprise"]
    return [
        Path(program_files) / "Microsoft Visual Studio" / "2022" / edition / "MSBuild" / "Current" / "Bin" / "MSBuild.exe"
        for edition in editions
    ]


def camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", value).lower()


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {camel_to_snake(key): value for key, value in payload.items()}


class LauncherBackend:
    def __init__(self, schedule_exit: Callable[[], None] | None = None) -> None:
        self.schedule_exit = schedule_exit or (lambda: None)
        self.commands: dict[str, Callable[..., Any]] = {
            "scan_siblings": self.scan_siblings,
            "app_runtime_info": self.app_runtime_info,
            "launcher_version": self.launcher_version,
            "read_repo_settings": self.read_repo_settings,
            "save_repo_settings": self.save_repo_settings,
            "read_dev_settings": self.read_dev_settings,
            "save_dev_settings": self.save_dev_settings,
            "install_launcher_update": self.install_launcher_update,
            "check_environment": self.check_environment,
            "launch_game": self.launch_game,
            "choose_scan_root": self.choose_scan_root,
            "clone_project": self.clone_project,
            "clone_custom_project": self.clone_custom_project,
            "open_project_folder": self.open_project_folder,
            "create_venv": self.create_venv,
            "install_dependencies": self.install_dependencies,
            "extract_assets": self.extract_assets,
            "extract_assets_visual_studio": self.extract_assets_visual_studio,
            "extract_assets_tcc": self.extract_assets_tcc,
            "open_external_url": self.open_external_url,
            "read_feature_assets": self.read_feature_assets,
            "clone_feature_asset": self.clone_feature_asset,
            "choose_and_store_msu": self.choose_and_store_msu,
            "store_msu_paths": self.store_msu_paths,
            "install_feature_asset": self.install_feature_asset,
            "read_sprite_preview": self.read_sprite_preview,
            "read_link_sprite_preview": self.read_link_sprite_preview,
            "read_link_sprite_palette": self.read_link_sprite_palette,
            "save_link_sprite_palette": self.save_link_sprite_palette,
            "build_link_sprite_assets": self.build_link_sprite_assets,
            "apply_snesrev_makefile_patch": self.apply_snesrev_makefile_patch,
            "apply_snesrev_solution_patch": self.apply_snesrev_solution_patch,
            "stored_rom_status": self.stored_rom_status,
            "store_rom_upload": self.store_rom_upload,
            "choose_and_store_rom": self.choose_and_store_rom,
            "open_stored_rom_folder": self.open_stored_rom_folder,
            "sync_stored_rom_to_projects": self.sync_stored_rom_to_projects,
            "read_randomizer_setup": self.read_randomizer_setup,
            "extract_randomizer_assets": self.extract_randomizer_assets,
            "run_randomizer": self.run_randomizer,
            "restore_vanilla_randomizer_yaml": self.restore_vanilla_randomizer_yaml,
            "compile_randomized_assets": self.compile_randomized_assets,
            "preview_repo_update": self.preview_repo_update,
            "apply_repo_update": self.apply_repo_update,
            "read_zelda_ini": self.read_zelda_ini,
            "update_zelda_ini_line": self.update_zelda_ini_line,
            "set_zelda_ini_value": self.set_zelda_ini_value,
        }

    def invoke(self, command: str, payload: dict[str, Any] | None = None) -> Any:
        handler = self.commands.get(command)
        if not handler:
            raise LauncherError(f"Unknown launcher command: {command}")
        return handler(**normalize_payload(payload or {}))

    def launcher_version(self) -> str:
        return current_update_version()

    def read_repo_settings(self) -> dict[str, Any]:
        return repo_settings_snapshot()

    def save_repo_settings(
        self,
        scan_paths: list[str] | None = None,
        clone_path: str | None = None,
    ) -> dict[str, Any]:
        normalized_scan_paths = normalize_repo_scan_paths(scan_paths or [])
        normalized_clone_path = normalize_repo_clone_path(clone_path, normalized_scan_paths)
        write_repo_settings(normalized_scan_paths, normalized_clone_path)
        return repo_settings_snapshot()

    def read_dev_settings(self) -> dict[str, Any]:
        return dev_settings_snapshot()

    def save_dev_settings(self, launcher_update_api_url: str | None = None) -> dict[str, Any]:
        url = normalize_launcher_update_api_url(launcher_update_api_url or "")
        write_dev_settings(url)
        snapshot = dev_settings_snapshot()
        snapshot["message"] = "Dev update path saved." if url else "Dev update path reset."
        return snapshot

    def app_runtime_info(self) -> dict[str, Any]:
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

    def scan_siblings(self, scan_roots: list[str] | None = None) -> dict[str, Any]:
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

    def check_environment(self, project_path: str | None = None, scan_root: str | None = None) -> dict[str, Any]:
        parent = resolve_scan_root(scan_root)
        project = Path(project_path) if project_path else None
        checks = [
            check_git(),
            check_python(),
            check_venv(project),
            check_python_dependencies(project),
            check_rom(project),
        ]
        if is_windows():
            checks.extend(check_windows_build_tools(project))
        elif uses_downloaded_linux_game_executable():
            checks.append(check_linux_game_executable_download(project))
        else:
            checks.extend(check_unix_build_tools())
        return {"os": os_name(), "parent_path": display_path(parent), "checks": checks, "next_steps": []}

    def launch_game(self, executable_path: str) -> dict[str, Any]:
        executable = Path(executable_path)
        executable_dir = executable.parent
        if not executable_dir:
            raise LauncherError("The executable path has no parent folder.")
        working_dir = launch_working_dir(executable, executable_dir)
        try:
            subprocess.Popen(
                [display_path(executable)],
                cwd=display_path(working_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=command_env(),
                **hidden_subprocess_kwargs(),
            )
        except OSError as error:
            raise LauncherError(f"Could not launch game: {error}") from error
        return action_result(True, "Game launched.")

    def choose_scan_root(self) -> str | None:
        return pick_folder("Select repo scan folder")

    def clone_project(self, scan_root: str | None = None, beta: bool | None = None) -> dict[str, Any]:
        ensure_clone_scan_root(scan_root)
        parent = resolve_scan_root(scan_root)
        use_beta = bool(beta)
        repo_name = "Z3R-Beta" if use_beta else "Z3R"
        repo_url = Z3R_BETA_REPO_URL if use_beta else Z3R_REPO_URL
        target = parent / repo_name
        if target.exists():
            raise LauncherError(f"Target folder already exists: {display_path(target)}")

        result = run_command(git_program(), ["clone", "--recursive", repo_url, repo_name], parent, "Clone complete.")
        return self.attach_rom_copy_message(target, result)

    def clone_custom_project(self, repo_url: str, scan_root: str | None = None) -> dict[str, Any]:
        ensure_clone_scan_root(scan_root)
        parent = resolve_scan_root(scan_root)
        normalized_url = normalize_github_url(repo_url)
        owner, repo = github_repo_owner_and_name(normalized_url)
        owner_dir = parent / owner
        target = owner_dir / repo
        if target.exists():
            raise LauncherError(f"Target folder already exists: {display_path(target)}")
        owner_dir.mkdir(parents=True, exist_ok=True)
        relative_target = f"{owner}/{repo}"
        result = run_command(git_program(), ["clone", "--recursive", normalized_url, relative_target], parent, "Custom clone complete.")
        return self.attach_rom_copy_message(target, result)

    def open_project_folder(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        if not project.is_dir():
            raise LauncherError(f"Project folder does not exist: {display_path(project)}")
        open_path(project, "project folder")
        return action_result(True, f"Opened project folder: {display_path(project)}")

    def create_venv(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        program = python_program()
        result = run_command(program, ["-m", "venv", ".venv"], project, "Virtual environment created.")
        if not result["ok"]:
            result = add_venv_creation_guidance(result, program, project)
        return result

    def install_dependencies(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        python = venv_python(project / ".venv") or venv_python(project / "venv")
        if not python:
            raise LauncherError("Create a venv before installing dependencies.")
        requirements = project / "requirements.txt"
        if not requirements.is_file():
            raise LauncherError(f"The selected project does not contain requirements.txt: {display_path(requirements)}")
        ssl_check = python_ssl_check(display_path(python), project)
        if not ssl_check["ok"]:
            return ssl_check
        return run_command(display_path(python), ["-m", "pip", "install", "-r", display_path(requirements)], project, "Python dependencies installed.")

    def extract_assets(self, project_path: str) -> dict[str, Any]:
        return self.extract_assets_with_route(project_path, "automatic")

    def extract_assets_visual_studio(self, project_path: str) -> dict[str, Any]:
        return self.extract_assets_with_route(project_path, "visual_studio")

    def extract_assets_tcc(self, project_path: str) -> dict[str, Any]:
        return self.extract_assets_with_route(project_path, "tcc")

    def open_external_url(self, url: str) -> None:
        open_external_url(url)
        return None

    def apply_snesrev_makefile_patch(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        if not project.is_dir():
            raise LauncherError(f"Project folder does not exist: {display_path(project)}")
        destination = project / "Makefile"
        destination.write_text(resource_text("patches/snesrev-zelda3/Makefile"), encoding="utf-8")
        return action_result(True, f"Patched Makefile installed at {display_path(destination)}.")

    def apply_snesrev_solution_patch(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        apply_windows_solution_patch_to_project(project)
        return action_result(True, f"Patched solution installed in {display_path(project)}.")

    def stored_rom_status(self) -> dict[str, Any]:
        return rom_status()

    def choose_and_store_rom(self) -> dict[str, Any] | None:
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

    def store_rom_upload(self, file_name: str, data_base64: str) -> dict[str, Any]:
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

    def open_stored_rom_folder(self) -> dict[str, Any]:
        storage = rom_storage_dir()
        storage.mkdir(parents=True, exist_ok=True)
        open_path(storage, "ROM storage folder")
        return action_result(True, f"Opened ROM storage folder: {display_path(storage)}")

    def sync_stored_rom_to_projects(self, project_paths: list[str]) -> dict[str, Any]:
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

    def read_zelda_ini(self, project_path: str) -> dict[str, Any]:
        path = Path(project_path) / "zelda3.ini"
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError as error:
            raise LauncherError(f"Could not read {display_path(path)}: {error}") from error
        return build_ini_snapshot(project_path, contents)

    def update_zelda_ini_line(self, project_path: str, line_number: int, raw_line: str) -> dict[str, Any]:
        path = Path(project_path) / "zelda3.ini"
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError as error:
            raise LauncherError(f"Could not read {display_path(path)}: {error}") from error
        lines, newline = split_preserving_newline(contents)
        if line_number <= 0 or line_number > len(lines):
            raise LauncherError(f"zelda3.ini line {line_number} is out of range (file has {len(lines)} lines).")
        lines[line_number - 1] = raw_line
        try:
            path.write_text(newline.join(lines), encoding="utf-8")
        except OSError as error:
            raise LauncherError(f"Could not write {display_path(path)}: {error}") from error
        return action_result(True, f"zelda3.ini line {line_number} updated.", raw_line)

    def set_zelda_ini_value(self, project_path: str, section: str, key: str, value: str) -> dict[str, Any]:
        section_name = clean_ini_section_name(section)
        key_name = clean_ini_key_name(key)
        value_text = clean_ini_value(value)
        path = Path(project_path) / "zelda3.ini"
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError as error:
            raise LauncherError(f"Could not read {display_path(path)}: {error}") from error

        lines, newline = split_preserving_newline(contents)
        raw_line = f"{key_name} = {value_text}"
        upsert_ini_line(lines, section_name, key_name, raw_line)

        try:
            path.write_text(newline.join(lines), encoding="utf-8")
        except OSError as error:
            raise LauncherError(f"Could not write {display_path(path)}: {error}") from error
        return action_result(True, f"zelda3.ini {section_name}.{key_name} updated.", raw_line)

    def read_feature_assets(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        storage = rom_storage_dir()
        return {
            "storage_dir": display_path(storage),
            "msu_download_url": MSU_DOWNLOAD_URL,
            "sprites_source_url": SPRITES_SOURCE_URL,
            "shaders_source_url": SHADERS_SOURCE_URL,
            "msu": build_group(
                list_msu_options(project / MSU_DIR, "project", True),
                list_msu_options(storage / MSU_DIR, "shared", False),
            ),
            "sprites": build_group(
                list_file_options(project / SPRITES_DIR, SPRITES_DIR, ["zspr"], "project"),
                list_file_options(storage / SPRITES_DIR, SPRITES_DIR, ["zspr"], "shared"),
            ),
            "shaders": build_group(
                list_file_options(project / SHADERS_DIR, SHADERS_DIR, ["glsl", "glslp"], "project"),
                list_file_options(storage / SHADERS_DIR, SHADERS_DIR, ["glsl", "glslp"], "shared"),
            ),
        }

    def clone_feature_asset(self, asset_kind: str) -> dict[str, Any]:
        catalog = {
            "sprites": (SPRITES_DIR, SPRITES_SOURCE_URL, "sprites", ["zspr"]),
            "shaders": (SHADERS_DIR, SHADERS_SOURCE_URL, "shaders", ["glsl", "glslp"]),
        }
        if asset_kind not in catalog:
            raise LauncherError("Unknown cloneable feature asset.")
        folder, url, label, extensions = catalog[asset_kind]
        storage = rom_storage_dir()
        destination = storage / folder
        if destination.is_dir():
            options = list_file_options(destination, folder, extensions, "shared")
            if options:
                return action_result(True, f"{label} repository is already available.", display_path(destination))
            if (destination / ".git").is_dir():
                return run_command(git_program(), ["pull", "--ff-only"], destination, f"Updated {label}.")
            raise LauncherError(
                f"{label} folder exists but contains no supported assets: {display_path(destination)}"
            )
        storage.mkdir(parents=True, exist_ok=True)
        return run_command(git_program(), ["clone", url, folder], storage, f"Cloned {label}.")

    def choose_and_store_msu(self) -> dict[str, Any] | None:
        selected = pick_folder("Select extracted MSU folder")
        if not selected:
            return None
        return store_msu_sources([Path(selected)])

    def store_msu_paths(self, paths: list[str]) -> dict[str, Any]:
        return store_msu_sources([Path(path) for path in paths])

    def install_feature_asset(self, project_path: str, asset_kind: str, asset_value: str) -> dict[str, Any]:
        project = Path(project_path)
        storage = rom_storage_dir()
        if asset_kind == "sprites":
            return install_single_asset(project, storage, asset_value)
        if asset_kind == "shaders":
            return install_shader_asset(project, storage, asset_value)
        if asset_kind == "msu":
            return install_msu_asset(project, storage, asset_value)
        raise LauncherError("Unknown feature asset type.")

    def read_sprite_preview(self, project_path: str, sprite_path: str) -> dict[str, Any]:
        relative = safe_relative_path(sprite_path)
        project = Path(project_path)
        storage = rom_storage_dir()
        sprite = next((path for path in (project / relative, storage / relative) if path.is_file()), None)
        if not sprite:
            raise LauncherError(f"Selected sprite was not found in the build or shared storage: {display_path(relative)}")
        try:
            bytes_data = sprite.read_bytes()
        except OSError as error:
            raise LauncherError(f"Could not read sprite {display_path(sprite)}: {error}") from error
        pixel_data, palette_data = parse_zspr_preview(bytes_data)
        return {
            "label": sprite.stem or display_path(relative),
            "pixel_data": list(pixel_data),
            "palette_data": list(palette_data),
        }

    def read_link_sprite_preview(self, project_path: str) -> dict[str, Any]:
        """Return Link sprite pixels for palette previews, preferring active LinkGraphics ZSPR."""

        project = Path(project_path)
        link_graphics = active_link_graphics(project)
        if link_graphics:
            return self.read_link_sprite_zspr_preview(project, link_graphics)
        try:
            pixel_data = read_compiled_link_graphics(project)
        except LinkSpritePreviewError as error:
            raise LauncherError(str(error)) from error
        return {
            "label": "Compiled Link graphics",
            "source": "zelda3_assets.dat",
            "pixel_data": list(pixel_data),
        }

    def read_link_sprite_zspr_preview(self, project: Path, sprite_path: str) -> dict[str, Any]:
        """Read the active LinkGraphics ZSPR file and return only its pixel data for recoloring."""

        relative = safe_relative_path(sprite_path)
        storage = rom_storage_dir()
        sprite = next((path for path in (project / relative, storage / relative) if path.is_file()), None)
        if not sprite:
            raise LauncherError(f"Active LinkGraphics sprite was not found: {display_path(relative)}")
        try:
            bytes_data = sprite.read_bytes()
        except OSError as error:
            raise LauncherError(f"Could not read sprite {display_path(sprite)}: {error}") from error
        pixel_data, _palette_data = parse_zspr_preview(bytes_data)
        return {
            "label": sprite.stem or display_path(relative),
            "source": path_to_slash(relative),
            "pixel_data": list(pixel_data),
        }

    def read_link_sprite_palette(self, project_path: str) -> dict[str, Any]:
        try:
            return read_link_sprite_palette_file(Path(project_path))
        except LinkSpritePaletteError as error:
            raise LauncherError(str(error)) from error
        except OSError as error:
            raise LauncherError(f"Could not read Link sprite palette: {error}") from error

    def save_link_sprite_palette(
        self,
        project_path: str,
        values: list[Any],
        active: bool = True,
    ) -> dict[str, Any]:
        try:
            snapshot = write_link_sprite_palette_file(Path(project_path), values, active)
        except LinkSpritePaletteError as error:
            raise LauncherError(str(error)) from error
        except OSError as error:
            raise LauncherError(f"Could not write Link sprite palette: {error}") from error
        snapshot["message"] = (
            "Link sprite palette override saved."
            if active
            else "Link sprite palette override disabled."
        )
        return snapshot

    def build_link_sprite_assets(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        python = venv_python(project / ".venv") or venv_python(project / "venv")
        if not python:
            raise LauncherError("Create a venv before rebuilding Link sprite assets.")
        if not (project / "assets" / "restool.py").is_file():
            raise LauncherError(
                f"The selected project does not contain assets/restool.py: {display_path(project)}"
            )
        return run_command(
            display_path(python),
            ["assets/restool.py"],
            project,
            "Link sprite asset file rebuilt.",
        )

    def read_randomizer_setup(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        entry_path = project / "assets" / "restool-randomize.py"
        engine_path = project / "assets" / "randomizer.py"
        config_files = [
            file_status("Randomizer CLI", entry_path),
            capability_status("Safe Mode support", entry_path, "--mode", "Update the selected Z3R folder's randomizer scripts before using Safe Mode."),
            file_status("Randomizer engine", engine_path),
            file_status("Vanilla masterlist", project / "assets" / "randomizer-masterlist.json"),
            folder_status("Dungeon YAML", project / "assets" / "dungeon", "Extract assets before randomizing if this folder is missing."),
            folder_status("Spoiler logs", project / "assets" / "randomizer-spoilers", "Created automatically when randomizer runs with spoiler output enabled."),
        ]
        return {
            "project_path": display_path(project),
            "available": entry_path.is_file() and engine_path.is_file(),
            "item_options": read_item_options(project / "assets" / "randomizer-masterlist.json"),
            "config_files": config_files,
        }

    def extract_randomizer_assets(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        python = project_python(project)
        extract = run_command(display_path(python), ["assets/restool.py", "--extract-from-rom", "--no-build"], project, "Randomizer asset extraction complete.")
        if not extract["ok"]:
            return extract
        masterlist = run_command(display_path(python), ["assets/restool-randomize.py", "--generate-masterlist"], project, "Randomizer masterlist generated.")
        return combine_results("Randomizer assets extracted and vanilla masterlist generated.", extract, masterlist)

    def run_randomizer(self, project_path: str, options: dict[str, Any]) -> dict[str, Any]:
        project = Path(project_path)
        python = project_python(project)
        entry_path = project / "assets" / "restool-randomize.py"
        options = options or {}
        requested_mode = options.get("mode") or "safe"
        if requested_mode == "safe" and not file_contains(entry_path, "--mode"):
            raise LauncherError(
                "The selected Z3R folder's randomizer CLI does not support Safe Mode yet. "
                "Update assets/restool-randomize.py and assets/randomizer.py in that folder, then try again."
            )
        args = ["assets/restool-randomize.py"]
        for key, flag in (("mode", "--mode"), ("seed", "--seed")):
            push_option(args, flag, options.get(key))
        if options.get("dry_run"):
            args.append("--dry-run")
        if options.get("no_spoiler"):
            args.append("--no-spoiler")
        if options.get("include_small_keys"):
            args.append("--include-small-keys")
        if options.get("include_big_chests"):
            args.append("--include-big-chests")
        for key, flag in (
            ("exclude_rooms", "--exclude-room"),
            ("exclude_locations", "--exclude-location"),
            ("exclude_items", "--exclude-item"),
            ("exclude_categories", "--exclude-category"),
        ):
            push_option(args, flag, options.get(key))
        return run_command(display_path(python), args, project, "Randomizer run complete.")

    def restore_vanilla_randomizer_yaml(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        python = project_python(project)
        return run_command(display_path(python), ["assets/restool-randomize.py", "--restore-vanilla"], project, "Vanilla randomizer YAML restored.")

    def compile_randomized_assets(self, project_path: str) -> dict[str, Any]:
        project = Path(project_path)
        python = project_python(project)
        return run_command(display_path(python), ["assets/restool.py"], project, "Randomized assets compiled.")

    def preview_repo_update(self, project_path: str) -> dict[str, Any]:
        project = repo_project_path(project_path)
        ensure_git_repo(project)
        git_output(project, ["fetch", "--prune"])
        upstream = upstream_ref(project)
        behind = behind_count(project, upstream)
        changes = upstream_changes(project, upstream)
        dirty = dirty_files(project)
        return {
            "project_path": display_path(project),
            "upstream": upstream,
            "behind_count": behind,
            "changes": changes,
            "warnings": update_warnings(changes, dirty),
            "dirty_files": dirty,
            "can_apply": bool(changes),
        }

    def apply_repo_update(self, project_path: str, selected_files: list[str]) -> dict[str, Any]:
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
        dirty = set(dirty_files(project))
        conflicting: list[str] = []
        for path in selected:
            change = changes_by_path[path]
            if path in dirty:
                conflicting.append(path)
            old_path = change.get("old_path")
            if old_path and old_path in dirty:
                conflicting.append(old_path)
        conflicting = sorted(set(conflicting))
        if conflicting:
            return action_result(False, "Selected files have local edits. Back them up or uncheck them before updating.", "\n".join(conflicting))
        applied: list[str] = []
        for path in selected:
            apply_change(project, upstream, changes_by_path[path])
            applied.append(path)
        return action_result(True, "Selected repo changes applied.", "\n".join(applied))

    def install_launcher_update(self) -> dict[str, Any]:
        current_version = current_update_version()
        update_dir = update_work_dir()
        update_dir.mkdir(parents=True, exist_ok=True)
        release = fetch_latest_release(update_dir)
        ordering = compare_versions(release["tag_name"], current_version)
        if ordering < 0:
            return action_result(True, f"Launcher {current_version} is newer than the latest published release {release['tag_name']}.")
        if ordering == 0:
            return action_result(True, f"Launcher is already up to date ({current_version}).")
        if is_flatpak_runtime():
            return self.install_flatpak_update(release, update_dir)
        if is_windows():
            return self.install_windows_update(release, update_dir)
        if is_macos():
            return self.install_macos_update(release, update_dir)
        if is_linux():
            return self.install_appimage_update(release, update_dir)
        raise LauncherError("Launcher updates are not packaged for this operating system yet.")

    def attach_rom_copy_message(self, project_path: Path, result: dict[str, Any]) -> dict[str, Any]:
        if not result["ok"]:
            return result
        clone_message = result["message"]
        copied = copy_stored_rom_to_project(project_path)
        if copied:
            result["message"] = f"{clone_message} SFC copied to {display_path(copied)}."
        else:
            result["message"] = f"{clone_message} No uploaded SFC is available to copy yet."
        return result

    def extract_assets_with_route(self, project_path: str, route: str) -> dict[str, Any]:
        project = Path(project_path)
        python = venv_python(project / ".venv") or venv_python(project / "venv")
        if not python:
            raise LauncherError("Create a venv before extracting assets.")
        extract = run_command(display_path(python), ["assets/restool.py", "--extract-from-rom"], project, "Asset extraction complete.")
        if not extract["ok"]:
            return extract
        if uses_downloaded_linux_game_executable():
            download = install_prebuilt_linux_game_executable(project)
            return combine_results("Asset extraction and executable download complete.", extract, download)
        build = self.build_executable(project, route)
        stdout = join_stage_output(extract["stdout"], build["stdout"])
        stderr = join_stage_output(extract["stderr"], build["stderr"])
        message = "Asset extraction and build complete." if build["ok"] else f"Build step failed after asset extraction: {build['message']}"
        return action_result(build["ok"], message, stdout, stderr)

    def build_executable(self, project: Path, route: str) -> dict[str, Any]:
        if is_windows():
            if route == "tcc":
                return run_tcc_build(project)
            if route == "visual_studio":
                return run_visual_studio_build(project)
            if (project / "third_party" / "tcc" / "tcc.exe").is_file():
                return run_tcc_build(project)
            return run_visual_studio_build(project)
        jobs = str(os.cpu_count() or 2)
        compiler = c_compiler_program()
        if not compiler:
            return action_result(False, missing_c_compiler_message())
        return run_command("make", [f"-j{jobs}", f"CC={compiler}"], project, "Build complete.")

    def install_windows_update(self, release: dict[str, Any], update_dir: Path) -> dict[str, Any]:
        asset = exact_asset(release, "Z3R-Launcher-windows-x64.exe")
        downloaded_exe = download_release_asset(asset, update_dir)
        script_path = update_dir / "apply-windows-update.ps1"
        log_path = update_dir / "apply-windows-update.log"
        target_path = current_executable_path()
        write_windows_update_script(script_path)
        subprocess.Popen([
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-LauncherPid",
            str(os.getpid()),
            "-Downloaded",
            str(downloaded_exe),
            "-Target",
            str(target_path),
            "-Relaunch",
            str(target_path),
            "-Log",
            str(log_path),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())
        self.schedule_exit()
        return action_result(
            True,
            f"Launcher update {release['tag_name']} downloaded. The launcher will close so the exe can be replaced.",
            f"Executable: {display_path(downloaded_exe)}\nUpdater log: {display_path(log_path)}",
        )

    def install_macos_update(self, release: dict[str, Any], update_dir: Path) -> dict[str, Any]:
        bundle_path = current_macos_bundle_path()
        asset = first_release_asset(release, [macos_update_asset_name(), "Z3R-Launcher-macos-universal.dmg"])
        dmg_path = download_release_asset(asset, update_dir)
        script_path = update_dir / "apply-macos-update.sh"
        mount_path = update_dir / "macos-dmg-mount"
        log_path = update_dir / "apply-macos-update.log"
        app_name = bundle_path.name
        write_macos_update_script(script_path)
        make_executable(script_path)
        subprocess.Popen([
            "/bin/sh",
            str(script_path),
            str(os.getpid()),
            str(dmg_path),
            str(mount_path),
            str(bundle_path),
            app_name,
            str(log_path),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())
        self.schedule_exit()
        return action_result(True, f"Launcher update {release['tag_name']} downloaded. The launcher will close, replace the app bundle, and reopen.", f"Updater log: {display_path(log_path)}")

    def install_flatpak_update(self, release: dict[str, Any], update_dir: Path) -> dict[str, Any]:
        asset = exact_asset(release, "Z3R-Launcher-linux.flatpak")
        bundle = download_release_asset(asset, update_dir)
        scope_arg = flatpak_install_scope_arg()
        output = run_process("flatpak-spawn", ["--host", "flatpak", "install", scope_arg, "--or-update", "--assumeyes", "--noninteractive", display_path(bundle)], capture=True)
        if output.returncode != 0:
            detail = decode_output(output.stderr).strip() or decode_output(output.stdout).strip()
            raise LauncherError(detail or f"Flatpak launcher install exited with status {output.returncode}")
        spawn_flatpak_relaunch()
        self.schedule_exit()
        return action_result(
            True,
            f"Launcher update {release['tag_name']} installed through Flatpak. The launcher will close and reopen.",
            decode_output(output.stdout).strip(),
            decode_output(output.stderr).strip(),
        )

    def install_appimage_update(self, release: dict[str, Any], update_dir: Path) -> dict[str, Any]:
        current_appimage = current_appimage_path()
        asset = exact_asset(release, "Z3R-Launcher-linux-x64.AppImage")
        downloaded_appimage = download_release_asset(asset, update_dir)
        script_path = update_dir / "apply-appimage-update.sh"
        log_path = update_dir / "apply-appimage-update.log"
        write_appimage_update_script(script_path)
        make_executable(script_path)
        subprocess.Popen([
            "/bin/sh",
            str(script_path),
            str(os.getpid()),
            str(downloaded_appimage),
            str(current_appimage),
            str(log_path),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())
        self.schedule_exit()
        return action_result(True, f"Launcher update {release['tag_name']} downloaded. The launcher will close, replace the AppImage, and reopen.", f"Updater log: {display_path(log_path)}")


def default_clone_requires_scan_path() -> bool:
    return is_flatpak_runtime() or is_packaged_macos()


def is_packaged_macos() -> bool:
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
    link_sprite_editor_available = (path / "assets" / "sprite_sheets.py").is_file()
    git_repo = (path / ".git").exists()
    if not asset_path and not executable_path and not has_source:
        return None
    notes: list[str] = []
    if asset_path and executable_path:
        if executable_path.parent == asset_path.parent or is_windows_runtime_output(executable_path):
            status = "ready"
        else:
            notes.append("Executable and zelda3_assets.dat are not beside each other; use a deploy build or copy assets beside the executable.")
            status = "needs-deploy-copy"
    elif asset_path:
        status = "assets-ready"
    elif executable_path:
        status = "missing-assets"
    else:
        status = "source-only"
    is_snesrev = is_discovered_snesrev_zelda3(path, owner)
    makefile_applied = is_snesrev and has_snesrev_makefile_patch(path)
    solution_applied = is_snesrev and has_solution and has_snesrev_solution_patch(path)
    return {
        "name": path.name or display_path(path),
        "owner": owner,
        "path": display_path(path),
        "asset_path": display_path(asset_path) if asset_path else None,
        "executable_path": display_path(executable_path) if executable_path else None,
        "git_repo": git_repo,
        "snesrev_makefile_patch_applied": makefile_applied,
        "snesrev_solution_patch_applied": solution_applied,
        "source_patch_needed": source_patch_for_platform(is_snesrev, has_solution, makefile_applied, solution_applied),
        "link_sprite_editor_available": link_sprite_editor_available,
        "status": status,
        "notes": notes,
    }


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


def ok_check(id_value: str, label: str, detail: str) -> dict[str, str]:
    return {"id": id_value, "label": label, "state": "ok", "detail": detail}


def missing_check(id_value: str, label: str, detail: str) -> dict[str, str]:
    return {"id": id_value, "label": label, "state": "missing", "detail": detail}


def unknown_check(id_value: str, label: str, detail: str) -> dict[str, str]:
    return {"id": id_value, "label": label, "state": "unknown", "detail": detail}


def python_ssl_check(program: str, cwd: Path | None = None) -> dict[str, Any]:
    try:
        output = run_process(program, ["-c", "import ssl; print(ssl.OPENSSL_VERSION)"], cwd=cwd, capture=True)
    except OSError as error:
        raise LauncherError(f"Could not run {program}: {error}") from error
    stdout = decode_output(output.stdout)
    stderr = decode_output(output.stderr)
    if output.returncode == 0:
        detail = stdout.strip()
        message = f"Python SSL support is available ({detail})." if detail else "Python SSL support is available."
        return action_result(True, message, stdout, stderr)
    return action_result(
        False,
        "The selected Python cannot import ssl, so pip cannot download HTTPS packages. Recreate the venv after installing a Python build with SSL support.",
        stdout,
        stderr,
    )


def check_git() -> dict[str, str]:
    if is_windows():
        path = bundled_git()
        if path:
            return ok_check("git", "Git", bundled_detail("Git", path))
    return check_command("git", "git", "Git", ["--version"], "Required for cloning and updating the Z3R repo.")


def check_python() -> dict[str, str]:
    if is_windows():
        path = bundled_python()
        if path:
            return ok_check("python", "Python", bundled_detail("Python", path))
        commands = [("py", ["--version"]), ("python", ["--version"])]
    else:
        commands = [("python3", ["--version"]), ("python", ["--version"])]
    for program, args in commands:
        check = check_command("python", program, "Python", args, "Required for asset extraction and venv setup.")
        if check["state"] == "ok":
            ssl_check = python_ssl_check(program)
            if not ssl_check["ok"]:
                return missing_check("python", "Python", ssl_check["message"])
            return check
    return missing_check("python", "Python", "Python was not found on PATH.")


def check_venv(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("venv", "Python virtual environment", "Select or clone a Z3R folder before checking its venv.")
    for folder in (project_path / ".venv", project_path / "venv"):
        if venv_python(folder):
            return ok_check("venv", "Python virtual environment", f"Found {display_path(folder)}")
    return missing_check("venv", "Python virtual environment", missing_venv_detail())


def missing_venv_detail() -> str:
    if is_linux():
        return "Create one with the Create venv button. On Debian/Ubuntu, install `python3-venv` if Python reports ensurepip is missing."
    return "Create one with `python -m venv .venv` inside the Z3R folder."


def check_python_dependencies(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("python-dependencies", "Python dependencies", "Select or clone a Z3R folder before checking Pillow and PyYAML.")
    python = venv_python(project_path / ".venv") or venv_python(project_path / "venv")
    if not python:
        return missing_check("python-dependencies", "Python dependencies", "Create a venv before installing or checking Python requirements.")
    ssl_check = python_ssl_check(display_path(python), project_path)
    if not ssl_check["ok"]:
        return missing_check("python-dependencies", "Python dependencies", ssl_check["message"])
    return check_command("python-dependencies", display_path(python), "Python dependencies", ["-c", "import PIL, yaml"], "Install dependencies with the venv before extracting assets.")


def c_compiler_program() -> str | None:
    path = command_env().get("PATH")
    for program in C_COMPILER_CANDIDATES:
        found = shutil.which(program, path=path)
        if found:
            return found
    return None


def check_c_compiler() -> dict[str, str]:
    path = command_env().get("PATH")
    for program in C_COMPILER_CANDIDATES:
        found = shutil.which(program, path=path)
        if not found:
            continue
        check = check_command("c-compiler", found, "C compiler", ["--version"], "Required to compile Z3R.")
        if check["state"] == "ok":
            check["detail"] = f"Found {found}: {check['detail']}"
            return check
    return missing_check("c-compiler", "C compiler", missing_c_compiler_message())


def missing_c_compiler_message() -> str:
    return "Required to compile Z3R. Install gcc or clang."


def check_rom(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("rom", "Game ROM (zelda3.sfc)", "Select or clone a Z3R folder before checking the ROM.")
    rom = project_path / STORED_ROM_NAME
    if rom.is_file():
        return ok_check("rom", "Game ROM (zelda3.sfc)", f"Found {display_path(rom)}")
    return missing_check("rom", "Game ROM (zelda3.sfc)", "Upload your SFC in the launcher, or place it as zelda3.sfc in the Z3R folder.")


def check_linux_game_executable_download(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("game-executable-download", "Linux executable download", "Select or clone a Z3R folder before checking executable downloads.")
    try:
        spec = project_release_spec(project_path)
    except LauncherError as error:
        return missing_check("game-executable-download", "Linux executable download", str(error))
    return ok_check("game-executable-download", "Linux executable download", f"Will download {spec['label']} from {spec['releases_url']}.")


def check_windows_build_tools(project_path: Path | None) -> list[dict[str, str]]:
    checks = [
        check_msbuild(),
        check_command("powershell", "where", "PowerShell", ["powershell"], "PowerShell can activate .venv and run setup commands."),
    ]
    if project_path:
        tcc = project_path / "third_party" / "tcc" / "tcc.exe"
        sdl = project_path / "third_party" / "SDL2-2.26.3" / "lib" / "x64" / "SDL2.dll"
        checks.append(check_project_or_bundled_file("tcc", "TCC", tcc, bundled_tcc(), "Required only for the lightweight TCC route."))
        checks.append(check_project_or_bundled_file("sdl2", "SDL2", sdl, bundled_sdl2_dll(), "Required by the TCC route and game runtime on Windows."))
    return checks


def check_msbuild() -> dict[str, str]:
    path = find_msbuild()
    if path:
        return ok_check("msbuild", "MSBuild", f"Found {display_path(path)}")
    return missing_check("msbuild", "MSBuild", "Install Build Tools for Visual Studio with Desktop development with C++.")


def check_unix_build_tools() -> list[dict[str, str]]:
    return [
        check_command("make", "make", "Make", ["--version"], "Required to compile Z3R on macOS and Linux."),
        check_c_compiler(),
        check_command("sdl2-dev", "sdl2-config", "SDL2 development files", ["--version"], "Required by the Makefile compiler flags."),
    ]


def check_command(id_value: str, program: str, label: str, args: list[str], missing_detail: str) -> dict[str, str]:
    try:
        output = run_process(program, args, capture=True)
    except OSError:
        return missing_check(id_value, label, missing_detail)
    if output.returncode == 0:
        stdout = decode_output(output.stdout).strip()
        stderr = decode_output(output.stderr).strip()
        return ok_check(id_value, label, stdout or stderr)
    return missing_check(id_value, label, decode_output(output.stderr).strip())


def check_project_or_bundled_file(id_value: str, label: str, project_path: Path, bundled_path: Path | None, missing_detail: str) -> dict[str, str]:
    if project_path.is_file():
        return ok_check(id_value, label, f"Found {display_path(project_path)}")
    if bundled_path:
        return ok_check(id_value, label, bundled_detail(label, bundled_path))
    return missing_check(id_value, label, missing_detail)


def launch_working_dir(executable: Path, executable_dir: Path) -> Path:
    if not is_windows():
        return executable_dir
    bin_dir = executable_dir.parent
    project_dir = bin_dir.parent if bin_dir else None
    if not project_dir:
        return executable_dir
    is_visual_studio = bin_dir.name.lower() == "bin"
    has_windows_runtime = executable.name.lower() == "zelda3.exe" and (executable_dir / "SDL2.dll").is_file()
    return project_dir if is_visual_studio and has_windows_runtime else executable_dir


def normalize_github_url(repo_url: str) -> str:
    trimmed = repo_url.strip()
    if trimmed.startswith("git clone"):
        raise LauncherError("Paste only the GitHub repository URL, not a git clone command.")
    if re.search(r"\s", trimmed):
        raise LauncherError("The GitHub URL cannot contain spaces.")
    if not trimmed.startswith("https://github.com/"):
        raise LauncherError("Enter a GitHub URL that starts with https://github.com/.")
    return trimmed.rstrip("/")


def normalize_launcher_update_api_url(value: str) -> str:
    trimmed = value.strip()

    if not trimmed:
        return ""

    if trimmed.startswith("https://github.com/"):
        owner, repo = github_repo_owner_and_name(normalize_github_url(trimmed))
        return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    api_match = re.fullmatch(
        r"https://api\.github\.com/repos/([^/\s]+)/([^/\s]+)/releases/latest",
        trimmed.rstrip("/"),
    )
    if not api_match:
        raise LauncherError("Enter a GitHub repo URL or a GitHub latest-release API URL.")

    owner, repo = api_match.groups()
    if not is_safe_segment(owner) or not is_safe_segment(repo):
        raise LauncherError("The update repository path contains unsupported characters.")

    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


def github_repo_owner_and_name(repo_url: str) -> tuple[str, str]:
    repo_part = repo_url.removeprefix("https://github.com/").split("?", 1)[0].split("#", 1)[0]
    parts = repo_part.split("/")
    if len(parts) != 2:
        raise LauncherError("Enter a GitHub repository URL like https://github.com/owner/repo.")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        raise LauncherError("Enter a GitHub repository URL like https://github.com/owner/repo.")
    if not is_safe_segment(owner):
        raise LauncherError("The owner name contains characters this launcher cannot use for a folder.")
    if not is_safe_segment(repo):
        raise LauncherError("The repository name contains characters this launcher cannot use for a folder.")
    return owner, repo


def is_safe_segment(segment: str) -> bool:
    return all(character.isascii() and (character.isalnum() or character in "._-") for character in segment)


def add_venv_creation_guidance(result: dict[str, Any], program: str, project: Path) -> dict[str, Any]:
    output = f"{result['stdout']}\n{result['stderr']}"
    if not is_missing_ensurepip_error(output):
        return result
    if is_linux():
        result["message"] = linux_venv_support_message(python_version_venv_package(program, project))
    else:
        result["message"] = "Python could not create .venv because ensurepip is missing. Install Python venv support, then press Create venv again."
    return result


def is_missing_ensurepip_error(output: str) -> bool:
    return (
        "ensurepip is not available" in output
        or "No module named ensurepip" in output
        or "python3-venv" in output
        or ("python3." in output and "-venv" in output)
    )


def python_version_venv_package(program: str, cwd: Path) -> str:
    try:
        output = run_process(program, ["-c", "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}-venv')"], cwd=cwd)
    except OSError:
        return "python3-venv"
    package = decode_output(output.stdout).strip()
    return package if output.returncode == 0 and package else "python3-venv"


def linux_venv_support_message(version_package: str) -> str:
    if version_package == "python3-venv":
        return "Python could not create .venv because ensurepip is missing. On Debian/Ubuntu, run `sudo apt-get install python3-venv`, then press Create venv again."
    return (
        f"Python could not create .venv because ensurepip is missing. On Debian/Ubuntu, run `sudo apt-get install {version_package}`. "
        "If that package is unavailable, run `sudo apt-get install python3-venv`, then press Create venv again."
    )


def run_visual_studio_build(project: Path) -> dict[str, Any]:
    if is_snesrev_zelda3_project(project, None):
        apply_windows_solution_patch_to_project(project)
    msbuild = find_msbuild()
    if not msbuild:
        raise LauncherError("MSBuild was not found. Install Build Tools for Visual Studio or use the TCC route.")
    return run_command(display_path(msbuild), ["Zelda3.sln", "/restore", "/p:RestorePackagesConfig=true", "/p:Configuration=Release", "/p:Platform=x64"], project, "Visual Studio build complete.")


def run_tcc_build(project: Path) -> dict[str, Any]:
    prepared = prepare_tcc_project_tools(project)
    result = run_command("cmd", ["/C", "call", "run_with_tcc.bat"], project, "TCC build complete.")
    if result["ok"] and prepared:
        result["message"] = f"{' '.join(prepared)} {result['message']}"
    return result


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
    if "linux" not in lower:
        return False
    if not any(token in lower for token in ("x64", "x86_64", "amd64")):
        return False
    blocked_tokens = ("appimage", "flatpak", "windows", "macos", "darwin", "apple", "silicon", "arm64", "aarch64")
    return not any(token in lower for token in blocked_tokens)


def linux_game_executable_asset_score(name: str, spec: dict[str, Any]) -> int:
    lower = name.lower()
    score = 0
    if lower in LINUX_GAME_EXECUTABLE_NAMES:
        score += 100
    if lower.endswith(".tar.gz"):
        score += 40
    elif lower.endswith(".tgz"):
        score += 35
    elif lower.endswith(".tar"):
        score += 30
    elif lower.endswith(".zip"):
        score += 20
    if str(spec["label"]).lower() in lower:
        score += 10
    return score


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
    lower = path.name.lower()
    return lower.endswith((".tar.gz", ".tgz", ".tar"))


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


def prepare_tcc_project_tools(project: Path) -> list[str]:
    if not (project / "run_with_tcc.bat").is_file():
        raise LauncherError("run_with_tcc.bat was not found in the project root.")
    prepared: list[str] = []
    if ensure_project_tcc(project):
        prepared.append("Copied bundled TCC into third_party/tcc.")
    if ensure_project_sdl2(project):
        prepared.append("Copied bundled SDL2 into third_party/SDL2-2.26.3.")
    return prepared


def ensure_project_tcc(project: Path) -> bool:
    project_tcc = project / "third_party" / "tcc" / "tcc.exe"
    if project_tcc.is_file():
        return False
    bundled = bundled_tcc()
    if not bundled:
        raise LauncherError("TCC was not found in the project or bundled launcher tools.")
    copy_dir_contents(bundled.parent, project / "third_party" / "tcc")
    if not project_tcc.is_file():
        raise LauncherError("Copied bundled TCC, but third_party/tcc/tcc.exe is still missing.")
    return True


def ensure_project_sdl2(project: Path) -> bool:
    project_sdl_root = project / "third_party" / "SDL2-2.26.3"
    project_sdl_header = project_sdl_root / "include" / "SDL.h"
    project_sdl_dll = project_sdl_root / "lib" / "x64" / "SDL2.dll"
    if project_sdl_header.is_file() and project_sdl_dll.is_file():
        return False
    bundled = bundled_sdl2_root()
    if not bundled:
        raise LauncherError("SDL2 headers and SDL2.dll were not found in the project or bundled launcher tools.")
    copy_dir_contents(bundled, project_sdl_root)
    if not project_sdl_header.is_file() or not project_sdl_dll.is_file():
        raise LauncherError("Copied bundled SDL2, but third_party/SDL2-2.26.3 is still incomplete.")
    return True


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


def rom_status(force_current: bool = False) -> dict[str, Any]:
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


def build_ini_snapshot(project_path: str, contents: str) -> dict[str, Any]:
    current_section = ""
    graphics_lines: list[dict[str, Any]] = []
    sound_lines: list[dict[str, Any]] = []
    feature_lines: list[dict[str, Any]] = []
    keymap_lines: list[dict[str, Any]] = []
    gamepad_lines: list[dict[str, Any]] = []
    aspect_value: str | None = None
    aspect_line: int | None = None
    window_size_value: str | None = None
    window_size_line: int | None = None
    for index, raw_line in enumerate(contents.splitlines(), start=1):
        trimmed = raw_line.lstrip()
        section = parse_section_header(trimmed)
        if section:
            current_section = section
            continue
        parsed = parse_key_line(trimmed)
        if not parsed:
            continue
        key, value, commented = parsed
        if current_section == "General" and key.lower() == "extendedaspectratio":
            aspect_value = value
            aspect_line = index
            continue
        if current_section == "Graphics" and key.lower() == "windowsize":
            window_size_value = value
            window_size_line = index
            continue
        snapshot = {"line_number": index, "section": current_section, "key": key, "value": value, "commented": commented, "raw": raw_line}
        if current_section == "Graphics":
            graphics_lines.append(snapshot)
        elif current_section == "Sound":
            sound_lines.append(snapshot)
        elif current_section == "Features":
            feature_lines.append(snapshot)
        elif current_section == "KeyMap":
            keymap_lines.append(snapshot)
        elif current_section == "GamepadMap":
            gamepad_lines.append(snapshot)
    return {
        "project_path": project_path,
        "aspect_ratio": {
            "line_number": aspect_line or 0,
            "raw_value": aspect_value or "",
            "window_size_line": window_size_line or 0,
            "window_size_value": window_size_value or "Auto",
        },
        "graphics_lines": graphics_lines,
        "sound_lines": sound_lines,
        "feature_lines": feature_lines,
        "keymap_lines": keymap_lines,
        "gamepad_lines": gamepad_lines,
    }


def active_link_graphics(project: Path) -> str | None:
    """Return the active LinkGraphics value from zelda3.ini, ignoring commented examples."""

    path = project / "zelda3.ini"
    try:
        snapshot = build_ini_snapshot(str(project), path.read_text(encoding="utf-8"))
    except OSError:
        return None
    for line in snapshot["graphics_lines"]:
        if line["key"].lower() == "linkgraphics" and not line["commented"] and line["value"].strip():
            return line["value"].strip()
    return None


def clean_ini_section_name(section: str) -> str:
    name = str(section).strip()
    if not name or any(character in name for character in "[]\r\n"):
        raise LauncherError("The zelda3.ini section name is invalid.")
    return name


def clean_ini_key_name(key: str) -> str:
    name = str(key).strip()
    if not name or not is_key_shape(name):
        raise LauncherError("The zelda3.ini key name is invalid.")
    return name


def clean_ini_value(value: str) -> str:
    text = str(value).strip()
    if "\r" in text or "\n" in text:
        raise LauncherError("The zelda3.ini value cannot contain line breaks.")
    return text


def upsert_ini_line(lines: list[str], section: str, key: str, raw_line: str) -> None:
    target_section = section.lower()
    target_key = key.lower()
    in_target_section = False
    found_section = False
    insert_at: int | None = None

    for index, raw in enumerate(lines):
        section_name = parse_section_header(raw.lstrip())
        if section_name:
            if in_target_section:
                insert_at = index
                break
            in_target_section = section_name.lower() == target_section
            if in_target_section:
                found_section = True
                insert_at = index + 1
            continue

        if not in_target_section:
            continue

        parsed = parse_key_line(raw.lstrip())
        if parsed and parsed[0].lower() == target_key:
            lines[index] = raw_line
            return
        insert_at = index + 1

    if found_section:
        lines.insert(insert_at if insert_at is not None else len(lines), raw_line)
        return

    append_ini_section(lines, section, raw_line)


def append_ini_section(lines: list[str], section: str, raw_line: str) -> None:
    insert_at = len(lines) - 1 if lines and lines[-1] == "" else len(lines)
    addition = [f"[{section}]", raw_line]

    if insert_at > 0 and lines[insert_at - 1].strip():
        addition.insert(0, "")

    lines[insert_at:insert_at] = addition


def parse_section_header(trimmed: str) -> str | None:
    if not trimmed.startswith("[") or "]" not in trimmed:
        return None
    name = trimmed[1:trimmed.find("]")].strip()
    return name or None


def parse_key_line(trimmed: str) -> tuple[str, str, bool] | None:
    if not trimmed:
        return None
    commented = False
    body = trimmed
    if body.startswith("#") or body.startswith(";"):
        commented = True
        body = body[1:].lstrip()
    if "=" not in body:
        return None
    key, value = body.split("=", 1)
    key = key.strip()
    if not key or not is_key_shape(key):
        return None
    return key, value.strip(), commented


def is_key_shape(key: str) -> bool:
    return all(character.isascii() and (character.isalnum() or character == "_") for character in key)


def split_preserving_newline(contents: str) -> tuple[list[str], str]:
    newline = "\r\n" if "\r\n" in contents else "\n"
    return contents.split(newline), newline


def collect_files(directory: Path, extensions: list[str]) -> list[Path]:
    files: list[Path] = []
    if not directory.is_dir():
        return files
    for child in directory.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            files.extend(collect_files(child, extensions))
        elif path_has_extension(child, extensions):
            files.append(child)
    return files


def path_has_extension(path: Path, extensions: list[str]) -> bool:
    return path.suffix.lower().lstrip(".") in [extension.lower() for extension in extensions]


def path_to_slash(path: Path) -> str:
    return "/".join(part for part in path.parts if part not in (path.anchor, os.sep))


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or any(part in ("..", "") for part in path.parts):
        raise LauncherError("Selected asset path is not safe to copy.")
    if is_windows() and path.drive:
        raise LauncherError("Selected asset path is not safe to copy.")
    return path


def sanitize_folder_name(name: str) -> str:
    return "".join(character for character in name if character.isascii() and (character.isalnum() or character in "-_"))


def build_group(project_options: list[dict[str, str]], shared_options: list[dict[str, str]]) -> dict[str, Any]:
    options_by_value = {option["value"]: option for option in shared_options}
    options_by_value.update({option["value"]: option for option in project_options})
    return {
        "available": bool(project_options or shared_options),
        "project_available": bool(project_options),
        "shared_available": bool(shared_options),
        "options": [options_by_value[key] for key in sorted(options_by_value)],
    }


def list_file_options(base_dir: Path, value_root: str, extensions: list[str], source: str) -> list[dict[str, str]]:
    files = sorted(collect_files(base_dir, extensions))
    options: list[dict[str, str]] = []
    for path in files:
        relative = path.relative_to(base_dir)
        value = path_to_slash(Path(value_root) / relative)
        options.append({"label": path.stem or value, "value": value, "source": source})
    return options


def list_msu_options(root: Path, source: str, include_root_pack: bool) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    if not root.is_dir():
        return options
    if include_root_pack:
        prefix = detect_msu_prefix(root, root)
        if prefix:
            options.append({"label": "Project MSU", "value": f"{MSU_DIR}/{prefix}", "source": source})
    for child in root.iterdir():
        if not child.is_dir():
            continue
        prefix = detect_msu_prefix(root, child)
        if prefix:
            options.append({"label": child.name or prefix, "value": f"{MSU_DIR}/{prefix}", "source": source})
    options.sort(key=lambda option: option["label"])
    return options


def detect_msu_prefix(root: Path, folder: Path) -> str | None:
    audio_files = sorted(collect_files(folder, ["pcm", "opuz", "msu"]))
    for file in audio_files:
        prefix = msu_prefix_from_file(root, file)
        if prefix:
            return prefix
    return None


def msu_prefix_from_file(root: Path, file: Path) -> str | None:
    extension = file.suffix.lower().lstrip(".")
    stem = file.stem
    if extension in ("pcm", "opuz"):
        prefix = numbered_msu_prefix(stem)
    elif extension == "msu":
        prefix = f"{stem}-"
    else:
        prefix = None
    if not prefix:
        return None
    relative_parent = file.parent.relative_to(root)
    return path_to_slash(relative_parent / prefix)


def numbered_msu_prefix(stem: str) -> str | None:
    if "-" not in stem:
        return None
    base, track = stem.rsplit("-", 1)
    return f"{base}-" if track and track.isdigit() else None


def store_msu_sources(sources: list[Path]) -> dict[str, Any]:
    if not sources:
        raise LauncherError("No MSU files or folders were provided.")
    storage = rom_storage_dir() / MSU_DIR
    storage.mkdir(parents=True, exist_ok=True)
    pack_name = msu_pack_name(sources)
    destination = storage / pack_name
    copied = 0
    for source in sources:
        if source.is_dir():
            copied += copy_dir_contents(source, destination)
        elif source.is_file():
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination / source.name)
            copied += 1
    return action_result(True, f"Stored MSU pack {pack_name}.", f"{copied} file(s) copied to {display_path(destination)}")


def msu_pack_name(sources: list[Path]) -> str:
    first = sources[0]
    name_source = first.name if first.is_dir() else (first.parent.name if first.parent else "")
    name = sanitize_folder_name(name_source)
    if not name:
        raise LauncherError("Could not determine a folder name for the MSU pack.")
    return name


def install_single_asset(project: Path, storage: Path, asset_value: str) -> dict[str, Any]:
    relative = safe_relative_path(asset_value)
    destination = project / relative
    if destination.is_file():
        return installed_result("Asset already exists in the selected build.", relative)
    source = storage / relative
    if not source.is_file():
        raise LauncherError(f"Selected asset was not found in shared storage: {display_path(source)}")
    copy_file_with_parents(source, destination)
    return installed_result("Asset copied into the selected build.", relative)


def install_shader_asset(project: Path, storage: Path, asset_value: str) -> dict[str, Any]:
    relative = safe_relative_path(asset_value)
    if not relative.parts or relative.parts[0] != SHADERS_DIR:
        raise LauncherError("Selected shader path did not include the shader repository folder.")

    source_root = storage / SHADERS_DIR
    source = storage / relative
    destination_root = project / SHADERS_DIR
    destination = project / relative
    ignored_names = {".git"}

    if source.is_file():
        if folder_matches_all_files(source_root, destination_root, ignored_names):
            return installed_result("Shader repository already exists in the selected build.", relative)
        copy_dir_contents(source_root, destination_root, ignored_names)
        if not destination.is_file():
            raise LauncherError(f"Copied shaders, but selected shader is still missing: {display_path(destination)}")
        return installed_result("Shader repository copied into the selected build.", relative)

    if destination.is_file():
        return installed_result("Shader already exists in the selected build.", relative)
    if not source_root.is_dir():
        raise LauncherError(f"Shared shader repository was not found: {display_path(source_root)}")
    raise LauncherError(f"Selected shader was not found in the build or shared storage: {display_path(relative)}")


def install_msu_asset(project: Path, storage: Path, asset_value: str) -> dict[str, Any]:
    relative = safe_relative_path(asset_value)
    if msu_prefix_exists(project, asset_value):
        return installed_msu_result("MSU pack already exists in the selected build.", relative, msu_mode_for_prefix(project, asset_value))
    parts = relative.parts
    if len(parts) < 2:
        raise LauncherError("Selected MSU path did not include a pack folder.")
    pack_path = Path(parts[1])
    source = storage / MSU_DIR / pack_path
    destination = project / MSU_DIR / pack_path
    if not source.is_dir():
        raise LauncherError(f"Selected MSU pack was not found in shared storage: {display_path(source)}")
    copy_dir_contents(source, destination)
    return installed_msu_result("MSU pack copied into the selected build.", relative, msu_mode_for_prefix(project, asset_value))


def copy_file_with_parents(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def installed_result(message: str, relative: Path) -> dict[str, Any]:
    return action_result(True, message, path_to_slash(relative))


def installed_msu_result(message: str, relative: Path, mode: str) -> dict[str, Any]:
    return action_result(True, message, f"{path_to_slash(relative)}\n{mode}")


def msu_prefix_exists(project: Path, asset_value: str) -> bool:
    prefix_path = project / asset_value
    parent = prefix_path.parent
    prefix = prefix_path.name
    if not parent.is_dir() or not prefix:
        return False
    for entry in parent.iterdir():
        name = entry.name
        if name.startswith(prefix) and name.lower().endswith((".pcm", ".opuz", ".msu")):
            return True
    return False


def msu_mode_for_prefix(project: Path, asset_value: str) -> str:
    prefix_path = project / asset_value
    parent = prefix_path.parent
    prefix = prefix_path.name
    if not parent.is_dir() or not prefix:
        return "true"
    for entry in parent.iterdir():
        if entry.name.startswith(prefix) and entry.name.lower().endswith(".opuz"):
            return "opuz"
    return "true"


def parse_zspr_preview(data: bytes) -> tuple[bytes, bytes]:
    if len(data) < 21 or data[0:4] != b"ZSPR":
        raise LauncherError("Selected file is not a valid ZSPR sprite.")
    pixel_offset = read_u32_le(data, 9)
    pixel_length = read_u16_le(data, 13)
    palette_offset = read_u32_le(data, 15)
    palette_length = read_u16_le(data, 19)
    if pixel_length == 0:
        raise LauncherError("Selected ZSPR file does not include pixel data.")
    return (
        read_bounded_slice(data, pixel_offset, min(pixel_length, 0x7000)),
        read_bounded_slice(data, palette_offset, min(palette_length, 256)),
    )


def read_u16_le(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise LauncherError("Selected ZSPR file has a truncated header.")
    return int.from_bytes(data[offset:offset + 2], "little")


def read_u32_le(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise LauncherError("Selected ZSPR file has a truncated header.")
    return int.from_bytes(data[offset:offset + 4], "little")


def read_bounded_slice(data: bytes, offset: int, length: int) -> bytes:
    end = offset + length
    if end > len(data):
        raise LauncherError("Selected ZSPR file points outside its data.")
    return data[offset:end]


def project_python(project: Path) -> Path:
    python = venv_python(project / ".venv") or venv_python(project / "venv")
    if not python:
        raise LauncherError("Create a venv before using the randomizer setup screen.")
    return python


def read_item_options(masterlist_path: Path) -> list[dict[str, Any]]:
    try:
        manifest = json.loads(masterlist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    locations = manifest.get("locations")
    if not isinstance(locations, list):
        return []
    counts: dict[int, int] = {}
    for entry in locations:
        if isinstance(entry, dict) and isinstance(entry.get("item"), int) and 0 <= entry["item"] <= 255:
            counts[entry["item"]] = counts.get(entry["item"], 0) + 1
    return [
        {"id": item_id, "label": item_label(item_id), "count": count, "detail": f"Item id {item_id}; appears in {count} vanilla chest location(s)."}
        for item_id, count in sorted(counts.items())
    ]


def item_label(item_id: int) -> str:
    labels = {
        6: "Mirror Shield",
        7: "Fire Rod",
        8: "Ice Rod",
        9: "Magic Hammer",
        10: "Hookshot",
        11: "Bow",
        12: "Boomerang",
        18: "Lamp",
        21: "Cane of Somaria",
        22: "Magic Bottle",
        23: "Piece of Heart",
        24: "Cane of Byrna",
        25: "Magic Cape",
        27: "Power Glove",
        28: "Titan's Mitt",
        31: "Moon Pearl",
        34: "Blue Mail",
        35: "Red Mail",
        36: "Small Key",
        37: "Compass",
        40: "Bombs",
        42: "Magical Boomerang",
        50: "Big Key",
        51: "Dungeon Map",
        52: "Rupee",
        53: "Rupees (5)",
        54: "Rupees (20)",
        63: "Heart Container",
        64: "Rupees (100)",
        65: "Rupees (50)",
        67: "Arrow",
        68: "Arrows (10)",
        70: "Rupees (300)",
    }
    return labels.get(item_id, "Item")


def file_status(label: str, path: Path) -> dict[str, str]:
    return {"label": label, "state": "found" if path.is_file() else "missing", "detail": display_path(path)}


def folder_status(label: str, path: Path, missing_detail: str) -> dict[str, str]:
    return {"label": label, "state": "found" if path.is_dir() else "missing", "detail": display_path(path) if path.is_dir() else missing_detail}


def capability_status(label: str, path: Path, needle: str, missing_detail: str) -> dict[str, str]:
    found = file_contains(path, needle)
    return {"label": label, "state": "found" if found else "missing", "detail": f"{display_path(path)} supports {needle}." if found else missing_detail}


def file_contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except OSError:
        return False


def combine_results(message: str, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    stdout = "\n".join(text for text in (first["stdout"], second["stdout"]) if text)
    stderr = "\n".join(text for text in (first["stderr"], second["stderr"]) if text)
    return action_result(first["ok"] and second["ok"], message if second["ok"] else second["message"], stdout, stderr)


def push_option(args: list[str], flag: str, value: str | None) -> None:
    if value is not None:
        trimmed = str(value).strip()
        if trimmed:
            args.extend([flag, trimmed])


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
    return {"A": "Added", "C": "Copied", "D": "Deleted", "M": "Modified", "R": "Renamed", "T": "Type changed"}.get(status_value[:1], "Changed")


def dirty_files(project: Path) -> list[str]:
    output = git_output(project, ["status", "--porcelain"])
    files: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            old_path, new_path = path.split(" -> ", 1)
            files.extend([old_path, new_path])
        else:
            files.append(path.strip('"'))
    return sorted(set(files))


def update_warnings(changes: list[dict[str, Any]], dirty: list[str]) -> list[str]:
    warnings: list[str] = []
    paths: list[str] = []
    for change in changes:
        if change.get("old_path"):
            paths.append(change["old_path"])
        paths.append(change["path"])
    if any(is_zelda_ini_path(path) for path in paths):
        warnings.append("zelda3.ini changes are included. Back up your ini file before updating.")
    if any(repo_path_in_folder(path, "assets") for path in paths):
        warnings.append("Assets changed. Build a fresh zelda3_assets.dat after applying this update.")
    if any(repo_path_in_folder(path, "src") or repo_path_in_folder(path, "snes") for path in paths):
        warnings.append("Source changed. Rebuild the game after applying this update.")
    if dirty:
        warnings.append("Local repo edits exist. Files with local edits are blocked from update until backed up or unchecked.")
    return warnings


def apply_change(project: Path, upstream: str, change: dict[str, Any]) -> None:
    if change["status"].startswith("D"):
        git_output(project, ["rm", "--quiet", "--ignore-unmatch", "--", change["path"]])
        return
    if change["status"].startswith("R") and change.get("old_path") and change["old_path"] != change["path"]:
        git_output(project, ["rm", "--quiet", "--ignore-unmatch", "--", change["old_path"]])
    git_output(project, ["checkout", upstream, "--", change["path"]])


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


def macos_update_asset_name() -> str:
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "Z3R-Launcher-macos-apple-silicon.dmg"
    return "Z3R-Launcher-macos-intel.dmg"


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


def flatpak_install_scope_arg() -> str:
    try:
        flatpak_info = FLATPAK_INFO_PATH.read_text(encoding="utf-8")
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
    subprocess.Popen([
        "flatpak-spawn",
        "--host",
        "sh",
        "-c",
        'while kill -0 "$1" 2>/dev/null; do sleep 1; done; flatpak run "$2"',
        "z3r-launcher-flatpak-relaunch",
        str(os.getpid()),
        APP_ID,
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())


def current_appimage_path() -> Path:
    appimage = os.environ.get("APPIMAGE")
    if not appimage:
        raise LauncherError("Linux self-update requires running the AppImage or Flatpak package.")
    path = Path(appimage)
    if not path.is_file():
        raise LauncherError(f"The APPIMAGE path does not exist anymore: {display_path(path)}")
    return path


def current_macos_bundle_path() -> Path:
    executable = current_executable_path()
    app_bundle = executable.parent.parent.parent
    if app_bundle.suffix == ".app":
        return app_bundle
    raise LauncherError("macOS self-update requires running from the packaged .app bundle.")


def write_windows_update_script(path: Path) -> None:
    path.write_text(r'''
param(
  [Parameter(Mandatory = $true)][int]$LauncherPid,
  [Parameter(Mandatory = $true)][string]$Downloaded,
  [Parameter(Mandatory = $true)][string]$Target,
  [Parameter(Mandatory = $true)][string]$Relaunch,
  [Parameter(Mandatory = $true)][string]$Log
)
$ErrorActionPreference = "Stop"
function Write-UpdateLog([string]$Message) {
  $stamp = Get-Date -Format o
  Add-Content -LiteralPath $Log -Value "$stamp $Message"
}
function Move-WithRetry([string]$Source, [string]$Destination) {
  for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
      Move-Item -LiteralPath $Source -Destination $Destination -Force
      return
    } catch {
      if ($attempt -eq 20) {
        throw
      }
      Start-Sleep -Milliseconds 250
    }
  }
}
try {
  Write-UpdateLog "Waiting for launcher process $LauncherPid to close."
  Wait-Process -Id $LauncherPid -ErrorAction SilentlyContinue
  if (!(Test-Path -LiteralPath $Downloaded)) {
    throw "Downloaded launcher exe was not found: $Downloaded"
  }
  $targetDirectory = Split-Path -Parent $Target
  if ($targetDirectory -and !(Test-Path -LiteralPath $targetDirectory)) {
    New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null
  }
  $temporaryTarget = "$Target.new"
  Remove-Item -LiteralPath $temporaryTarget -Force -ErrorAction SilentlyContinue
  Write-UpdateLog "Moving downloaded launcher exe into place."
  Move-WithRetry -Source $Downloaded -Destination $temporaryTarget
  Move-WithRetry -Source $temporaryTarget -Destination $Target
  if (Test-Path -LiteralPath $Relaunch) {
    Write-UpdateLog "Relaunching updated launcher."
    Start-Process -FilePath $Relaunch
  }
} catch {
  Write-UpdateLog $_.Exception.Message
  exit 1
}
'''.lstrip(), encoding="utf-8")


def write_macos_update_script(path: Path) -> None:
    path.write_text(r'''#!/bin/sh
set -eu
pid="$1"
dmg="$2"
mount="$3"
target="$4"
app_name="$5"
log="$6"
exec > "$log" 2>&1
while kill -0 "$pid" 2>/dev/null; do
  sleep 1
done
rm -rf "$mount"
mkdir -p "$mount"
hdiutil attach -nobrowse -quiet -mountpoint "$mount" "$dmg"
trap 'hdiutil detach "$mount" -quiet >/dev/null 2>&1 || true; rm -rf "$mount"' EXIT
source_app="$mount/$app_name"
if [ ! -d "$source_app" ]; then
  source_app="$(find "$mount" -maxdepth 2 -name '*.app' -type d | head -n 1)"
fi
if [ -z "$source_app" ] || [ ! -d "$source_app" ]; then
  echo "No app bundle was found in the mounted DMG."
  exit 2
fi
rm -rf "$target"
ditto "$source_app" "$target"
xattr -dr com.apple.quarantine "$target" >/dev/null 2>&1 || true
open "$target"
''', encoding="utf-8")


def write_appimage_update_script(path: Path) -> None:
    path.write_text(r'''#!/bin/sh
set -eu
pid="$1"
downloaded="$2"
target="$3"
log="$4"
exec > "$log" 2>&1
while kill -0 "$pid" 2>/dev/null; do
  sleep 1
done
chmod +x "$downloaded"
tmp="${target}.updating"
mv "$downloaded" "$tmp"
mv "$tmp" "$target"
chmod +x "$target"
"$target" >/dev/null 2>&1 &
''', encoding="utf-8")


def make_executable(path: Path) -> None:
    if os.name == "posix":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def pick_folder(title: str) -> str | None:
    commands: list[list[str]] = []
    if is_windows():
        script = (
            "$shell = New-Object -ComObject Shell.Application; "
            f"$folder = $shell.BrowseForFolder(0, '{powershell_quote(title)}', 0); "
            "if ($folder -ne $null) { $folder.Self.Path }"
        )
        commands.append(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    elif is_macos():
        commands.append(["osascript", "-e", f'POSIX path of (choose folder with prompt "{applescript_quote(title)}")'])
    else:
        if is_flatpak_runtime():
            commands.extend([
                ["flatpak-spawn", "--host", "/usr/bin/zenity", "--file-selection", "--directory", f"--title={title}"],
                ["flatpak-spawn", "--host", "/usr/bin/kdialog", "--getexistingdirectory", str(Path.home()), "--title", title],
                ["flatpak-spawn", "--host", "/usr/bin/yad", "--file", "--directory", f"--title={title}"],
            ])
        commands.extend([
            ["zenity", "--file-selection", "--directory", f"--title={title}"],
            ["kdialog", "--getexistingdirectory", str(Path.home()), "--title", title],
            ["yad", "--file", "--directory", f"--title={title}"],
        ])
    picked = run_picker_commands(commands)
    if picked is not None:
        return picked
    return tkinter_pick_folder(title)


def pick_file(title: str, filters: list[tuple[str, str]]) -> str | None:
    commands: list[list[str]] = []
    if is_windows():
        filter_text = "SNES ROM (*.sfc)|*.sfc"
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
            f"$dialog.Title = '{powershell_quote(title)}'; "
            f"$dialog.Filter = '{powershell_quote(filter_text)}'; "
            "if ($dialog.ShowDialog() -eq 'OK') { $dialog.FileName }"
        )
        commands.append(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    elif is_macos():
        commands.append(["osascript", "-e", f'POSIX path of (choose file of type {{"sfc"}} with prompt "{applescript_quote(title)}")'])
    else:
        if is_flatpak_runtime():
            commands.extend([
                ["flatpak-spawn", "--host", "/usr/bin/zenity", "--file-selection", f"--title={title}", "--file-filter=SNES ROM | *.sfc"],
                ["flatpak-spawn", "--host", "/usr/bin/kdialog", "--getopenfilename", str(Path.home()), "*.sfc|SNES ROM"],
                ["flatpak-spawn", "--host", "/usr/bin/yad", "--file", f"--title={title}"],
            ])
        commands.extend([
            ["zenity", "--file-selection", f"--title={title}", "--file-filter=SNES ROM | *.sfc"],
            ["kdialog", "--getopenfilename", str(Path.home()), "*.sfc|SNES ROM"],
            ["yad", "--file", f"--title={title}"],
        ])
    picked = run_picker_commands(commands)
    if picked is not None:
        return picked
    return tkinter_pick_file(title, filters)


def run_picker_commands(commands: list[list[str]]) -> str | None:
    for command in commands:
        try:
            output = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=command_env(),
                check=False,
                **hidden_subprocess_kwargs(),
            )
        except OSError:
            continue
        if output.returncode == 0:
            value = decode_output(output.stdout).strip()
            return value or None
        stderr = decode_output(output.stderr).lower()
        if "cancel" in stderr or "canceled" in stderr:
            return None
    return None


def tkinter_pick_folder(title: str) -> str | None:
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        raise LauncherError("No folder picker is available. Paste the folder path into the field instead.")
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = filedialog.askdirectory(title=title)
        return value or None
    finally:
        root.destroy()


def tkinter_pick_file(title: str, filters: list[tuple[str, str]]) -> str | None:
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        raise LauncherError("No file picker is available.")
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = filedialog.askopenfilename(title=title, filetypes=filters)
        return value or None
    finally:
        root.destroy()


def powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def applescript_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
