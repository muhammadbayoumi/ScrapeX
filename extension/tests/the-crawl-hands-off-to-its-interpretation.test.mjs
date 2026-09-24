/**
 * A CRAWL NOW QUEUES ITS OWN INTERPRETATION, AND THE RUN SCREEN HAD NO IDEA.
 *
 * `pollJobOnce` adopts whatever `liveJob` returns and, when there IS one, repoints
 * `state.jobRef` at it and returns. The branch that draws the finished job's verdict and
 * refreshes the cards runs ONLY when the active list is empty — which was true for as
 * long as one job followed another by his own hand, and stopped being true the moment a
 * crawl started queueing its own follow-up. Measured on the merge gate: `_finish` commits
 * COMPLETED and the interpretation is committed `queued` 2.51 ms later, against
 * `POLL_MS = 1500`. So the handoff is not a race that sometimes happens — it is what
 * happens, after every directory crawl.
 *
 * WHAT HE WOULD HAVE SEEN. The mini-player title was `${source_key} — ${status}` and
 * names no kind at all, so `muqawil_org — running` at 56/56 became `muqawil_org — queued`
 * at 0, the log pane repointed to a job whose log is empty, and the row counts the crawl
 * was run for never refreshed. Issue 778 is the same sentence about a different pair.
 *
 * HOW IT IS TESTED. `app.js` is the panel's runtime and exports nothing, so this uses the
 * harness `healthy.test.mjs` and `finish-estimate.test.mjs` already use: read the file as
 * text, pull the functions out by name, and run them in a scope built here. The
 * alternative is not testing them, which is the state the gate found this handoff in.
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
const SETTLE_OUTGOING = extract(
  "settleOutgoing", /^async function settleOutgoing\(\) \{[\s\S]*?^\}/m);
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

/** `pollJobOnce` and `settleOutgoing` over stubbed IO, returning what each stub saw. */
function runner({ active, byRef, visible = true }) {
  const seen = {
    activity: [], logsFor: [], miniplayer: [], loadSources: 0, fetched: [],
  };
  const state = { job: null, jobRef: null };
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
    "refreshRunButton", "loadSources", "document", "clearTimeout", "setTimeout",
    "POLL_MS",
    // `pollTimer` is a module-level `let` in app.js that `pollJobOnce` assigns.
    `let pollTimer;\n${SETTLE_OUTGOING}\n${POLL_JOB_ONCE}\nreturn {pollJobOnce, settleOutgoing};`);
  const built = build(
    api, state, liveJob,
    (job) => seen.miniplayer.push(job && job.job_ref),
    (job) => seen.activity.push(job && job.job_ref),
    () => {}, () => {}, async () => { seen.loadSources += 1; },
    { visibilityState: visible ? "visible" : "hidden" },
    () => {}, () => {}, 1500);
  return { ...built, state, seen };
}

test("the crawl's verdict is drawn before the chained job is adopted", async () => {
  // THE MEASURED SEQUENCE. Poll 1: the crawl is running and is adopted. Poll 2: it has
  // finished and its own interpretation is already `queued`, so the active list is NOT
  // empty and the old code returned without ever reporting the crawl.
  const first = runner({ active: [CRAWL], byRef: { job_crawl: CRAWL } });
  await first.pollJobOnce();
  assert.equal(first.state.jobRef, "job_crawl");

  const second = runner({
    active: [CHAINED],
    byRef: { job_crawl: { ...CRAWL_DONE, log: [{ message: "job completed" }] },
             job_read: { ...CHAINED, log: [] } },
  });
  second.state.jobRef = "job_crawl";
  await second.pollJobOnce();

  assert.ok(second.seen.activity.includes("job_crawl"),
    `the crawl's final state was never drawn: activity = ${JSON.stringify(second.seen.activity)}. ` +
    "He watched it to 56/56 and the screen moved on without telling him how it ended.");
  assert.ok(second.seen.logsFor.includes("job_crawl"),
    "the log pane repointed without ever fetching the crawl's own log -- which holds " +
    "both 'job completed' and the one line naming the job that replaced it");
  assert.equal(second.seen.loadSources, 1,
    "loadSources() never ran, so the row counts he crawled for did not refresh");
  assert.equal(second.state.jobRef, "job_read",
    "having settled the crawl, the poll must still adopt the live job");
});

test("a poll that stays on one job does not redraw it as finished", async () => {
  // The other side of the same guard: `settleOutgoing` must fire on a HANDOFF, not on
  // every poll. Firing each time would call `loadSources()` at 1500 ms for the whole
  // run of a fourteen-hour crawl.
  const still = runner({ active: [CRAWL], byRef: { job_crawl: CRAWL } });
  still.state.jobRef = "job_crawl";
  await still.pollJobOnce();
  assert.equal(still.seen.loadSources, 0,
    "the poll refreshed every card while the same job was still running");
  assert.ok(!still.seen.activity.includes(undefined));
});

test("nothing active still reports the last job, through the same one reader", async () => {
  // The pre-existing branch, which `settleOutgoing` was factored out of. It has to keep
  // working, and it has to keep clearing the ref.
  const over = runner({
    active: [], byRef: { job_crawl: { ...CRAWL_DONE, log: [{ message: "job completed" }] } },
  });
  over.state.jobRef = "job_crawl";
  await over.pollJobOnce();
  assert.deepEqual(over.seen.activity, ["job_crawl"]);
  assert.equal(over.seen.loadSources, 1);
  assert.equal(over.state.jobRef, null, "the finished ref was not cleared");
});

/** `renderMiniplayer` over stub nodes, returning every textContent it wrote. */
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
    `${RENDER_MINIPLAYER}
return renderMiniplayer;`);
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
  assert.equal(titleFor({ ...CRAWL, source_keys: ["a", "b", "c"] }), "3 sites — running");
});
