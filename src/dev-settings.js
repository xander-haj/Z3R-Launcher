// Hidden local developer settings. Normal users never see this entry point.

const UNLOCK_TIMEOUT_MS = 3000;
const UNLOCK_SEQUENCE = [
  "ArrowUp",
  "ArrowUp",
  "ArrowDown",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowLeft",
  "ArrowRight",
  "b",
  "a",
  "Enter",
];

// Wires the hidden keyboard unlock and developer settings dialog.
export function connectDevSettings(helpers) {
  const state = {
    progress: 0,
    timer: null,
    triggerCount: 0,
    triggerTimer: null,
  };

  helpers.elements.devUnlockInput.addEventListener("keydown", (event) => handleUnlockKey(event, helpers, state));
  helpers.elements.devSettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveDevSettings(helpers);
  });
  helpers.elements.devSettingsSaveButton.addEventListener("click", async () => saveDevSettings(helpers));
  helpers.elements.devSettingsResetButton.addEventListener("click", async () => resetDevSettings(helpers));
  helpers.elements.devSettingsCloseButton.addEventListener("click", () => helpers.elements.devSettingsDialog.close());
  helpers.elements.devUpdatePathInput.addEventListener("input", () => refreshDevSourcePreview(helpers));

  document.addEventListener("keydown", (event) => {
    if (!isDevUnlockTrigger(event, helpers)) {
      return;
    }

    event.preventDefault();
    recordUnlockTriggerPress(helpers, state);
  });
}

// Requires three intentional Q presses within the timeout before showing the sequence box.
function recordUnlockTriggerPress(helpers, state) {
  state.triggerCount += 1;

  if (state.triggerCount === 1) {
    state.triggerTimer = window.setTimeout(() => resetUnlockTrigger(state), UNLOCK_TIMEOUT_MS);
  }

  if (state.triggerCount >= 3) {
    resetUnlockTrigger(state);
    openUnlockDialog(helpers, state);
  }
}

// Opens the short-lived unlock input.
function openUnlockDialog(helpers, state) {
  const { devUnlockDialog, devUnlockInput } = helpers.elements;
  resetUnlockState(state);
  devUnlockInput.value = "";

  if (!devUnlockDialog.open) {
    devUnlockDialog.showModal();
  }

  devUnlockInput.focus();
  armUnlockTimeout(helpers, state);
}

// Handles the secret key sequence inside the unlock input.
function handleUnlockKey(event, helpers, state) {
  if (event.key === "Escape") {
    closeUnlockDialog(helpers, state);
    return;
  }

  const key = normalizeUnlockKey(event.key);

  if (!key) {
    if (isIgnorableUnlockKey(event.key)) {
      return;
    }

    event.preventDefault();
    closeUnlockDialog(helpers, state);
    return;
  }

  event.preventDefault();
  armUnlockTimeout(helpers, state);

  if (key !== UNLOCK_SEQUENCE[state.progress]) {
    closeUnlockDialog(helpers, state);
    return;
  }

  state.progress += 1;
  helpers.elements.devUnlockInput.value = "*".repeat(state.progress);

  if (state.progress === UNLOCK_SEQUENCE.length) {
    closeUnlockDialog(helpers, state);
    openDevSettings(helpers);
  }
}

// Opens and populates the developer settings dialog.
async function openDevSettings(helpers) {
  const { elements } = helpers;
  elements.devSettingsStatus.textContent = "";

  if (!elements.devSettingsDialog.open) {
    elements.devSettingsDialog.showModal();
  }

  try {
    applyDevSettingsSnapshot(await helpers.call("read_dev_settings"), helpers);
  } catch (error) {
    elements.devSettingsStatus.textContent = String(error);
  }

  elements.devUpdatePathInput.focus();
}

// Saves the local update-check override.
async function saveDevSettings(helpers) {
  const { elements, log } = helpers;
  elements.devSettingsStatus.textContent = "Saving...";

  try {
    const snapshot = await helpers.call("save_dev_settings", {
      launcherUpdateApiUrl: elements.devUpdatePathInput.value,
      launcherUpdateSource: selectedUpdateSource(helpers),
    });
    applyDevSettingsSnapshot(snapshot, helpers);
    await helpers.refreshActivityUpdateInfo?.();
    elements.devSettingsStatus.textContent = snapshot.message;
    log(snapshot.message);
  } catch (error) {
    elements.devSettingsStatus.textContent = String(error);
  }
}

// Clears the local override so the launcher uses the public backend default again.
async function resetDevSettings(helpers) {
  const { elements, log } = helpers;
  elements.devSettingsStatus.textContent = "Resetting...";

  try {
    const snapshot = await helpers.call("save_dev_settings", {
      launcherUpdateApiUrl: "",
      launcherUpdateSource: "default",
    });
    applyDevSettingsSnapshot(snapshot, helpers);
    await helpers.refreshActivityUpdateInfo?.();
    elements.devSettingsStatus.textContent = snapshot.message;
    log(snapshot.message);
  } catch (error) {
    elements.devSettingsStatus.textContent = String(error);
  }
}

// Mirrors the backend's current/default/effective update paths into the dialog.
function applyDevSettingsSnapshot(snapshot, helpers) {
  const { elements } = helpers;
  elements.devUpdatePathInput.value = snapshot.launcher_update_api_url ?? "";
  renderUpdateSourceChoices(snapshot, helpers);
}

function renderUpdateSourceChoices(snapshot, helpers) {
  const { elements } = helpers;
  const container = devSettingsPathsContainer(helpers);
  container.innerHTML = `
    <label class="dev-update-source-row">
      <input class="dev-update-source-checkbox" type="checkbox" value="default" />
      <span><strong>Default</strong><p id="devDefaultUpdatePath" class="path-line"></p></span>
    </label>
    <label class="dev-update-source-row">
      <input class="dev-update-source-checkbox" type="checkbox" value="dev" />
      <span><strong>Dev</strong><p id="devEffectiveUpdatePath" class="path-line"></p></span>
    </label>
  `;
  elements.devDefaultUpdatePath = container.querySelector("#devDefaultUpdatePath");
  elements.devEffectiveUpdatePath = container.querySelector("#devEffectiveUpdatePath");
  for (const input of container.querySelectorAll(".dev-update-source-checkbox")) {
    input.addEventListener("change", () => chooseUpdateSource(input, helpers));
  }
  elements.devDefaultUpdatePath.textContent = snapshot.default_launcher_update_api_url ?? "";
  setCheckedUpdateSource(snapshot.launcher_update_source, helpers);
  refreshDevSourcePreview(helpers);
}

function refreshDevSourcePreview(helpers) {
  const { elements } = helpers;
  const devUrl = elements.devUpdatePathInput.value.trim();
  const devCheckbox = updateSourceCheckbox(helpers, "dev");
  const defaultCheckbox = updateSourceCheckbox(helpers, "default");
  elements.devEffectiveUpdatePath.textContent = devUrl || "No dev update path saved.";
  if (devCheckbox) {
    devCheckbox.disabled = !devUrl;
  }
  if (!devUrl && devCheckbox?.checked) {
    if (defaultCheckbox) {
      defaultCheckbox.checked = true;
    }
    devCheckbox.checked = false;
  }
}

function chooseUpdateSource(input, helpers) {
  if (!input.checked) {
    input.checked = true;
    return;
  }
  if (input.value === "dev" && !helpers.elements.devUpdatePathInput.value.trim()) {
    input.checked = false;
    const defaultCheckbox = updateSourceCheckbox(helpers, "default");
    if (defaultCheckbox) {
      defaultCheckbox.checked = true;
    }
    return;
  }
  for (const item of updateSourceCheckboxes(helpers)) {
    item.checked = item === input;
  }
}

function setCheckedUpdateSource(source, helpers) {
  const devUrl = helpers.elements.devUpdatePathInput.value.trim();
  const selected = source === "dev" && devUrl ? "dev" : "default";
  for (const input of updateSourceCheckboxes(helpers)) {
    input.checked = input.value === selected;
  }
}

function selectedUpdateSource(helpers) {
  const selected = [...updateSourceCheckboxes(helpers)].find((input) => input.checked)?.value;
  return selected === "dev" && helpers.elements.devUpdatePathInput.value.trim() ? "dev" : "default";
}

function updateSourceCheckbox(helpers, value) {
  return [...updateSourceCheckboxes(helpers)].find((input) => input.value === value) ?? null;
}

function updateSourceCheckboxes(helpers) {
  return devSettingsPathsContainer(helpers)?.querySelectorAll(".dev-update-source-checkbox") ?? [];
}

function devSettingsPathsContainer(helpers) {
  return helpers.elements.devDefaultUpdatePath.closest(".dev-settings-paths");
}

// Reports whether this keydown is the hidden entry trigger.
function isDevUnlockTrigger(event, helpers) {
  if (event.repeat || event.key.toLowerCase() !== "q" || event.altKey || event.ctrlKey || event.metaKey) {
    return false;
  }

  if (!document.hasFocus() || isTypingTarget(event.target)) {
    return false;
  }

  return !helpers.elements.devUnlockDialog.open && !helpers.elements.devSettingsDialog.open;
}

// Prevents the hidden trigger from stealing normal text entry.
function isTypingTarget(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

// Converts browser key names into the unlock sequence values.
function normalizeUnlockKey(key) {
  if (key === "Enter" || key.startsWith("Arrow")) {
    return key;
  }

  const lowered = key.toLowerCase();
  return lowered === "a" || lowered === "b" ? lowered : "";
}

// Lets modifier-only key presses avoid failing the secret sequence.
function isIgnorableUnlockKey(key) {
  return ["Shift", "Control", "Alt", "Meta", "CapsLock", "NumLock", "ScrollLock"].includes(key);
}

function armUnlockTimeout(helpers, state) {
  clearUnlockTimeout(state);
  state.timer = window.setTimeout(() => closeUnlockDialog(helpers, state), UNLOCK_TIMEOUT_MS);
}

function closeUnlockDialog(helpers, state) {
  clearUnlockTimeout(state);
  resetUnlockState(state);

  if (helpers.elements.devUnlockDialog.open) {
    helpers.elements.devUnlockDialog.close();
  }
}

function clearUnlockTriggerTimeout(state) {
  if (state.triggerTimer !== null) {
    window.clearTimeout(state.triggerTimer);
    state.triggerTimer = null;
  }
}

function resetUnlockTrigger(state) {
  clearUnlockTriggerTimeout(state);
  state.triggerCount = 0;
}

function clearUnlockTimeout(state) {
  if (state.timer !== null) {
    window.clearTimeout(state.timer);
    state.timer = null;
  }
}

function resetUnlockState(state) {
  state.progress = 0;
}
