// Reusable row renderer for the Controls screen. Each row pairs an "enable" checkbox
// (toggles the leading "#" comment in the ini line) with an editable text input. When
// the checkbox is off the row appears greyed out and collapsed, and the line in the
// ini becomes commented; when on the row expands and the input is editable.
//
// This module knows NOTHING about which tab it is rendering into. Callers (the KeyMap
// and Gamepad tab builders inside controls-screen.js) just pass the IniLineSnapshot
// records and a backend-call helper.

// Imports: shared HTML escape util.
import { escapeHtml } from "./shared-utils.js";

// Debounce window for free-form text input auto-save. Matches the aspect ratio widget's
// value so the launcher's edit cadence is consistent across screens.
const TEXT_DEBOUNCE_MS = 250;

// Builds a single editable row and appends it to `container`. lineSnapshot carries the
// 1-based line_number, the parsed key, value, and commented state. helpers is the same
// shared object every screen module receives.
export function appendControlsRow(container, lineSnapshot, helpers) {
  const row = document.createElement("div");
  row.className = `controls-row ${lineSnapshot.commented ? "controls-row-disabled" : ""}`;

  row.innerHTML = `
    <label class="controls-toggle">
      <input type="checkbox" ${lineSnapshot.commented ? "" : "checked"} />
      <span></span>
    </label>
    <span class="controls-label">${escapeHtml(lineSnapshot.key)}</span>
    <input
      type="text"
      class="controls-value"
      value="${escapeHtml(lineSnapshot.value)}"
      ${lineSnapshot.commented ? "disabled" : ""}
    />
  `;

  const checkbox = row.querySelector(".controls-toggle input");
  const valueInput = row.querySelector(".controls-value");

  // State that survives across edits in this row.
  const localState = {
    lineNumber: lineSnapshot.line_number,
    key: lineSnapshot.key,
    value: lineSnapshot.value,
    commented: lineSnapshot.commented,
    debounceHandle: null,
  };

  wireRowToggle(row, checkbox, valueInput, localState, helpers);
  wireRowValue(valueInput, localState, helpers);

  container.append(row);
  return row;
}

// Checkbox flip toggles the leading "#" comment and re-enables/greys out the input.
// Writes immediately (no debounce) because toggling is a discrete action, not typing.
function wireRowToggle(row, checkbox, valueInput, localState, helpers) {
  checkbox.addEventListener("change", () => {
    localState.commented = !checkbox.checked;
    valueInput.disabled = localState.commented;
    row.classList.toggle("controls-row-disabled", localState.commented);
    saveControlsRow(localState, helpers);
  });
}

// Free-form text edits debounce 250ms after the last keystroke so rapid typing does
// not generate one file write per character. Edits made while the row is greyed out
// (commented) are ignored because the input is also `disabled` in that state.
function wireRowValue(valueInput, localState, helpers) {
  valueInput.addEventListener("input", () => {
    localState.value = valueInput.value;
    clearTimeout(localState.debounceHandle);
    localState.debounceHandle = setTimeout(() => {
      saveControlsRow(localState, helpers);
    }, TEXT_DEBOUNCE_MS);
  });
}

// Composes the replacement ini line from the row's current state and writes it back
// via the backend's line-number addressed update command.
export async function saveControlsRow(localState, helpers) {
  const body = `${localState.key} = ${localState.value}`;
  const rawLine = localState.commented ? `#${body}` : body;
  await helpers.call("update_zelda_ini_line", {
    projectPath: helpers.state.selectedPath,
    lineNumber: localState.lineNumber,
    rawLine,
  });
}
