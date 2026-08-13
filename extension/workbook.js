// The mbiXaddin configuration workbook, read and checked.
//
// WHAT THIS FILE IS. Six Google Sheets tabs describe an Excel add-in entirely:
// which tables exist, what fields each has, where its data comes from, how a
// source column becomes a field, which views the ribbon offers, and what the
// ribbon looks like. Editing them by hand in Google Sheets is editing a
// database through a text box — every reference is a string nobody checks, and
// a mistake surfaces as a table that fails to load in front of whoever is using
// Excel that morning.
//
// WHAT IT IS NOT. It knows nothing about Chrome, the network, or the DOM. That
// is deliberate and it is the whole reason the rules here can be driven with
// hostile input in `node --test` rather than clicked at.
//
// THE ENGINE IS NOT INVOLVED IN ANY OF THIS — the owner's ruling, restated
// 2026-08-12: «الكونسول يخص extension بنسبة 100%، المحرك غير مسؤول عنه اطلاقا».
// No route, no Python, no 127.0.0.1 anywhere in the Console's path.

/**
 * The six tabs, in the order the workbook itself carries them, with the columns
 * observed in the live file on 2026-08-12.
 *
 * NAMED, NOT DISCOVERED. A tab renamed in Google Sheets must fail loudly here
 * rather than silently produce a workbook with one section missing — a Console
 * that quietly edits five of six sheets is worse than one that refuses.
 */
export const SHEETS = [
  {
    tab: "1.TableDefinition",
    key: "ENTITY_KEY",
    columns: ["ENTITY_KEY", "DISPLAY_NAME", "ENTITY_TYPE", "LICENSE_TIER",
              "IS_ACTIVE", "IS_VISIBLE", "STORAGE_STRATEGY", "PARENT_KEY",
              "VIEW_MODE", "BUSINESS_DOMAIN", "UX_CONFIG", "SYS_CONFIG",
              "RIBBON_CONFIG", "EXPORT_CONFIG"],
  },
  {
    tab: "2.SchemaRule",
    key: null,                      // composite: ENTITY_KEY + ATTRIBUTE_KEY
    columns: ["ENTITY_KEY", "ATTRIBUTE_KEY", "DISPLAY_HEADER", "ORDINAL_POS",
              "LICENSE_TIER", "SEMANTIC_ROLE", "DATA_TYPE", "IS_PK",
              "IS_MANDATORY", "IS_VIRTUAL", "IS_DERIVED", "IS_VISIBLE",
              "UX_CONFIG", "LOGIC_CONFIG"],
  },
  {
    tab: "3.DataSource",
    key: "SOURCE_KEY",
    columns: ["SOURCE_KEY", "TARGET_ENTITY_KEY", "PROFILE_KEY", "SOURCE_REGION",
              "SOURCE_URI", "VERSION_TAG", "DISPLAY_LABEL", "MIN_LICENSE_REQ",
              "IS_ACTIVE", "CONTEXT_PROPS", "Note", "Drive"],
  },
  {
    tab: "4.DataMap",
    key: null,                      // composite: PROFILE_KEY + TARGET_ATTRIBUTE_KEY
    columns: ["PROFILE_KEY", "TARGET_ATTRIBUTE_KEY", "SOURCE_TYPE", "MATCH_MODE",
              "SOURCE_EXPRESSION", "TRANSFORM_CHAIN", "PROCESS_CONFIG"],
  },
  {
    tab: "5.ExportViews",
    key: "VIEW_KEY",
    columns: ["VIEW_KEY", "ENTITY_KEY", "LABEL", "SCREEN_TIP", "SUPER_TIP",
              "ICON", "COLUMNS", "ALIASES", "WHERE_FILTER", "SORT_BY",
              "IS_ACTIVE", "VIEW_CONFIG"],
  },
  {
    tab: "6.RibbonControls",
    key: "ITEM_KEY",
    columns: ["ITEM_KEY", "CONTROL_KEY", "REGION", "PARENT_KEY", "ORDER",
              "ACTION_CLASS", "ACTION_TAG", "MENU_LAYOUT", "LABEL", "SCREEN_TIP",
              "SUPER_TIP", "ICON", "IS_ACTIVE", "Excel", "File", "Folder"],
  },
];

/** The tab names, for `spreadsheets.values.batchGet`'s ranges. */
export const TAB_NAMES = SHEETS.map((s) => s.tab);

/**
 * Turn Sheets' `values.batchGet` answer into rows keyed by column name.
 *
 * SHEETS TRUNCATES. A row whose trailing cells are empty comes back SHORT — a
 * fourteen-column sheet yields a three-element array when the rest is blank —
 * so every read must pad rather than index. Reading `row[11]` on such a row
 * gives `undefined`, which is not the same as "" and compares differently
 * against every rule below. The first version of this did index, and reported
 * every short row as missing its last column.
 *
 * Row numbers are 1-based and count the header, so they match what the owner
 * sees in Google Sheets when the Console names a row.
 */
export function parseWorkbook(valueRanges) {
  const byTab = new Map();
  for (const range of valueRanges || []) {
    const name = String(range.range || "").split("!")[0].replace(/^'|'$/g, "");
    byTab.set(name, range.values || []);
  }

  const sheets = {};
  const missing = [];
  for (const spec of SHEETS) {
    const grid = byTab.get(spec.tab);
    if (!grid) { missing.push(spec.tab); continue; }

    const header = (grid[0] || []).map((c) => String(c ?? "").trim());
    const rows = [];
    for (let i = 1; i < grid.length; i++) {
      const cells = grid[i] || [];
      if (!cells.some((c) => String(c ?? "").trim())) continue;   // wholly blank
      const row = {_row: i + 1};
      header.forEach((name, col) => {
        if (name) row[name] = String(cells[col] ?? "").trim();
      });
      rows.push(row);
    }
    sheets[spec.tab] = {header, rows};
  }
  return {sheets, missing};
}

/**
 * The drop-down lists, DERIVED FROM THE WORKBOOK ITSELF.
 *
 * Not a vocabulary typed into this file. A hard-coded list of entity keys would
 * be wrong the first time the owner adds a table, and wrong silently — the
 * Console would refuse a value the add-in accepts, which teaches the owner to
 * ignore it. Everything offered here is something the workbook already
 * contains, so the lists cannot drift from the file they describe.
 *
 * Where a field's vocabulary is a genuine enum in the add-in's C#, that list
 * belongs here too and must come from the code, not from the values in use —
 * a value nobody has used yet is still valid. Those arrive as `known`.
 */
export function vocabularies(workbook, known = {}) {
  const rows = (tab) => (workbook.sheets[tab]?.rows) || [];
  const distinct = (tab, column) => {
    const seen = new Set();
    for (const r of rows(tab)) {
      const v = (r[column] || "").trim();
      if (v) seen.add(v);
    }
    return [...seen].sort();
  };

  const attributesByEntity = {};
  for (const r of rows("2.SchemaRule")) {
    const e = r.ENTITY_KEY, a = r.ATTRIBUTE_KEY;
    if (!e || !a) continue;
    (attributesByEntity[e] ||= []).push(a);
  }
  for (const list of Object.values(attributesByEntity)) list.sort();

  return {
    entityKeys: distinct("1.TableDefinition", "ENTITY_KEY"),
    profileKeys: distinct("4.DataMap", "PROFILE_KEY"),
    sourceKeys: distinct("3.DataSource", "SOURCE_KEY"),
    viewKeys: distinct("5.ExportViews", "VIEW_KEY"),
    // Per entity, because offering every attribute in the workbook is offering
    // the wrong ones: a map targets an attribute OF ITS OWN ENTITY.
    attributesByEntity,
    entityTypes: known.entityTypes || distinct("1.TableDefinition", "ENTITY_TYPE"),
    storageStrategies: known.storageStrategies
      || distinct("1.TableDefinition", "STORAGE_STRATEGY"),
    licenseTiers: known.licenseTiers || distinct("1.TableDefinition", "LICENSE_TIER"),
    semanticRoles: known.semanticRoles || distinct("2.SchemaRule", "SEMANTIC_ROLE"),
    dataTypes: known.dataTypes || distinct("2.SchemaRule", "DATA_TYPE"),
    sourceTypes: known.sourceTypes || distinct("4.DataMap", "SOURCE_TYPE"),
    matchModes: known.matchModes || distinct("4.DataMap", "MATCH_MODE"),
    regions: distinct("3.DataSource", "SOURCE_REGION"),
    // Marks which lists are only "what is in use" rather than "what is legal".
    // A Console that presented the two identically would be claiming knowledge
    // it does not have.
    derivedFromUseAlone: Object.keys({
      entityTypes: 1, storageStrategies: 1, licenseTiers: 1, semanticRoles: 1,
      dataTypes: 1, sourceTypes: 1, matchModes: 1,
    }).filter((k) => !known[k]),
  };
}

/**
 * Everything wrong with the workbook that can be known without the add-in.
 *
 * SEVERITY IS HONEST ABOUT WHAT IS KNOWN. `broken` means a reference that
 * cannot resolve — a name pointing at nothing, which no reading of any code
 * makes fine. `unused` means something exists that nothing consumes; whether
 * that is a defect or merely tidy-up depends on what the add-in does at
 * runtime, and until that is read from the C# this file will not call it an
 * error. Overstating severity is how a checker gets ignored.
 */
export function inspect(workbook) {
  const rows = (tab) => (workbook.sheets[tab]?.rows) || [];
  const found = [];
  const say = (severity, tab, row, kind, detail) =>
    found.push({severity, tab, row, kind, detail});

  for (const tab of workbook.missing || []) {
    say("broken", tab, null, "tab missing",
        `The workbook has no tab named "${tab}". It was renamed, deleted, or `
        + "this is not the configuration workbook.");
  }

  const entities = new Set(rows("1.TableDefinition").map((r) => r.ENTITY_KEY).filter(Boolean));

  // ---- references that cannot resolve --------------------------------------
  for (const [tab, column] of [["3.DataSource", "TARGET_ENTITY_KEY"],
                               ["2.SchemaRule", "ENTITY_KEY"],
                               ["5.ExportViews", "ENTITY_KEY"]]) {
    for (const r of rows(tab)) {
      const v = r[column];
      if (v && !entities.has(v)) {
        say("broken", tab, r._row, "unknown entity",
            `${column} is "${v}", and 1.TableDefinition has no such ENTITY_KEY.`);
      }
    }
  }

  // A map's target attribute must exist in the schema OF THE ENTITY that map
  // feeds — which is reached through the source that names the profile.
  // A BLANK PROFILE IS NOT AN ABSENT ONE. The add-in resolves an empty
  // PROFILE_KEY — and the literal "DEFAULT", case-insensitively — to the row's
  // TARGET_ENTITY_KEY, then looks up DataMap under that name.
  //
  // The first version of this file did not know that and reported FIFTEEN
  // orphan profiles in the owner's workbook. Thirteen of them were mine: every
  // source that leaves PROFILE_KEY blank still names a profile, it just names
  // it by the entity. Two are real — GARB and GARB2. Reporting thirteen
  // problems that are not problems is how a checker teaches its owner to stop
  // reading it, which costs more than the two it would have found.
  const profileOf = (row) => {
    const named = (row.PROFILE_KEY || "").trim();
    return (!named || named.toUpperCase() === "DEFAULT")
      ? (row.TARGET_ENTITY_KEY || "")
      : named;
  };

  const entityOfProfile = new Map();
  for (const r of rows("3.DataSource")) {
    const profile = profileOf(r);
    if (profile && r.TARGET_ENTITY_KEY) entityOfProfile.set(profile, r.TARGET_ENTITY_KEY);
  }
  const attributes = new Map();
  for (const r of rows("2.SchemaRule")) {
    if (!r.ENTITY_KEY || !r.ATTRIBUTE_KEY) continue;
    if (!attributes.has(r.ENTITY_KEY)) attributes.set(r.ENTITY_KEY, new Set());
    attributes.get(r.ENTITY_KEY).add(r.ATTRIBUTE_KEY);
  }
  for (const r of rows("4.DataMap")) {
    const entity = entityOfProfile.get(r.PROFILE_KEY);
    if (!entity || !r.TARGET_ATTRIBUTE_KEY) continue;
    const known = attributes.get(entity);
    if (known && !known.has(r.TARGET_ATTRIBUTE_KEY)) {
      say("broken", "4.DataMap", r._row, "attribute not in schema",
          `Maps to "${r.TARGET_ATTRIBUTE_KEY}" for profile "${r.PROFILE_KEY}", `
          + `which feeds ${entity} — and 2.SchemaRule defines no such attribute `
          + "for it. The value has nowhere to land.");
    }
  }

  // ---- duplicate keys ------------------------------------------------------
  for (const spec of SHEETS) {
    if (!spec.key) continue;
    const seen = new Map();
    for (const r of rows(spec.tab)) {
      const v = r[spec.key];
      if (!v) continue;
      if (seen.has(v)) {
        say("broken", spec.tab, r._row, "duplicate key",
            `${spec.key} "${v}" is already used on row ${seen.get(v)}. Which of `
            + "the two wins is whatever the reader happens to do last.");
      } else {
        seen.set(v, r._row);
      }
    }
  }

  // ---- things nothing consumes --------------------------------------------
  // Through the SAME resolution the add-in uses, or a blank PROFILE_KEY looks
  // like a source that references nothing while the add-in reads it happily.
  const referenced = new Set(rows("3.DataSource").map(profileOf).filter(Boolean));
  const defined = new Map();
  for (const r of rows("4.DataMap")) {
    if (r.PROFILE_KEY) defined.set(r.PROFILE_KEY, (defined.get(r.PROFILE_KEY) || 0) + 1);
  }
  for (const [profile, n] of defined) {
    if (!referenced.has(profile)) {
      say("unused", "4.DataMap", null, "profile nothing references",
          `"${profile}" defines ${n} mapping${n === 1 ? "" : "s"} and no row in `
          + "3.DataSource names it. Those mappings never run.");
    }
  }
  for (const profile of referenced) {
    if (!defined.has(profile)) {
      say("broken", "3.DataSource", null, "profile has no mappings",
          `"${profile}" is named as a PROFILE_KEY and 4.DataMap defines no `
          + "mapping for it, so nothing tells the add-in how to read the source.");
    }
  }
  for (const entity of entities) {
    if (!rows("3.DataSource").some((r) => r.TARGET_ENTITY_KEY === entity)) {
      say("unused", "1.TableDefinition", null, "entity with no source",
          `"${entity}" is defined and no 3.DataSource row loads it.`);
    }
    if (!attributes.has(entity)) {
      say("unused", "1.TableDefinition", null, "entity with no fields",
          `"${entity}" has no 2.SchemaRule rows, so it has no columns.`);
    }
  }

  // ---- the address the add-in actually fetches -----------------------------
  for (const r of rows("3.DataSource")) {
    const uri = r.SOURCE_URI || "";
    if (!uri) {
      say("broken", "3.DataSource", r._row, "no address",
          `"${r.SOURCE_KEY}" has no SOURCE_URI, so there is nothing to load.`);
      continue;
    }
    // The live workbook uses Google's PUBLISHED form. It is not the same URL as
    // the spreadsheet's own: /d/e/2PACX-… is a publish token, and it serves
    // whatever the sheet currently holds — which is why writing rows through
    // the Sheets API is enough and nothing has to be re-published.
    if (uri.includes("/d/e/2PACX") && !uri.includes("output=")) {
      say("broken", "3.DataSource", r._row, "published address with no format",
          "A published Google Sheets URL needs output=tsv (or csv); without it "
          + "the add-in receives a web page rather than rows.");
    }
    if (/\/spreadsheets\/d\/(?!e\/)/.test(uri) && uri.includes("/edit")) {
      say("broken", "3.DataSource", r._row, "an edit link, not a data address",
          "This is the link from the browser's address bar. It serves HTML for a "
          + "person, not rows for a program. Use File → Share → Publish to web.");
    }
  }

  const order = {broken: 0, unused: 1};
  found.sort((a, b) => order[a.severity] - order[b.severity]
    || a.tab.localeCompare(b.tab) || (a.row || 0) - (b.row || 0));
  return found;
}
