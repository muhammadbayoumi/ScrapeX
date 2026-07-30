// THE GATE THAT DECIDES WHETHER THE OWNER MUST PASTE THE SCRIPT AGAIN.
//
// Everything here runs the REAL apps_script/StagingAppScript.txt — the exact
// characters that get pasted into the spreadsheet — not a copy of its logic. A
// test against a reimplementation would have passed all the way through the
// years this file refused a payload for being NEWER.
//
// It loads by evaluating the file: every top-level statement in it is a plain
// const or a function declaration, and every Google global (SpreadsheetApp,
// LockService, PropertiesService) is only ever touched INSIDE a function body,
// so the file parses and defines itself with no Apps Script runtime present.
// The two functions exercised below take their spreadsheet as an argument, so a
// twenty-line fake sheet is enough to watch them write.
//
// Run: node --test apps_script/tests/*.test.mjs
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const SOURCE = readFileSync(new URL("../StagingAppScript.txt", import.meta.url), "utf8");
const gas = new Function(SOURCE + `
  return {
    compatGeneration_, compatProblem_, reassemble_, writeTable_, headerDrift_,
    SYNC_PAYLOAD_VERSION, SYNC_PAYLOAD_COMPAT_VERSION, SYNC_PAYLOAD_COMPAT_MIN_VERSION,
    SYNC_GENERATION_OF_VERSION,
  };
`)();

/* One chunk as collectBatches_ hands it to reassemble_. */
function chunk(overrides = {}) {
  return {
    index: 1, total: 1,
    version: gas.SYNC_PAYLOAD_VERSION,
    compat: gas.SYNC_PAYLOAD_COMPAT_VERSION,
    header: ["id", "price"], rows: [["1", "10.00"]],
    scraped_at: "2026-07-30T10:00:00Z", row: 2,
    ...overrides,
  };
}

// ---- the friction that is being removed ------------------------------------

test("a NEWER content version is not a refusal — this is the whole point", () => {
  // The additive case: a ScrapeX release adds a column, stamps content 99, and
  // says "still generation 5". The pasted script has never heard of 99 and must
  // publish anyway. Under the old equality gate this was the re-paste.
  assert.equal(gas.compatProblem_(99, gas.SYNC_PAYLOAD_COMPAT_VERSION), "");
  const batch = gas.reassemble_([chunk({ version: 99 })]);
  assert.deepEqual(batch.rows, [["1", "10.00"]]);
});

test("an extra column in a newer payload lands in the sheet untouched", () => {
  const ss = fakeSpreadsheet();
  const header = ["id", "price", "brand_new_column"];
  gas.writeTable_(ss, "MADAR", header, [["1", "10.00", "arrived"]]);
  assert.deepEqual(ss.sheets.MADAR.written, [header, ["1", "10.00", "arrived"]]);
});

// ---- what the equality gate was protecting, kept -----------------------------

test("a newer GENERATION is refused, naming both numbers and which failed", () => {
  const problem = gas.compatProblem_(9, 9);
  assert.match(problem, /payload_compat_version 9 is newer/);
  assert.match(problem, new RegExp(`generation ${gas.SYNC_PAYLOAD_COMPAT_VERSION}`));
  assert.match(problem, /payload_version is 9/);
  assert.match(problem, new RegExp(`pasted at payload_version ${gas.SYNC_PAYLOAD_VERSION}`));
  assert.match(problem, /renamed, removed or given a new meaning/);
  assert.match(problem, /paste the current StagingAppScript\.txt/);
  assert.throws(() => gas.reassemble_([chunk({ version: 9, compat: 9 })]), /is newer than/);
});

test("an OLDER generation is refused differently — no paste can fix that batch", () => {
  const problem = gas.compatProblem_(1, null);
  assert.match(problem, /payload_compat_version 1 is older/);
  assert.match(problem, /before a column changed meaning/);
  // The remedies are opposite, so the two messages must not be confusable.
  assert.doesNotMatch(problem, /paste the current StagingAppScript/);
});

test("a version this script never heard of, declaring nothing, is refused", () => {
  // A producer newer than this file that forgot to stamp its generation. The one
  // outcome that must never happen is a guess.
  assert.equal(gas.compatGeneration_(42, undefined), null);
  assert.match(gas.compatProblem_(42, undefined), /payload_version 42 is unknown/);
});

// ---- the mailbox that predates the field ------------------------------------

test("batches sent before payload_compat_version existed still publish", () => {
  // _INBOX is full of these: stamped 6, carrying no generation at all. 6 was
  // additive over 5, so it IS generation 5, and the ledger is what knows that.
  // Get this wrong and every tab goes stale the day the script is pasted.
  for (const declared of [undefined, null, ""]) {
    assert.equal(gas.compatProblem_(6, declared), "", `version 6 with ${declared}`);
    assert.equal(gas.compatProblem_(5, declared), "", `version 5 with ${declared}`);
  }
  const batch = gas.reassemble_([chunk({ version: 6, compat: undefined })]);
  assert.deepEqual(batch.rows, [["1", "10.00"]]);
});

test("the ledger agrees with what the two constants claim", () => {
  assert.equal(gas.SYNC_GENERATION_OF_VERSION[String(gas.SYNC_PAYLOAD_VERSION)],
               gas.SYNC_PAYLOAD_COMPAT_VERSION);
  assert.ok(gas.SYNC_PAYLOAD_COMPAT_MIN_VERSION <= gas.SYNC_PAYLOAD_COMPAT_VERSION);
});

// ---- a reorder must stay safe, proved rather than trusted --------------------

test("a REORDERED header still lands with every value under its own name", () => {
  const ss = fakeSpreadsheet();
  const forward = ["id", "price", "currency"];
  const row = { id: "1", price: "10.00", currency: "SAR" };
  gas.writeTable_(ss, "MADAR", forward, [forward.map((c) => row[c])]);

  const reversed = [...forward].reverse();
  gas.writeTable_(ss, "MADAR", reversed, [reversed.map((c) => row[c])]);

  const [header, values] = ss.sheets.MADAR.written;
  assert.deepEqual(header, reversed);
  header.forEach((column, i) => assert.equal(values[i], row[column],
    `${column} must carry its own value wherever the header puts it`));
});

test("a reorder is not reported as columns appearing or vanishing", () => {
  const ss = fakeSpreadsheet();
  const forward = ["id", "price", "currency"];
  gas.writeTable_(ss, "MADAR", forward, [["1", "10.00", "SAR"]]);
  const drift = gas.writeTable_(ss, "MADAR", [...forward].reverse(), [["SAR", "10.00", "1"]]);
  assert.deepEqual(drift, { added: [], removed: [] });
});

// ---- and a column that appears or vanishes must be said out loud -------------

test("a column nobody has seen before is reported, not written in silence", () => {
  const ss = fakeSpreadsheet();
  gas.writeTable_(ss, "MADAR", ["id", "price"], [["1", "10.00"]]);
  const drift = gas.writeTable_(ss, "MADAR", ["id", "price", "price_trade"],
                                [["1", "10.00", "9.00"]]);
  assert.deepEqual(drift, { added: ["price_trade"], removed: [] });
});

test("a column that vanished is reported — the rename's second line of defence", () => {
  // If a rename ever slips through without the generation moving, the sheet
  // would keep the old column beside the new one, filling with nothing. The
  // gate is supposed to catch that; this is what catches it if the gate did not.
  const ss = fakeSpreadsheet();
  gas.writeTable_(ss, "MADAR", ["id", "brand_raw"], [["1", "LUXIFY"]]);
  const drift = gas.writeTable_(ss, "MADAR", ["id", "brand"], [["1", "LUXIFY"]]);
  assert.deepEqual(drift, { added: ["brand"], removed: ["brand_raw"] });
});

test("a brand-new tab reports no drift — every column in it IS the tab", () => {
  const ss = fakeSpreadsheet();
  const drift = gas.writeTable_(ss, "NEWSOURCE", ["id", "price"], [["1", "10.00"]]);
  assert.deepEqual(drift, { added: [], removed: [] });
});

test("a stray cell out to the right is not an unnamed column that vanished", () => {
  // getLastColumn() answers for the whole SHEET, so anything the owner typed
  // off past the table widens row 1 with blanks. Reported, they would be
  // nameless "column gone" entries and a permanent warning in _RUNS.
  const ss = fakeSpreadsheet();
  gas.writeTable_(ss, "MADAR", ["id", "price"], [["1", "10.00"]]);
  ss.sheets.MADAR.written[0] = ["id", "price", "", ""];  // a note two columns over

  const drift = gas.writeTable_(ss, "MADAR", ["id", "price"], [["1", "11.00"]]);
  assert.deepEqual(drift, { added: [], removed: [] });
});

/* The smallest thing writeTable_ can write to: it asks for a sheet by name,
 * inserts one when there is none, clears it, and sets one rectangular range.
 * Only the calls that function actually makes are implemented — a fake that
 * answered more would be inventing behaviour nothing here relies on. */
function fakeSpreadsheet() {
  const sheets = {};
  function makeSheet() {
    const sheet = {
      written: [],
      clear() { this.written = []; return this; },
      getLastRow() { return this.written.length; },
      getLastColumn() { return this.written.length ? this.written[0].length : 0; },
      setFrozenRows() { return this; },
      getRange(row, column, numRows, numColumns) {
        const target = this;
        return {
          setNumberFormat() { return this; },
          setValues(values) {
            for (let r = 0; r < values.length; r++) target.written[row - 1 + r] = values[r];
            return this;
          },
          getValues() {
            const out = [];
            for (let r = 0; r < numRows; r++) {
              out.push((target.written[row - 1 + r] || []).slice(column - 1, column - 1 + numColumns));
            }
            return out;
          },
        };
      },
    };
    return sheet;
  }
  return {
    sheets,
    getSheetByName(name) { return sheets[name] || null; },
    insertSheet(name) { sheets[name] = makeSheet(); return sheets[name]; },
  };
}
