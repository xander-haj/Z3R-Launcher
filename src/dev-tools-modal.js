import { escapeHtml } from "./shared-utils.js";

const TRIGGER_KEYS = ["d", "e", "v"];
const TRIGGER_TIMEOUT_MS = 3000;
const HOME_REVEAL_TIMEOUT_MS = 2800;

export function connectDevTools(helpers) {
  const refs = ensureDevToolElements();
  const state = { progress: 0, timer: null, sessionId: null, homeRevealTimer: null, stopPromise: null };

  refs.closeButton.addEventListener("click", () => refs.dialog.close());
  refs.downloadButton.addEventListener("click", async () => downloadDevTools(refs, helpers));
  refs.installButton.addEventListener("click", async () => installSelectedTools(refs, helpers));
  refs.repoSelect.addEventListener("change", async () => refreshCatalog(refs, helpers));
  refs.runnerCloseButton.addEventListener("click", () => {
    void closeRunner(refs, state, helpers).catch((error) => helpers.log(`Could not stop dev tool: ${error}`));
  });
  refs.homeZone.addEventListener("pointerdown", (event) => revealHomeButton(event, refs, state));
  refs.homeButton.addEventListener("click", () => {
    void closeRunner(refs, state, helpers).catch((error) => helpers.log(`Could not stop dev tool: ${error}`));
  });
  helpers.elements.backButton.addEventListener("click", () => {
    if (helpers.state.activeView === "dev-tool-runner") {
      void closeRunner(refs, state, helpers).catch((error) => helpers.log(`Could not stop dev tool: ${error}`));
    }
  });
  document.addEventListener("keydown", (event) => handleDocumentKey(event, refs, state, helpers));

  return {
    open(projectPath, toolId) {
      return openDevTool(projectPath, toolId, refs, state, helpers);
    },
  };
}

function ensureDevToolElements() {
  const dialog = document.createElement("dialog");
  dialog.className = "scan-path-dialog dev-tools-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="dev-tools-form">
      <div class="dev-tools-heading">
        <h2>Dev Tools</h2>
        <p>Install launcher-managed tools into a selected repo.</p>
      </div>
      <label class="scan-path-field">
        <span>Target repo</span>
        <select id="devToolsRepoSelect"></select>
      </label>
      <div id="devToolsStatus" class="dev-tools-status"></div>
      <div id="devToolsList" class="dev-tools-list"></div>
      <div class="dev-tools-actions">
        <button id="devToolsDownloadButton" class="secondary-button" type="button">Download / Update</button>
        <button id="devToolsInstallButton" class="primary-button" type="button">Install Selected</button>
        <button id="devToolsCloseButton" class="secondary-button" type="button">Close</button>
      </div>
    </form>
  `;

  const panel = document.createElement("section");
  panel.id = "devToolRunnerPanel";
  panel.className = "view-panel dev-tool-runner-panel";
  panel.dataset.view = "dev-tool-runner";
  panel.setAttribute("aria-label", "Dev tool runner");
  panel.innerHTML = `
    <div id="devToolHomeZone" class="dev-tool-home-zone">
      <button id="devToolHomeButton" class="dev-tool-home-button" type="button" aria-label="Back to launcher home">
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="M3 11.5L12 4l9 7.5"></path>
          <path d="M6.5 10.5V20h11v-9.5"></path>
          <path d="M10 20v-5h4v5"></path>
        </svg>
      </button>
    </div>
    <button id="devToolRunnerCloseButton" class="dev-tool-exit-button" type="button" aria-label="Close editor"></button>
    <iframe id="devToolRunnerFrame" class="dev-tool-frame" title="Dev tool"></iframe>
  `;

  document.body.append(dialog);
  document.querySelector(".workspace")?.prepend(panel);
  return {
    dialog,
    repoSelect: dialog.querySelector("#devToolsRepoSelect"),
    status: dialog.querySelector("#devToolsStatus"),
    list: dialog.querySelector("#devToolsList"),
    downloadButton: dialog.querySelector("#devToolsDownloadButton"),
    installButton: dialog.querySelector("#devToolsInstallButton"),
    closeButton: dialog.querySelector("#devToolsCloseButton"),
    runnerPanel: panel,
    homeZone: panel.querySelector("#devToolHomeZone"),
    homeButton: panel.querySelector("#devToolHomeButton"),
    runnerFrame: panel.querySelector("#devToolRunnerFrame"),
    runnerCloseButton: panel.querySelector("#devToolRunnerCloseButton"),
  };
}

function handleDocumentKey(event, refs, state, helpers) {
  if (event.key === "Escape" && helpers.state.activeView === "dev-tool-runner") {
    void closeRunner(refs, state, helpers).catch((error) => helpers.log(`Could not stop dev tool: ${error}`));
    return;
  }
  handleTriggerKey(event, refs, state, helpers);
}

function handleTriggerKey(event, refs, state, helpers) {
  if (!isTriggerCandidate(event, helpers)) {
    return;
  }

  const expected = TRIGGER_KEYS[state.progress];
  if (event.key.toLowerCase() !== expected) {
    resetTrigger(state);
    return;
  }

  event.preventDefault();
  state.progress += 1;
  armTriggerTimeout(state);
  if (state.progress === TRIGGER_KEYS.length) {
    resetTrigger(state);
    openDialog(refs, helpers);
  }
}

async function openDialog(refs, helpers) {
  populateRepoOptions(refs, helpers);
  if (!refs.dialog.open) {
    refs.dialog.showModal();
  }
  await refreshCatalog(refs, helpers);
}

function populateRepoOptions(refs, helpers) {
  refs.repoSelect.textContent = "";
  for (const candidate of helpers.state.candidates) {
    const option = document.createElement("option");
    option.value = candidate.path;
    option.textContent = candidate.owner ? `${candidate.owner}/${candidate.name}` : candidate.name;
    option.selected = candidate.path === helpers.state.selectedPath;
    refs.repoSelect.append(option);
  }
}

async function refreshCatalog(refs, helpers) {
  const projectPath = selectedRepoPath(refs);
  refs.status.textContent = projectPath ? "Reading dev tools..." : "Select or clone a repo first.";
  refs.list.textContent = "";
  refs.installButton.disabled = !projectPath;

  if (!projectPath) {
    return;
  }

  try {
    const catalog = await helpers.call("read_dev_tools", { projectPath });
    refs.status.textContent = catalog.shared_available
      ? `Downloaded source: ${catalog.shared_repo}`
      : `Source not downloaded yet: ${catalog.source_url}`;
    renderToolList(refs, catalog.tools);
  } catch (error) {
    refs.status.textContent = String(error);
  }
}

function renderToolList(refs, tools) {
  refs.list.textContent = "";
  for (const tool of tools) {
    const row = document.createElement("label");
    row.className = "dev-tool-row";
    row.innerHTML = `
      <input type="checkbox" value="${escapeHtml(tool.id)}" ${tool.available ? "checked" : "disabled"} />
      <span>
        <strong>${escapeHtml(tool.label)}</strong>
        <small>${tool.installed ? "Installed" : tool.available ? "Ready to install" : "Download required"}</small>
      </span>
    `;
    refs.list.append(row);
  }
}

async function downloadDevTools(refs, helpers) {
  refs.downloadButton.disabled = true;
  refs.status.textContent = "Downloading dev tools...";
  try {
    const result = await helpers.call("clone_dev_tools");
    helpers.log(result.message);
    refs.status.textContent = result.message;
    if (result.ok) {
      await refreshCatalog(refs, helpers);
    }
  } catch (error) {
    refs.status.textContent = String(error);
  } finally {
    refs.downloadButton.disabled = false;
  }
}

async function installSelectedTools(refs, helpers) {
  const projectPath = selectedRepoPath(refs);
  const toolIds = selectedToolIds(refs);
  if (!projectPath || toolIds.length === 0) {
    refs.status.textContent = "Select a repo and at least one downloaded tool.";
    return;
  }

  refs.installButton.disabled = true;
  try {
    for (const toolId of toolIds) {
      const result = await helpers.call("install_dev_tool", { projectPath, toolId });
      helpers.log(result.message);
      refs.status.textContent = result.message;
    }
    await helpers.refreshScan();
    await refreshCatalog(refs, helpers);
  } catch (error) {
    refs.status.textContent = String(error);
  } finally {
    refs.installButton.disabled = false;
  }
}

async function openDevTool(projectPath, toolId, refs, state, helpers) {
  if (state.stopPromise) {
    await state.stopPromise.catch(() => {});
  }

  const result = await helpers.call("launch_dev_tool", { projectPath, toolId });
  helpers.log(result.message);

  state.sessionId = result.session_id;
  hideHomeButton(refs, state);
  refs.runnerFrame.src = result.embed_url ?? result.url;
  helpers.showView("dev-tool-runner");
}

async function closeRunner(refs, state, helpers) {
  const sessionId = state.sessionId;
  state.sessionId = null;
  refs.runnerFrame.removeAttribute("src");
  hideHomeButton(refs, state);
  helpers.showView("builds");
  const stopPromise = helpers.call("stop_dev_tool", sessionId ? { sessionId } : {});
  state.stopPromise = stopPromise;
  try {
    await stopPromise;
  } finally {
    if (state.stopPromise === stopPromise) {
      state.stopPromise = null;
    }
  }
}

function selectedRepoPath(refs) {
  return refs.repoSelect.value || "";
}

function revealHomeButton(event, refs, state) {
  if (event.target !== refs.homeZone) {
    return;
  }
  refs.homeZone.classList.add("revealed");
  window.clearTimeout(state.homeRevealTimer);
  state.homeRevealTimer = window.setTimeout(() => hideHomeButton(refs, state), HOME_REVEAL_TIMEOUT_MS);
}

function hideHomeButton(refs, state) {
  refs.homeZone.classList.remove("revealed");
  window.clearTimeout(state.homeRevealTimer);
  state.homeRevealTimer = null;
}

function selectedToolIds(refs) {
  return [...refs.list.querySelectorAll("input[type='checkbox']:checked")]
    .filter((input) => !input.disabled)
    .map((input) => input.value);
}

function isTriggerCandidate(event, helpers) {
  if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || helpers.state.activeView !== "builds") {
    return false;
  }
  if (!document.hasFocus() || document.querySelector("dialog[open]") || isTypingTarget(event.target)) {
    return false;
  }
  return event.key.length === 1;
}

function isTypingTarget(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

function armTriggerTimeout(state) {
  window.clearTimeout(state.timer);
  state.timer = window.setTimeout(() => resetTrigger(state), TRIGGER_TIMEOUT_MS);
}

function resetTrigger(state) {
  window.clearTimeout(state.timer);
  state.timer = null;
  state.progress = 0;
}
