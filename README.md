# Z3R Launcher

Z3R Launcher is a cross-platform launcher for Xander's Z3R fork. It helps users find,
clone, set up, build, customize, randomize, and launch local Z3R projects from one place.

Prebuilt installers and packages are provided from the repository's
[GitHub Releases tab](https://github.com/xander-haj/lawn/releases). Use those unless you
specifically want to build the launcher from source.

## App Overview

The launcher is Python-only: a plain HTML/CSS/JavaScript frontend in `src/` and a
standard-library Python backend in `z3r_launcher/`. The Python process serves the UI on
localhost, opens it in your default browser, and exposes the same command surface the
frontend uses for scanning, setup actions, INI editing, updates, and launching games.

## Main features:

- Scans the launcher folder and user-added repo folders for Z3R builds.
- Uploads and stores a user-supplied `zelda3.sfc`, then copies it into detected or cloned projects.
- Clones the default Z3R repo or a custom GitHub fork.
- Checks project setup state for Git, Python, virtualenv, Python packages, ROM files, SDL2, Make,
  MSBuild, TCC, executable downloads, and related platform tools.
- Runs guided setup actions: create venv, install project requirements, extract assets, and either
  build or download the game executable for the current package type.
- Launches ready builds.
- Edits selected `zelda3.ini` settings, including aspect ratio, controls, gamepad settings, and feature toggles.
- Manages optional feature assets such as MSU packs, sprites, and shaders.
- Provides a randomizer setup screen for supported Z3R folders.
- Checks GitHub Releases from the Python backend and installs launcher updates with the matching platform package.

The launcher does not include a ROM. Users must provide their own legally obtained compatible US `.sfc` file.

## How To Use

- Upload sfc file
- Choose scan directory location and add it
- Clone Z3R, Z3R-Beta (via checkbox), or another snesrev based zelda3 project
- Click on environments
- Click the buttons in order until the play button lights up
- If you want to randomize your dat file the head over to the randomizer page
- Edit the ini and control features
- Edit sprites and shaders
- Navigate back to home and play the game

## OS Differences

dmg and flatpak file users will need to specify a scan path to avoid read and write permission in the default directory (where the executable is ran from) before cloning a repo

## Run From Source

Requirements:

- Python 3.10 or newer
- Git, Python venv support, and Make/SDL2 or Windows build tools only for native source builds

Run from the repository root:

```sh
python3 -m z3r_launcher
```

The command starts a localhost server and opens the launcher in your default browser.

## Build Packages

Build each desktop package on its target operating system. PyInstaller packages the Python runtime
for AppImage, macOS, and Windows; Flatpak uses the GNOME SDK runtime Python.

### Linux AppImage

The release workflow builds the AppImage on Ubuntu with PyInstaller and AppImageKit:

```sh
python3 -m pip install --upgrade pyinstaller certifi
python3 -m PyInstaller --clean packaging/pyinstaller/z3r-launcher.spec
```

The workflow then assembles an AppDir with:

- `dist/z3r-launcher`
- `packaging/appimage/AppRun`
- `packaging/appimage/io.github.xander_haj.Z3RLauncher.desktop`
- `resources/icons/128x128.png`

The workflow emits `Z3R-Launcher-linux-x64.AppImage`.

### macOS DMGs

macOS releases are built natively on GitHub's Intel and Apple Silicon macOS runners:

- Intel: `Z3R-Launcher-macos-intel.dmg`
- Apple Silicon: `Z3R-Launcher-macos-apple-silicon.dmg`

The PyInstaller spec creates `dist/Z3R Launcher.app`. The release workflow copies that app bundle
into a DMG staging folder with an `/Applications` shortcut, then creates the compressed DMG with
`hdiutil`.

### Flatpak

The Flatpak manifest is `packaging/flatpak/io.github.xander_haj.Z3RLauncher.yml`.
It installs the Python package, static UI, resources, and bundled-tool metadata into
`/app/share/z3r-launcher`, then runs `/usr/bin/python3 -m z3r_launcher`.

The Flatpak uses the GNOME SDK runtime so Steam Deck and other Flatpak users can run the
launcher-managed Git, Python, venv, and pip path inside the sandbox instead of installing
those tools on the host OS. For Z3R and Z3R-Beta, packaged Linux builds generate
`zelda3_assets.dat` locally, then download the matching Linux executable from GitHub
Releases. The Flatpak can work in the home folder and Steam Deck removable-media paths
under `/run/media`.

### Windows Setup Exe

Windows releases bundle the launcher executable plus the project-build toolkit. Prepare and verify
the toolkit first:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ./scripts/prepare-windows-toolkit.ps1
powershell.exe -ExecutionPolicy Bypass -File ./scripts/verify-windows-toolkit.ps1
```

The toolkit is generated under `bundled-tools/windows/` and includes portable Git, Python, TCC,
and SDL2. It is packaged into the PyInstaller executable so users can clone and build without
installing those dependencies separately.

Build the executable and setup package:

```powershell
python -m pip install --upgrade pyinstaller certifi
python -m PyInstaller --clean packaging/pyinstaller/z3r-launcher.spec
copy dist\z3r-launcher.exe dist\Z3R-Launcher-windows-x64.exe
$repoRoot = (Get-Location).Path
makensis.exe "/DREPO_ROOT=$repoRoot" packaging\windows\z3r-launcher.nsi
```

The NSIS output is `dist/Z3R-Launcher-windows-x64-setup.exe`.

## Dependencies for Building Z3R Projects Inside the Launcher

These are needed by users who want the launcher to clone and build Z3R projects from source.

All platforms:

- A legally obtained compatible US ROM uploaded through `Upload SFC`, or placed in the project as `zelda3.sfc`
- Git
- Python 3
- A project-local Python virtual environment
- Python packages from the selected Z3R project's `requirements.txt`

macOS:

- Xcode Command Line Tools for `make` and `clang`
- SDL2 development files, for example `brew install sdl2`

Linux:

- `make` and a C compiler available as `cc`, `gcc`, or `clang`
- SDL2 development files, for example `sudo apt-get install libsdl2-dev` on Debian/Ubuntu
- `python3-venv` on Debian/Ubuntu if Python cannot create a virtual environment

Prebuilt AppImage and Flatpak launcher releases do not compile the Linux game
executable locally. They build `zelda3_assets.dat` from the user's ROM, then
download the matching Linux executable from the selected Z3R or Z3R-Beta GitHub
Release.

Windows:

- Visual Studio Build Tools with `Desktop development with C++` for the MSBuild route, or
- TCC and SDL2 for the lightweight TCC route
- Windows Terminal or another terminal app for running setup commands

Prebuilt Windows releases include bundled portable Git, Python, TCC, and SDL2 for the
launcher-managed setup path. MSBuild is still required if you choose the Visual Studio build route.

## Launcher Updates

The top-bar Updates button checks the latest published GitHub Release for `xander-haj/lawn`.
When a newer release exists, the launcher downloads and starts the matching package:

- Windows uses `Z3R-Launcher-windows-x64-setup.exe`, preserving the required bundled Git, Python, SDL2,
  and TCC toolkit.
- macOS uses `Z3R-Launcher-macos-intel.dmg` on Intel Macs and
  `Z3R-Launcher-macos-apple-silicon.dmg` on Apple Silicon Macs.
- AppImage releases replace the running AppImage file and relaunch it.
- Flatpak releases download the `.flatpak` bundle and run the host Flatpak install-or-update command.

The updater does not execute remote scripts. It downloads release packages and runs fixed platform installer commands.
