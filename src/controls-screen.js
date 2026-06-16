// Controls screen orchestrator: loads the project's zelda3.ini snapshot, builds both
// tabs around the controller overlay, and wires tab switching + the back button.
//
// Tab layout (both tabs share the same shape):
//   1. Keyboard layout dropdown (KeyMap tab only; picks active QWERTY/QWERTZ/AZERTY).
//   2. SNES controller image with 12 overlay labels bound to the active Controls= line.
//   3. "Additional Configs" heading.
//   4. Generic editable rows for every OTHER line in the section (everything whose key
//      is not "Controls").

// Imports: row builder, keyboard preset dropdown, controller overlay renderer, and the
// shared HTML escape util so the title/author text injected by innerHTML stays safe.
import { appendControlsRow } from "./controls-rows.js";
import { renderKeyboardPresetSection } from "./controls-keyboard-preset.js";
import { renderControllerOverlay } from "./controller-overlay.js";
import { escapeHtml } from "./shared-utils.js";

// Public connector. Wires the tab buttons once at boot and exposes a refresh() callable
// the host invokes whenever the Controls view becomes active. The screen relies on the
// topbar's global Back to home button for navigation (no duplicate in-header button).
export function connectControlsScreen(helpers) {
  const refs = collectScreenElements();

  refs.tabButtons.forEach((button) => {
    button.addEventListener("click", () => activateTab(refs, button.dataset.controlsTab));
  });

  return {
    async refresh() {
      await refreshControlsContent(refs, helpers);
    },
  };
}

// Collects the DOM nodes this screen owns. One-time lookup at boot.
function collectScreenElements() {
  return {
    panel: document.querySelector("#controlsPanel"),
    title: document.querySelector("#controlsTitle"),
    author: document.querySelector("#controlsAuthor"),
    tabButtons: document.querySelectorAll(".controls-tab-button"),
    keymapTab: document.querySelector("#controlsKeymapTab"),
    gamepadTab: document.querySelector("#controlsGamepadTab"),
  };
}

// Activates one tab by id and visually highlights the matching tab button. Tab content
// is already rendered in refreshControlsContent — switching is purely a visibility flip.
function activateTab(refs, tabId) {
  refs.tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.controlsTab === tabId);
  });
  refs.keymapTab.classList.toggle("active", tabId === "keymap");
  refs.gamepadTab.classList.toggle("active", tabId === "gamepad");
}

// Loads the project's zelda3.ini and re-renders both tab panels. Called every time the
// user arrives on the Controls view so the page always reflects on-disk truth.
async function refreshControlsContent(refs, helpers) {
  refs.keymapTab.textContent = "";
  refs.gamepadTab.textContent = "";

  if (!helpers.state.selectedPath) {
    setHeading(refs, null);
    refs.keymapTab.innerHTML = `<p class="controls-empty">Select or clone a Z3R folder before opening Controls.</p>`;
    return;
  }

  // Lookup the matching card candidate so the heading mirrors the card's repo name and
  // optional "by <owner>" line — the full project path is intentionally NOT shown here.
  const candidate = helpers.state.candidates.find(
    (entry) => entry.path === helpers.state.selectedPath,
  );

  let snapshot;
  try {
    snapshot = await helpers.call("read_zelda_ini", { projectPath: helpers.state.selectedPath });
  } catch (error) {
    helpers.log(`Could not read zelda3.ini: ${error}`);
    setHeading(refs, candidate);
    refs.keymapTab.innerHTML = `<p class="controls-empty">zelda3.ini missing or unreadable.</p>`;
    return;
  }

  setHeading(refs, candidate);

  await renderKeymapTab(refs.keymapTab, snapshot.keymap_lines, helpers);
  await renderGamepadTab(refs.gamepadTab, snapshot.gamepad_lines, helpers);
  activateTab(refs, "keymap");
}

// Paints the heading title + optional "by <owner>" author line from the card candidate.
// Falls back to a plain "Controls" title when no project is selected.
function setHeading(refs, candidate) {
  if (!candidate) {
    refs.title.textContent = "Controls";
    refs.author.textContent = "";
    return;
  }
  refs.title.textContent = candidate.name;
  refs.author.textContent = candidate.owner ? `by ${candidate.owner}` : "";
}

// Renders the KeyMap tab: layout dropdown -> controller overlay -> Additional Configs.
async function renderKeymapTab(container, keymapLines, helpers) {
  const presetLines = keymapLines.filter((line) => line.key === "Controls");
  const otherLines = keymapLines.filter((line) => line.key !== "Controls");

  // Slot the dynamic overlay container before mounting the dropdown so the preset's
  // onActiveChange callback can find the slot when it fires for the initial state.
  const overlaySlot = document.createElement("div");
  overlaySlot.className = "controller-overlay-slot";
  // Track the active preset so dropdown changes can re-render the overlay against the
  // newly-active line without rebuilding everything else.
  const overlayState = { activeLine: null };
  renderKeyboardPresetSection(container, presetLines, helpers, async (activeLine) => {
    overlayState.activeLine = activeLine;
    overlaySlot.textContent = "";
    await renderControllerOverlay(overlaySlot, "keymap", activeLine, helpers);
  });
  container.append(overlaySlot);

  appendAdditionalConfigs(container, otherLines, helpers);
}

// Renders the Gamepad tab: short XInput clarifying note in the top-left, controller
// overlay against [GamepadMap] Controls, then the Additional Configs section for any
// remaining gamepad keys.
async function renderGamepadTab(container, gamepadLines, helpers) {
  const controlsLine = gamepadLines.find((line) => line.key === "Controls");
  const otherLines = gamepadLines.filter((line) => line.key !== "Controls");

  // Small left-aligned hint that tells the user gamepad bindings use XInput button names
  // (A/B/X/Y, Lb/Rb, DpadUp, Back, Start). Lives only on this tab.
  const hint = document.createElement("p");
  hint.className = "controls-tab-hint";
  hint.textContent = "Inputs use XInput button names (A, B, X, Y, Lb, Rb, DpadUp, Back, Start).";
  container.append(hint);

  const overlaySlot = document.createElement("div");
  overlaySlot.className = "controller-overlay-slot";
  container.append(overlaySlot);
  if (controlsLine) {
    await renderControllerOverlay(overlaySlot, "gamepad", controlsLine, helpers);
  } else {
    overlaySlot.innerHTML = `<p class="controls-empty">No [GamepadMap] Controls line found in zelda3.ini.</p>`;
  }

  appendAdditionalConfigs(container, otherLines, helpers);
}

// Renders the "Additional Configs" heading and the generic editable row list for every
// non-Controls line in the section. Shared by both tabs so the section consistently
// pairs the overlay above with simple rows below.
function appendAdditionalConfigs(container, otherLines, helpers) {
  if (otherLines.length === 0) {
    return;
  }
  const heading = document.createElement("p");
  heading.className = "controls-additional-heading";
  heading.textContent = "Additional Configs";
  container.append(heading);

  const list = document.createElement("div");
  list.className = "controls-row-list";
  for (const line of otherLines) {
    appendControlsRow(list, line, helpers);
  }
  container.append(list);
}
