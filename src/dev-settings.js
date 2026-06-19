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
  };

  helpers.elements.devUnlockInput.addEventListener("keydown", (event) => handleUnlockKey(event, helpers, state));
  helpers.elements.devSettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveDevSettings(helpers);
  });
  helpers.elements.devSettingsSaveButton.addEventListener("click", async () => saveDevSettings(helpers));
  helpers.elements.devSettingsResetButton.addEventListener("click", async () => resetDevSettings(helpers));
  helpers.elements.devSettingsCloseButton.addEventListener("click", () => helpers.elements.devSettingsDialog.close());

  document.addEventListener("keydown", (event) => {
    if (!isDevUnlockTrigger(event, helpers)) {
      return;
    }

    event.preventDefault();
    openUnlockDialog(helpers, state);
  });
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
    });
    applyDevSettingsSnapshot(snapshot, helpers);
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
    });
    applyDevSettingsSnapshot(snapshot, helpers);
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
  elements.devDefaultUpdatePath.textContent = snapshot.default_launcher_update_api_url ?? "";
  elements.devEffectiveUpdatePath.textContent = snapshot.effective_launcher_update_api_url ?? "";
}

// Reports whether this keydown is the hidden entry trigger.
function isDevUnlockTrigger(event, helpers) {
  if (event.key.toLowerCase() !== "q" || event.altKey || event.ctrlKey || event.metaKey) {
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

function clearUnlockTimeout(state) {
  if (state.timer !== null) {
    window.clearTimeout(state.timer);
    state.timer = null;
  }
}

function resetUnlockState(state) {
  state.progress = 0;
}
