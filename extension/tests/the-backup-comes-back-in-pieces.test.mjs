// Reading a backup OUT of Drive without ever holding it.
//
// The twin of upload-holds-one-chunk.test.mjs, and it exists for the failure
// that has actually happened: 541,531,989 bytes asked of a side-panel document
// came back as 0, four presses running (#788). Every property below is one
// whose failure either loses the archive or brings the whole of it into the
// panel's memory, which is the same thing one machine later.

import {test} from "node:test";
import assert from "node:assert/strict";

import {
  readLatestInPieces, BUNDLE_FORMAT, LATEST,
} from "../drive.js";

const DIGEST = "a".repeat(64);

/** One response, built by hand so what Drive sends stays visible here. */
function reply(status, {body = null, headers = {}, stream = false} = {}) {
  const lower = new Map(
    Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  const bytes = typeof body === "string" ? new TextEncoder().encode(body)
    : (body instanceof Uint8Array ? body : new TextEncoder().encode(
      body === null ? "" : JSON.stringify(body)));
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {get: (name) => lower.get(String(name).toLowerCase()) ?? null},
    json: async () => (typeof body === "string" ? JSON.parse(body) : body),
    text: async () => new TextDecoder().decode(bytes),
    blob: async () => new Blob([bytes]),
    body: stream ? {
      getReader() {
        // Deliberately small reads: a stream that arrives in pieces smaller
        // than one chunk is the normal case, and a reader that forwarded every
        // read would send hundreds of requests instead of tens.
        let at = 0;
        return {
          async read() {
            if (at >= bytes.length) return {value: undefined, done: true};
            const value = bytes.slice(at, at + 7);
            at += value.length;
            return {value, done: false};
          },
        };
      },
    } : null,
  };
}

/** A Drive holding one archive, answering ranges or refusing to. */
function driveHolding(archive, {ranged = true, pointer = {}} = {}) {
  const asked = [];
  const fetchImpl = async (url, init = {}) => {
    const text = String(url);
    asked.push({url: text, range: (init.headers || {}).Range || null});
    if (text.includes("mimeType")) {
      return reply(200, {body: {files: [{id: "folder-1"}]}});
    }
    if (text.includes("/files?") || text.includes("q=")) {
      return reply(200, {body: {files: [{id: "ptr", name: LATEST}]}});
    }
    if (text.includes("/ptr") && text.includes("alt=media")) {
      return reply(200, {body: JSON.stringify({
        file_id: "arch", bytes: archive.length, sha256: DIGEST,
        bundle_format: BUNDLE_FORMAT, ...pointer,
      })});
    }
    if (text.includes("/arch") && !text.includes("alt=media")) {
      return reply(200, {body: {id: "arch", size: String(archive.length)}});
    }
    if (text.includes("/arch") && text.includes("alt=media")) {
      if (!ranged) return reply(200, {body: archive, stream: true});
      const match = /bytes=(\d+)-(\d+)/.exec((init.headers || {}).Range || "");
      if (!match) return reply(200, {body: archive, stream: true});
      const from = Number(match[1]);
      const to = Math.min(Number(match[2]), archive.length - 1);
      return reply(206, {
        body: archive.slice(from, to + 1),
        headers: {"content-range": `bytes ${from}-${to}/${archive.length}`},
      });
    }
    throw new Error(`nothing in this fake answers ${text}`);
  };
  return {fetchImpl, asked};
}

/** An engine that keeps what it is given, and says where it is. */
function anEngine({completeAt = null} = {}) {
  const held = [];
  let received = 0;
  const deliver = async (piece, about) => {
    const bytes = new Uint8Array(await piece.arrayBuffer());
    if (bytes.length === 0 && received === 0 && completeAt === 0) {
      return {received: about.total, total: about.total, complete: true,
              name: "from-drive-already.zip", already_here: true};
    }
    if (bytes.length) held.push(bytes);
    received += bytes.length;
    return {
      received, total: about.total, complete: received >= about.total,
      name: "from-drive-test.zip", already_here: false,
    };
  };
  return {deliver, held, at: () => received};
}

function joined(pieces) {
  const size = pieces.reduce((n, p) => n + p.length, 0);
  const all = new Uint8Array(size);
  let at = 0;
  for (const piece of pieces) { all.set(piece, at); at += piece.length; }
  return all;
}

const ARCHIVE = new Uint8Array(100).map((_, i) => i % 251);

test("the whole archive arrives, in order, from ranged reads", async () => {
  const drive = driveHolding(ARCHIVE);
  const engine = anEngine();

  const landed = await readLatestInPieces("tok", {
    chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
  });

  assert.deepEqual(joined(engine.held), ARCHIVE);
  assert.equal(landed.complete, true);
  assert.equal(landed.name, "from-drive-test.zip");
});

test("nothing bigger than one chunk is ever held", async () => {
  // THE PROPERTY THE WHOLE FUNCTION EXISTS FOR. A reader that accumulated and
  // delivered once at the end would pass every other test in this file and
  // reproduce the failure it was written for.
  const drive = driveHolding(ARCHIVE);
  const engine = anEngine();

  await readLatestInPieces("tok", {
    chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
  });

  for (const piece of engine.held) {
    assert.ok(piece.length <= 32,
              `a piece of ${piece.length} bytes was held for a 32 byte chunk`);
  }
  assert.equal(engine.held.length, 4, "100 bytes in 32 byte windows is four reads");
});

test("a Drive that ignores the range is streamed, not accumulated", async () => {
  // Nothing in this repository records whether Drive honours a Range on
  // `alt=media`. The 200 answer must still work, and must still not hold the
  // archive -- which is what the chunk-size assertion below is checking.
  const drive = driveHolding(ARCHIVE, {ranged: false});
  const engine = anEngine();

  const landed = await readLatestInPieces("tok", {
    chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
  });

  assert.deepEqual(joined(engine.held), ARCHIVE);
  assert.equal(landed.complete, true);
  for (const piece of engine.held) {
    assert.ok(piece.length <= 32 + 7,
              `streaming held ${piece.length} bytes for a 32 byte chunk`);
  }
  const media = drive.asked.filter((call) => call.url.includes("alt=media")
                                          && call.url.includes("/arch"));
  assert.equal(media.length, 1, "the stream was read more than once");
});

test("the engine decides where every read starts, not arithmetic here", async () => {
  // The same rule the upload side learned from Drive's own 308: whatever the
  // far side says it holds is the next offset. An engine that accepted less
  // than it was sent must be read from where it actually is -- on every read,
  // not only the first. THIS TEST WAS WEAKER THAN THAT ONCE: it pinned the
  // opening handoff alone, and a mutant that advanced by chunk size inside the
  // loop survived it.
  const drive = driveHolding(ARCHIVE);
  const deliver = async (piece, about) => {
    const bytes = new Uint8Array(await piece.arrayBuffer());
    if (bytes.length === 0) return {received: 0, total: about.total, complete: false};
    // Half of every piece, so each read starts somewhere arithmetic would not
    // have guessed. `max(1, ...)` because a half of one byte is none, and an
    // engine that never advances is a loop that never ends.
    const taken = Math.max(1, Math.floor(bytes.length / 2));
    const at = Math.min(about.offset + taken, about.total);
    return {received: at, total: about.total, complete: at >= about.total};
  };

  await readLatestInPieces("tok", {
    chunkBytes: 32, deliver, fetchImpl: drive.fetchImpl,
  });

  const ranges = drive.asked.filter((c) => c.range).map((c) => c.range);
  assert.deepEqual(ranges.slice(0, 3),
                   ["bytes=0-31", "bytes=16-47", "bytes=32-63"],
                   "a read started where this file decided rather than where "
                   + "the engine said it was");
});

test("a backup the engine already holds is not read at all", async () => {
  const drive = driveHolding(ARCHIVE);
  const engine = anEngine({completeAt: 0});

  const landed = await readLatestInPieces("tok", {
    chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
  });

  assert.equal(landed.already_here, true);
  const media = drive.asked.filter((call) => call.url.includes("/arch")
                                          && call.url.includes("alt=media"));
  assert.equal(media.length, 0,
               "625 MB was read out of Drive for a file already on the disk");
});

test("a pointer with no digest is refused before anything is read", async () => {
  // Without a digest the destination cannot prove what arrived is what was
  // uploaded, and a corrupt archive that verifies against nothing is worse than
  // no archive: it is offered in the Bundles card as the way back.
  const drive = driveHolding(ARCHIVE, {pointer: {sha256: undefined}});
  const engine = anEngine();

  await assert.rejects(
    () => readLatestInPieces("tok", {
      chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
    }),
    (error) => {
      assert.equal(error.kind, "no-digest");
      return true;
    });
  assert.equal(engine.held.length, 0, "a piece was sent anyway");
});

test("with nowhere to put the pieces it refuses rather than reads", async () => {
  const drive = driveHolding(ARCHIVE);
  await assert.rejects(
    () => readLatestInPieces("tok", {chunkBytes: 32, fetchImpl: drive.fetchImpl}),
    (error) => {
      assert.equal(error.kind, "no-destination");
      return true;
    });
});

test("Google's own refusal keeps its kind and stops the read", async () => {
  const archive = ARCHIVE;
  let served = 0;
  const fetchImpl = async (url, init = {}) => {
    const text = String(url);
    if (text.includes("mimeType")) return reply(200, {body: {files: [{id: "f"}]}});
    if (text.includes("q=")) return reply(200, {body: {files: [{id: "ptr", name: LATEST}]}});
    if (text.includes("/ptr")) {
      return reply(200, {body: JSON.stringify({
        file_id: "arch", bytes: archive.length, sha256: DIGEST,
        bundle_format: BUNDLE_FORMAT})});
    }
    if (text.includes("/arch") && !text.includes("alt=media")) {
      return reply(200, {body: {id: "arch", size: String(archive.length)}});
    }
    served += 1;
    if (served === 1) {
      const match = /bytes=(\d+)-(\d+)/.exec((init.headers || {}).Range || "");
      return reply(206, {body: archive.slice(Number(match[1]), Number(match[2]) + 1)});
    }
    return reply(401, {body: {error: {message: "Invalid Credentials"}}});
  };
  const engine = anEngine();

  await assert.rejects(
    () => readLatestInPieces("tok", {
      chunkBytes: 32, deliver: engine.deliver, fetchImpl,
    }),
    (error) => {
      assert.equal(error.kind, "unauthorized");
      assert.equal(error.status, 401);
      return true;
    });
  assert.ok(engine.at() > 0 && engine.at() < ARCHIVE.length,
            "the read neither started nor stopped where the refusal happened");
});
