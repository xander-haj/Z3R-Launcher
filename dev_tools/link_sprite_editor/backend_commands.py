from __future__ import annotations

from pathlib import Path
from typing import Any

from z3r_launcher.errors import LauncherError
from z3r_launcher.ini_tools import active_ini_value
from z3r_launcher.platform_paths import display_path, is_windows
from z3r_launcher.processes import run_command
from z3r_launcher.project_files import rom_storage_dir, venv_python

from .compiled_preview import LinkSpritePreviewError, read_compiled_link_graphics
from .palette import LinkSpritePaletteError, read_link_sprite_palette, write_link_sprite_palette
from .zspr import parse_zspr_palette_words, parse_zspr_preview, write_zspr_palette_words


def read_link_sprite_preview(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    link_graphics = active_ini_value(project, "Graphics", "LinkGraphics")
    if link_graphics:
        return read_link_sprite_zspr_preview(project, link_graphics)
    try:
        pixel_data = read_compiled_link_graphics(project)
    except LinkSpritePreviewError as error:
        raise LauncherError(str(error)) from error
    return {
        "label": "Compiled Link graphics",
        "source": "zelda3_assets.dat",
        "pixel_data": list(pixel_data),
    }


def read_link_sprite_zspr_preview(project: Path, sprite_path: str) -> dict[str, Any]:
    relative = safe_relative_path(sprite_path)
    storage = rom_storage_dir()
    sprite = next((path for path in (project / relative, storage / relative) if path.is_file()), None)
    if not sprite:
        raise LauncherError(f"Active LinkGraphics sprite was not found: {display_path(relative)}")
    try:
        bytes_data = sprite.read_bytes()
    except OSError as error:
        raise LauncherError(f"Could not read sprite {display_path(sprite)}: {error}") from error
    pixel_data, _palette_data = parse_zspr_preview(bytes_data)
    return {
        "label": sprite.stem or display_path(relative),
        "source": path_to_slash(relative),
        "pixel_data": list(pixel_data),
    }


def read_link_sprite_palette_command(project_path: str) -> dict[str, Any]:
    try:
        return read_palette_snapshot(Path(project_path))
    except LinkSpritePaletteError as error:
        raise LauncherError(str(error)) from error
    except OSError as error:
        raise LauncherError(f"Could not read Link sprite palette: {error}") from error


def save_link_sprite_palette(project_path: str, values: list[Any], active: bool = True) -> dict[str, Any]:
    project = Path(project_path)
    try:
        snapshot = write_link_sprite_palette(project, values, active)
        if active:
            write_active_zspr_palette(project, snapshot["values"])
        snapshot = read_palette_snapshot(project)
    except LinkSpritePaletteError as error:
        raise LauncherError(str(error)) from error
    except OSError as error:
        raise LauncherError(f"Could not write Link sprite palette: {error}") from error
    if active and snapshot.get("palette_source") == "zspr":
        snapshot["message"] = "Link sprite palette saved to the selected ZSPR and asset override."
    else:
        snapshot["message"] = (
            "Link sprite palette override saved."
            if active
            else "Link sprite palette override disabled."
        )
    return snapshot


def read_palette_snapshot(project: Path) -> dict[str, Any]:
    snapshot = read_link_sprite_palette(project)
    snapshot["palette_source"] = "asset_override" if snapshot["active"] else "asset_default"
    snapshot["palette_source_path"] = snapshot["path"]

    try:
        zspr_path = active_zspr_file(project, require_existing=True)
    except LauncherError as error:
        snapshot["palette_source_error"] = f"Could not read selected ZSPR palette: {error}"
        return snapshot

    if not zspr_path:
        return snapshot

    try:
        zspr_words = parse_zspr_palette_words(zspr_path.read_bytes())
    except (LauncherError, OSError) as error:
        snapshot["palette_source_error"] = f"Could not read selected ZSPR palette: {error}"
        return snapshot

    snapshot["values"] = zspr_words + snapshot["values"][len(zspr_words):]
    snapshot["palette_source"] = "zspr"
    snapshot["palette_source_path"] = display_path(zspr_path)
    return snapshot


def write_active_zspr_palette(project: Path, values: list[int]) -> None:
    zspr_path = active_zspr_file(project, require_existing=True)
    if not zspr_path:
        return

    try:
        data = zspr_path.read_bytes()
        zspr_path.write_bytes(write_zspr_palette_words(data, values))
    except OSError as error:
        raise LauncherError(f"Could not write selected ZSPR palette {display_path(zspr_path)}: {error}") from error


def active_zspr_file(project: Path, require_existing: bool = False) -> Path | None:
    link_graphics = active_ini_value(project, "Graphics", "LinkGraphics")
    if not link_graphics:
        return None

    relative = safe_relative_path(link_graphics)
    if relative.suffix.lower() != ".zspr":
        return None

    storage = rom_storage_dir()
    zspr_path = next((path for path in (project / relative, storage / relative) if path.is_file()), None)
    if zspr_path or not require_existing:
        return zspr_path
    raise LauncherError(f"Active LinkGraphics sprite was not found: {display_path(relative)}")


def build_link_sprite_assets(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    python = venv_python(project / ".venv") or venv_python(project / "venv")
    if not python:
        raise LauncherError("Create a venv before rebuilding Link sprite assets.")
    if not (project / "assets" / "restool.py").is_file():
        raise LauncherError(f"The selected project does not contain assets/restool.py: {display_path(project)}")
    return run_command(display_path(python), ["assets/restool.py"], project, "Link sprite asset file rebuilt.")


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or any(part in ("..", "") for part in path.parts):
        raise LauncherError("Selected asset path is not safe to copy.")
    if is_windows() and path.drive:
        raise LauncherError("Selected asset path is not safe to copy.")
    return path


def path_to_slash(path: Path) -> str:
    return "/".join(part for part in path.parts if part not in (path.anchor, "/"))
