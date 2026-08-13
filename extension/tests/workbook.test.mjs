// The Console's rules, driven with the workbook's own worst cases.
//
// The fixtures below are not invented. They are the shapes measured in the
// owner's live configuration workbook on 2026-08-12 — fifteen profiles nothing
// references, one mapping pointing at an attribute that does not exist — plus
// the shapes the add-in's C# says are dangerous and the file happens not to
// contain yet.

import { test } from "node:test";
import assert from "node:assert/strict";

import { SHEETS, TAB_NAMES, parseWorkbook, vocabularies, inspect }
  from "../workbook.js";
import { readBoolean, BOOLEAN_DEFAULTS, TRUE_SPELLINGS, FALSE_SPELLINGS,
         KNOWN_VOCABULARIES, SHEET_GIDS, SOURCE_TYPES, TRANSFORMS }
  from "../addin-contract.js";

/**
 * A `values.batchGet` answer, built the way Sheets really builds one.
 *
 * TRAILING BLANKS ARE TRUNCATED. Sheets returns a SHORT array when a row's last
 * cells are empty — a fourteen-column sheet yields three elements — so this
 * helper truncates too. A fixture that padded every row would let a
 * `row[11]`-style read pass here and fail against Google.
 */
function batch(tabs) {
  return Object.entries(tabs).map(([tab, rows]) => ({
    range: `${tab}!A1:Z1000`,
    values: rows.map((row) => {
      const cells = [...row];
      while (cells.length && !String(cells.at(-1) ?? "").trim()) cells.pop();
      return cells;
    }),
  }));
}

/** Header rows straight from the spec, so a fixture cannot drift from it. */
const header = (tab) => SHEETS.find((s) => s.tab === tab).columns;

/** A workbook that is entirely correct — the control for every test below. */
function sound() {
  return batch({
    "1.TableDefinition": [header("1.TableDefinition"),
      ["T_DIESEL", "Diesel", "COST", "Free", "True", "", "ReplaceAll"]],
    "2.SchemaRule": [header("2.SchemaRule"),
      ["T_DIESEL", "Price", "Price", "1", "", "PRICE", "DECIMAL", "True"],
      ["T_DIESEL", "Name", "Name", "2", "", "NAME", "TEXT"]],
    "3.DataSource": [header("3.DataSource"),
      ["SRC_DIESEL", "T_DIESEL", "P_DIESEL", "EG",
       "https://docs.google.com/spreadsheets/d/e/2PACX-1vAAA/pub?gid=1&single=true&output=tsv"]],
    "4.DataMap": [header("4.DataMap"),
      ["P_DIESEL", "Price", "Header", "Exact", "price"],
      ["P_DIESEL", "Name", "Header", "Exact", "name"]],
    "5.ExportViews": [header("5.ExportViews")],
    "6.RibbonControls": [header("6.RibbonControls")],
  });
}

const problems = (ranges) => inspect(parseWorkbook(ranges));
const kinds = (ranges) => problems(ranges).map((p) => p.kind);

// ---------------------------------------------------------------------------
// Reading the sheet at all
// ---------------------------------------------------------------------------

test("a correct workbook yields nothing to say", () => {
  assert.deepEqual(problems(sound()), [],
    "the checker invented a problem in a workbook that has none, which is the "
    + "fastest way to teach the owner to ignore it");
});

test("a truncated row keeps its named columns and does not invent empties", () => {
  const {sheets} = parseWorkbook(sound());
  const row = sheets["1.TableDefinition"].rows[0];

  assert.equal(row.ENTITY_KEY, "T_DIESEL");
  assert.equal(row.STORAGE_STRATEGY, "ReplaceAll");
  // Sheets truncated everything after it; the parser must read "" and not
  // undefined, because every rule below compares against a string.
  assert.equal(row.PARENT_KEY, "", "a trailing blank came back as undefined");
  assert.equal(row.EXPORT_CONFIG, "");
});

test("row numbers match what the owner sees in Google Sheets", () => {
  const {sheets} = parseWorkbook(sound());
  // Header is row 1, so the first data row is 2. A checker that named row 1
  // would send the owner to the header every time.
  assert.equal(sheets["2.SchemaRule"].rows[0]._row, 2);
  assert.equal(sheets["2.SchemaRule"].rows[1]._row, 3);
});

test("a wholly blank row is not a row", () => {
  const ranges = sound();
  ranges[0].values.push([], ["", "  ", ""]);
  assert.equal(parseWorkbook(ranges).sheets["1.TableDefinition"].rows.length, 1);
});

test("a missing tab is named, not silently skipped", () => {
  const ranges = sound().filter((r) => !r.range.startsWith("4.DataMap"));
  const workbook = parseWorkbook(ranges);

  assert.deepEqual(workbook.missing, ["4.DataMap"]);
  assert.ok(problems(ranges).some((p) => p.kind === "tab missing"),
    "a workbook with a renamed tab reported no problem — the Console would "
    + "then check five sheets and call the sixth correct");
});

test("every tab this repository names carries a gid the add-in compiled in", () => {
  // Not a test of the workbook: a test that the two lists in this repository
  // agree. They are edited in different files for different reasons.
  assert.deepEqual(Object.keys(SHEET_GIDS).sort(), [...TAB_NAMES].sort());
});

// ---------------------------------------------------------------------------
// References that cannot resolve
// ---------------------------------------------------------------------------

test("a source pointing at an entity that does not exist", () => {
  const ranges = sound();
  ranges[2].values[1][1] = "T_TYPO";

  const found = problems(ranges).filter((p) => p.kind === "unknown entity");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "broken");
  assert.equal(found[0].row, 2, "the owner is not told which row to open");
  assert.match(found[0].detail, /T_TYPO/);
});

test("MEASURED IN THE LIVE FILE — a mapping targeting an attribute that is not there", () => {
  // 4.DataMap row 7 of the owner's own workbook: the CHAOS_PROF profile maps a
  // "Date" column, and T_CHAOS has no such attribute. The add-in warns and then
  // SILENTLY DROPS the row — "its data will be lost" is its own wording — and
  // because the finding is only a Warn, the sync completes and reports success.
  const ranges = sound();
  ranges[3].values.push(["P_DIESEL", "Date", "Header", "Exact", "date"]);

  const found = problems(ranges).filter((p) => p.kind === "attribute not in schema");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "broken");
  assert.match(found[0].detail, /Date/);
  assert.match(found[0].detail, /nowhere to land/);
});

test("a mapping is judged against ITS OWN entity's attributes, not every attribute", () => {
  // The trap: "Price" exists — on a different table. A checker that gathered
  // every attribute in the workbook into one set would pass this and let the
  // owner ship a mapping that drops its column.
  const ranges = sound();
  ranges[0].values.push(["T_OTHER", "Other", "COST", "Free", "True", "", "ReplaceAll"]);
  ranges[1].values.push(["T_OTHER", "Tonnage", "Tonnage", "1", "", "QTY", "DECIMAL"]);
  ranges[2].values.push(["SRC_OTHER", "T_OTHER", "P_OTHER", "EG",
                         "https://docs.google.com/spreadsheets/d/e/2PACX-1vB/pub?gid=2&single=true&output=tsv"]);
  ranges[3].values.push(["P_OTHER", "Price", "Header", "Exact", "price"]);

  const found = problems(ranges).filter((p) => p.kind === "attribute not in schema");
  assert.equal(found.length, 1, "an attribute belonging to another table was accepted");
  assert.match(found[0].detail, /T_OTHER/);
});

test("MEASURED IN THE LIVE FILE — fifteen profiles nothing references", () => {
  // The other direction, and the add-in treats the two completely differently:
  // this one only wastes the mappings. Reported as `unused`, deliberately, so
  // it cannot crowd out the ones that break a table.
  const ranges = sound();
  ranges[3].values.push(["P_NOBODY_ASKED", "Price", "Header", "Exact", "x"],
                        ["P_NOBODY_ASKED", "Name", "Header", "Exact", "y"]);

  const found = problems(ranges).filter((p) => p.kind === "profile nothing references");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "unused", "an unused profile was reported as broken");
  assert.match(found[0].detail, /2 mappings/);
});

test("a source naming a profile that has NO mappings is broken, not unused", () => {
  // The add-in hard-fails this source — IngestionResult.Fail("No mappings for
  // profile X") — so the whole table is empty. The severity must say so.
  const ranges = sound();
  ranges[2].values.push(["SRC_LONELY", "T_DIESEL", "P_NOT_DEFINED", "EG",
                         "https://docs.google.com/spreadsheets/d/e/2PACX-1vC/pub?gid=3&single=true&output=tsv"]);

  const found = problems(ranges).filter((p) => p.kind === "profile has no mappings");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "broken",
    "a source that cannot ingest at all was filed beside a tidy-up");
});

test("a duplicate key names the row it collides with", () => {
  const ranges = sound();
  ranges[2].values.push(["SRC_DIESEL", "T_DIESEL", "P_DIESEL", "EG",
                         "https://docs.google.com/spreadsheets/d/e/2PACX-1vD/pub?gid=4&single=true&output=tsv"]);

  const found = problems(ranges).filter((p) => p.kind === "duplicate key");
  assert.equal(found.length, 1);
  assert.match(found[0].detail, /row 2/, "the owner is not told where the twin is");
});

// ---------------------------------------------------------------------------
// The address the add-in actually fetches
// ---------------------------------------------------------------------------

test("a published URL with no output format", () => {
  const ranges = sound();
  ranges[2].values[1][4] =
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vAAA/pub?gid=1&single=true";

  const found = problems(ranges).filter(
    (p) => p.kind === "published address with no format");
  assert.equal(found.length, 1);
  assert.match(found[0].detail, /output=tsv/);
});

test("the link from the browser's address bar is refused with the reason", () => {
  // The commonest mistake by far, and it fails in the least helpful way: the
  // add-in receives a web page and reports a parse error about the DATA.
  const ranges = sound();
  ranges[2].values[1][4] =
    "https://docs.google.com/spreadsheets/d/1AbCdEf/edit#gid=0";

  const found = problems(ranges).filter(
    (p) => p.kind === "an edit link, not a data address");
  assert.equal(found.length, 1);
  assert.match(found[0].detail, /Publish to web/);
});

test("a source with no address at all", () => {
  const ranges = sound();
  ranges[2].values[1][4] = "";
  assert.ok(kinds(ranges).includes("no address"));
});

// ---------------------------------------------------------------------------
// Severity, and the order the owner reads
// ---------------------------------------------------------------------------

test("what breaks a table is listed before what merely sits unused", () => {
  const ranges = sound();
  ranges[3].values.push(["P_NOBODY", "Price", "Header", "Exact", "x"]);   // unused
  ranges[2].values[1][1] = "T_TYPO";                                      // broken

  const order = problems(ranges).map((p) => p.severity);
  assert.equal(order[0], "broken");
  assert.ok(order.lastIndexOf("broken") < order.indexOf("unused"),
    "a tidy-up was printed above something that empties a table");
});

// ---------------------------------------------------------------------------
// The drop-downs
// ---------------------------------------------------------------------------

test("the lists offer what the ADD-IN accepts, not what the file happens to use", () => {
  const workbook = parseWorkbook(sound());
  const withCode = vocabularies(workbook, KNOWN_VOCABULARIES);
  const fromFileAlone = vocabularies(workbook);

  // The file uses one source type. The add-in accepts five.
  assert.deepEqual(fromFileAlone.sourceTypes, ["Header"]);
  assert.deepEqual(withCode.sourceTypes, SOURCE_TYPES);
  assert.ok(withCode.sourceTypes.includes("Formula"),
    "a legal value nobody has typed yet would be refused by the Console");
});

test("a list derived from use alone says so", () => {
  const workbook = parseWorkbook(sound());

  assert.ok(vocabularies(workbook).derivedFromUseAlone.includes("sourceTypes"),
    "the Console cannot tell the owner which of its lists are guesses");
  assert.ok(!vocabularies(workbook, KNOWN_VOCABULARIES)
    .derivedFromUseAlone.includes("sourceTypes"));
});

test("attributes are offered per entity, because a mapping targets its own", () => {
  const ranges = sound();
  ranges[0].values.push(["T_OTHER", "Other", "COST", "Free", "True", "", "ReplaceAll"]);
  ranges[1].values.push(["T_OTHER", "Tonnage", "Tonnage", "1", "", "QTY", "DECIMAL"]);

  const {attributesByEntity} = vocabularies(parseWorkbook(ranges));
  assert.deepEqual(attributesByEntity.T_DIESEL, ["Name", "Price"]);
  assert.deepEqual(attributesByEntity.T_OTHER, ["Tonnage"]);
});

test("entity and profile keys come from the workbook, so they cannot go stale", () => {
  const list = vocabularies(parseWorkbook(sound()));
  assert.deepEqual(list.entityKeys, ["T_DIESEL"]);
  assert.deepEqual(list.profileKeys, ["P_DIESEL"]);
});

// ---------------------------------------------------------------------------
// The boolean that fails open
// ---------------------------------------------------------------------------

test("every spelling the add-in's converter accepts, in both languages", () => {
  for (const yes of TRUE_SPELLINGS) {
    assert.equal(readBoolean(yes, "untouched"), true, `${yes} did not read as true`);
    assert.equal(readBoolean(yes.toUpperCase(), "untouched"), true,
      `${yes} is case-sensitive here and is not in the add-in`);
  }
  for (const no of FALSE_SPELLINGS) {
    assert.equal(readBoolean(no, "untouched"), false, `${no} did not read as false`);
  }
});

test("A BLANK IS_ACTIVE MEANS THE ROW IS LIVE — the most consequential default", () => {
  const fallback = BOOLEAN_DEFAULTS["3.DataSource"].IS_ACTIVE;
  assert.equal(fallback, true);
  assert.equal(readBoolean("", fallback), true,
    "an empty IS_ACTIVE was read as off. It is ON, and a Console that showed "
    + "it as off would tell the owner a source is disabled while it syncs");
});

test("AND SO DOES A TYPO — the failure is open, not closed", () => {
  // SmartConverter returns null for anything it does not know; the TSV parser
  // assigns only when a conversion produced a value; so the property keeps its
  // declared default. `Active` switches a table ON and records nothing.
  const fallback = BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE;
  for (const typo of ["Active", "X", "TRUE!", "yes please", "١"]) {
    assert.equal(readBoolean(typo, fallback), true,
      `"${typo}" did not fall back to the declared default`);
  }
});

test("the same blank means the opposite on SchemaRule, and that is not a bug", () => {
  assert.equal(BOOLEAN_DEFAULTS["2.SchemaRule"].IS_PK, false);
  assert.equal(readBoolean("", BOOLEAN_DEFAULTS["2.SchemaRule"].IS_PK), false);
  // Same column name, opposite meaning, one sheet apart. A single shared
  // default would be wrong on one of them.
  assert.notEqual(BOOLEAN_DEFAULTS["2.SchemaRule"].IS_PK,
                  BOOLEAN_DEFAULTS["1.TableDefinition"].IS_ACTIVE);
});

test("no spelling counts as both true and false", () => {
  const both = TRUE_SPELLINGS.filter((s) => FALSE_SPELLINGS.includes(s));
  assert.deepEqual(both, []);
});

// ---------------------------------------------------------------------------
// The contract's own shape
// ---------------------------------------------------------------------------

test("the transform list is the add-in's, and it is chained with a pipe", () => {
  assert.equal(TRANSFORMS.length, 10);
  assert.ok(TRANSFORMS.includes("JSON_EXTRACT"));
  // The separator matters as much as the names: a comma-separated chain parses
  // as one unknown transform and is dropped whole.
  assert.ok(!TRANSFORMS.some((t) => t.includes("|")));
});

// ---------------------------------------------------------------------------
// A blank PROFILE_KEY is not an absent one.
//
// THIRTEEN OF THE FIFTEEN ORPHANS I FIRST REPORTED WERE MINE. The add-in
// resolves an empty PROFILE_KEY — and the literal "DEFAULT" — to the row's
// TARGET_ENTITY_KEY, then looks up DataMap under that name. My checker did not
// know, so every source that leaves the column blank looked like a source
// referencing nothing, and every profile named after an entity looked orphaned.
//
// Reporting thirteen problems that are not problems is how a checker teaches
// its owner to stop reading it — which costs more than the two it found.
// ---------------------------------------------------------------------------

test("a source with a BLANK profile still names one — its entity", () => {
  const ranges = sound();
  // The shape the live workbook uses more than any other: no profile column.
  ranges[2].values[1][2] = "";
  // values[1] and [2]; values[0] is the header row, and writing over it makes
  // the whole sheet unparseable — which is how the first draft of this test
  // passed while asserting nothing.
  ranges[3].values[1][0] = "T_DIESEL";
  ranges[3].values[2][0] = "T_DIESEL";

  const orphans = problems(ranges).filter(
    (p) => p.kind === "profile nothing references");
  assert.deepEqual(orphans, [],
    "a profile named after the entity was reported as orphaned, because the "
    + "blank PROFILE_KEY beside it was read as 'no profile' rather than as "
    + "'the default one'");
});

test('the literal "DEFAULT" resolves the same way, in any case', () => {
  for (const spelling of ["DEFAULT", "default", "Default"]) {
    const ranges = sound();
    ranges[2].values[1][2] = spelling;
    ranges[3].values[1][0] = "T_DIESEL";
    ranges[3].values[2][0] = "T_DIESEL";

    assert.deepEqual(
      problems(ranges).filter((p) => p.kind === "profile nothing references"), [],
      `"${spelling}" was not treated as the default profile`);
  }
});

test("and the mapping's target is still judged against the right entity", () => {
  // The resolution must reach BOTH readings of PROFILE_KEY. If only the orphan
  // check learned it, a blank-profile source would stop reporting orphans and
  // start missing attributes that do not exist.
  const ranges = sound();
  ranges[2].values[1][2] = "";
  // values[1] and [2]; values[0] is the header row, and writing over it makes
  // the whole sheet unparseable — which is how the first draft of this test
  // passed while asserting nothing.
  ranges[3].values[1][0] = "T_DIESEL";
  ranges[3].values[2][0] = "T_DIESEL";
  ranges[3].values.push(["T_DIESEL", "NotAColumn", "Header", "Exact", "x"]);

  const found = problems(ranges).filter(
    (p) => p.kind === "attribute not in schema");
  assert.equal(found.length, 1,
    "a mapping under a defaulted profile is no longer checked at all");
  assert.match(found[0].detail, /NotAColumn/);
});

test("a profile named after nothing at all is STILL an orphan", () => {
  // The correction must not swallow the two real ones. GARB and GARB2 in the
  // owner's file match no entity and no source names them.
  const ranges = sound();
  ranges[3].values.push(["GARB", "Price", "Header", "Exact", "x"]);

  const orphans = problems(ranges).filter(
    (p) => p.kind === "profile nothing references");
  assert.equal(orphans.length, 1);
  assert.match(orphans[0].detail, /GARB/);
});
