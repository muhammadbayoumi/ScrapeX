// The Console — reads the add-in's configuration workbook, and says what is
// wrong with it before offering to change anything.
//
// THE ENGINE IS NOT INVOLVED. No fetch to 127.0.0.1, no import from anything
// that talks to it. The owner's ruling, restated 2026-08-12: «الكونسول يخص
// extension بنسبة 100%، المحرك غير مسؤول عنه اطلاقا».

import { getToken } from "./identity.js";
import { chooseSpreadsheet } from "./picker.js";
import { TAB_NAMES, parseWorkbook, inspect, vocabularies, SHEETS } from "./workbook.js";
import { KNOWN_VOCABULARIES, SHEET_GIDS, LICENSE_TIERS, readBoolean,
         BOOLEAN_DEFAULTS } from "./addin-contract.js";
import { checkDataSourceRow, stopsThisSource, switchedOff, suggestedKey }
  from "./datasource-rules.js";

const $ = (id) => document.getElementById(id);
const SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets";

//: Where the chosen workbook is remembered. storage.local, not session: this is
//: a decision about which file the add-in reads, not a passing choice, and
//: making the owner find it again every morning would be its own defect.
const REMEMBERED = "scrapexConfigWorkbook";

const SOURCES = "3.DataSource";
const state = {token: "", fileId: "", name: "", workbook: null, editing: null};

function say(id, text, tone = "") {
  const node = $(id);
  if (!node) return;
  node.textContent = text;
  node.className = tone ? `hint ${tone}` : "hint";
}

// ---- Google -----------------------------------------------------------------

async function ask(path, token) {
  const answer = await fetch(`${SHEETS_API}/${path}`, {
    headers: {Authorization: `Bearer ${token}`},
  });
  if (!answer.ok) {
    let detail = `${answer.status}`;
    try {
      const body = await answer.json();
      detail = body?.error?.message || detail;
    } catch { /* a body that is not JSON tells us nothing extra */ }
    throw new Error(detail);
  }
  return answer.json();
}

/**
 * The tab ids of a spreadsheet, by tab name.
 *
 * `spreadsheets.get` with a fields mask, because the whole document would be
 * megabytes of cell data to answer a question about six names.
 */
async function tabsOf(fileId, token) {
  const book = await ask(
    `${encodeURIComponent(fileId)}?fields=properties.title,sheets.properties`,
    token);
  const tabs = {};
  for (const sheet of book.sheets || []) {
    const properties = sheet.properties || {};
    tabs[properties.title] = String(properties.sheetId);
  }
  return {title: book.properties?.title || "", tabs};
}

/** All six tabs in one call. */
async function readWorkbook(fileId, token) {
  const ranges = TAB_NAMES
    .map((tab) => `ranges=${encodeURIComponent(`'${tab}'!A1:CA2000`)}`)
    .join("&");
  const answer = await ask(
    `${encodeURIComponent(fileId)}/values:batchGet?${ranges}`, token);
  return parseWorkbook(answer.valueRanges || []);
}

// ---- is this even the right file --------------------------------------------

/**
 * THE CHECK THAT COMES BEFORE EVERY OTHER CHECK.
 *
 * The add-in does not find its configuration by name. `EndpointCatalog` carries
 * six tab ids compiled into the build, and fetches each one directly. So a
 * workbook can have all six tab NAMES, look perfect, and be a copy the add-in
 * has never read — and a Console that checked it would report that everything
 * is fine about a file nobody opens. That is a worse outcome than refusing.
 */
function identify(tabs) {
  const wrong = [];
  const absent = [];
  for (const [tab, gid] of Object.entries(SHEET_GIDS)) {
    if (!(tab in tabs)) absent.push(tab);
    else if (tabs[tab] !== gid) wrong.push({tab, found: tabs[tab], wanted: gid});
  }
  return {ok: !wrong.length && !absent.length, wrong, absent};
}

// ---- what it says -----------------------------------------------------------

function renderFindings(found) {
  const list = $("findings-list");
  list.textContent = "";

  const broken = found.filter((f) => f.severity === "broken");
  const unused = found.filter((f) => f.severity === "unused");

  if (!found.length) {
    say("findings-summary",
        "Nothing to report. Every reference resolves and every source has an "
        + "address the add-in can read.", "ok");
    return;
  }

  say("findings-summary",
      `${broken.length} ${broken.length === 1 ? "problem" : "problems"} that `
      + `would change what the add-in loads, and ${unused.length} that would `
      + "not.");

  for (const finding of found) {
    const row = document.createElement("div");
    row.className = `finding finding-${finding.severity}`;

    const where = document.createElement("span");
    where.className = "finding-where";
    where.textContent = finding.row
      ? `${finding.tab} · row ${finding.row}`
      : finding.tab;

    const kind = document.createElement("span");
    kind.className = "finding-kind";
    kind.textContent = finding.kind;

    const detail = document.createElement("p");
    detail.className = "finding-detail";
    detail.textContent = finding.detail;

    row.append(where, kind, detail);
    list.append(row);
  }
}

function renderSheets(workbook) {
  const list = $("sheets-list");
  list.textContent = "";
  const lists = vocabularies(workbook, KNOWN_VOCABULARIES);

  for (const tab of TAB_NAMES) {
    const sheet = workbook.sheets[tab];
    const row = document.createElement("div");
    row.className = "sheet-row";

    const name = document.createElement("span");
    name.className = "sheet-name";
    name.textContent = tab;

    const count = document.createElement("span");
    count.className = "sheet-count";
    count.textContent = sheet ? `${sheet.rows.length} rows` : "not found";

    row.append(name, count);
    list.append(row);
  }

  const note = document.createElement("p");
  note.className = "hint";
  note.textContent =
    `${lists.entityKeys.length} tables, ${lists.profileKeys.length} mapping `
    + `profiles, ${lists.sourceKeys.length} sources.`;
  list.append(note);
}


// ---- navigation --------------------------------------------------------------
//
// THE PANEL'S OWN SHAPE, deliberately: a registry of screen names, sections
// called `cv-<name>`, and rail buttons carrying `data-view`. A second navigation
// idiom in the same product is a second thing to learn for no gain.
//
// `inspect` is in the registry and NOT in the rail: it is reached by choosing a
// table, and a rail button for it would be a button with nothing to show.

const VIEWS = ["overview", "scrapex", "tables", "inspect", "sources", "problems"];

function showView(name) {
  for (const view of VIEWS) {
    $(`cv-${view}`)?.classList.toggle("hidden", view !== name);
  }
  // Inspect belongs to Tables, so the rail keeps Tables lit rather than going
  // blank on a screen that is plainly still about a table.
  const lit = name === "inspect" ? "tables" : name;
  for (const button of document.querySelectorAll(".rail-link[data-view]")) {
    const on = button.dataset.view === lit;
    button.setAttribute("aria-selected", String(on));
    button.tabIndex = on ? 0 : -1;
  }
  document.querySelector(".console-main")?.scrollTo({top: 0});
}

// ---- the source list and its editor ------------------------------------------

/** The world a row is judged against, rebuilt from whatever is loaded now. */
function worldFor(workbook, exceptRow = null) {
  const rows = (tab) => (workbook.sheets[tab]?.rows) || [];
  const tables = rows("1.TableDefinition");
  return {
    entities: tables.map((r) => r.ENTITY_KEY).filter(Boolean),
    activeEntities: tables
      .filter((r) => readBoolean(r.IS_ACTIVE,
                                 BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE))
      .map((r) => r.ENTITY_KEY).filter(Boolean),
    profilesDefined: [...new Set(rows("4.DataMap")
      .map((r) => r.PROFILE_KEY).filter(Boolean))],
    others: rows(SOURCES).filter((r) => r !== exceptRow),
  };
}

function renderSources(workbook) {
  const list = $("sources-list");
  list.textContent = "";
  const rows = workbook.sheets[SOURCES]?.rows || [];

  let dead = 0;
  let noted = 0;
  for (const row of rows) {
    const found = checkDataSourceRow(row, worldFor(workbook, row));
    const stops = stopsThisSource(found);
    const off = switchedOff(found);
    if (stops) dead += 1;
    if (found.length && !stops) noted += 1;

    const item = document.createElement("button");
    item.type = "button";
    item.className = "source-row"
      + (stops ? " source-stopped" : found.length ? " source-noted" : "");
    item.addEventListener("click", () => edit(row));

    const key = document.createElement("span");
    key.className = "source-key";
    key.textContent = row.SOURCE_KEY || "(no key)";

    const into = document.createElement("span");
    into.className = "source-into";
    into.textContent = row.TARGET_ENTITY_KEY || "—";

    const verdict = document.createElement("span");
    verdict.className = "source-verdict";
    // THREE DIFFERENT THINGS, said differently. "Nothing comes out" is a
    // failure; "switched off" is a decision; a note is neither.
    verdict.textContent = stops ? "produces nothing"
      : off ? "switched off"
      : found.length ? `${found.length} note${found.length === 1 ? "" : "s"}`
      : "";

    item.append(key, into, verdict);
    list.append(item);
  }

  say("sources-summary",
      `${rows.length} sources. ${dead} produce nothing; ${noted} have something `
      + "worth reading. Choose one to edit.",
      dead ? "err" : "");
  $("count-sources").textContent = rows.length || "";
}

/** Fill a `<select>`, keeping a value the sheet already holds even if unlisted. */
function options(id, values, current, {blank = ""} = {}) {
  const select = $(id);
  select.textContent = "";
  const all = [...values];
  if (current && !all.some((v) => String(v).toLowerCase() === current.toLowerCase())) {
    // NEVER SILENTLY REPLACE WHAT IS IN THE SHEET. An unknown value is a fact
    // about the workbook, and a drop-down that quietly dropped it would change
    // the row the moment it was opened.
    all.unshift(current);
  }
  if (blank !== null) {
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = blank;
    select.append(empty);
  }
  for (const value of all) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
  select.value = current ?? "";
}

const FIELDS = ["SOURCE_KEY", "TARGET_ENTITY_KEY", "PROFILE_KEY", "SOURCE_URI",
                "DISPLAY_LABEL", "SOURCE_REGION", "IS_ACTIVE", "MIN_LICENSE_REQ",
                "VERSION_TAG", "CONTEXT_PROPS"];

function readForm() {
  const row = {};
  for (const name of FIELDS) row[name] = $(`f-${name}`).value.trim();
  if (state.editing?._row) row._row = state.editing._row;
  return row;
}

/** Re-judge the form as it stands and put each finding beside its own field. */
function judge() {
  const row = readForm();
  const found = checkDataSourceRow(row, worldFor(state.workbook, state.editing));

  for (const name of FIELDS) {
    const note = $(`n-${name}`);
    if (!note) continue;
    const mine = found.filter((f) => f.field === name);
    note.textContent = mine
      .map((f) => f.fix ? `${f.detail} ${f.fix}` : f.detail).join(" ");
    note.className = "field-note"
      + (mine.some((f) => f.severity === "Critical" || f.severity === "Error")
         ? " note-error"
         : mine.length ? " note-warn" : "");
  }

  const stops = stopsThisSource(found);
  const blocking = found.filter(
    (f) => f.severity === "Critical" || f.severity === "Error");

  // SAVING IS REFUSED ONLY WHEN THE ROW WOULD PRODUCE NOTHING. A row the add-in
  // merely complains about is a row the add-in still runs, and a Console that
  // refused it would be stricter than the thing it configures — which teaches
  // an owner to edit the sheet directly and never come back.
  $("editor-save").disabled = stops;
  say("editor-verdict",
      stops
        ? "As it stands this source produces nothing. Saving is refused."
        : blocking.length
          ? `Saveable. The add-in will record ${blocking.length} `
            + `${blocking.length === 1 ? "complaint" : "complaints"} about it and sync it anyway.`
          : "Nothing to report.",
      stops ? "err" : blocking.length ? "" : "ok");
  return found;
}

function edit(row) {
  state.editing = row;
  const workbook = state.workbook;
  const lists = vocabularies(workbook, KNOWN_VOCABULARIES);
  const profiles = [...new Set([...lists.profileKeys, "DEFAULT"])].sort();

  $("editor-where").textContent = row._row
    ? `${SOURCES}, row ${row._row}`
    : `${SOURCES}, a new row at the end`;

  $("f-SOURCE_KEY").value = row.SOURCE_KEY || "";
  options("f-TARGET_ENTITY_KEY", lists.entityKeys, row.TARGET_ENTITY_KEY || "",
          {blank: "— choose a table —"});
  options("f-PROFILE_KEY", profiles, row.PROFILE_KEY || "",
          {blank: "— blank: use the table's own key —"});
  $("f-SOURCE_URI").value = row.SOURCE_URI || "";
  $("f-DISPLAY_LABEL").value = row.DISPLAY_LABEL || "";
  options("f-SOURCE_REGION", ["GLOBAL", ...lists.regions], row.SOURCE_REGION || "",
          {blank: "— none —"});
  $("f-IS_ACTIVE").value =
    readBoolean(row.IS_ACTIVE, BOOLEAN_DEFAULTS[SOURCES].IS_ACTIVE) ? "TRUE" : "FALSE";
  options("f-MIN_LICENSE_REQ", LICENSE_TIERS, row.MIN_LICENSE_REQ || "",
          {blank: "— none —"});
  $("f-VERSION_TAG").value = row.VERSION_TAG || "";
  $("f-CONTEXT_PROPS").value = row.CONTEXT_PROPS || "";

  showView("sources");
  $("editor-card").classList.remove("hidden");
  judge();
  $("editor-card").scrollIntoView({behavior: "smooth", block: "start"});
}

/** Write the row back, and only that row. */
async function save() {
  const row = readForm();
  const columns = SHEETS.find((s) => s.tab === SOURCES).columns;
  const values = [columns.map((name) => row[name] ?? "")];

  // A1 for the row's OWN span, so a save cannot touch a neighbour. A new row
  // goes to the first line after the last one read.
  const last = state.workbook.sheets[SOURCES].rows.at(-1);
  const line = row._row || ((last?._row || 1) + 1);
  const end = String.fromCharCode("A".charCodeAt(0) + columns.length - 1);
  const range = `'${SOURCES}'!A${line}:${end}${line}`;

  $("editor-save").disabled = true;
  say("editor-verdict", "Saving…");
  try {
    const answer = await fetch(
      `${SHEETS_API}/${encodeURIComponent(state.fileId)}/values/`
      + `${encodeURIComponent(range)}?valueInputOption=RAW`,
      {method: "PUT",
       headers: {Authorization: `Bearer ${state.token}`,
                 "Content-Type": "application/json"},
       body: JSON.stringify({values})});
    if (!answer.ok) {
      let detail = `${answer.status}`;
      try { detail = (await answer.json())?.error?.message || detail; } catch { /* */ }
      throw new Error(detail);
    }
  } catch (error) {
    say("editor-verdict", `Not saved: ${error.message}`, "err");
    $("editor-save").disabled = false;
    return;
  }

  // RE-READ RATHER THAN PATCH IN MEMORY. The sheet is the truth, another editor
  // may have moved something, and a Console showing its own optimistic copy is
  // the beginning of the drift this page exists to prevent.
  $("editor-card").classList.add("hidden");
  state.editing = null;
  await show(state.fileId);
}


// ---- what this tool collects, and whether the add-in knows ------------------

//: ScrapeX's own sources, as the add-in would have to name them. Read from the
//: workbook rather than typed here: the three that exist are already named
//: ScrapeX_*, and the convention is the only thing that ties the two products
//: together. A hard-coded list would be wrong the first time a source is added.
const SCRAPEX_MARK = /^(ScrapeX|Agent)_/i;

function renderScrapeX(workbook) {
  const list = $("scrapex-list");
  list.textContent = "";
  const sources = workbook.sheets[SOURCES]?.rows || [];
  const mine = sources.filter((r) => SCRAPEX_MARK.test(r.SOURCE_KEY || ""));
  const entities = new Set((workbook.sheets["1.TableDefinition"]?.rows || [])
    .map((r) => r.ENTITY_KEY).filter(Boolean));

  for (const row of mine) {
    const table = row.TARGET_ENTITY_KEY || "";
    const known = entities.has(table);
    list.append(pairRow(row.SOURCE_KEY, table || "—",
                        known ? "registered" : "no such table",
                        known ? "" : "pair-missing",
                        known ? () => showTable(table) : null));
  }

  if (!mine.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent =
      "No source in this workbook is named ScrapeX_… or Agent_…, so nothing "
      + "here is recognisably this tool's.";
    list.append(empty);
  }

  say("scrapex-summary",
      `${mine.length} of this workbook's ${sources.length} sources come from `
      + "ScrapeX. Choosing one opens the table it feeds.");
  $("count-scrapex").textContent = mine.length || "";
}

/** One row of a two-column list, optionally a button. */
function pairRow(left, right, note, extra = "", onClick = null) {
  const row = document.createElement(onClick ? "button" : "div");
  if (onClick) { row.type = "button"; row.addEventListener("click", onClick); }
  row.className = `pair-row ${extra}`.trim();

  const a = document.createElement("span");
  a.className = "pair-key";
  a.textContent = left;
  const b = document.createElement("span");
  b.className = "pair-into";
  b.textContent = right;
  const c = document.createElement("span");
  c.className = "pair-note";
  c.textContent = note;

  row.append(a, b, c);
  return row;
}

// ---- every table, and one table across every sheet --------------------------

function renderTables(workbook) {
  const list = $("tables-list");
  list.textContent = "";
  const tables = workbook.sheets["1.TableDefinition"]?.rows || [];

  for (const row of tables) {
    const key = row.ENTITY_KEY;
    if (!key) continue;
    const active = readBoolean(row.IS_ACTIVE,
                               BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE);
    const fields = (workbook.sheets["2.SchemaRule"]?.rows || [])
      .filter((r) => (r.ENTITY_KEY || "").toLowerCase() === key.toLowerCase()).length;
    list.append(pairRow(key, row.DISPLAY_NAME || "—",
                        `${fields} field${fields === 1 ? "" : "s"}`
                        + (active ? "" : " · off"),
                        active ? "" : "pair-off",
                        () => showTable(key)));
  }
  $("count-tables").textContent = tables.length || "";
}

/** A titled block of rows inside the inspect screen. */
function block(title, rows, empty) {
  const card = document.createElement("section");
  card.className = "card";
  const heading = document.createElement("h2");
  heading.textContent = title;
  card.append(heading);

  if (!rows.length) {
    const none = document.createElement("p");
    none.className = "hint";
    none.textContent = empty;
    card.append(none);
    return card;
  }
  const holder = document.createElement("div");
  holder.className = "pair-rows";
  for (const row of rows) holder.append(row);
  card.append(holder);
  return card;
}

/**
 * ONE TABLE, EVERYWHERE IT APPEARS.
 *
 * The reason this screen exists: the six sheets are a database whose foreign
 * keys are strings, and answering "what is T_BITUMEN made of" by hand means
 * filtering five sheets by the same word and holding the answers in your head.
 */
function showTable(key) {
  const workbook = state.workbook;
  const same = (a) => (a || "").toLowerCase() === key.toLowerCase();
  const rows = (tab) => workbook.sheets[tab]?.rows || [];

  const definition = rows("1.TableDefinition").find((r) => same(r.ENTITY_KEY));
  const fields = rows("2.SchemaRule").filter((r) => same(r.ENTITY_KEY));
  const sources = rows(SOURCES).filter((r) => same(r.TARGET_ENTITY_KEY));
  const profiles = new Set(sources.map((r) => {
    const named = (r.PROFILE_KEY || "").trim();
    return (!named || named.toUpperCase() === "DEFAULT") ? key : named;
  }));
  const maps = rows("4.DataMap").filter((r) => profiles.has(r.PROFILE_KEY));
  const views = rows("5.ExportViews").filter((r) => same(r.ENTITY_KEY));

  $("inspect-name").textContent = key;
  $("inspect-lede").textContent = definition
    ? `${definition.DISPLAY_NAME || "no display name"} · `
      + `${definition.ENTITY_TYPE || "no type"} · `
      + `${definition.STORAGE_STRATEGY || "no storage strategy"}`
    : "This name is used elsewhere in the workbook and no table defines it.";

  const body = $("inspect-body");
  body.textContent = "";

  body.append(block("Fields", fields.map((r) => pairRow(
    r.ATTRIBUTE_KEY, r.DATA_TYPE || "TEXT",
    [r.SEMANTIC_ROLE, readBoolean(r.IS_PK, false) ? "key" : "",
     readBoolean(r.IS_MANDATORY, false) ? "required" : ""].filter(Boolean).join(" · "))),
    "No fields, so this table has no columns — the add-in refuses to sync it."));

  body.append(block("Sources", sources.map((r) => pairRow(
    r.SOURCE_KEY, r.PROFILE_KEY || "(the table's own key)",
    r.SOURCE_REGION || "")),
    "Nothing loads this table."));

  body.append(block("Mappings", maps.map((r) => pairRow(
    r.SOURCE_EXPRESSION || "(no expression)", `→ ${r.TARGET_ATTRIBUTE_KEY}`,
    [r.SOURCE_TYPE, r.TRANSFORM_CHAIN].filter(Boolean).join(" · "))),
    "No mapping tells the add-in how to read this table's source."));

  body.append(block("Export views", views.map((r) => pairRow(
    r.VIEW_KEY, r.LABEL || "—", r.COLUMNS ? `${r.COLUMNS.split(",").length} columns` : "")),
    "No export view offers this table."));

  // THE RIBBON, WHICH NEITHER OF THE ADD-IN'S OWN SURFACES SHOWS. Its Console
  // never reads 6.RibbonControls, and its Info tab's "RIBBON_CONFIG" section is
  // a different thing — the JSON bag on the definition, not these rows. So the
  // buttons a person actually presses are invisible in the tool built to
  // explain the configuration.
  //
  // ACTION_TAG carries the entity, sometimes with a region after a pipe
  // (`T_BITUMEN|EG`), which is why this matches on the part before it.
  const ribbon = rows("6.RibbonControls").filter((r) => {
    const tag = (r.ACTION_TAG || "").split("|")[0].trim();
    return same(tag);
  });
  body.append(block("Ribbon", ribbon.map((r) => pairRow(
    r.LABEL || r.ITEM_KEY, r.ACTION_TAG || "—",
    [r.ACTION_CLASS, r.REGION].filter(Boolean).join(" · "))),
    "No ribbon entry points at this table, so nothing in Excel opens it."));

  // ---- the two warnings the add-in's Info panel gets right --------------------
  const notes = [];
  const strategy = (definition?.STORAGE_STRATEGY || "").toLowerCase();
  if (strategy === "replaceall") {
    notes.push(["ReplaceAll", "Every sync DELETES all rows in this table before "
      + "writing. Nothing accumulates, and nothing survives a source that comes "
      + "back empty."]);
  }
  const keys = fields.filter((r) => readBoolean(r.IS_PK, false));
  if (strategy === "mergeupsert" && !keys.length) {
    notes.push(["MergeUpsert with no key", "There is no IS_PK column to match "
      + "on, so every sync APPENDS the same rows again. The table grows a "
      + "duplicate set each time."]);
  }
  if (keys.length > 1) {
    notes.push(["Composite key", `${keys.length} columns are marked IS_PK and the `
      + `add-in uses only the first (${keys[0].ATTRIBUTE_KEY}). Composite keys are `
      + "not supported."]);
  }
  if (notes.length) {
    const card = document.createElement("section");
    card.className = "card";
    const heading = document.createElement("h2");
    heading.textContent = "How this table is written";
    card.append(heading);
    for (const [title, detail] of notes) {
      const line = document.createElement("p");
      line.className = "hint err";
      const strong = document.createElement("b");
      strong.textContent = `${title}. `;
      line.append(strong, document.createTextNode(detail));
      card.append(line);
    }
    body.append(card);
  }

  showView("inspect");
}

// ---- the flow ---------------------------------------------------------------

async function show(fileId) {
  say("workbook-state", "Reading the workbook…");
  $("sheets-card").classList.add("hidden");
  $("editor-card").classList.add("hidden");

  let identity;
  try {
    identity = await tabsOf(fileId, state.token);
  } catch (error) {
    say("workbook-state",
        `That workbook could not be opened: ${error.message}`, "err");
    return;
  }

  state.name = identity.title;
  const verdict = identify(identity.tabs);
  $("workbook-identity").textContent = identity.title;

  if (!verdict.ok) {
    // REFUSED, and told exactly why. "Something is wrong" would send the owner
    // looking at the data; the tab ids are the thing that is wrong.
    const parts = [];
    if (verdict.absent.length) {
      parts.push(`it has no ${verdict.absent.join(", ")}`);
    }
    for (const {tab, found, wanted} of verdict.wrong) {
      parts.push(`${tab} is tab ${found} here and the add-in reads tab ${wanted}`);
    }
    say("workbook-state",
        "This is not the workbook the add-in reads — " + parts.join("; ")
        + ". Nothing is shown, because checking the wrong file and reporting it "
        + "correct is worse than saying nothing.", "err");
    $("workbook-choose").hidden = false;
    return;
  }

  let workbook;
  try {
    workbook = await readWorkbook(fileId, state.token);
  } catch (error) {
    say("workbook-state", `The sheets could not be read: ${error.message}`, "err");
    return;
  }

  await chrome.storage.local.set({[REMEMBERED]: {fileId, name: identity.title}});
  state.workbook = workbook;
  say("workbook-state",
      "This is the workbook the add-in reads — all six tabs match.", "ok");
  $("workbook-choose").hidden = false;
  $("workbook-recheck").hidden = false;

  const found = inspect(workbook);
  renderFindings(found);
  renderSources(workbook);
  renderScrapeX(workbook);
  renderTables(workbook);
  renderSheets(workbook);
  $("sheets-card").classList.remove("hidden");
  $("count-problems").textContent = found.length || "";
  $("rail-book").textContent = identity.title;
}

async function pick() {
  $("workbook-choose").disabled = true;
  say("workbook-state",
      "Choose the workbook in the tab that just opened, then come back here.");
  try {
    const picked = await chooseSpreadsheet({token: state.token, surface: "console"});
    if (!picked) {
      say("workbook-state", "Nothing was chosen.");
      return;
    }
    state.fileId = picked.fileId;
    await show(picked.fileId);
  } catch (error) {
    say("workbook-state", error.message || "The chooser could not be opened.", "err");
  } finally {
    $("workbook-choose").disabled = false;
  }
}

async function start() {
  const result = await getToken({interactive: false});
  if (result.state !== "ok" || !result.token) {
    say("workbook-state",
        "Sign in with Google from the ScrapeX panel first — this page reads a "
        + "spreadsheet with your account, and asks for nothing else.", "err");
    return;
  }
  state.token = result.token;

  const held = await chrome.storage.local.get(REMEMBERED);
  const remembered = held[REMEMBERED];
  $("workbook-choose").hidden = false;

  if (remembered?.fileId) {
    state.fileId = remembered.fileId;
    await show(remembered.fileId);
    return;
  }
  say("workbook-state",
      "Choose the workbook the Excel add-in reads. This page will refuse any "
      + "other file rather than check the wrong one.");
}

for (const button of document.querySelectorAll(".rail-link[data-view]")) {
  button.addEventListener("click", () => showView(button.dataset.view));
}
$("inspect-back").addEventListener("click", () => showView("tables"));
$("workbook-recheck").addEventListener("click", () => {
  if (state.fileId) show(state.fileId);
});
$("workbook-choose").addEventListener("click", () => pick());
$("source-add").addEventListener("click", () => edit({}));
$("editor-cancel").addEventListener("click", () => {
  state.editing = null;
  $("editor-card").classList.add("hidden");
});
$("editor-save").addEventListener("click", () => save());
// Judged on every keystroke and every choice, because a rule the owner meets
// only when he presses Save is a rule that arrives after the work.
for (const name of FIELDS) {
  const control = $(`f-${name}`);
  control.addEventListener("input", () => judge());
  control.addEventListener("change", () => judge());
}
// The key has a stated convention; offer it rather than making him retype it.
for (const name of ["TARGET_ENTITY_KEY", "PROFILE_KEY"]) {
  $(`f-${name}`).addEventListener("change", () => {
    const key = $("f-SOURCE_KEY");
    if (!key.value.trim()) {
      key.value = suggestedKey(readForm());
      judge();
    }
  });
}
$("workbook-recheck").addEventListener("click", () => {
  if (state.fileId) show(state.fileId);
});

start();
