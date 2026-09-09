// The Jobs page's rules, driven with the four things that were invisible to him.
//
// Every case here is a job that existed on his warehouse on 2026-09-07, when the panel
// could show one active job out of 163.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  controlsFor, isSettled, jobLabel, jobWaitingLine, liveJob, ownsAWorker,
  progressFraction, progressLine, rowsFrom, statusTone, summariseJobs,
} from "../jobsview.js";

/** The pair that cost him 33 minutes: a blocked job entered 18 seconds after the one
 *  doing the work, and `jobs[0]` drew the blocked one. */
const BLOCKED = {
  job_ref: "job_1a95d29ebf89", job_kind: "profile_crawl", status: "preparing",
  source_keys: ["muqawil_org"], current_source_key: null,
  progress: {done: 0, total: 1}, fetch: {requests: 0, expected: 938},
  queued_behind: null, created_at: "2026-09-07T10:33:44Z", finished_at: null,
};
const WORKING = {
  job_ref: "job_034c51a29deb", job_kind: "profile_crawl", status: "running",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  progress: {done: 0, total: 1}, fetch: {requests: 620, expected: 938},
  queued_behind: null, created_at: "2026-09-07T10:33:25Z", finished_at: null,
};
const PAUSED = {
  job_ref: "job_0212decca681", job_kind: "dataset_interpret", status: "paused",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  progress: {done: 0, total: 1}, fetch: {requests: 300, expected: 909},
  queued_behind: null, created_at: "2026-09-06T14:01:14Z", finished_at: null,
};
const DONE = {
  job_ref: "job_7b891d5b67ac", job_kind: "profile_crawl", status: "completed",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  progress: {done: 1, total: 1}, fetch: {requests: 938, expected: 938},
  queued_behind: null, created_at: "2026-09-07T13:53:17Z",
  finished_at: "2026-09-07T14:23:50Z",
};

test("the working job wins the mini-player, not whichever was entered last", () => {
  // ISSUE 778. `jobs[0]` over a newest-first list drew `0/938 preparing` while another
  // job was at 620/938, and he read the panel as nothing working.
  assert.equal(liveJob([BLOCKED, WORKING])?.job_ref, WORKING.job_ref);
  assert.equal(liveJob([WORKING, BLOCKED])?.job_ref, WORKING.job_ref);
});

test("with nothing holding a worker, a waiting job is still shown", () => {
  assert.equal(liveJob([BLOCKED])?.job_ref, BLOCKED.job_ref);
  assert.equal(liveJob([DONE]), null, "a settled job was adopted as live");
  assert.equal(liveJob([]), null);
  assert.equal(liveJob(null), null);
});

test("a still job says what it waits for, and never invents a reason", () => {
  // The measured case: `queued_behind` is NULL for a job blocked on the per-host
  // politeness lane, so the payload cannot name a job — and claiming one would be a
  // sentence he could act on and be wrong about.
  const said = jobWaitingLine(BLOCKED);
  assert.match(said, /waiting for this site's turn/);
  assert.doesNotMatch(said, /job_/, `it named a job it does not know: ${said}`);

  const behind = {...BLOCKED, status: "queued",
                  queued_behind: {job_ref: "job_034c51a29deb",
                                  current_source_key: "muqawil_org"}};
  assert.match(jobWaitingLine(behind), /job_034c51a29deb/);
  assert.match(jobWaitingLine(behind), /muqawil_org/);

  assert.match(jobWaitingLine(PAUSED), /you resume it/);
  assert.equal(jobWaitingLine(WORKING), "", "a running job was given a waiting line");
  assert.equal(jobWaitingLine(DONE), "", "a finished job was given a waiting line");
});

test("the controls offered are the ones set_control can honour", () => {
  // A button that cannot work is worse than no button: the route answers 409 for a job
  // that has already finished.
  assert.deepEqual(controlsFor(DONE), []);
  assert.deepEqual(controlsFor(PAUSED), ["resume", "cancel"]);
  assert.deepEqual(controlsFor(WORKING), ["pause", "cancel"]);
  assert.deepEqual(controlsFor({status: "cancelling"}), ["cancel"],
    "a job already stopping was offered Pause");
  assert.deepEqual(controlsFor({status: "requires_review"}), ["cancel"]);
});

test("progress is counted in the unit the job measures", () => {
  // `requests`/`expected` IS THE SHAPE THE ENGINE SERVES. Reading it as `done`/`total`
  // -- which is `progress`'s shape -- drew nothing at all, and the DOM guard is what
  // caught that: an assumed payload is the same defect as an assumed file path.
  assert.equal(progressLine(WORKING), "620 of 938 requests");
  assert.equal(progressLine(PAUSED), "300 of 909 requests");
  assert.equal(progressLine({progress: {done: 0, total: 1}, fetch: {}}),
    "0 of 1 source(s)", "the source count is the fallback and it was dropped");
  assert.equal(progressLine({}), "", "a job with nothing measured was given a figure");
  // A NUMERATOR WITH NO DENOMINATOR IS STILL NEWS: a crawl whose total is not yet known
  // has fetched a real number of pages, and silence is what made a working job look
  // stopped.
  assert.equal(progressLine({fetch: {requests: 41, expected: null}}), "41 requests");
});

test("a job with no denominator gets no bar rather than a bar at zero", () => {
  assert.equal(progressFraction(WORKING), 620 / 938);
  assert.equal(progressFraction({}), null,
    "a bar drawn at 0% says nothing has happened, which may be false");
  assert.equal(progressFraction({fetch: {requests: 41, expected: null}}), null,
    "a numerator with no denominator was turned into a fraction");
  assert.equal(progressFraction({fetch: {requests: 9999, expected: 938}}), 1,
    "a bar past its own total");
});

test("the label names the kind in words and the source it is working", () => {
  assert.equal(jobLabel(WORKING), "Profile fetch · muqawil_org");
  assert.equal(jobLabel(PAUSED), "Interpretation · muqawil_org");
  assert.equal(jobLabel({job_kind: "directory_crawl", source_keys: ["muqawil_org"]}),
    "Listing crawl · muqawil_org");
  assert.equal(jobLabel({job_kind: "something_new"}), "something_new",
    "an unknown kind must still name itself rather than reading 'Job'");
});

test("amber is `off`, because `warn` renders as plain grey in this panel", () => {
  assert.equal(statusTone("completed"), "ok");
  assert.equal(statusTone("failed"), "err");
  assert.equal(statusTone("partially_completed"), "off");
  assert.equal(statusTone("paused"), "off");
  assert.notEqual(statusTone("partially_completed"), "warn");
});

test("the summary says how many and in what state", () => {
  const said = summariseJobs({jobs: [WORKING, BLOCKED, DONE, PAUSED]});
  assert.match(said, /4 jobs/);
  assert.match(said, /1 running/);
  assert.match(said, /1 completed/);
  assert.match(summariseJobs({jobs: []}), /No jobs yet/);
  assert.match(summariseJobs({jobs: [DONE]}), /1 job\b/, "one job was called jobs");
});

test("the rows keep the payload's order and carry every job, settled included", () => {
  // THE WHOLE POINT: 162 of his 163 jobs were unreachable because the only query the
  // panel made carried `active_only=true`.
  const rows = rowsFrom({jobs: [DONE, WORKING, BLOCKED, PAUSED]});

  assert.deepEqual(rows.map((row) => row.job_ref),
    [DONE.job_ref, WORKING.job_ref, BLOCKED.job_ref, PAUSED.job_ref]);
  assert.equal(rows.filter((row) => row.settled).length, 1);
  assert.equal(rows.find((row) => row.job_ref === WORKING.job_ref).live, true);
  assert.equal(rows.filter((row) => row.job_ref).length, 4);
  assert.deepEqual(rowsFrom({jobs: [null, {}, DONE]}).map((r) => r.job_ref),
    [DONE.job_ref], "a job with no ref reached the page as a row with no identity");
});

test("held and settled are read off the vocabulary, not guessed", () => {
  for (const status of ["preparing", "running", "resuming", "pausing", "cancelling"]) {
    assert.equal(ownsAWorker({status}), true, status);
  }
  for (const status of ["queued", "scheduled", "paused", "requires_review"]) {
    assert.equal(ownsAWorker({status}), false, status);
  }
  for (const status of ["cancelled", "completed", "completed_with_errors",
                        "partially_completed", "failed"]) {
    assert.equal(isSettled({status}), true, status);
  }
  assert.equal(isSettled({status: "paused"}), false,
    "a paused job is not finished; it is waiting for him");
});

test("no name here collides with one app.js already defines", async () => {
  // A COLLISION THE HARNESS EXPOSES AND PRODUCTION HIDES. The panel's modules are
  // separate scopes when the browser loads them and ONE scope in
  // `tools/panel_harness.py`, which inlines them all. `app.js` already had
  // `waitingLine(s)` for the dataset card's amber lines, so `rowsFrom` called THAT one
  // and every job's waiting line came back empty -- silently, and only in the test. The
  // fix was the rename; this is what makes the next one loud.
  //
  // A LITERAL SEARCH AND NOT A REGEX, deliberately: `function name(` is exactly what a
  // declaration in app.js looks like, and a hand-escaped pattern is a second thing to
  // get wrong -- it was, on the first attempt here.
  const here = await import("../jobsview.js");
  const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
  const clashes = Object.keys(here).filter(
    (name) => app.includes(`function ${name}(`));

  assert.deepEqual(clashes, [],
    `app.js declares its own ${clashes.join(", ")}, and the harness inlines both into `
    + "one scope -- whichever loads last wins and the other stops working in silence");
});

