// Inline Aspect Ratio compound widget mounted into each Detected Build card. The widget
// shows the project's current ExtendedAspectRatio value as an editable text input with a
// dropdown arrow button to its right. The arrow toggles a flyout panel containing:
//   * Four radio rows for the supported aspect ratio choices (16:9, 16:10, 18:9, 4:3)
//   * Three flag checkboxes (extend_y prefix, unchanged_sprites suffix, no_visual_fixes suffix)
//   * A WindowSize text input (Auto or WidthxHeight) sourced from [Graphics] WindowSize
//
// Edits auto-save to {project_path}/zelda3.ini:
//   * Radio + checkbox + WindowSize flyout changes write immediately.
//   * Free-form typing in the input or in WindowSize debounces 250ms after the last keystroke.
// All writes go through update_zelda_ini_line by absolute line number so the rest of the
// file (and its comments) is preserved verbatim.

// Imports: escapeHtml for safe placeholder text rendering of project-controlled strings.
import { escapeHtml } from "./shared-utils.js";

// Supported aspect ratio values, in the order they appear in the dropdown.
const RATIO_OPTIONS = ["16:9", "16:10", "18:9", "4:3"];

// Suffix flag ids; "extend_y" is a prefix flag and lives in its own slot in the value.
const SUFFIX_FLAGS = ["unchanged_sprites", "no_visual_fixes"];

// Debounce window (ms) for free-form text input auto-save. Long enough that normal typing
// does not generate one file write per keystroke; short enough to feel reactive.
const TEXT_DEBOUNCE_MS = 250;

// Public mount point. Called by project-cards.js for each rendered card; safely no-ops
// when the mount element is missing (e.g. empty-state card).
export async function mountAspectRatioWidget(mountElement, candidate, helpers) {
  if (!mountElement || !candidate?.path) {
    return;
  }

  // Load the current ini snapshot for this project. If the file is missing or unreadable,
  // surface the error into the activity log and render a disabled placeholder so the card
  // still renders cleanly.
  let snapshot;
  try {
    snapshot = await helpers.call("read_zelda_ini", { projectPath: candidate.path });
  } catch (error) {
    helpers.log(`zelda3.ini unavailable for ${candidate.name}: ${error}`);
    renderUnavailable(mountElement);
    return;
  }

  const state = parseAspectState(snapshot.aspect_ratio);
  state.projectPath = candidate.path;
  state.aspectLineNumber = snapshot.aspect_ratio.line_number;
  state.windowSizeLineNumber = snapshot.aspect_ratio.window_size_line;
  state.helpers = helpers;
  state.debounceHandle = null;
  state.windowSizeDebounceHandle = null;

  renderWidget(mountElement, state);
}

// Renders the read-only placeholder shown when zelda3.ini could not be loaded. The card
// still gets its Controls / Environment / Randomizer / Play buttons; only the aspect
// widget itself is greyed out.
function renderUnavailable(mountElement) {
  mountElement.innerHTML = `
    <div class="aspect-widget aspect-widget-disabled" title="zelda3.ini missing or unreadable">
      <input type="text" class="aspect-input" value="zelda3.ini missing" disabled />
    </div>
  `;
}

// Builds the entire widget DOM and wires every interactive listener. Kept in one place
// so the cluster of inputs always shares the same `state` reference.
function renderWidget(mountElement, state) {
  mountElement.innerHTML = `
    <div class="aspect-widget">
      <input type="text" class="aspect-input" value="${escapeHtml(composeValue(state))}" />
      <button type="button" class="aspect-toggle" aria-expanded="false" title="Aspect ratio options">▼</button>
      <div class="aspect-flyout" hidden>${buildFlyoutMarkup(state)}</div>
    </div>
  `;

  const input = mountElement.querySelector(".aspect-input");
  const toggle = mountElement.querySelector(".aspect-toggle");
  const flyout = mountElement.querySelector(".aspect-flyout");

  // Toggle visibility on arrow press; aria-expanded mirrors visibility for accessibility.
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    if (flyout.hasAttribute("hidden")) {
      flyout.removeAttribute("hidden");
      toggle.setAttribute("aria-expanded", "true");
    } else {
      flyout.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", "false");
    }
  });

  // Don't close the flyout when the user clicks INSIDE it; only outside clicks close.
  flyout.addEventListener("click", (event) => event.stopPropagation());

  wireInputListeners(input, mountElement, state);
  wireFlyoutListeners(mountElement, state);
}

// Reads the current state object back into the canonical text value the input shows
// AND the ini line stores. extend_y is a prefix; ratio comes next; suffix flags follow.
export function composeValue(state) {
  const tokens = [];
  if (state.extend_y) {
    tokens.push("extend_y");
  }
  tokens.push(state.ratio || "16:9");
  for (const flag of SUFFIX_FLAGS) {
    if (state[flag]) {
      tokens.push(flag);
    }
  }
  return tokens.join(", ");
}

// Splits the raw value into structured state: extend_y prefix, ratio, suffix flags.
// Whitespace and case are normalized so typed input round-trips with flyout selections.
export function parseAspectState(aspect) {
  const tokens = (aspect.raw_value || "")
    .split(",")
    .map((token) => token.trim().toLowerCase())
    .filter(Boolean);
  const state = {
    ratio: "16:9",
    extend_y: false,
    unchanged_sprites: false,
    no_visual_fixes: false,
    windowSize: aspect.window_size_value || "Auto",
  };

  // First pass: pull out the prefix flag if present so it doesn't get confused with
  // suffix flags or with the ratio token itself.
  let consumed = 0;
  if (tokens[0] === "extend_y") {
    state.extend_y = true;
    consumed = 1;
  }

  // Next token after the optional prefix should be the ratio.
  const ratioToken = tokens[consumed];
  if (ratioToken && RATIO_OPTIONS.some((option) => option.toLowerCase() === ratioToken)) {
    state.ratio = RATIO_OPTIONS.find((option) => option.toLowerCase() === ratioToken);
    consumed += 1;
  }

  // Remaining tokens are treated as suffix flags. Unknown tokens are ignored silently
  // so a typo in the ini doesn't crash the widget.
  for (const token of tokens.slice(consumed)) {
    if (SUFFIX_FLAGS.includes(token)) {
      state[token] = true;
    }
  }

  return state;
}

// Builds the flyout HTML for radio rows, flag checkboxes, and the WindowSize input.
function buildFlyoutMarkup(state) {
  const ratioRows = RATIO_OPTIONS.map(
    (option) => `
      <label class="aspect-radio-row">
        <input type="radio" name="aspect-ratio" value="${option}" ${state.ratio === option ? "checked" : ""}/>
        <span>${option}</span>
      </label>
    `,
  ).join("");

  return `
    <p class="aspect-flyout-heading">Ratio</p>
    <div class="aspect-radio-group">${ratioRows}</div>
    <p class="aspect-flyout-heading">Flags</p>
    <label class="aspect-flag-row">
      <input type="checkbox" data-flag="extend_y" ${state.extend_y ? "checked" : ""}/>
      <span>extend_y (prefix)</span>
    </label>
    <label class="aspect-flag-row">
      <input type="checkbox" data-flag="unchanged_sprites" ${state.unchanged_sprites ? "checked" : ""}/>
      <span>unchanged_sprites</span>
    </label>
    <label class="aspect-flag-row">
      <input type="checkbox" data-flag="no_visual_fixes" ${state.no_visual_fixes ? "checked" : ""}/>
      <span>no_visual_fixes</span>
    </label>
    <p class="aspect-flyout-heading">Window Size</p>
    <input type="text" class="aspect-window-size" value="${escapeHtml(state.windowSize)}" placeholder="Auto or WidthxHeight" />
  `;
}

// Wires the free-form input field. Typing debounces; the flyout re-syncs to whatever
// the user typed so radios and checkboxes stay consistent.
function wireInputListeners(input, mountElement, state) {
  input.addEventListener("input", () => {
    clearTimeout(state.debounceHandle);
    state.debounceHandle = setTimeout(() => {
      const reparsed = parseAspectState({
        raw_value: input.value,
        window_size_value: state.windowSize,
      });
      Object.assign(state, reparsed);
      syncFlyoutFromState(mountElement, state);
      saveAspectLine(state);
    }, TEXT_DEBOUNCE_MS);
  });
}

// Wires radio, checkbox, and WindowSize input listeners. Non-text inputs save instantly;
// the WindowSize text input debounces just like the main input.
function wireFlyoutListeners(mountElement, state) {
  for (const radio of mountElement.querySelectorAll('input[name="aspect-ratio"]')) {
    radio.addEventListener("change", () => {
      state.ratio = radio.value;
      mountElement.querySelector(".aspect-input").value = composeValue(state);
      saveAspectLine(state);
    });
  }

  for (const checkbox of mountElement.querySelectorAll(".aspect-flag-row input[type=checkbox]")) {
    checkbox.addEventListener("change", () => {
      const flag = checkbox.dataset.flag;
      state[flag] = checkbox.checked;
      mountElement.querySelector(".aspect-input").value = composeValue(state);
      saveAspectLine(state);
    });
  }

  const windowSize = mountElement.querySelector(".aspect-window-size");
  windowSize.addEventListener("input", () => {
    clearTimeout(state.windowSizeDebounceHandle);
    state.windowSizeDebounceHandle = setTimeout(() => {
      state.windowSize = windowSize.value;
      saveWindowSizeLine(state);
    }, TEXT_DEBOUNCE_MS);
  });
}

// Repaints the flyout radio + checkbox visual state from the in-memory state object.
function syncFlyoutFromState(mountElement, state) {
  for (const radio of mountElement.querySelectorAll('input[name="aspect-ratio"]')) {
    radio.checked = radio.value === state.ratio;
  }
  for (const checkbox of mountElement.querySelectorAll(".aspect-flag-row input[type=checkbox]")) {
    checkbox.checked = !!state[checkbox.dataset.flag];
  }
}

// Writes the composed ExtendedAspectRatio line back to zelda3.ini.
async function saveAspectLine(state) {
  if (!state.aspectLineNumber) {
    return;
  }
  const rawLine = `ExtendedAspectRatio = ${composeValue(state)}`;
  await state.helpers.call("update_zelda_ini_line", {
    projectPath: state.projectPath,
    lineNumber: state.aspectLineNumber,
    rawLine,
  });
}

// Writes the WindowSize line back to zelda3.ini. Empty values default to "Auto" so the
// game still starts even if the user clears the field by accident.
async function saveWindowSizeLine(state) {
  if (!state.windowSizeLineNumber) {
    return;
  }
  const value = state.windowSize.trim() || "Auto";
  const rawLine = `WindowSize = ${value}`;
  await state.helpers.call("update_zelda_ini_line", {
    projectPath: state.projectPath,
    lineNumber: state.windowSizeLineNumber,
    rawLine,
  });
}
