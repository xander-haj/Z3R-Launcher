from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .constants import APPIMAGE_ENV_KEYS, C_COMPILER_CANDIDATES, PYTHON_CHILD_ENV_KEYS
from .errors import LauncherError
from .platform_paths import (
    display_path,
    hidden_subprocess_kwargs,
    is_flatpak_runtime,
    is_linux,
    is_macos,
    is_windows,
    windows_tools_dir,
)


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
    return value if isinstance(value, str) else value.decode("utf-8", errors="replace")


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
    return path or find_msbuild_with_vswhere() or first_existing(common_msbuild_paths())


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


def c_compiler_program() -> str | None:
    path = command_env().get("PATH")
    for program in C_COMPILER_CANDIDATES:
        found = shutil.which(program, path=path)
        if found:
            return found
    return None


def linux_host_program_path(program: str) -> str | None:
    for directory in ("/usr/bin", "/bin", "/usr/local/bin"):
        candidate = Path(directory) / program
        if candidate.is_file():
            return str(candidate)
    return None


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


def open_external_url(url: str) -> None:
    if not (url.startswith("https://") or url.startswith("http://")):
        raise LauncherError("Only http and https documentation links can be opened.")

    if is_windows():
        subprocess.Popen(["rundll32", "url.dll,FileProtocolHandler", url], stdin=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())
        return
    if is_macos():
        subprocess.Popen(["open", url], stdin=subprocess.DEVNULL, env=command_env(), **hidden_subprocess_kwargs())
        return

    opener = linux_host_program_path("xdg-open") or "xdg-open"
    subprocess.Popen([opener, url], stdin=subprocess.DEVNULL, env=command_env(remove_appimage=True), **hidden_subprocess_kwargs())
