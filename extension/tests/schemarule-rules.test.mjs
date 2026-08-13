// One SchemaRule row, judged as the add-in judges it.
//
// The sheet where the add-in is quietest: a repeated column name is resolved
// last-wins with NO record anywhere. Several tests below exist only to hold that
// distinction — between a fault the add-in reports and one it does not — because
// it is the distinction the Console is for.

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkSchemaRuleRow, checkEntityRoles } from "../schemarule-rules.js";

const sound = (over = {}) => ({
  ENTITY_KEY: "T_BITUMEN",
  ATTRIBUTE_KEY: "PRICE_SAR",
  DISPLAY_HEADER: "Price (SAR)",
  ORDINAL_POS: "3",
  LICENSE_TIER: "Free",
  SEMANTIC_ROLE: "PRICE",
  DATA_TYPE: "DECIMAL",
  IS_PK: "FALSE",
  IS_MANDATORY: "FALSE",
  IS_VIRTUAL: "FALSE",
  IS_DERIVED: "FALSE",
  IS_VISIBLE: "TRUE",
  UX_CONFIG: "",
  LOGIC_CONFIG: "",
  ...over,
});

const live = [{ENTITY_KEY: "T_BITUMEN", IS_ACTIVE: "TRUE"}];
const codes = (found) => found.map((f) => f.code);
const fields = (found) => found.map((f) => f.field);

test("a sound row produces nothing at all", () => {
  assert.deepEqual(checkSchemaRuleRow(sound(), [], live), []);
});

test("either key blank rejects the row and stops", () => {
  for (const blank of ["ENTITY_KEY", "ATTRIBUTE_KEY"]) {
    const found = checkSchemaRuleRow(sound({[blank]: ""}), [], live);
    assert.equal(found.length, 1, `${blank} produced a cascade`);
    assert.equal(found[0].severity, "Critical");
    assert.equal(found[0].field, blank);
  }
});

// ---------------------------------------------------------------------------
// The fault the add-in never mentions.
// ---------------------------------------------------------------------------

test("a repeated column name is LAST-wins, silently, and the Console says so", () => {
  const found = checkSchemaRuleRow(
    sound(), [sound({DISPLAY_HEADER: "Price", SEMANTIC_ROLE: ""})], live);
  const clash = found.filter((f) => f.field === "ATTRIBUTE_KEY");
  assert.equal(clash.length, 1);
  assert.equal(clash[0].severity, "Error");
  assert.match(clash[0].detail, /LAST row/);
  assert.match(clash[0].detail, /no log line/,
    "the message does not say that nothing anywhere records this");
});

test("the duplicate is per ENTITY, not per sheet", () => {
  // A column of the same name on a DIFFERENT table is normal and must not be
  // flagged — CODE, NAME and UNIT repeat across nearly every table there is.
  const otherTable = [{...sound(), ENTITY_KEY: "T_DIESEL"}];
  assert.deepEqual(
    checkSchemaRuleRow(sound(), otherTable, live).filter(
      (f) => f.code === "SILENT_OVERRIDE"),
    [],
    "siblings are being read as the whole sheet rather than one table's rows");
});

test("a column whose table does not exist is dropped from the graph", () => {
  const found = checkSchemaRuleRow(sound({ENTITY_KEY: "T_GHOST"}), [], live);
  const orphan = found.filter((f) => f.code === "ORPHAN_COLS");
  assert.equal(orphan.length, 1);
  assert.equal(orphan[0].severity, "Error");
});

test("a table that is switched OFF drops its columns just the same", () => {
  const found = checkSchemaRuleRow(
    sound(), [], [{ENTITY_KEY: "T_BITUMEN", IS_ACTIVE: "FALSE"}]);
  const orphan = found.find((f) => f.code === "ORPHAN_COLS");
  assert.ok(orphan, "a switched-off table stopped orphaning its columns");
  assert.match(orphan.detail, /ACTIVE tables only/);
});

// ---------------------------------------------------------------------------
// The key, and the three combinations the add-in refuses.
// ---------------------------------------------------------------------------

test("a key cannot be virtual or derived", () => {
  for (const flag of ["IS_VIRTUAL", "IS_DERIVED"]) {
    const found = checkSchemaRuleRow(
      sound({IS_PK: "TRUE", IS_MANDATORY: "TRUE", [flag]: "TRUE"}), [], live);
    const refused = found.filter((f) => f.field === "IS_PK"
      && f.severity === "Error");
    assert.equal(refused.length, 1, `IS_PK + ${flag} was allowed`);
  }
});

test("a key that may be empty breaks the merge it exists for", () => {
  const found = checkSchemaRuleRow(sound({IS_PK: "TRUE"}), [], live);
  const said = found.find((f) => f.field === "IS_PK");
  assert.equal(said.severity, "Warning");
  assert.match(said.fix, /IS_MANDATORY/);
});

test("a composite key is described exactly, not as unsupported", () => {
  // The add-in's own warning says composite keys are unsupported. That is true
  // of three call sites and FALSE of the database, which builds a real compound
  // key — so repeating the add-in's wording would teach the wrong thing.
  const found = checkSchemaRuleRow(
    sound({ATTRIBUTE_KEY: "CODE", IS_PK: "TRUE", IS_MANDATORY: "TRUE"}),
    [sound({ATTRIBUTE_KEY: "REGION", IS_PK: "TRUE"})], live);
  const said = found.find((f) => f.field === "IS_PK" && f.severity === "Warning");
  assert.match(said.detail, /compound key and de-duplicates correctly/);
  assert.match(said.detail, /FIRST key column/);
});

// ---------------------------------------------------------------------------
// Vocabularies, and the blanks that are legitimate.
// ---------------------------------------------------------------------------

test("a blank role is NONE, which is a real value and never a fault", () => {
  assert.deepEqual(checkSchemaRuleRow(sound({SEMANTIC_ROLE: ""}), [], live), [],
    "an ordinary data column with no engine meaning was flagged");
});

test("a blank ordinal is 0 and legitimate; a negative one is not used", () => {
  assert.deepEqual(checkSchemaRuleRow(sound({ORDINAL_POS: ""}), [], live), []);
  const negative = checkSchemaRuleRow(sound({ORDINAL_POS: "-1"}), [], live);
  assert.equal(negative.length, 1);
  assert.equal(negative[0].severity, "Warning");
  const words = checkSchemaRuleRow(sound({ORDINAL_POS: "third"}), [], live);
  assert.equal(words[0].severity, "Error");
});

test("the DATA_TYPE aliases the parser normalises are accepted, and named", () => {
  for (const [typed, meant] of [["Boolean", "BOOL"], ["Varchar", "TEXT"],
                                ["Integer", "INT"], ["Double", "DECIMAL"]]) {
    const found = checkSchemaRuleRow(sound({DATA_TYPE: typed}), [], live);
    assert.equal(found.length, 1, `${typed} was refused`);
    assert.equal(found[0].severity, "Info");
    assert.match(found[0].detail, new RegExp(meant));
  }
});

test("an unreadable type leaves the column as TEXT, and says what that costs", () => {
  const found = checkSchemaRuleRow(sound({DATA_TYPE: "Money"}), [], live);
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /stop adding up/);
});

test("repeatable roles repeat; singular ones do not", () => {
  const twice = (role) => checkSchemaRuleRow(
    sound({SEMANTIC_ROLE: role}),
    [sound({ATTRIBUTE_KEY: "OTHER", SEMANTIC_ROLE: role})], live)
    .filter((f) => f.field === "SEMANTIC_ROLE");

  assert.deepEqual(twice("MENU_GROUP"), [],
    "MENU_GROUP is the one repeatable menu role and was refused");
  assert.deepEqual(twice("EXPORT_GROUP"), []);

  // NONE is not a role. It is what every ordinary column carries, so counting
  // it as singular fires on nearly every table there is — measured at 23 false
  // warnings against the owner's real workbook before this was excluded.
  assert.deepEqual(twice("NONE"), [],
    "NONE is being counted as a repeated role");
  assert.deepEqual(twice("none"), [], "and the check is case-sensitive again");

  const menu = twice("MENU_LABEL");
  assert.equal(menu.length, 1);
  assert.equal(menu[0].code, "ERR_DUPLICATE",
    "MENU_LABEL is one of the ten the add-in warns about");

  // An engine role repeats with NO warning anywhere in the add-in — two PRICE
  // columns is entirely silent, which is why this one is Console-only.
  const price = twice("PRICE");
  assert.equal(price.length, 1);
  assert.equal(price[0].code, "SILENT_OVERRIDE");
  assert.match(price[0].detail, /NOTHING about it at all/);
});

test("a broken bag loses all of its settings", () => {
  const found = checkSchemaRuleRow(
    sound({LOGIC_CONFIG: "{Min: 0}"}), [], live);
  assert.deepEqual(fields(found), ["LOGIC_CONFIG"]);
  assert.equal(found[0].code, "INVALID_JSON");
});

// ---------------------------------------------------------------------------
// What a whole entity needs, which no single row can answer.
// ---------------------------------------------------------------------------

test("a CONVERSION table without its three roles cannot convert", () => {
  const found = checkEntityRoles("T_UNITS", [sound({SEMANTIC_ROLE: "NAME"})],
    {ENTITY_KEY: "T_UNITS", ENTITY_TYPE: "CONVERSION"});
  assert.equal(found.length, 3);
  for (const role of ["CONV_SOURCE", "CONV_TARGET", "CONV_FACTOR"]) {
    assert.ok(found.some((f) => f.detail.includes(role)), `${role} not demanded`);
  }
  assert.deepEqual([...new Set(found.map((f) => f.severity))], ["Error"]);
});

test("a COST table with no PRICE is a warning, not an error", () => {
  // The add-in's own severity. Raising it would block a table it happily syncs.
  const found = checkEntityRoles("T_BITUMEN", [sound({SEMANTIC_ROLE: "NAME"})],
    {ENTITY_KEY: "T_BITUMEN", ENTITY_TYPE: "COST"});
  assert.deepEqual([...new Set(found.map((f) => f.severity))], ["Warning"]);
});

test("a LIBRARY table needs a way to identify and a way to download", () => {
  const bare = checkEntityRoles("T_DOCS", [sound({SEMANTIC_ROLE: "NAME"})],
    {ENTITY_KEY: "T_DOCS", ENTITY_TYPE: "LIBRARY"});
  assert.ok(bare.some((f) => f.severity === "Error" && /MENU_KEY/.test(f.detail)));
  assert.ok(bare.some((f) => /downloaded/.test(f.detail)));

  // A primary key satisfies the identity requirement on its own.
  const keyed = checkEntityRoles("T_DOCS",
    [sound({SEMANTIC_ROLE: "NAME", IS_PK: "TRUE"}),
     sound({ATTRIBUTE_KEY: "URL", SEMANTIC_ROLE: "MENU_URL"}),
     sound({ATTRIBUTE_KEY: "LBL", SEMANTIC_ROLE: "MENU_LABEL"})],
    {ENTITY_KEY: "T_DOCS", ENTITY_TYPE: "LIBRARY"});
  assert.deepEqual(keyed.filter((f) => f.severity === "Error"), []);
});

test("both URL roles together is not an error — one simply wins", () => {
  const found = checkEntityRoles("T_DOCS",
    [sound({ATTRIBUTE_KEY: "A", SEMANTIC_ROLE: "MENU_KEY"}),
     sound({ATTRIBUTE_KEY: "B", SEMANTIC_ROLE: "MENU_URL"}),
     sound({ATTRIBUTE_KEY: "C", SEMANTIC_ROLE: "MENU_DRIVE_URL"}),
     sound({ATTRIBUTE_KEY: "D", SEMANTIC_ROLE: "MENU_LABEL"})],
    {ENTITY_KEY: "T_DOCS", ENTITY_TYPE: "LIBRARY"});
  const both = found.find((f) => /MENU_URL wins/.test(f.detail));
  assert.ok(both);
  assert.equal(both.severity, "Info");
});

test("an ordinary table demands no roles at all", () => {
  assert.deepEqual(
    checkEntityRoles("T_REF", [sound({SEMANTIC_ROLE: ""})],
      {ENTITY_KEY: "T_REF", ENTITY_TYPE: "REF"}),
    [], "a plain reference table was made to justify itself");
});

test("every finding carries a code", () => {
  const messy = checkSchemaRuleRow(
    sound({ENTITY_KEY: "T_GHOST", DATA_TYPE: "Money", DISPLAY_HEADER: "",
      IS_PK: "TRUE", IS_VIRTUAL: "TRUE"}), [], live);
  assert.ok(messy.length >= 4);
  for (const found of messy) assert.ok(found.code, `${found.field} has no code`);
  assert.ok(!codes(messy).includes("INVALID_VALUE")
    || messy.every((f) => f.code !== "INVALID_VALUE" || f.field !== "ENTITY_KEY"));
});
