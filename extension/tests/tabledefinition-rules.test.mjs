// One TableDefinition row, judged as the add-in judges it.
//
// Every expectation is the add-in's behaviour read out of its C#, not a
// preference. Where a rule looks strange — a blank strategy that means
// MergeUpsert, a switched-off parent that behaves like a missing one — the
// strange part is the add-in's and the test says so, because that is exactly the
// kind of rule someone later "corrects" into something more reasonable.

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkTableDefinitionRow, hasPrimaryKey, tableSwitchedOff }
  from "../tabledefinition-rules.js";

/** A row with nothing wrong with it — the control for every test below. */
const sound = (over = {}) => ({
  ENTITY_KEY: "T_BITUMEN",
  DISPLAY_NAME: "Bitumen",
  ENTITY_TYPE: "COST",
  LICENSE_TIER: "Free",
  IS_ACTIVE: "TRUE",
  IS_VISIBLE: "TRUE",
  STORAGE_STRATEGY: "MergeUpsert",
  PARENT_KEY: "",
  VIEW_MODE: "Table",
  BUSINESS_DOMAIN: "MATERIAL",
  UX_CONFIG: "",
  SYS_CONFIG: "",
  RIBBON_CONFIG: "",
  EXPORT_CONFIG: "",
  ...over,
});

/** A key column for T_BITUMEN, so the MergeUpsert rule is satisfied by default. */
const withKey = [{ENTITY_KEY: "T_BITUMEN", ATTRIBUTE_KEY: "CODE", IS_PK: "TRUE"}];

const codes = (found) => found.map((f) => f.code);
const fields = (found) => found.map((f) => f.field);
const worst = (found) => found.map((f) => f.severity);

test("a sound row produces nothing at all", () => {
  assert.deepEqual(checkTableDefinitionRow(sound(), [], withKey), []);
});

test("no key rejects the row and says nothing else", () => {
  const found = checkTableDefinitionRow(sound({ENTITY_KEY: ""}), [], withKey);
  // The add-in stops at this one (yield break), so a second complaint here would
  // be the Console describing checks that never run.
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Critical");
  assert.equal(found[0].field, "ENTITY_KEY");
});

test("a repeated key says which row wins, because edits go to the wrong one", () => {
  const found = checkTableDefinitionRow(
    sound(), [sound({DISPLAY_NAME: "Bitumen (old)"})], withKey);
  const dup = found.filter((f) => f.code === "DUPLICATE");
  assert.equal(dup.length, 1);
  assert.match(dup[0].detail, /FIRST row is used/);
});

test("a missing name does NOT fall back to the key, and says so", () => {
  const found = checkTableDefinitionRow(sound({DISPLAY_NAME: ""}), [], withKey);
  const named = found.filter((f) => f.field === "DISPLAY_NAME");
  assert.equal(named.length, 1);
  // The whole point: the fallback everyone assumes exists is dead code.
  assert.match(named[0].detail, /BLANK label/);
});

// ---------------------------------------------------------------------------
// The worst fault this sheet can carry, and the one nothing reports.
// ---------------------------------------------------------------------------

test("MergeUpsert with no key column duplicates the file on every sync", () => {
  const found = checkTableDefinitionRow(sound(), [], []);   // no SchemaRule rows
  const fatal = found.filter((f) => f.code === "NO_CONFLICT_TARGET");
  assert.equal(fatal.length, 1);
  assert.equal(fatal[0].severity, "Error");
  assert.match(fatal[0].detail, /EVERY SYNC APPENDS/);
});

test("and a BLANK strategy is MergeUpsert, so it carries the same fault", () => {
  // The case a reader is likeliest to miss: blank is not "no strategy", it is
  // MergeUpsert — chosen deliberately, because enum zero would be ReplaceAll.
  const found = checkTableDefinitionRow(
    sound({STORAGE_STRATEGY: ""}), [], []);
  assert.ok(codes(found).includes("NO_CONFLICT_TARGET"),
    "a blank strategy stopped being treated as MergeUpsert");
  assert.match(found.find((f) => f.code === "NO_CONFLICT_TARGET").detail,
    /blank strategy means MergeUpsert/);
});

test("a key column anywhere on the sheet settles it", () => {
  assert.deepEqual(
    checkTableDefinitionRow(sound(), [], withKey).filter(
      (f) => f.code === "NO_CONFLICT_TARGET"), []);
  // And the helper the workflow will ask directly, including the case-folding
  // the add-in does throughout.
  assert.equal(hasPrimaryKey("t_bitumen", withKey), true);
  assert.equal(hasPrimaryKey("T_OTHER", withKey), false);
});

test("a key column that is switched OFF is still a key", () => {
  // IS_PK is what the DDL reads; there is no IS_ACTIVE on 2.SchemaRule at all.
  // Inventing one here would refuse a table the add-in is happy with.
  assert.equal(hasPrimaryKey("T_BITUMEN", [
    {ENTITY_KEY: "T_BITUMEN", ATTRIBUTE_KEY: "CODE", IS_PK: "نعم"}]), true,
  "the Arabic spelling for true stopped counting");
});

test("Append and ReplaceAll each say what they cost", () => {
  const replace = checkTableDefinitionRow(
    sound({STORAGE_STRATEGY: "ReplaceAll"}), [], withKey);
  assert.match(replace.find((f) => f.field === "STORAGE_STRATEGY").detail,
    /DELETES every row/);

  const append = checkTableDefinitionRow(
    sound({STORAGE_STRATEGY: "Append"}), [], withKey);
  const note = append.find((f) => f.field === "STORAGE_STRATEGY");
  assert.equal(note.severity, "Info");
  assert.match(note.detail, /keeps its OLD value/);
  // Append needs no key, so the fatal rule must not fire on it.
  assert.deepEqual(append.filter((f) => f.code === "NO_CONFLICT_TARGET"), []);
});

test("an unreadable strategy is not coerced to the first enum value", () => {
  const found = checkTableDefinitionRow(
    sound({STORAGE_STRATEGY: "Replace All"}), [], withKey);
  const bad = found.find((f) => f.field === "STORAGE_STRATEGY"
    && f.code === "INVALID_VALUE");
  assert.ok(bad, "an unknown strategy stopped being reported");
  assert.match(bad.detail, /would delete everything/);
});

// ---------------------------------------------------------------------------
// Inheritance, where two different faults look identical from the sheet.
// ---------------------------------------------------------------------------

test("a table cannot be its own parent", () => {
  const found = checkTableDefinitionRow(
    sound({PARENT_KEY: "t_bitumen"}), [], withKey);
  const loop = found.filter((f) => f.code === "ERR_CIRCULAR");
  assert.equal(loop.length, 1);
  assert.equal(loop[0].severity, "Critical");
});

test("a parent that is switched off is reported differently from a missing one", () => {
  const missing = checkTableDefinitionRow(
    sound({PARENT_KEY: "T_NOWHERE"}), [], withKey);
  assert.match(missing.find((f) => f.field === "PARENT_KEY").detail,
    /Nothing is named/);

  const off = checkTableDefinitionRow(
    sound({PARENT_KEY: "T_BASE"}),
    [sound({ENTITY_KEY: "T_BASE", IS_ACTIVE: "FALSE"})], withKey);
  const said = off.find((f) => f.field === "PARENT_KEY");
  assert.match(said.detail, /switched off/,
    "the harder case reads as a plain missing parent");
  assert.match(said.detail, /ACTIVE rows only/);
});

test("inheritance is one level, and a grandparent is called out", () => {
  const found = checkTableDefinitionRow(
    sound({PARENT_KEY: "T_MID"}),
    [sound({ENTITY_KEY: "T_MID", PARENT_KEY: "T_ROOT"})], withKey);
  const note = found.find((f) => f.field === "PARENT_KEY");
  assert.equal(note.severity, "Info");
  assert.match(note.detail, /applied ONCE/);
});

test("switching a table off orphans the tables that inherit from it", () => {
  const found = checkTableDefinitionRow(
    sound({IS_ACTIVE: "FALSE"}),
    [sound({ENTITY_KEY: "T_CHILD", PARENT_KEY: "T_BITUMEN"})], withKey);
  const orphans = found.filter((f) => f.field === "IS_ACTIVE"
    && f.severity === "Warning");
  assert.equal(orphans.length, 1);
  assert.match(orphans[0].detail, /T_CHILD/,
    "the message does not name the tables that just lost their parent");
});

test("hidden is not the same as off", () => {
  const hidden = checkTableDefinitionRow(
    sound({IS_VISIBLE: "FALSE"}), [], withKey);
  assert.match(hidden.find((f) => f.field === "IS_VISIBLE").detail,
    /still syncs/);
  assert.equal(tableSwitchedOff(sound({IS_VISIBLE: "FALSE"})), false);
  assert.equal(tableSwitchedOff(sound({IS_ACTIVE: "FALSE"})), true);
  // A blank IS_ACTIVE means LIVE on this sheet. Reading it as "off" would make
  // the Console call every incomplete row disabled.
  assert.equal(tableSwitchedOff(sound({IS_ACTIVE: ""})), false);
});

// ---------------------------------------------------------------------------
// The four JSON bags.
// ---------------------------------------------------------------------------

test("a broken bag loses ALL of its settings, not the broken part", () => {
  const found = checkTableDefinitionRow(
    sound({UX_CONFIG: '{"TabColor": '}), [], withKey);
  const bad = found.filter((f) => f.field === "UX_CONFIG");
  assert.equal(bad.length, 1);
  assert.equal(bad[0].severity, "Error");
  assert.match(bad[0].detail, /EVERY setting in it/);
});

test("but a trailing comma is NOT broken — the add-in's parser accepts it", () => {
  // Found by running these rules against the owner's real workbook: three cells
  // came back as errors and all three were fine. Every bag in the product is
  // parsed by Newtonsoft, which takes a trailing comma; JSON.parse does not.
  // This is the exact text of one of those cells.
  const real = `{
"HeaderText":"الهيئة العامة للطرق والكباري",
"HeaderStyle":"TableHeader",
}`;
  const found = checkTableDefinitionRow(
    sound({EXPORT_CONFIG: real}), [], withKey);

  assert.equal(found.length, 1, "the tolerated cell produced more than a note");
  assert.equal(found[0].severity, "Info",
    "a cell the add-in reads every day is being reported as a fault");
  assert.match(found[0].detail, /trailing comma/);
  // And the settings inside it are still read, so HeaderStyle is still checked.
  const wrongStyle = checkTableDefinitionRow(
    sound({EXPORT_CONFIG: '{"HeaderStyle":"Fancy",}'}), [], withKey);
  assert.ok(wrongStyle.some((f) => f.severity === "Error"),
    "tolerating the comma stopped the values inside being checked");
});

test("a comment is tolerated too, and a URL inside a string is not a comment", () => {
  const commented = checkTableDefinitionRow(
    sound({SYS_CONFIG: `{ // how many rows the teaser shows
"TeaserRowCount": 5 }`}),
    [], withKey);
  assert.equal(commented.length, 1);
  assert.equal(commented[0].severity, "Info");

  // The relaxation strips `//`, and a value like "https://x" contains one. If
  // that were cut, a perfectly good bag would become unreadable.
  const url = checkTableDefinitionRow(
    sound({SYS_CONFIG: '{"TeaserText": "see https://example.com/x"}'}), [], withKey);
  assert.deepEqual(url, [], "a URL in a string was mistaken for a comment");
});

test("a misspelt key is kept and ignored, and the accepted set is offered", () => {
  const found = checkTableDefinitionRow(
    sound({SYS_CONFIG: '{"AllowEdits": true}'}), [], withKey);
  const said = found.find((f) => f.field === "SYS_CONFIG");
  assert.equal(said.code, "UNKNOWN_KEY");
  assert.match(said.fix, /AllowEdit/);
});

test("the closed lists inside the bags are checked too", () => {
  const found = checkTableDefinitionRow(
    sound({UX_CONFIG: '{"Direction": "RTL"}',
      RIBBON_CONFIG: '{"ControlSize": "Huge"}',
      EXPORT_CONFIG: '{"HeaderStyle": "Note"}'}), [], withKey);
  assert.deepEqual(fields(found), ["RIBBON_CONFIG"],
    "a valid Direction or HeaderStyle was refused, or a bad ControlSize passed");
  assert.equal(found[0].severity, "Error");
});

test("every finding carries a code the add-in would print", () => {
  const messy = checkTableDefinitionRow(
    sound({DISPLAY_NAME: "", ENTITY_TYPE: "COSTS", STORAGE_STRATEGY: ""}),
    [], []);
  assert.ok(messy.length >= 3);
  assert.ok(!worst(messy).includes(undefined));
  for (const found of messy) assert.ok(found.code, `${found.field} has no code`);
});
