// Where the engine is, and how a page asks it. ONE expression of both.
//
// WHY THIS IS ITS OWN FILE, extracted from app.js on 2026-08-15. The panel was
// the only surface that talked to the engine, so the address, the abort
// lifetime, the request deadlines and the JSON error shape all lived inside a
// six-thousand-line module as private state. The Console proved a second page
// is cheap; the Data page (plan B2) needs the same five things. Copying them
// would put the rules for reaching the engine in two places, and the day they
// disagree is the day one surface times out where the other retries.
//
// WHAT BELONGS HERE: the backend's address, the controller its requests hang
// off, and the policy every local call obeys. WHAT DOES NOT: anything about a
// particular page's screens or state machine. The line is "would a second page
// need this?" — `engineGeneration` and `accountGeneration` stayed in the panel
// because they count the PANEL's own in-flight work.
//
// THE PAGE LIFETIME IS SHARED, NOT THE PAGE. `pageController` is created once
// per page because each page loads its own instance of this module — the panel
// imports it as `panelController` and nothing at its sixteen call sites moved.

import { getBackend } from "./engine.js";
import { deadlineForLocalRequest, fetchWithDeadline, markStartup }
  from "./startup.js";

// Captured BEFORE the override below, and before any page code runs: this
// module's body executes first because app.js imports it.
const nativeFetch = window.fetch.bind(window);

/** This page's whole lifetime. Aborted once, when the page stops working. */
export const pageController = new AbortController();

/**
 * The requests belonging to the CURRENT backend. Replaced rather than reused
 * when the address changes, so answers from the old engine cannot land in a
 * panel now pointed at a new one.
 */
let backendController = new AbortController();
let activeBackend = "";
let generation = 0;
let firstDestinationDataMarked = false;
const onChange = [];

/**
 * How many times the backend has changed.
 *
 * A FUNCTION, NOT AN EXPORTED VARIABLE, and the difference is not style: an
 * imported binding cannot be assigned from the importing module, so a caller
 * that read it as a value would silently hold a stale copy of a counter whose
 * whole purpose is to go stale.
 */
export const backendGeneration = () => generation;

/** The signal every request to the current backend hangs off. */
export const backendSignal = () => backendController.signal;

/** Cancel everything in flight to the current backend. */
export function abortBackend() { backendController.abort(); }

/**
 * Run `fn` whenever the backend address changes.
 *
 * The panel uses this to invalidate its own engine-check generation. That bump
 * used to sit inside `activateBackend`, which meant this file would have had to
 * know about a counter that is none of its business.
 */
export function whenBackendChanges(fn) { onChange.push(fn); }

export function activateBackend(url) {
  const clean = String(url || "").replace(/\/+$/, "");
  if (clean === activeBackend) return clean;
  backendController.abort();
  backendController = new AbortController();
  activeBackend = clean;
  generation += 1;
  for (const listener of onChange) listener(generation);
  return clean;
}

export async function backendBase() {
  if (activeBackend) return activeBackend;
  return activateBackend(await getBackend());
}

function localApiPath(input) {
  try {
    const url = new URL(String(input), window.location.href);
    if (!url.pathname.startsWith("/api/")) return null;
    if (activeBackend && !String(input).startsWith(activeBackend)) return null;
    return url.pathname + url.search;
  } catch (_) {
    return null;
  }
}

// The shared appearance/timezone modules use fetch directly. Install the same
// endpoint policy beneath them without changing the byte-identical Web UI
// copies of those modules. Calls that already declare a signal keep it.
window.fetch = (input, options = {}) => {
  const path = localApiPath(input);
  if (!path || options.signal) return nativeFetch(input, options);
  const deadline = deadlineForLocalRequest(path, options.method || "GET");
  return fetchWithDeadline(
    nativeFetch, input, options, deadline,
    [pageController.signal, backendController.signal],
  );
};

const DESTINATION_DATA_PATH =
  /^\/api\/(?:sources|outputs|jobs|resolve|records|changes|schedules|storage|settings|fields|rates)(?:[/?]|$)/;

export async function api(path, options = {}) {
  const backend = await backendBase();
  const method = options.method || "GET";
  const deadlineMs = options.deadlineMs || deadlineForLocalRequest(path, method);
  const requestOptions = {...options};
  delete requestOptions.deadlineMs;
  if (!firstDestinationDataMarked && DESTINATION_DATA_PATH.test(path)) {
    firstDestinationDataMarked = true;
    markStartup("first-destination-data-request", {path});
  }
  const res = await fetchWithDeadline(
    window.fetch, backend + path, requestOptions, deadlineMs,
    [pageController.signal, backendController.signal],
  );
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw Object.assign(new Error(detail), {status: res.status, kind: "http"});
  }
  return res.json();
}

export const post = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body || {}),
});

export const del = (path) => api(path, { method: "DELETE" });
