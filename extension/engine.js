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

// `running` means the background worker is alive, not merely that something
// answered on port 8000. `reachable` lets the UI distinguish those states.
export async function checkEngine() {
  const backend = await getBackend();
  try {
    const res = await fetch(backend + "/api/health", { signal: AbortSignal.timeout(2500) });
    if (!res.ok) return { running: false, reachable: true, backend };
    const h = await res.json();
    return {
      running: h.worker_alive !== false,
      reachable: true,
      version: h.version,
      sources: h.sources_with_data,
      databases: h.databases || null,
      backend,
    };
  } catch (_) {
    return { running: false, reachable: false, backend };
  }
}
