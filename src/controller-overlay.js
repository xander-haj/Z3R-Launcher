// Renders the SNES controller image with 12 overlay labels showing the current binding
// for each button (D-pad x4, Select, Start, A/B/X/Y, L, R). Used by both Controls tabs:
//   * KeyMap mode: clicking a label arms keypress capture; the next key press becomes
//     the new binding for that slot.
//   * Gamepad mode: clicking a label swaps it for an inline text input the user types
//     into (capture-on-press cannot reliably distinguish gamepad buttons in a browser
//     without polling the Gamepad API, so we stay with text edit for those bindings).

// Imports: shared escape util and the key-capture translation helper.
import { escapeHtml } from "./shared-utils.js";
import { captureKeyName } from "./key-capture.js";

// Cached positions JSON so we don't re-fetch on every render. fetch() is awaited on the
// first call; subsequent renders re-use the resolved structure.
let positionsCache = null;

// Public entry point. container is the tab panel element to render into; mode is
// "keymap" | "gamepad"; controlsLine is the IniLineSnapshot for the active Controls=
// line; helpers carries state + the backend invoker.
export async function renderControllerOverlay(container, mode, controlsLine, helpers) {
  const positions = await loadPositions(helpers);
  if (!positions) {
    container.innerHTML = `<p class="controls-empty">Controller image positions unavailable.</p>`;
    return;
  }

  // Split the active Controls = "Up, Down, ..." value into 12 slots. Missing slots
  // (e.g. a fork that truncated the line) render as empty labels so the overlay
  // doesn't crash — the user can still click to set them.
  const slots = (controlsLine?.value ?? "")
    .split(",")
    .map((part) => part.trim());
  while (slots.length < positions.buttons.length) {
    slots.push("");
  }

  const frame = document.createElement("div");
  // Per-mode class lets the CSS relax the label max-width on the Gamepad tab where
  // labels like "DpadRight" have no whitespace to wrap on and would otherwise overflow
  // the background. KeyMap keeps the tighter max-width so "Right Shift" still stacks.
  frame.className = `controller-frame controller-frame-${mode}`;
  frame.innerHTML = `<img src="${escapeHtml(positions.image)}" alt="SNES controller" class="controller-image" />`;

  positions.buttons.forEach((button, index) => {
    const label = createOverlayLabel(button, slots[index], index);
    label.addEventListener("click", (event) => {
      event.stopPropagation();
      beginEdit({ label, mode, controlsLine, slots, index, helpers });
    });
    frame.append(label);
  });

  container.append(frame);
}

// Builds one absolutely positioned label. `button` is the position config entry,
// `binding` is the current value to display, `index` is the slot in the Controls= list.
function createOverlayLabel(button, binding, index) {
  const label = document.createElement("button");
  label.type = "button";
  label.className = "controller-button-label";
  label.style.top = button.top;
  label.style.left = button.left;
  label.dataset.buttonId = button.id;
  label.dataset.index = String(index);
  label.title = `${button.displayName} (click to rebind)`;
  label.textContent = binding || "—";
  return label;
}

// Entry point for editing one slot. Routes to capture mode or inline input mode based
// on which tab the overlay was rendered into.
function beginEdit(context) {
  if (context.mode === "keymap") {
    beginKeyCapture(context);
  } else {
    beginInlineEdit(context);
  }
}

// Arms a one-shot keydown listener so the next non-modifier press becomes the new
// binding for this slot. Escape cancels without writing. Clicks outside the label also
// cancel so the screen doesn't get stuck in listening mode.
function beginKeyCapture(context) {
  const { label } = context;
  label.classList.add("listening");
  const originalText = label.textContent;
  label.textContent = "Press a key";

  const cleanup = () => {
    label.classList.remove("listening");
    window.removeEventListener("keydown", onKeydown, true);
    window.removeEventListener("mousedown", onOutsideClick, true);
  };

  const onKeydown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      label.textContent = originalText;
      cleanup();
      return;
    }
    const captured = captureKeyName(event);
    if (!captured) {
      // Bare modifier press: stay armed.
      return;
    }
    event.preventDefault();
    cleanup();
    commitSlotValue(context, captured);
  };

  const onOutsideClick = (event) => {
    if (event.target !== label) {
      label.textContent = originalText;
      cleanup();
    }
  };

  // capture=true so the listener fires before any other key handler on the page.
  window.addEventListener("keydown", onKeydown, true);
  window.addEventListener("mousedown", onOutsideClick, true);
}

// Inline edit path used by the Gamepad tab. Swaps the label for a small text input;
// Enter commits, Escape reverts.
function beginInlineEdit(context) {
  const { label, slots, index } = context;
  const input = document.createElement("input");
  input.type = "text";
  input.value = slots[index] ?? "";
  input.className = "controller-button-input";
  input.style.top = label.style.top;
  input.style.left = label.style.left;
  label.replaceWith(input);
  input.focus();
  input.select();

  const cancel = () => {
    input.replaceWith(label);
  };

  input.addEventListener("blur", () => {
    commitInline(context, input);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitInline(context, input);
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
  });
}

// Commit helper for the Gamepad inline editor. Restores the label DOM and writes the
// new value to the ini.
function commitInline(context, input) {
  const value = input.value.trim();
  if (!input.isConnected) {
    return;
  }
  input.replaceWith(context.label);
  context.label.textContent = value || "—";
  commitSlotValue(context, value);
}

// Shared write path used by both edit modes. Updates the slot in the cached 12-value
// array, recomposes the full Controls = line, and writes it back to zelda3.ini via the
// existing line-number-addressed backend command.
async function commitSlotValue(context, newValue) {
  const { slots, index, label, controlsLine, helpers } = context;
  slots[index] = newValue;
  label.textContent = newValue || "—";

  const body = `Controls = ${slots.join(", ")}`;
  const rawLine = controlsLine.commented ? `#${body}` : body;
  await helpers.call("update_zelda_ini_line", {
    projectPath: helpers.state.selectedPath,
    lineNumber: controlsLine.line_number,
    rawLine,
  });
}

// Loads controls-button-positions.json on demand and caches the result. Returns null on
// any fetch / parse error so the caller can render a graceful fallback.
async function loadPositions(helpers) {
  if (positionsCache) {
    return positionsCache;
  }
  try {
    const response = await fetch("./controls-button-positions.json");
    positionsCache = await response.json();
  } catch (error) {
    helpers.log(`Could not load controls-button-positions.json: ${error}`);
    positionsCache = null;
  }
  return positionsCache;
}
