// What one row of 4.DataMap SAYS, in words rather than in five enums.
//
// SPLIT OUT OF console.js SO IT CAN BE TESTED. That file reaches for the DOM in
// its first function and calls `start()` on its last line, so nothing in it can
// be imported by `node --test`. The sentence under an expanded mapping row is
// the part of that card with rules of its own — a verb per source type, two
// clauses that must be DROPPED rather than printed with an em dash, and a chain
// split into the steps it runs in — and a reader will believe every one of
// them. extension/tests/datamap-view.test.mjs is the reason this file exists.
//
// IT ANSWERS FOR THE ADD-IN, NOT FOR THE CELL. A blank SOURCE_TYPE is Header
// and a blank MATCH_MODE is Exact, so the card groups and reads a blank cell as
// the add-in will act on it. What it will NOT do is replace a value the sheet
// actually holds: an unrecognised mode is shown as typed, because
// `datamap-rules.js` is already reporting it and a card that quietly printed
// "Exact" over it would be arguing with the finding beside it.

import { SOURCE_TYPES, MATCH_MODES, TRANSFORM_SEPARATOR }
  from "./addin-contract.js";

const text = (row, name) => String(row?.[name] ?? "").trim();
const same = (a, b) => String(a).toUpperCase() === String(b).toUpperCase();

/**
 * The source type the add-in will USE.
 *
 * Blank is Header, and so is a spelling the add-in does not know: the lookup
 * finds nothing and the branch falls through to the default.
 * `datamap-rules.js` reads it exactly this way — a card that grouped an
 * unrecognised type under "somewhere else" would be describing a different
 * add-in from the one whose findings sit on the same screen.
 */
export function effectiveSourceType(row) {
  return SOURCE_TYPES.find((t) => same(t, text(row, "SOURCE_TYPE"))) || "Header";
}

/**
 * What to print under "Header match", which is only ever read for one type.
 *
 * Empty for every other type — the caller prints the em dash, because a dash is
 * a mark on a screen and not a value this module has any business inventing.
 */
export function headerMatch(row) {
  if (effectiveSourceType(row) !== "Header") return "";
  const named = text(row, "MATCH_MODE");
  if (!named) return "Exact";                       // a blank cell means Exact
  // Never over-write what is in the sheet. `options()` in console.js holds the
  // same line for the same reason: an unknown value is a FACT about the
  // workbook, and hiding it behind the default is how it stops being fixed.
  return MATCH_MODES.find((m) => same(m, named)) || named;
}

/** The chain, one step per element, in the order it runs. Empty when blank. */
export function transformSteps(row) {
  return text(row, "TRANSFORM_CHAIN")
    .split(TRANSFORM_SEPARATOR)
    .map((step) => step.trim())
    .filter(Boolean);
}

//: The verb each source type reads as. The phrasing is the design's, verbatim,
//: and it is the whole reason the sentence is worth showing: "Index" is a word
//: about the sheet, "comes from position" is a sentence about the data.
const VERBS = {
  Header: "comes from the column",
  Index: "comes from position",
  Constant: "is always",
  Context: "comes from the run's",
  Formula: "is computed as",
};

/**
 * One row, as the parts of a sentence.
 *
 * A CLAUSE WITH NOTHING TO SAY IS DROPPED, never printed with an em dash in it.
 * A constant reads `CURRENCY is always SAR` — no `matched`, no `, then` — and
 * `matched —` would be a sentence about nothing in a panel whose only job is to
 * be read as one. `match` and `steps` are empty in exactly those cases, so the
 * caller appends the clause or does not.
 */
export function mappingSentence(row) {
  return {
    target: text(row, "TARGET_ATTRIBUTE_KEY"),
    verb: VERBS[effectiveSourceType(row)],
    source: text(row, "SOURCE_EXPRESSION"),
    match: headerMatch(row),
    steps: transformSteps(row),
  };
}

/**
 * The rows in two groups, by where the value comes from.
 *
 * A constant is not a mapping in the same sense as a header lookup — one is a
 * name that has to be found in a file that may not carry it, the other cannot
 * fail to resolve — and a flat list said nothing about the difference.
 *
 * Membership is DERIVED from the source type and never authored twice, and a
 * group with no rows is dropped along with its label rather than left standing
 * over nothing.
 */
export function mappingGroups(rows) {
  const groups = [
    {label: "From a header — the name is looked up", rows: []},
    {label: "From somewhere else — no name involved", rows: []},
  ];
  for (const row of rows || []) {
    groups[effectiveSourceType(row) === "Header" ? 0 : 1].rows.push(row);
  }
  return groups.filter((group) => group.rows.length);
}
