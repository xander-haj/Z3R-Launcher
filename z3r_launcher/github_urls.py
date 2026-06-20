from __future__ import annotations

import re

from .errors import LauncherError


def normalize_github_url(repo_url: str) -> str:
    trimmed = repo_url.strip()
    if trimmed.startswith("git clone"):
        raise LauncherError("Paste only the GitHub repository URL, not a git clone command.")
    if re.search(r"\s", trimmed):
        raise LauncherError("The GitHub URL cannot contain spaces.")
    if not trimmed.startswith("https://github.com/"):
        raise LauncherError("Enter a GitHub URL that starts with https://github.com/.")
    return trimmed.rstrip("/")


def normalize_launcher_update_api_url(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    if trimmed.startswith("https://github.com/"):
        owner, repo = github_repo_owner_and_name(normalize_github_url(trimmed))
        return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    api_match = re.fullmatch(
        r"https://api\.github\.com/repos/([^/\s]+)/([^/\s]+)/releases/latest",
        trimmed.rstrip("/"),
    )
    if not api_match:
        raise LauncherError("Enter a GitHub repo URL or a GitHub latest-release API URL.")

    owner, repo = api_match.groups()
    if not is_safe_segment(owner) or not is_safe_segment(repo):
        raise LauncherError("The update repository path contains unsupported characters.")
    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


def github_repo_owner_and_name(repo_url: str) -> tuple[str, str]:
    repo_part = repo_url.removeprefix("https://github.com/").split("?", 1)[0].split("#", 1)[0]
    parts = repo_part.split("/")
    if len(parts) != 2:
        raise LauncherError("Enter a GitHub repository URL like https://github.com/owner/repo.")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        raise LauncherError("Enter a GitHub repository URL like https://github.com/owner/repo.")
    if not is_safe_segment(owner):
        raise LauncherError("The owner name contains characters this launcher cannot use for a folder.")
    if not is_safe_segment(repo):
        raise LauncherError("The repository name contains characters this launcher cannot use for a folder.")
    return owner, repo


def is_safe_segment(segment: str) -> bool:
    return all(character.isascii() and (character.isalnum() or character in "._-") for character in segment)
