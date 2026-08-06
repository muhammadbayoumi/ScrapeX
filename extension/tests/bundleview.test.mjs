// The panel reading the owner's data with no engine on the machine.
//
// Decision 8. Everything here runs under `node --test` with no browser and no
// engine, because the whole claim is that reading needs neither.
//
// GZIP AND NOT ZIP: a browser has DecompressionStream built in and no zip
// reader at all, and this repository ships no npm dependency. Node has the same
// DecompressionStream, so what is tested here is what the panel runs.

import { test } from "node:test";
import assert from "node:assert/strict";
import { gzipSync } from "node:zlib";

import { readPanelPack, datasetSummaries, rowsOf, toCsv }
  from "../bundleview.js";

function packOf(entries) {
  const text = entries.map((e) => JSON.stringify(e)).join("\n") + "\n";
  return new Blob([gzipSync(Buffer.from(text, "utf8"))]);
}

const ENTRIES = [
  { dataset: "MADAR", table: "current",
    row: { product_name: "Cement", product_name_ar: "أسمنت", price: 23.5 } },
  { dataset: "MADAR", table: "current",
    row: { product_name: "Sand", product_name_ar: "رمل", price: 8 } },
  { dataset: "MADAR", table: "history",
    row: { product_name: "Cement", price: 22.0, business_date: "2026-07-01" } },
  { dataset: "SHOP", table: "current",
    row: { product_name: "Lamp", product_name_ar: "مصباح", price: 99 } },
];

test("the rows come back with no engine, no database and no library", async () => {
  const datasets = await readPanelPack(packOf(ENTRIES));

  assert.equal(datasets.size, 2);
  assert.equal(rowsOf(datasets, "MADAR").length, 2);
  assert.equal(rowsOf(datasets, "MADAR")[0].product_name_ar, "أسمنت");
  assert.equal(rowsOf(datasets, "MADAR", "history").length, 1);
});

test("a number is still a number, so a column sorts", async () => {
  // The reason the export is JSON Lines and not only csv. A panel reading
  // "23.5" as text sorts 100 before 23.5, which is the kind of wrong that
  // looks like working software.
  const datasets = await readPanelPack(packOf(ENTRIES));

  assert.equal(typeof rowsOf(datasets, "MADAR")[0].price, "number");
});

test("the dataset list is what the Data page shows when nothing can be asked", async () => {
  const datasets = await readPanelPack(packOf(ENTRIES));

  const summaries = datasetSummaries(datasets);

  assert.deepEqual(summaries.map((s) => s.source_key), ["MADAR", "SHOP"]);
  assert.equal(summaries[0].rows, 2);
  assert.equal(summaries[0].has_history, true);
  assert.equal(summaries[1].has_history, false);
});

test("a truncated download loses its last row and not the whole file", async () => {
  // A pack cut short by a failed download ends mid-line. Refusing the file over
  // it turns a recoverable download into "you have no data" — which is the one
  // answer a backup must never give.
  const text = ENTRIES.map((e) => JSON.stringify(e)).join("\n");
  const cut = text.slice(0, text.length - 20);
  const datasets = await readPanelPack(new Blob([gzipSync(Buffer.from(cut, "utf8"))]));

  assert.equal(rowsOf(datasets, "MADAR").length, 2, "earlier rows were lost too");
});

test("a line with no dataset is skipped rather than crashing the page", async () => {
  const datasets = await readPanelPack(packOf([
    { table: "current", row: { a: 1 } },     // no dataset
    ENTRIES[0],
  ]));

  assert.equal(datasets.size, 1);
  assert.equal(rowsOf(datasets, "MADAR").length, 1);
});

test("a pack with a final line and no newline still yields it", async () => {
  // gzip of text that does not end in a newline. The reader carries a partial
  // line between chunks, and a version that only flushed on "\n" would drop
  // the last row of every file written that way.
  const text = ENTRIES.map((e) => JSON.stringify(e)).join("\n");
  const datasets = await readPanelPack(new Blob([gzipSync(Buffer.from(text, "utf8"))]));

  assert.equal(rowsOf(datasets, "SHOP").length, 1);
});

test("a row split across two chunks is reassembled", async () => {
  // 64 MB of text arrives in pieces and a row lands on the boundary. Asserted
  // with a row long enough that the stream must split it.
  const long = { dataset: "BIG", table: "current",
                 row: { product_name: "x".repeat(200_000), price: 1 } };
  const datasets = await readPanelPack(packOf([long]));

  assert.equal(rowsOf(datasets, "BIG")[0].product_name.length, 200_000);
});

// ---- exporting, which is the other half of Decision 8 -----------------------

test("the csv header is every column any row has, in first-seen order", () => {
  // Not the first row's keys. A row carrying an extra promoted axis would
  // otherwise lose that column silently for the whole file.
  const csv = toCsv([{ a: 1, b: 2 }, { a: 3, c: 4 }]);

  assert.equal(csv.split("\r\n")[0], "﻿a,b,c");
});

test("a cell with a comma, a quote or a newline survives", () => {
  const csv = toCsv([{ name: 'He said "go", then left\nquickly' }]);

  assert.match(csv, /"He said ""go"", then left\nquickly"/);
});

test("the csv carries the mark Excel needs for Arabic", () => {
  const csv = toCsv([{ product_name_ar: "أسمنت" }]);

  assert.ok(csv.startsWith("﻿"),
    "no BOM, so Excel opens the Arabic as mojibake");
  assert.ok(csv.includes("أسمنت"));
});

test("an absent value is empty and not the word undefined", () => {
  const csv = toCsv([{ a: 1, b: null }, { a: undefined, b: 2 }]);

  assert.equal(csv.split("\r\n")[1], "1,");
  assert.equal(csv.split("\r\n")[2], ",2");
});
