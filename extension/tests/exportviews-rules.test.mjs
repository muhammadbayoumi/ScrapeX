// 5.ExportViews — the rules, and the blank sheet they exist to prevent.
//
// Every expectation here is the ADD-IN's behaviour, not a preference. Where a
// test asserts silence, that silence is the add-in's too: a blank COLUMNS means
// "export everything" and flagging it would teach an owner to ignore us.

import test from "node:test";
import assert from "node:assert/strict";

import { checkExportViewRow, columnList, exportableAttributes, exportsNothing,
  viewSwitchedOff } from "../exportviews-rules.js";

const VIEW = {
  VIEW_KEY: "RATES", ENTITY_KEY: "T_UNITS", LABEL: "Rates",
  COLUMNS: "", ALIASES: "", WHERE_FILTER: "", SORT_BY: "", VIEW_CONFIG: "",
};
const DEFINITIONS = [{ENTITY_KEY: "T_UNITS"}, {ENTITY_KEY: "T_ITEMS"}];
const SCHEMA = [
  {ENTITY_KEY: "T_UNITS", ATTRIBUTE_KEY: "ITEM_NAME"},
  {ENTITY_KEY: "T_UNITS", ATTRIBUTE_KEY: "RATE_2021"},
  {ENTITY_KEY: "T_UNITS", ATTRIBUTE_KEY: "INTERNAL", IS_VIRTUAL: "1"},
  {ENTITY_KEY: "T_UNITS", ATTRIBUTE_KEY: "HIDDEN", IS_VISIBLE: "0"},
];

const check = (over = {}, others = []) =>
  checkExportViewRow({...VIEW, ...over}, others, DEFINITIONS, SCHEMA);
const codes = (found) => found.map((f) => f.code);
const on = (found, field) => found.filter((f) => f.field === field);

// ---- the two rows the add-in rejects whole ---------------------------------

test("a view with no key is Critical and nothing after it is read", () => {
  const found = check({VIEW_KEY: "", COLUMNS: "NOPE", SORT_BY: "X LIMIT 5"});
  assert.equal(found.length, 1, "the row kept being checked past its Critical");
  assert.equal(found[0].severity, "Critical");
  assert.equal(found[0].field, "VIEW_KEY");
});

test("a view with no entity is Critical too", () => {
  const found = check({ENTITY_KEY: ""});
  assert.equal(found.length, 1);
  assert.equal(found[0].field, "ENTITY_KEY");
});

// ---- the silent losses ------------------------------------------------------

test("a duplicate VIEW_KEY is global, not per entity, and is thrown away", () => {
  const found = on(check({}, [{VIEW_KEY: "rates", ENTITY_KEY: "T_ITEMS"}]),
                   "VIEW_KEY");
  assert.equal(found.length, 1, "a duplicate on a DIFFERENT entity was allowed");
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /INSERT OR IGNORE/);
});

test("every COLUMNS name missing is the blank sheet, and is called that", () => {
  const found = check({COLUMNS: "NOPE, ALSO_NOPE"});
  assert.ok(exportsNothing(found), "the worst failure in this sheet was not named");
  const columns = on(found, "COLUMNS");
  assert.equal(columns[0].severity, "Error");
  assert.match(columns[0].detail, /blank sheet|completely blank/i);
});

test("SOME names missing is a warning, not the blank sheet", () => {
  const found = check({COLUMNS: "ITEM_NAME, NOPE"});
  assert.equal(exportsNothing(found), false);
  assert.equal(on(found, "COLUMNS")[0].severity, "Warning");
});

test("a real column that is virtual or hidden is dropped exactly like a typo", () => {
  for (const name of ["INTERNAL", "HIDDEN"]) {
    const found = check({COLUMNS: name});
    assert.ok(exportsNothing(found),
      `${name} is defined but never exported, and was treated as exportable`);
  }
});

test("a BLANK COLUMNS means every column and must not be flagged", () => {
  assert.deepEqual(on(check({COLUMNS: ""}), "COLUMNS"), []);
  assert.deepEqual(on(check({COLUMNS: "   "}), "COLUMNS"), []);
});

test("only the comma separates COLUMNS", () => {
  assert.deepEqual(columnList("A, B ,, C"), ["A", "B", "C"]);
  assert.deepEqual(columnList("A;B"), ["A;B"], "a semicolon became a separator");
  assert.deepEqual(columnList("A|B"), ["A|B"], "a pipe became a separator");
});

test("a non-empty COLUMNS that parses to nothing is the add-in's own warning", () => {
  const found = on(check({COLUMNS: " , , "}), "COLUMNS");
  assert.equal(found[0].severity, "Warning");
  assert.equal(found[0].code, "ERR_FORMAT");
});

// ---- ALIASES ---------------------------------------------------------------

test("ALIASES keys are case-SENSITIVE, unlike COLUMNS one cell away", () => {
  const found = on(check({ALIASES: '{"rate_2021": "Rate"}'}), "ALIASES");
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /CASE-\s*SENSITIVELY/);
  assert.match(found[0].fix, /RATE_2021/);
});

test("a correctly cased alias is silent", () => {
  assert.deepEqual(on(check({ALIASES: '{"RATE_2021": "Rate"}'}), "ALIASES"), []);
});

test("a comma list where an object belongs is Error INVALID_JSON", () => {
  const found = on(check({ALIASES: "RATE_2021, ITEM_NAME"}), "ALIASES");
  assert.equal(found[0].code, "INVALID_JSON");
  assert.match(found[0].detail, /empty/i);
});

test("a trailing comma is TOLERATED, because Newtonsoft tolerates it", () => {
  assert.deepEqual(on(check({ALIASES: '{"RATE_2021": "Rate",}'}), "ALIASES"), [],
    "the Console refused a bag the add-in reads every day");
});

// ---- the raw SQL fragments --------------------------------------------------

test("a semicolon in WHERE_FILTER cuts the rest away, and behaves differently in a menu", () => {
  const found = on(check({WHERE_FILTER: "PRICE > 0; DROP TABLE X"}), "WHERE_FILTER");
  assert.equal(found[0].severity, "Warning");
  assert.match(found[0].detail, /Library menu|no such truncation/i);
});

test("double quotes are identifiers in SQLite and produce an empty sheet", () => {
  const found = on(check({WHERE_FILTER: 'REGION = "EG"'}), "WHERE_FILTER");
  assert.match(found[0].fix, /single quotes/i);
});

test("a LIMIT in SORT_BY is an Error, because the engine appends its own", () => {
  const found = on(check({SORT_BY: "NAME ASC LIMIT 50"}), "SORT_BY");
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /100001|LIMIT n LIMIT/);
});

test("the keywords the engine writes itself are refused at the front", () => {
  assert.match(on(check({SORT_BY: "ORDER BY NAME"}), "SORT_BY")[0].detail,
    /ORDER BY ORDER BY/);
  assert.match(on(check({WHERE_FILTER: "WHERE PRICE > 0"}), "WHERE_FILTER")[0].detail,
    /WHERE WHERE/);
});

test("ordinary fragments are left alone", () => {
  const found = check({WHERE_FILTER: "RATE_2021 > 0 AND REGION = 'EG'",
                       SORT_BY: "ITEM_NAME ASC, RATE_2021 DESC"});
  assert.deepEqual(on(found, "WHERE_FILTER"), []);
  assert.deepEqual(on(found, "SORT_BY"), []);
});

// ---- VIEW_CONFIG ------------------------------------------------------------

test("VIEW_CONFIG takes exactly the five keys the code deserialises", () => {
  const found = on(check({VIEW_CONFIG: '{"HeaderText": "x", "Heading": "y"}'}),
                   "VIEW_CONFIG");
  assert.equal(found.length, 1);
  assert.equal(found[0].code, "UNKNOWN_KEY");
  assert.match(found[0].detail, /Heading/);
});

test("a banner style outside the five falls back, and the Console says so", () => {
  const found = on(check({VIEW_CONFIG: '{"HeaderStyle": "Loud"}'}), "VIEW_CONFIG");
  assert.equal(found[0].code, "INVALID_VALUE");
  assert.match(found[0].detail, /Marketing/);
});

test("a banner style in the wrong case WORKS and is only noted", () => {
  const found = on(check({VIEW_CONFIG: '{"HeaderStyle": "marketing"}'}),
                   "VIEW_CONFIG");
  assert.equal(found[0].severity, "Info");
});

// ---- the rest ---------------------------------------------------------------

test("an entity no table defines is an orphan nothing else reports", () => {
  const found = on(check({ENTITY_KEY: "T_GHOST"}), "ENTITY_KEY");
  assert.equal(found[0].code, "ORPHAN_VIEW");
  assert.match(found[0].detail, /does NOT cover views/);
});

test("a blank LABEL is a Warning, and the VIEW_KEY genuinely becomes the text", () => {
  const found = on(check({LABEL: ""}), "LABEL");
  assert.equal(found[0].severity, "Warning");
});

test("exportableAttributes is the engine's list, not the sheet's", () => {
  assert.deepEqual(exportableAttributes("T_UNITS", SCHEMA),
                   ["ITEM_NAME", "RATE_2021"]);
  assert.deepEqual(exportableAttributes("t_units", SCHEMA),
                   ["ITEM_NAME", "RATE_2021"], "the lookup is case-sensitive");
});

test("IS_ACTIVE is read with the add-in's default, so blank means live", () => {
  assert.equal(viewSwitchedOff({}), false);
  assert.equal(viewSwitchedOff({IS_ACTIVE: "no"}), true);
  assert.equal(viewSwitchedOff({IS_ACTIVE: "لا"}), true);
  assert.equal(viewSwitchedOff({IS_ACTIVE: "Active"}), false,
    "an unreadable spelling must keep the add-in's TRUE default");
});

test("a clean row says nothing at all", () => {
  assert.deepEqual(check({COLUMNS: "ITEM_NAME, RATE_2021"}), []);
});

test("the columns of an entity we do not know are not judged", () => {
  // Not laziness — a guess. With no SchemaRule rows for T_GHOST the exportable
  // set is empty, and "every name misses" would be true of EVERY view of it.
  // Reporting a blank sheet on that evidence would cry wolf on a workbook whose
  // real fault is one row above, on ENTITY_KEY.
  const found = check({ENTITY_KEY: "T_GHOST", COLUMNS: "ITEM_NAME"});
  assert.deepEqual(on(found, "COLUMNS"), []);
  assert.equal(on(found, "ENTITY_KEY")[0].code, "ORPHAN_VIEW");
});

test("every finding names its field and carries a code", () => {
  const found = check({LABEL: "", COLUMNS: "NOPE", ALIASES: "oops",
                       SORT_BY: "X LIMIT 2", VIEW_CONFIG: '{"Nope": 1}'});
  assert.ok(found.length >= 5, `only ${found.length}: ${codes(found).join()}`);
  for (const f of found) {
    assert.ok(f.field, "a finding with no field cannot be shown beside a cell");
    assert.ok(f.code, `${f.field} has no code`);
    assert.ok(f.detail);
  }
});
