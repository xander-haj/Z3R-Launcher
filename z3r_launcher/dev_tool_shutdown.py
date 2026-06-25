"""Launcher-owned shutdown helpers for fixed-port dev tool servers."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

# Launcher port/process helpers.
from .dev_tool_ports import port_is_bindable
from .dev_tool_processes import (
    listening_pids,
    process_exists,
    read_pid_file,
    remove_pid_file,
    stop_pid,
    stop_port_listeners,
    stop_process,
)
from .errors import LauncherError


# Polling must be short because the Home overlay is a lifecycle control, not passive navigation.
POLL_INTERVAL_SECONDS = 0.05


# Stop one launcher-managed server and prove its fixed port can be reused.
# Parameters:
# - process: the active Popen object when the launcher still has it in memory.
# - pid_path: the pid-file path used to recover a process after frontend/backend state drift.
# - port: the fixed TCP port the dev tool must release before relaunch.
# - timeout: the per-stage grace period before escalating from interrupt to terminate to kill.
# Returns: None. Raises LauncherError if the port remains owned or unbindable after shutdown.
def stop_fixed_port_server(
    process: subprocess.Popen | None,
    pid_path: Path | None,
    port: int,
    timeout: float,
) -> None:
    tracked_pid = process.pid if process and process.poll() is None else None
    pid_file_pid = read_pid_file(pid_path)
    listener_pids = active_listener_pids(port)

    stop_process(process, timeout)
    if process and process.poll() is None:
        raise LauncherError("Overworld Editor process did not exit after shutdown.")

    if should_stop_pid(pid_file_pid, tracked_pid, listener_pids, port):
        stop_pid(pid_file_pid, timeout)

    stop_port_listeners(port, timeout)
    if not wait_for_port_release(port, timeout):
        stop_port_listeners(port, timeout)

    if not wait_for_port_release(port, timeout):
        raise LauncherError(f"Overworld Editor did not release port {port} after shutdown.")

    remove_pid_file(pid_path)


# Decide whether a pid-file value is safe and relevant enough to signal.
# Parameters:
# - pid: the pid read from disk, or None if no valid pid was stored.
# - tracked_pid: the pid already handled through the live Popen object.
# - listener_pids: the current processes known to own the fixed port.
# - port: the fixed TCP port that determines whether a stale pid still matters.
# Returns: True when the pid should receive the Ctrl+C-style shutdown sequence.
def should_stop_pid(pid: int | None, tracked_pid: int | None, listener_pids: set[int], port: int) -> bool:
    if not pid or pid == tracked_pid or pid == os.getpid() or not process_exists(pid):
        return False
    return pid in listener_pids or not port_released(port)


# Wait for the fixed port to have no listeners and accept a new bind.
# Parameters:
# - port: the TCP port reserved for the dev tool.
# - timeout: the maximum wait duration for this verification pass.
# Returns: True when no process owns the port and the launcher can bind it.
def wait_for_port_release(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_released(port):
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return port_released(port)


# Check the complete release contract used after shutdown.
# Parameters:
# - port: the fixed TCP port that must be reusable before relaunch.
# Returns: True only when no listener remains and the port is bindable.
def port_released(port: int) -> bool:
    return not active_listener_pids(port) and port_is_bindable(port)


# Return listener pids without ever treating the launcher process as a kill target.
# Parameters:
# - port: the TCP port whose owning processes should be inspected.
# Returns: a set of process ids currently listening on the port.
def active_listener_pids(port: int) -> set[int]:
    return {pid for pid in listening_pids(port) if pid != os.getpid()}
