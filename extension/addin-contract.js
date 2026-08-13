// What mbiXaddin's C# actually accepts.
//
// READ FROM THE CODE, NOT FROM THE DATA. Seven agents read ~350 .cs files on
// 2026-08-12 and returned 216 answers with file:line; the full record is
// docs/reviews/mbiXaddin-config-contract-20260812.md. This file is the part the
// Console needs at runtime.
//
// WHY THIS IS SEPARATE FROM workbook.js. A vocabulary derived from the values
// already in a sheet describes what someone has typed, not what the add-in will
// take: a legal value nobody has used yet would be missing, and the Console
// would refuse it. Every list below comes from an enum, a switch or a constant
// in the add-in — so the Console can offer a value the workbook has never seen
// and be right.
//
// IT IS ALSO THE PART THAT GOES STALE. The add-in is a separate repository on a
// separate release cycle. Each list carries the date it was read; when the
// add-in changes, this file is wrong until someone re-reads it, and that is
// better than pretending to derive it.

/** When this was read out of the add-in's source. */
export const CONTRACT_READ_ON = "2026-08-12";

// ---- 4.DataMap -------------------------------------------------------------

/** How a source column is located. */
export const SOURCE_TYPES = ["Header", "Index", "Context", "Constant", "Formula"];

/** How SOURCE_EXPRESSION is matched against the source. */
export const MATCH_MODES = ["Exact", "Contains", "StartsWith", "Regex", "Fuzzy"];

/**
 * SOURCE_TYPE=Context takes one of these and nothing else — the expression is a
 * name the add-in resolves itself, not a column.
 */
export const CONTEXT_EXPRESSIONS = ["SYNC_DATE", "SYNCTIMESTAMP", "SYNCTIME",
                                    "CURRENTTIER"];

/**
 * TRANSFORM_CHAIN is PIPE-separated and case-insensitive; `:` introduces an
 * argument (`SUBSTRING:0,3`). An unknown name is not a syntax error to the
 * add-in — it is dropped — which is exactly the class of silent loss the
 * Console exists to catch before it ships.
 */
export const TRANSFORMS = ["TRIM", "UPPER", "LOWER", "TO_DECIMAL", "TO_INT",
                           "TO_DATE", "TO_BOOL", "ABS", "SUBSTRING",
                           "JSON_EXTRACT"];
export const TRANSFORM_SEPARATOR = "|";

/** PROCESS_CONFIG is JSON; these are the only keys the add-in reads. */
export const PROCESS_CONFIG_KEYS = ["NullStrategy", "DefaultValue",
                                    "ErrorStrategy", "AutoTrim", "RowFilter"];
export const MAP_STRATEGIES = ["Skip", "UseDefault", "Fail"];
export const ROW_FILTER_OPERATORS = ["EQ", "NEQ", "GT", "LT", "GTE", "LTE",
                                     "CONTAINS", "NOT_CONTAINS", "NOT_EMPTY",
                                     "EMPTY", "IN", "NOT_IN"];

// ---- 2.SchemaRule ----------------------------------------------------------

export const SEMANTIC_ROLES = [
  "NONE", "PRICE", "QTY", "TOTAL", "UNIT", "NAME",
  "CONV_SOURCE", "CONV_TARGET", "CONV_FACTOR", "CONV_DATE_START", "CONV_DATE_END",
  "MENU_KEY", "MENU_LABEL", "MENU_SCREENTIP", "MENU_SUPERTIP", "MENU_ICON",
  "MENU_ACTION", "MENU_URL", "MENU_DRIVE_URL", "MENU_FORMAT", "MENU_ORDER",
  "MENU_GROUP", "EXPORT_GROUP", "MENU_FACET",
];

/** The three roles a single entity may carry more than once. */
export const REPEATABLE_ROLES = ["MENU_GROUP", "EXPORT_GROUP", "MENU_FACET"];

export const DATA_TYPES = ["TEXT", "DECIMAL", "INT", "BOOL", "DATE", "DATETIME",
                           "GUID", "JSON", "PERCENTAGE", "BLOB"];

/** UX_CONFIG and LOGIC_CONFIG are JSON; these are the keys that are read. */
export const UX_CONFIG_KEYS = ["Width", "Format", "Align", "HeaderColor",
                               "WrapText", "AutoFit"];
export const LOGIC_CONFIG_KEYS = ["Min", "Max", "Formula", "LookupRef",
                                  "DefaultVal", "ListSource", "ListItems",
                                  "ListStrict"];

// ---- 1.TableDefinition and 3.DataSource ------------------------------------

export const ENTITY_TYPES = ["COST", "PERF", "REF", "COMP", "CONVERSION",
                             "COST_ENG", "AUDIT", "ASSEMBLY", "LIBRARY",
                             "SYSTEM"];

/**
 * Seven spellings, and they are not seven strategies: the add-in accepts both a
 * PascalCase and an UPPERCASE family. Offering all seven would invite a workbook
 * where two rows mean the same thing and look different, so the Console offers
 * the three the live file already uses and accepts the rest silently.
 */
export const STORAGE_STRATEGIES = ["ReplaceAll", "MergeUpsert", "Append"];
export const STORAGE_STRATEGY_ALIASES = ["REPLACE", "UPSERT", "MERGE", "INSERT"];

/** In rank order — Free is the least, Admin the most. */
export const LICENSE_TIERS = ["Free", "Standard", "Premium", "Admin"];

export const VIEW_MODES = ["Table", "Card", "Chart"];

export const BUSINESS_DOMAINS = ["MATERIAL", "LABOR", "EQUIPMENT", "VENDOR",
                                 "PROJECT", "FINANCE", "SYSTEM", "GARB"];

/** CONTEXT_PROPS is JSON on 3.DataSource. */
export const CONTEXT_PROPS_KEYS = ["SourceType", "SyncFreq", "SkipRows",
                                   "Encoding", "Delimiter", "TimeoutSeconds",
                                   "ActionUrl"];
export const CONTEXT_SOURCE_TYPES = ["GoogleSheetTsv", "LocalCsv", "RestApi",
                                     "LocalSqlite", "Manual"];
export const SYNC_FREQUENCIES = ["Hourly", "Daily", "Weekly", "Monthly"];

// ---- 6.RibbonControls ------------------------------------------------------

export const MENU_LAYOUTS = ["Nested", "Grouped", "GroupedLarge", "Tiles",
                             "Flat", "FlatLarge", "NestedLarge"];

/** Four are routed by ActionRouter; four are read when a menu is built. */
export const CLICKABLE_ACTIONS = ["Download", "Stream", "Export", "UpdateTable"];
export const MENU_ACTIONS = ["Menu", "Library", "ExportTree", "ViewList"];
export const ACTION_CLASSES = [...CLICKABLE_ACTIONS, ...MENU_ACTIONS];

// ---- booleans, and the reason this file exists -----------------------------

/**
 * THE MOST DANGEROUS FIELD IN THE WORKBOOK, and it looks like the safest.
 *
 * `SmartConverter.IsTrue` accepts sixteen spellings across two languages. What
 * it does with a SEVENTEENTH is the problem: it returns null, the TSV parser
 * only assigns when a conversion produced a value, and the property therefore
 * keeps its declared C# default — which for IS_ACTIVE and IS_VISIBLE is TRUE.
 *
 * So `Active`, `X`, `TRUE!` and an EMPTY CELL all mean the same thing: the row
 * is live, and nothing anywhere records that a value was not understood. The
 * failure is OPEN. A typo here switches a table on.
 *
 * That is why the Console offers a closed list and flags everything else, and
 * why it must never present a blank as "off".
 */
export const TRUE_SPELLINGS = ["1", "true", "yes", "y", "on", "نعم", "صح", "صحيح"];
export const FALSE_SPELLINGS = ["0", "false", "no", "n", "off", "لا", "خطأ", "غلط"];

/** What the add-in makes of a cell, exactly as its parser does. */
export function readBoolean(cell, whenUnreadable) {
  const value = String(cell ?? "").trim().toLowerCase();
  if (TRUE_SPELLINGS.includes(value)) return true;
  if (FALSE_SPELLINGS.includes(value)) return false;
  return whenUnreadable;                       // blank AND unrecognised alike
}

/**
 * The declared C# default for every boolean column, which is what an
 * unreadable cell falls back to. Split by sheet because they disagree, and the
 * disagreement is the whole point: on TableDefinition and DataSource a blank
 * means YES, on SchemaRule it means NO.
 */
export const BOOLEAN_DEFAULTS = {
  "1.TableDefinition": {IS_ACTIVE: true, IS_VISIBLE: true},
  "2.SchemaRule": {IS_PK: false, IS_MANDATORY: false, IS_VIRTUAL: false,
                   IS_DERIVED: false, IS_VISIBLE: true},
  "3.DataSource": {IS_ACTIVE: true},
  "5.ExportViews": {IS_ACTIVE: true},
  "6.RibbonControls": {IS_ACTIVE: true},
};

// ---- how the add-in itself names a fault -----------------------------------

/**
 * Its own error codes. The Console uses THESE rather than inventing a parallel
 * vocabulary, so a fault has one name on both surfaces and an owner searching
 * for it finds both.
 */
export const ERROR_CODES = {
  reference: "ERR_REF",
  duplicate: "ERR_DUPLICATE",
  orphanMapping: "ORPHAN_MAPPING",
  missingKey: "PK_MISSING",
  mandatoryUnmapped: "MANDATORY_UNMAPPED",
  badJson: "INVALID_JSON",
  unknownKey: "UNKNOWN_KEY",
  badValue: "INVALID_VALUE",
  required: "ERR_REQUIRED",
  transform: "ERR_TRANSFORM",
};

/**
 * Its four severities. Only Error and above block a sync — which is why both
 * problems already measured in the live workbook (fifteen orphan profiles, one
 * mapping to a non-existent attribute) are recorded as Warn and ship anyway.
 */
export const SEVERITIES = ["Info", "Warning", "Error", "Critical"];
export const BLOCKS_SYNC_FROM = "Error";

/** The six tabs, by the gid compiled into the add-in's endpoints.json. */
export const SHEET_GIDS = {
  "1.TableDefinition": "1974308164",
  "2.SchemaRule": "1666369555",
  "3.DataSource": "434807667",
  "4.DataMap": "2085184385",
  "5.ExportViews": "756534895",
  "6.RibbonControls": "1089316777",
};

/**
 * Everything above, shaped for `vocabularies(workbook, known)` so the Console's
 * drop-downs come from the code and fall back to the file only where the code
 * has nothing to say.
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
