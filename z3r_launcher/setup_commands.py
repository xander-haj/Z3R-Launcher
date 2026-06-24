from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .constants import Z3R_BETA_REPO_URL, Z3R_REPO_URL
from .environment_checks import missing_c_compiler_message, python_ssl_check
from .errors import LauncherError
from .github_urls import github_repo_owner_and_name, normalize_github_url
from .linux_game_downloads import install_prebuilt_linux_game_executable
from .platform_paths import display_path, hidden_subprocess_kwargs, is_linux, is_windows, uses_downloaded_linux_game_executable
from .processes import (
    action_result,
    bundled_sdl2_dll,
    bundled_sdl2_root,
    bundled_tcc,
    c_compiler_program,
    command_env,
    decode_output,
    find_msbuild,
    git_program,
    python_program,
    run_command,
    run_process,
)
from .project_shell import run_project_shell_command
from .project_files import (
    apply_windows_solution_patch_to_project,
    copy_dir_contents,
    copy_stored_rom_to_project,
    is_snesrev_zelda3_project,
    resource_text,
    venv_python,
)


def launch_game(executable_path: str) -> dict[str, Any]:
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


def clone_project(scan_root: str | None = None, beta: bool | None = None) -> dict[str, Any]:
    from .app_commands import ensure_clone_scan_root
    from .platform_paths import resolve_scan_root

    ensure_clone_scan_root(scan_root)
    parent = resolve_scan_root(scan_root)
    use_beta = bool(beta)
    repo_name = "Z3R-Beta" if use_beta else "Z3R"
    repo_url = Z3R_BETA_REPO_URL if use_beta else Z3R_REPO_URL
    target = parent / repo_name
    if target.exists():
        raise LauncherError(f"Target folder already exists: {display_path(target)}")

    result = run_command(git_program(), ["clone", "--recursive", repo_url, repo_name], parent, "Clone complete.")
    return attach_rom_copy_message(target, result)


def clone_custom_project(repo_url: str, scan_root: str | None = None) -> dict[str, Any]:
    from .app_commands import ensure_clone_scan_root
    from .platform_paths import resolve_scan_root

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
    return attach_rom_copy_message(target, result)


def open_project_folder(project_path: str) -> dict[str, Any]:
    from .processes import open_path

    project = Path(project_path)
    if not project.is_dir():
        raise LauncherError(f"Project folder does not exist: {display_path(project)}")
    open_path(project, "project folder")
    return action_result(True, f"Opened project folder: {display_path(project)}")


def create_venv(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    program = python_program()
    result = run_command(program, ["-m", "venv", ".venv"], project, "Virtual environment created.")
    return add_venv_creation_guidance(result, program, project) if not result["ok"] else result


def install_dependencies(project_path: str) -> dict[str, Any]:
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


def extract_assets(project_path: str) -> dict[str, Any]:
    return extract_assets_with_route(project_path, "automatic")


def extract_assets_visual_studio(project_path: str) -> dict[str, Any]:
    return extract_assets_with_route(project_path, "visual_studio")


def extract_assets_tcc(project_path: str) -> dict[str, Any]:
    return extract_assets_with_route(project_path, "tcc")


def extract_assets_with_route(project_path: str, route: str) -> dict[str, Any]:
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
    return extract


def build_project(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    if is_windows():
        return run_visual_studio_build(project)
    return run_project_shell_command("make -j$(nproc)", project, "Project build complete.")


def rebuild_project(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    if is_windows():
        return run_visual_studio_build(project, rebuild=True)
    return run_project_shell_command("make clean && make -j$(nproc)", project, "Project rebuild complete.")


def build_project_visual_studio(project_path: str) -> dict[str, Any]:
    return run_visual_studio_build(Path(project_path))


def rebuild_project_visual_studio(project_path: str) -> dict[str, Any]:
    return run_visual_studio_build(Path(project_path), rebuild=True)


def build_project_tcc(project_path: str) -> dict[str, Any]:
    return run_tcc_build(Path(project_path))


def build_executable(project: Path, route: str) -> dict[str, Any]:
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


def apply_snesrev_makefile_patch(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    if not project.is_dir():
        raise LauncherError(f"Project folder does not exist: {display_path(project)}")
    destination = project / "Makefile"
    destination.write_text(resource_text("patches/snesrev-zelda3/Makefile"), encoding="utf-8")
    return action_result(True, f"Patched Makefile installed at {display_path(destination)}.")


def apply_snesrev_solution_patch(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    apply_windows_solution_patch_to_project(project)
    return action_result(True, f"Patched solution installed in {display_path(project)}.")


def attach_rom_copy_message(project_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    if not result["ok"]:
        return result
    clone_message = result["message"]
    copied = copy_stored_rom_to_project(project_path)
    if copied:
        result["message"] = f"{clone_message} SFC copied to {display_path(copied)}."
    else:
        result["message"] = f"{clone_message} No uploaded SFC is available to copy yet."
    return result


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


def run_visual_studio_build(project: Path, rebuild: bool = False) -> dict[str, Any]:
    if is_snesrev_zelda3_project(project, None):
        apply_windows_solution_patch_to_project(project)
    msbuild = find_msbuild()
    if not msbuild:
        raise LauncherError("MSBuild was not found. Install Build Tools for Visual Studio or use the TCC route.")
    args = ["Zelda3.sln", "/restore", "/p:RestorePackagesConfig=true", "/p:Configuration=Release", "/p:Platform=x64"]
    if rebuild:
        args.insert(1, "/t:Rebuild")
    message = "Visual Studio rebuild complete." if rebuild else "Visual Studio build complete."
    return run_command(display_path(msbuild), args, project, message)


def run_tcc_build(project: Path) -> dict[str, Any]:
    prepared = prepare_tcc_project_tools(project)
    result = run_command("cmd", ["/C", "call", "run_with_tcc.bat"], project, "TCC build complete.")
    if result["ok"] and prepared:
        result["message"] = f"{' '.join(prepared)} {result['message']}"
    return result


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


def combine_results(message: str, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    stdout = "\n".join(text for text in (first["stdout"], second["stdout"]) if text)
    stderr = "\n".join(text for text in (first["stderr"], second["stderr"]) if text)
    return action_result(first["ok"] and second["ok"], message if second["ok"] else second["message"], stdout, stderr)
