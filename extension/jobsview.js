// What the Jobs page MAKES of `/api/jobs` — and nothing else.
//
// HIS REQUEST, 2026-09-07: «اريد اضافة jobs بحيث اقدر اتابع مثل ما قلت مهمة كذا انتهت
// او مهمة كذات توقفت لانى لا ارى ذلك من خلال extension» — so he can follow that one job
// finished and another stopped, because he cannot see that through the extension.
//
// MEASURED THE DAY HE ASKED: his warehouse held 163 jobs — 104 completed, 28 failed, 23
// cancelled, 4 partially completed, 3 completed with errors, 1 running — and the panel
// asked one question, once: `/api/jobs?active_only=true&limit=5`, then `jobs[0]`. So
// every FINISHED job was unreachable and only one active job was ever drawn. In one day
// that hid a sweep at 620/938 behind a blocked one showing 0/938 (he read it as nothing
// working), a duplicate sweep he could not see was a second job, a cancelled job that
// ran to completion, and a paused interpretation at 300/909.
//
// PURE, like datatable.js and taxonomyfilter.js: app.js cannot be imported under
// `node --test`, so every rule a wrong sentence could come from lives here.
//
// AND IT IS NOT A SECOND ACTIVITY LOG. The Console page exists and the Run screen draws
// one job's log; this is a LIST that opens one of them.

/** Terminal statuses, from `scrapex/vocab.py:TERMINAL_JOB_STATUSES`. */
const SETTLED = new Set(["cancelled", "completed", "completed_with_errors",
                         "partially_completed", "failed"]);

/** Where the worker is holding the job, from `vocab.WORKER_HELD_STATUSES` plus the two
 *  transitional statuses `set_control` parks a held job in. A job in one of these owns a
 *  runtime; anything else non-terminal is waiting for one or for him. */
const HELD = new Set(["preparing", "running", "resuming", "pausing", "cancelling"]);

/** Where the job is actually ADVANCING, which is not the same as holding a worker.
 *
 *  THE DOT MUST NOT DISAGREE WITH `ADOPTION_ORDER`. `app.css` calls the dot "ONE DOT FOR
 *  'THIS IS THE ONE MOVING', which is the question the whole page exists to answer", and
 *  it was drawn from `HELD` -- so it lit on the `preparing` job that sat blocked on the
 *  politeness lane for 33 minutes, beside a badge reading `preparing` and a waiting line
 *  saying it may be blocked, while announcing "running" to a screen reader. That is the
 *  same wrong discriminator `ADOPTION_ORDER` below is built to reject. */
const MOVING = new Set(["running", "resuming"]);

/** Statuses that wait on HIM and never advance on their own — `BLOCKING_JOB_STATUSES`
 *  excludes them for the same reason. */
const HIS_MOVE = new Set(["paused", "requires_review"]);

const KIND_LABELS = {
  crawl: "Crawl",
  directory_crawl: "Listing crawl",
  profile_crawl: "Profile fetch",
  dataset_interpret: "Interpretation",
  organization_enrichment: "Enrichment",
};

export function isSettled(job) {
  return SETTLED.has(String(job?.status || ""));
}

export function ownsAWorker(job) {
  return HELD.has(String(job?.status || ""));
}

/** Whether this is the one moving, which is what the row's dot claims. */
export function isMoving(job) {
  return MOVING.has(String(job?.status || ""));
}

/** `completed_with_errors` as `completed with errors`. The panel un-underscores a status
 *  everywhere it shows one -- `renderActivity`, `renderMiniplayer` and `summariseJobs`
 *  below -- and the row's badge was the one surface opting out, so the same screen spelt
 *  one status two ways. */
export function statusWords(status) {
  return String(status || "").replace(/_/g, " ");
}

/**
 * How much a status means "this job is the one doing the work". Higher wins.
 *
 * `preparing` RANKS BELOW `running`, AND THAT IS THE WHOLE FIX. The engine's
 * `WORKER_HELD_STATUSES` counts `preparing` as held, which is correct for what that
 * set decides — a pause has to wait for a safe boundary. It is the wrong
 * discriminator here: the job that cost him 33 minutes of silence sat in `preparing`
 * for the whole of it, blocked on the per-host politeness lane, while another job was
 * at 620/938. Adopting by "held" alone draws the blocked one, which is the defect
 * wearing a different mask.
 */
const ADOPTION_ORDER = ["running", "resuming", "pausing", "cancelling", "preparing",
                        "queued", "scheduled", "requires_review", "paused"];

/**
 * Which job the mini-player should adopt.
 *
 * ISSUE 778, AND `jobs[0]` IS THE DEFECT. The list comes back newest first, so a job
 * entered eighteen seconds after the one doing the work is drawn instead of it —
 * measured 2026-09-07: the panel showed `0/938 preparing` while another job was at
 * 620/938, and he read the panel as nothing working.
 *
 * Among jobs of equal standing the payload's own order decides, which is newest first.
 */
export function liveJob(jobs) {
  const live = (jobs || []).filter((job) => job && !isSettled(job));
  if (!live.length) return null;
  const rank = (job) => {
    const at = ADOPTION_ORDER.indexOf(String(job.status || ""));
    // AN UNKNOWN STATUS SORTS LAST AND IS STILL SHOWN. A status this file has not
    // heard of is news, and dropping the job would hide exactly the thing that is new.
    return at === -1 ? ADOPTION_ORDER.length : at;
  };
  return live.reduce((best, job) => (rank(job) < rank(best) ? job : best), live[0]);
}

/** `Profile fetch · muqawil_org`, from the payload's own words. */
export function jobLabel(job) {
  const kind = KIND_LABELS[job?.job_kind] || String(job?.job_kind || "Job");
  const source = job?.current_source_key
    || (job?.source_keys || [])[0] || "";
  return source ? `${kind} · ${source}` : kind;
}

/**
 * What the job has done, in the unit it actually measures.
 *
 * REQUESTS AGAINST A STATED TOTAL, AND `fetch` IS WHERE THAT LIVES -- `requests` and
 * `expected`, which is the shape `_fetch_progress` serves and its docstring calls "the
 * ONE place this is computed". I first read it as `done`/`total`, which is `progress`'s
 * shape, and the page drew nothing at all: an assumed payload is the same defect as an
 * assumed file path, and the DOM guard is what caught it.
 *
 * `progress` COUNTS SOURCES AND IS THE FALLBACK, never the headline: a one-source job is
 * 0/1 for its whole duration, which is the 0% he watched for 18 minutes while 1,030
 * requests succeeded behind it.
 *
 * A GUESS WEARS A `~`, WHICH IS THE PANEL'S EXISTING CONVENTION AND NOT A NEW ONE.
 * `renderProgress` marks an estimated denominator that way and says why -- "a declared
 * total drops the `~` because it is a count, not a guess" -- and `_BASIS_RANK` calls an
 * undated guess displayed as a fact the failure it exists to prevent. This row dropped
 * `basis` entirely, so `620 of 938` read as a measurement whichever it was. The row is
 * tighter than the Activity panel, so it takes the `~` and leaves the date there.
 */
export function progressLine(job) {
  const [done, total, unit, basis] = counted(job);
  if (!(total > 0)) {
    // A NUMERATOR WITH NO DENOMINATOR IS STILL NEWS. A crawl whose total is not yet
    // known has fetched a real number of pages, and saying nothing is what made a
    // working job look stopped.
    return done > 0 ? `${done.toLocaleString()} ${unit}` : "";
  }
  const tilde = basis === "estimate" ? "~" : "";
  return `${done.toLocaleString()} of ${tilde}${total.toLocaleString()} ${unit}`;
}

/** `[done, total, unit, basis]`, from whichever of the two the job actually carries.
 *  `basis` is `measured`, `declared`, `estimate` or null, and only `fetch` states one. */
function counted(job) {
  const fetch = job?.fetch || {};
  const requests = Number(fetch.requests || 0);
  const expected = Number(fetch.expected || 0);
  if (requests > 0 || expected > 0) {
    return [requests, expected, "requests", fetch.basis || null];
  }
  const progress = job?.progress || {};
  return [Number(progress.done || 0), Number(progress.total || 0),
          progress.unit || "source(s)", null];
}

/** 0–1, or null when the job states no denominator. Null is not zero: a bar drawn at
 *  0% for a job with no total says "nothing has happened", which may be false. */
export function progressFraction(job) {
  const [done, total] = counted(job);
  if (!(total > 0)) return null;
  return Math.max(0, Math.min(1, done / total));
}

/**
 * Why this job is not moving — and it refuses to invent a reason.
 *
 * ISSUE 778's SECOND HALF. `queued_behind` is in the payload and is `null` for a job
 * blocked on the per-host politeness lane, which is the case that cost him 33 minutes of
 * silence: the job was `preparing`, nothing said why, and the honest answer is that it is
 * waiting for the site's turn rather than for a named job. Saying "waiting for job X"
 * when we do not know which is worse than saying we do not know.
 *
 * THE SHAPE IS `_queued_behind`'s AND WAS ASSUMED ONCE ALREADY. This read
 * `behind.job_ref`, `current_source_key` and `source_keys` -- three fields no producer
 * emits. `_queued_behind` (`scrapex/webui/app.py:4341-4356`) returns exactly
 * `{position, capacity, running_count, running, starting_now}`, so the branch was dead
 * against the real engine, every queued job fell through to "waiting for a worker", and
 * the guard passed only because it fabricated the payload. Same defect as reading
 * `fetch` as `done`/`total`, in a second field: an assumed payload is the same defect as
 * an assumed file path.
 */
export function jobWaitingLine(job) {
  const status = String(job?.status || "");
  if (isSettled(job) || ownsAWorker(job) && status === "running") return "";
  const behind = job?.queued_behind;
  if (behind) {
    // A JOB INSIDE THE FREE SLOTS IS NOT WAITING FOR ANYTHING. `_queued_behind` says so
    // with `starting_now`, and its own comment forbids the panel calling that "queued":
    // the worker starts it on the next poll.
    if (behind.starting_now) return "a slot is free — it starts on the next poll";
    const holders = (behind.running || [])
      .map((one) => (one?.source_keys || []).join(", ")).filter(Boolean);
    const ahead = Number(behind.position || 0) - 1;
    return `waiting for a slot — the engine crawls ${behind.capacity} at a time and is `
      + `busy with ${holders.length ? holders.join("; ") : "another job"}`
      + (ahead > 0 ? ` · ${ahead} ahead of it` : "");
  }
  if (status === "paused") return "paused — it moves when you resume it";
  if (status === "requires_review") return "waiting for you to review it";
  if (status === "preparing" || status === "resuming") {
    return "starting — or waiting for this site's turn, which nothing in the payload "
      + "can name yet";
  }
  if (status === "queued" || status === "scheduled") return "waiting for a worker";
  if (status === "pausing") return "stopping at its next safe boundary";
  if (status === "cancelling") return "cancelling at its next safe boundary";
  return "";
}

/**
 * Which controls this job can actually take.
 *
 * MATCHED TO `set_control`, NOT GUESSED. A button that cannot work is worse than no
 * button: the route answers 409 for a job that is already finished, and `set_control`
 * settles a job the worker is not holding on the spot. So a settled job gets nothing, a
 * paused one gets Resume, and everything else gets what it can honour.
 */
export function controlsFor(job) {
  if (isSettled(job)) return [];
  const status = String(job?.status || "");
  if (status === "paused") return ["resume", "cancel"];
  if (status === "pausing" || status === "cancelling") return ["cancel"];
  if (status === "requires_review") return ["cancel"];
  return ["pause", "cancel"];
}

/** The badge class this status wears. The kit defines exactly three variants --
 *  `.badge.ok`, `.badge.off` and `.badge.danger` (`design/components.css:644-661`) -- and
 *  a class outside that set renders as plain grey, which is the mistake
 *  `renderEngineDetail` already records about `warn`.
 *
 *  `failed` WORE `err` UNTIL REVIEW, AND `err` IS A MESSAGE TONE, NOT A BADGE ONE. `.err`
 *  does exist (`components.css:75`, `color: var(--red)`) but `.chip, .badge` sets
 *  `color: var(--muted)` at equal specificity 550 lines later, so the cascade won and
 *  every failed job drew grey -- indistinguishable from `cancelled` and from a status
 *  this file has never heard of. 28 of the 163 jobs measured on 2026-09-07 were failures,
 *  and they are the rows he is looking for. */
export function statusTone(status) {
  const value = String(status || "");
  if (value === "completed") return "ok";
  if (value === "failed") return "danger";
  if (value === "completed_with_errors" || value === "partially_completed"
      || value === "requires_review") return "off";
  if (value === "cancelled") return "";
  if (HIS_MOVE.has(value)) return "off";
  return "";
}

/** `163 jobs · 1 running · 23 cancelled`, so the page says what it is showing.
 *
 *  NAMED `summariseJobs` AND NOT `summarise`, WHICH IS A HARNESS CONSTRAINT ON THE
 *  PRODUCTION CODE AND WORTH STATING. `tools/panel_harness.py` inlines every panel
 *  module and strips the `import` lines, so a name that exists only as an ALIAS
 *  (`import { summarise as summariseJobs }`) is not defined in the harness at all --
 *  it threw inside `showView`, the page kept its placeholder, and the guard reported
 *  "0 of 4 jobs drawn". `datatable.js` already exports a `summarise` of its own, so
 *  the specific name is the better one regardless. */
export function summariseJobs(payload) {
  const jobs = (payload?.jobs || []).filter(Boolean);
  if (!jobs.length) return "No jobs yet. Start one from the Run screen.";
  const counts = new Map();
  for (const job of jobs) {
    const key = String(job.status || "");
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const parts = [`${jobs.length.toLocaleString()} job${jobs.length === 1 ? "" : "s"}`];
  for (const [status, count] of [...counts.entries()].sort((a, b) => b[1] - a[1])) {
    parts.push(`${count.toLocaleString()} ${statusWords(status)}`);
  }
  return parts.join(" · ");
}

/**
 * The rows to draw, newest first, exactly as the payload ordered them.
 *
 * NOT RE-SORTED HERE. `list_jobs` orders by `job_id DESC`, which is the order they were
 * entered; re-sorting by a timestamp in the page would disagree with it the moment two
 * jobs share a second, and `created_at` is stored at second resolution.
 */
export function rowsFrom(payload) {
  return (payload?.jobs || []).filter((job) => job && job.job_ref).map((job) => ({
    job_ref: job.job_ref,
    label: jobLabel(job),
    status: job.status,
    tone: statusTone(job.status),
    progress: progressLine(job),
    fraction: progressFraction(job),
    waiting: jobWaitingLine(job),
    controls: controlsFor(job),
    settled: isSettled(job),
    live: isMoving(job),
    created_at: job.created_at,
    finished_at: job.finished_at,
    error_summary: job.error_summary || "",
  }));
}


// ---- how fast a crawl is actually going -------------------------------------

/** How far back the rate is measured.
 *
 * Two minutes is long enough to smooth a slow page and short enough that a crawl which
 * changes pace is followed rather than averaged away.
 */
export const RATE_WINDOW_MS = 120000;

//: (time, requests) readings for the job currently being drawn.
let rateSamples = { jobRef: null, points: [] };

/** Record one reading of a job's request count, for `recentRate` to divide.
 *
 * WHY NOT THE WALL CLOCK, WHICH IS WHAT THIS REPLACED. The estimate used to divide by
 * `Date.now() - started_at`, which counts every second since the job began, including
 * the ones in which nothing ran.
 *
 * MEASURED ON HIS MACHINE, 2026-09-21. The laptop slept for 3h 35m in the middle of the
 * Oman register's first crawl -- Windows logged `entering sleep` and `returned from a low
 * power state`, and the stored pages have a hole in exactly that window. The wall clock
 * read **4h 1m for 24 minutes of work**: the rate came out 10x too low, and the estimate
 * it feeds would have printed **325 minutes** where the truth was 32.
 *
 * IT SELF-HEALS AFTER A SLEEP, and that is why this is a window rather than a correction.
 * The first reading after waking prunes every stale point, leaving one, so no estimate is
 * offered until a second arrives a poll later. A missing number is better than a wrong
 * one, and nothing here can carry a stall forward into the answer.
 *
 * `now` IS AN ARGUMENT so a test can state the clock instead of sleeping for it. The
 * caller passes nothing and gets `Date.now()`.
 */
export function observeRate(job, now = Date.now()) {
  const fetched = (job && job.fetch) || {};
  if (!job || !job.job_ref || typeof fetched.requests !== "number") return;
  if (rateSamples.jobRef !== job.job_ref) {
    // A DIFFERENT JOB IS A DIFFERENT CRAWL. Carrying points across would divide one
    // job's requests by another job's seconds.
    rateSamples = { jobRef: job.job_ref, points: [] };
  }
  rateSamples.points.push({ at: now, requests: fetched.requests });
  while (rateSamples.points.length > 1
         && now - rateSamples.points[0].at > RATE_WINDOW_MS) {
    rateSamples.points.shift();
  }
}

/** Requests per second across the window, or `null` when it cannot be said. */
export function recentRate() {
  const points = rateSamples.points;
  if (points.length < 2) return null;
  const first = points[0];
  const last = points[points.length - 1];
  const seconds = (last.at - first.at) / 1000;
  const gained = last.requests - first.requests;
  // `gained <= 0` is a crawl that has stalled, or a counter that went backwards on a
  // resume. Either way there is no honest rate, and dividing by one would print a
  // duration rather than admit that.
  if (seconds <= 0 || gained <= 0) return null;
  return gained / seconds;
}

/** Drop every reading. Exported for tests; the panel never needs it. */
export function forgetRate() {
  rateSamples = { jobRef: null, points: [] };
}
