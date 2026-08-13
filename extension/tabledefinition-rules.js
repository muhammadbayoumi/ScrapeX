// One row of 1.TableDefinition, judged exactly as the add-in judges it.
//
// SAME DISCIPLINE AS `datasource-rules.js`, and for the same reason: every rule
// below was read out of the C# with file:line
// (docs/reviews/mbiXaddin-config-contract-*.md). A rule invented here would be a
// Console refusing something the add-in accepts, and that teaches an owner to
// work around the Console rather than with it.
//
// THIS SHEET IS THE REGISTRY. A DataSource points at a table; a SchemaRule
// describes its columns; a DataMap fills them. If the row here is wrong or
// missing, none of that runs — so several of the rules below are about what
// OTHER sheets contain, and take them as arguments rather than guessing.

import { readBoolean, readConfigBag, BOOLEAN_DEFAULTS, ERROR_CODE, LOG_TAG,
  CONSOLE_ONLY_CODE,
  ENTITY_TYPES, STORAGE_STRATEGIES, STORAGE_STRATEGY_ALIASES, LICENSE_TIERS,
  VIEW_MODES, BUSINESS_DOMAINS, TABLE_UX_CONFIG_KEYS, TABLE_SYS_CONFIG_KEYS,
  RIBBON_CONFIG_KEYS, EXPORT_CONFIG_KEYS, DIRECTIONS, CONTROL_SIZES,
  BANNER_STYLES } from "./addin-contract.js";

/** The add-in's own cap on both key columns. SystemConstants ERR_LENGTH. */
const KEY_LIMIT = 100;

const finding = (severity, field, code, detail, fix = "") =>
  ({severity, field, code, detail, fix});

const text = (row, name) => String(row?.[name] ?? "").trim();

/**
 * The four JSON bags, and the closed lists inside two of them.
 *
 * A malformed bag is dropped WHOLE at runtime — not partially — so one stray
 * comma silently discards every setting in it. That is why a parse failure is
 * an Error here and not a warning.
 */
const BAGS = {
  UX_CONFIG: {keys: TABLE_UX_CONFIG_KEYS,
              closed: {Direction: DIRECTIONS}},
  SYS_CONFIG: {keys: TABLE_SYS_CONFIG_KEYS, closed: {}},
  RIBBON_CONFIG: {keys: RIBBON_CONFIG_KEYS,
                  closed: {ControlSize: CONTROL_SIZES}},
  EXPORT_CONFIG: {keys: EXPORT_CONFIG_KEYS,
                  closed: {HeaderStyle: BANNER_STYLES, FooterStyle: BANNER_STYLES}},
};

/** Case-insensitive throughout, because the add-in matches keys that way. */
const same = (a, b) => a.toUpperCase() === b.toUpperCase();

/**
 * Is this table's primary key defined anywhere on 2.SchemaRule?
 *
 * Exported because it is the hinge of the worst fault this sheet can carry, and
 * the guided workflow needs to ask the same question before it lets a table be
 * saved with MergeUpsert.
 */
export function hasPrimaryKey(entityKey, schemaRules) {
  return (schemaRules || []).some(
    (rule) => same(String(rule?.ENTITY_KEY ?? "").trim(), entityKey)
      && readBoolean(rule?.IS_PK, BOOLEAN_DEFAULTS["2.SchemaRule"].IS_PK));
}

function checkBag(row, name, found) {
  const raw = text(row, name);
  if (!raw) return;                          // blank is a default object, never a fault

  const {value: parsed, tolerated, unreadable} = readConfigBag(raw);
  if (unreadable) {
    found.push(finding("Error", name, ERROR_CODE.badJson,
      "Nothing here can be read as a settings object — not even allowing for "
      + "the add-in's own leniency. The whole bag is dropped at runtime, not "
      + "just the broken part, so EVERY setting in it stops applying.",
      "Check the brackets and quotes, or empty the cell."));
    return;
  }
  if (!parsed) return;
  if (tolerated) {
    found.push(finding("Info", name, ERROR_CODE.badJson,
      "Not strict JSON — a trailing comma or a comment. The add-in's parser "
      + "accepts it and always has, so nothing is broken; anything else reading "
      + "this cell would refuse it."));
  }

  const {keys, closed} = BAGS[name];
  for (const key of Object.keys(parsed)) {
    if (!keys.includes(key)) {
      found.push(finding("Warning", name, ERROR_CODE.unknownKey,
        `"${key}" is not a setting the add-in reads. It is kept and ignored.`,
        `Accepted here: ${keys.join(", ")}.`));
      continue;
    }
    const allowed = closed[key];
    const value = parsed[key];
    if (allowed && value !== null && value !== undefined
        && !allowed.includes(String(value))) {
      found.push(finding("Error", name, ERROR_CODE.badValue,
        `${key}="${value}" is not one of the values the add-in accepts.`,
        `Use one of: ${allowed.join(", ")}.`));
    }
  }
}

/**
 * One TableDefinition row, against the rest of the workbook.
 *
 * `others` is every OTHER row of this sheet — needed for the duplicate key and
 * for resolving PARENT_KEY, which is looked up among ACTIVE rows only.
 * `schemaRules` is all of 2.SchemaRule, needed for the MergeUpsert rule.
 */
export function checkTableDefinitionRow(row, others = [], schemaRules = []) {
  const found = [];
  const key = text(row, "ENTITY_KEY");

  // 1 — ENTITY_KEY. Critical, and the add-in stops here (yield break), so the
  // Console stops too rather than printing a cascade about a row nothing reads.
  if (!key) {
    return [finding("Critical", "ENTITY_KEY", ERROR_CODE.required,
      "There is no key, so this row defines no table. It is rejected whole, and "
      + "every source and column pointing at it is orphaned.")];
  }
  if (key.length > KEY_LIMIT) {
    found.push(finding("Error", "ENTITY_KEY", ERROR_CODE.tooLong,
      `${key.length} characters; the add-in refuses anything over ${KEY_LIMIT}.`));
  }
  if (others.some((other) => same(text(other, "ENTITY_KEY"), key))) {
    found.push(finding("Error", "ENTITY_KEY", LOG_TAG.duplicateEntity,
      `"${key}" is defined more than once. Only the FIRST row is used — the rest `
      + "are dropped, so edits made to the wrong one appear to do nothing.",
      "Rename one of them, or delete the row that is not wanted."));
  }

  // 2 — DISPLAY_NAME. A Fail, so the row survives — but the fallback everyone
  // assumes is there does not exist.
  if (!text(row, "DISPLAY_NAME")) {
    found.push(finding("Error", "DISPLAY_NAME", ERROR_CODE.required,
      "No name. It does NOT fall back to the key: `EffectiveLabel` reads "
      + "`RIBBON_CONFIG?.Label ?? DISPLAY_NAME ?? ENTITY_KEY`, and because "
      + "DISPLAY_NAME starts as an empty string rather than null, the last "
      + "branch can never run. The ribbon button renders with a BLANK label.",
      "Type the name that should appear in Excel."));
  }

  // 3 — the closed lists. A value outside one is not coerced; it is recorded and
  // the property keeps its declared default.
  for (const [field, vocabulary] of [["ENTITY_TYPE", ENTITY_TYPES],
                                     ["LICENSE_TIER", LICENSE_TIERS],
                                     ["VIEW_MODE", VIEW_MODES],
                                     ["BUSINESS_DOMAIN", BUSINESS_DOMAINS]]) {
    const value = text(row, field);
    if (value && !vocabulary.some((allowed) => same(allowed, value))) {
      found.push(finding("Error", field, ERROR_CODE.badValue,
        `"${value}" is not a value the add-in knows.`,
        `Accepted: ${vocabulary.join(", ")}.`));
    }
  }

  // 3b — a blank ENTITY_TYPE is inherited before it is judged. The add-in warns
  // only when it is still null AFTER MergeWithParent, so a child of a typed
  // parent is silent and a root with no type is not. Found by opening the real
  // T_BITUMEN, whose type is blank and whose parent is nothing.
  if (!text(row, "ENTITY_TYPE")) {
    const parentRow = others.find(
      (other) => same(text(other, "ENTITY_KEY"), text(row, "PARENT_KEY")));
    if (!text(parentRow || {}, "ENTITY_TYPE")) {
      found.push(finding("Warning", "ENTITY_TYPE", ERROR_CODE.required,
        "No kind, and nothing to inherit one from. The table still syncs, but "
        + "every rule that turns on the kind — a CONVERSION's three columns, a "
        + "COST table's price, a LIBRARY's menu — is skipped without comment."));
    }
  }

  // 4 — STORAGE_STRATEGY, and the fault that costs the most.
  const strategyText = text(row, "STORAGE_STRATEGY");
  const knownStrategy = STORAGE_STRATEGIES.find((s) => same(s, strategyText))
    || (STORAGE_STRATEGY_ALIASES.some((a) => same(a, strategyText))
      ? strategyText : "");
  if (strategyText && !knownStrategy) {
    found.push(finding("Error", "STORAGE_STRATEGY", ERROR_CODE.badValue,
      `"${strategyText}" is not a strategy. It is NOT coerced to the first enum `
      + "value — the parser records the error and leaves MergeUpsert in place, "
      + "which is deliberate: enum zero is ReplaceAll, and that would delete "
      + "everything.",
      `Accepted: ${STORAGE_STRATEGIES.join(", ")}.`));
  }

  // Blank means MergeUpsert, so the check below must treat blank as MergeUpsert
  // too — this is the case a reader is most likely to miss.
  const effective = knownStrategy && same(knownStrategy, "ReplaceAll") ? "ReplaceAll"
    : knownStrategy && same(knownStrategy, "Append") ? "Append"
      : "MergeUpsert";

  if (effective === "MergeUpsert" && !hasPrimaryKey(key, schemaRules)) {
    found.push(finding("Error", "STORAGE_STRATEGY",
      CONSOLE_ONLY_CODE.duplicatesForever,
      (strategyText ? "MergeUpsert" : "A blank strategy means MergeUpsert, and it")
      + ` needs a primary key. No column of "${key}" on 2.SchemaRule has IS_PK, `
      + "so no PRIMARY KEY is created, INSERT OR REPLACE has nothing to match "
      + "on, and EVERY SYNC APPENDS THE WHOLE FILE AGAIN. Nothing reports this: "
      + "the check that would have runs only when a PK column exists.",
      "Set IS_PK on the column that identifies a row, or use Append."));
  }
  if (effective === "ReplaceAll") {
    found.push(finding("Warning", "STORAGE_STRATEGY", ERROR_CODE.badValue,
      "Every sync DELETES every row of this table first, then loads the file. "
      + "Anything the source has dropped since last time is gone from Excel too."));
  }
  if (effective === "Append") {
    found.push(finding("Info", "STORAGE_STRATEGY", ERROR_CODE.badValue,
      "Rows are only added. A row already present is silently skipped, and a "
      + "row the source has corrected keeps its OLD value."));
  }

  // 5 — PARENT_KEY. Blank is the normal case for most rows and is never a fault.
  const parent = text(row, "PARENT_KEY");
  if (parent && same(parent, key)) {
    found.push(finding("Critical", "PARENT_KEY", ERROR_CODE.circular,
      "A table cannot inherit from itself. This is one of the few things the "
      + "add-in refuses outright."));
  } else if (parent) {
    const match = others.find((other) => same(text(other, "ENTITY_KEY"), parent));
    const parentIsLive = match
      && readBoolean(match.IS_ACTIVE, BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE);
    if (!match) {
      found.push(finding("Warning", "PARENT_KEY", ERROR_CODE.reference,
        `Nothing is named "${parent}". Inheritance is skipped and this becomes a `
        + "root table — silently, with only a line in the log."));
    } else if (!parentIsLive) {
      found.push(finding("Warning", "PARENT_KEY", ERROR_CODE.reference,
        `"${parent}" exists but is switched off, and the lookup is built from `
        + "ACTIVE rows only. So this behaves exactly as if the parent did not "
        + "exist at all — which is the harder version to spot.",
        "Switch the parent on, or clear this."));
    } else if (text(match, "PARENT_KEY")) {
      found.push(finding("Info", "PARENT_KEY", ERROR_CODE.reference,
        `"${parent}" has a parent of its own, and inheritance is applied ONCE. `
        + "Nothing from the grandparent reaches this table."));
    }
  }

  // 6 — the switches, and what each one actually turns off.
  if (!readBoolean(row?.IS_ACTIVE, BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE)) {
    const orphaned = others.filter((other) => same(text(other, "PARENT_KEY"), key));
    found.push(finding("Info", "IS_ACTIVE", ERROR_CODE.badFormat,
      "Switched off. The table is removed from the graph before anything is "
      + "built, so its sources never sync and it cannot be anyone's parent."));
    if (orphaned.length) {
      found.push(finding("Warning", "IS_ACTIVE", ERROR_CODE.reference,
        `${orphaned.map((o) => text(o, "ENTITY_KEY")).join(", ")} inherit from `
        + "this table, and a switched-off parent is invisible to the lookup. "
        + "They quietly became root tables.",
        "Switch this back on, or give them their own settings."));
    }
  } else if (!readBoolean(row?.IS_VISIBLE,
    BOOLEAN_DEFAULTS["1.TableDefinition"].IS_VISIBLE)) {
    found.push(finding("Info", "IS_VISIBLE", ERROR_CODE.badFormat,
      "Hidden from the ribbon menus only. It still syncs, and its data is still "
      + "written."));
  }

  // 7 — the four bags.
  for (const name of Object.keys(BAGS)) checkBag(row, name, found);

  return found;
}

/**
 * Does anything at all come out of this table?
 *
 * The counterpart of `stopsThisSource` on the other sheet, and split from
 * "switched off" for the same reason: a table that is empty on purpose must not
 * be reported next to one that is empty by accident.
 */
export function tableProducesNothing(found) {
  return found.some((f) => f.severity === "Critical");
}

/** Deliberately empty, rather than broken. */
export function tableSwitchedOff(row) {
  return !readBoolean(row?.IS_ACTIVE,
    BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE);
}
