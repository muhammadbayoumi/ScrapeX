// Side-panel startup primitives. Marks stay in the document for DevTools and
// are also copied to the service worker's short-lived session trace so host
// opening and document startup share one clock. No account data is included.

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
  // THE ONLY DEADLINE HERE DERIVED FROM A MEASUREMENT INSTEAD OF CHOSEN, because
  // POST /api/bundle does not stream. The engine copies the warehouse, exports
  // every dataset, hashes each file, zips the lot and hashes that -- all before
  // it writes a first byte -- so this bound is the WHOLE JOB, not the time to
  // answer. Every other rule below bounds a reply that starts arriving at once.
  //
  // MEASURED on the owner's machine 2026-08-29: warehouse 1,490 MB, build 71 s,
  // pack 33 s, 104 s in total, archive 372.6 MB. It was running under
  // `localMutation: 10000`, so the panel reported failure on a backup that had
  // SUCCEEDED -- the engine finished 94 seconds after the panel gave up, because
  // aborting a fetch cancels nothing on the far side of it.
  //
  // 600000 is 5.8x that measurement and covers a warehouse near 8.5 GB, more than
  // this machine has free -- so the disk runs out before the deadline does. THAT
  // DERIVATION IS ALSO ITS EXPIRY DATE: the warehouse grew 13x in 17 days, and the
  // real fix is to stop making a browser wait for a synchronous build (R-76).
  bundleBuild: 600000,
  //: A restore moves a multi-gigabyte file aside and another into its place, and
  //: it is bounded by the SAME argument as bundleBuild rather than by a guess:
  //: `POST /api/storage/restore` does not stream, so the deadline has to cover
  //: the whole operation and not just time-to-first-byte. The first defect the
  //: owner reported on 2026-09-02 was exactly this shape -- "The request exceeded
  //: its 10000 ms deadline" on a backup of a 1,490 MB warehouse -- so shipping a
  //: restore under the generic bound would have reproduced it on the one action
  //: that must not be interrupted halfway.
  storageRestore: 600000,
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
  // `(?:\?|$)` and NOT `(?:[/?]|$)` like every other rule, which is the whole
  // point of writing it out: /api/bundle/archive and /api/bundle/panel-pack are
  // FileResponse streams whose headers arrive immediately, and they must keep the
  // fast generic bound. Only the build is slow, so only the build is matched.
  [/^\/api\/bundle(?:\?|$)/, STARTUP_DEADLINES.bundleBuild],
  [/^\/api\/storage\/restore(?:[/?]|$)/, STARTUP_DEADLINES.storageRestore],
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
  // Straight into the document's own chrome.storage.session trace, which emits
  // the matching performance mark itself. This used to be a runtime.sendMessage
  // whose failure was swallowed, so the marks went missing in exactly the case
  // worth recording: a startup that never finishes and a service worker that is
  // not listening.
  //
  // Exactly ONE emitter, deliberately: marking here as well would put two
  // entries under every name, and a timeline that counts each event twice is a
  // timeline nobody can read an ordering out of.
  const trace = globalThis.ScrapeXPanelTrace;
  if (trace) {
    try {
      trace.mark(name, detail);
      return;
    } catch (_) {}
  }
  try {
    const startTime = globalThis.performance.now();
    if (detail === undefined) {
      globalThis.performance.mark(`scrapex:${name}`, {startTime});
    } else {
      globalThis.performance.mark(`scrapex:${name}`, {startTime, detail});
    }
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

    // A HIDDEN DOCUMENT NEVER GETS A FRAME, so waiting for one is waiting for
    // nothing. Measured on the owner's machine, twice, from this file's own
    // trace: the side panel document is created with visibilityState "hidden",
    // rAF is requested at 28ms and does not fire until 2372ms -- the moment
    // Chrome finally marks the document visible. The 250ms fallback does not
    // rescue it either, because timers are throttled in a hidden document too:
    // it fired at 767ms and 1131ms in two runs.
    //
    // So the shell sat ready at 168ms and startup waited ~785ms for a paint
    // opportunity that could not arrive. That wait is OURS, and it is the part
    // of the blank panel this repository can actually fix. It does not make
    // Chrome paint sooner -- nothing here can -- but when Chrome does show the
    // panel, everything behind the first frame is already done instead of
    // starting then.
    if (visibilityState() === "hidden") {
      finish("hidden");
      return;
    }

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
