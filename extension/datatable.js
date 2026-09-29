// What the Data page asks the engine for its table, and what it says when the
// engine cannot answer — and nothing else.
//
// PURE ON PURPOSE, exactly like workbook.js: no DOM, no fetch, no chrome, no
// Tabulator. data.js is a page controller and cannot be imported under
// `node --test` — it reads `window.location` and starts loading the moment it
// is imported. Everything here can be driven with hostile input instead, which
// is the only reason any of it is covered at all.
//
// The rule for what belongs here: if getting it wrong would put WRONG NUMBERS
// or a WRONG SENTENCE in front of the owner, it belongs here and it gets a test.
// Layout and colour do not.
//
// THE COLUMNS, THE ROW COUNT, THE PREFIX LINE AND THE FOLD ARE THE GRID'S NOW
// (#1198). The page runs the engine's own grid.js, which draws all four from the
// payload the way the engine's page always has, so the helpers that drew them
// here were a second opinion and are gone.

import { selectionQuery } from "./taxonomyfilter.js";

/**
 * The source key this page was opened for, read from its own address.
 *
 * Returns "" for anything that is not a usable key, INCLUDING a key that is
 * only whitespace — the page then says it needs a source instead of asking the
 * engine for `/api/table/%20` and reporting the 404 as if the engine were down.
 */
export function sourceKeyFrom(search) {
  const raw = new URLSearchParams(String(search || "")).get("source") || "";
  return raw.trim();
}

/**
 * The table request for the path grid.js hands its host, narrowed to this page's
 * site and activity selection.
 *
 * THE PATH MAY ALREADY CARRY A QUERY. grid.js appends `?fold=1` or `?fold=0` when
 * the reader chose ALL or ONE, and nothing otherwise, so the join is `&` or `?`
 * by what is there. Appending `&nodes=…` to a bare path would ask for a source
 * whose key ends in it.
 */
export function tableRequest(path, site, nodes, mode) {
  const narrowing = (site ? `&site_key=${encodeURIComponent(site)}` : "")
    + selectionQuery(nodes, mode);
  if (!narrowing) return String(path);
  return String(path) + (String(path).includes("?") ? "&" : "?") + narrowing.slice(1);
}

/**
 * The sentence for a table the engine did not give, by what actually happened.
 *
 * A 404 IS AN ANSWER, NOT A STOPPED ENGINE. `request()` in backend.js marks an
 * HTTP refusal with `kind: "http"` and its status; anything else never reached an
 * answer. Telling the owner to start an engine that answered 404 sends him to
 * restart something that is running perfectly well.
 */
export function whyNoTable(error, key) {
  const message = String(error?.message || "no reason given");
  if (error?.kind === "http" && error?.status === 404) {
    return `The engine has no table named ${key}.`;
  }
  if (error?.kind === "http") {
    return `The engine refused the table (HTTP ${error.status}): ${message}.`;
  }
  return `The engine did not answer: ${message}. It may be stopped — the panel's `
    + "Run screen starts it.";
}
