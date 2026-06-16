// Small frontend utilities shared by the card builder, environment screen, controls screen,
// and randomizer screens. Kept in its own file so multiple per-screen modules can import
// them without depending on the launcher's main bootstrap module.

// Escapes text inserted through template strings so filesystem names or user-typed values
// cannot inject markup. Used everywhere an unsanitized string lands inside innerHTML.
export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Maps backend status ids onto the short user-facing labels rendered on each project card.
// Falling back to the raw status string keeps unknown future statuses visible instead of
// silently hidden.
export function labelStatus(status) {
  const labels = {
    ready: "Ready",
    "needs-deploy-copy": "Needs deploy copy",
    "assets-ready": "Assets ready",
    "missing-assets": "Missing assets",
    "source-only": "Setup needed",
  };

  return labels[status] ?? status;
}
