// The Data page — one source's whole table, read from the engine and drawn by the
// engine's own grid.
//
// PLAN B2, AND IT IS THE PATTERN-SETTER. Five more pages follow this one out of
// the engine, so what this page proves or breaks decides how they are written.
// Three things it is meant to prove:
//
//   1. A tab page can reach the engine at all, through backend.js rather than a
//      second copy of the address and the deadline policy.
//   2. A vendored library is allowed and worth its bytes — writing a second grid
//      to avoid 446 KB would mean re-solving Arabic collation, money formatting
//      and tax verdicts, which is grid.js's real value.
//   3. The payload the engine already serves is enough. `/api/table` was built
//      for the web page it is replacing, and nothing about it had to change.
//
// THE GRID IS THE ENGINE'S OWN (#1198). This page used to draw its own Tabulator
// from the payload, and so showed a different table from /source/<key>: no tax,
// no country names, no currency beside a price, no AR|EN. Now grid.js, the file
// that page runs, runs here too. This file is its HOST: it tells grid.js where
// the engine is, loads the table for it through backend.js, and asks it to
// refresh when the activity filter changes. It draws no table of its own.
//
// WHICH ENDPOINT. The Data page has always run on `/api/table/{source_key}`, not
// on the panel's card endpoint `/api/records`, which is compact, paginated at 100,
// and whose own docstring says "the panel shows cards, never a table".

import { api, backendBase, backendGeneration } from "./backend.js";
// What a wrong sentence could come from lives apart from this page BECAUSE this
// page cannot be imported under `node --test` — it reads window.location and
// starts loading the moment it is imported.
import { sourceKeyFrom, tableRequest, whyNoTable } from "./datatable.js";
import {
  filterSummary, modeLabel, selectionFrom, selectionUrl, treeFrom, undeclaredLine,
} from "./taxonomyfilter.js";

const $ = (id) => document.getElementById(id);

/** Which source this tab is showing. Named in the URL so the tab is shareable
 *  and survives a reload — the panel opens it with ?source=KEY. */
const SOURCE_KEY = sourceKeyFrom(window.location.search);
const SITE_KEY = new URLSearchParams(window.location.search).get("site")?.trim() || "";

/** The activity nodes he has ticked. Issue 543. Seeded from the address, because
 *  the grid reloads the page after a column change, a Reset columns and a fold
 *  change, and a reload keeps only what the address carries. */
const restored = selectionFrom(window.location.search);
const chosen = new Set(restored.nodes);

/** What grid.js hands its host once it has asked for the first table: {refresh}. */
let grid = null;
/** Every table request is numbered, so an answer that a newer one overtook never
 *  writes the status line. grid.js drops that answer's rows on its own. */
let tableAsks = 0;
/** The pause after the last tick before the table is asked again. */
let settling = null;
const SETTLE_MS = 250;

function show(id, text) {
  const node = $(id);
  node.textContent = text || "";
  node.classList.toggle("hidden", !text);
}

function mode() {
  return $("data-activities-mode").value;
}

/**
 * The table, for the path grid.js hands over.
 *
 * IT NEVER ANSWERS WITH SOMETHING THAT IS NOT A TABLE. A failure rejects, with
 * the sentence the owner should read, and grid.js puts it on the page: under the
 * frame when there is no table yet, or in this page's status line when a refresh
 * failed and the last rows stay. Resolving with nothing would reach the grid as
 * "the answer is not a table", which names no cause.
 *
 * THE SELECTION IS READ WHEN THE GRID ASKS, not when it was ticked, so a refresh
 * always carries the newest ticks.
 */
async function loadTable(path) {
  const ask = ++tableAsks;
  const first = grid === null;
  const generation = backendGeneration();
  let answer;
  try {
    answer = await api(tableRequest(path, SITE_KEY, [...chosen], mode()));
  } catch (error) {
    if (generation !== backendGeneration()) throw new Error(MOVED);
    throw new Error(whyNoTable(error, SOURCE_KEY));
  }
  // A DIFFERENT BACKEND IS NOW AUTHORITATIVE. Painting this answer would put one
  // engine's rows under another engine's name.
  if (generation !== backendGeneration()) throw new Error(MOVED);
  // The first table says what an address's selection left. A refresh says it
  // through its own outcome, below.
  if (first && ask === tableAsks) $("data-summary").textContent = filterSummary(answer);
  return answer;
}

const MOVED = "The engine's address changed while the table was loading. Reload the page.";

/** grid.js calls this once, after it has asked for the first table. The first
 *  table already carries the selection read from the address, so this asks for
 *  nothing: a refresh here would ask twice. */
function connect(handle) {
  grid = handle;
}

/** Ask the grid for the table again and say, in the status line, what came of it. */
function refreshNow(doing, failed = "Could not filter") {
  clearTimeout(settling);
  settling = null;
  if (!grid) {
    show("data-blocked", "The grid is not running, so the table cannot be asked "
      + "again. Reload the page.");
    return;
  }
  $("data-summary").textContent = doing;
  grid.refresh().then((outcome) => {
    // A superseded ask says nothing: the newer one will.
    if (outcome.state === "drawn") $("data-summary").textContent = filterSummary(outcome.payload);
  }, (error) => {
    // ROWS ARE CLAIMED ONLY WHEN THERE ARE ROWS. With no table on screen (the first
    // load failed, or the source had none) grid.js has already put the fault in its
    // own note, and a second line here would say it twice, one of them wrongly.
    // Tabulator marks the element it builds into with its own class.
    $("data-summary").textContent = $("grid").classList.contains("tabulator")
      ? `${failed}: ${error.message} The rows below are the last answer drawn.`
      : "";
  });
}

/** The selection, written into this page's address in place: no Back entry. */
function writeAddress() {
  window.history.replaceState(window.history.state, "",
    selectionUrl(window.location.href, [...chosen], mode()));
}

/**
 * A tick, an untick, Clear, or a change of Any/All that changes the answer.
 *
 * THE ADDRESS FIRST, then the table. `replaceState` adds no Back entry per tick,
 * and it has to come before the ask: a reload the grid starts in between keeps
 * only what the address says. Ticks then settle for SETTLE_MS, so four quick
 * ticks cost one request; Clear and Any/All are one decision each and ask at once.
 */
function selectionChanged({now = false} = {}) {
  writeAddress();
  $("data-activities-clear").hidden = chosen.size === 0;
  const doing = chosen.size
    ? `Filtering ${SOURCE_KEY} by ${chosen.size} ${chosen.size === 1 ? "activity" : "activities"}…`
    : "Showing every row again…";
  if (now) {
    refreshNow(doing);
    return;
  }
  $("data-summary").textContent = doing;
  clearTimeout(settling);
  settling = setTimeout(() => refreshNow(doing), SETTLE_MS);
}

/**
 * The activity tree, drawn once per source.
 *
 * BUILT WITH `textContent`, NEVER MARKUP. Every one of these names came off
 * muqawil.org, and this repository treats scraped content as untrusted input.
 */
function drawNode(node) {
  const li = document.createElement("li");
  const label = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.value = String(node.node_id);
  box.checked = chosen.has(node.node_id);
  box.addEventListener("change", () => {
    if (box.checked) chosen.add(node.node_id);
    else chosen.delete(node.node_id);
    selectionChanged();
  });
  const name = document.createElement("span");
  name.textContent = node.name_ar || node.name || String(node.node_id);
  const held = document.createElement("span");
  held.className = "held";
  held.textContent = Number(node.held || 0).toLocaleString();
  label.append(box, name, held);
  li.append(label);
  if (node.children?.length) {
    const list = document.createElement("ul");
    node.children.forEach((child) => list.append(drawNode(child)));
    li.append(list);
  }
  return li;
}

async function loadActivities() {
  // NOTHING IS ASKED WITHOUT A SOURCE, and the guard is here rather than at the one
  // call below because `test_a_page_opened_with_no_source_asks_for_one` counts the
  // requests a sourceless page makes.
  if (!SOURCE_KEY) return;
  // NOT CALLED `payload`, AND THAT IS NOT A STYLE CHOICE:
  // `test_the_table_payload_answers_every_key_its_readers_read` derives the table
  // contract from dotted reads off a variable of that name, comments included.
  let answer;
  try {
    answer = await api(`/api/taxonomy/${encodeURIComponent(SOURCE_KEY)}`);
  } catch (_) {
    // NOT A SECOND RED LINE. The table already says when the engine is not
    // answering, and reporting one fault twice is how a screen stops being read.
    // But a selection from the address narrows the table whether or not this
    // answers, and it must stay possible to take it off.
    strandedSelection();
    return;
  }
  const group = (answer?.groups || [])[0];
  const roots = group ? treeFrom(group) : [];
  if (!roots.length) {
    strandedSelection();
    return;
  }
  const list = document.createElement("ul");
  roots.forEach((node) => list.append(drawNode(node)));
  $("data-activities-tree").replaceChildren(list);
  $("data-undeclared").textContent = undeclaredLine(group);
  $("data-activities-toggle").textContent =
    group.scheme?.name_ar || group.scheme?.name || "Activities";
  $("data-activities").classList.remove("hidden");
  // An address that carried a selection opens on it, first ticked box in view.
  if (chosen.size) {
    $("data-activities-tree").classList.remove("hidden");
    $("data-activities-toggle").setAttribute("aria-expanded", "true");
    $("data-activities-tree").querySelector("input:checked")?.scrollIntoView({block: "nearest"});
  }
}

/**
 * The address carried a selection and the list it came from could not be drawn: the
 * taxonomy was refused, timed out, or has no groups. The table is still narrowed by
 * it, so the control to take it off is shown with a line saying why the list is not.
 */
function strandedSelection() {
  if (!chosen.size) return;
  $("data-activities-toggle").hidden = true;
  $("data-undeclared").textContent = `The list of activities could not be read, so the `
    + `${chosen.size} chosen in this page's address cannot be shown. The table is narrowed `
    + "by them; Clear shows every row.";
  $("data-activities").classList.remove("hidden");
}

function sayMode() {
  $("data-activities-mode-label").textContent = modeLabel(mode());
}

/** What grid.js reads as it starts, none of which it can do without. */
const GRID_NEEDS = ["Tabulator", "ScrapeXUI", "ScrapeXSplitButton", "ScrapeXTime"];

async function start() {
  if (!SOURCE_KEY) {
    show("data-blocked", "This page needs a source: open it from the panel, or "
      + "add ?source=SOURCE_KEY to the address.");
    $("data-frame").classList.add("hidden");
    $("grid-note").hidden = true;
    return;
  }
  document.title = `${SOURCE_KEY} — ScrapeX`;
  $("data-source").textContent = SOURCE_KEY;
  $("data-features-scope").textContent = `Saved for ${SOURCE_KEY}`;
  $("data-activities-mode").value = restored.mode;
  sayMode();
  $("data-activities-clear").hidden = chosen.size === 0;

  // SAID, NOT SILENT. grid.js returns without a word when Tabulator is missing,
  // and throws on its first line when ui.js is; either way no table and no reason.
  const missing = GRID_NEEDS.filter((name) => !window[name]);
  if (missing.length) {
    show("data-blocked", `The table cannot start: ${missing.join(", ")} did not load. `
      + "Reload the page; if it stays, reinstall the extension.");
    $("grid-note").hidden = true;
    return;
  }

  // RESOLVE THE ADDRESS BEFORE ANYTHING READS ITS GENERATION, and the order is
  // the whole of it. `backendBase()` ACTIVATES the backend the first time it is
  // called, and activating bumps the generation. Reading the number first meant
  // reading 0, asking, and then finding 1 — so the guard decided a different
  // engine was authoritative and returned WITHOUT PAINTING. Every first load did
  // that, in production, for everyone, and no static test saw it (#194).
  const base = await backendBase();
  $("grid").dataset.source = SOURCE_KEY;
  // grid.js reads the host once, as it starts, so the host is set first.
  window.ScrapeXGridHost = Object.freeze({base, loadTable, connect});
  const script = document.createElement("script");
  script.addEventListener("error", () => {
    show("data-blocked", "The table's script did not load. Reload the page; if it "
      + "stays, reinstall the extension.");
    $("grid-note").hidden = true;
  });
  // connect() runs inside grid.js, before this event. No handle by now means the
  // grid returned before it started.
  script.addEventListener("load", () => {
    if (!grid) show("data-blocked", "The table's script ran but the grid did not start.");
  });
  script.src = "grid.js";
  document.body.append(script);
  loadActivities();
}

$("data-reload").addEventListener("click",
  () => refreshNow("Asking the engine again…", "Could not reload"));
$("data-activities-toggle").addEventListener("click", () => {
  const open = $("data-activities-tree").classList.toggle("hidden") === false;
  $("data-activities-toggle").setAttribute("aria-expanded", String(open));
});
$("data-activities-mode").addEventListener("change", () => {
  sayMode();
  // ONLY WHEN IT CHANGES SOMETHING. Any and All are the same question for one node,
  // so flipping the toggle with nothing or one thing ticked writes the address and
  // asks nothing.
  if (chosen.size > 1) selectionChanged({now: true});
  else writeAddress();
});
$("data-activities-clear").addEventListener("click", () => {
  chosen.clear();
  $("data-activities-tree").querySelectorAll("input[type=checkbox]")
    .forEach((box) => { box.checked = false; });
  selectionChanged({now: true});
});

start();
