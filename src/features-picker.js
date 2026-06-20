// Filterable asset picker shared by MSU, sprite, and shader controls on the Features screen.

// Imports: shared escaping for labels built from filesystem-derived names.
import { escapeHtml } from "./shared-utils.js";

let pickerId = 0;

// Adds a text-filterable picker plus an apply button for one group of discovered assets.
export function appendOptionPicker(section, options, buttonLabel, onApply, selectedValue = "", config = {}) {
  const row = document.createElement("div");
  const listId = `featuresPicker${pickerId++}`;
  row.className = "features-picker-row";
  row.innerHTML = `
    <div class="features-picker-control">
      <input
        class="features-filter-input"
        type="text"
        list="${listId}"
        placeholder="Type to filter"
        autocomplete="off"
      />
      <button
        class="secondary-button features-picker-toggle"
        type="button"
        aria-expanded="false"
      >Show all</button>
      <datalist id="${listId}">
        ${options.map(optionMarkup).join("")}
      </datalist>
      <div class="features-picker-menu" hidden></div>
    </div>
    <button class="secondary-button" type="button">${escapeHtml(buttonLabel)}</button>
  `;

  const input = row.querySelector(".features-filter-input");
  const toggle = row.querySelector(".features-picker-toggle");
  const menu = row.querySelector(".features-picker-menu");
  const button = row.lastElementChild;
  const lookup = buildOptionLookup(options);
  button.disabled = Boolean(config.disabled);
  button.title = config.disabledTitle ?? "";
  input.value = optionLabelForValue(options, selectedValue) ?? optionDisplayLabel(options[0]);
  input.addEventListener("input", () => {
    if (!menu.hidden) {
      renderMenu(menu, options, input.value, input, closeMenu);
    }
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
    }
  });
  toggle.addEventListener("click", () => {
    if (menu.hidden) {
      renderMenu(menu, options, "", input, closeMenu);
      openMenu();
    } else {
      closeMenu();
    }
  });
  row.addEventListener("focusout", () => {
    setTimeout(() => {
      if (!row.contains(document.activeElement)) {
        closeMenu();
      }
    }, 0);
  });
  button.addEventListener("click", async () => {
    if (button.disabled) {
      return;
    }

    const selectedValue = resolveValue();

    button.disabled = true;
    try {
      await onApply(selectedValue);
    } finally {
      button.disabled = false;
    }
  });
  section.append(row);

  function resolveValue() {
    return lookup.get(input.value) ?? input.value;
  }

  function openMenu() {
    menu.hidden = false;
    toggle.textContent = "Hide";
    toggle.setAttribute("aria-expanded", "true");
  }

  function closeMenu() {
    menu.hidden = true;
    toggle.textContent = "Show all";
    toggle.setAttribute("aria-expanded", "false");
  }

  return {
    input,
    resolveValue,
    setValue(value) {
      input.value = optionLabelForValue(options, value) ?? value;
    },
  };
}

// Rebuilds the custom option menu. The native datalist remains as a browser fallback.
function renderMenu(menu, options, query, input, closeMenu) {
  const normalizedQuery = String(query).trim().toLowerCase();
  const matches = options.filter((option) => {
    const label = optionDisplayLabel(option).toLowerCase();
    const value = option.value.toLowerCase();
    return !normalizedQuery || label.includes(normalizedQuery) || value.includes(normalizedQuery);
  });

  menu.textContent = "";

  if (matches.length === 0) {
    const empty = document.createElement("div");
    empty.className = "features-picker-empty";
    empty.textContent = "No matches";
    menu.append(empty);
    return;
  }

  for (const option of matches) {
    const optionButton = document.createElement("button");
    optionButton.className = "features-picker-option";
    optionButton.type = "button";
    optionButton.textContent = optionDisplayLabel(option);
    optionButton.addEventListener("click", () => {
      input.value = optionDisplayLabel(option);
      closeMenu();
      input.focus();
    });
    menu.append(optionButton);
  }
}

// Returns the display label for the current ini value when the value is present in options.
function optionLabelForValue(options, selectedValue) {
  const selected = options.find((option) => option.value === selectedValue);

  return selected ? optionDisplayLabel(selected) : selectedValue;
}

// Creates one datalist option whose value is readable while still mapping back to the asset path.
function optionMarkup(option) {
  return `<option value="${escapeHtml(optionDisplayLabel(option))}"></option>`;
}

// Uses a label that includes whether the asset came from shared storage or the selected build.
function optionDisplayLabel(option) {
  return `${option.label} (${option.source})`;
}

// Accepts either the displayed label or the raw path so pasting a known value still works.
function buildOptionLookup(options) {
  const lookup = new Map();

  for (const option of options) {
    lookup.set(optionDisplayLabel(option), option.value);
    lookup.set(option.value, option.value);
  }

  return lookup;
}
