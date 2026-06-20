from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import LauncherError
from .platform_paths import display_path
from .processes import action_result, run_command
from .project_files import venv_python


def read_randomizer_setup(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    entry_path = project / "assets" / "restool-randomize.py"
    engine_path = project / "assets" / "randomizer.py"
    config_files = [
        file_status("Randomizer CLI", entry_path),
        capability_status("Safe Mode support", entry_path, "--mode", "Update the selected Z3R folder's randomizer scripts before using Safe Mode."),
        file_status("Randomizer engine", engine_path),
        file_status("Vanilla masterlist", project / "assets" / "randomizer-masterlist.json"),
        folder_status("Dungeon YAML", project / "assets" / "dungeon", "Extract assets before randomizing if this folder is missing."),
        folder_status("Spoiler logs", project / "assets" / "randomizer-spoilers", "Created automatically when randomizer runs with spoiler output enabled."),
    ]
    return {
        "project_path": display_path(project),
        "available": entry_path.is_file() and engine_path.is_file(),
        "item_options": read_item_options(project / "assets" / "randomizer-masterlist.json"),
        "config_files": config_files,
    }


def extract_randomizer_assets(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    python = project_python(project)
    extract = run_command(display_path(python), ["assets/restool.py", "--extract-from-rom", "--no-build"], project, "Randomizer asset extraction complete.")
    if not extract["ok"]:
        return extract
    masterlist = run_command(display_path(python), ["assets/restool-randomize.py", "--generate-masterlist"], project, "Randomizer masterlist generated.")
    return combine_results("Randomizer assets extracted and vanilla masterlist generated.", extract, masterlist)


def run_randomizer(project_path: str, options: dict[str, Any]) -> dict[str, Any]:
    project = Path(project_path)
    python = project_python(project)
    entry_path = project / "assets" / "restool-randomize.py"
    options = options or {}
    requested_mode = options.get("mode") or "safe"
    if requested_mode == "safe" and not file_contains(entry_path, "--mode"):
        raise LauncherError(
            "The selected Z3R folder's randomizer CLI does not support Safe Mode yet. "
            "Update assets/restool-randomize.py and assets/randomizer.py in that folder, then try again."
        )
    args = ["assets/restool-randomize.py"]
    for key, flag in (("mode", "--mode"), ("seed", "--seed")):
        push_option(args, flag, options.get(key))
    if options.get("dry_run"):
        args.append("--dry-run")
    if options.get("no_spoiler"):
        args.append("--no-spoiler")
    if options.get("include_small_keys"):
        args.append("--include-small-keys")
    if options.get("include_big_chests"):
        args.append("--include-big-chests")
    for key, flag in (
        ("exclude_rooms", "--exclude-room"),
        ("exclude_locations", "--exclude-location"),
        ("exclude_items", "--exclude-item"),
        ("exclude_categories", "--exclude-category"),
    ):
        push_option(args, flag, options.get(key))
    return run_command(display_path(python), args, project, "Randomizer run complete.")


def restore_vanilla_randomizer_yaml(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    python = project_python(project)
    return run_command(display_path(python), ["assets/restool-randomize.py", "--restore-vanilla"], project, "Vanilla randomizer YAML restored.")


def compile_randomized_assets(project_path: str) -> dict[str, Any]:
    project = Path(project_path)
    python = project_python(project)
    return run_command(display_path(python), ["assets/restool.py"], project, "Randomized assets compiled.")


def project_python(project: Path) -> Path:
    python = venv_python(project / ".venv") or venv_python(project / "venv")
    if not python:
        raise LauncherError("Create a venv before using the randomizer setup screen.")
    return python


def read_item_options(masterlist_path: Path) -> list[dict[str, Any]]:
    try:
        manifest = json.loads(masterlist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    locations = manifest.get("locations")
    if not isinstance(locations, list):
        return []
    counts: dict[int, int] = {}
    for entry in locations:
        if isinstance(entry, dict) and isinstance(entry.get("item"), int) and 0 <= entry["item"] <= 255:
            counts[entry["item"]] = counts.get(entry["item"], 0) + 1
    return [
        {"id": item_id, "label": item_label(item_id), "count": count, "detail": f"Item id {item_id}; appears in {count} vanilla chest location(s)."}
        for item_id, count in sorted(counts.items())
    ]


def item_label(item_id: int) -> str:
    labels = {
        6: "Mirror Shield",
        7: "Fire Rod",
        8: "Ice Rod",
        9: "Magic Hammer",
        10: "Hookshot",
        11: "Bow",
        12: "Boomerang",
        18: "Lamp",
        21: "Cane of Somaria",
        22: "Magic Bottle",
        23: "Piece of Heart",
        24: "Cane of Byrna",
        25: "Magic Cape",
        27: "Power Glove",
        28: "Titan's Mitt",
        31: "Moon Pearl",
        34: "Blue Mail",
        35: "Red Mail",
        36: "Small Key",
        37: "Compass",
        40: "Bombs",
        42: "Magical Boomerang",
        50: "Big Key",
        51: "Dungeon Map",
        52: "Rupee",
        53: "Rupees (5)",
        54: "Rupees (20)",
        63: "Heart Container",
        64: "Rupees (100)",
        65: "Rupees (50)",
        67: "Arrow",
        68: "Arrows (10)",
        70: "Rupees (300)",
    }
    return labels.get(item_id, "Item")


def file_status(label: str, path: Path) -> dict[str, str]:
    return {"label": label, "state": "found" if path.is_file() else "missing", "detail": display_path(path)}


def folder_status(label: str, path: Path, missing_detail: str) -> dict[str, str]:
    return {"label": label, "state": "found" if path.is_dir() else "missing", "detail": display_path(path) if path.is_dir() else missing_detail}


def capability_status(label: str, path: Path, needle: str, missing_detail: str) -> dict[str, str]:
    found = file_contains(path, needle)
    return {"label": label, "state": "found" if found else "missing", "detail": f"{display_path(path)} supports {needle}." if found else missing_detail}


def file_contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except OSError:
        return False


def combine_results(message: str, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    stdout = "\n".join(text for text in (first["stdout"], second["stdout"]) if text)
    stderr = "\n".join(text for text in (first["stderr"], second["stderr"]) if text)
    return action_result(first["ok"] and second["ok"], message if second["ok"] else second["message"], stdout, stderr)


def push_option(args: list[str], flag: str, value: str | None) -> None:
    if value is not None:
        trimmed = str(value).strip()
        if trimmed:
            args.extend([flag, trimmed])
