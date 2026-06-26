from __future__ import annotations

import http.client
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from .constants import OVERWORLD_EDITOR_PORT
from .dev_tool_assets import active_dev_tool_project
from .dev_tool_mods import prepare_mod_command
from .errors import LauncherError


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "server",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "date",
}


def dev_tool_proxy_target(path: str) -> str | None:
    """Return the Overworld Editor route that the launcher may proxy."""
    if path == "/dev-tool":
        return "/"
    if path.startswith("/dev-tool/"):
        return path.removeprefix("/dev-tool")
    if path.startswith((
        "/api/mods",
        "/api/overworld-dump",
        "/api/editor-assets",
        "/api/generated-preview",
    )):
        return path
    if path == "/api/info":
        return path
    if path.startswith(("/assets/", "/src/")):
        return path
    return None


def proxy_dev_tool_request(
    handler: BaseHTTPRequestHandler,
    parsed: urllib.parse.ParseResult,
    max_request_bytes: int,
) -> None:
    target_path = dev_tool_proxy_target(parsed.path)
    if target_path is None:
        handler.send_error(HTTPStatus.NOT_FOUND)
        return

    body = read_request_body(handler, max_request_bytes)
    if body is None:
        return

    target = urllib.parse.urlunparse(("", "", target_path, "", parsed.query, ""))
    if not prepare_proxied_command(handler, target_path):
        return
    headers = proxied_request_headers(handler)
    connection: http.client.HTTPConnection | None = None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", OVERWORLD_EDITOR_PORT, timeout=20)
        connection.request(handler.command, target, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read()
    except (OSError, http.client.HTTPException) as error:
        write_text(handler, HTTPStatus.BAD_GATEWAY, f"Overworld Editor server is unavailable: {error}")
        return
    finally:
        if connection:
            connection.close()

    handler.send_response(response.status, response.reason)
    for key, value in response.getheaders():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(response_body)))
    handler.end_headers()
    handler.wfile.write(response_body)


def prepare_proxied_command(handler: BaseHTTPRequestHandler, target_path: str) -> bool:
    project = active_dev_tool_project()
    if project is None:
        return True
    try:
        prepare_mod_command(project, target_path)
    except LauncherError as error:
        write_text(handler, HTTPStatus.BAD_REQUEST, str(error))
        return False
    except ValueError as error:
        write_text(handler, HTTPStatus.BAD_REQUEST, f"Could not prepare mod command: {error}")
        return False
    except OSError as error:
        write_text(handler, HTTPStatus.BAD_REQUEST, f"Could not prepare mod command: {error}")
        return False
    return True


def read_request_body(handler: BaseHTTPRequestHandler, max_request_bytes: int) -> bytes | None:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        write_text(handler, HTTPStatus.BAD_REQUEST, "Invalid request length.")
        return None
    if length < 0 or length > max_request_bytes:
        write_text(handler, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
        return None
    return handler.rfile.read(length) if length else b""


def proxied_request_headers(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key in ("Content-Type", "Accept", "Cache-Control"):
        value = handler.headers.get(key)
        if value:
            headers[key] = value
    headers["Host"] = f"127.0.0.1:{OVERWORLD_EDITOR_PORT}"
    return headers


def write_text(handler: BaseHTTPRequestHandler, status: HTTPStatus, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
