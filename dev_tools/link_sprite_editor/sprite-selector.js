import { createSpriteGrid } from "./sprite-grid.js";

const LINK_GRAPHICS_KEY = "LinkGraphics";

export async function renderSpriteSelector(container, helpers, refresh, browser) {
  let iniSnapshot;
  let assets;

  try {
    [iniSnapshot, assets] = await Promise.all([
      helpers.call("read_zelda_ini", { projectPath: helpers.state.selectedPath }),
      helpers.call("read_feature_assets", { projectPath: helpers.state.selectedPath }),
    ]);
  } catch (error) {
    helpers.log(`Could not read Link sprite options: ${error}`);
    appendSelectorUnavailable(container, "Link sprite options are unavailable.");
    return;
  }

  const line = findLine(iniSnapshot.graphics_lines, LINK_GRAPHICS_KEY);
  const section = document.createElement("section");
  section.className = "features-asset-section link-sprite-picker-section";
  section.innerHTML = `
    <div class="features-asset-heading">
      <h3>ZSPR Sprite</h3>
      <span class="features-asset-status ${assets.sprites.available ? "available" : "missing"}">
        ${assets.sprites.available ? "Available" : "Not available"}
      </span>
    </div>
  `;

  const actionRow = appendActionRow(section);
  appendButton(actionRow, "Source", async () => helpers.openExternalUrl(assets.sprites_source_url));

  if (!assets.sprites.shared_available) {
    appendButton(actionRow, "Clone sprites", async () => {
      const result = await helpers.call("clone_feature_asset", { assetKind: "sprites" });
      helpers.log(result.message);
      await refresh();
    });
  }

  if (assets.sprites.options.length > 0) {
    appendSpritePicker(section, {
      options: assets.sprites.options,
      browser,
      helpers,
      selectedValue: line?.value ?? "",
      onApply: async (value) => {
        const applied = await applySpriteSelection(value, line, helpers);
        if (applied) {
          await refresh();
        }
      },
    });

    if (!line) {
      appendUnavailable(section, `${LINK_GRAPHICS_KEY} will be created in zelda3.ini when applied.`);
    }
  } else {
    appendUnavailable(section, "No link sprite options found.");
  }

  container.append(section);
}

function appendSpritePicker(section, config) {
  const row = document.createElement("div");
  const lookup = buildOptionLookup(config.options);
  let gridController = null;

  row.className = "features-picker-row link-sprite-picker-row";
  row.innerHTML = `
    <div class="features-picker-control">
      <input
        class="features-filter-input"
        type="text"
        placeholder="Type to filter"
        autocomplete="off"
      />
      <button
        class="secondary-button features-picker-toggle"
        type="button"
        aria-expanded="false"
      >Show all</button>
    </div>
    <button class="secondary-button" type="button">Use sprite</button>
  `;

  const input = row.querySelector(".features-filter-input");
  const toggle = row.querySelector(".features-picker-toggle");
  const applyButton = row.lastElementChild;
  input.value = (
    optionLabelForValue(config.options, config.selectedValue)
    ?? optionDisplayLabel(config.options[0])
  );

  input.addEventListener("input", () => {
    gridController?.filter(input.value);
  });
  toggle.addEventListener("click", () => {
    if (config.browser.isOpen()) {
      config.browser.hide();
      return;
    }

    gridController = createSpriteGrid({
      options: config.options,
      selectedValue: resolveValue(),
      helpers: config.helpers,
      onChoose(option) {
        input.value = optionDisplayLabel(option);
        config.browser.hide();
      },
      onClose() {
        config.browser.hide();
      },
    });
    config.browser.show(gridController.element, () => {
      gridController?.destroy();
      gridController = null;
      syncToggle();
    });
    gridController.filter("");
    syncToggle();
  });
  applyButton.addEventListener("click", async () => {
    applyButton.disabled = true;
    try {
      await config.onApply(resolveValue());
    } finally {
      applyButton.disabled = false;
    }
  });

  section.append(row);

  function resolveValue() {
    return lookup.get(input.value) ?? input.value;
  }

  function syncToggle() {
    const open = config.browser.isOpen();
    toggle.textContent = open ? "Hide" : "Show all";
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
}

function appendSelectorUnavailable(container, message) {
  const section = document.createElement("section");
  section.className = "features-asset-section link-sprite-picker-section";
  section.innerHTML = `
    <div class="features-asset-heading">
      <h3>ZSPR Sprite</h3>
      <span class="features-asset-status missing">Not available</span>
    </div>
  `;
  appendUnavailable(section, message);
  container.append(section);
}

async function applySpriteSelection(value, line, helpers) {
  const spritePath = value.trim();
  if (!spritePath) {
    helpers.log("Select a sprite before applying.");
    return false;
  }

  const result = await helpers.call("install_feature_asset", {
    projectPath: helpers.state.selectedPath,
    assetKind: "sprites",
    assetValue: spritePath,
  });
  const [assetPath] = splitInstallOutput(result.stdout);
  if (!assetPath) {
    helpers.log("Sprite install did not return a copied asset path.");
    return false;
  }

  await saveIniValue(line, assetPath, helpers);
  helpers.log(result.message);
  return true;
}

function appendActionRow(section) {
  const row = document.createElement("div");
  row.className = "features-action-row";
  section.append(row);
  return row;
}

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

async function saveIniValue(line, value, helpers) {
  if (!line) {
    await helpers.call("set_zelda_ini_value", {
      projectPath: helpers.state.selectedPath,
      section: "Graphics",
      key: LINK_GRAPHICS_KEY,
      value,
    });
    return;
  }

  await helpers.call("update_zelda_ini_line", {
    projectPath: helpers.state.selectedPath,
    lineNumber: line.line_number,
    rawLine: replaceIniValue(line.raw, line.key, value),
  });
}

function splitInstallOutput(output) {
  return String(output).trim().split(/\r?\n/).filter(Boolean);
}

function findLine(lines, key) {
  return lines.find((line) => line.key.toLowerCase() === key.toLowerCase());
}

function optionLabelForValue(options, selectedValue) {
  const selected = options.find((option) => option.value === selectedValue);
  return selected ? optionDisplayLabel(selected) : selectedValue;
}

function optionDisplayLabel(option) {
  return option ? `${option.label} (${option.source})` : "";
}

function buildOptionLookup(options) {
  const lookup = new Map();

  for (const option of options) {
    lookup.set(optionDisplayLabel(option), option.value);
    lookup.set(option.value, option.value);
  }

  return lookup;
}

function replaceIniValue(rawLine, key, value) {
  const pattern = new RegExp(
    `^(\\s*)(?:[#;]\\s*)?(${escapeRegExp(key)})(\\s*=\\s*)([^#;]*)(\\s*(?:[#;].*)?)$`,
    "i",
  );
  const match = rawLine.match(pattern);
  return match ? `${match[1]}${match[2]}${match[3]}${value}${match[5]}` : `${key} = ${value}`;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function appendUnavailable(container, message) {
  const node = document.createElement("p");
  node.className = "features-empty";
  node.textContent = message;
  container.append(node);
}
