// Connects the top-bar Updates button to the Python updater. The backend owns GitHub
// release checks and installer handoff so WebView network failures cannot block it.
export function connectLauncherUpdateChecker(helpers) {
  const { elements } = helpers;

  elements.updateCheckButton.addEventListener("click", async () => {
    await installLauncherUpdate(helpers);
  });
}

// Runs the updater command and mirrors its ActionResult output in the activity log.
async function installLauncherUpdate(helpers) {
  const { elements, call, log } = helpers;
  const originalText = elements.updateCheckButton.textContent;
  elements.updateCheckButton.disabled = true;
  elements.updateCheckButton.textContent = "Updating";

  try {
    const result = await call("install_launcher_update");
    log(result.message);

    if (result.stdout) {
      log(result.stdout.trim());
    }

    if (result.stderr) {
      log(result.stderr.trim());
    }
  } catch (error) {
    log(`Could not update launcher: ${error}`);
  } finally {
    elements.updateCheckButton.disabled = false;
    elements.updateCheckButton.textContent = originalText;
  }
}
