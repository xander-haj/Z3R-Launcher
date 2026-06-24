from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .errors import LauncherError
from .platform_paths import display_path, hidden_subprocess_kwargs, is_macos, is_windows
from .processes import action_result, command_env, decode_output, macos_search_paths
from .project_files import venv_python


def run_project_shell_command(command: str, cwd: Path, success_message: str) -> dict[str, Any]:
    actual_command = project_shell_command(command, cwd)
    program, args = shell_command_parts(actual_command)
    try:
        output = subprocess.run(
            [program, *args],
            cwd=str(cwd),
            env=project_shell_env(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except OSError as error:
        raise LauncherError(f"Could not run {command}: {error}") from error

    stdout = decode_output(output.stdout)
    stderr = decode_output(output.stderr)
    ok = output.returncode == 0
    message = success_message if ok else f"{command} exited with status {output.returncode}"
    return action_result(ok, message, stdout, stderr)


def shell_command_parts(command: str) -> tuple[str, list[str]]:
    if not is_macos():
        return "/bin/sh", ["-lc", command]
    shell = os.environ.get("SHELL") or "/bin/zsh"
    return shell, ["-lic", command]


def project_shell_env(project: Path) -> dict[str, str]:
    env = command_env(isolate_python=True)
    venv = project_venv_path(project)
    if not venv:
        return env
    env["VIRTUAL_ENV"] = display_path(venv)
    env["PATH"] = os.pathsep.join([display_path(venv_bin_path(venv)), env.get("PATH", "")])
    return env


def project_shell_command(command: str, project: Path) -> str:
    prefixes = project_path_prefixes(project)
    exports: list[str] = []
    venv = project_venv_path(project)
    if venv:
        exports.append(f"export VIRTUAL_ENV={shlex.quote(display_path(venv))}")
    if prefixes:
        path_prefix = os.pathsep.join(display_path(path) for path in prefixes)
        exports.append(f"export PATH={double_quote_shell(f'{path_prefix}{os.pathsep}$PATH')}")
    if not exports:
        return command
    return f"{'; '.join(exports)}; {command}"


def project_path_prefixes(project: Path) -> list[Path]:
    prefixes: list[Path] = []
    venv = project_venv_path(project)
    if venv:
        prefixes.append(venv_bin_path(venv))
    if is_macos():
        prefixes.extend(macos_search_paths())
    return unique_paths(prefixes)


def unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def double_quote_shell(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
    return f'"{escaped}"'


def project_venv_path(project: Path) -> Path | None:
    for folder in (project / ".venv", project / "venv"):
        if venv_python(folder):
            return folder
    return None


def venv_bin_path(venv: Path) -> Path:
    return venv / ("Scripts" if is_windows() else "bin")
