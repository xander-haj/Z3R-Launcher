from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import LauncherError
from .platform_paths import display_path


def read_zelda_ini(project_path: str) -> dict[str, Any]:
    path = Path(project_path) / "zelda3.ini"
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise LauncherError(f"Could not read {display_path(path)}: {error}") from error
    return build_ini_snapshot(project_path, contents)


def update_zelda_ini_line(project_path: str, line_number: int, raw_line: str) -> dict[str, Any]:
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
    return {"ok": True, "message": f"zelda3.ini line {line_number} updated.", "stdout": raw_line, "stderr": ""}


def set_zelda_ini_value(project_path: str, section: str, key: str, value: str) -> dict[str, Any]:
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
    return {"ok": True, "message": f"zelda3.ini {section_name}.{key_name} updated.", "stdout": raw_line, "stderr": ""}


def build_ini_snapshot(project_path: str, contents: str) -> dict[str, Any]:
    current_section = ""
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in ("Graphics", "Sound", "Features", "KeyMap", "GamepadMap")}
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
        if current_section in buckets:
            buckets[current_section].append(line_snapshot(index, current_section, key, value, commented, raw_line))

    return {
        "project_path": project_path,
        "aspect_ratio": {
            "line_number": aspect_line or 0,
            "raw_value": aspect_value or "",
            "window_size_line": window_size_line or 0,
            "window_size_value": window_size_value or "Auto",
        },
        "graphics_lines": buckets["Graphics"],
        "sound_lines": buckets["Sound"],
        "feature_lines": buckets["Features"],
        "keymap_lines": buckets["KeyMap"],
        "gamepad_lines": buckets["GamepadMap"],
    }


def line_snapshot(index: int, section: str, key: str, value: str, commented: bool, raw: str) -> dict[str, Any]:
    return {"line_number": index, "section": section, "key": key, "value": value, "commented": commented, "raw": raw}


def active_ini_value(project: Path, section: str, key: str) -> str | None:
    path = project / "zelda3.ini"
    try:
        snapshot = build_ini_snapshot(str(project), path.read_text(encoding="utf-8"))
    except OSError:
        return None
    section_key = f"{section.lower()}_lines"
    for line in snapshot.get(section_key, []):
        if line["key"].lower() == key.lower() and not line["commented"] and line["value"].strip():
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
    else:
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
