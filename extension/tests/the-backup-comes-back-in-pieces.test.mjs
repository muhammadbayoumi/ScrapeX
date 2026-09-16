// Reading a backup OUT of Drive without ever holding it.
//
// The twin of upload-holds-one-chunk.test.mjs, and it exists for the failure
// that has actually happened: 541,531,989 bytes asked of a side-panel document
// came back as 0, four presses running (#788). Every property below is one
// whose failure either loses the archive or brings the whole of it into the
// panel's memory, which is the same thing one machine later.

import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {dirname, join} from "node:path";

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

/** A Drive holding one archive, answering ranges or refusing to.
 *
 * `serves` is what the 200 path actually delivers, which is not always what the
 * pointer promised: a connection that drops mid-stream ends cleanly with less.
 */
function driveHolding(archive, {ranged = true, pointer = {}, serves = null} = {}) {
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
      if (!ranged) {
        return reply(200, {body: serves || archive, stream: true});
      }
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

/** An engine that keeps what it is given, and says where it is.
 *
 * `holding` is a transfer it already has part of -- what a `.part` on the disk
 * looks like from here.
 */
function anEngine({completeAt = null, holding = 0} = {}) {
  const held = [];
  let received = holding;
  // A REAL CHUNK AT ZERO IS A RESTART, which is what the route does with one:
  // the tail it was holding is dropped rather than appended to.
  const restart = () => { received = 0; held.length = 0; };
  const deliver = async (piece, about) => {
    const bytes = new Uint8Array(await piece.arrayBuffer());
    if (bytes.length === 0 && completeAt === 0) {
      return {received: about.total, total: about.total, complete: true,
              name: "from-drive-already.zip", already_here: true};
    }
    if (bytes.length === 0) {
      return {received, total: about.total, complete: false};
    }
    if (about.offset === 0 && received) restart();
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

test("a stream that stops short is a refusal, not a fetched backup", async () => {
  // THE ONE THE MERGE GATE CAUGHT, and it is #788's own symptom: the read that
  // returns less than it promised, reported in the success colour. The ranged
  // loop cannot end early -- it is bounded by `total` -- but the streamed path
  // ends when the stream ends, which on a dropped connection is any number.
  const short = ARCHIVE.slice(0, 63);
  const drive = driveHolding(ARCHIVE, {ranged: false, serves: short});
  const engine = anEngine();

  await assert.rejects(
    () => readLatestInPieces("tok", {
      chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
    }),
    (error) => {
      assert.equal(error.kind, "truncated");
      assert.match(error.message, /63 of 100/);
      return true;
    });
});

test("a stream that brings nothing at all is a refusal too", async () => {
  // SHARPER THAN THE SHORT ONE: with no bytes delivered, the answer never moves
  // off the opening probe's reply -- which has no name -- so the sentence the
  // owner read was "Fetched 0.0 MB as undefined".
  const drive = driveHolding(ARCHIVE, {ranged: false, serves: new Uint8Array(0)});
  const engine = anEngine();

  await assert.rejects(
    () => readLatestInPieces("tok", {
      chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
    }),
    (error) => {
      assert.equal(error.kind, "truncated");
      assert.match(error.message, /0 of 100/);
      return true;
    });
  assert.equal(engine.held.length, 0);
});

test("a fetch resumes from what the destination is already holding", async () => {
  // The probe is a QUESTION, and its answer is where this fetch starts. Before
  // the gate, the panel asked and then began at zero anyway, so a failure at
  // 99% cost the whole 625 MB again -- and the route's 409 resume branch had no
  // caller at all.
  const drive = driveHolding(ARCHIVE);
  const engine = anEngine({holding: 40});

  const landed = await readLatestInPieces("tok", {
    chunkBytes: 32, deliver: engine.deliver, fetchImpl: drive.fetchImpl,
  });

  const ranges = drive.asked.filter((c) => c.range).map((c) => c.range);
  assert.equal(ranges[0], "bytes=40-71",
               "the fetch restarted from zero over bytes the engine already had");
  assert.equal(landed.complete, true);
  assert.deepEqual(joined(engine.held), ARCHIVE.slice(40));
});

test("a stream restarts the transfer, because a 200 cannot resume", async () => {
  // WHERE THIS CHANGE'S TWO NEW BEHAVIOURS MEET, and the line that makes them
  // agree could be deleted with every suite green. A 200 is the whole file from
  // byte zero; announcing those pieces at the offset the engine was holding
  // would write them past the end -- 140 bytes of a 100-byte archive, reported
  // as complete.
  const drive = driveHolding(ARCHIVE, {ranged: false});
  const engine = anEngine({holding: 40});
  const at = [];
  const deliver = async (piece, about) => {
    const bytes = new Uint8Array(await piece.arrayBuffer());
    if (bytes.length) at.push(about.offset);
    return engine.deliver(piece, about);
  };

  const landed = await readLatestInPieces("tok", {
    chunkBytes: 32, deliver, fetchImpl: drive.fetchImpl,
  });

  assert.equal(at[0], 0, "the stream was announced from where the engine was");
  assert.deepEqual(joined(engine.held), ARCHIVE);
  assert.equal(landed.complete, true);
  assert.equal(landed.received, ARCHIVE.length,
               `the engine ended holding ${landed.received} of ${ARCHIVE.length}`);
});

test("a destination that says it holds everything never gets a backwards range", async () => {
  // THE BELT on the engine's answer. `bytes=100-99` is a range Google refuses
  // in its own words, and the owner would read that refusal as Google's fault
  // about a file on his own disk -- the failure `refuse()` in drive.js was
  // written against. The engine decides that state properly now; this is what
  // stops a number from ever becoming that request.
  const drive = driveHolding(ARCHIVE);
  const deliver = async (piece, about) => {
    const bytes = new Uint8Array(await piece.arrayBuffer());
    if (bytes.length === 0) {
      return {received: about.total, total: about.total, complete: false};
    }
    const at = Math.min(about.offset + bytes.length, about.total);
    return {received: at, total: about.total, complete: at >= about.total,
            name: "from-drive-test.zip", already_here: false};
  };

  await readLatestInPieces("tok", {
    chunkBytes: 32, deliver, fetchImpl: drive.fetchImpl,
  });

  for (const range of drive.asked.filter((c) => c.range).map((c) => c.range)) {
    const [, from, to] = /bytes=(\d+)-(\d+)/.exec(range);
    assert.ok(Number(to) >= Number(from), `Drive was asked for ${range}`);
  }
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

// THE SENTENCE HE READS WHEN IT WORKS, which nothing in this repository ran.
//
// The first merge-gate pass caught the panel reporting `Fetched 0.0 MB as
// undefined` -- a success sentence built from a reply that carried no name --
// and the guard written for it was a DOM test that leaves Drive unstubbed, so
// every run there ends in the failure branch and the success sentence is never
// drawn. The third pass proved it: `as ${landed.name}` could be replaced with
// `as ${undefined}` in `extension/app.js` and the whole repository stayed green.
//
// Read out of app.js rather than imported, the way `escaping.test.mjs` reads
// `esc()`: app.js is the panel's entry point and touches chrome.* at module
// scope. Reading the two lines under test keeps this honest -- if they move,
// this fails loudly instead of testing a copy that has drifted.
const HERE = dirname(fileURLToPath(import.meta.url));
const PANEL = readFileSync(join(HERE, "..", "app.js"), "utf8");

function loadTheSentences() {
  const found = PANEL.match(
    // `\r?\n`, because `.gitattributes` stores LF and Windows checks out CRLF:
    // a guard that reads the panel's own source has to read it on both.
    /async function fetchBackupFromDrive[^]*?\r?\n(  if \(landed\.already_here\) \{[^]*?)\r?\n\}/);
  assert.ok(found,
    "fetchBackupFromDrive no longer ends with the two sentences this reads");
  // eslint-disable-next-line no-new-func
  return new Function("landed", "fmtMegabytes", found[1]);
}

const sentences = loadTheSentences();
// The panel's own formatter, read the same way, so the size in the sentence
// is its arithmetic rather than this file's idea of it.
function loadMegabytes() {
  const found = PANEL.match(/function fmtMegabytes\(n\) \{\r?\n([^]*?)\r?\n\}/);
  assert.ok(found, "fmtMegabytes is no longer where this guard reads it from");
  // eslint-disable-next-line no-new-func
  return new Function("n", found[1]);
}

const megabytes = loadMegabytes();

test("the sentence the panel ends on names the file that landed", () => {
  const said = sentences(
    {complete: true, received: 4194304, total: 4194304,
     name: "from-drive-1a2b3c4d5e6f7a8b.zip", already_here: false},
    megabytes);

  assert.match(said, /from-drive-1a2b3c4d5e6f7a8b\.zip/,
    `the fetch did not say what it made: ${said}`);
  assert.ok(!said.includes("undefined"),
    `the panel reported a value it does not have: ${said}`);
  assert.match(said, /^Fetched 4\.0 MB as /, said);
});

test("a backup already on this computer is named too, not called undefined", () => {
  const said = sentences(
    {complete: true, received: 10, total: 10,
     name: "from-drive-00112233445566aa.zip", already_here: true},
    megabytes);

  assert.match(said, /already on this computer as from-drive-00112233445566aa\.zip/,
    said);
  assert.ok(!said.includes("undefined"), said);
});

test("both sentences send him to the card that unpacks it", () => {
  // The fetch leaves an archive; only `adopt-bundle` turns it into a warehouse.
  // A sentence that stops at "Fetched 597.0 MB" is a dead end on the day he is
  // restoring, which is the only day this control is ever pressed.
  for (const already_here of [true, false]) {
    const said = sentences(
      {complete: true, received: 1, total: 1, name: "from-drive-x.zip",
       already_here}, megabytes);
    assert.match(said, /Open Database and press it to unpack it\./, said);
  }
});
