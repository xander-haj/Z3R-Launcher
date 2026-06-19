// Renders the Detected Builds card grid and wires per-card buttons.
// Extracted from main.js so the card markup, click handlers, and per-card widget mounts
// have a focused home as the card surface area grows (Aspect Ratio + Controls buttons,
// nested {owner}/{repo} discoveries, etc).

// Imports: shared utilities and the per-card Aspect Ratio compound widget.
import { escapeHtml, labelStatus } from "./shared-utils.js";
import { mountAspectRatioWidget } from "./card-aspect-ratio.js";

let cardMenuCloserAttached = false;

// Wires up the project-list rendering loop and exposes a `render()` callback the host
// uses to repaint after any state change. `helpers` carries state, DOM refs, the backend
// invoker, the logger, and view-switch callbacks so the module stays free of globals.
export function connectProjectCards(helpers) {
  ensureCardMenuCloser();

  return {
    // Renders every candidate card and the empty-state card when none were discovered.
    render() {
      renderProjectList(helpers);
    },
  };
}

// Replaces the project list with one section per scan path, or an empty-state card.
function renderProjectList(helpers) {
  const { elements, state } = helpers;
  elements.projectList.textContent = "";

  if (state.candidates.length === 0) {
    elements.projectList.append(buildEmptyCard());
    return;
  }

  for (const group of state.scanGroups) {
    if ((group.candidates ?? []).length === 0) {
      continue;
    }

    elements.projectList.append(buildScanGroup(group, helpers));
  }
}

// Builds one visual section per scan path so users can distinguish which root found each repo.
function buildScanGroup(group, helpers) {
  const section = document.createElement("section");
  section.className = "scan-group";
  section.innerHTML = `<h3 class="scan-group-title">${escapeHtml(group.label)}</h3>`;

  const grid = document.createElement("div");
  grid.className = "project-grid";

  for (const candidate of group.candidates) {
    grid.append(buildProjectCard(candidate, helpers));
  }

  section.append(grid);
  return section;
}

// Builds the "no folders found" placeholder shown when scan_siblings returned 0 results.
// It uses a single-column modifier so the help text doesn't inherit the real card's
// action-button grid.
function buildEmptyCard() {
  const empty = document.createElement("article");
  empty.className = "project-card project-card-empty";
  empty.innerHTML = `
    <span class="status warning">Setup needed</span>
    <h3>No Z3R folders found</h3>
    <p class="path-line">Use Clone Z3R or add a repo scan path that contains a Z3R folder.</p>
  `;
  return empty;
}

// Constructs one fully-wired card for a discovered candidate, including all click
// handlers and the inline Aspect Ratio widget. Each button stops click propagation so
// pressing Environment / Randomizer / Controls / Play does NOT also trigger the
// card-level selectProject handler.
function buildProjectCard(candidate, helpers) {
  const { state, selectProject } = helpers;
  const card = document.createElement("article");
  const isPlayable = candidate.status === "ready" && Boolean(candidate.executable_path);
  const selectedClass = candidate.path === state.selectedPath ? "selected" : "";
  const playableClass = isPlayable ? "" : "not-playable";
  card.className = `project-card ${selectedClass} ${playableClass}`;
  card.addEventListener("click", () => {
    closeAllCardMenus();
    selectProject(candidate.path);
  });

  // Status pill colors derive from the backend status string; unknown statuses fall back to
  // the "warning" gold palette so they remain visible rather than disappearing.
  const statusClass = { ready: "ready", "missing-assets": "missing" }[candidate.status] ?? "warning";
  const playDisabled = !isPlayable;
  const authorLine = candidate.owner
    ? `<p class="card-author">by ${escapeHtml(candidate.owner)}</p>`
    : "";

  card.innerHTML = buildCardMarkup({
    statusClass,
    statusLabel: labelStatus(candidate.status),
    playDisabled,
    nameSafe: escapeHtml(candidate.name),
    authorLine,
    patchButton: sourcePatchButtonMarkup(candidate, isPlayable),
    repoButton: repoButtonMarkup(candidate, isPlayable),
    disabledUntilPlayable: disabledUntilPlayableAttribute(isPlayable),
    linkSpriteAttributes: linkSpriteButtonAttributes(candidate),
  });

  wireCardButtons(card, candidate, helpers);
  // Mount the inline Aspect Ratio compound widget into the placeholder slot. The widget
  // owns its own debounce + auto-save loop against the project's zelda3.ini.
  const aspectMount = card.querySelector(".card-aspect-mount");
  void mountAspectRatioWidget(aspectMount, candidate, helpers).then(() => {
    if (!isPlayable) {
      disableCardAspectControls(aspectMount);
    }
  });

  return card;
}

function disableCardAspectControls(mountElement) {
  mountElement?.classList.add("card-aspect-mount-disabled");
  mountElement?.querySelectorAll("button, input, select, textarea").forEach((control) => {
    control.disabled = true;
  });
}

// Centralizes the card HTML so wireCardButtons can stay focused on event wiring.
// Editor navigation is grouped under category flyouts to keep the card footer compact.
function buildCardMarkup({
  statusClass,
  statusLabel,
  playDisabled,
  nameSafe,
  authorLine,
  patchButton,
  repoButton,
  disabledUntilPlayable,
  linkSpriteAttributes,
}) {
  return `
    <span class="status ${statusClass}">${statusLabel}</span>
    <div class="card-top-actions">
      <button class="play-button" type="button" ${playDisabled ? "disabled" : ""}>Play</button>
      ${repoButton}
      ${patchButton}
    </div>
    <div class="card-title-block">
      <h3>${nameSafe}</h3>
      ${authorLine}
    </div>
    <div class="card-config-actions">
      <div class="card-aspect-mount"></div>
      <div class="card-category-actions">
        <div class="card-category-menu-wrap">
          <button
            class="secondary-button card-category-button"
            type="button"
            data-card-menu="mods"
            aria-expanded="false"
            ${linkSpriteAttributes}
          >Mods</button>
          <div class="card-action-menu" data-card-menu="mods" hidden>
            <button class="secondary-button link-sprite-button" type="button" ${linkSpriteAttributes}>
              Link Sprite
            </button>
          </div>
        </div>
        <div class="card-category-menu-wrap">
          <button
            class="secondary-button card-category-button"
            type="button"
            data-card-menu="ini"
            aria-expanded="false"
            ${disabledUntilPlayable}
          >.ini</button>
          <div class="card-action-menu" data-card-menu="ini" hidden>
            <button class="secondary-button features-button" type="button" ${disabledUntilPlayable}>
              Features
            </button>
            <button class="secondary-button controls-button" type="button" ${disabledUntilPlayable}>
              Controls
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="card-setup-actions">
      <button class="secondary-button environment-button" type="button">Environment</button>
      <button class="secondary-button randomizer-button" type="button" ${disabledUntilPlayable}>Randomizer</button>
    </div>
  `;
}

// Attaches the per-button click handlers. The aspect ratio widget mounts later because
// it lives inside the placeholder element and owns its own DOM structure.
function wireCardButtons(card, candidate, helpers) {
  const { call, log, refreshScan, selectProject, openEnvironment, openRepoUpdate, showView, launchProject } = helpers;

  wireCategoryMenus(card);

  card.querySelector(".environment-button").addEventListener("click", async (event) => {
    event.stopPropagation();
    await openEnvironment(candidate.path);
  });

  card.querySelector(".randomizer-button").addEventListener("click", async (event) => {
    event.stopPropagation();
    await selectProject(candidate.path);
    showView("randomizer");
  });

  card.querySelector(".controls-button").addEventListener("click", async (event) => {
    event.stopPropagation();
    closeAllCardMenus();
    await selectProject(candidate.path);
    showView("controls");
  });

  card.querySelector(".link-sprite-button").addEventListener("click", async (event) => {
    event.stopPropagation();
    closeAllCardMenus();
    await selectProject(candidate.path);
    showView("link-sprite");
  });

  card.querySelector(".features-button").addEventListener("click", async (event) => {
    event.stopPropagation();
    closeAllCardMenus();
    await selectProject(candidate.path);
    showView("features");
  });

  card.querySelector(".play-button").addEventListener("click", async (event) => {
    event.stopPropagation();
    await launchProject(candidate);
  });

  const patchButton = card.querySelector(".source-patch-button");
  if (patchButton) {
    patchButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      const command = candidate.source_patch_needed === "solution"
        ? "apply_snesrev_solution_patch"
        : "apply_snesrev_makefile_patch";
      const result = await call(command, { projectPath: candidate.path });
      log(result.message);
      await refreshScan();
    });
  }

  const repoButton = card.querySelector(".repo-update-button");
  if (repoButton) {
    repoButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      await openRepoUpdate(candidate);
    });
  }
}

function ensureCardMenuCloser() {
  if (cardMenuCloserAttached) {
    return;
  }

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !event.target.closest(".card-category-menu-wrap")) {
      closeAllCardMenus();
    }
  });
  cardMenuCloserAttached = true;
}

function wireCategoryMenus(card) {
  for (const button of card.querySelectorAll(".card-category-button")) {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleCardMenu(card, button.dataset.cardMenu);
    });
  }

  for (const menu of card.querySelectorAll(".card-action-menu")) {
    menu.addEventListener("click", (event) => event.stopPropagation());
  }
}

function toggleCardMenu(card, menuName) {
  const menu = card.querySelector(`.card-action-menu[data-card-menu="${menuName}"]`);
  const button = card.querySelector(`.card-category-button[data-card-menu="${menuName}"]`);
  const shouldOpen = menu?.hasAttribute("hidden") ?? false;
  closeAllCardMenus();

  if (!menu || !button || !shouldOpen) {
    return;
  }

  menu.removeAttribute("hidden");
  button.setAttribute("aria-expanded", "true");
}

function closeAllCardMenus() {
  for (const menu of document.querySelectorAll(".card-action-menu")) {
    menu.setAttribute("hidden", "");
  }

  for (const button of document.querySelectorAll(".card-category-button")) {
    button.setAttribute("aria-expanded", "false");
  }
}

// Keeps platform-specific source patch markup in one place so normal cards remain unchanged.
function disabledUntilPlayableAttribute(isPlayable) {
  return isPlayable ? "" : "disabled";
}

function linkSpriteButtonAttributes(candidate) {
  return candidate.link_sprite_editor_available
    ? ""
    : 'disabled title="assets/sprite_sheets.py was not found"';
}

function sourcePatchButtonMarkup(candidate, isPlayable) {
  const labels = {
    makefile: "Patch Makefile",
    solution: "Patch SLN",
  };
  const label = labels[candidate.source_patch_needed];
  const disabled = disabledUntilPlayableAttribute(isPlayable);

  return label
    ? `<button class="secondary-button source-patch-button" type="button" ${disabled}>${label}</button>`
    : "";
}

function repoButtonMarkup(candidate, isPlayable) {
  const disabled = disabledUntilPlayableAttribute(isPlayable);

  return candidate.git_repo
    ? `<button class="secondary-button repo-update-button" type="button" ${disabled}>Open Repo</button>`
    : "";
}
