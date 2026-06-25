from __future__ import annotations

import os
import socket

from .errors import LauncherError


LOCALHOST = "127.0.0.1"
CONNECT_TIMEOUT_SECONDS = 0.2


def port_accepts_connections(port: int) -> bool:
    """Return whether a local TCP listener is accepting connections on the given port."""
    try:
        with socket.create_connection((LOCALHOST, port), timeout=CONNECT_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def port_is_bindable(port: int) -> bool:
    """Return whether the launcher can bind the editor port for a new server right now."""
    if port_accepts_connections(port):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        if os.name != "nt":
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((LOCALHOST, port))
        except OSError:
            return False
    return True


def require_port_bindable(port: int) -> None:
    """Raise a launcher-facing error unless the editor port is available for a new bind."""
    if port_is_bindable(port):
        return
    raise LauncherError(f"Port {port} is already in use. Close the existing editor server first.")
