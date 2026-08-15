// The Data page — one source's whole table, read from the engine and drawn here.
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
// WHICH ENDPOINT, AND WHY NOT THE ONE THE PLAN NAMED. The plan said
// `/api/records` "already exists for it". It does not: `/api/records` is the
// PANEL's card endpoint — compact, paginated at 100, and its own docstring says
// "the panel shows cards, never a table". The Data page has always run on
// `/api/table/{source_key}`, whose payload is deliberately leaner per row
// because the tax verdict travels once per region instead of on every row.
// Building this on the card endpoint would have shipped cards and called it the
// migration.

import { api, backendBase, backendGeneration } from "./backend.js";
// The reading of a payload lives apart from this page BECAUSE this page cannot
// be imported under `node --test` — it reads window.location and starts loading
// the moment it is imported. Everything a wrong number could come from is in
// datatable.js, where hostile input can be pushed through it.
import { columnsFrom, foldControl, sourceKeyFrom, summarise, truncationNotice }
  from "./datatable.js";

const $ = (id) => document.getElementById(id);

/** Which source this tab is showing. Named in the URL so the tab is shareable
 *  and survives a reload — the panel opens it with ?source=KEY. */
const SOURCE_KEY = sourceKeyFrom(window.location.search);

let table = null;

function show(id, text) {
  const node = $(id);
  node.textContent = text || "";
  node.classList.toggle("hidden", !text);
}

async function load() {
  if (!SOURCE_KEY) {
    show("data-blocked", "This page needs a source: open it from the panel, or "
      + "add ?source=SOURCE_KEY to the address.");
    return;
  }
  // RESOLVE THE ADDRESS BEFORE READING ITS GENERATION, and the order is the
  // whole of it. `backendBase()` ACTIVATES the backend the first time it is
  // called, and activating bumps the generation. Capturing the number first
  // meant capturing 0, asking, and then finding 1 — so the guard below decided
  // a different engine was authoritative and returned WITHOUT PAINTING.
  //
  // Every first load did that. The page said "Reading…" for ever, in
  // production, for everyone, and no test saw it: 2,460 engine tests and 398
  // extension tests all pass on a page nobody had ever rendered. It was found
  // by opening it in a browser, which is the only thing that could have.
  await backendBase();
  const generation = backendGeneration();
  show("data-blocked", "");
  $("data-source").textContent = SOURCE_KEY;
  $("data-summary").textContent = "Reading…";

  let payload;
  try {
    const wanted = $("data-fold").checked ? "1" : "0";
    payload = await api(
      `/api/table/${encodeURIComponent(SOURCE_KEY)}?fold=${wanted}`);
  } catch (error) {
    // A DIFFERENT BACKEND IS NOW AUTHORITATIVE. Painting this answer would put
    // one engine's rows under another engine's name.
    if (generation !== backendGeneration()) return;
    $("data-summary").textContent = "";
    show("data-blocked", `The engine did not answer: ${error.message}. It may be `
      + "stopped — the panel's Run screen starts it.");
    return;
  }
  if (generation !== backendGeneration()) return;

  // The fold switch reflects what the source is SET to until the reader says
  // otherwise, so it is only pushed from the payload on the first load.
  if (table === null) $("data-fold").checked = Boolean(payload.folded);
  const fold = foldControl(payload);
  $("data-fold").disabled = fold.disabled;
  $("data-fold-label").textContent = fold.label;

  $("data-summary").textContent = summarise(payload);
  show("data-truncated", truncationNotice(payload));

  const rows = payload.rows || [];
  if (table === null) {
    table = new window.Tabulator("#data-grid", {
      data: rows,
      columns: columnsFrom(payload),
      layout: "fitDataStretch",
      // The whole table is already in memory; the grid pages it so a source
      // with twenty thousand rows does not put twenty thousand nodes in the DOM.
      pagination: true,
      paginationSize: 100,
      paginationCounter: "rows",
      placeholder: "This source has no rows yet. Run a crawl from the panel.",
      height: "100%",
      index: "offer_id",
    });
  } else {
    table.setColumns(columnsFrom(payload));
    table.replaceData(rows);
  }
}

$("data-reload").addEventListener("click", load);
$("data-fold").addEventListener("change", load);

load();
