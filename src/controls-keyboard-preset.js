// Owns the "Keyboard Layout" dropdown at the top of the KeyMap tab. The zelda3.ini ships
// with three Controls = ... lines (QWERTY, QWERTZ, AZERTY) where exactly one is meant to
// be uncommented at a time. The dropdown picks the active preset; whichever option is
// selected ends up uncommented and the other two get commented.
//
// With the controller overlay handling per-button rebinding directly on the image, this
// module no longer renders an editable text input for the 12-key value — only the
// layout dropdown plus a small "active preset" pill stays here. The overlay binds to
// the active preset's IniLineSnapshot and writes individual slot updates itself.

// Imports: shared HTML escape util for safe rendering of the layout label strings.
import { escapeHtml } from "./shared-utils.js";

// The three keyboard layouts the upstream ini documents. Order matches the dropdown.
const LAYOUT_LABELS = ["QWERTY", "QWERTZ", "AZERTY"];

// Public render entry point. controlsLines is the ordered list of [KeyMap] lines whose
// key is "Controls" — typically three rows; renderer tolerates fewer if a fork removed
// one. onActiveChange is invoked with the IniLineSnapshot of the newly-active preset
// whenever the user switches layout (after the comment/uncomment writes complete).
export function renderKeyboardPresetSection(container, controlsLines, helpers, onActiveChange) {
  if (controlsLines.length === 0) {
    return null;
  }

  // Snapshot each layout slot to its current line. The dropdown stores the index into
  // this list as its <option> value so the change handler can look up either side of
  // the swap by integer index.
  const presets = controlsLines.map((line, index) => ({
    label: LAYOUT_LABELS[index] ?? `Layout ${index + 1}`,
    line,
  }));

  // Active preset = the first uncommented line. Falls back to index 0 when none of the
  // three are uncommented; the user can then enable one explicitly via the dropdown.
  const initialActive = Math.max(0, presets.findIndex((preset) => !preset.line.commented));

  const section = document.createElement("div");
  section.className = "controls-keyboard-preset";
  section.innerHTML = buildPresetMarkup(presets, initialActive);
  container.append(section);

  wirePresetSection(section, presets, initialActive, helpers, onActiveChange);
  // Immediately surface the initial active preset so the caller can render the overlay
  // against it without waiting for the user to interact with the dropdown.
  if (onActiveChange) {
    onActiveChange(presets[initialActive].line);
  }
  return presets[initialActive].line;
}

// Builds the dropdown markup. The Controls text input that used to live here is gone —
// the controller overlay is now the editor for the 12 button bindings.
function buildPresetMarkup(presets, activeIndex) {
  const options = presets
    .map(
      (preset, index) => `
        <option value="${index}" ${index === activeIndex ? "selected" : ""}>
          ${escapeHtml(preset.label)}
        </option>
      `,
    )
    .join("");

  return `
    <label class="controls-keyboard-label">
      <span>Keyboard Layout</span>
      <select class="controls-keyboard-select">${options}</select>
    </label>
  `;
}

// Wires the dropdown change handler. Switching presets writes both the previously-active
// and newly-active line back to the ini (commented / uncommented flip), then notifies
// the caller so the controller overlay can re-render against the new active line.
function wirePresetSection(section, presets, activeIndex, helpers, onActiveChange) {
  const select = section.querySelector(".controls-keyboard-select");
  const state = { activeIndex };

  select.addEventListener("change", async () => {
    const newIndex = Number.parseInt(select.value, 10);
    if (Number.isNaN(newIndex) || !presets[newIndex]) {
      return;
    }

    const previous = presets[state.activeIndex];
    const next = presets[newIndex];

    // Flip comment-state in memory first so the overlay can re-render immediately, then
    // write both lines back. Writes happen sequentially because the backend touches one
    // file lock at a time.
    previous.line.commented = true;
    next.line.commented = false;
    state.activeIndex = newIndex;

    await writePresetLine(previous.line, helpers);
    await writePresetLine(next.line, helpers);

    if (onActiveChange) {
      onActiveChange(next.line);
    }
  });
}

// Writes one preset line back to its zelda3.ini slot, preserving its current value and
// the comment state we just toggled. The value text is never modified here — that lives
// inside the controller overlay.
async function writePresetLine(line, helpers) {
  const body = `Controls = ${line.value}`;
  const rawLine = line.commented ? `#${body}` : body;
  await helpers.call("update_zelda_ini_line", {
    projectPath: helpers.state.selectedPath,
    lineNumber: line.line_number,
    rawLine,
  });
}
