from __future__ import annotations

from pathlib import Path


APP_ID = "io.github.xander_haj.Z3RLauncher"
APP_NAME = "Z3R Launcher"
APP_IDENTIFIER = "com.xander.z3r-launcher"
Z3R_REPO_URL = "https://github.com/xander-haj/Z3R"
Z3R_BETA_REPO_URL = "https://github.com/xander-haj/Z3R-Beta"
Z3R_RELEASES_URL = "https://github.com/xander-haj/Z3R/releases"
Z3R_BETA_RELEASES_URL = "https://github.com/xander-haj/Z3R-Beta/releases"
Z3R_RELEASE_API_URL = "https://api.github.com/repos/xander-haj/Z3R/releases/latest"
Z3R_BETA_RELEASE_API_URL = "https://api.github.com/repos/xander-haj/Z3R-Beta/releases/latest"
LAUNCHER_RELEASE_API_URL = "https://api.github.com/repos/xander-haj/Z3R-Launcher/releases/latest"
SPRITES_SOURCE_URL = "https://github.com/snesrev/sprites-gfx.git"
SHADERS_SOURCE_URL = "https://github.com/snesrev/glsl-shaders"
MSU_DOWNLOAD_URL = "https://www.zeldix.net/f11-msu1-development"
MSU_DIR = "msu"
SPRITES_DIR = "sprites-gfx"
SHADERS_DIR = "glsl-shaders"
STORED_ROM_NAME = "zelda3.sfc"
DEV_SETTINGS_FILE = "dev-settings.json"
REPO_SETTINGS_FILE = "repo-settings.json"
GITHUB_TOKEN_ENV = "Z3R_LAUNCHER_GITHUB_TOKEN"
FLATPAK_INFO_PATH = Path("/.flatpak-info")
C_COMPILER_CANDIDATES = ("cc", "gcc", "clang")
APPIMAGE_ENV_KEYS = ("APPDIR", "APPIMAGE", "ARGV0", "OWD", "LD_LIBRARY_PATH")
PYTHON_CHILD_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONEXECUTABLE",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
    "VIRTUAL_ENV_PROMPT",
)
PROJECT_RELEASES = {
    "xander-haj/z3r": {
        "id": "z3r",
        "label": "Z3R",
        "releases_url": Z3R_RELEASES_URL,
        "api_url": Z3R_RELEASE_API_URL,
        "preferred_assets": ("Z3R-linux-x64.tar.gz",),
    },
    "xander-haj/z3r-beta": {
        "id": "z3r-beta",
        "label": "Z3R-Beta",
        "releases_url": Z3R_BETA_RELEASES_URL,
        "api_url": Z3R_BETA_RELEASE_API_URL,
        "preferred_assets": ("Z3R-Beta-linux-x64.tar.gz", "Z3R-linux-x64.tar.gz"),
    },
}
LINUX_GAME_EXECUTABLE_NAMES = ("zelda3", "zelda3.real")
LINUX_GAME_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar", ".zip")
