from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .constants import DEV_TOOLS_DIR, DEV_TOOLS_SOURCE_URL, OVERWORLD_EDITOR_PORT, OVERWORLD_EDITOR_REPO
from .dev_tool_processes import (
    dev_tool_subprocess_kwargs,
    remove_pid_file,
    stop_process,
    write_pid_file,
)
from .dev_tool_ports import port_accepts_connections, port_is_bindable, require_port_bindable
from .dev_tool_shutdown import stop_fixed_port_server
from .errors import LauncherError
from .platform_paths import display_path
from .processes import (
    action_result,
    command_env,
    git_program,
    python_program,
    run_command,
)
from .project_files import folder_matches_all_files, rom_storage_dir, venv_python


DEFAULT_TOOL = {
    "id": "overworld_editor",
    "label": "Overworld Editor",
    "repo_name": OVERWORLD_EDITOR_REPO,
    "entry_file": "index.html",
    "server_file": "server.py",
    "manifest_file": "tool-manifest.json",
}
COPY_IGNORES = {".git", "__pycache__"}
STARTUP_TIMEOUT_SECONDS = 4.0
STOP_TIMEOUT_SECONDS = 1.0
RUNNING_TOOLS: dict[str, dict[str, Any]] = {}
DEV_TOOL_LOCK = threading.RLock()


def read_dev_tools(project_path: str | None = None) -> dict[str, Any]:
    with DEV_TOOL_LOCK:
        project = Path(project_path) if project_path else None
        shared = shared_dev_tool_repo()
        installed_dir = project_tool_dir(project, DEFAULT_TOOL) if project else Path()
        available = tool_files_available(shared, DEFAULT_TOOL)
        installed = tool_files_available(installed_dir, DEFAULT_TOOL) if project else False
        tool = tool_snapshot(DEFAULT_TOOL, available, installed, shared, installed_dir)
        return {
            "storage_dir": display_path(shared_dev_tools_root()),
            "source_url": DEV_TOOLS_SOURCE_URL,
            "shared_repo": display_path(shared),
            "shared_available": available,
            "tools": [tool],
        }


def clone_dev_tools() -> dict[str, Any]:
    with DEV_TOOL_LOCK:
        return clone_dev_tools_locked()


def clone_dev_tools_locked() -> dict[str, Any]:
    storage = shared_dev_tools_root()
    destination = shared_dev_tool_repo()
    storage.mkdir(parents=True, exist_ok=True)

    if destination.is_dir():
        if (destination / ".git").is_dir():
            result = run_command(git_program(), ["pull", "--ff-only"], destination, "Updated dev tools.")
            if result["ok"] and not tool_files_available(destination, DEFAULT_TOOL):
                raise LauncherError("Updated dev tools, but the Overworld Editor files are missing.")
            return verified_source_result(result, destination)
        if tool_files_available(destination, DEFAULT_TOOL):
            return verified_source_result(
                action_result(True, "Dev tools are already available.", display_path(destination)),
                destination,
            )

    if destination.exists():
        raise LauncherError(f"Dev tools folder exists but is incomplete: {display_path(destination)}")

    result = run_command(
        git_program(),
        ["clone", DEV_TOOLS_SOURCE_URL, OVERWORLD_EDITOR_REPO],
        storage,
        "Cloned dev tools.",
    )
    if result["ok"] and not tool_files_available(destination, DEFAULT_TOOL):
        raise LauncherError("Cloned dev tools, but the Overworld Editor files are missing.")
    return verified_source_result(result, destination)


def install_dev_tool(project_path: str, tool_id: str) -> dict[str, Any]:
    with DEV_TOOL_LOCK:
        return install_dev_tool_locked(project_path, tool_id)


def install_dev_tool_locked(project_path: str, tool_id: str) -> dict[str, Any]:
    tool = require_tool(tool_id)
    source = shared_dev_tool_repo()
    if not tool_files_available(source, tool):
        raise LauncherError("Download dev tools before installing the Overworld Editor.")

    project = require_project(project_path)
    destination = project_tool_dir(project, tool)
    ensure_not_same_folder(source, destination)
    ensure_install_destination(destination)

    session_id = tool_session_id(project, tool)
    restart_after_install = running_session(session_id) is not None
    if restart_after_install:
        stop_running_session(session_id)

    copied = overwrite_installed_tool(source, destination)

    restarted_url = None
    if restart_after_install:
        restarted_url = start_dev_tool_server(project, tool, destination, session_id)

    result = action_result(
        True,
        installed_tool_message(tool, destination, restart_after_install),
        install_detail(copied, restart_after_install),
    )
    result.update({
        "verified": True,
        "copied": copied,
        "restarted": restart_after_install,
        "session_id": session_id if restart_after_install else None,
        "url": restarted_url,
        "embed_url": "/dev-tool/" if restart_after_install else None,
        "source_version": tool_manifest_version(source, tool),
        "installed_version": tool_manifest_version(destination, tool),
    })
    return result


def installed_dev_tools(project_path: Path | str) -> list[dict[str, str]]:
    project = Path(project_path)
    return [
        {
            "id": DEFAULT_TOOL["id"],
            "label": DEFAULT_TOOL["label"],
            "repo_name": DEFAULT_TOOL["repo_name"],
        }
    ] if tool_files_available(project_tool_dir(project, DEFAULT_TOOL), DEFAULT_TOOL) else []


def launch_dev_tool(project_path: str, tool_id: str) -> dict[str, Any]:
    with DEV_TOOL_LOCK:
        return launch_dev_tool_locked(project_path, tool_id)


def launch_dev_tool_locked(project_path: str, tool_id: str) -> dict[str, Any]:
    tool = require_tool(tool_id)
    project = require_project(project_path)
    tool_dir = project_tool_dir(project, tool)
    if not tool_files_available(tool_dir, tool):
        raise LauncherError(f"{tool['label']} is not installed for this repo.")

    session_id = tool_session_id(project, tool)
    existing = running_session(session_id)
    url = existing["url"] if existing else start_dev_tool_server(project, tool, tool_dir, session_id)

    result = action_result(True, f"Launched {tool['label']}.", url)
    result.update({
        "tool_id": tool["id"],
        "label": tool["label"],
        "url": url,
        "embed_url": "/dev-tool/",
        "external": False,
        "session_id": session_id,
    })
    return result


def stop_dev_tool(session_id: str | None = None) -> dict[str, Any]:
    with DEV_TOOL_LOCK:
        if session_id:
            stop_running_session(session_id)
        else:
            stop_all_dev_tools()
        return action_result(True, "Dev tool stopped.")


def active_dev_tool_project() -> Path | None:
    for session in RUNNING_TOOLS.values():
        process = session.get("process")
        project = session.get("project")
        if process and process.poll() is None and isinstance(project, Path):
            return project
    return None


def shared_dev_tools_root() -> Path:
    return rom_storage_dir() / DEV_TOOLS_DIR


def shared_dev_tool_repo() -> Path:
    return shared_dev_tools_root() / OVERWORLD_EDITOR_REPO


def tool_snapshot(
    tool: dict[str, str],
    available: bool,
    installed: bool,
    shared_dir: Path,
    installed_dir: Path,
) -> dict[str, Any]:
    return {
        "id": tool["id"],
        "label": tool["label"],
        "repo_name": tool["repo_name"],
        "available": available,
        "installed": installed,
        "source_version": tool_manifest_version(shared_dir, tool) if available else None,
        "installed_version": tool_manifest_version(installed_dir, tool) if installed else None,
    }


def tool_manifest_version(folder: Path, tool: dict[str, str]) -> str | None:
    manifest_name = tool.get("manifest_file")
    if not manifest_name:
        return None
    try:
        data = json.loads((folder / manifest_name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = str(data.get("version") or "").strip()
    return f"v{version.removeprefix('v')}" if version else None


def verified_source_result(result: dict[str, Any], source: Path) -> dict[str, Any]:
    if result.get("ok"):
        result.update({
            "verified": tool_files_available(source, DEFAULT_TOOL),
            "source_version": tool_manifest_version(source, DEFAULT_TOOL),
        })
    return result


def ensure_install_destination(destination: Path) -> None:
    if destination.exists() and not destination.is_dir():
        raise LauncherError(f"Install path exists but is not a folder: {display_path(destination)}")


def overwrite_installed_tool(source: Path, destination: Path) -> int:
    try:
        destination.mkdir(parents=True, exist_ok=True)
        copied = overwrite_dir_contents(source, destination, COPY_IGNORES)
        remove_extra_installed_files(source, destination, COPY_IGNORES)
        verify_installed_tool(source, destination)
    except OSError as error:
        raise LauncherError(f"Could not overwrite installed Overworld Editor files: {error}") from error
    return copied


def overwrite_dir_contents(source: Path, destination: Path, ignored_names: set[str]) -> int:
    copied = 0
    for child in source.iterdir():
        if child.name in ignored_names:
            continue
        target = destination / child.name
        if child.is_dir():
            if target.exists() and (not target.is_dir() or target.is_symlink()):
                remove_installed_child(target)
            target.mkdir(parents=True, exist_ok=True)
            copied += overwrite_dir_contents(child, target, ignored_names)
        elif child.is_file():
            if target.exists() and target.is_dir():
                remove_installed_child(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
            copied += 1
    return copied


def remove_extra_installed_files(source: Path, destination: Path, ignored_names: set[str]) -> None:
    for child in list(destination.iterdir()):
        source_child = source / child.name
        if child.name in ignored_names or not source_child.exists():
            remove_installed_child(child)
        elif child.is_dir():
            if source_child.is_dir() and not child.is_symlink():
                remove_extra_installed_files(source_child, child, ignored_names)
            else:
                remove_installed_child(child)
        elif not source_child.is_file():
            remove_installed_child(child)


def remove_installed_child(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink()


def verify_installed_tool(source: Path, destination: Path) -> None:
    if not folder_matches_all_files(source, destination, COPY_IGNORES):
        raise LauncherError("Installed Overworld Editor files did not match the downloaded source.")
    if installed_folder_has_extra_files(source, destination, COPY_IGNORES):
        raise LauncherError("Installed Overworld Editor still contains stale files from an older source.")


def installed_folder_has_extra_files(source: Path, destination: Path, ignored_names: set[str]) -> bool:
    if not destination.is_dir():
        return True
    for child in destination.iterdir():
        if child.name in ignored_names:
            return True
        source_child = source / child.name
        if not source_child.exists():
            return True
        if child.is_dir():
            if not source_child.is_dir() or installed_folder_has_extra_files(source_child, child, ignored_names):
                return True
        elif child.is_file():
            if not source_child.is_file():
                return True
        else:
            return True
    return False


def installed_tool_message(tool: dict[str, str], destination: Path, restarted: bool) -> str:
    if restarted:
        return f"Installed and restarted {tool['label']} for {display_path(destination)}."
    return f"Installed {tool['label']} into {display_path(destination)}."


def install_detail(copied: int, restarted: bool) -> str:
    lines = [
        f"{copied} file(s) overwritten in the selected repo.",
        "Removed stale installed files that are not in the downloaded source.",
        "Verified installed files match the downloaded source.",
    ]
    if restarted:
        lines.append("Restarted the running Overworld Editor session.")
    return "\n".join(lines)


def require_tool(tool_id: str) -> dict[str, str]:
    if tool_id != DEFAULT_TOOL["id"]:
        raise LauncherError("Unknown dev tool.")
    return DEFAULT_TOOL


def require_project(project_path: str) -> Path:
    project = Path(project_path)
    if not project.is_dir():
        raise LauncherError(f"Project folder does not exist: {display_path(project)}")
    return project


def project_tool_dir(project: Path | None, tool: dict[str, str]) -> Path:
    if project is None:
        return Path()
    return project / DEV_TOOLS_DIR / tool["repo_name"]


def tool_files_available(folder: Path, tool: dict[str, str]) -> bool:
    return (folder / tool["entry_file"]).is_file() and (folder / tool["server_file"]).is_file()


def ensure_not_same_folder(source: Path, destination: Path) -> None:
    try:
        same_folder = source.resolve() == destination.resolve()
    except OSError:
        same_folder = False
    if same_folder:
        raise LauncherError("The shared dev tool source and selected repo install path are the same folder.")


def tool_session_id(project: Path, tool: dict[str, str]) -> str:
    return f"{display_path(project.resolve())}:{tool['id']}"


def running_session(session_id: str) -> dict[str, Any] | None:
    session = RUNNING_TOOLS.get(session_id)
    process = session.get("process") if session else None
    if process and process.poll() is None and port_accepts_connections(OVERWORLD_EDITOR_PORT):
        return session
    if process and process.poll() is None:
        stop_running_session(session_id)
        return None
    if not port_is_bindable(OVERWORLD_EDITOR_PORT):
        stop_running_session(session_id)
        return None
    remove_pid_file(session.get("pid_path") if session else None)
    RUNNING_TOOLS.pop(session_id, None)
    return None


def start_dev_tool_server(project: Path, tool: dict[str, str], tool_dir: Path, session_id: str) -> str:
    stop_other_sessions(session_id)
    stop_stale_session(session_id)
    require_port_bindable(OVERWORLD_EDITOR_PORT)
    url = f"http://127.0.0.1:{OVERWORLD_EDITOR_PORT}/"
    log_path = dev_tool_log_path(project, tool)
    pid_path = dev_tool_pid_path(project, tool)
    log_file = log_path.open("ab")
    try:
        process = subprocess.Popen(
            [
                python_executable(project),
                str(tool_dir / tool["server_file"]),
                "--host",
                "127.0.0.1",
                "--port",
                str(OVERWORLD_EDITOR_PORT),
            ],
            cwd=str(tool_dir),
            env=dev_tool_env(project),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **dev_tool_subprocess_kwargs(),
        )
    except OSError as error:
        raise LauncherError(f"Could not start {tool['label']}: {error}") from error
    finally:
        log_file.close()
    try:
        write_pid_file(pid_path, process.pid)
        wait_for_server(process, tool, log_path)
    except OSError as error:
        stop_process(process, STOP_TIMEOUT_SECONDS)
        remove_pid_file(pid_path)
        raise LauncherError(f"Could not track {tool['label']} process: {error}") from error
    except LauncherError:
        stop_process(process, STOP_TIMEOUT_SECONDS)
        remove_pid_file(pid_path)
        raise
    RUNNING_TOOLS[session_id] = {
        "process": process,
        "url": url,
        "label": tool["label"],
        "pid_path": pid_path,
        "project": project,
    }
    return url


def python_executable(project: Path) -> str:
    python = project_venv_python(project)
    if python:
        return display_path(python)
    return python_program()


def dev_tool_env(project: Path) -> dict[str, str]:
    env = command_env(remove_appimage=True)
    python = project_venv_python(project)
    if python:
        env["PATH"] = os.pathsep.join([str(python.parent), env.get("PATH", "")])
        env["VIRTUAL_ENV"] = str(python.parent.parent)
    return env


def project_venv_python(project: Path) -> Path | None:
    for folder in (project / ".venv", project / "venv"):
        python = venv_python(folder)
        if python:
            return python
    return None


def dev_tool_log_path(project: Path, tool: dict[str, str]) -> Path:
    log_dir = project / DEV_TOOLS_DIR / ".launcher-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{tool['id']}.log"
    path.write_text("", encoding="utf-8")
    return path


def dev_tool_pid_path(project: Path, tool: dict[str, str]) -> Path:
    return project / DEV_TOOLS_DIR / ".launcher-logs" / f"{tool['id']}.pid"


def wait_for_server(process: subprocess.Popen, tool: dict[str, str], log_path: Path) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError(startup_error_message(tool, "server exited before it could open", log_path))
        if port_accepts_connections(OVERWORLD_EDITOR_PORT):
            return
        time.sleep(0.1)
    stop_process(process, STOP_TIMEOUT_SECONDS)
    raise LauncherError(startup_error_message(tool, "did not start on", log_path))


def startup_error_message(tool: dict[str, str], reason: str, log_path: Path) -> str:
    message = f"{tool['label']} {reason} http://127.0.0.1:{OVERWORLD_EDITOR_PORT}/."
    detail = read_log_tail(log_path).strip()
    return f"{message}\n{detail}" if detail else message


def read_log_tail(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-4000:].decode("utf-8", errors="replace")


def stop_running_session(session_id: str) -> None:
    session = RUNNING_TOOLS.get(session_id)
    process = session.get("process") if session else None
    pid_path = session.get("pid_path") if session else pid_path_from_session_id(session_id)
    stop_fixed_port_server(process, pid_path, OVERWORLD_EDITOR_PORT, STOP_TIMEOUT_SECONDS)
    RUNNING_TOOLS.pop(session_id, None)


def stop_stale_session(session_id: str) -> None:
    pid_path = pid_path_from_session_id(session_id)
    stop_fixed_port_server(None, pid_path, OVERWORLD_EDITOR_PORT, STOP_TIMEOUT_SECONDS)


def stop_other_sessions(session_id: str) -> None:
    for running_session_id in list(RUNNING_TOOLS):
        if running_session_id != session_id:
            stop_running_session(running_session_id)


def stop_all_dev_tools() -> None:
    for session_id in list(RUNNING_TOOLS):
        stop_running_session(session_id)
    stop_fixed_port_server(None, None, OVERWORLD_EDITOR_PORT, STOP_TIMEOUT_SECONDS)


def pid_path_from_session_id(session_id: str) -> Path | None:
    try:
        project_text, tool_id = session_id.rsplit(":", 1)
        tool = require_tool(tool_id)
    except (ValueError, LauncherError):
        return None
    return dev_tool_pid_path(Path(project_text), tool)


atexit.register(stop_all_dev_tools)
