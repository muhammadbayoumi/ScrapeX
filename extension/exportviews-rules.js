// One row of 5.ExportViews, judged exactly as the add-in judges it.
//
// EVERY RULE HERE IS THE ADD-IN'S. `ExportViewEntity.Validate()` is the whole
// of its own checking (ExportViewEntity.cs:304-345) and it is SHORT: two
// Criticals, one Warning, and two bag checks. Everything else this sheet can
// get wrong, the add-in does not check at all — it exports something wrong and
// says nothing. Those are marked CONSOLE_ONLY_CODE, never dressed in one of the
// add-in's codes, because a code an owner cannot find in the add-in's log sends
// them searching for a string that is not there (the lesson of PR 187 — and
// writing that as a hash and three digits is a colour literal to the guard in
// tests/test_vendor.py, which is why it is spelled out).
//
// THE FAILURE THIS SHEET IS WORST AT is a BLANK SHEET. If every name in COLUMNS
// misses, the intersection is empty, RenderInternal logs "No visible columns for
// current user tier" and RETURNS — after the worksheet was already created
// (ExportEngine.cs:112 creates, :258-262 returns). The owner gets a brand-new
// empty sheet named after the view and no dialog at all. The reading calls that
// "the single worst failure mode in this cluster for a Console to prevent".

import { readBoolean, BOOLEAN_DEFAULTS, ERROR_CODE, CONSOLE_ONLY_CODE,
  BANNER_STYLES, EXPORT_CONFIG_KEYS, readConfigBag }
  from "./addin-contract.js";

/** Severities in the order the add-in ranks them. */
const RANK = {Info: 0, Warning: 1, Error: 2, Critical: 3};

const finding = (severity, field, code, detail, fix = "") =>
  ({severity, field, code, detail, fix});

const text = (row, column) => String(row?.[column] ?? "").trim();

/**
 * COLUMNS as the add-in splits it — and ONLY as it splits it.
 *
 * `COLUMNS.Split(',').Select(c => c.Trim()).Where(c => !IsNullOrEmpty)`
 * (ExportViewEntity.cs:202-203). A semicolon, a newline and a pipe are NOT
 * separators here, which matters because VIEW_CONFIG.LinkedEntities one column
 * away DOES split on all of them. Guessing that the two agree is how a Console
 * starts describing a program the add-in is not.
 */
export function columnList(raw) {
  return String(raw ?? "").split(",").map((c) => c.trim()).filter(Boolean);
}

/**
 * The attribute keys this view's entity actually publishes to an export.
 *
 * The engine builds the visible list from SchemaRule and only THEN intersects
 * it with COLUMNS (ExportEngine.cs:1194-1202), so a name that is real but
 * IS_VIRTUAL or not IS_VISIBLE is dropped exactly like a typo is. Both have to
 * be modelled here or the Console would call a losing name a winning one.
 */
export function exportableAttributes(entityKey, schemaRules) {
  const wanted = String(entityKey ?? "").trim().toLowerCase();
  return (schemaRules || [])
    .filter((r) => text(r, "ENTITY_KEY").toLowerCase() === wanted)
    .filter((r) => !readBoolean(r.IS_VIRTUAL, BOOLEAN_DEFAULTS["2.SchemaRule"].IS_VIRTUAL))
    .filter((r) => readBoolean(r.IS_VISIBLE, BOOLEAN_DEFAULTS["2.SchemaRule"].IS_VISIBLE))
    .map((r) => text(r, "ATTRIBUTE_KEY"))
    .filter(Boolean);
}

/**
 * A raw SQLite fragment, read for the traps the engine cannot survive.
 *
 * THERE IS NO EXPRESSION LANGUAGE AND NO PARSER — WHERE_FILTER and SORT_BY are
 * concatenated verbatim into `SELECT * FROM [Entity] WHERE … ORDER BY … LIMIT
 * 100001` (ExportQuerySql.cs:41-48) and SQLite is the only validator. When it
 * refuses, the exception is swallowed TWICE (LocalDbManager.cs:138-141, then
 * ExportEngine.cs:1292-1296) and the render proceeds: headers, banner,
 * formatting, and ZERO rows. An owner cannot tell "my SQL is broken" from "no
 * rows match", which is why these are checked here at all.
 *
 * Only unambiguous traps are reported. This is NOT a SQL parser and must never
 * grow into one — a Console that guessed at valid SQLite would refuse working
 * filters, and the owner would learn to ignore it.
 */
function fragmentTraps(field, raw, {sortBy = false} = {}) {
  const value = String(raw ?? "");
  const found = [];
  if (!value.trim()) return found;

  if (value.includes(";")) {
    found.push(finding(
      "Warning", field, ERROR_CODE.badFormat,
      "Everything from the first \";\" is CUT before the query runs "
      + "(ExportQuerySql.CleanFragment), so the rest of this cell is silently "
      + "discarded — and on a Library menu the same text is used with no such "
      + "truncation at all, so one cell would behave two ways.",
      "Write a single expression with no semicolon."));
  }
  if (/"/.test(value)) {
    found.push(finding(
      "Warning", field, ERROR_CODE.badFormat,
      "Double quotes are IDENTIFIERS in SQLite, not strings — \"EG\" asks for a "
      + "column named EG. A missing column makes the whole query fail, and the "
      + "failure is swallowed into an empty sheet.",
      "Use single quotes for text: REGION = 'EG'."));
  }
  if (sortBy && /\bLIMIT\b/i.test(value)) {
    found.push(finding(
      "Error", field, ERROR_CODE.badFormat,
      "The engine appends its own LIMIT after this one (ExportEngine.cs:74, "
      + "MaxExportRows + 1), producing `LIMIT n LIMIT 100001` — a SQL error "
      + "that arrives as a sheet with headers and no rows.",
      "Remove LIMIT; the engine caps the export itself."));
  }
  if (sortBy && /^\s*ORDER\s+BY\b/i.test(value)) {
    found.push(finding(
      "Warning", field, ERROR_CODE.badFormat,
      "The engine writes ORDER BY itself and appends this cell after it, so a "
      + "leading ORDER BY here becomes `ORDER BY ORDER BY …`.",
      "Write only the sort body: NAME ASC, RATE DESC."));
  }
  if (!sortBy && /^\s*WHERE\b/i.test(value)) {
    found.push(finding(
      "Warning", field, ERROR_CODE.badFormat,
      "The engine writes WHERE itself and appends this cell after it, so a "
      + "leading WHERE here becomes `WHERE WHERE …`.",
      "Write only the condition: PRICE > 0."));
  }
  return found;
}

/**
 * One 5.ExportViews row.
 *
 * `others` is every OTHER row of the sheet — VIEW_KEY is a PRIMARY KEY on
 * `_SYS_EXPORT_VIEWS` (SqlBuilderService.cs:370) written with INSERT OR IGNORE
 * (LocalDbManager.WriteSession.cs:100), so a duplicate is discarded on persist
 * and NOTHING says so. It is global, not per entity, which is the half a reader
 * is likeliest to get wrong.
 */
export function checkExportViewRow(row, others = [], definitions = [],
                                   schemaRules = []) {
  const found = [];
  const viewKey = text(row, "VIEW_KEY");
  const entityKey = text(row, "ENTITY_KEY");

  // ---- the add-in's two Criticals, and they stop the row -------------------
  if (!viewKey) {
    return [finding("Critical", "VIEW_KEY", ERROR_CODE.required,
      "A view with no key is rejected whole (ExportViewEntity.cs:306-314) and "
      + "nothing it says below is ever read.",
      "Give it a key that is unique across this entire sheet.")];
  }
  if (!entityKey) {
    return [finding("Critical", "ENTITY_KEY", ERROR_CODE.required,
      "Without it the parent table cannot be determined and the row is "
      + "rejected whole (ExportViewEntity.cs:317-322).",
      "Name the ENTITY_KEY this view exports.")];
  }

  // ---- uniqueness, which the add-in does not report at all -----------------
  const clash = (others || []).some(
    (other) => text(other, "VIEW_KEY").toLowerCase() === viewKey.toLowerCase());
  if (clash) {
    found.push(finding("Error", "VIEW_KEY", CONSOLE_ONLY_CODE.silentOverride,
      `"${viewKey}" is used by another row. VIEW_KEY is the PRIMARY KEY of the `
      + "whole sheet — not per entity — and the sync writes with INSERT OR "
      + "IGNORE, so the second row is thrown away on persist with no warning "
      + "and no log line.",
      "Make every VIEW_KEY unique across all entities."));
  }

  // ---- the entity it names ------------------------------------------------
  const known = (definitions || []).map((d) => text(d, "ENTITY_KEY")).filter(Boolean);
  if (known.length) {
    const match = known.find(
      (key) => key.toLowerCase() === entityKey.toLowerCase());
    if (!match) {
      found.push(finding("Error", "ENTITY_KEY", CONSOLE_ONLY_CODE.orphanView,
        `No table is defined with the key "${entityKey}". The orphan pass that `
        + "warns about columns and sources does NOT cover views, so this one "
        + "simply never appears anywhere and nothing reports it missing.",
        "Point it at a key that exists on 1.TableDefinition."));
    } else if (match !== entityKey) {
      found.push(finding("Warning", "ENTITY_KEY", ERROR_CODE.reference,
        `The table is defined as "${match}" and this says "${entityKey}". The `
        + "lookup tolerates the difference; the two spellings in one workbook "
        + "do not tolerate a reader.",
        `Write it as "${match}".`));
    }
  }

  if (!text(row, "LABEL")) {
    found.push(finding("Warning", "LABEL", ERROR_CODE.required,
      "With no label the button carries the VIEW_KEY as its text "
      + "(ExportViewEntity.cs:285). That fallback genuinely works — this is "
      + "about what the owner reads on the ribbon.",
      "Give it the words you want on the button."));
  }

  // ---- COLUMNS: a filter, not an order, and the blank-sheet trap ----------
  const columnsRaw = String(row?.COLUMNS ?? "");
  const columns = columnList(columnsRaw);
  if (columnsRaw.trim() && columns.length === 0) {
    found.push(finding("Warning", "COLUMNS", ERROR_CODE.badFormat,
      "This cell has content but no name survives the split on commas "
      + "(ExportViewEntity.cs:331-336) — the add-in warns and exports every "
      + "column, which is what a BLANK cell means.",
      "List attribute keys separated by commas, or clear the cell."));
  }
  if (columns.length) {
    const exportable = exportableAttributes(entityKey, schemaRules);
    if (exportable.length) {
      const allowed = new Set(exportable.map((k) => k.toLowerCase()));
      const missing = columns.filter((c) => !allowed.has(c.toLowerCase()));
      if (missing.length === columns.length) {
        found.push(finding("Error", "COLUMNS", CONSOLE_ONLY_CODE.blankExport,
          `Not one of these names is an exportable column of ${entityKey}, so `
          + "the intersection is empty. The worksheet is created FIRST and the "
          + "render then returns on \"No visible columns for current user "
          + "tier\" — the owner gets a new, completely blank sheet named after "
          + "this view, with no error dialog.",
          "Every name must be an ATTRIBUTE_KEY of this entity that is neither "
          + "IS_VIRTUAL nor hidden."));
      } else if (missing.length) {
        found.push(finding("Warning", "COLUMNS", CONSOLE_ONLY_CODE.silentDrop,
          `${missing.join(", ")} — no such exportable column on ${entityKey}. `
          + "Unknown names are dropped by the intersection in silence: no "
          + "warning, no log line. A name that IS defined but is IS_VIRTUAL or "
          + "hidden disappears the same way.",
          "Remove them, or check IS_VIRTUAL and IS_VISIBLE on 2.SchemaRule."));
      }
    }
    if (columns.some((c) => /[;|\n]/.test(c))) {
      found.push(finding("Warning", "COLUMNS", ERROR_CODE.badFormat,
        "Only the COMMA separates names here. A semicolon or a pipe stays "
        + "inside the name and matches no column.",
        "Separate every name with a comma."));
    }
  }

  // ---- ALIASES: a JSON object, and its keys are case-SENSITIVE -------------
  const aliasesRaw = String(row?.ALIASES ?? "");
  if (aliasesRaw.trim()) {
    const bag = readConfigBag(aliasesRaw);
    const aliases = bag.value;
    if (bag.unreadable) {
      found.push(finding("Error", "ALIASES", ERROR_CODE.badJson,
        "This is not a readable JSON OBJECT. The parse fails safe to an EMPTY "
        + "map (JsonSafeParser.cs:106-110), so the export still runs and every "
        + "header silently keeps its DISPLAY_HEADER — a rename that never "
        + "happened and never complained. Note ALIASES is an object, not a "
        + "parallel list to COLUMNS; the two have no length relationship.",
        "Write an object: {\"RATE_2021\": \"Rate\", \"ITEM_NAME\": \"Item\"}"));
    } else if (aliases) {
      const exportable = exportableAttributes(entityKey, schemaRules);
      const exact = new Set(exportable);
      const lower = new Map(exportable.map((k) => [k.toLowerCase(), k]));
      for (const key of Object.keys(aliases)) {
        if (exact.has(key)) continue;
        const real = lower.get(key.toLowerCase());
        if (real) {
          found.push(finding("Error", "ALIASES", CONSOLE_ONLY_CODE.silentDrop,
            `"${key}" is never looked up: alias keys are matched CASE-`
            + `SENSITIVELY (a plain Dictionary with no comparer), unlike `
            + `COLUMNS one cell away. The column is "${real}".`,
            `Write the key as "${real}".`));
        } else if (exportable.length) {
          found.push(finding("Warning", "ALIASES", CONSOLE_ONLY_CODE.silentDrop,
            `"${key}" is not an exportable column of ${entityKey}, so this `
            + "rename is never applied and nothing says so.",
            "Remove it, or correct it to a real ATTRIBUTE_KEY."));
        }
        if (String(aliases[key] ?? "") === "") {
          found.push(finding("Info", "ALIASES", CONSOLE_ONLY_CODE.silentDrop,
            `"${key}" is mapped to an empty string, which the add-in reads as `
            + "NO alias (ExportViewEntity.cs:296) — the header falls back to "
            + "DISPLAY_HEADER rather than becoming blank.",
            "Give it the header you want, or drop the key."));
        }
      }
    }
  }

  found.push(...fragmentTraps("WHERE_FILTER", row?.WHERE_FILTER));
  found.push(...fragmentTraps("SORT_BY", row?.SORT_BY, {sortBy: true}));

  // ---- VIEW_CONFIG: the same bag as the entity's, and it OVERRIDES it ------
  const viewConfigRaw = String(row?.VIEW_CONFIG ?? "");
  if (viewConfigRaw.trim()) {
    const parsed = readConfigBag(viewConfigRaw);
    const bag = parsed.value;
    if (parsed.unreadable) {
      found.push(finding("Error", "VIEW_CONFIG", ERROR_CODE.badJson,
        "Unreadable JSON. The WHOLE bag is then ignored — not just the broken "
        + "key — so the banner, the footer and any linked entities all revert.",
        "Check the quotes and braces."));
    } else if (bag) {
      for (const key of Object.keys(bag)) {
        if (!EXPORT_CONFIG_KEYS.includes(key)) {
          found.push(finding("Warning", "VIEW_CONFIG", ERROR_CODE.unknownKey,
            `"${key}" is not read by anything. The five the code deserialises `
            + `are ${EXPORT_CONFIG_KEYS.join(", ")}.`,
            "Remove it, or correct the spelling."));
        }
      }
      for (const styleKey of ["HeaderStyle", "FooterStyle"]) {
        const style = bag[styleKey];
        if (style === undefined || style === null || style === "") continue;
        const match = BANNER_STYLES.find(
          (s) => s.toLowerCase() === String(style).toLowerCase());
        if (!match) {
          found.push(finding("Warning", "VIEW_CONFIG", ERROR_CODE.badValue,
            `${styleKey} "${style}" is not a banner style, so the default is `
            + `used. The five are ${BANNER_STYLES.join(", ")}.`,
            `Choose one of them.`));
        } else if (match !== String(style)) {
          found.push(finding("Info", "VIEW_CONFIG", ERROR_CODE.badValue,
            `${styleKey} is matched case-insensitively, so "${style}" works — `
            + `the add-in's own spelling is "${match}".`,
            `Write "${match}".`));
        }
      }
    }
  }

  return found.sort((a, b) => RANK[b.severity] - RANK[a.severity]);
}

/**
 * Does this view export a blank sheet? The one outcome worth its own question.
 *
 * Named separately because the Build screen asks it per view, and because the
 * answer is not "is there an Error" — a duplicate VIEW_KEY is an Error too and
 * produces no sheet at all rather than an empty one.
 */
export function exportsNothing(found) {
  return found.some((f) => f.code === CONSOLE_ONLY_CODE.blankExport);
}

/** IS_ACTIVE, with the add-in's own default for a blank or unreadable cell. */
export function viewSwitchedOff(row) {
  return readBoolean(row?.IS_ACTIVE,
                     BOOLEAN_DEFAULTS["5.ExportViews"].IS_ACTIVE) === false;
}
