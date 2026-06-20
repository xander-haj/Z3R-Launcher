// Features screen orchestrator. Loads the selected project's zelda3.ini snapshot,
// lists optional shared assets, and writes boot-time settings before the game starts.

// Imports: shared escaping for headings and option labels fed by filesystem/repo names.
import { escapeHtml } from "./shared-utils.js";
import { appendOptionPicker } from "./features-picker.js";
import { appendSpritePreview } from "./features-sprite-preview.js";

// Stable zelda3.ini keys owned by this screen.
const REARRANGE_HUD_KEY = "RearrangeHUD";
const LINK_GRAPHICS_KEY = "LinkGraphics";
const SHADER_KEY = "Shader";
const ENABLE_MSU_KEY = "EnableMSU";
const MSU_PATH_KEY = "MSUPath";

// Public connector. Exposes a refresh method so main.js can repaint the screen whenever
// the selected project changes or the user navigates into the Features view.
export function connectFeaturesScreen(helpers) {
  const refs = collectScreenElements();

  return {
    async refresh() {
      await refreshFeaturesContent(refs, helpers);
    },
  };
}

// Collects the DOM nodes this screen owns. One-time lookup keeps refresh work cheap.
function collectScreenElements() {
  return {
    title: document.querySelector("#featuresTitle"),
    author: document.querySelector("#featuresAuthor"),
    content: document.querySelector("#featuresContent"),
  };
}

// Reads zelda3.ini plus shared asset availability and renders controls for the selected project.
async function refreshFeaturesContent(refs, helpers) {
  refs.content.textContent = "";

  if (!helpers.state.selectedPath) {
    setHeading(refs, null);
    refs.content.innerHTML = `<p class="features-empty">Select or clone a Z3R folder before opening Features.</p>`;
    return;
  }

  const candidate = helpers.state.candidates.find(
    (entry) => entry.path === helpers.state.selectedPath,
  );

  try {
    const [snapshot, assets] = await Promise.all([
      helpers.call("read_zelda_ini", { projectPath: helpers.state.selectedPath }),
      helpers.call("read_feature_assets", { projectPath: helpers.state.selectedPath }),
    ]);
    setHeading(refs, candidate);
    renderFeatures(refs, snapshot, assets, helpers);
  } catch (error) {
    helpers.log(`Could not read feature settings: ${error}`);
    setHeading(refs, candidate);
    refs.content.innerHTML = `<p class="features-empty">Feature settings are unavailable.</p>`;
  }
}

// Mirrors card heading text so users can tell which discovered project is being edited.
function setHeading(refs, candidate) {
  if (!candidate) {
    refs.title.textContent = "Features";
    refs.author.textContent = "";
    return;
  }

  refs.title.textContent = candidate.name;
  refs.author.textContent = candidate.owner ? `by ${candidate.owner}` : "";
}

// Renders the full Features surface from the current snapshot and asset report.
function renderFeatures(refs, snapshot, assets, helpers) {
  refs.content.textContent = "";
  renderRearrangeHudToggle(refs.content, snapshot, helpers);
  renderMsuSection(refs, snapshot, assets, helpers);
  renderSelectableAssetSection(refs, snapshot, assets, helpers, {
    title: "Link sprite",
    kind: "sprites",
    lineKey: LINK_GRAPHICS_KEY,
    section: "Graphics",
    lines: snapshot.graphics_lines,
    group: assets.sprites,
    sourceUrl: assets.sprites_source_url,
    cloneLabel: "Clone sprites",
    applyLabel: "Use sprite",
  });
  renderSelectableAssetSection(refs, snapshot, assets, helpers, {
    title: "Shader",
    kind: "shaders",
    lineKey: SHADER_KEY,
    section: "Graphics",
    lines: snapshot.graphics_lines,
    group: assets.shaders,
    sourceUrl: assets.shaders_source_url,
    cloneLabel: "Clone shaders",
    applyLabel: "Use shader",
  });
}

// Renders the boot-time RearrangeHUD ini boolean.
function renderRearrangeHudToggle(container, snapshot, helpers) {
  const featureLine = findLine(snapshot.feature_lines, REARRANGE_HUD_KEY);

  if (!featureLine) {
    appendUnavailable(container, `${REARRANGE_HUD_KEY} was not found in zelda3.ini.`);
    return;
  }

  const enabled = isIniTruthy(featureLine.value) && !featureLine.commented;
  const row = document.createElement("label");
  row.className = "features-toggle-row";
  row.innerHTML = `
    <input class="features-checkbox" type="checkbox" ${enabled ? "checked" : ""} />
    <span class="features-toggle-copy">
      <span class="features-toggle-label">Rearrange HUD</span>
      <span class="features-toggle-state">${enabled ? "Enabled" : "Disabled"}</span>
    </span>
  `;

  const checkbox = row.querySelector(".features-checkbox");
  const state = row.querySelector(".features-toggle-state");
  checkbox.addEventListener("change", async () => {
    await saveCheckboxLine(featureLine, checkbox, state, helpers);
  });

  container.append(row);
}

// Renders MSU availability, download/import actions, and the selected pack installer.
function renderMsuSection(refs, snapshot, assets, helpers) {
  const enableLine = findLine(snapshot.sound_lines, ENABLE_MSU_KEY);
  const pathLine = findLine(snapshot.sound_lines, MSU_PATH_KEY);
  const section = buildAssetSection("Audio MSU", assets.msu);
  const actionRow = appendActionRow(section);

  appendLinkButton(actionRow, "MSU Downloads", assets.msu_download_url, helpers);
  appendButton(actionRow, "Import MSU Folder", async () => {
    const result = await helpers.call("choose_and_store_msu");
    if (result) {
      helpers.log(result.message);
      await refreshFeaturesContent(refs, helpers);
    }
  });
  appendMsuDropZone(section, refs, helpers);

  if (assets.msu.options.length > 0 && enableLine && pathLine) {
    appendOptionPicker(
      section,
      assets.msu.options,
      "Use MSU",
      async (value) => {
        const result = await installAsset("msu", value, helpers);
        const [msuPath, mode = "true"] = splitInstallOutput(result.stdout);
        await saveIniValue(pathLine, msuPath, helpers);
        await saveIniValue(enableLine, mode, helpers);
        helpers.log(result.message);
        await refreshFeaturesContent(refs, helpers);
      },
      pathLine.value,
    );
  } else if (assets.msu.options.length > 0) {
    appendUnavailable(section, `${ENABLE_MSU_KEY} or ${MSU_PATH_KEY} was not found in zelda3.ini.`);
  } else {
    appendUnavailable(section, "No MSU packs found in shared storage or the selected build.");
  }

  refs.content.append(section);
}

// Renders clone/source controls plus dropdown installer for sprite and shader repositories.
function renderSelectableAssetSection(refs, snapshot, assets, helpers, config) {
  const line = findLine(config.lines, config.lineKey);
  const section = buildAssetSection(config.title, config.group);
  const actionRow = appendActionRow(section);

  appendLinkButton(actionRow, "Source", config.sourceUrl, helpers);
  if (!config.group.shared_available) {
    appendButton(actionRow, config.cloneLabel, async () => {
      const result = await helpers.call("clone_feature_asset", { assetKind: config.kind });
      helpers.log(result.message);
      await refreshFeaturesContent(refs, helpers);
    });
  }

  if (config.group.options.length > 0) {
    const picker = appendOptionPicker(
      section,
      config.group.options,
      config.applyLabel,
      async (value) => {
        const result = await installAsset(config.kind, value, helpers);
        const [assetPath] = splitInstallOutput(result.stdout);
        await saveIniValue(line, assetPath, helpers, {
          section: config.section,
          key: config.lineKey,
        });
        helpers.log(result.message);
        await refreshFeaturesContent(refs, helpers);
      },
      line?.value ?? "",
    );

    if (config.kind === "sprites") {
      appendSpritePreview(section, picker, helpers);
    }

    if (!line) {
      appendUnavailable(section, `${config.lineKey} will be created in zelda3.ini when applied.`);
    }
  } else {
    appendUnavailable(section, `No ${config.title.toLowerCase()} options found.`);
  }

  refs.content.append(section);
}

// Creates a section shell with an availability status line.
function buildAssetSection(title, group) {
  const section = document.createElement("section");
  section.className = "features-asset-section";
  section.innerHTML = `
    <div class="features-asset-heading">
      <h3>${escapeHtml(title)}</h3>
      <span class="features-asset-status ${group.available ? "available" : "missing"}">
        ${group.available ? "Available" : "Not available"}
      </span>
    </div>
  `;
  return section;
}

// Appends a row that holds source/import/clone buttons.
function appendActionRow(section) {
  const row = document.createElement("div");
  row.className = "features-action-row";
  section.append(row);
  return row;
}

// Appends a normal action button.
function appendButton(row, label, onClick) {
  const button = document.createElement("button");
  button.className = "secondary-button";
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await onClick();
    } finally {
      button.disabled = false;
    }
  });
  row.append(button);
}

// Appends an external-link button through the backend opener.
function appendLinkButton(row, label, url, helpers) {
  appendButton(row, label, async () => {
    await helpers.openExternalUrl(url);
  });
}

// Adds a drag/drop area for extracted MSU files when the WebView exposes file paths.
function appendMsuDropZone(section, refs, helpers) {
  const zone = document.createElement("div");
  zone.className = "features-drop-zone";
  zone.textContent = "Drop MSU folder or files";
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("active");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("active"));
  zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    zone.classList.remove("active");
    const paths = Array.from(event.dataTransfer?.files ?? [])
      .map((file) => file.path)
      .filter(Boolean);

    if (paths.length === 0) {
      helpers.log("Dropped MSU files did not expose local paths. Use Import MSU Folder instead.");
      return;
    }

    const result = await helpers.call("store_msu_paths", { paths });
    helpers.log(result.message);
    await refreshFeaturesContent(refs, helpers);
  });
  section.append(zone);
}

// Calls the backend installer for a selected asset.
async function installAsset(assetKind, assetValue, helpers) {
  return helpers.call("install_feature_asset", {
    projectPath: helpers.state.selectedPath,
    assetKind,
    assetValue,
  });
}

// Saves a checkbox-backed boolean line and reverts UI state on failure.
async function saveCheckboxLine(line, checkbox, state, helpers) {
  const requestedState = checkbox.checked;
  checkbox.disabled = true;

  try {
    await saveIniValue(line, requestedState ? "1" : "0", helpers);
    state.textContent = requestedState ? "Enabled" : "Disabled";
    helpers.log(`Rearrange HUD ${requestedState ? "enabled" : "disabled"}.`);
  } catch (error) {
    checkbox.checked = !requestedState;
    state.textContent = checkbox.checked ? "Enabled" : "Disabled";
    helpers.log(`Could not update Rearrange HUD: ${error}`);
  } finally {
    checkbox.disabled = false;
  }
}

// Writes only the value for an existing INI line so surrounding whitespace is preserved.
async function saveIniValue(line, value, helpers, fallback = null) {
  if (!line) {
    if (!fallback) {
      throw new Error("No zelda3.ini line was available to update.");
    }

    await helpers.call("set_zelda_ini_value", {
      projectPath: helpers.state.selectedPath,
      section: fallback.section,
      key: fallback.key,
      value,
    });
    return;
  }

  const rawLine = replaceIniValue(line.raw, line.key, value);

  await helpers.call("update_zelda_ini_line", {
    projectPath: helpers.state.selectedPath,
    lineNumber: line.line_number,
    rawLine,
  });

  line.raw = rawLine;
  line.value = value;
  line.commented = false;
}

// Finds a case-insensitive key inside one parsed INI section.
function findLine(lines, key) {
  return lines.find((line) => line.key.toLowerCase() === key.toLowerCase());
}

// Converts common INI boolean spellings into the checkbox state.
function isIniTruthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value).trim().toLowerCase());
}

// Parses install stdout. MSU returns "path\nmode"; sprites/shaders return only "path".
function splitInstallOutput(output) {
  return String(output).trim().split(/\r?\n/).filter(Boolean);
}

// Replaces the right side of `key = value`, removing a leading comment marker when present.
function replaceIniValue(rawLine, key, value) {
  const pattern = new RegExp(
    `^(\\s*)(?:[#;]\\s*)?(${escapeRegExp(key)})(\\s*=\\s*)([^#;]*)(\\s*(?:[#;].*)?)$`,
    "i",
  );
  const match = rawLine.match(pattern);

  if (!match) {
    return `${key} = ${value}`;
  }

  return `${match[1]}${match[2]}${match[3]}${value}${match[5]}`;
}

// Escapes an INI key before using it inside a feature-line replacement regex.
function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Appends a compact unavailable message for missing required INI lines.
function appendUnavailable(container, message) {
  const node = document.createElement("p");
  node.className = "features-empty";
  node.textContent = message;
  container.append(node);
}
