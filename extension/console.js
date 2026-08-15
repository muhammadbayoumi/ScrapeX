// The Console — reads the add-in's configuration workbook, and says what is
// wrong with it before offering to change anything.
//
// THE ENGINE IS NOT INVOLVED. No fetch to 127.0.0.1, no import from anything
// that talks to it. The owner's ruling, restated 2026-08-12: «الكونسول يخص
// extension بنسبة 100%، المحرك غير مسؤول عنه اطلاقا».

import { getToken } from "./identity.js";
import { chooseSpreadsheet } from "./picker.js";
import { TAB_NAMES, parseWorkbook, inspect, vocabularies, SHEETS } from "./workbook.js";
import { KNOWN_VOCABULARIES, SHEET_GIDS, LICENSE_TIERS, ENTITY_TYPES,
         STORAGE_STRATEGIES, BUSINESS_DOMAINS, VIEW_MODES, DATA_TYPES,
         SEMANTIC_ROLES, SOURCE_TYPES, MATCH_MODES, readBoolean,
         BOOLEAN_DEFAULTS, ACTION_CLASSES, MENU_LAYOUTS, RIBBON_CONTROL_KEYS }
         from "./addin-contract.js";
import { checkDataSourceRow, stopsThisSource, switchedOff, suggestedKey }
  from "./datasource-rules.js";
import { checkTableDefinitionRow, tableProducesNothing }
  from "./tabledefinition-rules.js";
import { checkSchemaRuleRow, checkEntityRoles } from "./schemarule-rules.js";
import { checkDataMapRow, checkProfileCoverage, resolvedProfiles, attributesFor }
  from "./datamap-rules.js";
import { effectiveSourceType, headerMatch, mappingSentence, mappingGroups }
  from "./datamap-view.js";
import { checkExportViewRow, exportsNothing } from "./exportviews-rules.js";
import { checkRibbonControlRow, rendersNowhere, buildsAMenu,
  effectiveActionClass } from "./ribboncontrols-rules.js";

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

/**
 * The last two sheets, read by the same rules as the first four.
 *
 * They have no editor card yet, so this is the only surface that reports them —
 * and reporting is the half that matters first: a view whose COLUMNS all miss
 * produces a BLANK SHEET with no dialog, and a ribbon row with a blank
 * CONTROL_KEY renders nowhere at all. Both are invisible in Excel and both are
 * one glance here.
 */
const LATE_SHEETS = {
  "5.ExportViews": {
    editor: "exportView",
    check: (row, rows) => checkExportViewRow(
      row, rows("5.ExportViews").filter((r) => r !== row),
      rows("1.TableDefinition"), rows("2.SchemaRule")),
    broken: exportsNothing,
  },
  "6.RibbonControls": {
    editor: "ribbonControl",
    check: (row, rows) => checkRibbonControlRow(
      row, rows("6.RibbonControls").filter((r) => r !== row),
      rows("5.ExportViews"), rows("1.TableDefinition")),
    broken: rendersNowhere,
  },
};

/** How many rows of a late sheet are broken, and how many merely noted. */
function lateSheetVerdict(tab, workbook) {
  const spec = LATE_SHEETS[tab];
  const rows = (name) => workbook?.sheets?.[name]?.rows || [];
  if (!spec || !workbook.sheets[tab]) return null;

  let broken = 0;
  let noted = 0;
  for (const row of rows(tab)) {
    const found = spec.check(row, rows);
    if (!found.length) continue;
    // "Broken" is the outcome an owner can SEE going wrong, not the severity.
    // A blank export and a control that renders nowhere are both silent in
    // Excel, which is exactly why they are counted apart from the rest.
    if (found.some((f) => f.severity === "Critical") || spec.broken(found)) {
      broken += 1;
    } else {
      noted += 1;
    }
  }
  return {broken, noted};
}

/**
 * Open a row of one of the two late sheets, worst first.
 *
 * WORST FIRST IS THE WHOLE BEHAVIOUR. These two sheets have no list screen of
 * their own, so an owner who presses Open has said "show me this sheet" and not
 * "show me row 1". A view that exports a blank sheet and a ribbon item that
 * renders nowhere are both invisible in Excel; putting either in front of them
 * is the only moment they are ever seen.
 */
function pickLateRow(tab, workbook) {
  const spec = LATE_SHEETS[tab];
  const rows = (name) => workbook?.sheets?.[name]?.rows || [];
  const all = rows(tab);
  if (!spec || !all.length) return;

  const rank = (row) => {
    const found = spec.check(row, rows);
    if (found.some((f) => f.severity === "Critical") || spec.broken(found)) return 0;
    if (found.length) return 1;
    return 2;
  };
  const worst = all.reduce(
    (best, row) => (rank(row) < rank(best) ? row : best), all[0]);
  edit(EDITORS[spec.editor], worst);
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

    const verdict = lateSheetVerdict(tab, workbook);
    if (verdict && (verdict.broken || verdict.noted)) {
      const said = document.createElement("span");
      said.className = "sheet-verdict"
        + (verdict.broken ? " sheet-stopped" : " sheet-noted");
      said.textContent = verdict.broken
        ? `${verdict.broken} row${verdict.broken === 1 ? "" : "s"} produce nothing`
        : `${verdict.noted} note${verdict.noted === 1 ? "" : "s"}`;
      row.append(said);
    }

    // The two sheets with no screen of their own open their rows from here.
    // A DIV that listens for a click is not a control — this is a real button,
    // so it is reachable by keyboard and announced as one.
    if (LATE_SHEETS[tab] && sheet?.rows.length) {
      const open = document.createElement("button");
      open.type = "button";
      open.className = "button ghost sheet-open";
      open.textContent = "Open";
      open.setAttribute("aria-label", `Open ${tab}`);
      open.addEventListener("click", () => pickLateRow(tab, workbook));
      row.append(open);
    }

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

const VIEWS = ["overview", "scrapex", "tables", "inspect", "sources", "build",
               "problems"];

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
    item.addEventListener("click", () => edit(EDITORS.source, row));

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

// ---- one editor, three sheets -----------------------------------------------
//
// THE THREE FORMS SHARE EVERYTHING EXCEPT THEIR SPEC. Reading the controls,
// putting each finding under its own field, deciding whether Save is allowed,
// and writing one row's own span are the same problem on every sheet, and three
// copies of them would drift apart at the first correction — which is the exact
// failure this page exists to catch in the workbook.
//
// What differs is declared below and nothing else: which tab, which controls,
// where the drop-down values come from, and what makes a row so broken that
// saving it would be pointless.

const EDITORS = {
  source: {
    tab: SOURCES,
    card: "editor-card", prefix: "",
    fields: ["SOURCE_KEY", "TARGET_ENTITY_KEY", "PROFILE_KEY", "SOURCE_URI",
             "DISPLAY_LABEL", "SOURCE_REGION", "IS_ACTIVE", "MIN_LICENSE_REQ",
             "VERSION_TAG", "CONTEXT_PROPS"],
    booleans: ["IS_ACTIVE"],
    view: "sources",
    lists(workbook) {
      const known = vocabularies(workbook, KNOWN_VOCABULARIES);
      return {
        TARGET_ENTITY_KEY: {values: known.entityKeys, blank: "— choose a table —"},
        PROFILE_KEY: {values: [...new Set([...known.profileKeys, "DEFAULT"])].sort(),
          blank: "— blank: use the table's own key —"},
        SOURCE_REGION: {values: ["GLOBAL", ...known.regions], blank: "— none —"},
        MIN_LICENSE_REQ: {values: LICENSE_TIERS, blank: "— none —"},
      };
    },
    check: (row, workbook, editing) =>
      checkDataSourceRow(row, worldFor(workbook, editing)),
    refuse: (found) => stopsThisSource(found),
    refused: "As it stands this source produces nothing. Saving is refused.",
    where: (row) => row._row ? `${SOURCES}, row ${row._row}`
      : `${SOURCES}, a new row at the end`,
  },

  table: {
    tab: "1.TableDefinition",
    card: "td-editor-card", prefix: "td-",
    fields: ["ENTITY_KEY", "DISPLAY_NAME", "ENTITY_TYPE", "STORAGE_STRATEGY",
             "PARENT_KEY", "LICENSE_TIER", "BUSINESS_DOMAIN", "VIEW_MODE",
             "IS_ACTIVE", "IS_VISIBLE", "UX_CONFIG", "SYS_CONFIG",
             "RIBBON_CONFIG", "EXPORT_CONFIG"],
    booleans: ["IS_ACTIVE", "IS_VISIBLE"],
    view: "inspect",
    lists(workbook, row) {
      const others = rowsOf(workbook, "1.TableDefinition")
        .map((r) => r.ENTITY_KEY).filter(Boolean)
        // A table may not be its own parent, so it is not offered as one. The
        // rule still exists and still fires — this only keeps the list honest.
        .filter((k) => k.toUpperCase() !== (row.ENTITY_KEY || "").toUpperCase());
      return {
        ENTITY_TYPE: {values: ENTITY_TYPES, blank: "— none —"},
        STORAGE_STRATEGY: {values: STORAGE_STRATEGIES,
          blank: "— blank: MergeUpsert —"},
        PARENT_KEY: {values: others.sort(), blank: "— none: a root table —"},
        LICENSE_TIER: {values: LICENSE_TIERS, blank: "— blank: Free —"},
        BUSINESS_DOMAIN: {values: BUSINESS_DOMAINS, blank: "— none —"},
        VIEW_MODE: {values: VIEW_MODES, blank: "— blank: Table —"},
      };
    },
    check: (row, workbook, editing) => checkTableDefinitionRow(
      row,
      rowsOf(workbook, "1.TableDefinition").filter((r) => r !== editing),
      rowsOf(workbook, "2.SchemaRule")),
    refuse: (found) => tableProducesNothing(found),
    refused: "As it stands this row defines no table. Saving is refused.",
    where: (row) => row._row ? `1.TableDefinition, row ${row._row}`
      : "1.TableDefinition, a new row at the end",
  },

  column: {
    tab: "2.SchemaRule",
    card: "sr-editor-card", prefix: "sr-",
    // ENTITY_KEY IS NOT A CONTROL. Which table a column belongs to is settled by
    // the screen you opened it from, and a free field for it is how a column
    // ends up orphaned — the fault this sheet reports most often.
    fields: ["ATTRIBUTE_KEY", "DISPLAY_HEADER", "DATA_TYPE", "SEMANTIC_ROLE",
             "ORDINAL_POS", "LICENSE_TIER", "IS_PK", "IS_MANDATORY", "IS_VIRTUAL",
             "IS_DERIVED", "IS_VISIBLE", "UX_CONFIG", "LOGIC_CONFIG"],
    booleans: ["IS_PK", "IS_MANDATORY", "IS_VIRTUAL", "IS_DERIVED", "IS_VISIBLE"],
    view: "inspect",
    lists: () => ({
      DATA_TYPE: {values: DATA_TYPES, blank: "— blank: TEXT —"},
      SEMANTIC_ROLE: {values: SEMANTIC_ROLES, blank: "— none: an ordinary column —"},
      LICENSE_TIER: {values: LICENSE_TIERS, blank: "— blank: Free —"},
    }),
    check: (row, workbook, editing) => checkSchemaRuleRow(
      row,
      rowsOf(workbook, "2.SchemaRule").filter((r) => r !== editing),
      rowsOf(workbook, "1.TableDefinition")),
    refuse: (found) => found.some((f) => f.severity === "Critical"),
    refused: "As it stands this row defines no column. Saving is refused.",
    where: (row) => row._row ? `2.SchemaRule, row ${row._row}`
      : "2.SchemaRule, a new row at the end",
  },
  mapping: {
    tab: "4.DataMap",
    card: "dm-editor-card", prefix: "dm-",
    fields: ["PROFILE_KEY", "TARGET_ATTRIBUTE_KEY", "SOURCE_TYPE",
             "SOURCE_EXPRESSION", "MATCH_MODE", "TRANSFORM_CHAIN",
             "PROCESS_CONFIG"],
    booleans: [],
    view: "inspect",
    lists(workbook, row) {
      const sources = rowsOf(workbook, SOURCES);
      const profile = String(row.PROFILE_KEY ?? "").trim();
      return {
        // THE RESOLVED profiles, not the raw PROFILE_KEY column. A source with
        // a blank profile resolves to its table's key, so the raw column would
        // offer "DEFAULT" — which is a dead row on this sheet.
        PROFILE_KEY: {values: resolvedProfiles(sources), blank: "— choose —"},
        TARGET_ATTRIBUTE_KEY: {
          values: attributesFor(profile, sources, rowsOf(workbook, "2.SchemaRule")),
          blank: "— choose a column —"},
        SOURCE_TYPE: {values: SOURCE_TYPES, blank: "— blank: Header —"},
        MATCH_MODE: {values: MATCH_MODES, blank: "— blank: Exact —"},
      };
    },
    check: (row, workbook, editing) => checkDataMapRow(
      row,
      rowsOf(workbook, "4.DataMap").filter((r) => r !== editing),
      rowsOf(workbook, SOURCES),
      rowsOf(workbook, "2.SchemaRule")),
    refuse: (found) => found.some((f) => f.severity === "Critical"),
    refused: "As it stands this row maps nothing. Saving is refused.",
    where: (row) => row._row ? `4.DataMap, row ${row._row}`
      : "4.DataMap, a new row at the end",
  },

  exportView: {
    tab: "5.ExportViews",
    card: "ev-editor-card", prefix: "ev-",
    fields: ["VIEW_KEY", "ENTITY_KEY", "LABEL", "COLUMNS", "ALIASES",
             "WHERE_FILTER", "SORT_BY", "ICON", "SCREEN_TIP", "SUPER_TIP",
             "IS_ACTIVE", "VIEW_CONFIG"],
    booleans: ["IS_ACTIVE"],
    view: "inspect",
    lists(workbook) {
      return {
        ENTITY_KEY: {values: rowsOf(workbook, "1.TableDefinition")
          .map((r) => String(r.ENTITY_KEY ?? "").trim()).filter(Boolean).sort(),
        blank: "— choose a table —"},
      };
    },
    check: (row, workbook, editing) => checkExportViewRow(
      row,
      rowsOf(workbook, "5.ExportViews").filter((r) => r !== editing),
      rowsOf(workbook, "1.TableDefinition"),
      rowsOf(workbook, "2.SchemaRule")),
    // REFUSED ON THE BLANK SHEET, not only on a Critical. A view whose COLUMNS
    // all miss saves cleanly, syncs cleanly, and hands the owner an empty
    // worksheet with no dialog — the one outcome this card exists to stop.
    refuse: (found) => found.some((f) => f.severity === "Critical")
                    || exportsNothing(found),
    refused: "As it stands this view exports a blank sheet. Saving is refused.",
    where: (row) => row._row ? `5.ExportViews, row ${row._row}`
      : "5.ExportViews, a new row at the end",
  },

  ribbonControl: {
    tab: "6.RibbonControls",
    card: "rc-editor-card", prefix: "rc-",
    fields: ["ITEM_KEY", "CONTROL_KEY", "LABEL", "ACTION_CLASS", "ACTION_TAG",
             "PARENT_KEY", "ORDER", "REGION", "MENU_LAYOUT", "ICON",
             "SCREEN_TIP", "SUPER_TIP", "IS_ACTIVE"],
    booleans: ["IS_ACTIVE"],
    view: "inspect",
    lists(workbook, row) {
      const siblings = rowsOf(workbook, "6.RibbonControls")
        .filter((r) => r !== row && buildsAMenu(effectiveActionClass(r)))
        .map((r) => String(r.ITEM_KEY ?? "").trim()).filter(Boolean);
      return {
        // NOT a text box. A key that misses renders nowhere and reports
        // nothing, and the blank default is itself a control that does not
        // exist — so the only safe control is one that cannot be typed wrong.
        CONTROL_KEY: {values: [...RIBBON_CONTROL_KEYS],
          blank: "— blank: mnuDynamic, which renders nowhere —"},
        ACTION_CLASS: {values: [...ACTION_CLASSES], blank: "— blank: Export —"},
        MENU_LAYOUT: {values: [...MENU_LAYOUTS], blank: "— blank: Nested —"},
        // Only containers, because children of a leaf are never enumerated.
        PARENT_KEY: {values: [...new Set(siblings)].sort(),
          blank: "— none: a top-level item —"},
      };
    },
    check: (row, workbook, editing) => checkRibbonControlRow(
      row,
      rowsOf(workbook, "6.RibbonControls").filter((r) => r !== editing),
      rowsOf(workbook, "5.ExportViews"),
      rowsOf(workbook, "1.TableDefinition")),
    refuse: (found) => found.some((f) => f.severity === "Critical")
                    || rendersNowhere(found),
    refused: "As it stands this item renders nowhere. Saving is refused.",
    where: (row) => row._row ? `6.RibbonControls, row ${row._row}`
      : "6.RibbonControls, a new row at the end",
  },
};

const rowsOf = (workbook, tab) => workbook?.sheets?.[tab]?.rows || [];

/** The control ids a spec owns. Written out so a typo is a missing element. */
const control = (spec, name) => `${spec.prefix}f-${name}`;
const noteId = (spec, name) => `${spec.prefix}n-${name}`;

function readForm(spec) {
  const row = {};
  for (const name of spec.fields) {
    const node = $(control(spec, name));
    if (node) row[name] = node.value.trim();
  }
  // Carried rather than typed: the row's line on the sheet, and for a column the
  // table it belongs to.
  if (state.editing?.row?._row) row._row = state.editing.row._row;
  if (state.editing?.entity) row.ENTITY_KEY = state.editing.entity;
  return row;
}

/** Re-judge the form as it stands and put each finding beside its own field. */
function judge(spec) {
  const row = readForm(spec);
  const found = spec.check(row, state.workbook, state.editing?.row);

  for (const name of spec.fields) {
    const note = $(noteId(spec, name));
    if (!note) continue;
    const mine = found.filter((f) => f.field === name);
    note.textContent = mine
      .map((f) => f.fix ? `${f.detail} ${f.fix}` : f.detail).join(" ");
    note.className = "field-note"
      + (mine.some((f) => f.severity === "Critical" || f.severity === "Error")
         ? " note-error"
         : mine.length ? " note-warn" : "");
  }

  // A finding about a field this form has no control for still has to be seen —
  // ENTITY_KEY on a column, for one, which is decided by the screen. It goes to
  // the verdict line rather than nowhere.
  const homeless = found.filter((f) => !spec.fields.includes(f.field));
  const stops = spec.refuse(found);
  const blocking = found.filter(
    (f) => f.severity === "Critical" || f.severity === "Error");

  // SAVING IS REFUSED ONLY WHEN THE ROW WOULD PRODUCE NOTHING. A row the add-in
  // merely complains about is a row the add-in still runs, and a Console that
  // refused it would be stricter than the thing it configures — which teaches
  // an owner to edit the sheet directly and never come back.
  $(`${spec.prefix}editor-save`).disabled = stops;
  say(`${spec.prefix}editor-verdict`,
      stops
        ? spec.refused
        : homeless.length
          ? homeless.map((f) => f.detail).join(" ")
          : blocking.length
            ? `Saveable. The add-in will record ${blocking.length} `
              + `${blocking.length === 1 ? "complaint" : "complaints"} about it `
              + "and sync it anyway."
            // COUNTED, NOT IGNORED. This line said "Nothing to report" beside
            // two amber notes, because it counted only what blocks. A verdict
            // that disagrees with the fields above it teaches the owner to
            // trust neither.
            : found.length
              ? `Saveable. ${found.length} ${found.length === 1 ? "note" : "notes"} `
                + "above, none of which stops the add-in."
              : "Nothing to report.",
      stops ? "err" : blocking.length || homeless.length || found.length ? "" : "ok");
  return found;
}

/**
 * Open one form on one row.
 *
 * `entity` is passed for a column and settles its ENTITY_KEY without a control.
 */
function edit(spec, row, entity = "") {
  state.editing = {spec, row, entity};
  const lists = spec.lists(state.workbook, row);

  $(`${spec.prefix}editor-where`).textContent = spec.where(row);

  for (const name of spec.fields) {
    const node = $(control(spec, name));
    if (!node) continue;
    const value = row[name] ?? "";
    if (spec.booleans.includes(name)) {
      node.value = readBoolean(value, BOOLEAN_DEFAULTS[spec.tab][name])
        ? "TRUE" : "FALSE";
    } else if (lists[name]) {
      options(control(spec, name), lists[name].values, String(value),
              {blank: lists[name].blank});
    } else {
      node.value = value;
    }
  }

  // Only one form at a time, or two verdicts disagree on the same screen.
  for (const other of Object.values(EDITORS)) {
    $(other.card).classList.toggle("hidden", other !== spec);
  }
  showView(spec.view);
  judge(spec);
  $(spec.card).scrollIntoView({behavior: "smooth", block: "start"});
}

/** Write the row back, and only that row. */
async function save(spec) {
  const row = readForm(spec);
  const columns = SHEETS.find((s) => s.tab === spec.tab).columns;
  const values = [columns.map((name) => row[name] ?? "")];

  // A1 for the row's OWN span, so a save cannot touch a neighbour. A new row
  // goes to the first line after the last one read.
  const last = rowsOf(state.workbook, spec.tab).at(-1);
  const line = row._row || ((last?._row || 1) + 1);
  const end = String.fromCharCode("A".charCodeAt(0) + columns.length - 1);
  const range = `'${spec.tab}'!A${line}:${end}${line}`;

  $(`${spec.prefix}editor-save`).disabled = true;
  say(`${spec.prefix}editor-verdict`, "Saving…");
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
    say(`${spec.prefix}editor-verdict`, `Not saved: ${error.message}`, "err");
    $(`${spec.prefix}editor-save`).disabled = false;
    return;
  }

  // RE-READ RATHER THAN PATCH IN MEMORY. The sheet is the truth, another editor
  // may have moved something, and a Console showing its own optimistic copy is
  // the beginning of the drift this page exists to prevent.
  const returning = state.editing;
  $(spec.card).classList.add("hidden");
  state.editing = null;
  await show(state.fileId);
  // A column was opened from a table's screen, so put that screen back.
  if (returning?.entity) showTable(returning.entity);
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

// ---- the Mappings card --------------------------------------------------------
//
// ONE CARD PER PROFILE. `PROFILE_KEY` is lifted out of the rows into a strip
// above them because it is one value for the whole set — so a table fed by two
// sources on two different profiles gets two cards, rather than one strip
// standing over rows that do not all belong to it.
//
// THERE IS NO ARROW COLUMN. Column order carries the direction: what the file
// holds on the left, what the add-in stores on the right. The list this
// replaces centred an arrow between three columns, so source and target never
// lined up and the transform text sat detached from the row it described.

const MAP_COLUMNS = ["Source value", "Source type", "Header match",
                     "Target attribute", "Transform"];

/** A `<span>`, with a class when it needs one and a direction when it is data. */
function cell(className, content, {auto = false} = {}) {
  const node = document.createElement("span");
  if (className) node.className = className;
  node.textContent = content;
  // ENGLISH CHROME, ANY-LANGUAGE DATA. A heading read out of an Arabic sheet is
  // laid out by the browser rather than guessed at here, and `dir` goes on the
  // value alone — never on the words around it, which are ours and are English.
  if (auto) node.dir = "auto";
  return node;
}

/** The one value the whole card belongs to, and how many rows that is. */
function profileStrip(profile, count) {
  const strip = document.createElement("div");
  strip.className = "map-profile";

  const facts = document.createElement("span");
  facts.className = "map-profile-facts";
  facts.append(
    cell("map-profile-label", "PROFILE_KEY"),
    cell("map-profile-key", profile),
    cell("map-profile-note",
         "The set every row below belongs to — one value for the whole "
         + "profile."));

  // DERIVED FROM THE ROWS RENDERED, never a number written beside them: a count
  // that is typed goes stale the moment a mapping is added, and it goes stale
  // in silence.
  strip.append(facts,
               cell("chip map-count",
                    `${count} ${count === 1 ? "row" : "rows"}`));
  return strip;
}

/**
 * ONE ROW OPEN AT A TIME, within one card.
 *
 * Opening another closes the first, and pressing the open one closes it. A
 * `null` closes every row, which is what Escape does.
 */
function openMapping(card, wanted) {
  for (const button of card.querySelectorAll(".map-cells")) {
    const open = button === wanted
      && button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(open));
    button.nextElementSibling.hidden = !open;
  }
}

/**
 * THE ROW, RESTATED IN WORDS.
 *
 * Assembled from spans rather than formatted into one string, so the target
 * keeps its colour and the source its weight — the two halves of the mapping
 * stay distinguishable inside the sentence exactly as they are in the row.
 */
function mappingLine(said) {
  const line = document.createElement("p");
  line.className = "map-sentence";
  line.append(
    cell("map-said-target", said.target || "(no column)"),
    cell("", said.verb),
    cell("map-said-source", said.source || "(no expression)", {auto: true}));

  // Both clauses are appended or omitted, never printed empty. `matched —` and
  // `, then —` are sentences about nothing.
  if (said.match) {
    line.append(cell("", "matched"),
                cell("map-said-mode", said.match.toLowerCase()));
  }
  if (said.steps.length) {
    line.append(cell("map-then", ", then"));
    for (const step of said.steps) line.append(cell("map-step", step));
  }
  return line;
}

/** One mapping: five cells that open onto the sentence they mean. */
function mappingRow(card, row) {
  const kind = effectiveSourceType(row);
  const said = mappingSentence(row);
  const match = headerMatch(row);

  const holder = document.createElement("div");
  holder.className = "map-row" + (kind === "Header" ? "" : " map-derived");

  // A REAL BUTTON, not a div that listens. It is the only way this row is
  // reachable by Tab, operable with Enter and Space, and announced with the
  // state it is actually in — and `:focus-visible` then comes from the shared
  // sheet rather than being declared again here.
  const button = document.createElement("button");
  button.type = "button";
  button.className = "map-cells map-grid";
  button.setAttribute("aria-expanded", "false");
  button.append(
    cell("map-source", said.source || "(no expression)", {auto: true}),
    // The chip says what the SHEET holds and is coloured by what the add-in
    // will DO with it, so a misspelt type still reads as the Header it will be
    // treated as without the misspelling being hidden.
    cell(`chip map-kind${kind === "Header" ? " accent" : ""}`,
         String(row.SOURCE_TYPE ?? "").trim() || kind),
    cell("map-match" + (match ? "" : " map-inert"), match || "—"),
    cell("map-target", said.target || "(no column)"),
    cell("map-chain", String(row.TRANSFORM_CHAIN ?? "").trim() || "—"));

  const panel = document.createElement("div");
  panel.className = "map-said";
  panel.hidden = true;
  panel.append(mappingLine(said));

  button.addEventListener("click", () => openMapping(card, button));
  holder.append(button, panel);
  return holder;
}

/** One mapping profile, as a card. */
function mappingsCard(profile, rows) {
  const card = document.createElement("section");
  card.className = "card map-card";

  const heading = document.createElement("h2");
  heading.textContent = "Mappings";
  card.append(heading, profileStrip(profile, rows.length));

  const head = document.createElement("div");
  head.className = "map-head map-grid";
  for (const name of MAP_COLUMNS) head.append(cell("", name));
  card.append(head);

  for (const group of mappingGroups(rows)) {
    const holder = document.createElement("div");
    holder.className = "map-group";
    holder.append(cell("map-group-label", group.label));
    for (const row of group.rows) holder.append(mappingRow(card, row));
    card.append(holder);
  }

  const foot = document.createElement("p");
  foot.className = "map-foot";
  foot.textContent =
    "Header match only means something when the source type is Header — a "
    + "constant, an index or a formula has no name to look for.";
  card.append(foot);

  card.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = card.querySelector('.map-cells[aria-expanded="true"]');
    if (!open) return;
    openMapping(card, null);
    // Back to the row that was open, and not to the top of the document: a key
    // that closes something should not also lose the reader's place.
    open.focus();
  });

  // THE FIRST ROW IS OPEN. A table where every row is shut looks inert, and the
  // sentence under a row is the thing this card was redrawn to show.
  openMapping(card, card.querySelector(".map-cells"));
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
     readBoolean(r.IS_MANDATORY, false) ? "required" : ""].filter(Boolean).join(" · "),
    "", () => edit(EDITORS.column, r, key))),
    "No fields, so this table has no columns — the add-in refuses to sync it."));

  body.append(block("Sources", sources.map((r) => pairRow(
    r.SOURCE_KEY, r.PROFILE_KEY || "(the table's own key)",
    r.SOURCE_REGION || "")),
    "Nothing loads this table."));

  // ONE CARD PER PROFILE, because the strip above the rows carries the profile
  // and that is one value for the whole set. A table fed by two sources on two
  // profiles is a real shape here, and one card would have to either drop the
  // strip or put a key over rows that do not all carry it.
  if (!maps.length) {
    body.append(block("Mappings", [],
      "No mapping tells the add-in how to read this table's source."));
  } else {
    for (const profile of [...profiles].sort()) {
      const mine = maps.filter((r) => r.PROFILE_KEY === profile);
      if (mine.length) body.append(mappingsCard(profile, mine));
    }
  }

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

  // ---- what the add-in would make of this table ------------------------------
  //
  // READ FROM THE RULES, not written again here. These three notes existed
  // before `tabledefinition-rules.js` did, and one of them was already wrong —
  // it repeated the add-in's own claim that a composite key is unsupported,
  // which is true of three call sites and false of the database that builds a
  // real compound key. Two statements of one fact is how that happens.
  const about = definition
    ? checkTableDefinitionRow(
      definition,
      rows("1.TableDefinition").filter((r) => r !== definition),
      rows("2.SchemaRule"))
    : [];
  const roles = definition ? checkEntityRoles(key, fields, definition) : [];
  const notes = [...about, ...roles].filter((f) => f.severity !== "Info");

  if (notes.length) {
    const card = document.createElement("section");
    card.className = "card";
    const heading = document.createElement("h2");
    heading.textContent = "How this table is written";
    card.append(heading);
    for (const found of notes) {
      const line = document.createElement("p");
      line.className = found.severity === "Warning" ? "hint" : "hint err";
      const strong = document.createElement("b");
      strong.textContent = `${found.field}. `;
      line.append(strong, document.createTextNode(
        found.fix ? `${found.detail} ${found.fix}` : found.detail));
      card.append(line);
    }
    body.append(card);
  }

  showView("inspect");
}

// ---- the guided order --------------------------------------------------------
//
// FOUR SHEETS HAVE TO AGREE BEFORE ONE TABLE LOADS, and the order they must be
// filled in is written down nowhere in the add-in. A table with no columns is
// refused; a source whose profile has no mappings FAILS OUTRIGHT; a mandatory
// column with no mapping rejects the source before any write. So the order is
// not a preference — it is the dependency graph, and getting it wrong produces
// a table that looks configured and loads nothing.
//
// NOTHING HERE IS STORED. Each step asks the workbook whether it is done, so a
// table half-built by hand in Google Sheets is picked up exactly where it
// stands — and a wizard that believed it was on step three while the sheet said
// otherwise cannot happen, because there is no belief to be wrong.

function buildSteps(workbook, entity) {
  const definitions = rowsOf(workbook, "1.TableDefinition");
  const schema = rowsOf(workbook, "2.SchemaRule");
  const sources = rowsOf(workbook, SOURCES);
  const maps = rowsOf(workbook, "4.DataMap");
  const mine = (key) => (row) =>
    (row[key] || "").toLowerCase() === entity.toLowerCase();

  const definition = definitions.find(mine("ENTITY_KEY"));
  const columns = schema.filter(mine("ENTITY_KEY"));
  const feeds = sources.filter(mine("TARGET_ENTITY_KEY"));

  const steps = [];

  // 1 — the table itself.
  const tableFound = definition
    ? checkTableDefinitionRow(
      definition, definitions.filter((r) => r !== definition), schema)
    : [];
  steps.push({
    title: "The table",
    sheet: "1.TableDefinition",
    done: Boolean(definition) && !tableProducesNothing(tableFound),
    why: definition
      ? "Defined."
      : `Nothing on 1.TableDefinition is called ${entity}. Until there is, `
        + "every column and every source pointing at it is orphaned.",
    act: definition ? "Edit it" : "Define it",
    open: () => edit(EDITORS.table, definition || {ENTITY_KEY: entity}),
    notes: tableFound.filter((f) => f.severity !== "Info"),
  });

  // 2 — its columns, and the key that MergeUpsert cannot work without.
  const keys = columns.filter(
    (r) => readBoolean(r.IS_PK, BOOLEAN_DEFAULTS["2.SchemaRule"].IS_PK));
  const strategy = (definition?.STORAGE_STRATEGY || "").trim().toLowerCase();
  const needsKey = !strategy || strategy === "mergeupsert" || strategy === "upsert"
    || strategy === "merge";
  steps.push({
    title: "Its columns",
    sheet: "2.SchemaRule",
    done: columns.length > 0 && (!needsKey || keys.length > 0),
    why: !columns.length
      ? "No columns, so there is no table to create and nothing to write into."
      : needsKey && !keys.length
        ? `${columns.length} columns and no key. This table merges on every `
          + "sync, and with no key to match on it appends the whole file again "
          + "each time — silently, for ever."
        : keys.length
          ? `${columns.length} columns, ${keys.length} of them the key.`
          : `${columns.length} columns and no key — which is right here, because `
            + "this table replaces its rows rather than merging them.",
    act: columns.length ? "Add another column" : "Add the first column",
    open: () => edit(EDITORS.column, {ENTITY_KEY: entity}, entity),
    notes: [],
  });

  // 3 — where the rows come from.
  const liveFeeds = feeds.filter(
    (row) => !stopsThisSource(checkDataSourceRow(row, worldFor(workbook, row))));
  steps.push({
    title: "A source",
    sheet: SOURCES,
    done: liveFeeds.length > 0,
    why: !feeds.length
      ? "Nothing loads this table, so it will be created and stay empty."
      : liveFeeds.length
        ? `${liveFeeds.length} of ${feeds.length} can produce rows.`
        : `${feeds.length} attached, and none of them produces anything.`,
    act: feeds.length ? "Add another source" : "Add the source",
    open: () => edit(EDITORS.source, {TARGET_ENTITY_KEY: entity}),
    notes: [],
  });

  // 4 — the mappings, per profile, which is where the add-in stops rather than
  // warns. A profile with no mappings does not degrade — it fails.
  const profiles = resolvedProfiles(liveFeeds.length ? liveFeeds : feeds);
  const gaps = profiles.flatMap(
    (profile) => checkProfileCoverage(profile, maps, sources, schema)
      .map((f) => ({...f, profile})));
  steps.push({
    title: "The mappings",
    sheet: "4.DataMap",
    done: profiles.length > 0 && !gaps.length,
    why: !profiles.length
      ? "No profile to map yet — a source has to exist first."
      : gaps.length
        ? gaps.map((f) => `${f.profile}: ${f.detail}`).join(" ")
        : `${profiles.length} ${profiles.length === 1 ? "profile" : "profiles"}, `
          + "each mapping its key and every required column.",
    act: "Add a mapping",
    open: () => edit(EDITORS.mapping,
                     {PROFILE_KEY: profiles[0] || entity}, entity),
    notes: [],
  });

  return steps;
}

function renderBuild() {
  const holder = $("build-steps");
  holder.textContent = "";
  const entity = ($("build-new").value.trim() || $("build-entity").value || "").trim();
  if (!entity) {
    say("build-entity-note", "Choose a table, or type a new key above.");
    return;
  }
  say("build-entity-note", "");

  const steps = buildSteps(state.workbook, entity);
  let blocked = false;

  steps.forEach((step, index) => {
    const card = document.createElement("section");
    card.className = "card build-step" + (step.done ? " build-done" : "")
      + (blocked ? " build-blocked" : "");

    const heading = document.createElement("h2");
    heading.textContent = `${index + 1}. ${step.title}`;
    const sheet = document.createElement("span");
    sheet.className = "build-sheet";
    sheet.textContent = step.sheet;
    heading.append(sheet);
    card.append(heading);

    const why = document.createElement("p");
    why.className = "hint" + (step.done ? " ok" : blocked ? "" : " err");
    why.textContent = blocked
      ? `Waiting for step ${index}. ${steps[index - 1].title.toLowerCase()}.`
      : step.why;
    card.append(why);

    for (const note of step.notes) {
      const line = document.createElement("p");
      line.className = "hint";
      line.textContent = `${note.field}: ${note.detail}`;
      card.append(line);
    }

    const row = document.createElement("div");
    row.className = "row";
    const button = document.createElement("button");
    button.type = "button";
    button.className = step.done ? "button ghost" : "button";
    button.textContent = step.act;
    // THE REFUSAL, and the whole point of the screen. A step cannot be taken
    // before the one it depends on, because taking it out of order is how a
    // table ends up looking configured and loading nothing.
    button.disabled = blocked;
    button.addEventListener("click", step.open);
    row.append(button);
    card.append(row);

    holder.append(card);
    if (!step.done) blocked = true;
  });
}

function renderBuildPicker(workbook) {
  const keys = rowsOf(workbook, "1.TableDefinition")
    .map((r) => r.ENTITY_KEY).filter(Boolean).sort();
  options("build-entity", keys, $("build-entity").value || "",
          {blank: "— choose a table —"});
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
  renderBuildPicker(workbook);
  renderBuild();
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
$("source-add").addEventListener("click", () => edit(EDITORS.source, {}));

// The build screen re-derives on every change, because its answer is a question
// about the workbook and not a position it is holding.
$("build-entity").addEventListener("change", () => {
  $("build-new").value = "";
  renderBuild();
});
$("build-new").addEventListener("input", () => renderBuild());

// Both buttons on the inspect screen act on the table currently open, which is
// the one fact neither form asks for.
$("inspect-edit").addEventListener("click", () => {
  const key = $("inspect-name").textContent;
  const row = rowsOf(state.workbook, "1.TableDefinition")
    .find((r) => (r.ENTITY_KEY || "").toLowerCase() === key.toLowerCase());
  // A name used elsewhere in the workbook with no definition behind it is a real
  // state of this screen, and the answer to it is to write the definition.
  edit(EDITORS.table, row || {ENTITY_KEY: key});
});
$("column-add").addEventListener("click", () => {
  const key = $("inspect-name").textContent;
  edit(EDITORS.column, {ENTITY_KEY: key}, key);
});

// Wiring is per editor and identical for each, which is the point of the spec.
for (const spec of Object.values(EDITORS)) {
  $(`${spec.prefix}editor-cancel`).addEventListener("click", () => {
    state.editing = null;
    $(spec.card).classList.add("hidden");
  });
  $(`${spec.prefix}editor-save`).addEventListener("click", () => save(spec));
  // Judged on every keystroke and every choice, because a rule the owner meets
  // only when he presses Save is a rule that arrives after the work.
  for (const name of spec.fields) {
    const node = $(control(spec, name));
    if (!node) continue;
    node.addEventListener("input", () => judge(spec));
    node.addEventListener("change", () => judge(spec));
  }
}

// The source key has a stated convention; offer it rather than making him
// retype it. Only this sheet has one.
for (const name of ["TARGET_ENTITY_KEY", "PROFILE_KEY"]) {
  $(`f-${name}`).addEventListener("change", () => {
    const key = $("f-SOURCE_KEY");
    if (!key.value.trim()) {
      key.value = suggestedKey(readForm(EDITORS.source));
      judge(EDITORS.source);
    }
  });
}
$("workbook-recheck").addEventListener("click", () => {
  if (state.fileId) show(state.fileId);
});

start();
