from __future__ import annotations

import struct
from pathlib import Path


ASSET_FILE_NAME = "zelda3_assets.dat"
LINK_GRAPHICS_ASSET = "kLinkGraphics"
LINK_GRAPHICS_SIZE = 0x7000


class LinkSpritePreviewError(ValueError):
    """User-facing validation error for compiled Link sprite preview data."""


def read_compiled_link_graphics(project: Path) -> bytes:
    asset_path = project / ASSET_FILE_NAME
    if not asset_path.is_file():
        raise LinkSpritePreviewError(f"{ASSET_FILE_NAME} was not found in the selected project.")

    try:
        data = asset_path.read_bytes()
    except OSError as error:
        raise LinkSpritePreviewError(f"Could not read {ASSET_FILE_NAME}: {error}") from error

    return normalize_link_graphics(find_asset_payload(data, LINK_GRAPHICS_ASSET, ASSET_FILE_NAME), ASSET_FILE_NAME)


def find_asset_payload(data: bytes, asset_name: str, label: str) -> bytes:
    if len(data) < 4:
        raise LinkSpritePreviewError(f"{label} is not a recognized Zelda3 asset file.")

    count = read_u32(data, 0)
    directory_end = 4 + count * 8
    if directory_end > len(data):
        raise LinkSpritePreviewError(f"{label} has a truncated asset directory.")

    entries: list[tuple[int, int]] = []
    for index in range(count):
        start = 4 + index * 8
        entries.append((read_u32(data, start), read_u32(data, start + 4)))

    names = read_asset_names(data, entries, label)
    for index, name in enumerate(names):
        if name != asset_name:
            continue
        offset, size = entries[index]
        end = offset + size
        if end > len(data):
            raise LinkSpritePreviewError(f"{label} has a truncated data block for {names[index]}.")
        return data[offset:end]

    raise LinkSpritePreviewError(f"{label} does not contain {asset_name}.")


def read_asset_names(data: bytes, entries: list[tuple[int, int]], label: str) -> list[str]:
    if not entries:
        raise LinkSpritePreviewError(f"{label} has an unexpected asset directory size.")

    first_offset = min(offset for offset, _size in entries)
    directory_end = 4 + len(entries) * 8
    names_blob = data[directory_end:first_offset]
    names = [name.decode("utf-8", errors="replace") for name in names_blob.split(b"\0") if name]
    return names[:len(entries)]


def normalize_link_graphics(payload: bytes, label: str) -> bytes:
    if len(payload) == LINK_GRAPHICS_SIZE:
        return payload
    if len(payload) > LINK_GRAPHICS_SIZE:
        return payload[:LINK_GRAPHICS_SIZE]
    raise LinkSpritePreviewError(
        f"{label} contains {LINK_GRAPHICS_ASSET}, but it is shorter than the expected 0x7000 bytes."
    )


def read_u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise LinkSpritePreviewError(f"{ASSET_FILE_NAME} has a truncated asset header.")
    return struct.unpack_from("<I", data, offset)[0]
