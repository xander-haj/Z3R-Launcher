// This module owns the Randomizer Setup screen so the launcher entry point can stay focused.

// Imports the always-open dropdown renderer that replaced the older chip-style picker.
// The dropdown module owns its own state (item id <-> category mapping, selection painting,
// and category->item disable wiring) so this file can stay under the 400-line ceiling.
import { renderExclusionDropdowns } from "./randomizer-exclusions.js";

// Wires randomizer buttons to fixed backend commands and refreshes the setup summary when the screen opens.
// options contains shared app state, DOM references, and backend helpers from main.js.
// Returns nothing; event listeners remain attached for the lifetime of the app.
export function connectRandomizerSetup(options) {
  const elements = getRandomizerElements();
  const { state } = options;
  let lastView = state.activeView;

  options.elements = elements;
  loadRandomizerGuidance(options);
  elements.randomizerExtractButton.addEventListener("click", () => extractAssets(options));
  elements.randomizerPreviewButton.addEventListener("click", () => runRandomizer(options, true));
  elements.randomizerRunButton.addEventListener("click", () => runRandomizer(options, false));
  elements.randomizerBuildButton.addEventListener("click", () => compileRandomizedAssets(options));
  elements.randomizerRestoreButton.addEventListener("click", () => restoreVanillaYaml(options));

  window.setInterval(() => {
    if (state.activeView === "randomizer" && lastView !== "randomizer") {
      refreshRandomizerSetup(options);
    }

    lastView = state.activeView;
  }, 200);
}

// Collects the Randomizer Setup DOM nodes in this module to keep main.js under the project line limit.
// Parameters: none.
// Returns an object of screen-specific elements used by the renderer and actions.
function getRandomizerElements() {
  return {
    randomizerInstructions: document.querySelector("#randomizerInstructions"),
    randomizerStatus: document.querySelector("#randomizerStatus"),
    randomizerMode: document.querySelector("#randomizerMode"),
    randomizerSeed: document.querySelector("#randomizerSeed"),
    randomizerExcludeRooms: document.querySelector("#randomizerExcludeRooms"),
    randomizerExcludeLocations: document.querySelector("#randomizerExcludeLocations"),
    randomizerExcludeItems: document.querySelector("#randomizerExcludeItems"),
    randomizerExcludeCategories: document.querySelector("#randomizerExcludeCategories"),
    // Containers for the always-open dropdown panels rendered by randomizer-exclusions.js.
    // The items panel is populated from the masterlist item options; the categories panel
    // uses the fixed CATEGORY_OPTIONS list inside that module.
    randomizerItemsDropdownPanel: document.querySelector("#randomizerItemsDropdownPanel"),
    randomizerCategoriesDropdownPanel: document.querySelector("#randomizerCategoriesDropdownPanel"),
    randomizerSmallKeys: document.querySelector("#randomizerSmallKeys"),
    randomizerBigChests: document.querySelector("#randomizerBigChests"),
    randomizerNoSpoiler: document.querySelector("#randomizerNoSpoiler"),
    randomizerConfigList: document.querySelector("#randomizerConfigList"),
    randomizerExtractButton: document.querySelector("#randomizerExtractButton"),
    randomizerPreviewButton: document.querySelector("#randomizerPreviewButton"),
    randomizerRunButton: document.querySelector("#randomizerRunButton"),
    randomizerBuildButton: document.querySelector("#randomizerBuildButton"),
    randomizerRestoreButton: document.querySelector("#randomizerRestoreButton"),
  };
}

// Loads editable Randomizer Setup instructions from JSON so copy changes do not require backend edits.
// options contains the screen elements and logger.
// Returns a promise that settles after the instruction area has been populated.
async function loadRandomizerGuidance(options) {
  const { elements, log } = options;

  try {
    const response = await fetch("./randomizer-guidance.json");
    const guidance = await response.json();
    renderRandomizerGuidance(elements, guidance.instructions ?? []);
  } catch (error) {
    log(`Could not load randomizer-guidance.json: ${error}`);
    renderRandomizerGuidance(elements, []);
  }
}

// Renders editable instruction steps into the left side of the Randomizer Setup screen.
// elements contains the target instruction node, and instructions is an ordered text list.
// Returns nothing after replacing the current instruction content.
function renderRandomizerGuidance(elements, instructions) {
  elements.randomizerInstructions.textContent = "";
  const list = document.createElement("ol");
  list.className = "step-list";

  for (const instruction of instructions) {
    const item = document.createElement("li");
    item.textContent = instruction;
    list.append(item);
  }

  elements.randomizerInstructions.append(list);
}

// Reads randomizer setup metadata from the selected project and paints the instructions/config list.
// options supplies the selected project path and safe backend command wrapper.
// Returns a promise that settles after the screen has been rendered.
async function refreshRandomizerSetup(options) {
  const { elements, state, call, log } = options;

  if (!state.selectedPath) {
    elements.randomizerStatus.textContent = "Select or clone a Z3R folder before opening randomizer setup.";
    elements.randomizerConfigList.textContent = "";
    updateRandomizerActions(elements, false);
    return;
  }

  try {
    const report = await call("read_randomizer_setup", { projectPath: state.selectedPath });
    renderRandomizerReport(elements, report);
  } catch (error) {
    log(`Could not read randomizer setup: ${error}`);
  }
}

// Converts the backend setup report into the visible instructions and config status rows.
// elements contains the target DOM nodes, and report is the serialized backend command result.
// Returns nothing after replacing the relevant screen content.
function renderRandomizerReport(elements, report) {
  elements.randomizerStatus.textContent = report.available
    ? `Randomizer files found in ${report.project_path}`
    : `Randomizer files are missing in ${report.project_path}`;
  elements.randomizerConfigList.textContent = "";
  updateRandomizerActions(elements, hasConfigFile(report, "Vanilla masterlist"));
  // Hand the item options from the backend to the dropdown module. The module also
  // re-runs the category->item disable pass internally so any categories already
  // present in the input field re-apply their disable effect after a fresh render.
  renderExclusionDropdowns(elements, report.item_options ?? []);

  for (const file of report.config_files) {
    const row = document.createElement("div");
    row.className = `randomizer-config-row state-${file.state}`;
    row.innerHTML = `
      <strong>${escapeHtml(file.label)}</strong>
      <span>${escapeHtml(file.state)}</span>
      <p class="path-line">${escapeHtml(file.detail)}</p>
    `;
    elements.randomizerConfigList.append(row);
  }
}

// Keeps the randomizer workflow ordered around the generated clean vanilla masterlist.
// elements contains the route buttons, and masterlistReady reflects the setup report.
// Returns nothing after disabling actions that should wait for the masterlist.
function updateRandomizerActions(elements, masterlistReady) {
  elements.randomizerExtractButton.disabled = false;
  elements.randomizerPreviewButton.disabled = !masterlistReady;
  elements.randomizerRunButton.disabled = !masterlistReady;
  elements.randomizerBuildButton.disabled = !masterlistReady;
}

// Finds one reported randomizer file by label and confirms it exists.
// report is the backend setup payload, and label is the display label to match.
// Returns true when the file row is present and marked found.
function hasConfigFile(report, label) {
  return report.config_files.some((file) => file.label === label && file.state === "found");
}

// Runs asset extraction from the randomizer workflow page as the first setup step.
// options provides the selected project path and shared action runner.
// Returns a promise that settles after extraction and refresh complete.
async function extractAssets(options) {
  const { selectedProjectPayload, runAction } = options;
  const payload = selectedProjectPayload();

  if (!payload) {
    return;
  }

  await runAction("extract_randomizer_assets", payload);
}

// Runs the randomizer with the current form options, using dry-run mode when requested.
// options provides the selected project path, logger, command runner, and scan refresh callback.
// Returns a promise that settles after the backend action and project refresh finish.
async function runRandomizer(options, dryRun) {
  const { selectedProjectPayload, runAction } = options;
  const payload = selectedProjectPayload();

  if (!payload) {
    return;
  }

  await runAction("run_randomizer", {
    ...payload,
    options: readRandomizerForm(options.elements, dryRun),
  });
}

// Compiles the already-randomized YAML into zelda3_assets.dat without re-extracting first.
// options provides the selected project path and shared action runner.
// Returns a promise that settles after the compile command and refresh complete.
async function compileRandomizedAssets(options) {
  const { selectedProjectPayload, runAction } = options;
  const payload = selectedProjectPayload();

  if (!payload) {
    return;
  }

  await runAction("compile_randomized_assets", payload);
}

// Restores randomized dungeon chest YAML back to the vanilla values saved in the masterlist.
// options provides the selected project path and shared action runner.
// Returns a promise that settles after restore and refresh complete.
async function restoreVanillaYaml(options) {
  const { selectedProjectPayload, runAction } = options;
  const payload = selectedProjectPayload();

  if (!payload) {
    return;
  }

  await runAction("restore_vanilla_randomizer_yaml", payload);
}

// Reads form controls into the backend payload shape, preserving comma-separated exclusions.
// elements contains the randomizer form controls, and dryRun forces no-write preview mode.
// Returns a plain object that can be serialized through backend invoke.
function readRandomizerForm(elements, dryRun) {
  return {
    mode: elements.randomizerMode.value,
    seed: cleanText(elements.randomizerSeed.value),
    dry_run: dryRun,
    no_spoiler: elements.randomizerNoSpoiler.checked,
    include_small_keys: elements.randomizerSmallKeys.checked,
    include_big_chests: elements.randomizerBigChests.checked,
    exclude_rooms: cleanText(elements.randomizerExcludeRooms.value),
    exclude_locations: cleanText(elements.randomizerExcludeLocations.value),
    exclude_items: cleanText(elements.randomizerExcludeItems.value),
    exclude_categories: cleanText(elements.randomizerExcludeCategories.value),
  };
}

// Trims user-entered text and converts blank form fields to null for optional backend fields.
// value is the raw input string from a form control.
// Returns a trimmed string or null when the user left the field empty.
function cleanText(value) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

// Escapes text inserted through template strings so filesystem data cannot become markup.
// value is any serializable value that should be displayed as text.
// Returns HTML-safe text.
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
