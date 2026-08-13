// One DataMap row, judged as the add-in judges it.
//
// This sheet's validation is ADVISORY in the add-in — findings become log lines
// and nothing filters a bad row out. So several tests below pin a fault the
// add-in accepts and then gets wrong, because that is the only place it can be
// caught: here, while it is being typed.

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkDataMapRow, checkProfileCoverage, resolvedProfiles, attributesFor }
  from "../datamap-rules.js";

const sound = (over = {}) => ({
  PROFILE_KEY: "T_BITUMEN",
  TARGET_ATTRIBUTE_KEY: "current_price",
  SOURCE_TYPE: "Header",
  MATCH_MODE: "Exact",
  SOURCE_EXPRESSION: "Price",
  TRANSFORM_CHAIN: "TRIM|TO_DECIMAL",
  PROCESS_CONFIG: "",
  ...over,
});

/** One source pointing at T_BITUMEN with a blank profile — the common shape. */
const sources = [{SOURCE_KEY: "SRC_A", TARGET_ENTITY_KEY: "T_BITUMEN",
                  PROFILE_KEY: ""}];
const schema = [
  {ENTITY_KEY: "T_BITUMEN", ATTRIBUTE_KEY: "code", IS_PK: "TRUE", IS_MANDATORY: "TRUE"},
  {ENTITY_KEY: "T_BITUMEN", ATTRIBUTE_KEY: "current_price", IS_MANDATORY: "FALSE"},
];

const codes = (found) => found.map((f) => f.code);
const fields = (found) => found.map((f) => f.field);

test("a sound row produces nothing at all", () => {
  assert.deepEqual(checkDataMapRow(sound(), [], sources, schema), []);
});

test("either mandatory field blank rejects the row and stops", () => {
  for (const blank of ["PROFILE_KEY", "TARGET_ATTRIBUTE_KEY"]) {
    const found = checkDataMapRow(sound({[blank]: ""}), [], sources, schema);
    assert.equal(found.length, 1, `${blank} produced a cascade`);
    assert.equal(found[0].severity, "Critical");
    assert.equal(found[0].field, blank);
  }
});

// ---------------------------------------------------------------------------
// The join nobody can see from the sheet.
// ---------------------------------------------------------------------------

test("a source with a blank profile resolves to its TABLE, not to DEFAULT", () => {
  assert.deepEqual(resolvedProfiles(sources), ["T_BITUMEN"]);
  assert.deepEqual(resolvedProfiles(
    [{TARGET_ENTITY_KEY: "T_X", PROFILE_KEY: "DEFAULT"}]), ["T_X"]);
  assert.deepEqual(resolvedProfiles(
    [{TARGET_ENTITY_KEY: "T_X", PROFILE_KEY: "CUSTOM"}]), ["CUSTOM"]);
});

test("a mapping literally named DEFAULT is a dead row, and says so", () => {
  const found = checkDataMapRow(
    sound({PROFILE_KEY: "DEFAULT"}), [], sources, schema);
  const dead = found.filter((f) => f.field === "PROFILE_KEY");
  assert.equal(dead.length, 1);
  assert.equal(dead[0].severity, "Error");
  assert.match(dead[0].detail, /DEAD ROW/);
  // And the reason it is easy to get wrong is named.
  assert.match(dead[0].detail, /own comment offers as an example/);
});

test("a profile nothing resolves to is a warning, not an error", () => {
  // Nothing reports these at sync time either — they simply sit there.
  const found = checkDataMapRow(
    sound({PROFILE_KEY: "T_NOWHERE"}), [], sources, schema);
  const orphan = found.find((f) => f.field === "PROFILE_KEY");
  assert.equal(orphan.severity, "Warning");
});

test("a column the schema does not have loses its data, and lists what exists", () => {
  const found = checkDataMapRow(
    sound({TARGET_ATTRIBUTE_KEY: "price"}), [], sources, schema);
  const orphan = found.find((f) => f.field === "TARGET_ATTRIBUTE_KEY");
  assert.equal(orphan.severity, "Error");
  assert.match(orphan.detail, /data is lost/);
  assert.match(orphan.fix, /current_price/, "the message does not offer the real names");
  assert.deepEqual(attributesFor("T_BITUMEN", sources, schema),
                   ["code", "current_price"]);
});

test("internal spaces are auto-corrected, and the Console does not rely on it", () => {
  const found = checkDataMapRow(
    sound({TARGET_ATTRIBUTE_KEY: "current price"}), [], sources, schema);
  const said = found.filter((f) => f.field === "TARGET_ATTRIBUTE_KEY");
  // One note about the spaces, and NO orphan error — because the cleaned name
  // does resolve, which is exactly what the add-in does before looking it up.
  assert.equal(said.length, 1);
  assert.equal(said[0].severity, "Warning");
  assert.match(said[0].detail, /replaced with underscores/);
});

test("two mappings for one column: last on the sheet wins", () => {
  const found = checkDataMapRow(
    sound(), [sound({SOURCE_EXPRESSION: "Cost"})], sources, schema);
  const clash = found.find((f) => f.code === "SILENT_OVERRIDE");
  assert.ok(clash, "a duplicated target stopped being reported");
  assert.match(clash.detail, /depends on row order/);
});

// ---------------------------------------------------------------------------
// Where the value comes from.
// ---------------------------------------------------------------------------

test("Formula is not implemented, and nulls every row", () => {
  const found = checkDataMapRow(
    sound({SOURCE_TYPE: "Formula"}), [], sources, schema);
  const said = found.find((f) => f.field === "SOURCE_TYPE");
  assert.equal(said.severity, "Error");
  assert.equal(said.code, "NOT_APPLIED");
  assert.match(said.detail, /NOT IMPLEMENTED/);
});

test("Index is a COLUMN position from zero, whatever the docs say", () => {
  assert.deepEqual(
    checkDataMapRow(sound({SOURCE_TYPE: "Index", SOURCE_EXPRESSION: "0"}),
                    [], sources, schema),
    [], "a valid column position was refused");
  for (const bad of ["-1", "2.5", "first", ""]) {
    const found = checkDataMapRow(
      sound({SOURCE_TYPE: "Index", SOURCE_EXPRESSION: bad}), [], sources, schema);
    assert.ok(found.some((f) => f.field === "SOURCE_EXPRESSION"),
      `Index accepted "${bad}"`);
  }
});

test("Context accepts exactly four tokens, and names the two that are fiction", () => {
  for (const good of ["SYNC_DATE", "synctime", "CURRENTTIER"]) {
    assert.deepEqual(
      checkDataMapRow(sound({SOURCE_TYPE: "Context", SOURCE_EXPRESSION: good,
        MATCH_MODE: ""}), [], sources, schema),
      [], `${good} was refused`);
  }
  const found = checkDataMapRow(
    sound({SOURCE_TYPE: "Context", SOURCE_EXPRESSION: "CurrentCountry",
      MATCH_MODE: ""}), [], sources, schema);
  const said = found.find((f) => f.field === "SOURCE_EXPRESSION");
  assert.match(said.detail, /documentation only/,
    "the message does not say that the add-in's own examples do not work");
});

test("MATCH_MODE is dead unless the source type is Header", () => {
  const found = checkDataMapRow(
    sound({SOURCE_TYPE: "Constant", SOURCE_EXPRESSION: "SAR",
      MATCH_MODE: "Contains"}), [], sources, schema);
  const said = found.find((f) => f.field === "MATCH_MODE");
  assert.equal(said.severity, "Warning");
  assert.match(said.detail, /does nothing at all/);
});

test("a Regex that does not compile matches NOTHING rather than failing", () => {
  const found = checkDataMapRow(
    sound({MATCH_MODE: "Regex", SOURCE_EXPRESSION: "Price(["}),
    [], sources, schema);
  const said = found.find((f) => f.field === "SOURCE_EXPRESSION");
  assert.equal(said.severity, "Error");
  assert.match(said.detail, /does NOT fail/);
});

test("Fuzzy is warned about even when it is spelled correctly", () => {
  // Two edits of tolerance and first-past-the-post is a silent wrong binding,
  // and there is no setting to tighten it.
  const found = checkDataMapRow(sound({MATCH_MODE: "Fuzzy"}), [], sources, schema);
  assert.match(found.find((f) => f.field === "MATCH_MODE").detail, /two edits/);
});

// ---------------------------------------------------------------------------
// The chain, where a typo is silent data corruption.
// ---------------------------------------------------------------------------

test("an unknown transform passes the value through UNCHANGED", () => {
  const found = checkDataMapRow(
    sound({TRANSFORM_CHAIN: "TRIM|TO_NUMBER"}), [], sources, schema);
  const said = found.find((f) => f.field === "TRANSFORM_CHAIN");
  assert.equal(said.severity, "Error");
  assert.match(said.detail, /UNCHANGED/);
});

test("the chain is case-insensitive and tolerates empty steps", () => {
  assert.deepEqual(
    checkDataMapRow(sound({TRANSFORM_CHAIN: "trim||Upper"}), [], sources, schema),
    [], "the add-in accepts both and this refused one");
});

test("SUBSTRING and JSON_EXTRACT are checked for their arguments", () => {
  assert.deepEqual(
    checkDataMapRow(sound({TRANSFORM_CHAIN: "SUBSTRING:0:3"}), [], sources, schema),
    []);
  assert.deepEqual(
    checkDataMapRow(sound({TRANSFORM_CHAIN: "JSON_EXTRACT:addr.city"}),
                    [], sources, schema), []);
  for (const bad of ["SUBSTRING", "SUBSTRING:x", "JSON_EXTRACT"]) {
    const found = checkDataMapRow(
      sound({TRANSFORM_CHAIN: bad}), [], sources, schema);
    assert.ok(found.some((f) => f.field === "TRANSFORM_CHAIN"),
      `"${bad}" was accepted`);
  }
  // A transform that takes none is only a note when given one — the add-in
  // ignores the argument rather than failing.
  const extra = checkDataMapRow(
    sound({TRANSFORM_CHAIN: "TRIM:2"}), [], sources, schema);
  assert.equal(extra[0].severity, "Warning");
});

// ---------------------------------------------------------------------------
// PROCESS_CONFIG, and the trap that passes every check the add-in makes.
// ---------------------------------------------------------------------------

test("a strategy in the wrong case passes validation and then does nothing", () => {
  const found = checkDataMapRow(
    sound({PROCESS_CONFIG: '{"NullStrategy":"usedefault"}'}), [], sources, schema);
  const said = found.find((f) => f.field === "PROCESS_CONFIG");
  assert.equal(said.severity, "Error");
  assert.match(said.detail, /falls through to Skip/);
  assert.match(said.fix, /UseDefault/);

  // And the correct spelling is accepted, with only the missing default noted.
  const right = checkDataMapRow(
    sound({PROCESS_CONFIG: '{"NullStrategy":"UseDefault","DefaultValue":"0"}'}),
    [], sources, schema);
  assert.deepEqual(right, []);
});

test("a wrong TYPE reverts the whole bag, not just its own key", () => {
  const found = checkDataMapRow(
    sound({PROCESS_CONFIG: '{"AutoTrim":"yes","RowFilter":"NOT_EMPTY"}'}),
    [], sources, schema);
  const said = found.find((f) => /AutoTrim/.test(f.detail));
  assert.equal(said.severity, "Error");
  assert.match(said.detail, /EVERY setting in the/);
});

test("an unknown row-filter operator keeps every row rather than failing", () => {
  const found = checkDataMapRow(
    sound({PROCESS_CONFIG: '{"RowFilter":"MATCHES:EG"}'}), [], sources, schema);
  const said = found.find((f) => f.field === "PROCESS_CONFIG");
  assert.match(said.detail, /KEEPS every row/);

  assert.deepEqual(
    checkDataMapRow(sound({PROCESS_CONFIG: '{"RowFilter":"IN:EG,SA,AE"}'}),
                    [], sources, schema), []);
  // EMPTY and NOT_EMPTY take no value; everything else needs one.
  assert.deepEqual(
    checkDataMapRow(sound({PROCESS_CONFIG: '{"RowFilter":"NOT_EMPTY"}'}),
                    [], sources, schema), []);
  assert.ok(checkDataMapRow(sound({PROCESS_CONFIG: '{"RowFilter":"EQ"}'}),
                            [], sources, schema).length);
});

test("a bag that is not an object at all reverts to defaults", () => {
  const found = checkDataMapRow(
    sound({PROCESS_CONFIG: '$preset:standard'}), [], sources, schema);
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /starting with a brace/);
});

// ---------------------------------------------------------------------------
// What a profile is missing — two of the four gates that stop a sync.
// ---------------------------------------------------------------------------

test("a profile with no mappings at all fails every source using it", () => {
  const found = checkProfileCoverage("T_BITUMEN", [], sources, schema);
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Critical");
  assert.match(found[0].detail, /FAILS OUTRIGHT/);
});

test("an unmapped key or required column is refused before any write", () => {
  // `code` is both the key and required; only current_price is mapped.
  const found = checkProfileCoverage("T_BITUMEN", [sound()], sources, schema);
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Critical");
  assert.match(found[0].detail, /key column code/);

  const complete = checkProfileCoverage(
    "T_BITUMEN", [sound(), sound({TARGET_ATTRIBUTE_KEY: "code"})], sources, schema);
  assert.deepEqual(complete, []);
});

test("an ordinary column left unmapped is not a fault", () => {
  // Only IS_PK and IS_MANDATORY stop a sync. Demanding the rest would make the
  // Console refuse a configuration the add-in syncs happily every day.
  const optional = [...schema,
    {ENTITY_KEY: "T_BITUMEN", ATTRIBUTE_KEY: "note", IS_MANDATORY: "FALSE"}];
  const found = checkProfileCoverage(
    "T_BITUMEN", [sound(), sound({TARGET_ATTRIBUTE_KEY: "code"})],
    sources, optional);
  assert.deepEqual(found, []);
});

test("every finding carries a code and a field", () => {
  const messy = checkDataMapRow(
    sound({SOURCE_TYPE: "Formula", TRANSFORM_CHAIN: "NOPE",
      PROCESS_CONFIG: '{"NullStrategy":"fail"}'}), [], sources, schema);
  assert.ok(messy.length >= 3);
  for (const found of messy) {
    assert.ok(found.code, `${found.field} has no code`);
    assert.ok(found.field, "a finding with no field cannot be shown anywhere");
  }
  assert.ok(!codes(messy).includes(undefined));
  assert.ok(!fields(messy).includes(undefined));
});
