// Owns the cloned-repo update dialog. It fetches a backend preview, renders upstream
// changed files as checkboxes, and applies only the checked paths.
import { escapeHtml } from "./shared-utils.js";

export function connectRepoUpdateManager(helpers) {
  const { elements } = helpers;

  elements.repoUpdateCloseButton.addEventListener("click", () => elements.repoUpdateDialog.close());
  elements.repoUpdateRefreshButton.addEventListener("click", async () => {
    if (helpers.state.repoUpdateProject) {
      await openRepoUpdate(helpers.state.repoUpdateProject, helpers);
    }
  });
  elements.repoUpdateOpenFolderButton.addEventListener("click", async () => {
    if (!helpers.state.repoUpdateProject) {
      return;
    }

    const result = await helpers.call("open_project_folder", {
      projectPath: helpers.state.repoUpdateProject.path,
    });
    helpers.log(result.message);
  });
  elements.repoUpdateRenameIniButton.addEventListener("click", async () => {
    await renameIniForRepoUpdate(helpers);
  });
  elements.repoUpdateApplyButton.addEventListener("click", async () => {
    await applySelectedRepoChanges(helpers);
  });

  return {
    async open(candidate) {
      await openRepoUpdate(candidate, helpers);
    },
  };
}

async function openRepoUpdate(candidate, helpers) {
  const { elements, state } = helpers;
  state.repoUpdateProject = candidate;
  elements.repoUpdateTitle.textContent = `Update ${candidate.name}`;
  elements.repoUpdatePath.textContent = candidate.path;
  elements.repoUpdateWarnings.textContent = "";
  elements.repoUpdateSummary.textContent = "Fetching upstream changes...";
  elements.repoUpdateFileList.textContent = "";
  clearRepoVerification(elements);
  elements.repoUpdateApplyButton.disabled = true;
  elements.repoUpdateRenameIniButton.classList.add("hidden");
  elements.repoUpdateRenameIniButton.disabled = true;

  if (!elements.repoUpdateDialog.open) {
    elements.repoUpdateDialog.showModal();
  }

  try {
    const preview = await helpers.call("preview_repo_update", {
      projectPath: candidate.path,
    });
    state.repoUpdatePreview = preview;
    renderRepoPreview(preview, helpers);
  } catch (error) {
    elements.repoUpdateSummary.textContent = String(error);
  }
}

function renderRepoPreview(preview, helpers) {
  const { elements } = helpers;
  elements.repoUpdateWarnings.textContent = "";
  elements.repoUpdateFileList.textContent = "";

  for (const warning of preview.warnings ?? []) {
    const item = document.createElement("p");
    item.className = "repo-warning";
    item.textContent = warning;
    elements.repoUpdateWarnings.append(item);
  }

  renderIniRenameButton(preview, helpers);

  if ((preview.changes ?? []).length === 0) {
    elements.repoUpdateSummary.textContent = preview.upstream
      ? `No unapplied upstream file changes found on ${preview.upstream}.`
      : "No unapplied upstream file changes found.";
    elements.repoUpdateApplyButton.disabled = true;
    return;
  }

  const countText = preview.behind_count === 1 ? "1 commit" : `${preview.behind_count} commits`;
  elements.repoUpdateSummary.textContent = `${countText} behind ${preview.upstream ?? "upstream"}.`;

  for (const change of preview.changes) {
    const row = document.createElement("label");
    row.className = "repo-update-file-row";
    row.innerHTML = `
      <input type="checkbox" value="${escapeHtml(change.path)}" checked />
      <span class="repo-update-status">${escapeHtml(change.label)}</span>
      <span class="repo-update-path">${escapeHtml(change.path)}</span>
    `;

    if (change.old_path) {
      row.querySelector(".repo-update-path").textContent = `${change.old_path} -> ${change.path}`;
    }

    elements.repoUpdateFileList.append(row);
  }

  elements.repoUpdateApplyButton.disabled = !preview.can_apply;
}

function renderIniRenameButton(preview, helpers) {
  const { elements } = helpers;
  const showButton = Boolean(preview.ini_update_available);
  elements.repoUpdateRenameIniButton.classList.toggle("hidden", !showButton);
  elements.repoUpdateRenameIniButton.disabled = !preview.can_rename_ini;
  elements.repoUpdateRenameIniButton.title = preview.can_rename_ini
    ? "Rename zelda3.ini to zelda3.user.ini before applying the update."
    : "zelda3.ini is missing or zelda3.user.ini already exists.";
}

async function renameIniForRepoUpdate(helpers) {
  const { state, elements } = helpers;
  if (!state.repoUpdateProject) {
    return;
  }

  clearRepoVerification(elements);
  elements.repoUpdateRenameIniButton.disabled = true;

  try {
    const result = await helpers.call("rename_zelda_ini_to_user_ini", {
      projectPath: state.repoUpdateProject.path,
    });
    helpers.log(result.message);
    if (!result.ok) {
      elements.repoUpdateRenameIniButton.disabled = false;
      showRepoFailure(elements, result.message || "Rename failed.");
      return;
    }
    await refreshRepoUpdateAfterSuccess(state.repoUpdateProject, helpers);
    showRepoVerification(elements, result.message || "zelda3.ini renamed.");
  } catch (error) {
    helpers.log(`Could not rename zelda3.ini: ${error}`);
    showRepoFailure(elements, `Rename failed: ${error}`);
    elements.repoUpdateRenameIniButton.disabled = false;
  }
}

async function applySelectedRepoChanges(helpers) {
  const { elements, state } = helpers;

  if (!state.repoUpdateProject || !state.repoUpdatePreview) {
    return;
  }

  const selectedFiles = [...elements.repoUpdateFileList.querySelectorAll("input:checked")].map(
    (input) => input.value,
  );

  elements.repoUpdateApplyButton.disabled = true;
  clearRepoVerification(elements);

  try {
    const result = await helpers.call("apply_repo_update", {
      projectPath: state.repoUpdateProject.path,
      selectedFiles,
    });
    helpers.log(result.message);

    if (result.stdout) {
      helpers.log(result.stdout.trim());
    }

    if (result.stderr) {
      helpers.log(result.stderr.trim());
    }

    if (!result.ok) {
      showRepoFailure(elements, result.message || "Repo update failed.");
      elements.repoUpdateApplyButton.disabled = false;
      return;
    }

    await refreshRepoUpdateAfterSuccess(state.repoUpdateProject, helpers);
    showRepoVerification(elements, result.message || "Selected repo changes applied.");
  } catch (error) {
    helpers.log(`Repo update apply failed: ${error}`);
    showRepoFailure(elements, `Repo update failed: ${error}`);
    elements.repoUpdateApplyButton.disabled = false;
  }
}

async function refreshRepoUpdateAfterSuccess(candidate, helpers) {
  try {
    await helpers.refreshScan();
    await openRepoUpdate(candidate, helpers);
  } catch (error) {
    helpers.log(`Repo update refresh failed after a confirmed change: ${error}`);
  }
}

function showRepoVerification(elements, message) {
  elements.repoUpdateVerification.textContent = `✓ ${message}`;
  elements.repoUpdateVerification.classList.remove("failed");
  elements.repoUpdateVerification.classList.remove("hidden");
}

function showRepoFailure(elements, message) {
  elements.repoUpdateVerification.textContent = message;
  elements.repoUpdateVerification.classList.add("failed");
  elements.repoUpdateVerification.classList.remove("hidden");
}

function clearRepoVerification(elements) {
  elements.repoUpdateVerification.textContent = "";
  elements.repoUpdateVerification.classList.remove("failed");
  elements.repoUpdateVerification.classList.add("hidden");
}
