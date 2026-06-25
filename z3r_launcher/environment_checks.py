from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import STORED_ROM_NAME
from .errors import LauncherError
from .linux_game_downloads import project_release_spec
from .platform_paths import display_path, is_linux, is_windows, os_name, resolve_scan_root, uses_downloaded_linux_game_executable
from .processes import (
    bundled_detail,
    bundled_git,
    bundled_python,
    bundled_sdl2_dll,
    bundled_tcc,
    c_compiler_program,
    decode_output,
    find_msbuild,
    run_process,
)
from .project_files import venv_python


def check_environment(project_path: str | None = None, scan_root: str | None = None) -> dict[str, Any]:
    parent = resolve_scan_root(scan_root)
    project = Path(project_path) if project_path else None
    checks = [check_git(), check_python(), check_venv(project), check_python_dependencies(project), check_rom(project)]
    if is_windows():
        checks.extend(check_windows_build_tools(project))
    elif uses_downloaded_linux_game_executable():
        checks.append(check_linux_game_executable_download(project))
    else:
        checks.extend(check_unix_build_tools())
    return {"os": os_name(), "parent_path": display_path(parent), "checks": checks, "next_steps": []}


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
        return {"ok": True, "message": message, "stdout": stdout, "stderr": stderr}
    return {
        "ok": False,
        "message": "The selected Python cannot import ssl, so pip cannot download HTTPS packages. Recreate the venv after installing a Python build with SSL support.",
        "stdout": stdout,
        "stderr": stderr,
    }


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
        return unknown_check("venv", "Python virtual environment", "Select or clone a repo before checking its venv.")
    for folder in (project_path / ".venv", project_path / "venv"):
        if venv_python(folder):
            return ok_check("venv", "Python virtual environment", f"Found {display_path(folder)}")
    return missing_check("venv", "Python virtual environment", missing_venv_detail())


def missing_venv_detail() -> str:
    if is_linux():
        return "Create one with the Create venv button. On Debian/Ubuntu, install `python3-venv` if Python reports ensurepip is missing."
    return "Create one with `python -m venv .venv` inside the selected repo."


def check_python_dependencies(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("python-dependencies", "Python dependencies", "Select or clone a repo before checking Pillow and PyYAML.")
    python = venv_python(project_path / ".venv") or venv_python(project_path / "venv")
    if not python:
        return missing_check("python-dependencies", "Python dependencies", "Create a venv before installing or checking Python requirements.")
    ssl_check = python_ssl_check(display_path(python), project_path)
    if not ssl_check["ok"]:
        return missing_check("python-dependencies", "Python dependencies", ssl_check["message"])
    return check_command("python-dependencies", display_path(python), "Python dependencies", ["-c", "import PIL, yaml"], "Install dependencies with the venv before extracting assets.")


def check_c_compiler() -> dict[str, str]:
    found = c_compiler_program()
    if found:
        check = check_command("c-compiler", found, "C compiler", ["--version"], missing_c_compiler_message())
        if check["state"] == "ok":
            check["detail"] = f"Found {found}: {check['detail']}"
            return check
    return missing_check("c-compiler", "C compiler", missing_c_compiler_message())


def missing_c_compiler_message() -> str:
    return "Required to compile Z3R. Install gcc or clang."


def check_rom(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("rom", "Game ROM (zelda3.sfc)", "Select or clone a repo before checking the ROM.")
    rom = project_path / STORED_ROM_NAME
    if rom.is_file():
        return ok_check("rom", "Game ROM (zelda3.sfc)", f"Found {display_path(rom)}")
    return missing_check("rom", "Game ROM (zelda3.sfc)", "Upload your SFC in the launcher, or place it as zelda3.sfc in the selected repo.")


def check_linux_game_executable_download(project_path: Path | None) -> dict[str, str]:
    if not project_path:
        return unknown_check("game-executable-download", "Linux executable download", "Select or clone a repo before checking executable downloads.")
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
