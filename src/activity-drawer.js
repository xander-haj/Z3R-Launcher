// Activity drawer controller: owns the console log, drawer toggle, copy/clear
// actions, and the local update-source/version label shown above the log.

export function createActivityDrawer(elements) {
  let callBackend = null;

  function log(message) {
    const now = new Date().toLocaleTimeString();
    elements.logOutput.textContent += `\n[${now}] ${message}`;
    elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
  }

  function connect(call) {
    callBackend = call;

    elements.activityToggle.addEventListener("click", () => {
      const isOpen = elements.activityPanel.classList.toggle("open");
      elements.activityToggle.setAttribute("aria-expanded", String(isOpen));
    });

    elements.clearLogButton.addEventListener("click", () => {
      elements.logOutput.textContent = "Ready.";
    });

    elements.copyLogButton.addEventListener("click", async () => {
      await copyConsoleOutput(elements, log);
    });
  }

  async function refreshUpdateInfo() {
    if (!callBackend) {
      return;
    }

    try {
      const [settings, version] = await Promise.all([
        callBackend("read_dev_settings"),
        callBackend("launcher_version"),
      ]);
      elements.activityUpdateInfo.textContent = updateInfoText(settings, version);
    } catch (error) {
      elements.activityUpdateInfo.textContent = "Update repo: unavailable | App version: unavailable";
    }
  }

  return { connect, log, refreshUpdateInfo };
}

async function copyConsoleOutput(elements, log) {
  try {
    await writeClipboard(elements.logOutput.textContent);
    log("Console output copied.");
  } catch (error) {
    log(`Could not copy console output: ${error}`);
  }
}

async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-1000px";
  textArea.style.top = "0";
  document.body.append(textArea);
  textArea.select();

  try {
    if (!document.execCommand("copy")) {
      throw new Error("Copy command was rejected.");
    }
  } finally {
    textArea.remove();
  }
}

function updateInfoText(settings, version) {
  const override = settings.launcher_update_api_url?.trim();
  const source = override ? "Dev update repo" : "Default update repo";
  const repo = repoDisplayName(settings.effective_launcher_update_api_url);
  return `${source}: ${repo} | App version: ${version}`;
}

function repoDisplayName(url) {
  const value = String(url ?? "");
  const match = value.match(/^https:\/\/api\.github\.com\/repos\/([^/]+)\/([^/]+)\/releases\/latest$/);
  return match ? `${match[1]}/${match[2]}` : value || "unknown";
}
