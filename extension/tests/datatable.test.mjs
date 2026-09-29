// The Data page's table request and its fault sentence, driven with hostile input.
//
// Everything here is about a WRONG NUMBER or a WRONG SENTENCE reaching the
// owner. Layout is not tested and should not be.

import test from "node:test";
import assert from "node:assert/strict";

import { sourceKeyFrom, tableRequest, whyNoTable } from "../datatable.js";

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

// ---- the request grid.js's path becomes ---------------------------------------

test("with no site and no selection, grid.js's path is asked exactly as handed", () => {
  for (const path of ["/api/table/X", "/api/table/X?fold=1", "/api/table/X?fold=0"]) {
    assert.equal(tableRequest(path, "", [], "any"), path);
  }
});

test("A BARE PATH GETS ?, and a path grid.js already queried gets &", () => {
  // grid.js sends ?fold= only when the reader chose; appending "&nodes=" to a bare
  // path would ask for a source whose key ends in it.
  assert.equal(tableRequest("/api/table/X", "", [11], "any"),
               "/api/table/X?nodes=11&nodes_mode=any");
  assert.equal(tableRequest("/api/table/X?fold=1", "", [11], "any"),
               "/api/table/X?fold=1&nodes=11&nodes_mode=any");
});

test("the site is encoded, and rides before the selection", () => {
  assert.equal(tableRequest("/api/table/X", "muqawil org&x=1", [], "any"),
               "/api/table/X?site_key=muqawil%20org%26x%3D1");
  assert.equal(tableRequest("/api/table/X?fold=0", "S", [3, 2], "all"),
               "/api/table/X?fold=0&site_key=S&nodes=2,3&nodes_mode=all");
});

test("a hostile selection is the selection query's to clean, not the path's", () => {
  assert.equal(tableRequest("/api/table/X", "", ["1; DROP", -4, 0, 2.5, "7", 7], "ANY"),
               "/api/table/X?nodes=7&nodes_mode=any");
  assert.equal(tableRequest("/api/table/X", "", null, null), "/api/table/X");
});

// ---- the sentence for a table the engine did not give --------------------------

test("A 404 SAYS THE ENGINE HAS NO SUCH TABLE, never that it is stopped", () => {
  const said = whyNoTable(Object.assign(new Error("Not Found"), {kind: "http", status: 404}),
                          "ALSWEED");
  assert.equal(said, "The engine has no table named ALSWEED.");
  assert.doesNotMatch(said, /stopped/);
});

test("another HTTP refusal names its status and the engine's own detail", () => {
  const said = whyNoTable(Object.assign(new Error("the database is locked"),
                                        {kind: "http", status: 503}), "X");
  assert.equal(said, "The engine refused the table (HTTP 503): the database is locked.");
});

test("a request that never reached an answer says the engine did not answer", () => {
  const said = whyNoTable(new TypeError("Failed to fetch"), "X");
  assert.match(said, /^The engine did not answer: Failed to fetch\./);
  assert.match(said, /Run screen/);
  assert.match(whyNoTable(undefined, "X"), /no reason given/);
});
