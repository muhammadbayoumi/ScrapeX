// Shared engine-detection helper for popup + onboarding.
import { PROTOCOL_VERSION } from "./transport.js";
import { fetchWithDeadline, isTimeoutError, STARTUP_DEADLINES } from "./startup.js";

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
export async function checkEngine({backend = null, signal = null,
                                   timeoutMs = STARTUP_DEADLINES.engineHealth} = {}) {
  const target = (backend || await getBackend()).replace(/\/+$/, "");
  try {
    const res = await fetchWithDeadline(
      fetch, target + "/api/health", {}, timeoutMs, [signal],
    );
    if (!res.ok) return { running: false, reachable: true, backend: target };
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
      // WHICH CODE THE ENGINE IS RUNNING, which `version` cannot say: ten
      // different trees report "0.3.0", so the number tells us what the engine
      // advertises and never what it is. `null` for an engine from before this
      // field existed — the same treatment `protocol_version` gets two blocks up,
      // and for the same reason: an engine too old to answer is not an engine
      // reporting a fault.
      build: h.build || null,
      // THE BANNER THAT COULD NOT APPEAR. The engine has published
      // `schema_lag` on every health answer since the schema gate was
      // built (scrapex/webui/app.py), and app.js renders it in full —
      // "Database is behind the engine", what breaks, and what fixes it.
      // The one thing missing was this line: `checkEngine` did not carry
      // the field, so `renderSchemaLag(engine.schema_lag)` was handed
      // `undefined` on every call and its own guard hid the banner every
      // time. Correct on both sides, load-bearing on nothing.
      //
      // `|| null` like `build` and `databases` above, and for the same
      // reason: an engine too old to answer is not an engine reporting a
      // fault, and the renderer treats absent and clean alike.
      //
      // THE ENGINE'S OWN KEY, not a camelCased one, so the single reader
      // (`renderSchemaLag(engine.schema_lag)` in app.js) needs no edit. The
      // rename is the kind of tidying that turns a one-line repair into a
      // two-file diff for no behaviour.
      schema_lag: h.schema_lag || null,
      backend: target,
    };
  } catch (error) {
    return {
      running: false,
      reachable: false,
      timedOut: isTimeoutError(error),
      cancelled: Boolean(signal?.aborted) && !isTimeoutError(error),
      backend: target,
    };
  }
}
