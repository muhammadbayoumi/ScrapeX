// The upload never holds the archive, and the size it checks is not its own.
//
// HE PRESSED "Back up to Drive" ON 2026-09-03 AND GOT: "The engine built an
// archive of 541531989 bytes and this panel read 0." The engine had built it, the
// file was complete on disk with no `.part` beside it, and the panel read nothing:
// a Chrome side panel asked to hold half a gigabyte in one Blob. A 378,655,878-byte
// build had worked four days earlier, so the ceiling sits between them and moves
// with the browser rather than with this code.
//
// `upload` was ALREADY resumable and chunked — it just sliced its 4 MB chunks out
// of a fully buffered Blob. So the fix is not a new upload path; it is that the
// thing being sliced no longer has to exist all at once.
//
// THE SECOND PROPERTY IS THE ONE THAT IS EASY TO LOSE. `expectSize` compares what
// the engine DESCRIBED against what ARRIVED, and on 2026-08-30 those resolved to
// different builds and a 0-byte archive reached Drive. A source sized from the
// manifest would make both sides of that comparison the same number, and the guard
// would pass on anything. So the size comes from the engine's `Content-Range`.

import {test} from "node:test";
import assert from "node:assert/strict";

import {blobSource, upload, DriveError} from "../drive.js";

const CHUNK = 4 * 1024 * 1024;

/** Drive's side of a resumable upload, and a record of every chunk it was sent. */
function drive(total) {
  const sent = [];
  const fetchImpl = async (url, options = {}) => {
    if (String(url).includes("uploadType=resumable")) {
      return {
        ok: true, status: 200,
        headers: {get: (k) => (k.toLowerCase() === "location"
          ? "https://upload.example.invalid/session" : null)},
        json: async () => ({}),
        text: async () => "",
      };
    }
    const range = options.headers?.["Content-Range"] || "";
    sent.push({range, bytes: options.body ? options.body.size ?? options.body.length : 0});
    const done = sent.reduce((n, c) => n + c.bytes, 0) >= total;
    return {
      ok: done, status: done ? 200 : 308,
      headers: {get: () => null},
      json: async () => ({id: "file-1", name: "archive.zip"}),
      text: async () => "",
    };
  };
  return {fetchImpl, sent};
}

/** A source that never materialises the whole thing, and says how much it was
 *  ever asked to produce at once. */
function countingSource(total) {
  const asked = [];
  return {
    asked,
    source: {
      size: total,
      chunk: async (start, end) => {
        asked.push(end - start);
        return new Blob([new Uint8Array(end - start)]);
      },
    },
  };
}

test("a source is uploaded one chunk at a time and never held whole", async () => {
  const total = CHUNK * 3 + 1234;
  const {fetchImpl, sent} = drive(total);
  const {asked, source} = countingSource(total);

  await upload("token", {source, name: "archive.zip", parent: "p", fetchImpl});

  assert.equal(asked.reduce((a, b) => a + b, 0), total,
               "the whole file was not uploaded");
  assert.ok(asked.length >= 4, `expected several chunks, got ${asked.length}`);
  const biggest = Math.max(...asked);
  assert.ok(biggest <= CHUNK,
            `one request asked for ${biggest} bytes; the point of this is that the `
            + `panel holds at most ${CHUNK}`);
  assert.equal(sent.length, asked.length,
               "a chunk was fetched and not sent, or sent and not fetched");
});

test("a blob still works, because a blob is the simplest source", async () => {
  const total = 1000;
  const {fetchImpl, sent} = drive(total);

  const stored = await upload("token", {
    blob: new Blob([new Uint8Array(total)]), name: "small.zip", parent: "p", fetchImpl,
  });

  assert.equal(stored.id, "file-1");
  assert.equal(sent.reduce((n, c) => n + c.bytes, 0), total);
});

test("blobSource exposes exactly what upload needs and nothing else", () => {
  const blob = new Blob([new Uint8Array(10)]);
  const source = blobSource(blob);

  assert.equal(source.size, 10);
  assert.equal(typeof source.chunk, "function");
  assert.equal(source.chunk(2, 5).size, 3);
});

test("nothing to upload is still refused, whichever way it was given", async () => {
  const {fetchImpl} = drive(0);
  await assert.rejects(
    () => upload("token", {name: "x.zip", parent: "p", fetchImpl}),
    (error) => error instanceof DriveError && error.kind === "empty");
});

test("a source that cannot produce a chunk stops the upload rather than shortening it",
     async () => {
  // A short read means the file changed under the upload or the connection was
  // cut. Uploading fewer bytes than promised would leave Drive holding an archive
  // that is wrong, and wrong quietly — which is the failure the 2026-08-30 guard
  // was added for, one level down.
  const total = CHUNK * 2;
  const {fetchImpl, sent} = drive(total);
  const source = {
    size: total,
    chunk: async (start) => {
      if (start === 0) return new Blob([new Uint8Array(CHUNK)]);
      throw Object.assign(new Error("the read was cut short"), {kind: "short-read"});
    },
  };

  await assert.rejects(
    () => upload("token", {source, name: "archive.zip", parent: "p", fetchImpl}),
    (error) => error.kind === "short-read" || /cut short/.test(error.message));
  assert.equal(sent.length, 1,
               "the upload continued after a chunk could not be produced");
});
