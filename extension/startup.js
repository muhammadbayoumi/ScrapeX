// Side-panel startup primitives. They are deliberately local: marks never
// leave the document and deadlines/cancellation carry no user data.

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
  try {
    if (detail === undefined) globalThis.performance.mark(`scrapex:${name}`);
    else globalThis.performance.mark(`scrapex:${name}`, {detail});
  } catch (_) {}
}

export function afterNextPaint() {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame !== "function") {
      setTimeout(resolve, 0);
      return;
    }
    // A promise resolved inside rAF continues in a microtask before that frame
    // paints. Hop to the next task so the static shell actually reaches pixels
    // before account/Engine work begins.
    requestAnimationFrame(() => setTimeout(resolve, 0));
  });
}

export function afterIdle(callback, timeout = 750) {
  if (typeof globalThis.requestIdleCallback === "function") {
    return globalThis.requestIdleCallback(callback, {timeout});
  }
  return setTimeout(callback, 0);
}
