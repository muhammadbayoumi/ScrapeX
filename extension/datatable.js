// What the Data page MAKES of a `/api/table` payload — and nothing else.
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

/**
 * The columns to draw, taken from the payload's own list.
 *
 * NOT A LIST WRITTEN IN THIS REPOSITORY. `columns` arrives ordered by
 * `fields.column_order`, which is the one answer the export, the Choose-Columns
 * panel and this grid all read. A literal list here would be a fourth opinion,
 * and the defect that produced that rule was exactly this: dragging a column
 * saved, reloaded the page, and changed nothing on screen because the grid was
 * reading its own copy.
 *
 * SCRAPED VALUES ARE UNTRUSTED. Every one of these came off somebody else's
 * website, so the formatter is `plaintext` — Tabulator sets textContent with
 * it, and nothing a shop publishes can become markup here.
 */
export function columnsFrom(payload) {
  return (payload?.columns || [])
    .filter((column) => column && column.key)
    .map((column) => ({
      title: column.label || column.key,
      field: column.key,
      formatter: "plaintext",
      headerSort: true,
      headerTooltip: true,
      resizable: true,
      widthGrow: 1,
      minWidth: 90,
    }));
}

/**
 * The sentence under the source name.
 *
 * "3 of 20000" RATHER THAN "3" is the whole point: a count that shows a prefix
 * as if it were the total is the failure the row cap exists to prevent, and the
 * summary is where a reader looks first.
 */
export function summarise(payload) {
  const rows = payload?.rows || [];
  const shown = payload?.returned ?? rows.length;
  const total = payload?.total ?? shown;
  const parts = [shown === total ? `${total} rows` : `${shown} of ${total} rows`];
  if (payload?.folded) parts.push("variants folded");
  if (payload?.bilingual) parts.push("bilingual");
  return parts.join(" · ");
}

/**
 * What to say when the engine stopped at the cap — or nothing when it did not.
 *
 * SAID, NOT INFERRED. `truncated` is a field the engine sets; deriving it from
 * a row count would mean re-deciding upstream's own bound in a second place,
 * and the two would disagree the day the cap moves.
 */
export function truncationNotice(payload) {
  if (!payload?.truncated) return "";
  const shown = payload?.returned ?? (payload?.rows || []).length;
  return `Stopped at ${shown} rows. This is a PREFIX of the table, not the `
    + "whole of it — export the source to read every row.";
}

/**
 * The fold switch: what it says, and whether it can be touched.
 *
 * A source with nothing to fold gets a DISABLED switch that says why, rather
 * than a live one that does nothing when pressed. `foldable` is the engine's
 * answer about what this source publishes — a shop has variants, a commodity
 * feed does not.
 */
export function foldControl(payload) {
  const foldable = Boolean(payload?.foldable);
  return {
    disabled: !foldable,
    label: foldable ? "Fold variants that share a price"
                    : "This source has no variants to fold",
  };
}

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
