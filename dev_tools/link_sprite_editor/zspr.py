from __future__ import annotations

from z3r_launcher.errors import LauncherError


ZSPR_PALETTE_WORD_COUNT = 60
ZSPR_PALETTE_BYTE_COUNT = ZSPR_PALETTE_WORD_COUNT * 2
ZSPR_TEXT_OFFSET = 29


def parse_zspr_preview(data: bytes) -> tuple[bytes, bytes]:
    pixel_offset, pixel_length, palette_offset, palette_length = read_zspr_header(data)
    if pixel_length == 0:
        raise LauncherError("Selected ZSPR file does not include pixel data.")
    return (
        read_bounded_slice(data, pixel_offset, min(pixel_length, 0x7000)),
        read_bounded_slice(data, palette_offset, min(palette_length, 256)),
    )


def parse_zspr_palette_words(data: bytes) -> list[int]:
    _pixel_offset, _pixel_length, palette_offset, palette_length = read_zspr_header(data)
    if palette_length < ZSPR_PALETTE_BYTE_COUNT:
        raise LauncherError("Selected ZSPR file does not include a complete player palette.")
    palette = read_bounded_slice(data, palette_offset, ZSPR_PALETTE_BYTE_COUNT)
    return [
        int.from_bytes(palette[index:index + 2], "little")
        for index in range(0, ZSPR_PALETTE_BYTE_COUNT, 2)
    ]


def parse_zspr_metadata(data: bytes) -> dict[str, str]:
    pixel_offset, _pixel_length, _palette_offset, _palette_length = read_zspr_header(data)
    limit = min(pixel_offset, len(data)) if pixel_offset > ZSPR_TEXT_OFFSET else len(data)
    display_text, offset = read_utf16z(data, ZSPR_TEXT_OFFSET, limit)
    author, offset = read_utf16z(data, offset, limit)
    author_rom_display, _offset = read_asciiz(data, offset, limit)
    return {
        "display_text": clean_metadata_text(display_text),
        "author": clean_metadata_text(author),
        "author_rom_display": clean_metadata_text(author_rom_display),
    }


def write_zspr_palette_words(data: bytes, palette_words: list[int]) -> bytes:
    _pixel_offset, _pixel_length, palette_offset, palette_length = read_zspr_header(data)
    if palette_length < ZSPR_PALETTE_BYTE_COUNT:
        raise LauncherError("Selected ZSPR file does not include a writable player palette.")
    if len(palette_words) < ZSPR_PALETTE_WORD_COUNT:
        raise LauncherError("A ZSPR player palette must include at least 60 colors.")

    mutable = bytearray(data)
    read_bounded_slice(data, palette_offset, ZSPR_PALETTE_BYTE_COUNT)
    for index, word in enumerate(palette_words[:ZSPR_PALETTE_WORD_COUNT]):
        mutable[palette_offset + index * 2:palette_offset + index * 2 + 2] = int(word).to_bytes(2, "little")
    return bytes(mutable)


def read_zspr_header(data: bytes) -> tuple[int, int, int, int]:
    if len(data) < 21 or data[0:4] != b"ZSPR":
        raise LauncherError("Selected file is not a valid ZSPR sprite.")
    return (
        read_u32_le(data, 9),
        read_u16_le(data, 13),
        read_u32_le(data, 15),
        read_u16_le(data, 19),
    )


def read_u16_le(data: bytes, offset: int) -> int:
    if offset + 2 > len(data):
        raise LauncherError("Selected ZSPR file has a truncated header.")
    return int.from_bytes(data[offset:offset + 2], "little")


def read_u32_le(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise LauncherError("Selected ZSPR file has a truncated header.")
    return int.from_bytes(data[offset:offset + 4], "little")


def read_bounded_slice(data: bytes, offset: int, length: int) -> bytes:
    end = offset + length
    if end > len(data):
        raise LauncherError("Selected ZSPR file points outside its data.")
    return data[offset:end]


def read_utf16z(data: bytes, offset: int, limit: int) -> tuple[str, int]:
    end = offset
    while end + 1 < limit:
        if data[end] == 0 and data[end + 1] == 0:
            return data[offset:end].decode("utf-16-le", errors="replace"), end + 2
        end += 2
    raise LauncherError("Selected ZSPR file has truncated metadata text.")


def read_asciiz(data: bytes, offset: int, limit: int) -> tuple[str, int]:
    end = offset
    while end < limit:
        if data[end] == 0:
            return data[offset:end].decode("ascii", errors="replace"), end + 1
        end += 1
    raise LauncherError("Selected ZSPR file has truncated ROM author text.")


def clean_metadata_text(value: str) -> str:
    return "".join(character for character in value if character.isprintable()).strip()
