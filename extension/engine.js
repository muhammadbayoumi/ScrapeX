// Shared engine-detection helper for popup + onboarding.
import { PROTOCOL_VERSION } from "./transport.js";

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
    // A mismatch is reported, never guessed at — the same rule the native path
    // has always followed, on the path that actually carries the data. An
    // engine too old to state a version at all is not a mismatch: it is an
    // engine from before this field existed, and it is left alone.
    const engineProtocol = h.protocol_version;
    const protocolMismatch =
      engineProtocol !== undefined && engineProtocol !== PROTOCOL_VERSION;
    return {
      running: h.worker_alive !== false,
      reachable: true,
      version: h.version,
      protocolMismatch,
      engineProtocol,
      clientProtocol: PROTOCOL_VERSION,
      sources: h.sources_with_data,
      databases: h.databases || null,
      backend,
    };
  } catch (_) {
    return { running: false, reachable: false, backend };
  }
}
