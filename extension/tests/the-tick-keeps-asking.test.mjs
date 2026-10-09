/**
 * THE ONE TICK: HOW OFTEN IT ASKS, WHEN IT STOPS, AND WHAT IT ASKS FOR (#1542).
 *
 * Every rule here is a timer or a count, which a browser test can only wait for. So,
 * as `the-crawl-hands-off-to-its-interpretation.test.mjs` does, this reads `app.js` as
 * text, pulls the functions out by name and runs them over stubbed IO and a timer queue
 * this file owns: "a timer is armed for 3000 ms" is a fact read, not a wait.
 *
 * - A failed tick backs off 1.5, 3, 6, 12, then 30 s while a job is active, and the
 *   first success starts the schedule again.
 * - With nothing active, a failed tick arms the 30 s idle probe instead; and a probe
 *   that finds the engine down asks again later, because the engine coming back up
 *   starts no poll of its own (`setStatus`). Both paths used to leave no timer at all.
 * - A change in the active set, a job starting OR ending, re-reads the Jobs history,
 *   and only while that page is on screen.
 * - The Sources payload a job's name needs is read once per panel, never per tick.
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

// Each function ends on a `}` in column 0, so a lazy match stops at its end.
const BACKOFF = extract("POLL_BACKOFF_MS", /^const POLL_BACKOFF_MS = .*;$/m);
const ARM_IDLE_PROBE = extract("armIdleProbe", /^function armIdleProbe\(\) \{[\s\S]*?^\}/m);
const NOTICE_ACTIVE_SET = extract(
  "noticeActiveSet", /^function noticeActiveSet\(jobs\) \{[\s\S]*?^\}/m);
const SOURCES_FOR_JOB_NAMES = extract(
  "sourcesForJobNames", /^function sourcesForJobNames\(\) \{[\s\S]*?^\}/m);
const POLL_JOB_ONCE = extract(
  "pollJobOnce", /^async function pollJobOnce\(\) \{[\s\S]*?^\}/m);

const LIVE = { job_ref: "job_a", status: "running", source_keys: ["x"] };

/**
 * The tick's functions over a scope built here. `answers` is what each tick read
 * returns in turn: a list of jobs, or `refused`. `timers` holds what is armed.
 */
function runner({ engineUp = true, answers = [], probe = async () => ({ jobs: [] }),
  activeBefore = null, view = "run" } = {}) {
  const timers = [];
  const seen = { polls: 0, reads: [], historyReads: 0, sourceReads: 0, probe, view };
  const state = { engineUp, job: null, jobRef: null, sources: [] };
  const api = async (path) => {
    seen.reads.push(path);
    if (path.endsWith("&limit=1")) return seen.probe();
    if (path.startsWith("/api/jobs?")) {
      const next = answers.shift();
      if (next === refused) throw new Error("engine did not answer");
      return { jobs: next || [] };
    }
    return { entries: [], total: 0 };
  };
  // eslint-disable-next-line no-new-func
  const build = new Function(
    "api", "state", "document", "setTimeout", "clearTimeout", "pollJob", "activeBefore",
    "currentViewName", "loadJobs", "loadSources",
    "let pollTimer = null, idleTimer = null, pollFailures = 0, sourcesForNames = null;\n"
      + "let lastActiveRefs = activeBefore;\n"
      + "const POLL_MS = 1500, JOBS_LIMIT = 200, IDLE_PROBE_MS = 30000;\n"
      + BACKOFF + "\n"
      + "const renderMiniplayer = () => {}, renderActivity = () => {}, renderLogs = () => {};\n"
      + "const refreshRunButton = () => {}, redrawWhatTheJobChanged = async () => {};\n"
      + "const isSettled = (job) => job.status === 'completed';\n"
      + "const liveJob = (jobs) => jobs[0] || null;\n"
      + [ARM_IDLE_PROBE, NOTICE_ACTIVE_SET, SOURCES_FOR_JOB_NAMES, POLL_JOB_ONCE].join("\n")
      + "\nreturn {pollJobOnce, armIdleProbe, noticeActiveSet, sourcesForJobNames};");
  const built = build(
    api, state, { visibilityState: "visible" },
    (fn, ms) => { const timer = { fn, ms, live: true }; timers.push(timer); return timer; },
    (timer) => { if (timer) timer.live = false; },
    () => { seen.polls += 1; },
    activeBefore,
    () => seen.view,
    () => { seen.historyReads += 1; },
    () => { seen.sourceReads += 1; return Promise.resolve(); });
  const armed = () => timers.filter((timer) => timer.live).map((timer) => timer.ms);
  /** Fire the one armed timer, as the clock reaching it would. */
  const fire = async () => {
    const live = timers.filter((timer) => timer.live);
    assert.equal(live.length, 1, `expected one armed timer, found ${live.length}`);
    live[0].live = false;
    await live[0].fn();
  };
  return { ...built, state, seen, armed, fire };
}

const refused = Symbol("refused");

test("failed ticks back off 1.5, 3, 6, 12, then 30 s while a job is active", async () => {
  const run = runner({ answers: Array(6).fill(refused), activeBefore: new Set(["job_a"]) });
  const waits = [];
  for (let i = 0; i < 6; i += 1) {
    await run.pollJobOnce();
    waits.push(...run.armed());
  }
  assert.deepEqual(waits, [1500, 3000, 6000, 12000, 30000, 30000],
    "the schedule the PR states is not the one the code runs");
});

test("the first success starts the back-off again from 1.5 s", async () => {
  const run = runner({ answers: [refused, refused, refused, [LIVE], refused],
    activeBefore: new Set(["job_a"]) });
  for (let i = 0; i < 3; i += 1) await run.pollJobOnce();
  assert.deepEqual(run.armed(), [6000]);
  await run.pollJobOnce();
  assert.deepEqual(run.armed(), [1500], "a live job is followed at POLL_MS");
  await run.pollJobOnce();
  assert.deepEqual(run.armed(), [1500],
    "after a success, one failure waited as if the old failures still counted");
});

test("a failed tick with nothing active arms the idle probe", async () => {
  const run = runner({ answers: [refused], activeBefore: new Set() });
  await run.pollJobOnce();
  assert.deepEqual(run.armed(), [30000],
    "a failed tick with no job to back off for left no timer at all");
});

test("a failed tick before any read has answered arms the idle probe too", async () => {
  const run = runner({ answers: [refused] });
  await run.pollJobOnce();
  assert.deepEqual(run.armed(), [30000]);
});

test("a probe that finds the engine down asks again later, without a read", async () => {
  const run = runner({ engineUp: false });
  run.armIdleProbe();
  await run.fire();
  assert.deepEqual(run.seen.reads, [], "a stopped engine is not read");
  assert.deepEqual(run.armed(), [30000],
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
  const run = runner();
  run.armIdleProbe();
  await run.fire();
  assert.deepEqual(run.seen.reads, ["/api/jobs?active_only=true&limit=1"]);
  assert.deepEqual(run.armed(), [30000]);
});

test("a job starting or ending re-reads the Jobs history while that page is shown", () => {
  const run = runner({ view: "jobs" });
  run.noticeActiveSet([{ job_ref: "a" }]);
  assert.equal(run.seen.historyReads, 0, "the first answer has nothing to compare with");
  run.noticeActiveSet([{ job_ref: "a" }]);
  assert.equal(run.seen.historyReads, 0, "the same set is not a change");
  run.noticeActiveSet([{ job_ref: "a" }, { job_ref: "b" }]);
  assert.equal(run.seen.historyReads, 1, "a job starting");
  run.noticeActiveSet([{ job_ref: "b" }]);
  assert.equal(run.seen.historyReads, 2, "a job ending");
  run.noticeActiveSet([{ job_ref: "c" }]);
  assert.equal(run.seen.historyReads, 3, "one ending as another starts, the size unchanged");
});

test("on any other page a change in the active set reads no history", () => {
  const run = runner({ view: "run" });
  run.noticeActiveSet([{ job_ref: "a" }]);
  run.noticeActiveSet([{ job_ref: "a" }, { job_ref: "b" }]);
  run.noticeActiveSet([]);
  assert.equal(run.seen.historyReads, 0);
});

test("ticks that follow a live job read the Sources payload once, not once per tick",
  async () => {
    const run = runner({ answers: [[LIVE], [LIVE], [LIVE]] });
    for (let i = 0; i < 3; i += 1) await run.pollJobOnce();
    assert.equal(run.seen.sourceReads, 1);
    assert.ok(!run.seen.reads.some((path) => path.startsWith("/api/sources")),
      "the tick asked for Sources itself");
  });
