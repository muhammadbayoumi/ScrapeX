/**
 * WITH NOTHING RUNNING, ONE SMALL READ EVERY 30 SECONDS — AND NO PATH THAT ENDS IT.
 *
 * The idle probe is the only thing that notices a job the scheduler starts while the
 * panel is open. Two paths left no timer at all, so the panel went quiet for good:
 *
 * - a failed tick with nothing known to be active: the back-off is for a job he is
 *   watching, and the probe was never armed in its place;
 * - a probe that fired while the engine was down: it returned without re-arming, and
 *   the engine coming back up starts no poll of its own (`setStatus`).
 *
 * HOW IT IS TESTED. As `the-crawl-hands-off-to-its-interpretation.test.mjs` does: read
 * `app.js` as text, pull the two functions out by name, and run them over stubbed IO and
 * a timer queue this file owns, so "a timer is armed" is a fact read, not a wait.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

function extract(name, pattern) {
  const match = SOURCE.match(pattern);
  assert.ok(match, `${name} is no longer where this guard reads it from in app.js`);
  return match[0];
}

const ARM_IDLE_PROBE = extract("armIdleProbe", /^function armIdleProbe\(\) \{[\s\S]*?^\}/m);
const POLL_JOB_ONCE = extract(
  "pollJobOnce", /^async function pollJobOnce\(\) \{[\s\S]*?^\}/m);

/** The two functions over a scope built here. `timers` holds what is armed, by delay. */
function runner({ engineUp = true, tick, probe = async () => ({ jobs: [] }), activeBefore }) {
  const timers = [];
  const seen = { polls: 0, reads: [], probe };
  const state = { engineUp, job: null, jobRef: null };
  const api = async (path) => {
    seen.reads.push(path);
    return path.endsWith("&limit=1") ? seen.probe() : tick();
  };
  // eslint-disable-next-line no-new-func
  const build = new Function(
    "api", "state", "document", "setTimeout", "clearTimeout", "pollJob", "activeBefore",
    "let pollTimer = null, idleTimer = null, pollFailures = 0, lastActiveRefs = activeBefore;\n"
      + "const POLL_BACKOFF_MS = [1500, 3000], JOBS_LIMIT = 200, IDLE_PROBE_MS = 30000;\n"
      + "const renderMiniplayer = () => {}, renderActivity = () => {};\n"
      + ARM_IDLE_PROBE + "\n" + POLL_JOB_ONCE
      + "\nreturn {pollJobOnce, armIdleProbe};");
  const built = build(
    api, state, { visibilityState: "visible" },
    (fn, ms) => { const timer = { fn, ms, live: true }; timers.push(timer); return timer; },
    (timer) => { if (timer) timer.live = false; },
    () => { seen.polls += 1; },
    activeBefore);
  const armed = () => timers.filter((timer) => timer.live);
  /** Fire the one armed timer, as the clock reaching it would. */
  const fire = async () => {
    const [timer] = armed();
    assert.ok(timer, "nothing is armed: the panel has stopped asking");
    timer.live = false;
    await timer.fn();
  };
  return { ...built, state, seen, armed, fire };
}

const refused = async () => { throw new Error("engine did not answer"); };

test("a failed tick with nothing active arms the idle probe", async () => {
  const run = runner({ tick: refused, activeBefore: new Set() });
  await run.pollJobOnce();
  assert.deepEqual(run.armed().map((timer) => timer.ms), [30000],
    "a failed tick with no job to back off for left no timer at all");
});

test("a failed tick before any read has answered arms the idle probe too", async () => {
  const run = runner({ tick: refused, activeBefore: null });
  await run.pollJobOnce();
  assert.deepEqual(run.armed().map((timer) => timer.ms), [30000]);
});

test("a failed tick while a job is active backs off instead, and arms one timer", async () => {
  const run = runner({ tick: refused, activeBefore: new Set(["job_a"]) });
  await run.pollJobOnce();
  assert.deepEqual(run.armed().map((timer) => timer.ms), [3000],
    "the back-off and the probe must not both run");
});

test("a probe that finds the engine down asks again later, without a read", async () => {
  const run = runner({ engineUp: false, tick: refused, activeBefore: new Set() });
  run.armIdleProbe();
  await run.fire();
  assert.deepEqual(run.seen.reads, [], "a stopped engine is not read");
  assert.deepEqual(run.armed().map((timer) => timer.ms), [30000],
    "the probe gave up while the engine was down, and nothing re-arms it");
  // AND IT RESUMES: the engine back up, the next probe reads, and a job found polls.
  run.state.engineUp = true;
  run.seen.probe = async () => ({ jobs: [{ job_ref: "job_new", status: "queued" }] });
  await run.fire();
  assert.deepEqual(run.seen.reads, ["/api/jobs?active_only=true&limit=1"]);
  assert.equal(run.seen.polls, 1);
  assert.deepEqual(run.armed(), [], "a probe that found a job hands over to the tick");
});

test("a probe that finds nothing with the engine up asks again in 30 seconds", async () => {
  const run = runner({ tick: refused });
  run.armIdleProbe();
  await run.fire();
  assert.deepEqual(run.seen.reads, ["/api/jobs?active_only=true&limit=1"]);
  assert.deepEqual(run.armed().map((timer) => timer.ms), [30000]);
});
