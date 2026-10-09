// The Jobs page's own rules (#1542), as designed and confirmed on 2026-10-09: how a
// status looks, what the time line says, what the count line says, which control a row
// exposes, and the sentence a refusal reads.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  jobsCountLine, menuControls, primaryControl, refusalLine, statusLook, timeLine,
} from "../jobsview.js";

// A formatter shaped like ScrapeXTime.format, over fixed stamps, so the rule is tested
// and not the zone: "date" names the day, "short" the day and time, "time" the time.
const STAMPS = {
  "2026-10-07T08:00:00Z": {date: "7 October 2026", short: "7 Oct, 8:00 AM", time: "8:00 AM"},
  "2026-10-07T09:12:00Z": {date: "7 October 2026", short: "7 Oct, 9:12 AM", time: "9:12 AM"},
  "2026-10-05T22:00:00Z": {date: "5 October 2026", short: "5 Oct, 10:00 PM", time: "10:00 PM"},
  "2026-10-06T00:37:00Z": {date: "6 October 2026", short: "6 Oct, 12:37 AM", time: "12:37 AM"},
  "2026-10-04T10:00:00Z": {date: "4 October 2026", short: "4 Oct, 10:00 AM", time: "10:00 AM"},
  "2026-10-04T10:03:00Z": {date: "4 October 2026", short: "4 Oct, 10:03 AM", time: "10:03 AM"},
  "2026-10-09T09:14:00Z": {date: "9 October 2026", short: "9 Oct, 9:14 AM", time: "9:14 AM"},
  "2026-10-05T08:00:00Z": {date: "5 October 2026", short: "5 Oct, 8:00 AM", time: "8:00 AM"},
  "2026-10-05T09:00:00Z": {date: "5 October 2026", short: "5 Oct, 9:00 AM", time: "9:00 AM"},
};
const fmt = (stamp, mode) => STAMPS[stamp][mode];

test("a status reads as the engine's word, sentence-cased, with its glyph and tone", () => {
  assert.deepEqual(statusLook("completed_with_errors"),
    {word: "Completed with errors", glyph: "material-warning", tone: "warning"});
  assert.deepEqual(statusLook("running"),
    {word: "Running", glyph: "material-pending", tone: "secondary"});
  assert.deepEqual(statusLook("failed"),
    {word: "Failed", glyph: "material-cancel", tone: "destructive"});
  assert.deepEqual(statusLook("completed"),
    {word: "Completed", glyph: "material-check-circle", tone: "brand"});
  assert.deepEqual(statusLook("paused"),
    {word: "Paused", glyph: "material-pause-circle", tone: "foreground"});
  // AN UNKNOWN STATUS STILL NAMES ITSELF: a status this file has not heard of is news.
  assert.deepEqual(statusLook("being_audited"),
    {word: "Being audited", glyph: "material-info", tone: "default"});
  for (const nothing of ["", null, undefined]) {
    assert.deepEqual(statusLook(nothing), {word: "", glyph: "material-info", tone: "default"},
      String(nothing));
  }
});

test("every status the engine knows has its own glyph and tone, as designed", () => {
  // The whole table, so no entry can drift: the in-between states warn, a cancelled job
  // is neutral rather than failed, and the tones follow Studio (see STATUS_LOOK).
  const designed = {
    preparing: ["material-sync", "warning"],
    running: ["material-pending", "secondary"],
    resuming: ["material-sync", "warning"],
    pausing: ["material-pause-circle", "warning"],
    cancelling: ["material-block", "warning"],
    queued: ["material-schedule", "default"],
    scheduled: ["material-schedule", "default"],
    paused: ["material-pause-circle", "foreground"],
    requires_review: ["material-warning", "warning"],
    failed: ["material-cancel", "destructive"],
    partially_completed: ["material-warning", "warning"],
    completed_with_errors: ["material-warning", "warning"],
    completed: ["material-check-circle", "brand"],
    cancelled: ["material-block", "default"],
    skipped: ["material-next-plan", "secondary"],
  };
  for (const [status, [glyph, tone]] of Object.entries(designed)) {
    const look = statusLook(status);
    assert.deepEqual([look.glyph, look.tone], [glyph, tone], status);
  }
});

test("the time line states what is stored, start to finish, and never a duration", () => {
  // started_at survives a resume (jobs.py:936), so a computed duration would count
  // pauses, waits and sleep; both stored values are shown instead (his choice C).
  assert.equal(timeLine({status: "running", started_at: "2026-10-07T08:00:00Z"}, fmt),
    "Started 7 Oct, 8:00 AM");
  assert.equal(timeLine({status: "partially_completed", started_at: "2026-10-07T08:00:00Z",
    finished_at: "2026-10-07T09:12:00Z"}, fmt), "Started 7 Oct, 8:00 AM → 9:12 AM");
  assert.equal(timeLine({status: "completed", started_at: "2026-10-05T22:00:00Z",
    finished_at: "2026-10-06T00:37:00Z"}, fmt), "Started 5 Oct, 10:00 PM → 6 Oct, 12:37 AM",
    "a finish on another day carries its date");
  // THE DAY IS THE START'S, NOT THE DAY IT WAS ADDED: queued on the 4th, run on the 5th.
  assert.equal(timeLine({status: "completed", created_at: "2026-10-04T10:00:00Z",
    started_at: "2026-10-05T08:00:00Z", finished_at: "2026-10-05T09:00:00Z"}, fmt),
  "Started 5 Oct, 8:00 AM → 9:00 AM");
  // A finish with nothing to finish from says nothing rather than half a line.
  assert.equal(timeLine({status: "completed", finished_at: "2026-10-05T09:00:00Z"}, fmt), "");
});

test("a job that never started says when it was added, and a cancel says so", () => {
  assert.equal(timeLine({status: "queued", created_at: "2026-10-04T10:00:00Z"}, fmt),
    "Added 4 Oct, 10:00 AM");
  assert.equal(timeLine({status: "cancelled", created_at: "2026-10-04T10:00:00Z",
    finished_at: "2026-10-04T10:03:00Z"}, fmt), "Added 4 Oct, 10:00 AM → cancelled 10:03 AM");
  assert.equal(timeLine({status: "cancelled", started_at: "2026-10-07T08:00:00Z",
    finished_at: "2026-10-07T09:12:00Z"}, fmt), "Started 7 Oct, 8:00 AM → cancelled 9:12 AM",
    "the same word whether it was cancelled queued or running");
  // A SKIP NEVER STARTED, and says so the way a cancel does (#1596).
  assert.equal(timeLine({status: "skipped", created_at: "2026-10-04T10:00:00Z",
    finished_at: "2026-10-04T10:00:00Z"}, fmt), "Added 4 Oct, 10:00 AM → skipped 10:00 AM");
  assert.equal(timeLine({status: "failed", created_at: "2026-10-04T10:00:00Z",
    finished_at: "2026-10-04T10:03:00Z"}, fmt), "Added 4 Oct, 10:00 AM → 10:03 AM",
    "a failure is not a cancel or a skip, and says neither");
});

test("a skip looks neutral and muted, and like neither a failure nor a cancel", () => {
  assert.deepEqual(statusLook("skipped"),
    {word: "Skipped", glyph: "material-next-plan", tone: "secondary"});
  for (const other of ["failed", "cancelled"]) {
    const look = statusLook(other);
    assert.notEqual(look.glyph, "material-next-plan", other);
    assert.notEqual(look.tone, "secondary", other);
  }
  assert.deepEqual(menuControls({status: "skipped"}), ["log"]);
  assert.equal(primaryControl({status: "skipped"}), null);
});

test("the count line says what is shown, and whether it is live", () => {
  const live = {shown: 8, total: 8, live: true, seconds: 1.5};
  assert.equal(jobsCountLine(live, fmt), "8 jobs · Refreshes every 1.5s while a job is in progress or queued");
  assert.equal(jobsCountLine({...live, total: 1, shown: 1}, fmt),
    "1 job · Refreshes every 1.5s while a job is in progress or queued");
  assert.equal(jobsCountLine({...live, shown: 2}, fmt),
    "2 of 8 jobs · Refreshes every 1.5s while a job is in progress or queued");
  assert.equal(jobsCountLine({shown: 3, total: 3, live: false, readAt: "2026-10-09T09:14:00Z"}, fmt),
    "3 jobs · Read at 9:14 AM", "not live: say when it was read");
  assert.equal(jobsCountLine({...live, total: 200, shown: 200, bounded: true}, fmt),
    "Newest 200 jobs shown; older jobs are not listed · Refreshes every 1.5s while a job is in progress or queued");
  assert.equal(jobsCountLine({...live, total: 200, shown: 3, bounded: true}, fmt),
    "3 of the newest 200 jobs · Refreshes every 1.5s while a job is in progress or queued");
  assert.equal(jobsCountLine({...live, readAt: "2026-10-09T09:14:00Z"}, fmt),
    "8 jobs · Refreshes every 1.5s while a job is in progress or queued",
    "live: the read time is not said beside it");
  assert.equal(jobsCountLine({shown: 0, total: 0, live: false}, fmt), "0 jobs");
  assert.equal(jobsCountLine({shown: 1234, total: 1234, live: false}, fmt), "1,234 jobs");
  assert.equal(jobsCountLine({shown: 2, total: 2, live: true}, fmt),
    "2 jobs · Refreshes every 1.5s while a job is in progress or queued",
    "the panel's tick, 1.5 s, when no interval is passed");
});

test("one exposed action per row, and the menu holds the rest", () => {
  assert.equal(primaryControl({status: "running"}), "pause");
  assert.equal(primaryControl({status: "queued"}), "pause");
  assert.equal(primaryControl({status: "paused"}), "resume");
  assert.equal(primaryControl({status: "cancelling"}), null);
  assert.equal(primaryControl({status: "completed"}), null);
  assert.deepEqual(menuControls({status: "running"}), ["log", "cancel"]);
  assert.deepEqual(menuControls({status: "cancelling"}), ["log"], "no Cancel on a job already cancelling");
  assert.deepEqual(menuControls({status: "completed"}), ["log"]);
});

test("a refusal names the job and the status it reached", () => {
  assert.equal(refusalLine("pause", "Listing crawl · muqawil.org", "completed"),
    "Pause was refused: Listing crawl · muqawil.org is already completed");
  assert.equal(refusalLine("cancel", "Crawl · elburoj.com", "cancelled"),
    "Cancel was refused: Crawl · elburoj.com is already cancelled");
  assert.equal(refusalLine("pause", "Crawl · elburoj.com", "completed_with_errors"),
    "Pause was refused: Crawl · elburoj.com is already completed with errors",
    "the status in words, as the row says it");
});
