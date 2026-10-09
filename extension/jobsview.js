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
                         "partially_completed", "failed", "skipped"]);

/** Where the worker is holding the job, from `vocab.WORKER_HELD_STATUSES` plus the two
 *  transitional statuses `set_control` parks a held job in. A job in one of these owns a
 *  runtime; anything else non-terminal is waiting for one or for him. */
const HELD = new Set(["preparing", "running", "resuming", "pausing", "cancelling"]);

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

/** `completed_with_errors` as `completed with errors`. The panel un-underscores a status
 *  everywhere it shows one -- `renderActivity`, `renderMiniplayer` and the Jobs rows
 *  (`statusLook`) -- so one screen never spells one status two ways. */
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

/** A source's domain, the panel's primary identity for it: the URL's host, lower-case,
 *  without a leading `www.` or a trailing dot. `sourceDomain` in app.js is this. */
export function domainOf(url) {
  let host = "";
  try { host = new URL(url).host; } catch (_) { host = String(url || ""); }
  host = host.replace(/\.$/, "");
  return host.toLowerCase().startsWith("www.") ? host.slice(4) : host;
}

/** The Sources entry a key names, by its `source_key` or the `site_key` behind it. */
export function sourceOf(key, sources) {
  return (sources || []).find((one) => one && (one.source_key === key
    || one.site_key === key)) || null;
}

/** The source a job is on now, else its first: the one its name leads with. */
export function jobLead(job) {
  return job?.current_source_key || (job?.source_keys || [])[0] || "";
}

/** "and 2 others" for a job of several sources; "" for one. */
export function othersLine(job) {
  const others = Math.max(0, (job?.source_keys || []).length - 1);
  return others ? `and ${others} other${others === 1 ? "" : "s"}` : "";
}

/** How the panel names one source key: the Sources identity's domain, else its name,
 *  else the key. A job carries keys only; a site's key can also arrive as the
 *  `site_key` behind a dataset card (`webui/app.py:942-947`), and a dataset's as its
 *  `source_key`, so either finds it. */
export function sourceTitle(key, sources) {
  const source = sourceOf(key, sources);
  if (!source) return key;
  return domainOf(source.base_url) || source.source_name || key;
}

/**
 * `Listing crawl · muqawil.org` -- the kind, and the source as the panel names sources.
 *
 * THE KIND STAYS (see `renderMiniplayer`): a crawl's chained interpretation starts on
 * the same source a few milliseconds after the crawl ends, and without the kind the line
 * reads as the crawl starting over. THE SOURCE IS THE PANEL'S ONE IDENTITY, the domain
 * (`sourceIdentity`, components.css:781), and no longer the key: this read the key "from
 * the payload's own words" because a job carries nothing else, so the row, the player
 * and the Sources page named one site three ways (#1542). Without `sources`, the key.
 */
export function jobLabel(job, sources = []) {
  const kind = KIND_LABELS[job?.job_kind] || String(job?.job_kind || "Job");
  const lead = jobLead(job);
  if (!lead) return kind;
  const more = othersLine(job);
  return `${kind} · ${sourceTitle(lead, sources)}${more ? ` ${more}` : ""}`;
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
  if (job?.status === "skipped") return "";   // never ran: "0 of 1" would say it did
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
  if (job?.status === "skipped") return null;   // never ran: no bar, not an empty one
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

/** The class a job's `error_summary` is drawn in. A skipped job's summary is the reason
 *  the schedule passed it over (#1596), not an error, so it is muted rather than red. */
export function summaryClass(status) {
  return String(status || "") === "skipped" ? "muted" : "err";
}

// ---- the Jobs page's own rules (#1542) ---------------------------------------------

/** Each status's glyph and tone. The WORD is the engine's own, sentence-cased: no job
 *  state is renamed here. Tones follow Studio (PreviousRunsTab.tsx@86c813ec:222-247:
 *  running muted, success brand-600, failed destructive, words coloured too;
 *  ProjectCardStatus.tsx@86c813ec:110-114, 171-187: paused in the foreground, the
 *  in-between states in warning). Glyphs are the Material sprite's until #1057 moves the
 *  panel to Lucide (docs/DESIGN-SYSTEM.md, Icons; his decision of 2026-10-09). */
const STATUS_LOOK = {
  running: ["material-pending", "secondary"],
  resuming: ["material-sync", "warning"],
  preparing: ["material-sync", "warning"],
  queued: ["material-schedule", "default"],
  scheduled: ["material-schedule", "default"],
  paused: ["material-pause-circle", "foreground"],
  pausing: ["material-pause-circle", "warning"],
  cancelling: ["material-block", "warning"],
  requires_review: ["material-warning", "warning"],
  failed: ["material-cancel", "destructive"],
  partially_completed: ["material-warning", "warning"],
  completed_with_errors: ["material-warning", "warning"],
  completed: ["material-check-circle", "brand"],
  cancelled: ["material-block", "default"],
  // #1596, his ruling D4: a scheduled firing that found its source busy and did not run.
  // THE TONE IS STUDIO'S: it draws its own skipped step as a plain `default` badge
  // (BranchManagement/ActionStatusBadge.tsx@86c813ec:18, 79), the tone a cancel wears
  // here -- the word in the foreground, the glyph muted, nothing like a failure. He chose
  // this (option C, 2026-10-09, on #1596) over `secondary`, which drew a skip exactly as
  // a running job is drawn. THE ONE DEPARTURE IS THE GLYPH: Studio's badge has none, and
  // this page's rule is that every status has one, so it takes Material's `next_plan` --
  // passed over, on to the next slot.
  skipped: ["material-next-plan", "default"],
};

export function statusLook(status) {
  const words = statusWords(status);
  const [glyph, tone] = STATUS_LOOK[String(status || "")] || ["material-info", "default"];
  return {word: words ? words[0].toUpperCase() + words.slice(1) : "", glyph, tone};
}

/**
 * When the job ran, as the warehouse stored it: "Started 7 Oct, 8:00 AM → 9:12 AM".
 *
 * NO DURATION, AND THAT IS THE POINT (his choice C). `started_at` survives a resume
 * (jobs.py:936) and no pause is stamped, so finish minus start counts pauses, waits for
 * the site's turn and a sleeping laptop -- 3 h 35 m of one crawl, measured. A job that
 * never started reads from `created_at`. A finish on another day carries its date, and
 * a cancel says so whichever state it was cancelled from. So does a skip (#1596), which
 * never started: "Added 9 Oct, 6:00 AM → skipped 6:00 AM". `fmt` is ScrapeXTime.format.
 */
export function timeLine(job, fmt) {
  const begun = job?.started_at;
  const from = begun ? `Started ${fmt(begun, "short")}`
    : job?.created_at ? `Added ${fmt(job.created_at, "short")}` : "";
  const end = job?.finished_at;
  if (!end || !from) return from;
  const sameDay = fmt(end, "date") === fmt(begun || job.created_at, "date");
  const when = sameDay ? fmt(end, "time") : fmt(end, "short");
  const how = job.status === "cancelled" || job.status === "skipped" ? `${job.status} ` : "";
  return `${from} → ${how}${when}`;
}

/** The line above the list: what is shown, out of what, and whether it is live. It is
 *  not a live region; a change he made is announced on its own. */
/** "1 job", "1,234 jobs": the count of jobs, worded one way wherever it is said. */
export function jobsNoun(n) {
  return `${n.toLocaleString()} job${n === 1 ? "" : "s"}`;
}

export function jobsCountLine({shown, total, live, seconds = 1.5, readAt, bounded, kept}, fmt) {
  const noun = jobsNoun;
  const parts = [bounded
    ? (shown === total ? `Newest ${total} jobs shown; older jobs are not listed`
      : `${shown.toLocaleString()} of the newest ${total} jobs`)
    : shown === total ? noun(total) : `${shown.toLocaleString()} of ${noun(total)}`];
  if (kept) parts.push(`${kept} kept until you change the filter`);
  if (live) parts.push(`Refreshes every ${seconds}s while a job is in progress or queued`);
  else if (readAt) parts.push(`Read at ${fmt(readAt, "time")}`);
  return parts.join(" · ");
}

/** THE SOURCES SEARCH, in one place: a source matches a term on its English or Arabic
 *  name, its key, or its domain. The Sources page and the Jobs page both ask this, so
 *  the two searches cannot drift apart (#1623's gate). */
export function sourceMatches(source, term) {
  const wanted = String(term || "").trim().toLowerCase();
  if (!wanted) return true;
  return [source?.source_name, source?.source_name_ar, source?.source_key,
    domainOf(source?.base_url)]
    .some((field) => String(field || "").toLowerCase().includes(wanted));
}

/** Search on the Jobs page: any of a job's sources matches as the Sources search would,
 *  and so does the job's own key -- which is all there is for one Sources does not list. */
export function jobMatches(job, term, sources = []) {
  const wanted = String(term || "").trim().toLowerCase();
  if (!wanted) return true;
  return (job?.source_keys || []).some((key) => {
    const source = sourceOf(key, sources);
    return String(key).toLowerCase().includes(wanted) || Boolean(source && sourceMatches(source, wanted));
  });
}

/** The statuses the filter offers: those in the list, plus any he selected whose last
 *  job has since settled into another, so he can still untick it. */
export function filterOptions(jobs, selected = new Set()) {
  const seen = [];
  for (const status of [...selected, ...(jobs || []).map((job) => job.status)]) {
    if (status && !seen.includes(status)) seen.push(status);
  }
  return seen;
}

/** The one action a row shows (table.mdx@86c813ec:201): Pause or Resume. */
export function primaryControl(job) {
  return controlsFor(job).find((control) => control !== "cancel") || null;
}

/** The rest, in the row's menu: its log, and Cancel where Cancel can still act. */
export function menuControls(job) {
  const status = String(job?.status || "");
  const cancel = controlsFor(job).includes("cancel") && status !== "cancelling";
  return cancel ? ["log", "cancel"] : ["log"];
}

export function refusalLine(control, label, status) {
  const verb = control[0].toUpperCase() + control.slice(1);
  return `${verb} was refused: ${label} is already ${statusWords(status)}`;
}

/** Which narrowing emptied the list. Studio's NoSearchResults wording for a search
 *  (NoSearchResults.tsx@86c813ec:29-32); its `description` for the other two. */
export function noResultsLine({term, statuses}) {
  const searched = String(term || "").trim();
  if (searched && statuses) return "No job matches the search and the selected statuses";
  if (searched) return `Your search for “${searched}” did not return any results`;
  return "No job has the selected statuses";
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
