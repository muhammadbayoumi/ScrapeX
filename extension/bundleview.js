// Reading the owner's data on a machine with no engine on it at all.
//
// DECISION 8, and the whole reason the backup is a bundle rather than a copy of
// the database. Spike 2 measured running SQLite here: OPFS loses WAL, an access
// handle is exclusive, the service worker cannot write, and wa-sqlite is 70-208x
// slower than Python on the Data page's own query — with a fast VFS that cannot
// open an existing database at all.
//
// None of it is needed. Viewing and exporting is READ-ONLY, so the engine writes
// a plain export and this reads it.
//
// GZIP AND NOT ZIP, and the reason is not preference. A browser has
// DecompressionStream for gzip and deflate built in, and no zip reader at all.
// Unpacking the archive would need a bundled library, and this repository ships
// no npm dependency on purpose. `panel.jsonl.gz` is the format the browser
// already has.
//
// MEASURED on the owner's warehouse: 64.1 MB of rows become 4.1 MB gzipped. A
// bare panel downloads four megabytes and shows months of data.

/**
 * Decompress and parse the panel pack.
 *
 * Streamed, not read whole: 4 MB compressed is 64 MB of text, and holding both
 * the bytes and the string at once for no reason is how a side panel gets
 * killed for memory on a small machine.
 */
export async function readPanelPack(blob) {
  const stream = blob.stream().pipeThrough(new DecompressionStream("gzip"));
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();

  const datasets = new Map();
  let carry = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    carry += value;
    let cut;
    while ((cut = carry.indexOf("\n")) >= 0) {
      const line = carry.slice(0, cut);
      carry = carry.slice(cut + 1);
      addLine(datasets, line);
    }
  }
  addLine(datasets, carry);   // a final line with no newline after it
  return datasets;
}

function addLine(datasets, line) {
  if (!line.trim()) return;
  let entry;
  try {
    entry = JSON.parse(line);
  } catch (_) {
    // ONE unreadable line is not a broken backup. A pack truncated by a failed
    // download loses its last line, and refusing the whole file over it would
    // turn a recoverable download into "you have no data".
    return;
  }
  if (!entry || typeof entry.dataset !== "string") return;
  const key = entry.dataset;
  if (!datasets.has(key)) datasets.set(key, new Map());
  const tables = datasets.get(key);
  const table = entry.table || "current";
  if (!tables.has(table)) tables.set(table, []);
  tables.get(table).push(entry.row);
}

/** What the Data page lists when there is no engine to ask. */
export function datasetSummaries(datasets) {
  return [...datasets.entries()].map(([key, tables]) => ({
    source_key: key,
    rows: (tables.get("current") || []).length,
    tables: [...tables.keys()].sort(),
    // The history table is what makes "when did this change" answerable
    // offline, and saying whether it is here is more useful than a row count
    // nobody asked for.
    has_history: tables.has("history"),
  })).sort((a, b) => b.rows - a.rows);
}

export function rowsOf(datasets, key, table = "current") {
  const tables = datasets.get(key);
  return (tables && tables.get(table)) || [];
}

/**
 * Rows as a CSV the owner can open, built from the rows themselves.
 *
 * The header is the union of every row's keys IN FIRST-SEEN ORDER, not the
 * first row's keys: a row that carries an extra promoted axis would otherwise
 * lose that column silently for the whole file.
 */
export function toCsv(rows) {
  const header = [];
  const seen = new Set();
  for (const row of rows) {
    for (const key of Object.keys(row || {})) {
      if (!seen.has(key)) { seen.add(key); header.push(key); }
    }
  }
  const cell = (value) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = [header.map(cell).join(",")];
  for (const row of rows) {
    lines.push(header.map((key) => cell((row || {})[key])).join(","));
  }
  // A BOM, because Excel guesses the encoding of a plain UTF-8 file wrong and
  // half of this data is Arabic. The engine's own csv writer does the same.
  return "﻿" + lines.join("\r\n") + "\r\n";
}
