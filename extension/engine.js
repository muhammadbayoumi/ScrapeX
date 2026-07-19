// Shared engine-detection helper for popup + onboarding.
// The extension is only a face; the ScrapeX engine is a local Python app the
// user must install. Here we detect whether it's installed & running.

export const DEFAULT_BACKEND = "http://127.0.0.1:8000";

export async function getBackend() {
  const { backend } = await chrome.storage.local.get("backend");
  return (backend || DEFAULT_BACKEND).replace(/\/+$/, "");
}

export async function setBackend(url) {
  await chrome.storage.local.set({ backend: (url || "").trim() || DEFAULT_BACKEND });
}

// Returns { running, version, sources, backend }. running=false means the local
// Python engine is not installed OR not started — the UI treats both as "set up".
export async function checkEngine() {
  const backend = await getBackend();
  try {
    const res = await fetch(backend + "/api/health", { signal: AbortSignal.timeout(2500) });
    if (!res.ok) return { running: false, backend };
    const h = await res.json();
    return { running: true, version: h.version, sources: h.sources_with_data, backend };
  } catch (_) {
    return { running: false, backend };
  }
}
