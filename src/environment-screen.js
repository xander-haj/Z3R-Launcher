// Renders the Environment screen: check rows, manual-install buttons, and the setup
// path step list. Extracted from main.js so the environment-specific DOM building has
// a focused home and main.js stays comfortably under the project line ceiling.

// Imports: shared escape util, environment action button enable/disable, manual install
// guide rendering, and the in-app guide page renderer.
import { escapeHtml } from "./shared-utils.js";
import { updateEnvironmentActions } from "./environment-actions.js";
import {
  getManualInstallGuide,
  hasManualInstallGuide,
  renderManualInstallGuide,
} from "./manual-guides.js";

// Public connector: returns the runChecks() callable that main.js wires to the refresh
// flow and to the Run Checks button. Centralizing the env render here keeps main.js
// focused on bootstrap + global wiring only.
export function connectEnvironmentScreen(helpers) {
  return {
    async runChecks() {
      await runEnvironmentChecks(helpers);
    },
  };
}

// Calls the backend env check command, stores the OS for manual-guide lookups, and
// refreshes the visual rows + action buttons + step list in one pass.
async function runEnvironmentChecks(helpers) {
  const { state, elements, call } = helpers;
  const report = await call("check_environment", {
    projectPath: state.selectedPath,
    scanRoot: null,
  });
  state.environmentOs = report.os;
  state.environmentChecks = report.checks;
  renderChecks(report.checks, helpers);
  updateEnvironmentActions(elements, report.checks, {
    actionRunning: state.environmentActionRunning,
    hasSelectedProject: Boolean(state.selectedPath),
    failedSetupStep: state.failedSetupStep,
    environmentOs: state.environmentOs,
    downloadedLinuxGameExecutable: Boolean(state.runtimeInfo?.downloaded_linux_game_executable),
  });
  renderPlayableBadge(helpers);
  renderSteps(helpers);
}

// Renders each backend check into a compact row. Missing dependencies that have a
// matching manual-install guide pick up an extra "Manual install" button on the right.
function renderChecks(checks, helpers) {
  const { elements } = helpers;
  elements.checkList.textContent = "";

  for (const check of checks) {
    const row = document.createElement("div");
    row.className = `check-row state-${check.state} ${hasManualAction(check, helpers) ? "has-action" : ""}`;
    row.innerHTML = `
      <span class="check ${escapeHtml(check.state)}">${escapeHtml(check.state)}</span>
      <strong>${escapeHtml(check.label)}</strong>
      <span class="path-line">${escapeHtml(check.detail || "No detail returned.")}</span>
    `;

    if (hasManualAction(check, helpers)) {
      const fixButton = document.createElement("button");
      fixButton.className = "check-action-button";
      fixButton.type = "button";
      fixButton.textContent = "Manual install";
      fixButton.addEventListener("click", () => openManualInstallGuide(check, helpers));
      row.append(fixButton);
    }

    elements.checkList.append(row);
  }
}

// Returns true when a check should expose a manual-install button. Rows that already
// have their own action buttons (venv, python-dependencies) are intentionally excluded.
function hasManualAction(check, helpers) {
  const automaticRows = ["venv", "python-dependencies"];
  return (
    check.state === "missing" &&
    !automaticRows.includes(check.id) &&
    hasManualInstallGuide(helpers.state.manualInstallGuides, helpers.state.environmentOs, check.id)
  );
}

// Opens the in-app manual-install guide view for the dependency represented by a row.
function openManualInstallGuide(check, helpers) {
  const { state, elements, log, showView, openExternalUrl } = helpers;
  const guide = getManualInstallGuide(state.manualInstallGuides, state.environmentOs, check.id);

  if (!guide) {
    log(`No manual install guide found for ${check.label} on ${state.environmentOs}.`);
    return;
  }

  renderManualInstallGuide(guide, elements, state.selectedPath, openExternalUrl);
  showView("manual-guide");
}

// Renders the Setup Path step list with the selected project path substituted in for
// every "{projectPath}" placeholder, and skips path-only steps when no project is
// selected yet so the user doesn't see literal placeholders.
function renderSteps(helpers) {
  const { state, elements } = helpers;
  const steps = setupStepsForRuntime(state);
  elements.stepList.textContent = "";

  for (const step of steps) {
    if (!state.selectedPath && step.includes("{projectPath}")) {
      continue;
    }

    const item = document.createElement("li");
    item.textContent = step.replace("{projectPath}", state.selectedPath ?? "");
    elements.stepList.append(item);
  }
}

function setupStepsForRuntime(state) {
  if (state.environmentOs === "linux" && state.runtimeInfo?.downloaded_linux_game_executable) {
    return state.setupGuidance?.linux_packaged ?? state.setupGuidance?.linux ?? [];
  }
  return state.setupGuidance?.[state.environmentOs] ?? [];
}

function renderPlayableBadge(helpers) {
  const { state, elements } = helpers;
  const candidate = state.candidates.find((entry) => entry.path === state.selectedPath);
  const playable = candidate?.status === "ready" && Boolean(candidate?.executable_path);

  elements.environmentPlayButton.disabled = !playable;
  elements.environmentPlayableBadge.classList.toggle("hidden", !playable);
}
