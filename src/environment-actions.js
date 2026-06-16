// This module derives Environment screen setup-action availability from read-only check rows.

// Enables each setup button only after the dependency gates before it are satisfied.
// elements contains the Environment screen action buttons, and checks are backend check rows.
// Returns nothing after updating disabled states in place.
export function updateEnvironmentActions(elements, checks, options = {}) {
  const actionRunning = options.actionRunning ?? false;
  const hasSelectedProject = options.hasSelectedProject ?? true;
  const failedSetupStep = options.failedSetupStep ?? null;
  const pythonReady = checkReady(checks, "python");
  const venvReady = checkReady(checks, "venv");
  const dependenciesReady = checkReady(checks, "python-dependencies");
  // Build assets invokes restool.py --extract-from-rom, which fails without zelda3.sfc in the project root.
  const romReady = checkReady(checks, "rom");
  const executableDownloadReady =
    !checks.some((check) => check.id === "game-executable-download") ||
    checkReady(checks, "game-executable-download");
  const windowsReady = checks.some((check) => check.id === "msbuild" || check.id === "tcc");
  const unixBuildIds = ["make", "c-compiler", "sdl2-dev"];
  const hasUnixBuildChecks = checks.some((check) => unixBuildIds.includes(check.id));
  const unixBuildReady = !hasUnixBuildChecks || checksReady(checks, unixBuildIds);
  const msbuildReady = checkReady(checks, "msbuild");
  const tccReady = checkReady(checks, "tcc");
  const baseBuildReady = pythonReady && venvReady && dependenciesReady && romReady && executableDownloadReady;
  const venvFailureBlocksDownstream = failedSetupStep === "create_venv";
  const dependencyFailureBlocksBuild = failedSetupStep === "install_dependencies";
  const setupBlocked = actionRunning || !hasSelectedProject;

  elements.venvButton.disabled = setupBlocked || !pythonReady;
  elements.dependenciesButton.disabled =
    setupBlocked || venvFailureBlocksDownstream || !pythonReady || !venvReady;
  elements.extractButton.classList.toggle("hidden", windowsReady);
  elements.extractButton.disabled =
    setupBlocked || venvFailureBlocksDownstream || dependencyFailureBlocksBuild || !baseBuildReady || !unixBuildReady;
  elements.extractVisualStudioButton.classList.toggle("hidden", !windowsReady || !msbuildReady);
  elements.extractVisualStudioButton.disabled =
    setupBlocked || venvFailureBlocksDownstream || dependencyFailureBlocksBuild || !baseBuildReady || !msbuildReady;
  elements.extractTccButton.classList.toggle("hidden", !windowsReady);
  elements.extractTccButton.disabled =
    setupBlocked || venvFailureBlocksDownstream || dependencyFailureBlocksBuild || !baseBuildReady || !tccReady;
}

// Looks up one environment check by stable id and treats only the explicit ok state as ready.
// checks is the backend report list, and id is the required dependency id.
// Returns true when the matching check exists and reports ok.
export function checkReady(checks, id) {
  return checks.some((check) => check.id === id && check.state === "ok");
}

export function checksReady(checks, ids) {
  return ids.every((id) => checkReady(checks, id));
}
