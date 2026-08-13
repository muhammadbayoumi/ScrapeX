// How mbiXaddin BEHAVES — the half no generator can find.
//
// Its sibling `addin-vocabulary.js` is generated from
// contract/addin-contract.json and holds every enum: what values a column
// accepts. That is mechanical, and it is guarded mechanically — edit it by hand
// and a test fails.
//
// THIS FILE IS THE OTHER HALF, and it is hand-written on purpose. None of what
// follows is in an enum:
//
//   - a blank IS_ACTIVE means the row is LIVE, not disabled
//   - an unrecognised value means the same thing, and records nothing
//   - the same column name means the opposite one sheet away
//   - a mapping to a missing attribute is warned about and silently dropped;
//     a source with no mappings hard-fails and empties its table
//
// All of it came from seven agents reading ~350 .cs files with file:line for
// every answer (docs/reviews/mbiXaddin-config-contract-20260812.md). A
// generator reflecting over types would find none of it.
//
// SO IT IS PINNED TO A NUMBER INSTEAD. `READ_AGAINST_BEHAVIOUR_VERSION` below
// records which behaviour this reading describes. mbiXaddin raises its own
// `behaviourVersion` whenever error handling or a default changes, and the test
// that compares the two fails — deliberately — demanding a fresh reading before
// anything ships. Behaviour cannot be automated, so instead it is made
// impossible to change silently.

export * from "./addin-vocabulary.js";

import {
  BEHAVIOUR_VERSION, TRUE_SPELLINGS, FALSE_SPELLINGS, CLICKABLE_ACTIONS,
  MENU_ACTIONS, ENTITY_TYPES, STORAGE_STRATEGIES, LICENSE_TIERS, SEMANTIC_ROLES,
  DATA_TYPES, SOURCE_TYPES, MATCH_MODES, SHEETS as CONTRACT_SHEETS,
  URI_GOOGLE_SHEETS_MARKER,
} from "./addin-vocabulary.js";

/**
 * The behaviour version this file's reading was taken against.
 *
 * WHEN THIS DIFFERS FROM THE CONTRACT'S, THE READING IS STALE. Raising it here
 * without re-reading the add-in's code would defeat the only mechanism guarding
 * the half that cannot be generated — so the test that compares them says, in
 * its own words, what has to happen first.
 */
export const READ_AGAINST_BEHAVIOUR_VERSION = 1;

/** Both halves of ACTION_CLASS, which the add-in routes differently. */
export const ACTION_CLASSES = [...CLICKABLE_ACTIONS, ...MENU_ACTIONS];

/**
 * What the add-in makes of a cell, exactly as `SmartConverter.IsTrue` does.
 *
 * THE MOST DANGEROUS FIELD IN THE WORKBOOK, and it looks like the safest. For a
 * spelling it does not know the converter returns null; the TSV parser assigns
 * only when a conversion produced a value; so the property keeps its declared
 * C# default — which for IS_ACTIVE and IS_VISIBLE is `true`.
 *
 * `Active`, `X`, `TRUE!` and an EMPTY CELL therefore all mean the same thing:
 * the row is live, and nothing anywhere records that a value was not
 * understood. The failure is OPEN. A typo switches a table on.
 *
 * That is why the Console offers a closed list and flags everything else, and
 * why it must never present a blank as "off".
 */
export function readBoolean(cell, whenUnreadable) {
  const value = String(cell ?? "").trim().toLowerCase();
  if (TRUE_SPELLINGS.includes(value)) return true;
  if (FALSE_SPELLINGS.includes(value)) return false;
  return whenUnreadable;                       // blank AND unrecognised alike
}

/**
 * What the add-in makes of an ADDRESS — `SourceUriValidator`'s own test, and a
 * companion to `readBoolean` above in every sense: a quirk of the add-in
 * reproduced here so the Console can report it, with the literals read from the
 * contract rather than written into this line.
 *
 * IT IS A SUBSTRING OF THE WHOLE ADDRESS, and that is a defect. The host is
 * never parsed, so
 *
 *     https://attacker.example/?x=docs.google.com&output=tsv
 *
 * is "a Google Sheet" as far as the add-in is concerned. It then fetches it
 * over plain HTTP with NO AUTHENTICATION, following up to five redirects, and
 * parses whatever returns as the table's rows.
 *
 * THIS FUNCTION IS NOT A SECURITY CHECK AND MUST NEVER BE USED AS ONE. It
 * answers exactly one question — "what will the add-in conclude?" — so the
 * Console's advice about a TSV format and a gid lands in precisely the cases
 * the add-in's does. Whether an address IS Google's is decided by parsing the
 * host, in `checkSourceUri`, which is also where the impostor above is reported.
 *
 * The real repair belongs in the add-in's C#; until it lands, the Console is
 * the only surface that says this out loud.
 */
export function readsUriAsGoogleSheets(uri) {
  return String(uri ?? "").toLowerCase().includes(URI_GOOGLE_SHEETS_MARKER);
}

/**
 * The declared C# default behind every boolean column — what an unreadable cell
 * falls back to. Split by sheet because they disagree, and the disagreement is
 * the point: on TableDefinition and DataSource a blank means YES, on SchemaRule
 * it means NO. One shared default would be wrong on one of them.
 */
export const BOOLEAN_DEFAULTS = {
  "1.TableDefinition": {IS_ACTIVE: true, IS_VISIBLE: true},
  "2.SchemaRule": {IS_PK: false, IS_MANDATORY: false, IS_VIRTUAL: false,
                   IS_DERIVED: false, IS_VISIBLE: true},
  "3.DataSource": {IS_ACTIVE: true},
  "5.ExportViews": {IS_ACTIVE: true},
  "6.RibbonControls": {IS_ACTIVE: true},
};

/**
 * How the add-in reacts to each fault the Console can detect — read from its
 * code, and the reason the two problems already measured in the live workbook
 * are reported at different severities.
 */
export const CONSEQUENCES = {
  sourceWithNoMappings: {
    code: "ORPHAN_MAPPING",
    what: "IngestionResult.Fail — the source never ingests and its table is empty",
    severity: "broken",
  },
  mappingToMissingAttribute: {
    code: "ERR_REF",
    what: "warned, then silently dropped — \"its data will be lost\"",
    severity: "broken",
  },
  profileNothingReferences: {
    code: "ORPHAN_MAPPING",
    what: "the mappings simply never run",
    severity: "unused",
  },
};

/**
 * The add-in's own error codes. The Console uses THESE rather than inventing a
 * parallel vocabulary, so one fault has one name on both surfaces and an owner
 * searching for it finds both.
 */
export const ERROR_CODE = {
  reference: "ERR_REF",
  duplicate: "ERR_DUPLICATE",
  orphanMapping: "ORPHAN_MAPPING",
  missingKey: "PK_MISSING",
  mandatoryUnmapped: "MANDATORY_UNMAPPED",
  badJson: "INVALID_JSON",
  unknownKey: "UNKNOWN_KEY",
  // THE TWO ARE NOT INTERCHANGEABLE, and the Console had them the wrong way
  // round on every DataSource field. `DataSourceEntity.Validate()` and
  // `SourceUriValidator` emit only ERR_REQUIRED and ERR_FORMAT — never
  // INVALID_VALUE, which lives one layer down in `ConfigValidator` and is
  // reached only through a JSON config bag. A Console code the add-in does not
  // emit for that fault sends an owner searching the add-in's log for a string
  // that is not in it, which is the exact failure this map exists to prevent.
  badFormat: "ERR_FORMAT",          // DataSourceEntity.cs:355, SourceUriValidator.cs:59
  badValue: "INVALID_VALUE",        // ConfigValidator.cs:106,129 — bags only
  required: "ERR_REQUIRED",
  transform: "ERR_TRANSFORM",
  tooLong: "ERR_LENGTH",            // SystemConstants.cs:358 — the 100-char keys
  circular: "ERR_CIRCULAR",         // TableDefinitionEntity.cs:461 — PARENT_KEY = itself
};

/**
 * How the add-in reads a JSON config bag — which is NOT how `JSON.parse` does.
 *
 * FOUND BY RUNNING THE RULES AGAINST THE OWNER'S REAL WORKBOOK. Three cells came
 * back as errors and all three were fine: they end in a trailing comma, and
 * every bag in this product is parsed by Newtonsoft (`using Newtonsoft.Json` in
 * ConfigResolver.cs:36 and ConfigValidator.cs:22), which accepts one. A Console
 * that refused them would be refusing what the add-in reads every day, and the
 * owner would learn to ignore it.
 *
 * Returns `{value, tolerated, unreadable}`:
 *   value       the object, or null
 *   tolerated   true when strict JSON refused it and the relaxations below did
 *               not — worth saying, because it is not portable, but it works
 *   unreadable  true when nothing could read it; the add-in drops the bag WHOLE
 *
 * THE RELAXATIONS ARE NOT ALL OF NEWTONSOFT'S. It also accepts single-quoted
 * strings and unquoted property names, which are not handled here, so a bag
 * written that way is reported as unreadable when the add-in would read it. That
 * is a known and narrow gap; the two below are what hand-edited JSON actually
 * contains, and both appear in the live workbook.
 */
export function readConfigBag(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return {value: null, tolerated: false, unreadable: false};

  const object = (parsed) =>
    parsed !== null && typeof parsed === "object" && !Array.isArray(parsed);

  try {
    const parsed = JSON.parse(text);
    return {value: object(parsed) ? parsed : null, tolerated: false,
      unreadable: !object(parsed)};
  } catch { /* fall through to the relaxations */ }

  const relaxed = text
    .replace(/\/\*[\s\S]*?\*\//g, "")            // /* block comments */
    .replace(/(^|[^:"'\\])\/\/[^\n\r]*/g, "$1")  // // line comments, not in a URL
    .replace(/,(\s*[}\]])/g, "$1");              // one or more trailing commas
  try {
    const parsed = JSON.parse(relaxed);
    return {value: object(parsed) ? parsed : null, tolerated: true,
      unreadable: !object(parsed)};
  } catch {
    return {value: null, tolerated: false, unreadable: true};
  }
}

/**
 * Faults the add-in reports ONLY as a bracketed tag on a log line.
 *
 * There is no `ValidationResult` behind these, so there is no error code and no
 * severity — and that is exactly why they matter to the Console: nothing in the
 * add-in's own report will mention them. The tag is still the string an owner
 * would search its log for, so it is what gets printed.
 */
export const LOG_TAG = {
  duplicateEntity: "DUPLICATE",     // MetadataOrchestrator.cs:538
  orphanColumns: "ORPHAN_COLS",     // MetadataOrchestrator.cs:591
};

/**
 * Faults the Console reports that the add-in HAS NO RULE FOR.
 *
 * Kept apart from `ERROR_CODE` on purpose, and enforced apart by a test: every
 * code above must appear in the add-in's vocabulary, and every code here must
 * appear in none of it. Borrowing one of the add-in's names for a finding it
 * never makes would claim a parity that does not exist — and the owner would
 * search its log for a code it cannot produce.
 */
export const CONSOLE_ONLY_CODE = {
  notApplied: "NOT_APPLIED",        // accepted, documented, and then ignored
  // A duplicate (ENTITY_KEY, ATTRIBUTE_KEY) on 2.SchemaRule. The add-in resolves
  // it by dictionary assignment — LAST WINS — and says NOTHING: no log line, no
  // ValidationResult, unlike the duplicate on 1.TableDefinition which at least
  // logs. So one of two column definitions is discarded in silence, and the
  // Console is the only place it can be seen. MetadataOrchestrator.cs:679-703.
  silentOverride: "SILENT_OVERRIDE",
  // MergeUpsert on a table with no IS_PK column anywhere. No PRIMARY KEY is
  // emitted, so INSERT OR REPLACE has nothing to conflict on and every sync
  // appends the whole file again. Nothing checks it, because the fatal check
  // that would have runs only `if (pkCol != null)`. DataIngestionService.cs:1484.
  duplicatesForever: "NO_CONFLICT_TARGET",
};

/** The six gids, flattened for the check that a chosen workbook is the right one. */
export const SHEET_GIDS = Object.fromEntries(
  Object.entries(CONTRACT_SHEETS).map(([tab, spec]) => [tab, spec.gid]));

/**
 * Shaped for `vocabularies(workbook, known)` so the Console's drop-downs come
 * from the add-in's code, and fall back to the workbook's own values only where
 * the code has nothing to say.
 */
export const KNOWN_VOCABULARIES = {
  entityTypes: ENTITY_TYPES,
  storageStrategies: STORAGE_STRATEGIES,
  licenseTiers: LICENSE_TIERS,
  semanticRoles: SEMANTIC_ROLES,
  dataTypes: DATA_TYPES,
  sourceTypes: SOURCE_TYPES,
  matchModes: MATCH_MODES,
};

/** Re-exported so a caller can pin its reading without importing both files. */
export { BEHAVIOUR_VERSION };
