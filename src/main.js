// Launcher bootstrap module. Owns shared state, the backend invoker wrapper, view
// switching, and top-bar button wiring. Per-screen DOM building lives in dedicated
// modules so this file stays focused on app-wide concerns.
import { invoke } from "./backend-client.js";
import { loadManualInstallGuides } from "./manual-guides.js";
import { connectRandomizerSetup } from "./randomizer-setup.js";
import { connectProjectCards } from "./project-cards.js";
import { connectEnvironmentScreen } from "./environment-screen.js";
import { connectControlsScreen } from "./controls-screen.js";
import { connectFeaturesScreen } from "./features-screen.js";
import { connectLinkSpriteEditor } from "./link-sprite-editor.js";
import { checksReady, updateEnvironmentActions } from "./environment-actions.js";
import { connectRepoUpdateManager } from "./repo-update-manager.js";
import { connectLauncherUpdateChecker } from "./launcher-update-checker.js";
import { connectDevSettings } from "./dev-settings.js";
import {
  connectScanPathManager,
  loadSavedRepoSettings,
  loadStoredClonePath,
  loadStoredScanPaths,
} from "./scan-path-manager.js";

// App-wide mutable state. Each screen module reads from this through the helpers bag
// so there is exactly one source of truth for the selected project, scan paths, etc.
const state = {
  candidates: [],
  scanGroups: [],
  selectedPath: null,
  scanPaths: loadStoredScanPaths(),
  clonePath: loadStoredClonePath(),
  hasStoredRom: false,
  activeView: "builds",
  environmentOs: "macos",
  setupGuidance: null,
  manualInstallGuides: null,
  runtimeInfo: null,
  environmentChecks: [],
  environmentActionRunning: false,
  failedSetupStep: null,
  repoUpdateProject: null,
  repoUpdatePreview: null,
};

// DOM references collected once at boot so screen modules don't repeat querySelector
// lookups on every render.
const elements = {
  viewPanels: document.querySelectorAll(".view-panel"),
  parentPath: document.querySelector("#parentPath"),
  projectList: document.querySelector("#projectList"),
  checkList: document.querySelector("#checkList"),
  stepList: document.querySelector("#stepList"),
  manualGuideTitle: document.querySelector("#manualGuideTitle"),
  manualGuideMeta: document.querySelector("#manualGuideMeta"),
  manualGuideContent: document.querySelector("#manualGuideContent"),
  logOutput: document.querySelector("#logOutput"),
  activityToggle: document.querySelector("#activityToggle"),
  activityPanel: document.querySelector("#activityPanel"),
  refreshButton: document.querySelector("#refreshButton"),
  updateCheckButton: document.querySelector("#updateCheckButton"),
  scanPathButton: document.querySelector("#scanPathButton"),
  uploadRomButton: document.querySelector("#uploadRomButton"),
  scanPathDialog: document.querySelector("#scanPathDialog"),
  scanPathForm: document.querySelector("#scanPathForm"),
  scanPathInput: document.querySelector("#scanPathInput"),
  scanPathSelectButton: document.querySelector("#scanPathSelectButton"),
  scanPathAddButton: document.querySelector("#scanPathAddButton"),
  scanPathList: document.querySelector("#scanPathList"),
  scanPathCloseButton: document.querySelector("#scanPathCloseButton"),
  scanPathsTabButton: document.querySelector("#scanPathsTabButton"),
  cloneTabButton: document.querySelector("#cloneTabButton"),
  scanPathsTabPanel: document.querySelector("#scanPathsTabPanel"),
  cloneTabPanel: document.querySelector("#cloneTabPanel"),
  clonePathSelect: document.querySelector("#clonePathSelect"),
  clonePathNotice: document.querySelector("#clonePathNotice"),
  cloneBetaCheckbox: document.querySelector("#cloneBetaCheckbox"),
  cloneZ3RModalButton: document.querySelector("#cloneZ3RModalButton"),
  cloneCustomUrl: document.querySelector("#cloneCustomUrl"),
  cloneCustomModalButton: document.querySelector("#cloneCustomModalButton"),
  environmentPlayableBadge: document.querySelector("#environmentPlayableBadge"),
  repoUpdateDialog: document.querySelector("#repoUpdateDialog"),
  repoUpdateForm: document.querySelector("#repoUpdateForm"),
  repoUpdateTitle: document.querySelector("#repoUpdateTitle"),
  repoUpdatePath: document.querySelector("#repoUpdatePath"),
  repoUpdateWarnings: document.querySelector("#repoUpdateWarnings"),
  repoUpdateSummary: document.querySelector("#repoUpdateSummary"),
  repoUpdateFileList: document.querySelector("#repoUpdateFileList"),
  repoUpdateOpenFolderButton: document.querySelector("#repoUpdateOpenFolderButton"),
  repoUpdateRefreshButton: document.querySelector("#repoUpdateRefreshButton"),
  repoUpdateApplyButton: document.querySelector("#repoUpdateApplyButton"),
  repoUpdateCloseButton: document.querySelector("#repoUpdateCloseButton"),
  devUnlockDialog: document.querySelector("#devUnlockDialog"),
  devUnlockInput: document.querySelector("#devUnlockInput"),
  devSettingsDialog: document.querySelector("#devSettingsDialog"),
  devSettingsForm: document.querySelector("#devSettingsForm"),
  devUpdatePathInput: document.querySelector("#devUpdatePathInput"),
  devEffectiveUpdatePath: document.querySelector("#devEffectiveUpdatePath"),
  devDefaultUpdatePath: document.querySelector("#devDefaultUpdatePath"),
  devSettingsStatus: document.querySelector("#devSettingsStatus"),
  devSettingsSaveButton: document.querySelector("#devSettingsSaveButton"),
  devSettingsResetButton: document.querySelector("#devSettingsResetButton"),
  devSettingsCloseButton: document.querySelector("#devSettingsCloseButton"),
  backButton: document.querySelector("#backButton"),
  checkButton: document.querySelector("#checkButton"),
  guideBackButton: document.querySelector("#guideBackButton"),
  venvButton: document.querySelector("#venvButton"),
  dependenciesButton: document.querySelector("#dependenciesButton"),
  extractButton: document.querySelector("#extractButton"),
  extractVisualStudioButton: document.querySelector("#extractVisualStudioButton"),
  extractTccButton: document.querySelector("#extractTccButton"),
  environmentPlayButton: document.querySelector("#environmentPlayButton"),
  clearLogButton: document.querySelector("#clearLogButton"),
};

const romFileInput = document.createElement("input");
romFileInput.type = "file";
romFileInput.accept = ".sfc";
romFileInput.hidden = true;
document.body.append(romFileInput);

// Timestamped activity console entry used by every screen for command output and
// non-fatal warnings. Keeps the log entries consistent and auto-scrolls to bottom.
function log(message) {
  const now = new Date().toLocaleTimeString();
  elements.logOutput.textContent += `\n[${now}] ${message}`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

// Safe backend invoker that routes backend errors into the activity log AND re-throws so
// callers can guard their own UI flow when needed.
async function call(command, payload = {}) {
  try {
    return await invoke(command, payload);
  } catch (error) {
    log(`${command} failed: ${error}`);
    throw error;
  }
}

// Opens trusted manual-guide links through the backend so browser and packaged app behavior match.
async function openExternalUrl(url) {
  await call("open_external_url", { url });
}

// View switching toggles the .active class on the matching panel. The Back to home
// button is hidden on the home view; the global topbar actions are home-only
// because they operate on ROM storage, scan paths, or new project folders.
function showView(view) {
  state.activeView = view;
  for (const panel of elements.viewPanels) {
    panel.classList.toggle("active", panel.dataset.view === view);
  }
  const onHome = view === "builds";
  elements.backButton.classList.toggle("hidden", onHome);
  elements.scanPathButton.classList.toggle("hidden", !onHome);
  elements.uploadRomButton.classList.toggle("hidden", !onHome);

  // Refresh the per-view content lazily so screens always reflect on-disk truth.
  if (view === "controls") {
    controlsScreen.refresh();
  }
  if (view === "features") {
    featuresScreen.refresh();
  }
  if (view === "link-sprite") {
    linkSpriteEditor.refresh();
  }
}

// Stores the selected project path and refreshes both the card grid (selected style)
// and the environment screen (which reacts to the new project's local files).
async function selectProject(projectPath) {
  if (state.selectedPath !== projectPath) {
    state.failedSetupStep = null;
  }

  state.selectedPath = projectPath;
  projectCards.render();
  await environmentScreen.runChecks();
}

// Opens the environment view for a specific project, mirroring openControls below.
async function openEnvironment(projectPath) {
  await selectProject(projectPath);
  showView("environment");
}

// Launches a ready project. The backend takes only the executable path and runs it
// from its own folder so no arbitrary shell execution happens here.
async function launchProject(candidate) {
  const result = await call("launch_game", { executablePath: candidate.executable_path });
  log(result.message);
}

// Runs a setup action and then refreshes scan + environment so the UI catches up.
async function runAction(command, payload = {}, options = {}) {
  const refreshOnFailure = options.refreshOnFailure ?? true;
  const result = await call(command, payload);
  log(result.message);

  if (result.stdout) {
    log(result.stdout.trim());
  }

  if (result.stderr) {
    log(result.stderr.trim());
  }

  if (result.ok || refreshOnFailure) {
    await refreshScan();
  } else {
    await environmentScreen.runChecks();
  }

  return result;
}

async function runSetupAction(command, payload, requiredCheckIds) {
  if (!payload) {
    return;
  }

  await environmentScreen.runChecks();

  if (!checksReady(state.environmentChecks, requiredCheckIds)) {
    log("This setup step is blocked until the required checks are OK.");
    return;
  }

  state.environmentActionRunning = true;
  updateEnvironmentActions(elements, state.environmentChecks, {
    actionRunning: true,
    hasSelectedProject: Boolean(state.selectedPath),
    failedSetupStep: state.failedSetupStep,
  });

  try {
    const result = await runAction(command, payload, { refreshOnFailure: false });

    if (!result.ok) {
      state.failedSetupStep = command;
      log("Fix the failed setup step before continuing.");
    } else {
      state.failedSetupStep = null;
    }
  } catch (error) {
    state.failedSetupStep = command;
    log("Fix the failed setup step before continuing.");
    await environmentScreen.runChecks();
  } finally {
    state.environmentActionRunning = false;
    updateEnvironmentActions(elements, state.environmentChecks, {
      actionRunning: false,
      hasSelectedProject: Boolean(state.selectedPath),
      failedSetupStep: state.failedSetupStep,
    });
  }
}

// Guard used by setup buttons that require a selected project — logs a hint and
// returns null so the calling handler can short-circuit cleanly.
function selectedProjectPayload() {
  if (!state.selectedPath) {
    log("Select or clone a Z3R folder first.");
    return null;
  }

  return { projectPath: state.selectedPath };
}

function extractAssetRequiredCheckIds() {
  const packagedLinuxDownload = Boolean(state.runtimeInfo?.downloaded_linux_game_executable);
  const baseIds = ["python", "venv", "python-dependencies", "rom"];
  return packagedLinuxDownload
    ? [...baseIds, "game-executable-download"]
    : [...baseIds, "make", "c-compiler", "sdl2-dev"];
}

// Re-runs the backend sibling scan, keeps the selected project alive when it still
// exists, and repaints the card grid and environment screen.
async function refreshScan() {
  const scan = await call("scan_siblings", { scanRoots: state.scanPaths });
  state.candidates = scan.candidates;
  state.scanGroups = scan.groups ?? [];
  elements.parentPath.textContent = "";

  if (state.hasStoredRom && state.candidates.length > 0) {
    const result = await call("sync_stored_rom_to_projects", {
      projectPaths: state.candidates.map((candidate) => candidate.path),
    });

    if (result.stdout) {
      log(`SFC copied to:\n${result.stdout}`);
    }
  }

  if (!state.candidates.some((candidate) => candidate.path === state.selectedPath)) {
    state.selectedPath = state.candidates[0]?.path ?? null;
    state.failedSetupStep = null;
  }

  projectCards.render();
  await environmentScreen.runChecks();
}

// Refreshes the launcher-managed ROM status independently from project scanning.
async function refreshRomStatus() {
  const status = await call("stored_rom_status");
  state.hasStoredRom = status.available;
  elements.uploadRomButton.textContent = status.available ? "Open SFC Folder" : "Upload SFC";
  elements.scanPathButton.disabled = !status.available;
  elements.scanPathButton.title = status.available ? "" : "Upload an SFC before managing repos.";
}

async function chooseRomFile() {
  if (window.showOpenFilePicker) {
    try {
      const [handle] = await window.showOpenFilePicker({
        multiple: false,
        types: [
          {
            description: "SNES ROM",
            accept: {
              "application/octet-stream": [".sfc"],
            },
          },
        ],
      });
      return handle.getFile();
    } catch (error) {
      if (error?.name === "AbortError") {
        return null;
      }
      throw error;
    }
  }

  return new Promise((resolve) => {
    let settled = false;

    function finish(file) {
      if (settled) {
        return;
      }
      settled = true;
      romFileInput.removeEventListener("change", onChange);
      window.removeEventListener("focus", onFocus);
      resolve(file);
    }

    function onChange() {
      finish(romFileInput.files?.[0] ?? null);
    }

    function onFocus() {
      window.setTimeout(() => {
        if (!romFileInput.files?.length) {
          finish(null);
        }
      }, 200);
    }

    romFileInput.value = "";
    romFileInput.addEventListener("change", onChange);
    window.addEventListener("focus", onFocus);
    romFileInput.click();
  });
}

async function storeSelectedRom() {
  const file = await chooseRomFile();

  if (!file) {
    return null;
  }

  if (!file.name.toLowerCase().endsWith(".sfc")) {
    throw new Error("Select a .sfc ROM file.");
  }

  const bytes = new Uint8Array(await file.arrayBuffer());
  return call("store_rom_upload", {
    fileName: file.name,
    dataBase64: bytesToBase64(bytes),
  });
}

function bytesToBase64(bytes) {
  const chunkSize = 0x8000;
  let binary = "";

  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }

  return btoa(binary);
}

// Loads the editable Setup Path JSON so step copy can change without backend edits.
async function loadSetupGuidance() {
  try {
    const response = await fetch("./setup-guidance.json");
    state.setupGuidance = await response.json();
  } catch (error) {
    log(`Could not load setup guidance: ${error}`);
    state.setupGuidance = null;
  }
}

// Loads the editable manual-install guide JSON consumed by environment-screen.js when
// a missing dependency row exposes a Manual install button.
async function loadGuideContent() {
  state.manualInstallGuides = await loadManualInstallGuides();
}

async function loadRuntimeInfo() {
  state.runtimeInfo = await call("app_runtime_info");
}

// One helpers bag shared with every screen module so they all see the same state +
// shared callbacks without reaching for module-level globals of their own.
const helpers = {
  state,
  elements,
  call,
  log,
  openExternalUrl,
  showView,
  selectProject,
  openEnvironment,
  launchProject,
  refreshScan,
  runAction,
  selectedProjectPayload,
};

// Each connect*() returns a small object the bootstrap calls into (render/refresh).
const projectCards = connectProjectCards(helpers);
const environmentScreen = connectEnvironmentScreen(helpers);
const controlsScreen = connectControlsScreen(helpers);
const featuresScreen = connectFeaturesScreen(helpers);
const linkSpriteEditor = connectLinkSpriteEditor(helpers);
const repoUpdateManager = connectRepoUpdateManager(helpers);
helpers.openRepoUpdate = repoUpdateManager.open;
connectScanPathManager(helpers);
connectLauncherUpdateChecker(helpers);
connectDevSettings(helpers);

elements.refreshButton.addEventListener("click", refreshScan);
elements.backButton.addEventListener("click", () => showView("builds"));
elements.guideBackButton.addEventListener("click", () => showView("environment"));
elements.activityToggle.addEventListener("click", () => {
  const isOpen = elements.activityPanel.classList.toggle("open");
  elements.activityToggle.setAttribute("aria-expanded", String(isOpen));
});
elements.checkButton.addEventListener("click", environmentScreen.runChecks);
elements.uploadRomButton.addEventListener("click", async () => {
  elements.uploadRomButton.disabled = true;

  try {
    if (state.hasStoredRom) {
      const result = await call("open_stored_rom_folder");
      log(result.message);
      return;
    }

    const status = await storeSelectedRom();

    if (status) {
      log(`SFC stored at ${status.path}`);
      await refreshRomStatus();
      await refreshScan();
    }
  } catch (error) {
    log(state.hasStoredRom ? `Could not open SFC folder: ${error}` : `Could not store SFC: ${error}`);
  } finally {
    elements.uploadRomButton.disabled = false;
  }
});
connectRandomizerSetup({
  state,
  call,
  log,
  refreshScan,
  runAction,
  selectedProjectPayload,
});
elements.clearLogButton.addEventListener("click", () => {
  elements.logOutput.textContent = "Ready.";
});
elements.venvButton.addEventListener("click", async () => {
  const payload = selectedProjectPayload();
  if (payload) {
    await runSetupAction("create_venv", payload, ["python"]);
  }
});
elements.dependenciesButton.addEventListener("click", async () => {
  const payload = selectedProjectPayload();
  if (payload) {
    await runSetupAction("install_dependencies", payload, ["python", "venv"]);
  }
});
elements.extractButton.addEventListener("click", async () => {
  const payload = selectedProjectPayload();
  if (payload) {
    await runSetupAction("extract_assets", payload, extractAssetRequiredCheckIds());
  }
});
elements.extractVisualStudioButton.addEventListener("click", async () => {
  const payload = selectedProjectPayload();
  if (payload) {
    await runSetupAction("extract_assets_visual_studio", payload, [
      "python",
      "venv",
      "python-dependencies",
      "rom",
      "msbuild",
    ]);
  }
});
elements.extractTccButton.addEventListener("click", async () => {
  const payload = selectedProjectPayload();
  if (payload) {
    await runSetupAction("extract_assets_tcc", payload, [
      "python",
      "venv",
      "python-dependencies",
      "rom",
      "tcc",
    ]);
  }
});
elements.environmentPlayButton.addEventListener("click", async () => {
  const candidate = state.candidates.find((entry) => entry.path === state.selectedPath);

  if (!candidate?.executable_path || candidate.status !== "ready") {
    log("Build the selected project before pressing Play.");
    return;
  }

  await launchProject(candidate);
});

showView(state.activeView);
await loadSetupGuidance();
await loadGuideContent();
await loadRuntimeInfo();
await loadSavedRepoSettings(helpers);
await refreshRomStatus();
refreshScan();
