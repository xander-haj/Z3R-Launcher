from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import LauncherError
from .platform_paths import hidden_subprocess_kwargs, is_flatpak_runtime, is_macos, is_windows
from .processes import command_env, decode_output


def pick_folder(title: str) -> str | None:
    commands: list[list[str]] = []
    if is_windows():
        script = (
            "$shell = New-Object -ComObject Shell.Application; "
            f"$folder = $shell.BrowseForFolder(0, '{powershell_quote(title)}', 0); "
            "if ($folder -ne $null) { $folder.Self.Path }"
        )
        commands.append(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    elif is_macos():
        commands.append(["osascript", "-e", f'POSIX path of (choose folder with prompt "{applescript_quote(title)}")'])
    else:
        if is_flatpak_runtime():
            commands.extend([
                ["flatpak-spawn", "--host", "/usr/bin/zenity", "--file-selection", "--directory", f"--title={title}"],
                ["flatpak-spawn", "--host", "/usr/bin/kdialog", "--getexistingdirectory", str(Path.home()), "--title", title],
                ["flatpak-spawn", "--host", "/usr/bin/yad", "--file", "--directory", f"--title={title}"],
            ])
        commands.extend([
            ["zenity", "--file-selection", "--directory", f"--title={title}"],
            ["kdialog", "--getexistingdirectory", str(Path.home()), "--title", title],
            ["yad", "--file", "--directory", f"--title={title}"],
        ])
    picked = run_picker_commands(commands)
    return picked if picked is not None else tkinter_pick_folder(title)


def pick_file(title: str, filters: list[tuple[str, str]]) -> str | None:
    commands: list[list[str]] = []
    if is_windows():
        filter_text = "SNES ROM (*.sfc)|*.sfc"
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
            f"$dialog.Title = '{powershell_quote(title)}'; "
            f"$dialog.Filter = '{powershell_quote(filter_text)}'; "
            "if ($dialog.ShowDialog() -eq 'OK') { $dialog.FileName }"
        )
        commands.append(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    elif is_macos():
        commands.append(["osascript", "-e", f'POSIX path of (choose file of type {{"sfc"}} with prompt "{applescript_quote(title)}")'])
    else:
        if is_flatpak_runtime():
            commands.extend([
                ["flatpak-spawn", "--host", "/usr/bin/zenity", "--file-selection", f"--title={title}", "--file-filter=SNES ROM | *.sfc"],
                ["flatpak-spawn", "--host", "/usr/bin/kdialog", "--getopenfilename", str(Path.home()), "*.sfc|SNES ROM"],
                ["flatpak-spawn", "--host", "/usr/bin/yad", "--file", f"--title={title}"],
            ])
        commands.extend([
            ["zenity", "--file-selection", f"--title={title}", "--file-filter=SNES ROM | *.sfc"],
            ["kdialog", "--getopenfilename", str(Path.home()), "*.sfc|SNES ROM"],
            ["yad", "--file", f"--title={title}"],
        ])
    picked = run_picker_commands(commands)
    return picked if picked is not None else tkinter_pick_file(title, filters)


def run_picker_commands(commands: list[list[str]]) -> str | None:
    for command in commands:
        try:
            output = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=command_env(),
                check=False,
                **hidden_subprocess_kwargs(),
            )
        except OSError:
            continue
        if output.returncode == 0:
            value = decode_output(output.stdout).strip()
            return value or None
        stderr = decode_output(output.stderr).lower()
        if "cancel" in stderr or "canceled" in stderr:
            return None
    return None


def tkinter_pick_folder(title: str) -> str | None:
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        raise LauncherError("No folder picker is available. Paste the folder path into the field instead.")
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = filedialog.askdirectory(title=title)
        return value or None
    finally:
        root.destroy()


def tkinter_pick_file(title: str, filters: list[tuple[str, str]]) -> str | None:
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        raise LauncherError("No file picker is available.")
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        value = filedialog.askopenfilename(title=title, filetypes=filters)
        return value or None
    finally:
        root.destroy()


def powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def applescript_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
