// This module loads and renders editable manual-install guides for missing environment dependencies.

// Loads guide copy from JSON so OS-specific install instructions can be edited without touching app code.
export async function loadManualInstallGuides(log) {
  try {
    const response = await fetch("./manual-install-guides.json");
    return await response.json();
  } catch (error) {
    log(`Could not load manual-install-guides.json: ${error}`);
    return {
      macos: {},
      windows: {},
      linux: {},
    };
  }
}

// Returns the guide for a dependency id on the active OS, or null when no starter guide exists yet.
export function getManualInstallGuide(guides, os, dependencyId) {
  return guides?.[os]?.[dependencyId] ?? null;
}

// Checks whether the active OS has guide content for the missing dependency row.
export function hasManualInstallGuide(guides, os, dependencyId) {
  return Boolean(getManualInstallGuide(guides, os, dependencyId));
}

// Renders the guide page with optional step images and reference links from the JSON guide file.
export function renderManualInstallGuide(guide, elements, selectedPath, openExternalUrl) {
  const projectPath = selectedPath ?? "your selected Z3R folder";
  elements.manualGuideTitle.textContent = guide.title ?? "Manual Install";
  elements.manualGuideMeta.textContent = guide.meta ?? "Manual install";
  elements.manualGuideContent.textContent = "";

  if (guide.summary) {
    const summary = document.createElement("p");
    summary.className = "guide-summary";
    summary.textContent = replaceProjectPath(guide.summary, projectPath);
    elements.manualGuideContent.append(summary);
  }

  for (const [index, step] of (guide.steps ?? []).entries()) {
    elements.manualGuideContent.append(renderStep(step, index + 1, projectPath));
  }

  if (Array.isArray(guide.links) && guide.links.length > 0) {
    elements.manualGuideContent.append(renderLinks(guide.links, openExternalUrl));
  }
}

// Creates one numbered guide step and includes an image only when the JSON entry provides one.
function renderStep(step, index, projectPath) {
  const section = document.createElement("section");
  section.className = "guide-step";

  const heading = document.createElement("h3");
  heading.innerHTML = `<span class="guide-step-index">${index}</span>${escapeHtml(step.title ?? `Step ${index}`)}`;
  section.append(heading);

  const text = document.createElement("p");
  text.className = "path-line";
  text.textContent = replaceProjectPath(step.text ?? "", projectPath);
  section.append(text);

  if (step.image) {
    const image = document.createElement("img");
    image.className = "guide-image";
    image.src = step.image;
    image.alt = step.alt ?? step.title ?? `Manual install step ${index}`;
    section.append(image);
  }

  return section;
}

// Renders trusted reference links as buttons so the backend can open them through the native OS.
function renderLinks(links, openExternalUrl) {
  const wrapper = document.createElement("div");
  wrapper.className = "guide-links";

  for (const link of links) {
    const button = document.createElement("button");
    button.className = "guide-link";
    button.type = "button";
    button.textContent = link.label;
    button.addEventListener("click", () => openExternalUrl(link.url));
    wrapper.append(button);
  }

  return wrapper;
}

// Replaces the project path token used by guides that need to mention the active Z3R folder.
function replaceProjectPath(text, projectPath) {
  return String(text).replaceAll("{projectPath}", projectPath);
}

// Escapes headings inserted through innerHTML so editable JSON cannot inject markup into the guide page.
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
