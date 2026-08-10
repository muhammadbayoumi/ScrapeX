// Side-panel startup primitives. Marks stay in the document for DevTools and
// are also copied to the service worker's short-lived session trace so host
// opening and document startup share one clock. No account data is included.

const STARTUP_EVENT = "scrapex-side-panel-startup-event";

export const STARTUP_DEADLINES = Object.freeze({
  silentToken: 2500,
  interactiveToken: 120000,
  accountDetails: 6000,
  engineHealth: 2500,
  engineVersion: 2500,
  uiContract: 2000,
  preferences: 2500,
  destinationData: 5000,
  localMutation: 10000,
  engineRepair: 15000,
  localGeneric: 5000,
});

// A new Side Panel document can exist before Chrome considers it active enough
// to service animation frames. Startup may offer the renderer a frame, but the
// Account and Engine checks must never wait indefinitely for one.
export const STARTUP_PAINT_FALLBACK_MS = 100;

const LOCAL_POLICIES = [
  [/^\/api\/(?:engine\/)?health(?:[/?]|$)/, STARTUP_DEADLINES.engineHealth],
  [/^\/api\/version(?:[/?]|$)/, STARTUP_DEADLINES.engineVersion],
  [/^\/api\/ui(?:[/?]|$)/, STARTUP_DEADLINES.uiContract],
  [/^\/api\/(?:appearance|timezone)(?:[/?]|$)/, STARTUP_DEADLINES.preferences],
  [/^\/api\/(?:engine\/restart|databases\/upgrade)(?:[/?]|$)/,
    STARTUP_DEADLINES.engineRepair],
  [/^\/api\/(?:sources|outputs|jobs|resolve|records|changes|schedules|storage|settings|fields|rates)(?:[/?]|$)/,
    STARTUP_DEADLINES.destinationData],
];

export function deadlineForLocalRequest(path, method = "GET") {
  const normalizedMethod = String(method || "GET").toUpperCase();
  for (const [pattern, deadline] of LOCAL_POLICIES) {
    if (pattern.test(path)) return deadline;
  }
  return normalizedMethod === "GET"
    ? STARTUP_DEADLINES.localGeneric
    : STARTUP_DEADLINES.localMutation;
}

export function isTimeoutError(error) {
  return Boolean(error && ["TimeoutError", "DeadlineExceededError"].includes(error.name));
}

function abortError(name, message) {
  try { return new globalThis.DOMException(message, name); }
  catch (_) { return Object.assign(new Error(message), {name}); }
}

/** Fetch with one deadline and any number of owner/lifecycle cancellation signals. */
export async function fetchWithDeadline(
  fetchImpl, input, init = {}, deadlineMs, ownerSignals = [],
) {
  if (!Number.isFinite(deadlineMs) || deadlineMs <= 0) {
    throw new TypeError("A positive request deadline is required.");
  }

  const controller = new AbortController();
  const signals = [init.signal, ...ownerSignals].filter(Boolean);
  const listeners = [];
  const abortFrom = (signal) => {
    if (controller.signal.aborted) return;
    controller.abort(signal.reason || abortError("AbortError", "The request was cancelled."));
  };
  for (const signal of signals) {
    if (signal.aborted) abortFrom(signal);
    else {
      const listener = () => abortFrom(signal);
      signal.addEventListener("abort", listener, {once: true});
      listeners.push([signal, listener]);
    }
  }

  const timer = setTimeout(() => {
    if (!controller.signal.aborted) {
      controller.abort(abortError(
        "TimeoutError", `The request exceeded its ${deadlineMs} ms deadline.`,
      ));
    }
  }, deadlineMs);

  try {
    return await fetchImpl(input, {...init, signal: controller.signal});
  } finally {
    clearTimeout(timer);
    listeners.forEach(([signal, listener]) =>
      signal.removeEventListener("abort", listener));
  }
}

export function markStartup(name, detail) {
  const startTime = globalThis.performance.now();
  try {
    if (detail === undefined) {
      globalThis.performance.mark(`scrapex:${name}`, {startTime});
    } else {
      globalThis.performance.mark(`scrapex:${name}`, {startTime, detail});
    }
  } catch (_) {}
  try {
    const delivery = globalThis.chrome?.runtime?.sendMessage({
      type: STARTUP_EVENT,
      event: {
        name,
        at: globalThis.performance.timeOrigin + startTime,
        detail,
      },
    });
    delivery?.catch?.(() => {});
  } catch (_) {}
}

export function afterNextPaint({
  signal,
  timeoutMs = STARTUP_PAINT_FALLBACK_MS,
  requestFrame = globalThis.requestAnimationFrame?.bind(globalThis),
  cancelFrame = globalThis.cancelAnimationFrame?.bind(globalThis),
  setTimer = globalThis.setTimeout.bind(globalThis),
  clearTimer = globalThis.clearTimeout.bind(globalThis),
} = {}) {
  return new Promise((resolve) => {
    let fallbackTimer;
    let frameTask;
    let frameHandle;
    let settled = false;
    const visibilityState = () => typeof document === "undefined"
      ? "unavailable"
      : document.visibilityState;
    const finish = (source) => {
      if (settled) return;
      settled = true;
      if (fallbackTimer !== undefined) clearTimer(fallbackTimer);
      if (frameTask !== undefined) clearTimer(frameTask);
      if (source !== "frame" && frameHandle !== undefined
          && typeof cancelFrame === "function") {
        cancelFrame(frameHandle);
      }
      signal?.removeEventListener("abort", abort);
      markStartup("paint-opportunity-resolved", {
        source, visibilityState: visibilityState(),
      });
      resolve({source});
    };
    const abort = () => finish("cancelled");

    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener("abort", abort, {once: true});
    fallbackTimer = setTimer(() => finish("timer"), timeoutMs);

    if (typeof requestFrame !== "function") return;
    markStartup("animation-frame-requested", {
      visibilityState: visibilityState(),
    });
    // A promise resolved inside rAF continues in a microtask before that frame
    // paints. Hop to the next task so the static shell actually reaches pixels
    // before account/Engine work begins. The fallback remains armed across both
    // hops, so neither a deferred frame nor its follow-up task can gate startup.
    try {
      frameHandle = requestFrame((timestamp) => {
        markStartup("animation-frame-resolved", {
          timestamp, visibilityState: visibilityState(),
        });
        frameTask = setTimer(() => finish("frame"), 0);
      });
    } catch (_) {
      // The timer owns the bounded fallback if a renderer rejects the request.
    }
  });
}

export function afterIdle(callback, timeout = 750) {
  if (typeof globalThis.requestIdleCallback === "function") {
    return globalThis.requestIdleCallback(callback, {timeout});
  }
  return setTimeout(callback, 0);
}
