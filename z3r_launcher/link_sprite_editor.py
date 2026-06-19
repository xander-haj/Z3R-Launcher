from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PALETTE_ASSIGNMENT = "override_armor_palette"
PALETTE_WORD_COUNT = 75
PALETTE_ROW_LENGTH = 15
PALETTE_ROW_LABELS = ("Green mail", "Blue mail", "Red mail", "Bunny", "Zap")
# The asset compiler writes armor palette entries as uint16 values, with SNES color data in the low 15 bits.
MAX_SNES_PALETTE_WORD = 0xFFFF
ASSIGNMENT_RE = re.compile(rf"^\s*{PALETTE_ASSIGNMENT}\s*=\s*(.*)$")
COMMENT_ASSIGNMENT_RE = re.compile(rf"^\s*#\s*{PALETTE_ASSIGNMENT}\s*=\s*(.*)$")


@dataclass(frozen=True)
class PaletteRegion:
    """Records where the active assignment and optional commented example live in sprite_sheets.py."""

    start: int
    end: int
    active_source: str
    commented_source: str | None


class LinkSpritePaletteError(ValueError):
    """User-facing validation error raised when the Link palette block cannot be handled safely."""


def read_link_sprite_palette(project: Path) -> dict[str, Any]:
    """Read the selected project's Link armor palette override.

    Args:
        project: Root folder of a detected Z3R checkout.

    Returns:
        A serializable snapshot containing the palette file path, active state, row labels,
        and the 75 SNES palette words used by compile_resources.py.

    Raises:
        LinkSpritePaletteError: If the sprite sheet file or override block is missing or malformed.
        OSError: If the file cannot be read.
    """

    path = sprite_sheet_path(project)
    contents = path.read_text(encoding="utf-8")
    region = find_palette_region(contents.splitlines())
    active_values = parse_palette_assignment(region.active_source)
    commented_values = parse_palette_assignment(region.commented_source) if region.commented_source else None
    values = active_values if active_values is not None else commented_values

    if values is None:
        raise LinkSpritePaletteError("No editable Link armor palette list was found in assets/sprite_sheets.py.")

    normalized = normalize_palette_values(values)
    return {
        "path": str(path),
        "active": active_values is not None,
        "values": normalized,
        "rows": [
            {"label": label, "start": index * PALETTE_ROW_LENGTH}
            for index, label in enumerate(PALETTE_ROW_LABELS)
        ],
        "word_count": PALETTE_WORD_COUNT,
        "row_length": PALETTE_ROW_LENGTH,
    }


def write_link_sprite_palette(project: Path, values: list[Any], active: bool) -> dict[str, Any]:
    """Replace only the Link palette override block in assets/sprite_sheets.py.

    Args:
        project: Root folder of a detected Z3R checkout.
        values: Flat list of 75 SNES palette words, as integers or hex strings.
        active: True writes an active override list; False writes None plus a commented list.

    Returns:
        A refreshed palette snapshot after the file has been written.

    Raises:
        LinkSpritePaletteError: If the palette cannot be validated or the block cannot be found.
        OSError: If the file cannot be read or written.
    """

    path = sprite_sheet_path(project)
    contents = path.read_text(encoding="utf-8")
    lines, newline, had_trailing_newline = split_source_lines(contents)
    region = find_palette_region(lines)
    normalized = normalize_palette_values(values)
    lines[region.start:region.end] = format_palette_block(normalized, active)
    new_contents = newline.join(lines)

    if had_trailing_newline:
        new_contents += newline

    path.write_text(new_contents, encoding="utf-8")
    return read_link_sprite_palette(project)


def sprite_sheet_path(project: Path) -> Path:
    """Resolve the sprite_sheets.py path for a project and ensure it exists."""

    path = project / "assets" / "sprite_sheets.py"

    if not path.is_file():
        raise LinkSpritePaletteError(f"assets/sprite_sheets.py was not found in {project}.")

    return path


def split_source_lines(contents: str) -> tuple[list[str], str, bool]:
    """Split source text while preserving the dominant newline style and final newline state."""

    newline = "\r\n" if "\r\n" in contents else "\n"
    return contents.splitlines(), newline, contents.endswith(("\n", "\r"))


def find_palette_region(lines: list[str]) -> PaletteRegion:
    """Find the active assignment and any immediately-following commented override example."""

    for index, line in enumerate(lines):
        if not ASSIGNMENT_RE.match(line):
            continue

        active_end = find_assignment_end(lines, index, commented=False)
        commented_source = None
        region_end = active_end

        if active_end < len(lines) and COMMENT_ASSIGNMENT_RE.match(lines[active_end]):
            comment_end = find_assignment_end(lines, active_end, commented=True)
            commented_source = assignment_source(lines[active_end:comment_end], commented=True)
            region_end = comment_end

        return PaletteRegion(
            start=index,
            end=region_end,
            active_source=assignment_source(lines[index:active_end], commented=False),
            commented_source=commented_source,
        )

    raise LinkSpritePaletteError("assets/sprite_sheets.py does not define override_armor_palette.")


def find_assignment_end(lines: list[str], start: int, commented: bool) -> int:
    """Return the exclusive end line for a one-line assignment or bracketed list assignment."""

    first = clean_comment_line(lines[start]) if commented else lines[start]
    depth = first.count("[") - first.count("]")

    if depth <= 0:
        return start + 1

    for index in range(start + 1, len(lines)):
        line = clean_comment_line(lines[index]) if commented else lines[index]
        depth += line.count("[") - line.count("]")

        if depth <= 0:
            return index + 1

    raise LinkSpritePaletteError("override_armor_palette list is missing its closing bracket.")


def assignment_source(lines: list[str], commented: bool) -> str:
    """Build parseable Python source for an active or commented override assignment."""

    if commented:
        return "\n".join(clean_comment_line(line) for line in lines)

    return "\n".join(lines)


def clean_comment_line(line: str) -> str:
    """Remove the leading comment marker from one commented palette assignment line."""

    stripped = line.lstrip()

    if not stripped.startswith("#"):
        return stripped

    return stripped[1:].lstrip(" ")


def parse_palette_assignment(source: str | None) -> list[Any] | None:
    """Parse the right side of an override_armor_palette assignment."""

    if not source:
        return None

    source = remove_full_line_comments(source)
    match = re.search(rf"{PALETTE_ASSIGNMENT}\s*=\s*(.*)", source, re.DOTALL)

    if not match:
        return None

    raw_value = match.group(1).strip()

    if raw_value == "None":
        return None

    try:
        value = ast.literal_eval(raw_value)
    except (SyntaxError, ValueError) as error:
        raise LinkSpritePaletteError(f"override_armor_palette could not be parsed: {error}") from error

    if not isinstance(value, list):
        raise LinkSpritePaletteError("override_armor_palette must be a flat list of SNES color words.")

    return value


def remove_full_line_comments(source: str) -> str:
    """Remove row-label comment lines before literal evaluation of the palette list."""

    return "\n".join(
        line
        for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )


def normalize_palette_values(values: list[Any]) -> list[int]:
    """Validate and normalize a flat palette list into integer SNES palette words."""

    if not isinstance(values, list):
        raise LinkSpritePaletteError("Link armor palette must be submitted as a flat list.")

    if len(values) != PALETTE_WORD_COUNT:
        raise LinkSpritePaletteError(f"Link armor palette must contain exactly {PALETTE_WORD_COUNT} colors.")

    normalized: list[int] = []

    for index, value in enumerate(values, start=1):
        normalized.append(normalize_palette_word(value, index))

    return normalized


def normalize_palette_word(value: Any, index: int) -> int:
    """Normalize one 16-bit palette word from an integer or hexadecimal string."""

    if isinstance(value, bool):
        raise LinkSpritePaletteError(f"Palette color {index} must be an integer color word, not a boolean.")

    if isinstance(value, int):
        word = value
    elif isinstance(value, str):
        word = parse_palette_word_string(value, index)
    else:
        raise LinkSpritePaletteError(f"Palette color {index} must be an integer or hexadecimal string.")

    if word < 0 or word > MAX_SNES_PALETTE_WORD:
        raise LinkSpritePaletteError(f"Palette color {index} must be between 0x0000 and 0xFFFF.")

    return word


def parse_palette_word_string(value: str, index: int) -> int:
    """Parse a user-provided hexadecimal SNES palette word string."""

    cleaned = value.strip().lower()

    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]

    if not cleaned or len(cleaned) > 4 or not re.fullmatch(r"[0-9a-f]+", cleaned):
        raise LinkSpritePaletteError(f"Palette color {index} must be a 1-4 digit hexadecimal value.")

    return int(cleaned, 16)


def format_palette_block(values: list[int], active: bool) -> list[str]:
    """Format the override block as source lines, preserving a commented palette when disabled."""

    if active:
        return [f"{PALETTE_ASSIGNMENT} = [", *format_palette_rows(values, ""), "]"]

    return [
        f"{PALETTE_ASSIGNMENT} = None",
        f"#{PALETTE_ASSIGNMENT} = [",
        *format_palette_rows(values, "#"),
        "#]",
    ]


def format_palette_rows(values: list[int], prefix: str) -> list[str]:
    """Format five 15-color palette rows without exceeding the project's line-length limit."""

    lines: list[str] = []

    for index, label in enumerate(PALETTE_ROW_LABELS):
        row = values[index * PALETTE_ROW_LENGTH:(index + 1) * PALETTE_ROW_LENGTH]
        lines.append(f"{prefix}  # {label}")
        lines.extend(format_palette_value_lines(row, prefix))

    return lines


def format_palette_value_lines(row: list[int], prefix: str) -> list[str]:
    """Split one 15-color row into two source lines for readability and line-length safety."""

    first = row[:8]
    second = row[8:]
    return [
        f"{prefix}  {format_palette_values(first)},",
        f"{prefix}  {format_palette_values(second)},",
    ]


def format_palette_values(values: list[int]) -> str:
    """Render color words as lowercase four-digit hexadecimal literals."""

    return ", ".join(f"0x{value:04x}" for value in values)
