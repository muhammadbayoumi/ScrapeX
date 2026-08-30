import { test } from "node:test";
import assert from "node:assert/strict";

import {
  afterNextPaint,
  STARTUP_DEADLINES,
  STARTUP_PAINT_FALLBACK_MS,
  deadlineForLocalRequest,
  fetchWithDeadline,
  markStartup,
} from "../startup.js";

function pendingFetch(_input, {signal}) {
  return new Promise((_resolve, reject) => {
    const stop = () => reject(signal.reason);
    if (signal.aborted) stop();
    else signal.addEventListener("abort", stop, {once: true});
  });
}

test("local endpoints receive purpose-specific deadlines", () => {
  assert.equal(deadlineForLocalRequest("/api/health"), STARTUP_DEADLINES.engineHealth);
  assert.equal(deadlineForLocalRequest("/api/version?extension_version=1"),
               STARTUP_DEADLINES.engineVersion);
  assert.equal(deadlineForLocalRequest("/api/ui"), STARTUP_DEADLINES.uiContract);
  assert.equal(deadlineForLocalRequest("/api/appearance"), STARTUP_DEADLINES.preferences);
  assert.equal(deadlineForLocalRequest("/api/timezone"), STARTUP_DEADLINES.preferences);
  assert.equal(deadlineForLocalRequest("/api/sources"), STARTUP_DEADLINES.destinationData);
  assert.equal(deadlineForLocalRequest("/api/unknown"), STARTUP_DEADLINES.localGeneric);
  assert.equal(deadlineForLocalRequest("/api/unknown", "POST"),
               STARTUP_DEADLINES.localMutation);
  assert.equal(deadlineForLocalRequest("/api/engine/restart", "POST"),
               STARTUP_DEADLINES.engineRepair);
  assert.equal(deadlineForLocalRequest("/api/bundle", "POST"),
               STARTUP_DEADLINES.bundleBuild);
});

// WHAT WAS MISSING HERE ON 2026-08-29, and the shape of the hole is the lesson.
// The case above had a row for every rule in the table and none for a path that
// matched no rule at all -- so `POST /api/bundle` collected `localMutation:
// 10000` for a job that takes 104 seconds on the owner's warehouse, and the
// panel told him a backup had FAILED while the engine went on to finish it. The
// abort cancelled nothing: the archive was closed 94 seconds later, complete.
//
// The fall-through is a plausible number for a mutation, which is exactly why
// nothing went red. A table like this cannot announce that it has stopped
// covering a route; only a case naming the route can.
test("the bundle build is bounded by the job, and its sub-paths are not", () => {
  assert.equal(deadlineForLocalRequest("/api/bundle", "POST"),
               STARTUP_DEADLINES.bundleBuild);
  assert.equal(deadlineForLocalRequest("/api/bundle?force=1", "POST"),
               STARTUP_DEADLINES.bundleBuild);

  // THE OVER-MATCH, which is the way this fix could have made things worse.
  // Both of these stream a FileResponse whose headers arrive at once, so the
  // deadline they carry is a real guard on a fast route. Writing the rule with
  // `(?:\?|$)` instead of the usual `(?:[/?]|$)` is what keeps them out of it.
  assert.equal(deadlineForLocalRequest("/api/bundle/archive"),
               STARTUP_DEADLINES.localGeneric);
  assert.equal(deadlineForLocalRequest("/api/bundle/panel-pack"),
               STARTUP_DEADLINES.localGeneric);
  assert.notEqual(STARTUP_DEADLINES.bundleBuild, STARTUP_DEADLINES.localMutation);
});

// A floor, not an equality: the number is expected to be revisited, and what is
// worth refusing is a revision that puts it back under the job it bounds. The
// ceiling is here because a bound this long is a STOPGAP -- the panel shows no
// progress for its whole duration, and R-76 records that the real fix is to stop
// making a browser wait on a synchronous build at all.
test("the bundle deadline still clears the measurement it was derived from", () => {
  assert.ok(STARTUP_DEADLINES.bundleBuild >= 300000,
            `bundleBuild is ${STARTUP_DEADLINES.bundleBuild} ms; the build was ` +
            "measured at 104000 ms on 2026-08-29 with a 1,490 MB warehouse");
  assert.ok(STARTUP_DEADLINES.bundleBuild <= 900000);
});

test("a nonresponsive request ends at its declared deadline", async () => {
  const started = globalThis.performance.now();
  await assert.rejects(
    fetchWithDeadline(pendingFetch, "/api/blackhole", {}, 25),
    (error) => error && error.name === "TimeoutError",
  );
  const elapsed = globalThis.performance.now() - started;
  assert.ok(elapsed >= 15, `deadline fired implausibly early (${elapsed}ms)`);
  assert.ok(elapsed < 250, `deadline was not enforced promptly (${elapsed}ms)`);
});

test("an owner cancellation aborts a request before its deadline", async () => {
  const owner = new AbortController();
  const request = fetchWithDeadline(pendingFetch, "/api/cancel", {}, 1000,
                                    [owner.signal]);
  owner.abort(new globalThis.DOMException("panel closed", "AbortError"));
  await assert.rejects(request, (error) => error && error.name === "AbortError");
});

test("every startup deadline is finite and positive", () => {
  for (const [name, value] of Object.entries(STARTUP_DEADLINES)) {
    assert.ok(Number.isFinite(value) && value > 0, `${name} has no finite deadline`);
  }
});

test("app startup marks land in the persistent document trace", () => {
  // These used to be runtime.sendMessage calls whose failure was swallowed, so
  // they went missing in the one case worth recording: a startup that never
  // finishes and a service worker that is not listening.
  const marked = [];
  const originalTrace = globalThis.ScrapeXPanelTrace;
  globalThis.ScrapeXPanelTrace = {
    mark(name, detail) { marked.push({name, detail}); },
  };
  try {
    markStartup("account-check-start", {interactive: false});
  } finally {
    if (originalTrace === undefined) delete globalThis.ScrapeXPanelTrace;
    else globalThis.ScrapeXPanelTrace = originalTrace;
  }

  assert.deepEqual(marked, [
    {name: "account-check-start", detail: {interactive: false}},
  ]);
});

test("a startup mark without a trace present still never throws", () => {
  const originalTrace = globalThis.ScrapeXPanelTrace;
  delete globalThis.ScrapeXPanelTrace;
  try {
    assert.doesNotThrow(() => markStartup("account-check-start", {interactive: false}));
  } finally {
    if (originalTrace === undefined) delete globalThis.ScrapeXPanelTrace;
    else globalThis.ScrapeXPanelTrace = originalTrace;
  }
});

test("startup takes the bounded fallback when an animation frame never runs", async () => {
  let blockedFrame;
  let cancelledHandle;
  const started = globalThis.performance.now();
  const result = await afterNextPaint({
    timeoutMs: 20,
    requestFrame: (callback) => {
      blockedFrame = callback;
      return 17;
    },
    cancelFrame: (handle) => { cancelledHandle = handle; },
  });
  const elapsed = globalThis.performance.now() - started;

  assert.equal(result.source, "timer");
  assert.equal(cancelledHandle, 17);
  assert.equal(typeof blockedFrame, "function");
  assert.ok(elapsed >= 10, `fallback fired implausibly early (${elapsed}ms)`);
  assert.ok(elapsed < 250, `blocked frame held startup (${elapsed}ms)`);
  assert.equal(STARTUP_PAINT_FALLBACK_MS, 100);
});

test("startup uses a frame when available and still resolves only once", async () => {
  let frameCallback;
  let cancellationCount = 0;
  const resultPromise = afterNextPaint({
    timeoutMs: 100,
    requestFrame: (callback) => {
      frameCallback = callback;
      return 23;
    },
    cancelFrame: () => { cancellationCount += 1; },
  });

  frameCallback(12.5);
  const result = await resultPromise;
  frameCallback(18.5);

  assert.deepEqual(result, {source: "frame"});
  assert.equal(cancellationCount, 0);
});

test("closing the panel cancels a pending paint opportunity", async () => {
  const owner = new AbortController();
  let cancelledHandle;
  const resultPromise = afterNextPaint({
    signal: owner.signal,
    timeoutMs: 1000,
    requestFrame: () => 31,
    cancelFrame: (handle) => { cancelledHandle = handle; },
  });
  owner.abort();

  assert.deepEqual(await resultPromise, {source: "cancelled"});
  assert.equal(cancelledHandle, 31);
});
