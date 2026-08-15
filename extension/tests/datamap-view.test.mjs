// The Mappings card's sentence, which a reader will believe.
//
// The card restates each row in words — «ITEM_CODE comes from the column Item
// Code matched exact, then TRIM UPPER» — and a sentence is read as a statement
// of fact in a way five enums in a row are not. So the rules under it are
// pinned here: the verb per source type, the two clauses that are DROPPED
// rather than printed empty, and the defaults a blank cell means.

import { test } from "node:test";
import assert from "node:assert/strict";

import { effectiveSourceType, headerMatch, transformSteps, mappingSentence,
  mappingGroups } from "../datamap-view.js";

const row = (over = {}) => ({
  PROFILE_KEY: "T_BITUMEN",
  TARGET_ATTRIBUTE_KEY: "ITEM_CODE",
  SOURCE_TYPE: "Header",
  MATCH_MODE: "Exact",
  SOURCE_EXPRESSION: "Item Code",
  TRANSFORM_CHAIN: "TRIM|UPPER",
  ...over,
});

test("a blank source type is Header, exactly as the add-in reads it", () => {
  assert.equal(effectiveSourceType(row({SOURCE_TYPE: ""})), "Header");
  assert.equal(effectiveSourceType(row({SOURCE_TYPE: "  "})), "Header");
});

test("an unrecognised source type is Header too, because that is what runs", () => {
  // The add-in's lookup finds nothing and its branch falls to the default.
  // Grouping this row under "somewhere else" would describe an add-in that
  // does not exist, while datamap-rules.js reports the spelling separately.
  assert.equal(effectiveSourceType(row({SOURCE_TYPE: "Headr"})), "Header");
});

test("a source type is matched whatever its case", () => {
  assert.equal(effectiveSourceType(row({SOURCE_TYPE: "constant"})), "Constant");
});

test("a blank match mode is Exact, and only on a Header row", () => {
  assert.equal(headerMatch(row({MATCH_MODE: ""})), "Exact");
  assert.equal(headerMatch(row({SOURCE_TYPE: "Constant", MATCH_MODE: ""})), "");
});

test("a match mode set on a row that cannot use one is still not shown", () => {
  // The add-in never reads it there, and printing it would state a rule that
  // does not apply beside four that do.
  assert.equal(headerMatch(row({SOURCE_TYPE: "Index", MATCH_MODE: "Fuzzy"})), "");
});

test("a match mode the add-in does not know is shown AS TYPED", () => {
  // Never over-written with the default: an unknown value is a fact about the
  // workbook, and a card that hid it behind "Exact" would be arguing with the
  // finding datamap-rules.js raises about the very same cell.
  assert.equal(headerMatch(row({MATCH_MODE: "Startswith"})), "StartsWith");
  assert.equal(headerMatch(row({MATCH_MODE: "Nearly"})), "Nearly");
});

test("the chain is split into the steps it runs, in order", () => {
  assert.deepEqual(transformSteps(row({TRANSFORM_CHAIN: "TRIM|TO_DECIMAL"})),
                   ["TRIM", "TO_DECIMAL"]);
  assert.deepEqual(transformSteps(row({TRANSFORM_CHAIN: " TRIM | UPPER "})),
                   ["TRIM", "UPPER"]);
});

test("no chain is no steps — never one step holding an empty string", () => {
  assert.deepEqual(transformSteps(row({TRANSFORM_CHAIN: ""})), []);
  assert.deepEqual(transformSteps(row({TRANSFORM_CHAIN: "||"})), []);
  assert.deepEqual(transformSteps({}), []);
});

test("a header row reads as the whole sentence", () => {
  assert.deepEqual(mappingSentence(row()), {
    target: "ITEM_CODE",
    verb: "comes from the column",
    source: "Item Code",
    match: "Exact",
    steps: ["TRIM", "UPPER"],
  });
});

test("a constant drops both clauses rather than printing them empty", () => {
  // «CURRENCY is always SAR» — no `matched —`, no `, then —`. Both are
  // sentences about nothing, and this panel exists to be read as one.
  const said = mappingSentence(row({
    TARGET_ATTRIBUTE_KEY: "CURRENCY", SOURCE_TYPE: "Constant",
    SOURCE_EXPRESSION: "SAR", MATCH_MODE: "", TRANSFORM_CHAIN: ""}));
  assert.equal(said.verb, "is always");
  assert.equal(said.match, "");
  assert.deepEqual(said.steps, []);
});

test("every source type has its own verb, and they are not interchangeable", () => {
  const verb = (type) => mappingSentence(row({SOURCE_TYPE: type})).verb;
  assert.equal(verb("Header"), "comes from the column");
  assert.equal(verb("Index"), "comes from position");
  assert.equal(verb("Constant"), "is always");
  assert.equal(verb("Context"), "comes from the run's");
  assert.equal(verb("Formula"), "is computed as");
});

test("the groups are derived from the source type, never authored twice", () => {
  const rows = [
    row({SOURCE_TYPE: "Header"}),
    row({SOURCE_TYPE: ""}),                       // Header by default
    row({SOURCE_TYPE: "Constant"}),
    row({SOURCE_TYPE: "Formula"}),
  ];
  const groups = mappingGroups(rows);
  assert.deepEqual(groups.map((g) => g.label), [
    "From a header — the name is looked up",
    "From somewhere else — no name involved",
  ]);
  assert.deepEqual(groups.map((g) => g.rows.length), [2, 2]);
});

test("a group with no rows is dropped along with its label", () => {
  // A label standing over nothing is a heading that promises rows and has none.
  const onlyHeaders = mappingGroups([row(), row()]);
  assert.deepEqual(onlyHeaders.map((g) => g.label),
                   ["From a header — the name is looked up"]);

  const onlyDerived = mappingGroups([row({SOURCE_TYPE: "Context"})]);
  assert.deepEqual(onlyDerived.map((g) => g.label),
                   ["From somewhere else — no name involved"]);

  assert.deepEqual(mappingGroups([]), []);
  assert.deepEqual(mappingGroups(null), []);
});
