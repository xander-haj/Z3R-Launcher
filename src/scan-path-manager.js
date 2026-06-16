// This module owns the Repos modal, including scan path persistence, clone path
// persistence, clone actions, and drag/drop ordering.
const SCAN_PATHS_STORAGE_KEY = "z3r-launcher-scan-paths";
const CLONE_PATH_STORAGE_KEY = "z3r-launcher-clone-path";

// Loads user-added scan paths from localStorage; the backend prepends the default path at scan time.
export function loadStoredScanPaths() {
  try {
    const stored = JSON.parse(localStorage.getItem(SCAN_PATHS_STORAGE_KEY) ?? "[]");
    return Array.isArray(stored) ? stored.filter((path) => typeof path === "string") : [];
  } catch (error) {
    return [];
  }
}

// Loads the optional clone destination override. Null means the backend should use the default root.
export function loadStoredClonePath() {
  return localStorage.getItem(CLONE_PATH_STORAGE_KEY);
}

// Wires modal controls to the shared app state and scan refresh callback.
export function connectScanPathManager(helpers) {
  const { elements } = helpers;

  elements.scanPathButton.addEventListener("click", () => openScanPathManager(helpers));
  elements.scanPathCloseButton.addEventListener("click", () => elements.scanPathDialog.close());
  elements.scanPathsTabButton.addEventListener("click", () => showRepoTab("scan", helpers));
  elements.cloneTabButton.addEventListener("click", () => showRepoTab("clone", helpers));
  elements.scanPathSelectButton.addEventListener("click", async () => {
    const selectedRoot = await helpers.call("choose_scan_root");

    if (selectedRoot) {
      elements.scanPathInput.value = selectedRoot;
    }
  });
  elements.scanPathForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await addScanPath(elements.scanPathInput.value, helpers);
  });
  elements.clonePathSelect.addEventListener("change", () => saveClonePathFromSelect(helpers));
  elements.cloneBetaCheckbox.addEventListener("change", () => updateCloneButtonState(helpers));
  elements.cloneZ3RModalButton.addEventListener("click", async () => {
    await runClone("clone_project", helpers);
  });
  elements.cloneCustomModalButton.addEventListener("click", async () => {
    const repoUrl = elements.cloneCustomUrl.value.trim();

    if (!repoUrl) {
      helpers.log("Paste a GitHub repository URL before cloning.");
      return;
    }

    await runClone("clone_custom_project", helpers, { repoUrl });
  });
}

// Opens the scan-path manager and paints user-added paths in their stored order.
function openScanPathManager(helpers) {
  const { elements } = helpers;
  elements.scanPathInput.value = "";
  elements.cloneCustomUrl.value = "";
  elements.cloneBetaCheckbox.checked = false;
  showRepoTab("scan", helpers);
  renderScanPathManager(helpers);
  renderClonePathOptions(helpers);
  elements.scanPathDialog.showModal();
  elements.scanPathInput.focus();
}

// Switches between Scan Paths and Clone panes without leaving the modal.
function showRepoTab(tab, helpers) {
  const { elements } = helpers;
  const onScan = tab === "scan";
  elements.scanPathsTabButton.classList.toggle("active", onScan);
  elements.cloneTabButton.classList.toggle("active", !onScan);
  elements.scanPathsTabPanel.classList.toggle("active", onScan);
  elements.cloneTabPanel.classList.toggle("active", !onScan);

  if (!onScan) {
    renderClonePathOptions(helpers);
  }
}

// Renders the manager list with draggable handles and remove buttons.
function renderScanPathManager(helpers) {
  const { elements, state } = helpers;
  elements.scanPathList.textContent = "";

  if (state.scanPaths.length === 0) {
    const empty = document.createElement("p");
    empty.className = "path-line";
    empty.textContent = state.runtimeInfo?.default_clone_requires_scan_path
      ? "Add a repo path here before cloning from this packaged launcher."
      : "Default launcher folder is already scanned. Add more folders here.";
    elements.scanPathList.append(empty);
    return;
  }

  state.scanPaths.forEach((path, index) => {
    elements.scanPathList.append(buildScanPathRow(path, index, helpers));
  });
}

// Builds one draggable manager row. Drag operations reorder state.scanPaths immediately.
function buildScanPathRow(path, index, helpers) {
  const { state, refreshScan } = helpers;
  const row = document.createElement("div");
  row.className = "scan-path-row";
  row.draggable = true;
  row.dataset.index = String(index);
  row.innerHTML = `
    <span class="scan-path-handle" aria-hidden="true">☰</span>
    <span class="scan-path-name">${pathFolderName(path)}</span>
    <button class="secondary-button scan-path-remove" type="button">Remove</button>
  `;

  row.addEventListener("dragstart", (event) => {
    row.classList.add("dragging");
    event.dataTransfer.setData("text/plain", String(index));
  });
  row.addEventListener("dragend", () => row.classList.remove("dragging"));
  row.addEventListener("dragover", (event) => event.preventDefault());
  row.addEventListener("drop", async (event) => {
    event.preventDefault();
    const fromIndex = Number(event.dataTransfer.getData("text/plain"));
    await moveScanPath(fromIndex, index, helpers);
  });
  row.querySelector(".scan-path-remove").addEventListener("click", async () => {
    state.scanPaths.splice(index, 1);
    saveScanPaths(state);
    renderScanPathManager(helpers);
    renderClonePathOptions(helpers);
    await refreshScan();
  });

  return row;
}

// Adds a pasted or selected path after trimming duplicates.
async function addScanPath(path, helpers) {
  const { elements, log, refreshScan, state } = helpers;
  const trimmed = path.trim();

  if (!trimmed) {
    log("Paste or select a folder path before adding it.");
    return;
  }

  if (!state.scanPaths.includes(trimmed)) {
    state.scanPaths.push(trimmed);
    saveScanPaths(state);
  }

  elements.scanPathInput.value = "";
  renderScanPathManager(helpers);
  renderClonePathOptions(helpers);
  await refreshScan();
}

// Moves one user-added scan path to match the drag/drop order shown in the manager.
async function moveScanPath(fromIndex, toIndex, helpers) {
  const { refreshScan, state } = helpers;

  if (!Number.isInteger(fromIndex) || fromIndex === toIndex) {
    return;
  }

  const [path] = state.scanPaths.splice(fromIndex, 1);
  state.scanPaths.splice(toIndex, 0, path);
  saveScanPaths(state);
  renderScanPathManager(helpers);
  renderClonePathOptions(helpers);
  await refreshScan();
}

// Persists only user-added paths because the launcher default is always active.
function saveScanPaths(state) {
  localStorage.setItem(SCAN_PATHS_STORAGE_KEY, JSON.stringify(state.scanPaths));
}

// Populates clone destinations from the current scan roots: default plus added paths.
function renderClonePathOptions(helpers) {
  const { elements, state } = helpers;
  const requiresManualPath = state.runtimeInfo?.default_clone_requires_scan_path ?? false;
  const options = [{ label: "Default", value: "", disabled: requiresManualPath }, ...state.scanPaths.map(pathToOption)];
  const validCloneValues = new Set(options.filter((option) => !option.disabled).map((option) => option.value));
  elements.clonePathSelect.textContent = "";

  if (!validCloneValues.has(state.clonePath ?? "")) {
    state.clonePath = null;
    localStorage.removeItem(CLONE_PATH_STORAGE_KEY);
  }

  for (const option of options) {
    const element = document.createElement("option");
    element.value = option.value;
    element.textContent = option.label;
    element.disabled = Boolean(option.disabled);
    elements.clonePathSelect.append(element);
  }

  elements.clonePathSelect.value = state.clonePath ?? "";

  if (requiresManualPath && !state.clonePath && state.scanPaths.length > 0) {
    state.clonePath = state.scanPaths[0];
    localStorage.setItem(CLONE_PATH_STORAGE_KEY, state.clonePath);
    elements.clonePathSelect.value = state.clonePath;
  }

  if (elements.clonePathSelect.value !== (state.clonePath ?? "")) {
    elements.clonePathSelect.value = "";
  }

  renderClonePathNotice(helpers);
  updateCloneButtonState(helpers);
}

// Saves the clone path override; the Default option returns cloning to the default root.
function saveClonePathFromSelect(helpers) {
  const { elements, log, state } = helpers;
  const clonePath = elements.clonePathSelect.value;
  state.clonePath = clonePath || null;

  if (state.clonePath) {
    localStorage.setItem(CLONE_PATH_STORAGE_KEY, state.clonePath);
    log(`Clone path set to ${state.clonePath}`);
  } else {
    localStorage.removeItem(CLONE_PATH_STORAGE_KEY);
    log("Clone path reset to the launcher default.");
  }

  renderClonePathNotice(helpers);
  updateCloneButtonState(helpers);
}

// Runs fixed or custom clone commands against the saved clone destination.
async function runClone(command, helpers, extraPayload = {}) {
  const { elements, refreshScan, state } = helpers;
  const requiresManualPath = state.runtimeInfo?.default_clone_requires_scan_path ?? false;

  if (requiresManualPath && !state.clonePath) {
    helpers.log(state.runtimeInfo?.default_clone_warning ?? "Add a repo scan path before cloning.");
    return;
  }

  saveClonePathFromSelect(helpers);
  elements.cloneZ3RModalButton.disabled = true;
  elements.cloneCustomModalButton.disabled = true;

  try {
    const payload = {
      scanRoot: state.clonePath,
      ...extraPayload,
    };

    if (command === "clone_project") {
      payload.beta = elements.cloneBetaCheckbox.checked;
    }

    const result = await helpers.call(command, payload);
    helpers.log(result.message);

    if (result.stdout) {
      helpers.log(result.stdout.trim());
    }

    if (result.stderr) {
      helpers.log(result.stderr.trim());
    }

    elements.cloneCustomUrl.value = "";
    await refreshScan();
  } finally {
    updateCloneButtonState(helpers);
  }
}

function renderClonePathNotice(helpers) {
  const { elements, state } = helpers;
  const warning = state.runtimeInfo?.default_clone_warning;
  const requiresManualPath = state.runtimeInfo?.default_clone_requires_scan_path ?? false;

  elements.clonePathNotice.classList.toggle("hidden", !requiresManualPath);
  elements.clonePathNotice.textContent = requiresManualPath
    ? warning ?? "Add a repo scan path before cloning from this packaged app."
    : "";
}

function updateCloneButtonState(helpers) {
  const { elements, state } = helpers;
  const requiresManualPath = state.runtimeInfo?.default_clone_requires_scan_path ?? false;
  const hasAllowedClonePath = !requiresManualPath || Boolean(state.clonePath);
  const beta = elements.cloneBetaCheckbox.checked;

  elements.cloneZ3RModalButton.textContent = beta ? "Clone Z3R Beta" : "Clone Z3R";
  elements.cloneZ3RModalButton.disabled = !hasAllowedClonePath;
  elements.cloneCustomModalButton.disabled = !hasAllowedClonePath;
}

// Extracts the final folder name for compact manager labels on every platform.
function pathFolderName(path) {
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts.at(-1) ?? path;
}

// Converts a full path into the compact dropdown option used by the Clone tab.
function pathToOption(path) {
  return {
    label: pathFolderName(path),
    value: path,
    disabled: false,
  };
}
