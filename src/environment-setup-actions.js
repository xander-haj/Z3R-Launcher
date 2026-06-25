// Wires Environment setup buttons to backend commands and keeps action gating in sync.

import { checksReady, updateEnvironmentActions } from "./environment-actions.js";

export function connectEnvironmentSetupActions(helpers, environmentScreen) {
  const { elements } = helpers;

  elements.venvButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "create_venv", ["python"]);
  });
  elements.dependenciesButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "install_dependencies", ["python", "venv"]);
  });
  elements.extractButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "extract_assets", assetRequiredCheckIds(helpers.state));
  });
  elements.buildProjectButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "build_project", projectBuildRequiredCheckIds(helpers.state));
  });
  elements.rebuildProjectButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "rebuild_project", ["make", "c-compiler", "sdl2-dev"]);
  });
  elements.buildVisualStudioButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "build_project_visual_studio", ["msbuild"]);
  });
  elements.rebuildVisualStudioButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "rebuild_project_visual_studio", ["msbuild"]);
  });
  elements.buildTccButton.addEventListener("click", async () => {
    await runSelectedSetupAction(helpers, environmentScreen, "build_project_tcc", ["tcc"]);
  });
}

async function runSelectedSetupAction(helpers, environmentScreen, command, requiredCheckIds) {
  const payload = helpers.selectedProjectPayload();
  if (!payload) {
    return;
  }
  await runSetupAction(helpers, environmentScreen, command, payload, requiredCheckIds);
}

async function runSetupAction(helpers, environmentScreen, command, payload, requiredCheckIds) {
  const { state, elements, log, runAction } = helpers;
  await environmentScreen.runChecks();

  if (!checksReady(state.environmentChecks, requiredCheckIds)) {
    log("This setup step is blocked until the required checks are OK.");
    return;
  }

  state.environmentActionRunning = true;
  refreshEnvironmentActions(helpers);

  try {
    const result = await runAction(command, payload, { refreshOnFailure: false });
    state.failedSetupStep = result.ok ? null : command;

    if (!result.ok) {
      log("Fix the failed setup step before continuing.");
    }
  } catch (error) {
    state.failedSetupStep = command;
    log("Fix the failed setup step before continuing.");
    await environmentScreen.runChecks();
  } finally {
    state.environmentActionRunning = false;
    refreshEnvironmentActions(helpers);
  }
}

function refreshEnvironmentActions(helpers) {
  const { state, elements } = helpers;
  updateEnvironmentActions(elements, state.environmentChecks, {
    actionRunning: state.environmentActionRunning,
    hasSelectedProject: Boolean(state.selectedPath),
    failedSetupStep: state.failedSetupStep,
    environmentOs: state.environmentOs,
    downloadedLinuxGameExecutable: Boolean(state.runtimeInfo?.downloaded_linux_game_executable),
  });
}

function assetRequiredCheckIds(state) {
  return ["python", "venv", "python-dependencies", "rom"];
}

function projectBuildRequiredCheckIds(state) {
  return state.runtimeInfo?.downloaded_linux_game_executable
    ? ["game-executable-download"]
    : ["make", "c-compiler", "sdl2-dev"];
}
