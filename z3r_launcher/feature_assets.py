from __future__ import annotations

import shutil
import os
from pathlib import Path
from typing import Any

from dev_tools.link_sprite_editor.zspr import parse_zspr_preview

from .constants import MSU_DIR, MSU_DOWNLOAD_URL, SHADERS_DIR, SHADERS_SOURCE_URL, SPRITES_DIR, SPRITES_SOURCE_URL
from .errors import LauncherError
from .pickers import pick_folder
from .platform_paths import display_path, is_windows
from .processes import action_result, git_program, run_command
from .project_files import copy_dir_contents, copy_file_with_parents, folder_matches_all_files, rom_storage_dir


def read_feature_assets(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    storage = rom_storage_dir()
    return {
        "storage_dir": display_path(storage),
        "msu_download_url": MSU_DOWNLOAD_URL,
        "sprites_source_url": SPRITES_SOURCE_URL,
        "shaders_source_url": SHADERS_SOURCE_URL,
        "msu": build_group(
            list_msu_options(project / MSU_DIR, "project", True),
            list_msu_options(storage / MSU_DIR, "shared", False),
        ),
        "sprites": build_group(
            list_file_options(project / SPRITES_DIR, SPRITES_DIR, ["zspr"], "project"),
            list_file_options(storage / SPRITES_DIR, SPRITES_DIR, ["zspr"], "shared"),
        ),
        "shaders": build_group(
            list_file_options(project / SHADERS_DIR, SHADERS_DIR, ["glsl", "glslp"], "project"),
            list_file_options(storage / SHADERS_DIR, SHADERS_DIR, ["glsl", "glslp"], "shared"),
        ),
    }


def clone_feature_asset(asset_kind: str) -> dict[str, Any]:
    catalog = {
        "sprites": (SPRITES_DIR, SPRITES_SOURCE_URL, "sprites", ["zspr"]),
        "shaders": (SHADERS_DIR, SHADERS_SOURCE_URL, "shaders", ["glsl", "glslp"]),
    }
    if asset_kind not in catalog:
        raise LauncherError("Unknown cloneable feature asset.")
    folder, url, label, extensions = catalog[asset_kind]
    storage = rom_storage_dir()
    destination = storage / folder
    if destination.is_dir():
        options = list_file_options(destination, folder, extensions, "shared")
        if options:
            return action_result(True, f"{label} repository is already available.", display_path(destination))
        if (destination / ".git").is_dir():
            return run_command(git_program(), ["pull", "--ff-only"], destination, f"Updated {label}.")
        raise LauncherError(f"{label} folder exists but contains no supported assets: {display_path(destination)}")
    storage.mkdir(parents=True, exist_ok=True)
    return run_command(git_program(), ["clone", url, folder], storage, f"Cloned {label}.")


def choose_and_store_msu() -> dict[str, Any] | None:
    selected = pick_folder("Select extracted MSU folder")
    return store_msu_sources([Path(selected)]) if selected else None


def store_msu_paths(paths: list[str]) -> dict[str, Any]:
    return store_msu_sources([Path(path) for path in paths])


def install_feature_asset(project_path: str, asset_kind: str, asset_value: str) -> dict[str, Any]:
    project = Path(project_path)
    storage = rom_storage_dir()
    if asset_kind == "sprites":
        return install_single_asset(project, storage, asset_value)
    if asset_kind == "shaders":
        return install_shader_asset(project, storage, asset_value)
    if asset_kind == "msu":
        return install_msu_asset(project, storage, asset_value)
    raise LauncherError("Unknown feature asset type.")


def read_sprite_preview(project_path: str, sprite_path: str) -> dict[str, Any]:
    relative = safe_relative_path(sprite_path)
    project = Path(project_path)
    storage = rom_storage_dir()
    sprite = next((path for path in (project / relative, storage / relative) if path.is_file()), None)
    if not sprite:
        raise LauncherError(f"Selected sprite was not found in the build or shared storage: {display_path(relative)}")
    try:
        bytes_data = sprite.read_bytes()
    except OSError as error:
        raise LauncherError(f"Could not read sprite {display_path(sprite)}: {error}") from error
    pixel_data, palette_data = parse_zspr_preview(bytes_data)
    return {
        "label": sprite.stem or display_path(relative),
        "pixel_data": list(pixel_data),
        "palette_data": list(palette_data),
    }


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or any(part in ("..", "") for part in path.parts):
        raise LauncherError("Selected asset path is not safe to copy.")
    if is_windows() and path.drive:
        raise LauncherError("Selected asset path is not safe to copy.")
    return path


def collect_files(directory: Path, extensions: list[str]) -> list[Path]:
    files: list[Path] = []
    if not directory.is_dir():
        return files
    for child in directory.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            files.extend(collect_files(child, extensions))
        elif path_has_extension(child, extensions):
            files.append(child)
    return files


def path_has_extension(path: Path, extensions: list[str]) -> bool:
    return path.suffix.lower().lstrip(".") in [extension.lower() for extension in extensions]


def path_to_slash(path: Path) -> str:
    return "/".join(part for part in path.parts if part not in (path.anchor, os.sep))


def sanitize_folder_name(name: str) -> str:
    return "".join(character for character in name if character.isascii() and (character.isalnum() or character in "-_"))


def build_group(project_options: list[dict[str, str]], shared_options: list[dict[str, str]]) -> dict[str, Any]:
    options_by_value = {option["value"]: option for option in shared_options}
    options_by_value.update({option["value"]: option for option in project_options})
    return {
        "available": bool(project_options or shared_options),
        "project_available": bool(project_options),
        "shared_available": bool(shared_options),
        "options": [options_by_value[key] for key in sorted(options_by_value)],
    }


def list_file_options(base_dir: Path, value_root: str, extensions: list[str], source: str) -> list[dict[str, str]]:
    files = sorted(collect_files(base_dir, extensions))
    options: list[dict[str, str]] = []
    for path in files:
        relative = path.relative_to(base_dir)
        value = path_to_slash(Path(value_root) / relative)
        options.append({"label": path.stem or value, "value": value, "source": source})
    return options


def list_msu_options(root: Path, source: str, include_root_pack: bool) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    if not root.is_dir():
        return options
    if include_root_pack:
        prefix = detect_msu_prefix(root, root)
        if prefix:
            options.append({"label": "Project MSU", "value": f"{MSU_DIR}/{prefix}", "source": source})
    for child in root.iterdir():
        if not child.is_dir():
            continue
        prefix = detect_msu_prefix(root, child)
        if prefix:
            options.append({"label": child.name or prefix, "value": f"{MSU_DIR}/{prefix}", "source": source})
    options.sort(key=lambda option: option["label"])
    return options


def detect_msu_prefix(root: Path, folder: Path) -> str | None:
    audio_files = sorted(collect_files(folder, ["pcm", "opuz", "msu"]))
    for file in audio_files:
        prefix = msu_prefix_from_file(root, file)
        if prefix:
            return prefix
    return None


def msu_prefix_from_file(root: Path, file: Path) -> str | None:
    extension = file.suffix.lower().lstrip(".")
    stem = file.stem
    if extension in ("pcm", "opuz"):
        prefix = numbered_msu_prefix(stem)
    elif extension == "msu":
        prefix = f"{stem}-"
    else:
        prefix = None
    if not prefix:
        return None
    relative_parent = file.parent.relative_to(root)
    return path_to_slash(relative_parent / prefix)


def numbered_msu_prefix(stem: str) -> str | None:
    if "-" not in stem:
        return None
    base, track = stem.rsplit("-", 1)
    return f"{base}-" if track and track.isdigit() else None


def store_msu_sources(sources: list[Path]) -> dict[str, Any]:
    if not sources:
        raise LauncherError("No MSU files or folders were provided.")
    storage = rom_storage_dir() / MSU_DIR
    storage.mkdir(parents=True, exist_ok=True)
    pack_name = msu_pack_name(sources)
    destination = storage / pack_name
    copied = 0
    for source in sources:
        if source.is_dir():
            copied += copy_dir_contents(source, destination)
        elif source.is_file():
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination / source.name)
            copied += 1
    return action_result(True, f"Stored MSU pack {pack_name}.", f"{copied} file(s) copied to {display_path(destination)}")


def msu_pack_name(sources: list[Path]) -> str:
    first = sources[0]
    name_source = first.name if first.is_dir() else (first.parent.name if first.parent else "")
    name = sanitize_folder_name(name_source)
    if not name:
        raise LauncherError("Could not determine a folder name for the MSU pack.")
    return name


def install_single_asset(project: Path, storage: Path, asset_value: str) -> dict[str, Any]:
    relative = safe_relative_path(asset_value)
    destination = project / relative
    if destination.is_file():
        return installed_result("Asset already exists in the selected build.", relative)
    source = storage / relative
    if not source.is_file():
        raise LauncherError(f"Selected asset was not found in shared storage: {display_path(source)}")
    copy_file_with_parents(source, destination)
    return installed_result("Asset copied into the selected build.", relative)


def install_shader_asset(project: Path, storage: Path, asset_value: str) -> dict[str, Any]:
    relative = safe_relative_path(asset_value)
    if not relative.parts or relative.parts[0] != SHADERS_DIR:
        raise LauncherError("Selected shader path did not include the shader repository folder.")

    source_root = storage / SHADERS_DIR
    source = storage / relative
    destination_root = project / SHADERS_DIR
    destination = project / relative
    ignored_names = {".git"}

    if source.is_file():
        if folder_matches_all_files(source_root, destination_root, ignored_names):
            return installed_result("Shader repository already exists in the selected build.", relative)
        copy_dir_contents(source_root, destination_root, ignored_names)
        if not destination.is_file():
            raise LauncherError(f"Copied shaders, but selected shader is still missing: {display_path(destination)}")
        return installed_result("Shader repository copied into the selected build.", relative)

    if destination.is_file():
        return installed_result("Shader already exists in the selected build.", relative)
    if not source_root.is_dir():
        raise LauncherError(f"Shared shader repository was not found: {display_path(source_root)}")
    raise LauncherError(f"Selected shader was not found in the build or shared storage: {display_path(relative)}")


def install_msu_asset(project: Path, storage: Path, asset_value: str) -> dict[str, Any]:
    relative = safe_relative_path(asset_value)
    if msu_prefix_exists(project, asset_value):
        return installed_msu_result("MSU pack already exists in the selected build.", relative, msu_mode_for_prefix(project, asset_value))
    parts = relative.parts
    if len(parts) < 2:
        raise LauncherError("Selected MSU path did not include a pack folder.")
    pack_path = Path(parts[1])
    source = storage / MSU_DIR / pack_path
    destination = project / MSU_DIR / pack_path
    if not source.is_dir():
        raise LauncherError(f"Selected MSU pack was not found in shared storage: {display_path(source)}")
    copy_dir_contents(source, destination)
    return installed_msu_result("MSU pack copied into the selected build.", relative, msu_mode_for_prefix(project, asset_value))


def installed_result(message: str, relative: Path) -> dict[str, Any]:
    return action_result(True, message, path_to_slash(relative))


def installed_msu_result(message: str, relative: Path, mode: str) -> dict[str, Any]:
    return action_result(True, message, f"{path_to_slash(relative)}\n{mode}")


def msu_prefix_exists(project: Path, asset_value: str) -> bool:
    prefix_path = project / asset_value
    parent = prefix_path.parent
    prefix = prefix_path.name
    if not parent.is_dir() or not prefix:
        return False
    for entry in parent.iterdir():
        name = entry.name
        if name.startswith(prefix) and name.lower().endswith((".pcm", ".opuz", ".msu")):
            return True
    return False


def msu_mode_for_prefix(project: Path, asset_value: str) -> str:
    prefix_path = project / asset_value
    parent = prefix_path.parent
    prefix = prefix_path.name
    if not parent.is_dir() or not prefix:
        return "true"
    for entry in parent.iterdir():
        if entry.name.startswith(prefix) and entry.name.lower().endswith(".opuz"):
            return "opuz"
    return "true"
