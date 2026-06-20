// Link Sprite Editor screen. Edits the armor/gloves palette override consumed by
// assets/compile_resources.py, then asks the backend to rebuild zelda3_assets.dat
// with assets/restool.py without extracting fresh ROM assets over the edit.

import { createSpriteBrowserHost } from "./browser-host.js";
import { createLinkSpritePreview } from "./preview.js";
import { renderSpriteSelector } from "./sprite-selector.js";

const EMPTY_MESSAGE = "Select or clone a Z3R folder before opening Link Sprite.";
const UNAVAILABLE_MESSAGE = "Link sprite palette editing is unavailable for this project.";
const HEX_PATTERN = /^[0-9a-f]{1,4}$/i;
// Palette entries are stored as uint16 words so existing sprite_sheets.py values such as FEB9 survive a save.
const MAX_SNES_PALETTE_WORD = 0xffff;
// Browser colors use the SNES BGR555 payload; bit 15 is storage-only and ignored by CGRAM color decoding.
const SNES_COLOR_MASK = 0x7fff;

// Connects the screen to app-wide helpers and exposes a refresh hook for main.js.
export function connectLinkSpriteEditor(helpers) {
  const refs = collectScreenElements();

  return {
    async refresh() {
      await refreshLinkSpriteEditor(refs, helpers);
    },
  };
}

// Collects DOM nodes owned by the Link Sprite screen.
function collectScreenElements() {
  return {
    title: document.querySelector("#linkSpriteTitle"),
    author: document.querySelector("#linkSpriteAuthor"),
    content: document.querySelector("#linkSpriteContent"),
    preview: null,
  };
}

// Loads the selected project's palette snapshot and renders the editor controls.
async function refreshLinkSpriteEditor(refs, helpers) {
  refs.preview?.destroy();
  refs.preview = null;
  refs.content.textContent = "";

  if (!helpers.state.selectedPath) {
    setHeading(refs, null);
    refs.content.append(emptyMessage(EMPTY_MESSAGE));
    return;
  }

  const candidate = helpers.state.candidates.find((entry) => entry.path === helpers.state.selectedPath);
  setHeading(refs, candidate);

  try {
    const snapshot = await helpers.call("read_link_sprite_palette", {
      projectPath: helpers.state.selectedPath,
    });
    const browser = createSpriteBrowserHost();
    await renderSpriteSelector(refs.content, helpers, () => refreshLinkSpriteEditor(refs, helpers), browser);
    refs.content.append(browser.host);
    const editor = renderEditor(refs, snapshot, helpers);
    browser.attachEditor(editor);
    refs.content.append(editor);
  } catch (error) {
    helpers.log(`Could not read Link sprite palette: ${error}`);
    refs.content.append(emptyMessage(UNAVAILABLE_MESSAGE));
  }
}

// Mirrors the selected project card so users can confirm which checkout is being edited.
function setHeading(refs, candidate) {
  if (!candidate) {
    refs.title.textContent = "Link Sprite";
    refs.author.textContent = "";
    return;
  }

  refs.title.textContent = candidate.name;
  refs.author.textContent = candidate.owner ? `by ${candidate.owner}` : "";
}

// Renders status, palette rows, and save/build controls for one palette snapshot.
function renderEditor(refs, snapshot, helpers) {
  const editorState = {
    values: [...snapshot.values],
    active: Boolean(snapshot.active),
    source: snapshot.palette_source ?? "",
    dirty: false,
    busy: false,
  };
  const editor = document.createElement("section");
  editor.className = "link-sprite-editor";
  editor.innerHTML = `
    <div class="link-sprite-editor-heading">
      <div class="link-sprite-editor-meta">
        <h3>Palette Editor</h3>
        <span class="link-sprite-state"></span>
      </div>
      <button class="secondary-button link-sprite-reload" type="button">Reload</button>
    </div>
    <p class="path-line link-sprite-path"></p>
    <p class="path-line link-sprite-palette-source"></p>
    <p class="link-sprite-preview-status">Loading sprite preview...</p>
    <div class="link-palette-grid"></div>
    <div class="link-sprite-actions">
      <button class="primary-button link-sprite-save" type="button">Save palette</button>
      <button class="secondary-button link-sprite-disable" type="button">Disable override</button>
      <button class="secondary-button link-sprite-build" type="button">Build asset file</button>
    </div>
    <p class="link-sprite-status"></p>
  `;

  const statePill = editor.querySelector(".link-sprite-state");
  const status = editor.querySelector(".link-sprite-status");
  const previewStatus = editor.querySelector(".link-sprite-preview-status");
  editor.querySelector(".link-sprite-path").textContent = snapshot.path;
  editor.querySelector(".link-sprite-palette-source").textContent = paletteSourceText(snapshot);
  const preview = createLinkSpritePreview(snapshot, editorState, previewStatus);
  editorState.preview = preview;
  refs.preview = preview;
  appendPaletteRows(editor.querySelector(".link-palette-grid"), snapshot, editorState, status, preview);
  const controls = collectEditorControls(editor);
  updateActiveState(statePill, editorState.active, editorState.source);
  wireEditorActions(controls, refs, helpers, editorState, status, statePill);
  preview.load(helpers).catch((error) => {
    helpers.log(`Could not load Link sprite preview: ${error}`);
  });
  return editor;
}

// Finds action buttons after the editor shell has been created.
function collectEditorControls(editor) {
  return {
    reload: editor.querySelector(".link-sprite-reload"),
    save: editor.querySelector(".link-sprite-save"),
    disable: editor.querySelector(".link-sprite-disable"),
    build: editor.querySelector(".link-sprite-build"),
    all: Array.from(editor.querySelectorAll("button, input, select")),
    editor,
  };
}

// Adds one editable row for each armor/effect palette returned by the backend.
function appendPaletteRows(container, snapshot, editorState, status, preview) {
  for (const row of snapshot.rows) {
    const section = document.createElement("section");
    section.className = "link-palette-row";
    section.innerHTML = `
      <h4>${row.label}</h4>
      <div class="link-palette-row-body">
        <div class="link-palette-cells"></div>
        <div class="link-sprite-row-preview"></div>
      </div>
    `;
    const cells = section.querySelector(".link-palette-cells");
    const previewSlot = section.querySelector(".link-sprite-row-preview");

    for (let offset = 0; offset < snapshot.row_length; offset += 1) {
      const index = row.start + offset;
      cells.append(buildPaletteCell(index, row.label, editorState, status));
    }

    preview.attachRow(row, previewSlot);
    container.append(section);
  }
}

// Builds one color swatch plus SNES hex editor cell.
function buildPaletteCell(index, rowLabel, editorState, status) {
  const cell = document.createElement("label");
  const displayIndex = String((index % 15) + 1).padStart(2, "0");
  cell.className = "link-palette-cell";
  cell.innerHTML = `<span>${displayIndex}</span>`;

  const color = document.createElement("input");
  color.type = "color";
  color.value = snesToCssHex(editorState.values[index]);
  color.setAttribute("aria-label", `${rowLabel} color ${displayIndex}`);

  const hex = document.createElement("input");
  hex.className = "link-palette-hex";
  hex.type = "text";
  hex.inputMode = "text";
  hex.maxLength = 4;
  hex.value = formatSnesHex(editorState.values[index]);
  hex.setAttribute("aria-label", `${rowLabel} color ${displayIndex} SNES hex`);

  color.addEventListener("input", () => {
    updatePaletteValue(index, cssHexToSnes(color.value), color, hex, editorState, status);
  });
  hex.addEventListener("input", () => {
    const parsed = parseSnesHex(hex.value);
    hex.classList.toggle("invalid", parsed === null);

    if (parsed !== null) {
      updatePaletteValue(index, parsed, color, hex, editorState, status, false);
    }
  });
  hex.addEventListener("blur", () => {
    if (!hex.classList.contains("invalid")) {
      hex.value = formatSnesHex(editorState.values[index]);
    }
  });

  cell.append(color, hex);
  return cell;
}

// Saves the changed value into state and keeps the color and hex inputs synchronized.
function updatePaletteValue(index, value, color, hex, editorState, status, formatHex = true) {
  editorState.values[index] = value;
  color.value = snesToCssHex(value);

  if (formatHex) {
    hex.value = formatSnesHex(value);
  }

  hex.classList.remove("invalid");
  editorState.preview?.render();
  editorState.dirty = true;
  status.textContent = "Unsaved palette changes.";
  status.className = "link-sprite-status warning";
}

// Wires reload, save, disable, and build actions to backend commands.
function wireEditorActions(controls, refs, helpers, editorState, status, statePill) {
  controls.reload.addEventListener("click", () => refreshLinkSpriteEditor(refs, helpers));
  controls.save.addEventListener("click", async () => {
    await savePalette(controls, helpers, editorState, status, statePill, true);
  });
  controls.disable.addEventListener("click", async () => {
    await savePalette(controls, helpers, editorState, status, statePill, false);
  });
  controls.build.addEventListener("click", async () => {
    if (hasInvalidHex(controls.editor)) {
      showActionStatus(status, "Fix invalid SNES hex values before building.", "error");
      return;
    }

    await withBusyControls(controls, editorState, async () => {
      if (editorState.dirty) {
        await savePalette(controls, helpers, editorState, status, statePill, true, false);
      }

      const result = await helpers.call("build_link_sprite_assets", {
        projectPath: helpers.state.selectedPath,
      });
      helpers.log(result.message);
      showActionStatus(status, result.message, result.ok ? "success" : "error");
    });
  });
}

// Persists the palette override block and updates local state from the backend snapshot.
async function savePalette(controls, helpers, editorState, status, statePill, active, manageBusy = true) {
  if (hasInvalidHex(controls.editor)) {
    showActionStatus(status, "Fix invalid SNES hex values before saving.", "error");
    return;
  }

  const action = async () => {
    const snapshot = await helpers.call("save_link_sprite_palette", {
      projectPath: helpers.state.selectedPath,
      values: editorState.values,
      active,
    });
    editorState.values = [...snapshot.values];
    editorState.active = Boolean(snapshot.active);
    editorState.source = snapshot.palette_source ?? "";
    editorState.dirty = false;
    updateActiveState(statePill, editorState.active, editorState.source);
    helpers.log(snapshot.message);
    showActionStatus(status, snapshot.message, "success");
  };

  if (manageBusy) {
    await withBusyControls(controls, editorState, action);
  } else {
    await action();
  }
}

// Disables every editor control while an async backend command is in flight.
async function withBusyControls(controls, editorState, action) {
  editorState.busy = true;
  setControlsDisabled(controls.all, true);

  try {
    await action();
  } finally {
    editorState.busy = false;
    setControlsDisabled(controls.all, false);
    editorState.preview?.syncControls?.();
  }
}

// Toggles disabled state for a group of controls.
function setControlsDisabled(controls, disabled) {
  for (const control of controls) {
    control.disabled = disabled;
  }
}

// Updates the active/disabled status pill shown above the palette grid.
function updateActiveState(node, active, source = "") {
  const usesZspr = source === "zspr";
  node.className = `link-sprite-state ${active || usesZspr ? "active" : "disabled"}`;
  node.textContent = usesZspr ? "ZSPR palette" : (active ? "Override active" : "Override disabled");
}

function paletteSourceText(snapshot) {
  if (snapshot.palette_source === "zspr") {
    return `Palette source: selected ZSPR (${snapshot.palette_source_path})`;
  }
  if (snapshot.palette_source_error) {
    return snapshot.palette_source_error;
  }
  return `Palette source: ${snapshot.active ? "assets override" : "asset defaults"}`;
}

// Shows a compact action result under the editor buttons.
function showActionStatus(status, message, tone) {
  status.textContent = message;
  status.className = `link-sprite-status ${tone}`;
}

// Reports whether any visible SNES hex input is currently invalid.
function hasInvalidHex(editor) {
  return Boolean(editor.querySelector(".link-palette-hex.invalid"));
}

// Builds a plain empty-state paragraph used when no selected project/editor is available.
function emptyMessage(message) {
  const node = document.createElement("p");
  node.className = "features-empty";
  node.textContent = message;
  return node;
}

// Converts a SNES palette word into a browser #RRGGBB value.
function snesToCssHex(word) {
  const colorWord = word & SNES_COLOR_MASK;
  const red = snesChannelToByte(colorWord & 0x1f);
  const green = snesChannelToByte((colorWord >> 5) & 0x1f);
  const blue = snesChannelToByte((colorWord >> 10) & 0x1f);
  return `#${byteToHex(red)}${byteToHex(green)}${byteToHex(blue)}`;
}

// Converts a browser #RRGGBB color into a SNES BGR555 word with the unused high bit clear.
function cssHexToSnes(value) {
  const red = cssChannelToSnes(value.slice(1, 3));
  const green = cssChannelToSnes(value.slice(3, 5));
  const blue = cssChannelToSnes(value.slice(5, 7));
  return red | (green << 5) | (blue << 10);
}

// Expands one 5-bit SNES color channel to 8-bit using bit replication.
function snesChannelToByte(value) {
  return (value << 3) | (value >> 2);
}

// Quantizes one two-digit CSS hex channel down to SNES 5-bit precision.
function cssChannelToSnes(hex) {
  return Math.round((Number.parseInt(hex, 16) * 31) / 255);
}

// Formats an 8-bit channel as two uppercase hex digits.
function byteToHex(value) {
  return value.toString(16).padStart(2, "0").toUpperCase();
}

// Formats a SNES palette word as the four-digit hex value users expect from sprite_sheets.py.
function formatSnesHex(value) {
  return value.toString(16).padStart(4, "0").toUpperCase();
}

// Parses a 1-4 digit SNES palette word and rejects values outside the uint16 range.
function parseSnesHex(value) {
  const cleaned = value.trim().replace(/^0x/i, "");

  if (!HEX_PATTERN.test(cleaned)) {
    return null;
  }

  const parsed = Number.parseInt(cleaned, 16);
  return parsed <= MAX_SNES_PALETTE_WORD ? parsed : null;
}
