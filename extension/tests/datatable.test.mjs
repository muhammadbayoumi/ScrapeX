// The Data page's reading of a /api/table payload, driven with hostile input.
//
// Everything here is about a WRONG NUMBER or a WRONG SENTENCE reaching the
// owner. Layout is not tested and should not be.

import test from "node:test";
import assert from "node:assert/strict";

import { columnsFrom, foldControl, sourceKeyFrom, summarise, truncationNotice }
  from "../datatable.js";

const PAYLOAD = {
  source_key: "SAMEHGABRIEL",
  columns: [{key: "product_name_ar", label: "الاسم"},
            {key: "price", label: "Price"},
            {key: "currency", label: "Currency"}],
  rows: [{offer_id: 1}, {offer_id: 2}],
  total: 2, returned: 2, truncated: false,
  folded: false, foldable: true, bilingual: false,
};

// ---- columns ---------------------------------------------------------------

test("the columns are the payload's, in the payload's order", () => {
  const columns = columnsFrom(PAYLOAD);
  assert.deepEqual(columns.map((c) => c.field),
                   ["product_name_ar", "price", "currency"]);
  assert.deepEqual(columns.map((c) => c.title), ["الاسم", "Price", "Currency"]);
});

test("EVERY column renders as plaintext, because every value was scraped", () => {
  // A formatter that interpreted markup would let a shop's product name run
  // script in the owner's browser. This is the assertion that says so.
  for (const column of columnsFrom(PAYLOAD)) {
    assert.equal(column.formatter, "plaintext", column.field);
  }
});

test("a column with no label falls back to its key rather than rendering blank", () => {
  const [column] = columnsFrom({columns: [{key: "price_trade"}]});
  assert.equal(column.title, "price_trade");
});

test("a column with no key is dropped, not drawn as an empty stripe", () => {
  assert.deepEqual(columnsFrom({columns: [{label: "Ghost"}, {key: "price"}]})
                     .map((c) => c.field), ["price"]);
});

test("a payload with no columns at all yields none, and does not throw", () => {
  for (const input of [{}, {columns: null}, null, undefined]) {
    assert.deepEqual(columnsFrom(input), []);
  }
});

// ---- the summary and the bound ---------------------------------------------

test("a whole table says its total", () => {
  assert.equal(summarise(PAYLOAD), "2 rows");
});

test("A PREFIX SAYS IT IS ONE. This is the failure the row cap exists for", () => {
  const capped = {...PAYLOAD, total: 91234, returned: 20000, rows: [],
                  truncated: true};
  assert.equal(summarise(capped), "20000 of 91234 rows");
  assert.match(truncationNotice(capped), /PREFIX/);
  assert.match(truncationNotice(capped), /20000/);
});

test("nothing is said about truncation when the engine did not truncate", () => {
  assert.equal(truncationNotice(PAYLOAD), "");
  assert.equal(truncationNotice({}), "");
});

test("the notice is driven by the engine's flag, not by a row count", () => {
  // Deriving it from `rows.length >= 20000` would re-decide upstream's own
  // bound here, and the two would disagree the day the cap moves.
  assert.equal(truncationNotice({truncated: true, returned: 3}).length > 0, true);
  assert.equal(truncationNotice({truncated: false, returned: 20000}), "");
});

test("folding and bilingual are stated, and only when true", () => {
  assert.equal(summarise({...PAYLOAD, folded: true}), "2 rows · variants folded");
  assert.equal(summarise({...PAYLOAD, bilingual: true}), "2 rows · bilingual");
  assert.equal(summarise({...PAYLOAD, folded: true, bilingual: true}),
               "2 rows · variants folded · bilingual");
});

test("a payload that states no counts falls back to what it actually sent", () => {
  assert.equal(summarise({rows: [{}, {}, {}]}), "3 rows");
  assert.equal(summarise({}), "0 rows");
});

// ---- the fold switch --------------------------------------------------------

test("a source with nothing to fold gets a disabled switch that says why", () => {
  assert.deepEqual(foldControl({foldable: false}),
    {disabled: true, label: "This source has no variants to fold"});
  assert.deepEqual(foldControl({foldable: true}),
    {disabled: false, label: "Fold variants that share a price"});
  assert.equal(foldControl({}).disabled, true,
    "a payload that says nothing must not offer a switch that does nothing");
});

// ---- which source this tab is for -------------------------------------------

test("the source key comes from the address", () => {
  assert.equal(sourceKeyFrom("?source=ALSWEED"), "ALSWEED");
  assert.equal(sourceKeyFrom("?source=SAMEH%20GABRIEL"), "SAMEH GABRIEL");
});

test("a blank or whitespace key is NO key, not a key made of spaces", () => {
  // Otherwise the page asks for /api/table/%20, gets a 404, and reports the
  // engine as unreachable — sending the owner to restart something that is
  // running perfectly well.
  for (const search of ["", "?source=", "?source=%20%20", "?other=x", null]) {
    assert.equal(sourceKeyFrom(search), "", String(search));
  }
});
