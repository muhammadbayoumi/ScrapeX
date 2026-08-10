import { test } from "node:test";
import assert from "node:assert/strict";

import {
  STARTUP_DEADLINES,
  deadlineForLocalRequest,
  fetchWithDeadline,
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
