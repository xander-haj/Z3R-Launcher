// This module renders the Randomizer Setup screen's two always-open exclusion dropdowns
// (items and categories) and keeps the comma-separated text inputs synchronized with
// the clickable options below them.
//
// Extracted from randomizer-setup.js so that file can stay under the project 400-line
// ceiling once category dropdown rendering and category->item disable wiring are added.
//
// Communication rules (one-way, category -> items):
//   * Clicking an item updates only the items input and reds out that single option.
//     It does NOT touch the categories input or the categories dropdown.
//   * Clicking a category updates the categories input, reds out that category, and
//     then disables every item option whose id maps to that category. Any matching
//     ids are also stripped from the items input so the user can't double-exclude.
//   * Deselecting a category un-reds it, removes it from the categories input, and
//     re-enables (but does NOT re-tick) the previously-disabled items.
//
// Item id -> category mapping mirrors assets/randomizer.py's ChestLocation.category().

// Numeric receipt ids that resolve to a non-default category in assets/randomizer.py.
// Anything not listed here falls through to the generic "item" category.
const ITEM_ID_TO_CATEGORY = {
  36: "small-key",
  50: "big-key",
  37: "compass",
  51: "map",
};

// List of categories shown in the categories dropdown, sorted alphabetically by label so
// the visible order matches the items dropdown's sort convention. Category ids and the
// ITEM_ID_TO_CATEGORY map are unchanged, so the comma-separated value sent to the backend
// still matches assets/randomizer.py's accepted category names.
const CATEGORY_OPTIONS = [
  { id: "big-key", label: "Big Key", detail: "Excludes every big key chest from shuffling." },
  { id: "compass", label: "Compass", detail: "Excludes every compass chest from shuffling." },
  { id: "map", label: "Dungeon Map", detail: "Excludes every dungeon map chest from shuffling." },
  { id: "item", label: "Other Items", detail: "Excludes every non-key, non-map, non-compass chest from shuffling." },
  { id: "small-key", label: "Small Key", detail: "Excludes every dungeon small key chest from shuffling." },
];

// Public entry point used by randomizer-setup.js. Replaces the old chip picker call.
// elements references the form inputs and the two new dropdown panel containers; the
// itemOptions array is the list returned by the backend read_randomizer_setup command.
// Returns nothing; click handlers stay attached for the lifetime of the screen.
export function renderExclusionDropdowns(elements, itemOptions) {
  // Bundle state needed by both dropdowns into one object so item-side handlers can
  // re-query the categories input (and vice versa) without prop drilling.
  const context = {
    elements,
    itemOptions: Array.isArray(itemOptions) ? itemOptions : [],
  };

  renderItemsDropdown(context);
  renderCategoriesDropdown(context);
  // After both dropdowns exist, re-run the category->item enforcement so any
  // categories the user already typed into the input persist their disable effect.
  applyCategoryDisablesToItems(context);
}

// Builds the items dropdown panel from the masterlist item list. Each row is a
// clickable option that toggles its id in the #randomizerExcludeItems input and
// flips its visual selected state.
function renderItemsDropdown(context) {
  const { elements, itemOptions } = context;
  const panel = elements.randomizerItemsDropdownPanel;
  panel.textContent = "";

  // No masterlist yet means we render guidance copy instead of an empty panel so
  // the user knows they need to run "Extract assets" first.
  if (itemOptions.length === 0) {
    const empty = document.createElement("p");
    empty.className = "exclusion-empty";
    empty.textContent = "Generate the vanilla masterlist to enable item toggles.";
    panel.append(empty);
    return;
  }

  // Snapshot of currently-excluded item ids so newly rendered options can paint
  // their selected state on initial load (e.g. after a refresh of the page).
  const selected = new Set(splitIntegerCsv(elements.randomizerExcludeItems.value));

  // Sort by label using locale-aware compare so the dropdown reads alphabetically
  // (Arrow, Big Key, Bombs, ...) instead of by numeric receipt id. The masterlist
  // arrives id-sorted from the backend, so the original order is preserved upstream
  // for anything else that consumes report.item_options.
  const orderedOptions = [...itemOptions].sort((left, right) =>
    String(left.label).localeCompare(String(right.label), undefined, { sensitivity: "base" }),
  );

  for (const item of orderedOptions) {
    const option = document.createElement("button");
    option.type = "button";
    option.className = `exclusion-option ${selected.has(String(item.id)) ? "selected" : ""}`;
    option.dataset.itemId = String(item.id);
    option.dataset.category = categoryForItemId(item.id);
    option.title = item.detail;
    option.textContent = `${item.label} (${item.id}) x${item.count}`;
    option.addEventListener("click", () => toggleItemSelection(context, option));
    panel.append(option);
  }
}

// Builds the categories dropdown panel using the fixed CATEGORY_OPTIONS list.
function renderCategoriesDropdown(context) {
  const { elements } = context;
  const panel = elements.randomizerCategoriesDropdownPanel;
  panel.textContent = "";

  // Pre-load the selected set from the input so categories the user already typed
  // (e.g. by manually editing the field) round-trip to a red-out state.
  const selected = new Set(splitTextCsv(elements.randomizerExcludeCategories.value));

  for (const category of CATEGORY_OPTIONS) {
    const option = document.createElement("button");
    option.type = "button";
    option.className = `exclusion-option ${selected.has(category.id) ? "selected" : ""}`;
    option.dataset.categoryId = category.id;
    option.title = category.detail;
    option.textContent = category.label;
    option.addEventListener("click", () => toggleCategorySelection(context, option));
    panel.append(option);
  }
}

// Toggles one item id in the #randomizerExcludeItems input and updates the option's
// red-out state. Disabled options short-circuit so a category-disabled item cannot
// be re-added by an accidental click.
function toggleItemSelection(context, option) {
  if (option.classList.contains("disabled")) {
    return;
  }

  const { elements } = context;
  const itemId = option.dataset.itemId;
  const selected = new Set(splitIntegerCsv(elements.randomizerExcludeItems.value));

  if (selected.has(itemId)) {
    selected.delete(itemId);
  } else {
    selected.add(itemId);
  }

  elements.randomizerExcludeItems.value = Array.from(selected)
    .sort(sortNumericText)
    .join(",");
  option.classList.toggle("selected", selected.has(itemId));
}

// Toggles one category id in the #randomizerExcludeCategories input and then
// re-runs the disable pass over the items dropdown so the UI reflects the
// category exclusion immediately.
function toggleCategorySelection(context, option) {
  const { elements } = context;
  const categoryId = option.dataset.categoryId;
  const selected = new Set(splitTextCsv(elements.randomizerExcludeCategories.value));

  if (selected.has(categoryId)) {
    selected.delete(categoryId);
  } else {
    selected.add(categoryId);
  }

  // Preserve the alphabetical CATEGORY_OPTIONS order in the input string so the
  // serialized value stays human-readable regardless of click order.
  elements.randomizerExcludeCategories.value = CATEGORY_OPTIONS
    .map((category) => category.id)
    .filter((id) => selected.has(id))
    .join(",");
  option.classList.toggle("selected", selected.has(categoryId));

  applyCategoryDisablesToItems(context);
}

// Walks the items dropdown and reconciles each option's disabled/selected state
// against the categories input. Items belonging to a currently-selected category
// become disabled (greyed out, non-clickable) and have their id removed from the
// items input so the backend doesn't receive a duplicate exclusion.
function applyCategoryDisablesToItems(context) {
  const { elements } = context;
  const excludedCategories = new Set(splitTextCsv(elements.randomizerExcludeCategories.value));
  const itemPanel = elements.randomizerItemsDropdownPanel;
  const itemSelected = new Set(splitIntegerCsv(elements.randomizerExcludeItems.value));
  let itemsInputChanged = false;

  for (const option of itemPanel.querySelectorAll(".exclusion-option")) {
    const category = option.dataset.category;
    const itemId = option.dataset.itemId;
    const categoryExcluded = excludedCategories.has(category);

    if (categoryExcluded) {
      // Strip the item id from the input only when it was actually present so we
      // don't churn the field on every re-render.
      if (itemSelected.has(itemId)) {
        itemSelected.delete(itemId);
        itemsInputChanged = true;
      }
      option.classList.add("disabled");
      // Disabled options should not visually appear "selected" — the category
      // pill is the source of truth while it is excluded.
      option.classList.remove("selected");
    } else {
      option.classList.remove("disabled");
      // Re-paint the option's selected state from the current input contents so
      // re-enabling a category does not silently re-add ids.
      option.classList.toggle("selected", itemSelected.has(itemId));
    }
  }

  if (itemsInputChanged) {
    elements.randomizerExcludeItems.value = Array.from(itemSelected)
      .sort(sortNumericText)
      .join(",");
  }
}

// Resolves an item receipt id to its randomizer category string. Anything not in
// the explicit map falls back to the catch-all "item" category, matching the
// default branch in assets/randomizer.py's ChestLocation.category().
function categoryForItemId(id) {
  return ITEM_ID_TO_CATEGORY[id] ?? "item";
}

// Parses a comma-separated user-entered integer list into normalized decimal
// strings. Supports the same 0x / decimal mix as the backend by passing radix 0
// to parseInt. Invalid tokens are dropped so the rest of the input still works.
function splitIntegerCsv(value) {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => String(Number.parseInt(part, 0)))
    .filter((part) => part !== "NaN");
}

// Parses a plain comma-separated text list (used for category ids). Unlike the
// integer parser this preserves the original token text after trimming.
function splitTextCsv(value) {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

// Sorts numeric text values as numbers so the rebuilt input reads "5,12,30"
// instead of "12,30,5" after a chain of clicks.
function sortNumericText(left, right) {
  return Number(left) - Number(right);
}
