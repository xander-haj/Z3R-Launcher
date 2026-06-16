from __future__ import annotations

import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .backend import LauncherBackend, LauncherError, open_external_url, static_dir


HEARTBEAT_TIMEOUT_SECONDS = 45
MAX_REQUEST_BYTES = 16 * 1024 * 1024


class ServerState:
    def __init__(self, token: str) -> None:
        self.token = token
        self.server: ThreadingHTTPServer | None = None
        self.last_seen = time.monotonic()
        self.active_commands = 0
        self.lock = threading.Lock()
        self.exiting = False

    def touch(self) -> None:
        with self.lock:
            self.last_seen = time.monotonic()

    def begin_command(self) -> None:
        with self.lock:
            self.last_seen = time.monotonic()
            self.active_commands += 1

    def end_command(self) -> None:
        with self.lock:
            self.last_seen = time.monotonic()
            self.active_commands = max(0, self.active_commands - 1)

    def should_timeout(self) -> bool:
        with self.lock:
            return (
                not self.exiting
                and self.active_commands == 0
                and time.monotonic() - self.last_seen > HEARTBEAT_TIMEOUT_SECONDS
            )

    def schedule_exit(self, delay: float = 1.2) -> None:
        with self.lock:
            if self.exiting:
                return
            self.exiting = True

        def close_server() -> None:
            time.sleep(delay)
            if self.server:
                self.server.shutdown()

        threading.Thread(target=close_server, daemon=True).start()


def make_handler(state: ServerState, backend: LauncherBackend) -> type[BaseHTTPRequestHandler]:
    class LauncherRequestHandler(BaseHTTPRequestHandler):
        server_version = "Z3RLauncherPython/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/ping":
                self.handle_ping()
                return
            self.serve_static(parsed)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/invoke":
                self.handle_invoke()
                return
            if parsed.path == "/api/ping":
                self.handle_ping()
                return
            if parsed.path == "/api/shutdown":
                self.handle_shutdown()
                return
            self.write_json({"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

        def handle_ping(self) -> None:
            if not self.authorized():
                self.write_json({"error": "Unauthorized."}, status=HTTPStatus.FORBIDDEN)
                return
            state.touch()
            self.write_json({"ok": True})

        def handle_shutdown(self) -> None:
            if not self.authorized():
                self.write_json({"error": "Unauthorized."}, status=HTTPStatus.FORBIDDEN)
                return
            state.touch()
            state.schedule_exit(delay=0.2)
            self.write_json({"ok": True})

        def handle_invoke(self) -> None:
            if not self.authorized():
                self.write_json({"error": "Unauthorized."}, status=HTTPStatus.FORBIDDEN)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.write_json({"error": "Invalid request length."}, status=HTTPStatus.BAD_REQUEST)
                return

            if length < 0 or length > MAX_REQUEST_BYTES:
                self.write_json({"error": "Request body is too large."}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return

            try:
                body = self.rfile.read(length)
                request = json.loads(body.decode("utf-8"))
                command = request["command"]
                payload = request.get("payload") or {}
                if not isinstance(command, str) or not isinstance(payload, dict):
                    raise ValueError("Invalid command payload.")
            except (KeyError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
                self.write_json({"error": f"Invalid invoke request: {error}"}, status=HTTPStatus.BAD_REQUEST)
                return

            state.begin_command()
            try:
                result = backend.invoke(command, payload)
            except LauncherError as error:
                self.write_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            except Exception as error:
                self.write_json({"error": f"{type(error).__name__}: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            else:
                self.write_json({"result": result})
            finally:
                state.end_command()

        def serve_static(self, parsed: urllib.parse.ParseResult) -> None:
            if parsed.path in ("", "/"):
                path = static_dir() / "index.html"
            else:
                relative = urllib.parse.unquote(parsed.path).lstrip("/")
                path = static_dir() / relative

            try:
                root = static_dir().resolve()
                resolved = path.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            if not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            state.touch()
            content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            try:
                data = resolved.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self) -> bool:
            return self.headers.get("X-Z3R-Launcher-Token") == state.token

        def write_json(self, value: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return LauncherRequestHandler


def start_timeout_monitor(state: ServerState) -> None:
    def monitor() -> None:
        while True:
            time.sleep(5)
            if state.should_timeout():
                state.schedule_exit(delay=0)
                return

    threading.Thread(target=monitor, daemon=True).start()


def main() -> None:
    token = secrets.token_urlsafe(32)
    state = ServerState(token)
    backend = LauncherBackend(schedule_exit=state.schedule_exit)
    handler = make_handler(state, backend)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    state.server = server
    start_timeout_monitor(state)
    host, port = server.server_address
    url = f"http://{host}:{port}/?token={urllib.parse.quote(token)}"

    if os.environ.get("Z3R_LAUNCHER_NO_BROWSER") != "1":
        try:
            open_external_url(url)
        except LauncherError as error:
            print(f"Could not open browser automatically: {error}", file=sys.stderr)

    print(f"Z3R Launcher is running at {url}", file=sys.stderr)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
