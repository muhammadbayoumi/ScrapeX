/**
 * A CRAWL NOW QUEUES ITS OWN INTERPRETATION, AND THE RUN SCREEN HAD NO IDEA.
 *
 * `pollJobOnce` adopts whatever `liveJob` returns and, when there IS one, repoints
 * `state.jobRef` at it and returns. The branch that refreshes the cards runs ONLY when
 * the active list is empty — true for as long as one job followed another by his own
 * hand, and false the moment a crawl started queueing its own follow-up. Measured on the
 * merge gate: `_finish` commits COMPLETED and the interpretation is committed `queued`
 * 2.51 ms later, against `POLL_MS = 1500`. So the handoff is not a race that sometimes
 * happens — it is what happens, after every directory crawl.
 *
 * WHAT HE WOULD HAVE SEEN. The row counts he crawled for never refreshed, and the
 * mini-player title was `${source_key} — ${status}`, which names no kind at all, so
 * `muqawil_org — running` at 56/56 became `muqawil_org — queued` at 0. Issue 778 is the
 * same sentence about a different pair.
 *
 * WHAT THIS FILE DOES **NOT** CLAIM, AND WHY THAT IS THE POINT. A first version drew the
 * finished crawl's verdict on the handoff too, and this file asserted that it had been
 * drawn. It was — and then overwritten four lines later, because `renderActivity` writes
 * the single `#activity` box and the incoming job gets it next. The assertion recorded a
 * CALL and called it a report. So the stubs below record what is still on screen when the
 * poll returns, and the durable claims are exactly two: the cards refresh, and the title
 * names the kind. The sentence about the outgoing job lives in the incoming job's own log
 * instead (`scrapex/directoryjob.py`), which is the pane the panel is about to open.
 *
 * HOW IT IS TESTED. `app.js` is the panel's runtime and exports nothing, so this uses the
 * harness `healthy.test.mjs` and `finish-estimate.test.mjs` already use: read the file as
 * text, pull the functions out by name, and run them in a scope built here.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { jobLabel, liveJob } from "../jobsview.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

function extract(name, pattern) {
  const match = SOURCE.match(pattern);
  assert.ok(match, `${name} is no longer where this guard reads it from in app.js`);
  return match[0];
}

// Each ends on a `}` in column 0 — every brace inside is indented — so a lazy match
// stops at the end of the function rather than at a block within it.
const POLL_JOB_ONCE = extract(
  "pollJobOnce", /^async function pollJobOnce\(\) \{[\s\S]*?^\}/m);
const REDRAW = extract(
  "redrawWhatTheJobChanged",
  /^async function redrawWhatTheJobChanged\(\) \{[\s\S]*?^\}/m);
const RENDER_MINIPLAYER = extract(
  "renderMiniplayer", /^function renderMiniplayer\(job, queued\) \{[\s\S]*?^\}/m);

const CRAWL = {
  job_ref: "job_crawl", job_kind: "directory_crawl", status: "running",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  fetch: { requests: 56, expected: 56, basis: "declared" },
};
const CHAINED = {
  job_ref: "job_read", job_kind: "dataset_interpret", status: "queued",
  source_keys: ["muqawil_org"], current_source_key: null,
};
const CRAWL_DONE = { ...CRAWL, status: "completed", finished_at: "2026-09-24T09:00:00Z" };

/** `pollJobOnce` over stubbed IO, recording what is on screen when it returns. */
function runner({ active, byRef, visible = true, view = "run" }) {
  // `activity` IS THE LAST VALUE THE BOX WAS GIVEN — what he can actually see.
  // `everDrawn` keeps the whole sequence, so a test can assert something was NOT drawn
  // at all rather than merely not drawn last.
  const seen = {
    activity: undefined, everDrawn: [], logShown: undefined, logsFor: [],
    miniplayer: undefined, loadSources: 0, loadDatasets: 0, fetched: [],
  };
  const state = { job: null, jobRef: null, jobStatus: null };
  const api = async (path) => {
    seen.fetched.push(path);
    if (path.startsWith("/api/jobs?")) return { jobs: active };
    const ref = path.split("/")[3];
    if (path.endsWith("/logs")) {
      seen.logsFor.push(ref);
      return { entries: (byRef[ref] || {}).log || [], total: 0 };
    }
    const job = byRef[ref];
    if (!job) throw new Error(`no such job ${ref}`);
    return job;
  };
  // eslint-disable-next-line no-new-func
  const build = new Function(
    "api", "state", "liveJob", "renderMiniplayer", "renderActivity", "renderLogs",
    "refreshRunButton", "loadSources", "loadDatasets", "currentViewName",
    "document", "clearTimeout", "setTimeout", "POLL_MS",
    // `pollTimer` is a module-level `let` in app.js that `pollJobOnce` assigns, and
    // `redrawWhatTheJobChanged` is defined beside it in the same file.
    "let pollTimer;\n" + REDRAW + "\n" + POLL_JOB_ONCE
      + "\nreturn {pollJobOnce};");
  const built = build(
    api, state, liveJob,
    (job) => { seen.miniplayer = job && job.job_ref; },
    (job) => {
      seen.activity = job && job.job_ref;
      seen.everDrawn.push(job && job.job_ref);
    },
    (entries) => { seen.logShown = entries; },
    () => {}, async () => { seen.loadSources += 1; },
    async () => { seen.loadDatasets += 1; }, () => view,
    { visibilityState: visible ? "visible" : "hidden" },
    () => {}, () => {}, 1500);
  return { ...built, state, seen };
}

test("the handoff refreshes the cards the crawl was run for", async () => {
  // THE MEASURED SEQUENCE. Poll 1: the crawl is running and is adopted. Poll 2: it has
  // finished and its own interpretation is already `queued`, so the active list is NOT
  // empty and the old code returned without ever refreshing a card.
  const first = runner({ active: [CRAWL], byRef: { job_crawl: CRAWL } });
  await first.pollJobOnce();
  assert.equal(first.state.jobRef, "job_crawl");
  assert.equal(first.seen.loadSources, 0, "a card refresh on an ordinary first poll");

  const second = runner({
    active: [CHAINED],
    byRef: {
      job_crawl: { ...CRAWL_DONE, log: [{ message: "job completed" }] },
      job_read: { ...CHAINED, log: [{ message: "started automatically when…" }] },
    },
  });
  second.state.jobRef = "job_crawl";
  second.state.jobStatus = CRAWL.status;
  await second.pollJobOnce();

  assert.equal(second.seen.loadSources, 1,
    "the crawl ended and no card refreshed, so the row counts he crawled for still " +
    "show what they showed before it started");
  assert.equal(second.state.jobRef, "job_read", "the live job was not adopted");
});

test("it does not draw the outgoing job, because the incoming one owns that box",
     async () => {
  // THE CORRECTION THE DESIGN SESSION'S PANEL READ FORCED. Drawing the crawl here is not
  // a report: `renderActivity` writes one `#activity` box and the incoming job gets it
  // four lines later, so it would be a flash plus two wasted requests. The sentence he
  // needs about the outgoing job is written into the INCOMING job's log by the engine.
  const over = runner({
    active: [CHAINED],
    byRef: {
      job_crawl: { ...CRAWL_DONE, log: [{ message: "job completed" }] },
      job_read: { ...CHAINED, log: [{ message: "started automatically when…" }] },
    },
  });
  over.state.jobRef = "job_crawl";
  over.state.jobStatus = CRAWL.status;
  await over.pollJobOnce();

  assert.equal(over.seen.activity, "job_read",
    `the box ended up showing ${over.seen.activity}; the live job owns it`);
  assert.ok(!over.seen.everDrawn.includes("job_crawl"),
    "the outgoing job was drawn and then overwritten in the same poll: " +
    `${JSON.stringify(over.seen.everDrawn)}. A call is not a thing seen.`);
  assert.ok(!over.seen.fetched.includes("/api/jobs/job_crawl"),
    "it fetched the outgoing job to draw something nothing can see");
  assert.deepEqual(over.seen.logsFor, ["job_read"],
    `the log pane fetched ${JSON.stringify(over.seen.logsFor)}`);
});

test("a poll that stays on one job does not refresh every card", async () => {
  // The other side of the guard: the refresh fires on a HANDOFF, not on every poll.
  // Firing each time would call `loadSources()` at 1500 ms for the whole run of a
  // fourteen-hour crawl.
  const still = runner({ active: [CRAWL], byRef: { job_crawl: CRAWL } });
  // BOTH, because the runtime now sets both: a `null` status reads as a status that
  // MOVED, and the redraw fires. Every place that adopts a ref adopts its status.
  still.state.jobRef = "job_crawl";
  still.state.jobStatus = CRAWL.status;
  await still.pollJobOnce();
  assert.equal(still.seen.loadSources, 0,
    "the poll refreshed every card while the same job was still running");
});

test("nothing active still reports the last job, because nothing overwrites it",
     async () => {
  // THE ONE PATH WHERE DRAWING THE OUTGOING JOB IS DURABLE. No live job means no
  // `renderActivity(job)` after it, so the verdict stays in the box.
  const over = runner({
    active: [],
    byRef: { job_crawl: { ...CRAWL_DONE, log: [{ message: "job completed" }] } },
  });
  over.state.jobRef = "job_crawl";
  over.state.jobStatus = CRAWL.status;
  await over.pollJobOnce();
  assert.equal(over.seen.activity, "job_crawl", "the verdict is not on screen");
  assert.deepEqual(over.seen.logShown, [{ message: "job completed" }]);
  assert.equal(over.seen.loadSources, 1);
  assert.equal(over.state.jobRef, null, "the finished ref was not cleared");
});

/** `renderMiniplayer` over stub nodes, returning the title it wrote. */
function titleFor(job) {
  const drawn = [];
  const nodes = {};
  const $ = (id) => (nodes[id] ||= {
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {} },
    set textContent(value) { drawn.push([id, value]); },
    get textContent() { return ""; },
  });
  // eslint-disable-next-line no-new-func
  const build = new Function("$", "jobLabel", "miniProgress", "fmtCount",
    RENDER_MINIPLAYER + "\nreturn renderMiniplayer;");
  build($, jobLabel, () => ({ text: "", pct: 0, indeterminate: false }), String)(job, 0);
  return drawn.filter(([id]) => id === "mini-title").map(([, value]) => value)[0];
}

test("the mini-player names the KIND, so a handoff cannot read as a restart", () => {
  assert.equal(titleFor(CRAWL), "Listing crawl · muqawil_org — running");
  assert.equal(titleFor(CHAINED), "Interpretation · muqawil_org — queued",
    "without the kind these two read as one job that went back to the beginning, " +
    "which is issue 778's sentence");
});

test("two sources keep the count, because no one kind covers them", () => {
  // `jobLabel` names ONE source, so a multi-source job keeps the "3 sites" wording
  // rather than silently naming the first key as if it were the whole job.
  assert.equal(titleFor({ ...CRAWL, source_keys: ["a", "b", "c"] }),
    "3 sites — running");
});


test("on the Data tab the handoff redraws the card, not only the Run list", async () => {
  // `loadSources()` redraws `#sites`, which lives in `<section id="view-run">`. The
  // DATASET CARD is drawn by `loadDatasets`, whose only callers are `showView("data")`
  // and the pause action -- so with the Data tab open and nothing navigating, the card
  // kept the row count it had BEFORE the crawl, went on saying "Interpretation under
  // way" after that job ended, and kept its Interpret row disabled.
  //
  // That stale row count is the exact complaint this whole feature exists for,
  // reappearing on the surface the feature added.
  const onData = runner({
    active: [CHAINED], view: "data",
    byRef: {
      job_crawl: { ...CRAWL_DONE, log: [{ message: "job completed" }] },
      job_read: { ...CHAINED, log: [{ message: "started automatically when…" }] },
    },
  });
  onData.state.jobRef = "job_crawl";
  onData.state.jobStatus = CRAWL.status;
  await onData.pollJobOnce();

  assert.equal(onData.seen.loadDatasets, 1,
    "the Data tab was on screen and its card never redrew, so it still shows the row " +
    "count and the badge it had before the crawl finished");
  assert.equal(onData.seen.loadSources, 1, "and the Run list must still refresh");
});

test("on the Run tab it does not redraw a card nobody is looking at", async () => {
  // The other side: `loadDatasets` rebuilds every dataset card and refetches their
  // counts. Doing that on a tab that is not on screen is work for nobody, at 1500 ms.
  const onRun = runner({
    active: [CHAINED], view: "run",
    byRef: {
      job_crawl: { ...CRAWL_DONE, log: [] },
      job_read: { ...CHAINED, log: [] },
    },
  });
  onRun.state.jobRef = "job_crawl";
  onRun.state.jobStatus = CRAWL.status;
  await onRun.pollJobOnce();

  assert.equal(onRun.seen.loadDatasets, 0,
    "it rebuilt the dataset cards while the Run tab was the one on screen");
  assert.equal(onRun.seen.loadSources, 1);
});


test("a status change inside one job redraws the card that now shows it", async () => {
  // THE CARD DRAWS A LIVE VALUE AND HAD NO LIVE REFRESH. Before this change the dataset
  // card showed counts and a badge, which only move when a job ENDS, so redrawing on a
  // ref change was enough. It now shows `interpreting.status`.
  //
  // `loadDatasets` has three callers: opening the Data tab, the pause action, and this
  // redraw. A status moving inside ONE job trips none of them — the ref never changes —
  // so the card painted `queued` once and kept it while the mini-player, which sits
  // outside `<main>` on every tab, showed the same job reach `paused`. The card then
  // said "nothing to press" over a job waiting for him to press Resume.
  const moving = runner({
    active: [{ ...CHAINED, status: "paused" }], view: "data",
    byRef: { job_read: { ...CHAINED, status: "paused", log: [] } },
  });
  moving.state.jobRef = "job_read";
  moving.state.jobStatus = "queued";          // what the last poll drew
  await moving.pollJobOnce();

  assert.equal(moving.seen.loadDatasets, 1,
    "the job went queued -> paused and the card was not redrawn, so it still says " +
    "\"queued ... Nothing to press\" over a job the player above it calls paused");
  assert.equal(moving.state.jobStatus, "paused",
    "and the new status was not remembered, so it would redraw again every poll");
});

test("the same status on the same job redraws nothing", async () => {
  // The other side. Without this, the redraw fires on every poll for the whole run of a
  // fourteen-hour crawl — `loadDatasets` rebuilds every card and refetches their counts.
  const still = runner({
    active: [CHAINED], view: "data",
    byRef: { job_read: { ...CHAINED, log: [] } },
  });
  still.state.jobRef = "job_read";
  still.state.jobStatus = CHAINED.status;
  await still.pollJobOnce();

  assert.equal(still.seen.loadDatasets, 0,
    "nothing changed and every dataset card was rebuilt anyway");
  assert.equal(still.seen.loadSources, 0);
});
