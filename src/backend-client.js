// Local Python backend bridge. It preserves the old invoke(command, payload) shape
// while sending requests to the token-protected localhost server that serves this UI.
const launchToken = new URLSearchParams(window.location.search).get("token") ?? "";
const headers = {
  "Content-Type": "application/json",
  "X-Z3R-Launcher-Token": launchToken,
};

export async function invoke(command, payload = {}) {
  const response = await fetch("/api/invoke", {
    method: "POST",
    headers,
    body: JSON.stringify({ command, payload }),
  });
  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw body.error ?? `${command} failed with HTTP ${response.status}`;
  }

  return body.result;
}

async function ping(path, keepalive = false) {
  if (!launchToken) {
    return;
  }

  try {
    await fetch(path, {
      method: "POST",
      headers,
      body: "{}",
      keepalive,
    });
  } catch (error) {
    // The backend may already be shutting down; no UI action is needed here.
  }
}

window.setInterval(() => ping("/api/ping"), 5000);
