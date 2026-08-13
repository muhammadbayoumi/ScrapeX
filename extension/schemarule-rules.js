// One row of 2.SchemaRule, judged exactly as the add-in judges it.
//
// THIS SHEET IS WHERE SILENCE IS WORST. Two rows with the same
// (ENTITY_KEY, ATTRIBUTE_KEY) are resolved by dictionary assignment — last one
// wins — and NOTHING is written anywhere: no log line, no ValidationResult, not
// even the `[DUPLICATE]` warning its sibling sheet gets. A column definition is
// discarded and no surface in the add-in will ever mention it. That is the
// single strongest argument for editing this sheet through the Console.
//
// Every rule below was read out of the C# with file:line
// (docs/reviews/mbiXaddin-config-contract-*.md).

import { readBoolean, BOOLEAN_DEFAULTS, ERROR_CODE, LOG_TAG, CONSOLE_ONLY_CODE,
  SEMANTIC_ROLES, REPEATABLE_ROLES, DATA_TYPES, LICENSE_TIERS, UX_CONFIG_KEYS,
  LOGIC_CONFIG_KEYS } from "./addin-contract.js";

const KEY_LIMIT = 100;

const finding = (severity, field, code, detail, fix = "") =>
  ({severity, field, code, detail, fix});

const text = (row, name) => String(row?.[name] ?? "").trim();
const same = (a, b) => a.toUpperCase() === b.toUpperCase();
const flag = (row, name) =>
  readBoolean(row?.[name], BOOLEAN_DEFAULTS["2.SchemaRule"][name]);

/**
 * Aliases the parser normalises BEFORE parsing DATA_TYPE, so the Console must
 * accept them too or it will refuse a spelling the add-in is happy with.
 * TsvParser.cs:186-198.
 */
const DATA_TYPE_ALIASES = {
  BOOLEAN: "BOOL", BIT: "BOOL",
  STRING: "TEXT", VARCHAR: "TEXT", NVARCHAR: "TEXT", CHAR: "TEXT",
  INTEGER: "INT",
  NUMBER: "DECIMAL", FLOAT: "DECIMAL", DOUBLE: "DECIMAL", NUMERIC: "DECIMAL",
};

/** The ten menu roles the add-in warns about when tagged more than once. */
const WARNED_SINGULAR_ROLES = [
  "MENU_KEY", "MENU_LABEL", "MENU_URL", "MENU_DRIVE_URL", "MENU_SCREENTIP",
  "MENU_SUPERTIP", "MENU_ICON", "MENU_ACTION", "MENU_FORMAT", "MENU_ORDER",
];

const BAGS = {
  UX_CONFIG: UX_CONFIG_KEYS,
  LOGIC_CONFIG: LOGIC_CONFIG_KEYS,
};

function checkBag(row, name, found) {
  const raw = text(row, name);
  if (!raw) return;
  let parsed = null;
  try {
    parsed = JSON.parse(raw);
  } catch {
    found.push(finding("Error", name, ERROR_CODE.badJson,
      "Not valid JSON, so the whole bag is dropped and every setting in it "
      + "stops applying."));
    return;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    found.push(finding("Error", name, ERROR_CODE.badJson,
      "Valid JSON, but not an object — nothing can be read out of it."));
    return;
  }
  for (const key of Object.keys(parsed)) {
    if (!BAGS[name].includes(key)) {
      found.push(finding("Warning", name, ERROR_CODE.unknownKey,
        `"${key}" is not a setting the add-in reads. It is kept and ignored.`,
        `Accepted here: ${BAGS[name].join(", ")}.`));
    }
  }
}

/**
 * One SchemaRule row, against the rest of the workbook.
 *
 * `others` is every OTHER row of 2.SchemaRule — the same convention as
 * `checkDataSourceRow`, so the caller excludes the row under edit and the
 * Console's `worldFor` helper does it in one place.
 *
 * It may be the whole sheet: the per-entity rules narrow it themselves rather
 * than trusting the caller to. That part is NOT convention but a correction —
 * CODE, NAME and UNIT repeat across nearly every table there is, and a caller
 * that filtered by nothing would be told its whole workbook was a mass of
 * clashes. A module about human error should not keep one in its own signature.
 *
 * `definitions` is all of 1.TableDefinition, needed to tell an orphan from a
 * good column.
 */
export function checkSchemaRuleRow(row, others = [], definitions = []) {
  const found = [];
  const entity = text(row, "ENTITY_KEY");
  const attribute = text(row, "ATTRIBUTE_KEY");
  const siblings = (others || []).filter(
    (other) => same(text(other, "ENTITY_KEY"), entity));

  // 1 and 2 — the two Critical fields. Either blank stops the add-in's own
  // validation (yield break), so the Console stops with it.
  if (!entity) {
    return [finding("Critical", "ENTITY_KEY", ERROR_CODE.required,
      "No table named, so this column belongs to nothing and the row is "
      + "rejected whole.")];
  }
  if (!attribute) {
    return [finding("Critical", "ATTRIBUTE_KEY", ERROR_CODE.required,
      "No column name. The row is rejected whole — it defines nothing.")];
  }
  if (attribute.length > KEY_LIMIT) {
    found.push(finding("Error", "ATTRIBUTE_KEY", ERROR_CODE.tooLong,
      `${attribute.length} characters; the add-in refuses anything over `
      + `${KEY_LIMIT}.`));
  }

  // 3 — THE SILENT ONE. Both keys together are the primary key of
  // _SYS_SCHEMA_RULES, and a repeat is resolved last-wins with no record.
  if (siblings.some((other) => same(text(other, "ATTRIBUTE_KEY"), attribute))) {
    found.push(finding("Error", "ATTRIBUTE_KEY", CONSOLE_ONLY_CODE.silentOverride,
      `"${attribute}" is defined more than once for ${entity}. The LAST row `
      + "wins and the others are discarded — with no log line and no warning "
      + "anywhere. Whichever definition you are looking at may not be the one "
      + "in use.",
      "Delete the duplicate, or rename one of them."));
  }

  // 4 — is there a table to belong to? Matched against ACTIVE definitions only.
  if (definitions.length) {
    const match = definitions.find((d) => same(text(d, "ENTITY_KEY"), entity));
    const live = match
      && readBoolean(match.IS_ACTIVE, BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE);
    if (!match) {
      found.push(finding("Error", "ENTITY_KEY", LOG_TAG.orphanColumns,
        `No table is called "${entity}", so this column is dropped from the `
        + "graph entirely.",
        "Fix the spelling, or define the table on 1.TableDefinition."));
    } else if (!live) {
      found.push(finding("Warning", "ENTITY_KEY", LOG_TAG.orphanColumns,
        `"${entity}" exists but is switched off, and the lookup is built from `
        + "ACTIVE tables only — so this column is dropped exactly as if the "
        + "table were missing."));
    }
  }

  // 5 — DISPLAY_HEADER. A Fail, but the export has a fallback chain, so the
  // consequence is cosmetic and the severity says so rather than the code.
  if (!text(row, "DISPLAY_HEADER")) {
    found.push(finding("Warning", "DISPLAY_HEADER", ERROR_CODE.required,
      "No header. The Excel column falls back to the attribute key, which is "
      + "readable but not what a reader expects to see."));
  }

  // 6 — the closed lists. A blank SEMANTIC_ROLE is NONE, which is a real member
  // meaning "no engine meaning", and must never be flagged.
  const role = text(row, "SEMANTIC_ROLE");
  if (role && !SEMANTIC_ROLES.some((allowed) => same(allowed, role))) {
    found.push(finding("Error", "SEMANTIC_ROLE", ERROR_CODE.badValue,
      `"${role}" is not a role the add-in knows.`,
      `Leave it empty for an ordinary column, or use one of: `
      + `${SEMANTIC_ROLES.join(", ")}.`));
  }

  const dataType = text(row, "DATA_TYPE");
  if (dataType) {
    const upper = dataType.toUpperCase();
    const resolved = DATA_TYPE_ALIASES[upper] || upper;
    if (!DATA_TYPES.includes(resolved)) {
      found.push(finding("Error", "DATA_TYPE", ERROR_CODE.badValue,
        `"${dataType}" is not a type. An unreadable value leaves the column as `
        + "TEXT, so numbers arrive in Excel as text and stop adding up.",
        `Accepted: ${DATA_TYPES.join(", ")}.`));
    } else if (resolved !== upper) {
      found.push(finding("Info", "DATA_TYPE", ERROR_CODE.badValue,
        `"${dataType}" is accepted and read as ${resolved}.`));
    }
  }

  const tier = text(row, "LICENSE_TIER");
  if (tier && !LICENSE_TIERS.some((allowed) => same(allowed, tier))) {
    found.push(finding("Error", "LICENSE_TIER", ERROR_CODE.badValue,
      `"${tier}" is not a tier.`, `Accepted: ${LICENSE_TIERS.join(", ")}.`));
  }

  // 7 — ORDINAL_POS. Blank is 0 and legitimate; a negative draws a warning and
  // is then used as 0 anyway.
  const ordinal = text(row, "ORDINAL_POS");
  if (ordinal && !/^-?\d+$/.test(ordinal)) {
    found.push(finding("Error", "ORDINAL_POS", ERROR_CODE.badValue,
      `"${ordinal}" is not a whole number, so the position falls back to 0 and `
      + "this column ties with every other blank one."));
  } else if (ordinal && Number(ordinal) < 0) {
    found.push(finding("Warning", "ORDINAL_POS", ERROR_CODE.badValue,
      "A negative position is not used — the add-in substitutes 0."));
  }

  // 8 — the flags, and the three combinations the add-in refuses.
  const isPk = flag(row, "IS_PK");
  if (isPk && flag(row, "IS_VIRTUAL")) {
    found.push(finding("Error", "IS_PK", ERROR_CODE.badValue,
      "A primary key cannot be virtual: a virtual column is never stored, so "
      + "there is nothing for the key to be."));
  }
  if (isPk && flag(row, "IS_DERIVED")) {
    found.push(finding("Error", "IS_PK", ERROR_CODE.badValue,
      "A primary key cannot be derived — it must come from the source, not "
      + "from a formula."));
  }
  if (isPk && !flag(row, "IS_MANDATORY")) {
    found.push(finding("Warning", "IS_PK", ERROR_CODE.badValue,
      "A key that is allowed to be empty breaks MergeUpsert: a null key matches "
      + "nothing, so those rows duplicate on every sync.",
      "Switch IS_MANDATORY on as well."));
  }

  // 9 — one key per table. The DDL supports a composite key and the rest of the
  // add-in does not, which is a split worth stating precisely.
  if (isPk && siblings.some((other) => flag(other, "IS_PK"))) {
    found.push(finding("Warning", "IS_PK", ERROR_CODE.badValue,
      "More than one column of this table is a key. SQLite gets a genuine "
      + "compound key and de-duplicates correctly — but the pre-flight check, "
      + "the row lookup and the library menu all read only the FIRST key column "
      + "in ordinal order, and the add-in's own warning says composite keys are "
      + "unsupported, which is true of those three and false of the database.",
      "Use one key column unless you know only SQLite will enforce the rest."));
  }

  // 10 — repeated roles. Three roles are repeatable by design; of the rest,
  // ten warn and the engine roles do not warn at all.
  if (role && !REPEATABLE_ROLES.some((r) => same(r, role))
      && siblings.some((other) => same(text(other, "SEMANTIC_ROLE"), role))) {
    const upper = role.toUpperCase();
    const quiet = !WARNED_SINGULAR_ROLES.includes(upper);
    found.push(finding("Warning", "SEMANTIC_ROLE",
      quiet ? CONSOLE_ONLY_CODE.silentOverride : ERROR_CODE.duplicate,
      `${role} is used by more than one column of ${entity}. Only the first in `
      + "ordinal order is read and the rest are ignored"
      + (quiet
        ? " — and for this role the add-in says NOTHING about it at all."
        : ", with a warning in the log."),
      `Repeatable roles are ${REPEATABLE_ROLES.join(", ")}; every other role `
      + "belongs to one column."));
  }

  // 11 — the two bags.
  for (const name of Object.keys(BAGS)) checkBag(row, name, found);

  return found;
}

/**
 * Roles a whole entity is REQUIRED to carry, given what kind of table it is.
 *
 * Kept apart from the row rules because none of it can be judged one row at a
 * time — and because the guided workflow asks this question at a different
 * moment: after the columns are defined, before a source is attached.
 */
export function checkEntityRoles(entityKey, rows, definition) {
  const found = [];
  const roles = rows.map((r) => text(r, "SEMANTIC_ROLE").toUpperCase());
  const type = text(definition, "ENTITY_TYPE").toUpperCase();
  const missing = (name) => !roles.includes(name);

  if (type === "CONVERSION") {
    for (const needed of ["CONV_SOURCE", "CONV_TARGET", "CONV_FACTOR"]) {
      if (missing(needed)) {
        found.push(finding("Error", "SEMANTIC_ROLE", ERROR_CODE.mandatoryUnmapped,
          `A CONVERSION table needs a ${needed} column and ${entityKey} has none. `
          + "Conversion cannot run.",
          `Tag the column that holds it with ${needed}.`));
      }
    }
  }
  if (type === "COST" && missing("PRICE")) {
    found.push(finding("Warning", "SEMANTIC_ROLE", ERROR_CODE.mandatoryUnmapped,
      `${entityKey} is a COST table with no PRICE column, so nothing that reads `
      + "a price will find one here."));
  }
  if (type === "LIBRARY") {
    if (missing("MENU_KEY") && !rows.some((r) => flag(r, "IS_PK"))) {
      found.push(finding("Error", "SEMANTIC_ROLE", ERROR_CODE.mandatoryUnmapped,
        "A LIBRARY table needs either a MENU_KEY column or a primary key. "
        + "Without one its menu cannot identify a row."));
    }
    if (missing("MENU_URL") && missing("MENU_DRIVE_URL")) {
      found.push(finding("Warning", "SEMANTIC_ROLE", ERROR_CODE.mandatoryUnmapped,
        "No MENU_URL and no MENU_DRIVE_URL, so nothing in this library can be "
        + "downloaded."));
    }
    if (roles.includes("MENU_URL") && roles.includes("MENU_DRIVE_URL")) {
      found.push(finding("Info", "SEMANTIC_ROLE", ERROR_CODE.duplicate,
        "Both MENU_URL and MENU_DRIVE_URL are tagged. MENU_URL wins and the "
        + "Drive column is never converted."));
    }
    if (missing("MENU_LABEL")) {
      found.push(finding("Warning", "SEMANTIC_ROLE", ERROR_CODE.mandatoryUnmapped,
        "No MENU_LABEL, so entries are named by their file name and then by "
        + "their key."));
    }
  }

  // Independent of the table's type: an export tree with nothing to group by
  // renders as "No documents available" rather than as an error.
  if (roles.includes("EXPORT_GROUP") === false
      && rows.some((r) => text(r, "SEMANTIC_ROLE").toUpperCase()
        .startsWith("MENU_")) && type === "LIBRARY") {
    found.push(finding("Info", "SEMANTIC_ROLE", ERROR_CODE.mandatoryUnmapped,
      "No EXPORT_GROUP column. An export-tree menu built from this table shows "
      + "\"No documents available\" instead of saying what is wrong."));
  }

  return found;
}
