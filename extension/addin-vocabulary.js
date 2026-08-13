// GENERATED — do not edit. Run `python tools/sync_addin_contract.py`.
//
// The source is contract/addin-contract.json, which describes what
// mbiXaddin's C# accepts. A test fails if this file and that one
// disagree, so a hand edit here is caught rather than shipped.
//
// contract version 1 · behaviour version 1 · read 2026-08-12 from muhammadbayoumi/mbiXaddin

export const CONTRACT_VERSION = 1;
export const BEHAVIOUR_VERSION = 1;
export const CONTRACT_READ_ON = "2026-08-12";

// ---- 4.DataMap -----------------------------------------------------------
export const SOURCE_TYPES = ["Header", "Index", "Context", "Constant", "Formula"];
export const MATCH_MODES = ["Exact", "Contains", "StartsWith", "Regex", "Fuzzy"];
export const CONTEXT_EXPRESSIONS = ["SYNC_DATE", "SYNCTIMESTAMP", "SYNCTIME", "CURRENTTIER"];
export const TRANSFORMS = ["TRIM", "UPPER", "LOWER", "TO_DECIMAL", "TO_INT", "TO_DATE", "TO_BOOL", "ABS", "SUBSTRING", "JSON_EXTRACT"];
export const PROCESS_CONFIG_KEYS = ["NullStrategy", "DefaultValue", "ErrorStrategy", "AutoTrim", "RowFilter"];
export const MAP_STRATEGIES = ["Skip", "UseDefault", "Fail"];
export const ROW_FILTER_OPERATORS = ["EQ", "NEQ", "GT", "LT", "GTE", "LTE", "CONTAINS", "NOT_CONTAINS", "NOT_EMPTY", "EMPTY", "IN", "NOT_IN"];

// ---- 2.SchemaRule --------------------------------------------------------
export const SEMANTIC_ROLES = ["NONE", "PRICE", "QTY", "TOTAL", "UNIT", "NAME", "CONV_SOURCE", "CONV_TARGET", "CONV_FACTOR", "CONV_DATE_START", "CONV_DATE_END", "MENU_KEY", "MENU_LABEL", "MENU_SCREENTIP", "MENU_SUPERTIP", "MENU_ICON", "MENU_ACTION", "MENU_URL", "MENU_DRIVE_URL", "MENU_FORMAT", "MENU_ORDER", "MENU_GROUP", "EXPORT_GROUP", "MENU_FACET"];
export const REPEATABLE_ROLES = ["MENU_GROUP", "EXPORT_GROUP", "MENU_FACET"];
export const DATA_TYPES = ["TEXT", "DECIMAL", "INT", "BOOL", "DATE", "DATETIME", "GUID", "JSON", "PERCENTAGE", "BLOB"];
export const UX_CONFIG_KEYS = ["Width", "Format", "Align", "HeaderColor", "WrapText", "AutoFit"];
export const LOGIC_CONFIG_KEYS = ["Min", "Max", "Formula", "LookupRef", "DefaultVal", "ListSource", "ListItems", "ListStrict"];

// ---- 1.TableDefinition and 3.DataSource ----------------------------------
export const ENTITY_TYPES = ["COST", "PERF", "REF", "COMP", "CONVERSION", "COST_ENG", "AUDIT", "ASSEMBLY", "LIBRARY", "SYSTEM"];
export const STORAGE_STRATEGIES = ["ReplaceAll", "MergeUpsert", "Append"];
export const STORAGE_STRATEGY_ALIASES = ["REPLACE", "UPSERT", "MERGE", "INSERT"];
export const LICENSE_TIERS = ["Free", "Standard", "Premium", "Admin"];
export const VIEW_MODES = ["Table", "Card", "Chart"];
export const BUSINESS_DOMAINS = ["MATERIAL", "LABOR", "EQUIPMENT", "VENDOR", "PROJECT", "FINANCE", "SYSTEM", "GARB"];
export const CONTEXT_PROPS_KEYS = ["SourceType", "SyncFreq", "SkipRows", "Encoding", "Delimiter", "TimeoutSeconds", "ActionUrl"];
export const CONTEXT_SOURCE_TYPES = ["GoogleSheetTsv", "LocalCsv", "RestApi", "LocalSqlite", "Manual"];
export const SYNC_FREQUENCIES = ["Hourly", "Daily", "Weekly", "Monthly"];

// ---- 6.RibbonControls ----------------------------------------------------
export const MENU_LAYOUTS = ["Nested", "Grouped", "GroupedLarge", "Tiles", "Flat", "FlatLarge", "NestedLarge"];
export const CLICKABLE_ACTIONS = ["Download", "Stream", "Export", "UpdateTable"];
export const MENU_ACTIONS = ["Menu", "Library", "ExportTree", "ViewList"];

// ---- booleans, severities and the add-in's own error codes ---------------
export const TRUE_SPELLINGS = ["1", "true", "yes", "y", "on", "نعم", "صح", "صحيح"];
export const FALSE_SPELLINGS = ["0", "false", "no", "n", "off", "لا", "خطأ", "غلط"];
export const SEVERITIES = ["Info", "Warning", "Error", "Critical"];
export const ERROR_CODES = ["ERR_REF", "ERR_DUPLICATE", "ORPHAN_MAPPING", "PK_MISSING", "MANDATORY_UNMAPPED", "INVALID_JSON", "UNKNOWN_KEY", "INVALID_VALUE", "ERR_REQUIRED", "ERR_TRANSFORM", "ERR_FORMAT"];

// ---- the sheets, and the gids compiled into the add-in ----------------------
export const SHEETS = {
  "1.TableDefinition": {
    gid: "1974308164",
    key: "ENTITY_KEY",
    registryCritical: true,
    columns: ["ENTITY_KEY", "DISPLAY_NAME", "ENTITY_TYPE", "LICENSE_TIER", "IS_ACTIVE", "IS_VISIBLE", "STORAGE_STRATEGY", "PARENT_KEY", "VIEW_MODE", "BUSINESS_DOMAIN", "UX_CONFIG", "SYS_CONFIG", "RIBBON_CONFIG", "EXPORT_CONFIG"],
  },
  "2.SchemaRule": {
    gid: "1666369555",
    key: null,
    registryCritical: true,
    columns: ["ENTITY_KEY", "ATTRIBUTE_KEY", "DISPLAY_HEADER", "ORDINAL_POS", "LICENSE_TIER", "SEMANTIC_ROLE", "DATA_TYPE", "IS_PK", "IS_MANDATORY", "IS_VIRTUAL", "IS_DERIVED", "IS_VISIBLE", "UX_CONFIG", "LOGIC_CONFIG"],
  },
  "3.DataSource": {
    gid: "434807667",
    key: "SOURCE_KEY",
    registryCritical: true,
    columns: ["SOURCE_KEY", "TARGET_ENTITY_KEY", "PROFILE_KEY", "SOURCE_REGION", "SOURCE_URI", "VERSION_TAG", "DISPLAY_LABEL", "MIN_LICENSE_REQ", "IS_ACTIVE", "CONTEXT_PROPS", "Note", "Drive"],
  },
  "4.DataMap": {
    gid: "2085184385",
    key: null,
    registryCritical: true,
    columns: ["PROFILE_KEY", "TARGET_ATTRIBUTE_KEY", "SOURCE_TYPE", "MATCH_MODE", "SOURCE_EXPRESSION", "TRANSFORM_CHAIN", "PROCESS_CONFIG"],
  },
  "5.ExportViews": {
    gid: "756534895",
    key: "VIEW_KEY",
    registryCritical: false,
    columns: ["VIEW_KEY", "ENTITY_KEY", "LABEL", "SCREEN_TIP", "SUPER_TIP", "ICON", "COLUMNS", "ALIASES", "WHERE_FILTER", "SORT_BY", "IS_ACTIVE", "VIEW_CONFIG"],
  },
  "6.RibbonControls": {
    gid: "1089316777",
    key: "ITEM_KEY",
    registryCritical: false,
    columns: ["ITEM_KEY", "CONTROL_KEY", "REGION", "PARENT_KEY", "ORDER", "ACTION_CLASS", "ACTION_TAG", "MENU_LAYOUT", "LABEL", "SCREEN_TIP", "SUPER_TIP", "ICON", "IS_ACTIVE", "Excel", "File", "Folder"],
  },
};

// ---- constants -------------------------------------------------------------
export const TRANSFORM_SEPARATOR = "|";
export const TRANSFORM_ARGUMENT_SEPARATOR = ":";
export const BLOCKS_SYNC_FROM = "Error";

// The three literals SourceUriValidator searches for inside the WHOLE
// address, case-insensitively (SourceUriValidator.cs:80-118). They are
// contract facts exactly like the transform separator above: change one in
// the add-in and every Console warning about an address becomes wrong.
// They live here rather than inline for the same reason the boolean
// spellings do — so a change to the add-in has one place to land.
export const URI_GOOGLE_SHEETS_MARKER = "docs.google.com";
export const URI_TSV_MARKERS = ["output=tsv", "format=tsv"];
export const URI_TAB_MARKER = "gid=";
