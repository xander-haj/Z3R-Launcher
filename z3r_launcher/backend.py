from __future__ import annotations

import re
from typing import Any, Callable

from dev_tools.link_sprite_editor.backend_commands import (
    build_link_sprite_assets,
    read_link_sprite_palette_command,
    read_link_sprite_preview,
    save_link_sprite_palette,
)

from .app_commands import (
    app_runtime_info,
    choose_and_store_rom,
    choose_scan_root,
    open_external_url,
    open_stored_rom_folder,
    read_dev_settings,
    read_repo_settings,
    save_dev_settings,
    save_repo_settings,
    stored_rom_status,
    store_rom_upload,
    sync_stored_rom_to_projects,
)
from .dev_tool_assets import (
    clone_dev_tools,
    install_dev_tool,
    launch_dev_tool,
    read_dev_tools,
    stop_dev_tool,
)
from .environment_checks import check_environment
from .errors import LauncherError
from .feature_assets import (
    choose_and_store_msu,
    clone_feature_asset,
    install_feature_asset,
    read_feature_assets,
    read_sprite_preview,
    store_msu_paths,
)
from .ini_tools import read_zelda_ini, set_zelda_ini_value, update_zelda_ini_line
from .platform_paths import app_data_dir, static_dir
from .randomizer_commands import (
    compile_randomized_assets,
    extract_randomizer_assets,
    read_randomizer_setup,
    restore_vanilla_randomizer_yaml,
    run_randomizer,
)
from .repo_scanner import scan_siblings
from .repo_update import apply_repo_update, preview_repo_update, rename_zelda_ini_to_user_ini
from .project_versions import read_project_release_version
from .setup_commands import (
    apply_snesrev_makefile_patch,
    apply_snesrev_solution_patch,
    build_project,
    build_project_tcc,
    build_project_visual_studio,
    clone_custom_project,
    clone_project,
    create_venv,
    extract_assets,
    extract_assets_tcc,
    extract_assets_visual_studio,
    install_dependencies,
    launch_game,
    open_project_folder,
    rebuild_project,
    rebuild_project_visual_studio,
)
from .update_downloads import current_update_version
from .update_installers import install_launcher_update


class LauncherBackend:
    def __init__(self, schedule_exit: Callable[[], None] | None = None) -> None:
        self.schedule_exit = schedule_exit or (lambda: None)
        self.commands: dict[str, Callable[..., Any]] = self.build_command_map()

    def build_command_map(self) -> dict[str, Callable[..., Any]]:
        return {
            "scan_siblings": scan_siblings,
            "read_project_release_version": read_project_release_version,
            "app_runtime_info": app_runtime_info,
            "launcher_version": current_update_version,
            "read_repo_settings": read_repo_settings,
            "save_repo_settings": save_repo_settings,
            "read_dev_settings": read_dev_settings,
            "save_dev_settings": save_dev_settings,
            "install_launcher_update": lambda allow_downgrade=False: install_launcher_update(
                self.schedule_exit,
                allow_downgrade,
            ),
            "check_environment": check_environment,
            "launch_game": launch_game,
            "choose_scan_root": choose_scan_root,
            "clone_project": clone_project,
            "clone_custom_project": clone_custom_project,
            "open_project_folder": open_project_folder,
            "create_venv": create_venv,
            "install_dependencies": install_dependencies,
            "extract_assets": extract_assets,
            "extract_assets_visual_studio": extract_assets_visual_studio,
            "extract_assets_tcc": extract_assets_tcc,
            "build_project": build_project,
            "build_project_visual_studio": build_project_visual_studio,
            "build_project_tcc": build_project_tcc,
            "rebuild_project": rebuild_project,
            "rebuild_project_visual_studio": rebuild_project_visual_studio,
            "open_external_url": open_external_url,
            "read_feature_assets": read_feature_assets,
            "clone_feature_asset": clone_feature_asset,
            "choose_and_store_msu": choose_and_store_msu,
            "store_msu_paths": store_msu_paths,
            "install_feature_asset": install_feature_asset,
            "read_sprite_preview": read_sprite_preview,
            "read_link_sprite_preview": read_link_sprite_preview,
            "read_link_sprite_palette": read_link_sprite_palette_command,
            "save_link_sprite_palette": save_link_sprite_palette,
            "build_link_sprite_assets": build_link_sprite_assets,
            "apply_snesrev_makefile_patch": apply_snesrev_makefile_patch,
            "apply_snesrev_solution_patch": apply_snesrev_solution_patch,
            "stored_rom_status": stored_rom_status,
            "store_rom_upload": store_rom_upload,
            "choose_and_store_rom": choose_and_store_rom,
            "open_stored_rom_folder": open_stored_rom_folder,
            "sync_stored_rom_to_projects": sync_stored_rom_to_projects,
            "read_dev_tools": read_dev_tools,
            "clone_dev_tools": clone_dev_tools,
            "install_dev_tool": install_dev_tool,
            "launch_dev_tool": launch_dev_tool,
            "stop_dev_tool": stop_dev_tool,
            "read_randomizer_setup": read_randomizer_setup,
            "extract_randomizer_assets": extract_randomizer_assets,
            "run_randomizer": run_randomizer,
            "restore_vanilla_randomizer_yaml": restore_vanilla_randomizer_yaml,
            "compile_randomized_assets": compile_randomized_assets,
            "preview_repo_update": preview_repo_update,
            "apply_repo_update": apply_repo_update,
            "rename_zelda_ini_to_user_ini": rename_zelda_ini_to_user_ini,
            "read_zelda_ini": read_zelda_ini,
            "update_zelda_ini_line": update_zelda_ini_line,
            "set_zelda_ini_value": set_zelda_ini_value,
        }

    def invoke(self, command: str, payload: dict[str, Any] | None = None) -> Any:
        handler = self.commands.get(command)
        if not handler:
            raise LauncherError(f"Unknown launcher command: {command}")
        return handler(**normalize_payload(payload or {}))


def camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", value).lower()


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {camel_to_snake(key): value for key, value in payload.items()}


__all__ = [
    "LauncherBackend",
    "LauncherError",
    "app_data_dir",
    "open_external_url",
    "static_dir",
]
