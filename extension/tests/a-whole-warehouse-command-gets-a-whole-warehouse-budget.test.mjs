// Three native commands read the whole warehouse. Two were judged by a ping's
// five seconds and START_ENGINE by 60 s (#1706, #1094), and the host went on to
// finish what the panel had already reported as not done.
//
// THE DURATIONS BELOW ARE HIS, NOT CHOSEN. Measured 2026-10-17 through the host,
// launched as Chrome launches it, on copies of his 2,232,049,664-byte warehouse:
// UPGRADE_DATABASE up to 146.0 s, CHECK_STARTUP up to 66.8 s cold, and
// START_ENGINE runs that same scan and then waits up to 3.5 s for the port.
// The derivations are at `warehouseCopy` and `integrityScan` in startup.js.

import { test, mock } from "node:test";
import assert from "node:assert/strict";

const SLOWEST_UPGRADE_MS = 146_000;
const SLOWEST_CHECK_MS = 66_800;
const SLOWEST_START_MS = SLOWEST_CHECK_MS + 3_500;

// A host that answers each command after `after` ms, or never when `after` is
// null. Every frame it was sent is kept, so a test can say which were.
function slowHost(after, reply) {
  const sent = [];
  globalThis.chrome = {
    runtime: {
      lastError: null,
      sendNativeMessage(_host, message, callback) {
        sent.push(message.command);
        if (after === null) return;
        setTimeout(() => callback(reply), after);
      },
    },
  };
  return sent;
}

const transport = await import("../transport.js");

// Settled or not, without waiting for it: the clock is the test's, not the host's.
function watch(promise) {
  const seen = {state: "pending"};
  promise.then((value) => Object.assign(seen, {state: "resolved", value}),
               (error) => Object.assign(seen, {state: "rejected", error}));
  return seen;
}

async function advance(ms) {
  mock.timers.tick(ms);
  // Let the callback's promise chain run before anyone reads the outcome.
  for (let turn = 0; turn < 5; turn += 1) await Promise.resolve();
}

for (const [name, call, slowest, reply] of [
  ["UPGRADE_DATABASE", () => transport.upgradeDatabase(), SLOWEST_UPGRADE_MS,
   {ok: true, message: "Applied 3 migrations to engine."}],
  ["CHECK_STARTUP", () => transport.checkStartup(), SLOWEST_CHECK_MS,
   {ok: true, databases: {}}],
  ["START_ENGINE", () => transport.startEngine(), SLOWEST_START_MS,
   {ok: true, confirmed: false}],
]) {
  test(`${name} is still heard when it takes as long as his warehouse took`, async () => {
    mock.timers.enable({apis: ["setTimeout"]});
    try {
      const sent = slowHost(slowest, reply);
      const seen = watch(call());
      await advance(slowest - 1);
      assert.equal(seen.state, "pending",
        `${name} gave up after ${slowest - 1} ms, before the ${slowest} ms his `
        + `warehouse took: ${seen.error && seen.error.message}`);
      await advance(1);
      assert.equal(seen.state, "resolved",
        `${name} answered at ${slowest} ms and the panel did not take the answer`);
      assert.deepEqual(seen.value, reply);
      assert.deepEqual(sent, [name]);
    } finally {
      mock.timers.reset();
    }
  });

  test(`${name} that never answers still ends, as a timeout and not a refusal`, async () => {
    mock.timers.enable({apis: ["setTimeout"]});
    try {
      slowHost(null);
      const seen = watch(call());
      // An hour is past any budget here; the point is that one exists.
      await advance(60 * 60 * 1000);
      assert.equal(seen.state, "rejected", `${name} waits for ever on a silent host`);
      assert.equal(seen.error.kind, "timeout",
        "a host that never answered is reported as something other than silence, "
        + "which is what the panel needs to tell 'not changed' from 'no answer yet'");
    } finally {
      mock.timers.reset();
    }
  });
}

test("a ping is still judged by a ping's budget", async () => {
  // THE OTHER HALF OF THE BOUNDARY. Only the commands that read the warehouse
  // were given long budgets; the launcher toggle answers from a file, and a
  // silent host there must still be reported in seconds, not minutes.
  mock.timers.enable({apis: ["setTimeout"]});
  try {
    slowHost(null);
    const seen = watch(transport.autostartStatus());
    await advance(5_000);
    assert.equal(seen.state, "rejected");
    assert.equal(seen.error.kind, "timeout");
  } finally {
    mock.timers.reset();
  }
});

test("every request that copies the warehouse first has the one budget that fits it", async () => {
  // #1706's third surface: Erase data copies the warehouse and then deletes (6.15 s
  // measured), and fell to the `sources` rule's 5 s. The upgrade's engine door had a
  // restart's 15 s for work measured at up to 146 s.
  const {deadlineForLocalRequest, STARTUP_DEADLINES} = await import("../startup.js");
  for (const path of ["/api/databases/upgrade", "/api/sources/AHRAMBC/wipe",
                      "/api/sources/GPP%20ENERGY/wipe"]) {
    assert.equal(deadlineForLocalRequest(path, "POST"), STARTUP_DEADLINES.warehouseCopy, path);
  }
  assert.ok(STARTUP_DEADLINES.warehouseCopy >= 2 * SLOWEST_UPGRADE_MS,
    "the budget no longer covers twice the slowest upgrade measured on his warehouse");
  // AND ONLY THOSE. The rows the wipe row sits above keep a page of rows' bound.
  assert.equal(deadlineForLocalRequest("/api/sources"), STARTUP_DEADLINES.destinationData);
  assert.equal(deadlineForLocalRequest("/api/sources/AHRAMBC"), STARTUP_DEADLINES.destinationData);
  assert.equal(deadlineForLocalRequest("/api/sources/AHRAMBC/wipe-log"),
               STARTUP_DEADLINES.destinationData);
});
