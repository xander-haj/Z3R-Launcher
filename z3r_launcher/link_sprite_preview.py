from __future__ import annotations

from pathlib import Path


# The launcher reads the same compiled asset file the game loads at runtime.
ASSET_FILE_NAME = "zelda3_assets.dat"
# The first 16 bytes identify the asset bundle format written by compile_resources.py.
ASSET_MAGIC = b"Zelda3_v0     \n\0"
# Header = 16-byte magic, 32-byte key hash, 32 reserved bytes, asset count, and key-string length.
ASSET_HEADER_LENGTH = 88
# kLinkGraphics is the compiled 4bpp Link tile sheet used when no ZSPR override is active.
LINK_GRAPHICS_ASSET = "kLinkGraphics"
# Player sprites and ZSPR character sprites store 0x7000 bytes of 4bpp tile data.
LINK_GRAPHICS_LENGTH = 0x7000


class LinkSpritePreviewError(ValueError):
    """User-facing validation error raised when Link preview pixels cannot be read safely."""


def read_compiled_link_graphics(project: Path) -> bytes:
    """Read kLinkGraphics pixels from the selected project's compiled zelda3_assets.dat file."""

    path = project / ASSET_FILE_NAME

    if not path.is_file():
        raise LinkSpritePreviewError(f"{ASSET_FILE_NAME} was not found in the selected project.")

    try:
        data = path.read_bytes()
    except OSError as error:
        raise LinkSpritePreviewError(f"Could not read {ASSET_FILE_NAME}: {error}") from error

    return read_asset_blob(data, LINK_GRAPHICS_ASSET, ASSET_FILE_NAME)


def read_asset_blob(data: bytes, asset_name: str, label: str) -> bytes:
    """Extract one named asset blob from the zelda3_assets.dat binary container."""

    if len(data) < ASSET_HEADER_LENGTH or data[:len(ASSET_MAGIC)] != ASSET_MAGIC:
        raise LinkSpritePreviewError(f"{label} is not a recognized Zelda3 asset file.")

    asset_count = read_u32_le(data, 80, label)
    key_length = read_u32_le(data, 84, label)
    sizes_offset = ASSET_HEADER_LENGTH
    sizes_length = asset_count * 4
    keys_offset = sizes_offset + sizes_length
    data_offset = keys_offset + key_length

    if keys_offset > len(data) or data_offset > len(data):
        raise LinkSpritePreviewError(f"{label} has a truncated asset directory.")

    sizes = [
        read_u32_le(data, sizes_offset + index * 4, label)
        for index in range(asset_count)
    ]
    names = parse_asset_names(data[keys_offset:data_offset], asset_count, label)
    offset = data_offset

    for index, size in enumerate(sizes):
        offset = align_u32(offset)
        end = offset + size

        if end > len(data):
            raise LinkSpritePreviewError(f"{label} has a truncated data block for {names[index]}.")

        if names[index] == asset_name:
            blob = data[offset:end]
            validate_link_graphics_blob(blob, label)
            return blob

        offset = end

    raise LinkSpritePreviewError(f"{label} does not contain {asset_name}.")


def parse_asset_names(raw_keys: bytes, expected_count: int, label: str) -> list[str]:
    """Decode the null-terminated asset-name directory stored in zelda3_assets.dat."""

    names = [item.decode("utf-8") for item in raw_keys.rstrip(b"\0").split(b"\0") if item]

    if len(names) != expected_count:
        raise LinkSpritePreviewError(f"{label} has an unexpected asset directory size.")

    return names


def validate_link_graphics_blob(blob: bytes, label: str) -> None:
    """Ensure the extracted Link graphics blob has the 0x7000-byte ZSPR/player size."""

    if len(blob) != LINK_GRAPHICS_LENGTH:
        raise LinkSpritePreviewError(
            f"{label} has Link graphics size 0x{len(blob):x}, expected 0x{LINK_GRAPHICS_LENGTH:x}."
        )


def read_u32_le(data: bytes, offset: int, label: str) -> int:
    """Read a little-endian uint32 from a checked offset inside an asset file."""

    if offset + 4 > len(data):
        raise LinkSpritePreviewError(f"{label} has a truncated asset header.")

    return int.from_bytes(data[offset:offset + 4], "little")


def align_u32(offset: int) -> int:
    """Return the next 4-byte-aligned offset used by compiled asset blobs."""

    return (offset + 3) & ~3
