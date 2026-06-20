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
import { collectAppElements } from "./app-elements.js";
import { createActivityDrawer } from "./activity-drawer.js";
import { createRomUploader } from "./rom-upload.js";
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

const elements = collectAppElements();
const activityDrawer = createActivityDrawer(elements);
const log = activityDrawer.log;

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

const romUploader = createRomUploader(call);

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
  refreshActivityUpdateInfo: activityDrawer.refreshUpdateInfo,
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
activityDrawer.connect(call);

elements.refreshButton.addEventListener("click", refreshScan);
elements.backButton.addEventListener("click", () => showView("builds"));
elements.guideBackButton.addEventListener("click", () => showView("environment"));
elements.checkButton.addEventListener("click", environmentScreen.runChecks);
elements.uploadRomButton.addEventListener("click", async () => {
  elements.uploadRomButton.disabled = true;

  try {
    if (state.hasStoredRom) {
      const result = await call("open_stored_rom_folder");
      log(result.message);
      return;
    }

    const status = await romUploader.storeSelectedRom();

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
await activityDrawer.refreshUpdateInfo();
await loadRuntimeInfo();
await loadSavedRepoSettings(helpers);
await refreshRomStatus();
refreshScan();
