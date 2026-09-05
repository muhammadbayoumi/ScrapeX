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
  /^\/api\/(?:sources|outputs|jobs|enrichment|resolve|records|changes|schedules|storage|settings|fields|rates)(?:[/?]|$)/;

/**
 * Every guarantee a request to the engine gets, and nothing about the body.
 *
 * EXTRACTED BECAUSE TWO CALLERS THREW THE STATUS AWAY. `extension/app.js` read
 * the Drive bundle's archive and panel-pack with a BARE `fetch(...).blob()`,
 * because `api()` ends in `res.json()` and a zip is not JSON. So the one request
 * in the product that moves half a gigabyte was the one request that could not
 * report why it failed.
 *
 * AND THE DEADLINE WAS NEVER THE MISSING PART — that was said here and it was
 * wrong. `window.fetch` is overridden above, and `localApiPath` matches any URL
 * under the active backend beginning `/api/`, so those bare calls already ran
 * through `fetchWithDeadline` with `deadlineForLocalRequest` and both abort
 * signals. What they lacked was the STATUS CHECK and the detail that comes with
 * it. Naming the wrong absence sends the next reader to the wrong layer: the
 * override is load-bearing for anything that calls `fetch` directly, and someone
 * told it does nothing for `/api/` is free to delete it.
 *
 * MEASURED ON HIS MACHINE, 2026-09-03: the engine built
 * `scrapex-bundle-20260903-131501.zip` at 541,531,989 bytes, the file was
 * complete on disk with no `.part` beside it, and the panel read **0**. The guard
 * added on 2026-08-30 refused the upload — correctly — but the message could only
 * say "this panel read 0", because the status was thrown away by the line that
 * read it. A build of 378,655,878 bytes had succeeded four days earlier.
 *
 * So the shape is one function that owns the request and two that own the parse.
 * A third caller cannot now acquire a bare fetch by needing a different body.
 */
async function request(path, options = {}) {
  const backend = await backendBase();
  const method = options.method || "GET";
  const deadlineMs = options.deadlineMs || deadlineForLocalRequest(path, method);
  const requestOptions = {...options};
  delete requestOptions.deadlineMs;
  const throwOnHttpError = requestOptions.throwOnHttpError !== false;
  delete requestOptions.throwOnHttpError;
  if (!firstDestinationDataMarked && DESTINATION_DATA_PATH.test(path)) {
    firstDestinationDataMarked = true;
    markStartup("first-destination-data-request", {path});
  }
  const res = await fetchWithDeadline(
    window.fetch, backend + path, requestOptions, deadlineMs,
    [pageController.signal, backendController.signal],
  );
  if (!res.ok && throwOnHttpError) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw Object.assign(new Error(detail), {status: res.status, kind: "http"});
  }
  return res;
}

export async function api(path, options = {}) {
  return (await request(path, options)).json();
}

/**
 * The same request, read as bytes.
 *
 * The `blob()` call can still fail on its own — a browser refusing to hold half
 * a gigabyte in memory raises HERE, after a 200 — and that is a different failure
 * from a 404 or a timeout. It is left to raise rather than be flattened into an
 * empty blob, so the caller's message can say which happened.
 */
export async function bytes(path, options = {}) {
  return (await request(path, options)).blob();
}

/**
 * The response itself, for the callers that have to READ the status.
 *
 * `api()` and `bytes()` turn a non-2xx into an error, which is right for almost
 * everything and wrong for four calls that BRANCH on it: `/api/databases/upgrade`
 * and `/api/engine/restart` treat a 404 as "this engine is too old" rather than as
 * a failure, and the restart poll asks `/api/health` repeatedly and needs a refusal
 * to be ordinary rather than fatal.
 *
 * THEY WERE BARE FETCHES, AND THAT WAS THE WRONG READING OF WHY. They did not need
 * to escape the request path — they needed a different verdict at the end of it.
 * The deadline and the abort signals they already had, from the `window.fetch`
 * override above; what they were missing is a way to say "a 404 here is an
 * answer, not a failure". Routing them through `request()` moves that guarantee
 * from an implicit seam to an explicit one that a test can see.
 *
 * `throwOnHttpError: false` is passed here, and by `sourceFor` and `range` — for
 * which a 206 is the SUCCESS case, not an error. What is pinned is the LOCATION,
 * not the count: the opt-out exists in this file and no call site outside it may
 * pass one, which is what the guard on it actually checks.
 */
export async function raw(path, options = {}) {
  return request(path, {...options, throwOnHttpError: false});
}

/**
 * Bytes `[start, end)` of a path the engine serves, and never more than that.
 *
 * WHY THIS EXISTS. `bytes()` reads a whole body into memory, which is fine for a
 * 4 MB panel-pack and is what failed on a 541,531,989-byte archive: a Chrome side
 * panel asked to hold half a gigabyte in one Blob, and the read came back empty.
 * Measured on his machine 2026-09-03 — the file was complete on disk and the panel
 * read 0. A 378 MB build had worked four days earlier, so the ceiling was somewhere
 * between them and moves with the browser rather than with this code.
 *
 * So the archive is never held whole. `drive.js` already uploads in 4 MB chunks
 * with a resumable session; it was slicing them out of a fully-buffered Blob. Now
 * each chunk is fetched as it is sent, so the panel holds ONE chunk however large
 * the warehouse grows.
 *
 * A SHORT CHUNK IS A FAILURE AND SAYS SO. The engine answers `206` with a
 * `Content-Range`, and a body shorter than asked for means the file changed under
 * the upload or the connection truncated — either way the archive being assembled
 * in Drive would be wrong, and wrong quietly. That is the shape the 2026-08-30
 * guard was added for, one level down.
 */
/**
 * A path the engine serves, expressed as something uploadable without holding it.
 *
 * THE SIZE COMES FROM THE ENGINE AND NOT FROM THE MANIFEST, and that is the whole
 * care in this function. `drive.js` `expectSize` exists to compare what the engine
 * DESCRIBED in its POST reply against what ARRIVED — on 2026-08-30 those resolved
 * to different builds and a 0-byte archive went to Drive. Sizing a source from the
 * manifest would make both sides of that comparison the same number and the guard
 * would pass on anything.
 *
 * So the length is read from the `Content-Range` of a one-byte request: `bytes
 * 0-0/541531989`. That is the file the engine will actually serve chunks from,
 * measured by the engine, which is the fact the manifest is being checked against.
 */
export async function sourceFor(path) {
  const res = await request(path, {
    headers: {Range: "bytes=0-0"}, throwOnHttpError: false,
  });
  if (res.status !== 206) {
    // A 200 here means the WHOLE archive is already on its way. Drop the body
    // rather than read it: materialising half a gigabyte is the exact failure
    // this function exists to avoid, and the caller has a whole-blob path for
    // engines that cannot serve ranges.
    await res.body?.cancel().catch(() => {});
    throw Object.assign(new Error(
      `The engine answered ${res.status} instead of serving a byte range, so the `
      + "archive cannot be uploaded a chunk at a time."),
      {status: res.status, kind: "no-range"});
  }
  const stated = /\/(\d+)\s*$/.exec(res.headers.get("content-range") || "");
  if (!stated) {
    throw new Error(
      "The engine served a byte range without saying how long the file is, so "
      + "there is nothing to check the manifest against.");
  }
  const size = Number(stated[1]);
  // PIN THE REPRESENTATION FOR THE WHOLE UPLOAD.
  //
  // `/api/bundle/archive` re-resolves "the newest zip on disk" on EVERY request
  // (scrapex/webui/app.py:3253), and 541,531,989 bytes is ~130 requests spread
  // over minutes. A second panel window -- side panels are per window, so that
  // is a second document -- taking a backup mid-upload finishes a new build, and
  // every chunk after it comes from a DIFFERENT file. The length guard below
  // cannot see that: if the new archive is longer, each chunk is still exactly
  // the size asked for, the total still matches, and the check button then
  // reports a spliced archive as complete.
  //
  // The engine already hands us what closes it. Measured against the live engine
  // on 2026-09-05, the one-byte probe answers:
  //     ETag: "c9d60b0b9a6ebd8b8d6e89b2612898fd"
  //     Content-Range: bytes 0-0/541531989
  // Starlette's FileResponse._should_use_range compares If-Range against the etag
  // OR the last-modified and answers 200 with the whole body when neither still
  // matches -- which `range` turns into a named, loud failure.
  const validator = res.headers.get("etag") || res.headers.get("last-modified");
  return {
    size,
    chunk: (start, end) => range(path, start, end, {total: size, validator}),
  };
}


export async function range(path, start, end, {total = null, validator = null} = {}) {
  const wanted = end - start;
  const headers = {Range: `bytes=${start}-${end - 1}`};
  // If-Range is what makes a swapped file ANSWERABLE. Without it the engine
  // happily serves byte 40,000,000 of whatever archive is newest now, and this
  // side has no way to tell that from byte 40,000,000 of the one it started on.
  if (validator) headers["If-Range"] = validator;
  const res = await request(path, {headers, throwOnHttpError: false});
  if (res.status !== 206 && res.status !== 200) {
    throw Object.assign(
      new Error(`The engine answered ${res.status} for bytes ${start}-${end - 1}.`),
      {status: res.status, kind: "http"});
  }
  if (validator && res.status === 200) {
    await res.body?.cancel().catch(() => {});
    throw Object.assign(new Error(
      "The archive on the engine changed while it was being uploaded, so the copy "
      + "in Drive would be part of one backup and part of another. Nothing was "
      + "finished. Take the backup again, and let it run on its own."),
      {kind: "changed-under-upload"});
  }
  // The total on every 206 costs nothing and is INDEPENDENT of the length asked
  // for, so it catches a swap that If-Range could not -- an engine that does not
  // send validators, or one whose etag survives a rebuild.
  const said = /\/(\d+)\s*$/.exec(res.headers.get("content-range") || "");
  if (total !== null && said && Number(said[1]) !== total) {
    await res.body?.cancel().catch(() => {});
    throw Object.assign(new Error(
      `The archive was ${total} bytes when this upload started and the engine now `
      + `says it is ${said[1]}, so it was rebuilt underneath. Nothing was `
      + "finished. Take the backup again."), {kind: "changed-under-upload"});
  }
  const chunk = await res.blob();
  if (chunk.size !== wanted) {
    throw Object.assign(new Error(
      `Asked the engine for ${wanted} bytes at ${start} and read ${chunk.size}. `
      + "The file changed under the upload or the read was cut short; what is in "
      + "Drive would be wrong."), {kind: "short-read"});
  }
  return chunk;
}

export const post = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body || {}),
});

export const del = (path) => api(path, { method: "DELETE" });
