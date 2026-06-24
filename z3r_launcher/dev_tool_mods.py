from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import LauncherError


MOD_COMMAND_RE = re.compile(r"^/api/mods/([^/]+)/(build|apply-overworld|dump-overworld)$")
MOD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SPRITE_STAGE_PATHS = {"Sprites", "Sprites.Beginning", "Sprites.FirstPart", "Sprites.SecondPart"}


def prepare_mod_command(project: Path, target_path: str) -> None:
    """Repair launcher-owned mod metadata before commands that invoke the repo builder."""
    match = MOD_COMMAND_RE.fullmatch(target_path)
    if not match:
        return
    normalize_child_sprite_metadata(project, match.group(1))


def normalize_child_sprite_metadata(project: Path, mod_id: str) -> int:
    """Move child-screen sprite patches onto their parent YAML area with coordinate offsets."""
    if not MOD_ID_RE.fullmatch(mod_id):
        raise LauncherError("Invalid overworld mod id.")

    metadata_path = project / "mods" / "overworld" / mod_id / "patches" / "metadata.json"
    area_metadata_path = project / "assets" / "overworld_dump" / "tables" / "area_metadata.json"
    if not metadata_path.is_file() or not area_metadata_path.is_file():
        return 0

    document = read_json(metadata_path)
    area_metadata = read_json(area_metadata_path)
    parent_ids = area_metadata.get("area_parent_ids") or area_metadata.get("area_heads") or []
    patches = document.get("patches")
    if not isinstance(patches, list):
        return 0

    unchanged: list[dict[str, Any]] = []
    sprite_ops: dict[tuple[int, tuple[str, ...]], dict[str, Any]] = {}
    child_rows: dict[tuple[int, tuple[str, ...]], list[list[Any]]] = {}
    ordered_keys: list[tuple[int, tuple[str, ...]]] = []
    changed = 0

    for operation in patches:
        converted = child_sprite_rows(project, parent_ids, operation)
        if converted:
            key, rows = converted
            append_key(ordered_keys, key)
            child_rows.setdefault(key, []).extend(rows)
            changed += 1
        elif is_sprite_operation(operation):
            key = sprite_operation_key(operation)
            if key:
                append_key(ordered_keys, key)
                sprite_ops[key] = clone_json(operation)
            else:
                unchanged.append(operation)
        else:
            unchanged.append(operation)

    if not changed:
        return 0

    document["patches"] = [*unchanged, *merged_sprite_operations(project, sprite_ops, child_rows, ordered_keys)]
    metadata_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changed


def child_sprite_rows(
    project: Path,
    parent_ids: list[Any],
    operation: Any,
) -> tuple[tuple[int, tuple[str, ...]], list[list[Any]]] | None:
    """Return adjusted sprite rows when a metadata.sprite patch targets a child screen."""
    if not is_sprite_operation(operation):
        return None

    area = parse_int(operation.get("area", operation.get("screen")))
    if area is None or area < 0 or area >= len(parent_ids):
        return None

    parent = parse_int(parent_ids[area])
    path = normalized_sprite_path(operation, parent if parent is not None else area)
    if parent is None or parent == area or not path:
        return None

    if overworld_yaml(project, area).is_file() or not overworld_yaml(project, parent).is_file():
        return None

    rows = operation.get("value", {}).get("sprites", [])
    if not isinstance(rows, list):
        return None

    x_offset, y_offset = child_screen_offset(area, parent)
    adjusted = [offset_sprite_row(row, x_offset, y_offset) for row in rows if isinstance(row, list)]
    return ((parent, tuple(path)), adjusted) if adjusted else None


def merged_sprite_operations(
    project: Path,
    sprite_ops: dict[tuple[int, tuple[str, ...]], dict[str, Any]],
    child_rows: dict[tuple[int, tuple[str, ...]], list[list[Any]]],
    ordered_keys: list[tuple[int, tuple[str, ...]]],
) -> list[dict[str, Any]]:
    """Build final metadata.sprite operations with child rows merged into parent sets."""
    merged = []
    for key in ordered_keys:
        operation = clone_json(sprite_ops[key]) if key in sprite_ops else base_sprite_operation(project, key)
        rows = child_rows.get(key, [])
        if rows:
            value = operation.setdefault("value", {})
            value.setdefault("sprites", []).extend(rows)
        merged.append(operation)
    return merged


def base_sprite_operation(project: Path, key: tuple[int, tuple[str, ...]]) -> dict[str, Any]:
    """Create a full sprite-set operation from the parent YAML file."""
    area, path = key
    value = read_yaml_sprite_set(overworld_yaml(project, area), path[0])
    return {"kind": "metadata.sprite", "area": area, "path": list(path), "value": value}


def read_yaml_sprite_set(path: Path, stage_key: str) -> dict[str, Any]:
    """Read the generated YAML sprite block shape without requiring PyYAML in the launcher."""
    lines = path.read_text(encoding="utf-8").splitlines()
    block = top_level_block(lines, stage_key)
    info: dict[str, Any] = {}
    sprites: list[list[Any]] = []
    for line in block:
        stripped = line.strip()
        if stripped.startswith("info:"):
            info = parse_inline_mapping(stripped.removeprefix("info:").strip())
        elif stripped.startswith("- [") and stripped.endswith("]"):
            sprites.append(parse_inline_list(stripped[2:]))
    return {"info": info, "sprites": sprites}


def top_level_block(lines: list[str], key: str) -> list[str]:
    """Return indented lines under one top-level YAML key."""
    marker = f"{key}:"
    for index, line in enumerate(lines):
        if line == marker:
            block: list[str] = []
            for child in lines[index + 1:]:
                if child and not child.startswith((" ", "-")):
                    break
                block.append(child)
            return block
    return []


def parse_inline_list(value: str) -> list[Any]:
    """Parse a simple YAML inline list used by extracted sprite rows."""
    inner = value.strip()[1:-1]
    return [parse_scalar(item) for item in split_top_level(inner)]


def parse_inline_mapping(value: str) -> dict[str, Any]:
    """Parse a simple YAML inline mapping used by sprite info and custom visuals."""
    if not value.startswith("{") or not value.endswith("}"):
        return {}
    result: dict[str, Any] = {}
    for item in split_top_level(value[1:-1]):
        if ":" not in item:
            continue
        key, raw = item.split(":", 1)
        result[key.strip()] = parse_scalar(raw.strip())
    return result


def split_top_level(value: str) -> list[str]:
    """Split comma-separated YAML inline values without splitting nested mappings."""
    items: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    for index, char in enumerate(value):
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            items.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    return [*items, tail] if tail else items


def parse_scalar(value: str) -> Any:
    """Parse the scalar subset used in extracted sprite YAML."""
    if value.startswith("{") and value.endswith("}"):
        return parse_inline_mapping(value)
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    parsed = parse_int(value)
    return parsed if parsed is not None else value


def normalized_sprite_path(operation: dict[str, Any], area: int) -> list[str]:
    """Return the supported full sprite-set path for one operation."""
    raw_path = operation.get("path")
    path = raw_path if isinstance(raw_path, list) else ["Sprites" if area >= 64 else "Sprites.FirstPart"]
    if not path:
        return []
    key = str(path[0])
    return [key] if key in SPRITE_STAGE_PATHS else []


def child_screen_offset(area: int, parent: int) -> tuple[int, int]:
    """Return 16px-tile offsets from child screen coordinates to parent-area coordinates."""
    return ((area % 8) - (parent % 8)) * 32, ((area // 8) - (parent // 8)) * 32


def offset_sprite_row(row: list[Any], x_offset: int, y_offset: int) -> list[Any]:
    """Copy one sprite row while shifting its x/y coordinates into parent-area space."""
    shifted = clone_json(row)
    x = parse_int(shifted[0])
    y = parse_int(shifted[1])
    if x is None or y is None:
        raise LauncherError("Sprite metadata contains a row with invalid x/y coordinates.")
    shifted[0] = x + x_offset
    shifted[1] = y + y_offset
    return shifted


def sprite_operation_key(operation: dict[str, Any]) -> tuple[int, tuple[str, ...]] | None:
    """Return the merge key for a valid metadata.sprite operation."""
    area = parse_int(operation.get("area", operation.get("screen")))
    if area is None:
        return None
    path = normalized_sprite_path(operation, area)
    return (area, tuple(path)) if path else None


def is_sprite_operation(operation: Any) -> bool:
    """Return true for metadata.sprite operation dictionaries."""
    return isinstance(operation, dict) and operation.get("kind") == "metadata.sprite"


def append_key(keys: list[tuple[int, tuple[str, ...]]], key: tuple[int, tuple[str, ...]]) -> None:
    """Append a merge key once while preserving first-seen ordering."""
    if key not in keys:
        keys.append(key)


def overworld_yaml(project: Path, area: int) -> Path:
    """Return the extracted YAML path for one overworld area id."""
    return project / "assets" / "overworld" / f"overworld-{area}.yaml"


def read_json(path: Path) -> Any:
    """Read one UTF-8 JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def clone_json(value: Any) -> Any:
    """Deep-copy JSON-compatible values without importing copy for one small use."""
    return json.loads(json.dumps(value))


def parse_int(value: Any) -> int | None:
    """Parse decimal or 0x-prefixed integer values used by mod patch JSON."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16 if value.lower().startswith("0x") else 10)
        except ValueError:
            return None
    return None
