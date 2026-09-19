// The Jobs page's rules, driven with the four things that were invisible to him.
//
// Every case here is a job that existed on his warehouse on 2026-09-07, when the panel
// could show one active job out of 163.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  controlsFor, isMoving, isSettled, jobLabel, jobWaitingLine, liveJob, ownsAWorker,
  progressFraction, progressLine, rowsFrom, statusTone, statusWords, summariseJobs,
} from "../jobsview.js";

/** `fetch` AS THE RUNNERS ACTUALLY LEAVE IT, which is empty.
 *
 *  Measured on his live engine 2026-09-10: `GET /api/jobs` returns
 *  `{requests: 0, expected: null, ...}` for every `profile_crawl` and
 *  `dataset_interpret` job, because neither runner is among `record_source_fetch`'s
 *  callers. These fixtures used to carry `{requests: 620, expected: 938}` AND an empty
 *  `counters`, which is a payload no producer can emit -- `_fetch_progress` derives
 *  `fetch` FROM `counters` -- so every assertion below certified a fiction and the real
 *  page said "620 of 938 source(s)" against twelve registered sources. */
const NO_FETCH = {requests: 0, expected: null, basis: null, as_of: null,
                  unknown_sources: [], sources: {}};

/** The pair that cost him 33 minutes: a blocked job entered 18 seconds after the one
 *  doing the work, and `jobs[0]` drew the blocked one. */
const BLOCKED = {
  job_ref: "job_1a95d29ebf89", job_kind: "profile_crawl", status: "preparing",
  source_keys: ["muqawil_org"], current_source_key: null,
  progress: {done: 0, total: 938, unit: "page(s)"}, fetch: {...NO_FETCH},
  queued_behind: null, created_at: "2026-09-07T10:33:44Z", finished_at: null,
};
const WORKING = {
  job_ref: "job_034c51a29deb", job_kind: "profile_crawl", status: "running",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  progress: {done: 620, total: 938, unit: "page(s)"}, fetch: {...NO_FETCH},
  queued_behind: null, created_at: "2026-09-07T10:33:25Z", finished_at: null,
};
const PAUSED = {
  job_ref: "job_0212decca681", job_kind: "dataset_interpret", status: "paused",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  progress: {done: 300, total: 909, unit: "page pair(s)"}, fetch: {...NO_FETCH},
  queued_behind: null, created_at: "2026-09-06T14:01:14Z", finished_at: null,
};
const DONE = {
  job_ref: "job_7b891d5b67ac", job_kind: "profile_crawl", status: "completed",
  source_keys: ["muqawil_org"], current_source_key: "muqawil_org",
  progress: {done: 938, total: 938, unit: "page(s)"}, fetch: {...NO_FETCH},
  queued_behind: null, created_at: "2026-09-07T13:53:17Z",
  finished_at: "2026-09-07T14:23:50Z",
};

/** A PRICE CRAWL, which is the one kind that DOES fill `fetch`. Without it the
 *  `fetch`-first branch of `counted` goes unmeasured, and the fix for the wrong unit
 *  would be free to delete it. */
const PRICE = {
  job_ref: "job_price", job_kind: "crawl", status: "running",
  source_keys: ["SALLA_SHOP"], current_source_key: "SALLA_SHOP",
  progress: {done: 0, total: 1},
  fetch: {requests: 1030, expected: 2461, basis: "estimate", as_of: "2026-07-29",
          unknown_sources: [], sources: {}},
  queued_behind: null, created_at: "2026-07-30T10:00:00Z", finished_at: null,
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

  assert.match(jobWaitingLine(PAUSED), /you resume it/);
  assert.equal(jobWaitingLine(WORKING), "", "a running job was given a waiting line");
  assert.equal(jobWaitingLine(DONE), "", "a finished job was given a waiting line");
});

// THE SHAPE BELOW IS `_queued_behind`'s, COPIED FROM THE ENGINE AND NOT INVENTED.
// `scrapex/webui/app.py:_queued_behind` returns exactly these five keys. The first
// version of this guard fabricated `{job_ref, current_source_key}` -- three fields no
// producer emits -- so it passed against a branch that could never run against the real
// engine, and every queued job silently fell through to "waiting for a worker".
const QUEUED_BEHIND = {
  position: 3, capacity: 2, running_count: 2,
  running: [{job_ref: "job_034c51a29deb", source_keys: ["muqawil_org"]},
            {job_ref: "job_7b891d5b67ac", source_keys: ["balady_gov_sa"]}],
  starting_now: false,
};

test("a queued job is told what holds the slots, in the payload's own shape", () => {
  const waiting = {...BLOCKED, status: "queued", queued_behind: QUEUED_BEHIND};
  const said = jobWaitingLine(waiting);

  assert.match(said, /2 at a time/, `the capacity is in the payload and was dropped: ${said}`);
  assert.match(said, /muqawil_org/, `the holders are named in the payload: ${said}`);
  assert.match(said, /balady_gov_sa/, said);
  assert.match(said, /2 ahead of it/, `position ${QUEUED_BEHIND.position} means 2 ahead: ${said}`);
  assert.doesNotMatch(said, /waiting for a worker/,
    "it fell through to the generic line, which is what reading a field no producer "
    + `emits looks like: ${said}`);
});

test("a job inside the free slots is not called queued", () => {
  // `_queued_behind`'s own comment: "True when this job is within the free slots -- it is
  // not really waiting, it starts on the next poll. The panel must not call that
  // 'queued'." `starting_now` was ignored entirely, so it did.
  const soon = {...BLOCKED, status: "queued",
                queued_behind: {...QUEUED_BEHIND, position: 1, starting_now: true}};
  const said = jobWaitingLine(soon);

  assert.match(said, /starts on the next poll/, said);
  assert.doesNotMatch(said, /waiting/,
    `a job the engine says is starting was told it is waiting: ${said}`);
});

test("the first job ahead is not miscounted, and a nameless holder still reads", () => {
  const first = {...BLOCKED, status: "queued",
                 queued_behind: {...QUEUED_BEHIND, position: 1}};
  assert.doesNotMatch(jobWaitingLine(first), /ahead of it/,
    "position 1 means nothing is ahead of it");

  const nameless = {...BLOCKED, status: "queued",
                    queued_behind: {...QUEUED_BEHIND, position: 1, running: []}};
  assert.match(jobWaitingLine(nameless), /another job/,
    "with no source key to name, it must still say what it is waiting for");
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

test("progress is counted in the unit the job says it counted", () => {
  // THE UNIT COMES FROM THE PAYLOAD AND NOT FROM THIS FILE. `_job_view` declares one
  // per kind, because the runner that wrote the number is the only thing that knows
  // what it counted. These two said `source(s)` until 2026-09-10 -- "469 of 469
  // source(s)" for 469 page pairs, against twelve registered sources.
  assert.equal(progressLine(WORKING), "620 of 938 page(s)");
  assert.equal(progressLine(PAUSED), "300 of 909 page pair(s)");
  // A PRICE CRAWL FILLS `fetch`, and requests win when they are there: `progress` is
  // 0/1 for its whole duration, which is the 0% he watched for 18 minutes while 1,030
  // requests succeeded behind it. Its total is an ESTIMATE, so it wears the tilde —
  // the two facts belong on one fixture rather than on two.
  assert.equal(progressLine(PRICE), "1,030 of ~2,461 requests");
  // AND A KIND THAT DECLARES NO UNIT COUNTS SOURCES, which is what the pair meant
  // before any kind declared anything.
  assert.equal(progressLine({progress: {done: 0, total: 1}, fetch: {}}),
    "0 of 1 source(s)", "the source count is the fallback and it was dropped");
  assert.equal(progressLine({}), "", "a job with nothing measured was given a figure");
  // A NUMERATOR WITH NO DENOMINATOR IS STILL NEWS: a crawl whose total is not yet known
  // has fetched a real number of pages, and silence is what made a working job look
  // stopped.
  assert.equal(progressLine({fetch: {requests: 41, expected: null}}), "41 requests");
});

test("an estimated total wears a tilde and a counted one does not", () => {
  // `_BASIS_RANK`: "claiming otherwise is how an undated guess gets displayed as a
  // fact." The mini-player marks it and this row dropped `basis` entirely, so a
  // denominator seeded from the LAST crawl read exactly like a measurement.
  assert.equal(progressLine({fetch: {requests: 620, expected: 938, basis: "estimate"}}),
    "620 of ~938 requests");
  assert.equal(progressLine({fetch: {requests: 620, expected: 938, basis: "declared"}}),
    "620 of 938 requests", "a declared total is a count and must not wear a ~");
  assert.equal(progressLine({fetch: {requests: 620, expected: 938, basis: "measured"}}),
    "620 of 938 requests");
  assert.equal(progressLine({fetch: {requests: 620, expected: 938}}),
    "620 of 938 requests", "no basis stated is not a guess stated");
  // The source-count fallback states no basis at all, so it never wears one.
  assert.equal(progressLine({progress: {done: 3, total: 7}, fetch: {}}),
    "3 of 7 source(s)");
});

test("a job with no denominator gets no bar rather than a bar at zero", () => {
  assert.equal(progressFraction(WORKING), 620 / 938);
  assert.equal(progressFraction(PRICE), 1030 / 2461);
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

test("every tone is a badge variant the kit actually defines", () => {
  // THE DEFECT CLASS, NOT THE ONE STATUS. `failed` returned `err`, which is a MESSAGE
  // tone in this panel and not a badge one -- `.badge.err` does not exist, so the
  // cascade fell back to `color: var(--muted)` and 28 of his 163 jobs drew grey,
  // indistinguishable from `cancelled`. An invalid `var()` and an undefined badge class
  // fail the same silent way, which is why this asserts the whole range.
  const DEFINED = new Set(["ok", "off", "danger", ""]);
  const STATUSES = ["completed", "failed", "completed_with_errors",
                    "partially_completed", "requires_review", "cancelled", "paused",
                    "running", "preparing", "queued", "scheduled", "resuming",
                    "pausing", "cancelling", "something_new"];
  for (const status of STATUSES) {
    assert.ok(DEFINED.has(statusTone(status)),
      `statusTone(${status}) = "${statusTone(status)}", which components.css does not `
      + "define -- it renders as plain grey and says nothing");
  }

  assert.equal(statusTone("completed"), "ok");
  assert.equal(statusTone("failed"), "danger",
    "a failed job must be the one colour he can pick out of 163 rows");
  assert.equal(statusTone("partially_completed"), "off");
  assert.equal(statusTone("paused"), "off");
});

test("a status is spelt one way per screen", () => {
  // The badge printed the raw status while the summary directly above it un-underscored
  // the same word, so one screen read `completed_with_errors` and `completed with
  // errors` at once.
  assert.equal(statusWords("completed_with_errors"), "completed with errors");
  assert.equal(statusWords("running"), "running");
  assert.equal(statusWords(null), "");
  assert.match(summariseJobs({jobs: [{job_ref: "j", status: "completed_with_errors"}]}),
    /completed with errors/);
});

test("the dot means moving, not merely holding a worker", () => {
  // `app.css` calls it "ONE DOT FOR 'THIS IS THE ONE MOVING'", and it was drawn from
  // `ownsAWorker` -- which is the discriminator `ADOPTION_ORDER` exists to reject. It lit
  // on the `preparing` job that sat blocked for 33 minutes and announced "running".
  assert.equal(isMoving(WORKING), true);
  assert.equal(isMoving({status: "resuming"}), true);
  assert.equal(isMoving(BLOCKED), false,
    "the blocked job that cost him 33 minutes was called moving");
  assert.equal(ownsAWorker(BLOCKED), true,
    "it does hold a worker -- which is exactly why the two must not be one question");
  for (const status of ["pausing", "cancelling", "queued", "paused"]) {
    assert.equal(isMoving({status}), false, status);
  }
  assert.equal(rowsFrom({jobs: [BLOCKED]})[0].live, false,
    "the row's dot still comes from 'holds a worker'");
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

// THE COLLISION GUARD LIVES IN `tests/test_panel_wiring.py`, NOT HERE.
//
// A version of it was written in this file first and it was the weaker of the two. It
// compared `Object.keys(exports)` against the literal `function name(` in `app.js`, so
// it could not see a non-exported top-level name (`SETTLED`, `HELD`, `KIND_LABELS`,
// `ADOPTION_ORDER`, `counted`), could not see a `const` declaration in `app.js` -- this
// module's own `JOBS_LIMIT` is one -- and looked at exactly one of the thirteen files
// `panel_harness.py` flattens into a single scope. A `const` clash is a SyntaxError that
// kills the whole harness page, which is the 2026-08-12 failure that guard records.
//
// `test_no_two_inlined_modules_declare_the_same_top_level_name` already holds that rule
// properly, for every pair of inlined modules; `jobsview.js` and `app.js` were simply
// missing from its list and are now in it. One rule, one home.

