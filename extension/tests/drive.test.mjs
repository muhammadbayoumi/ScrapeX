// What the panel's Drive client must never get wrong.
//
// The module this replaces, scrapex/drive.py, had zero tests and zero callers,
// and shipped two defects that only a first real upload would have found. The
// point of this file is that the replacement cannot repeat that: every property
// below is one whose failure loses data or silently uploads nothing.

import {test} from "node:test";
import assert from "node:assert/strict";

import {
  backUp, download, fetchLatest, folderId, listing, prunable, upload,
  fetchPanelPack, verifyStored,
  BUNDLE_FORMAT, DriveError, KEEP, LATEST, PANEL_PACK,
} from "../drive.js";
import {readFileSync} from "node:fs";

/** A stand-in for one fetch response. Deliberately not a real Response: the
 * 308 case below is the one that matters most, and a hand-built object makes
 * what Drive actually sends visible in the test rather than hidden in a spec. */
function reply(status, {body = null, headers = {}} = {}) {
  const lower = new Map(
    Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {get: (name) => lower.get(String(name).toLowerCase()) ?? null},
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
    blob: async () => new Blob([typeof body === "string" ? body : ""]),
    body: null,
  };
}

/** A fetch that answers from a script and records what it was asked. */
function scripted(handlers) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({url: String(url), method: init.method || "GET", init});
    for (const [match, respond] of handlers) {
      if (match(String(url), init)) return respond(String(url), init, calls);
    }
    throw new Error(`no scripted reply for ${init.method || "GET"} ${url}`);
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

const isSearch = (url, init) =>
  url.startsWith("https://www.googleapis.com/drive/v3/files?") &&
  (init.method || "GET") === "GET";
const isStart = (url, init) =>
  url.startsWith("https://www.googleapis.com/upload/drive/v3/files?") &&
  init.method === "POST";
const isPut = (url, init) => url.startsWith("https://session.example/") &&
  init.method === "PUT";
//: `files/{id}?fields=…` — the post-upload check, which is a GET on ONE file
//: and therefore does not collide with isSearch's `files?…` listing.
const isGetFile = (url, init) =>
  /^https:\/\/www\.googleapis\.com\/drive\/v3\/files\/[^?]+\?fields=/.test(url) &&
  (init.method || "GET") === "GET";
//: What Drive answers when it holds a file it will not describe. Scripted into
//: the tests below that are about ORDER rather than about verification, so the
//: check is exercised without pinning a size in a test that is not about one.
const undescribed = () => reply(200, {body: {}});

const SESSION = "https://session.example/one";


test("a 308 continues the upload instead of aborting it", async () => {
  // THE TRAP. Drive answers every incomplete chunk with 308 Resume Incomplete,
  // and fetch() reports 308 with ok === false. A client that treated !ok as
  // failure would abort every upload larger than one chunk on its first chunk —
  // and would do it while reporting a Google error that Google never sent.
  const puts = [];
  const fetchImpl = scripted([
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, (_url, init) => {
      puts.push(init.headers["Content-Range"]);
      if (puts.length < 3) {
        const upto = puts.length * 4 * 1024 * 1024 - 1;
        return reply(308, {headers: {Range: `bytes=0-${upto}`}});
      }
      return reply(200, {body: {id: "file-1", name: "bundle.zip"}});
    }],
  ]);

  const blob = new Blob([new Uint8Array(10 * 1024 * 1024)]);
  const seen = [];
  const stored = await upload("tok", {
    blob, name: "bundle.zip", parent: "folder-1", fetchImpl,
    onProgress: (p) => seen.push(p.sent),
  });

  assert.equal(stored.id, "file-1");
  assert.equal(puts.length, 3, "the upload did not run to completion");
  assert.equal(puts[0], `bytes 0-${4 * 1024 * 1024 - 1}/${10 * 1024 * 1024}`);
  assert.equal(seen[0], 0, "no progress was reported before the first byte");
  assert.equal(seen.at(-1), blob.size, "the bar never reached the end");
});


test("the next chunk starts where Drive says it does, not where we assumed", async () => {
  // Drive is allowed to accept fewer bytes than were sent. Trusting our own
  // arithmetic would then skip a range, and the upload would finish "successfully"
  // with a hole in the middle of the archive.
  const ranges = [];
  const fetchImpl = scripted([
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, (_url, init) => {
      ranges.push(init.headers["Content-Range"]);
      if (ranges.length === 1) {
        return reply(308, {headers: {Range: "bytes=0-999"}});   // only 1000 bytes
      }
      return reply(200, {body: {id: "f", name: "n"}});
    }],
  ]);

  await upload("tok", {
    blob: new Blob([new Uint8Array(5 * 1024 * 1024)]),
    name: "n", parent: "p", fetchImpl,
  });

  assert.match(ranges[1], /^bytes 1000-/,
               `resumed at the wrong offset: ${ranges[1]}`);
});


test("a missing session address is named as the permission problem it is", async () => {
  const fetchImpl = scripted([[isStart, () => reply(200, {headers: {}})]]);

  await assert.rejects(
    () => upload("tok", {blob: new Blob(["x"]), name: "n", parent: "p", fetchImpl}),
    (error) => {
      assert.ok(error instanceof DriveError);
      assert.equal(error.kind, "no-session");
      assert.match(error.message, /host permission/,
                   "the error does not tell the reader where to look");
      return true;
    });
});


test("the pointer is written only after the archive is safely up", async () => {
  // THE ORDERING THAT MATTERS. A pointer written first names a backup that may
  // never arrive, and a restoring machine follows the pointer.
  const order = [];
  const fetchImpl = scripted([
    [isSearch, (url) => {
      if (url.includes("mimeType")) return reply(200, {body: {files: [{id: "folder-1"}]}});
      return reply(200, {body: {files: []}});
    }],
    [isStart, (_url, init) => {
      order.push(`start:${JSON.parse(init.body).name}`);
      return reply(200, {headers: {Location: SESSION}});
    }],
    [isPut, () => reply(200, {body: {id: "up", name: "bundle.zip"}})],
    [isGetFile, undescribed],
  ]);

  await backUp("tok", {
    archive: new Blob(["archive bytes"]), name: "bundle.zip",
    manifest: {sha256: "abc", created_at: "2026-08-11T00:00:00Z"}, fetchImpl,
  });

  assert.deepEqual(order, ["start:bundle.zip", `start:${LATEST}`],
                   "the pointer was uploaded before (or without) the archive");
});


test("a failed archive upload never touches the existing pointer", async () => {
  const deleted = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [{id: "old-pointer", name: LATEST}]}}))],
    [isStart, () => reply(500, {body: {error: {message: "Backend Error"}}})],
    [(url, init) => init.method === "DELETE", (url) => {
      deleted.push(url); return reply(204);
    }],
  ]);

  await assert.rejects(() => backUp("tok", {
    archive: new Blob(["bytes"]), name: "bundle.zip", fetchImpl,
  }), DriveError);

  assert.deepEqual(deleted, [],
    "the old pointer was deleted even though the new backup never arrived — a " +
    "restoring machine would now be told there is no backup at all");
});


test("prunable sorts by createdTime rather than trusting the order it was given", async () => {
  // The Python version relied on the caller passing files newest-first and said
  // so only in a comment. A function whose correctness depends on an argument's
  // order, with nothing checking that order, is one refactor away from deleting
  // the newest backups and keeping the oldest.
  const files = [
    {id: "a", name: "a.zip", createdTime: "2026-08-01T00:00:00Z"},
    {id: "e", name: "e.zip", createdTime: "2026-08-05T00:00:00Z"},
    {id: "c", name: "c.zip", createdTime: "2026-08-03T00:00:00Z"},
    {id: "d", name: "d.zip", createdTime: "2026-08-04T00:00:00Z"},
    {id: "b", name: "b.zip", createdTime: "2026-08-02T00:00:00Z"},
  ];

  const doomed = prunable(files, KEEP).map((f) => f.id).sort();

  assert.deepEqual(doomed, ["a", "b"],
    "the oldest two were not the ones chosen; the newest backups were at risk");
});


test("the pointer is never a pruning candidate", async () => {
  const files = [
    {name: LATEST, id: "p", createdTime: "2026-08-09T00:00:00Z"},
    ...Array.from({length: 6}, (_, n) => ({
      id: `z${n}`, name: `z${n}.zip`,
      createdTime: `2026-08-0${n + 1}T00:00:00Z`,
    })),
  ];

  const doomed = prunable(files, KEEP);

  assert.equal(doomed.some((f) => f.name === LATEST), false,
    "latest.json was going to be deleted; every device would then believe no " +
    "backup exists while every backup is still sitting there");
});


test("a truncated download refuses rather than handing back half a warehouse", async () => {
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [{id: "ptr", name: LATEST}]}}))],
    [(url, init) => url.includes("alt=media") && (init.method || "GET") === "GET",
      (url) => (url.includes("ptr")
        ? reply(200, {body: JSON.stringify({file_id: "arch", bytes: 999})})
        : reply(200, {body: "short"}))],
  ]);

  await assert.rejects(() => fetchLatest("tok", {fetchImpl}), (error) => {
    assert.equal(error.kind, "truncated");
    assert.match(error.message, /Nothing was restored/);
    return true;
  });
});


test("a backup from a newer engine is refused with the remedy in the sentence", async () => {
  // Carried over from the Python module, which had this right. Without it an
  // older device opens an archive it does not understand and reports whatever
  // it manages to read as the warehouse.
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [{id: "ptr", name: LATEST}]}}))],
    [(url) => url.includes("alt=media"),
      () => reply(200, {body: JSON.stringify(
        {file_id: "arch", bytes: 10, bundle_format: BUNDLE_FORMAT + 1})})],
  ]);

  await assert.rejects(() => fetchLatest("tok", {fetchImpl}), (error) => {
    assert.equal(error.kind, "wrong-format");
    assert.match(error.message, /Update the ScrapeX engine/,
                 "the refusal does not say what to do about it");
    assert.match(error.message, /Nothing was restored/);
    return true;
  });
});


test("the panel and the engine agree on the bundle format number", async () => {
  // Two constants in two languages that cannot import each other. The Python
  // twin is the one bundle.py writes into every manifest; if they ever differ,
  // every backup this panel makes is one it will refuse to read back.
  const python = readFileSync(
    new URL("../../scrapex/bundle.py", import.meta.url), "utf8");
  const found = /^BUNDLE_FORMAT\s*=\s*(\d+)/m.exec(python);

  assert.ok(found, "scrapex/bundle.py no longer defines BUNDLE_FORMAT");
  assert.equal(Number(found[1]), BUNDLE_FORMAT,
    `the engine writes bundle format ${found[1]} and this panel reads ` +
    `${BUNDLE_FORMAT}; change both or neither`);
});


test("only one pointer ever exists, however many were there before", async () => {
  const deleted = [];
  const uploaded = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [
        {id: "old-a", name: LATEST, createdTime: "2026-08-01T00:00:00Z"},
        {id: "old-b", name: LATEST, createdTime: "2026-08-02T00:00:00Z"},
      ]}}))],
    [isStart, (_url, init) => {
      uploaded.push(JSON.parse(init.body).name);
      return reply(200, {headers: {Location: SESSION}});
    }],
    [isPut, () => reply(200, {body: {id: "new", name: "x"}})],
    [isGetFile, undescribed],
    [(_url, init) => init.method === "DELETE",
      (url) => { deleted.push(url); return reply(204); }],
  ]);

  await backUp("tok", {archive: new Blob(["b"]), name: "bundle.zip", fetchImpl});

  assert.equal(deleted.filter((u) => u.includes("old-")).length, 2,
    "a stale pointer survived; two files now claim to be the current backup");
  assert.equal(uploaded.filter((n) => n === LATEST).length, 1);
});


test("the token is never written down anywhere", async () => {
  // The whole reason this work moved into the panel. chrome.storage, localStorage
  // and a module-level cache are three different ways to turn a token Chrome
  // manages into one this repository has to protect.
  const source = readFileSync(new URL("../drive.js", import.meta.url), "utf8");

  for (const sink of ["chrome.storage", "localStorage", "sessionStorage",
                      "indexedDB", "document.cookie"]) {
    assert.equal(source.includes(sink), false,
      `drive.js reaches for ${sink}. The token is Chrome's to hold and this ` +
      "module's to pass on, never to keep.");
  }
});


test("an empty Drive says so instead of failing", async () => {
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
  ]);

  await assert.rejects(() => fetchLatest("tok", {fetchImpl}), (error) => {
    assert.equal(error.kind, "no-backup");
    return true;
  });
});


test("a 401 tells the owner to sign in rather than reporting a network fault", async () => {
  const fetchImpl = scripted([
    [isSearch, () => reply(401, {body: {error: {message: "Invalid Credentials"}}})],
  ]);

  await assert.rejects(() => folderId("stale", {fetchImpl}), (error) => {
    assert.equal(error.status, 401);
    assert.equal(error.kind, "unauthorized");
    assert.match(error.message, /Sign in again/);
    return true;
  });
});


test("no token at all is refused before a request is made", async () => {
  const fetchImpl = scripted([]);   // any call at all throws "no scripted reply"

  await assert.rejects(() => listing("", "folder-1", {fetchImpl}), (error) => {
    assert.equal(error.kind, "no-token");
    return true;
  });
  assert.equal(fetchImpl.calls.length, 0, "a request went out with no token");
});


test("a deleted backup folder is not written into", async () => {
  // Searched with 'me' in owners and trashed = false, so a folder the owner threw
  // away is not found and a fresh one is made. Backups going into a trashed
  // folder is the failure where everything reports success and nothing is
  // recoverable.
  const fetchImpl = scripted([
    [isSearch, () => reply(200, {body: {files: []}})],
    [(url, init) => url.startsWith("https://www.googleapis.com/drive/v3/files?") &&
      init.method === "POST", () => reply(200, {body: {id: "fresh-folder"}})],
  ]);

  assert.equal(await folderId("tok", {fetchImpl}), "fresh-folder");
  // `+` for space, because that is how URLSearchParams encodes a query and
  // decodeURIComponent does not undo it. Decoding without this reads the query
  // as `trashed+=+false` and fails on a request that was perfectly correct.
  const query = decodeURIComponent(fetchImpl.calls[0].url).replace(/\+/g, " ");
  assert.match(query, /trashed = false/);
  assert.match(query, /'me' in owners/);
});


test("download reports progress and returns the bytes", async () => {
  const chunks = [new Uint8Array([1, 2, 3]), new Uint8Array([4, 5])];
  let index = 0;
  const fetchImpl = scripted([[() => true, () => ({
    ok: true, status: 200,
    headers: {get: (n) => (n.toLowerCase() === "content-length" ? "5" : null)},
    body: {getReader: () => ({
      read: async () => (index < chunks.length
        ? {value: chunks[index++], done: false}
        : {value: undefined, done: true}),
    })},
    json: async () => ({}), text: async () => "",
    blob: async () => new Blob(chunks),
  })]]);

  const seen = [];
  const blob = await download("tok", "f", {
    fetchImpl, onProgress: (p) => seen.push(p),
  });

  assert.equal(blob.size, 5);
  assert.deepEqual(seen.map((p) => p.received), [0, 3, 5]);
  assert.equal(seen.at(-1).total, 5);
});


test("the panel pack goes up after the archive and before the pointer", async () => {
  // Same rule as everything else here: the pointer is written last, so it can
  // only ever name files that have already arrived. A pointer promising a pack
  // that failed would send a bare panel to fetch something that is not there,
  // with no engine on that machine to explain it.
  const order = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, (_url, init) => {
      order.push(JSON.parse(init.body).name);
      return reply(200, {headers: {Location: SESSION}});
    }],
    [isPut, () => reply(200, {body: {id: "up", name: "x"}})],
    [isGetFile, undescribed],
  ]);

  await backUp("tok", {
    archive: new Blob(["archive"]), name: "bundle.zip",
    panelPack: new Blob(["pack"]), fetchImpl,
  });

  assert.deepEqual(order, ["bundle.zip", PANEL_PACK, LATEST],
    "the three uploads did not happen in the one order that is safe");
});


test("the pointer records the pack, so a reader never guesses a filename", async () => {
  let written = null;
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, (_url, init) => {
      written = JSON.parse(init.body).name;
      return reply(200, {headers: {Location: SESSION}});
    }],
    [isPut, (_url, init) => {
      if (written === LATEST) {
        // The pointer's own bytes, which is the only place its shape is real.
        return init.body.text().then((text) =>
          reply(200, {body: {id: "ptr", name: LATEST, _wrote: text}}));
      }
      return reply(200, {body: {id: `id-${written}`, name: written}});
    }],
    [isGetFile, undescribed],
  ]);

  const result = await backUp("tok", {
    archive: new Blob(["a"]), name: "bundle.zip",
    panelPack: new Blob(["12345"]), fetchImpl,
  });

  assert.equal(result.panel_pack.name, PANEL_PACK);
  assert.equal(result.panel_pack.bytes, 5);
  assert.ok(result.panel_pack.file_id, "the pack's id was not recorded");
});


test("a backup with no pack still works and says so in the pointer", async () => {
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, () => reply(200, {body: {id: "up", name: "x"}})],
    [isGetFile, undescribed],
  ]);

  const result = await backUp("tok", {
    archive: new Blob(["a"]), name: "bundle.zip", fetchImpl,
  });

  assert.equal(result.panel_pack, null,
    "an absent pack must be null, not missing — a reader has to tell the two "
    + "apart to give the owner the right sentence");
});


test("only one panel pack ever exists, however many were there before", async () => {
  const deleted = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [
        {id: "old-pack", name: PANEL_PACK, createdTime: "2026-08-01T00:00:00Z"},
      ]}}))],
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, () => reply(200, {body: {id: "new", name: "x"}})],
    [isGetFile, undescribed],
    [(_url, init) => init.method === "DELETE",
      (url) => { deleted.push(url); return reply(204); }],
  ]);

  await backUp("tok", {
    archive: new Blob(["a"]), name: "bundle.zip",
    panelPack: new Blob(["p"]), fetchImpl,
  });

  assert.equal(deleted.filter((u) => u.includes("old-pack")).length, 1,
    "the previous pack survived; retention only proposes .zip files, so it "
    + "would sit there forever growing one 4 MB file per backup");
});


test("an old backup with no pack is named, not reported as no data", async () => {
  // The owner's warehouse is safe; it is this one screen that cannot open it,
  // and the fix is one more backup. "No data" would say the opposite.
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [{id: "ptr", name: LATEST}]}}))],
    [(url) => url.includes("alt=media"),
      () => reply(200, {body: JSON.stringify({file_id: "a", bytes: 1})})],
  ]);

  await assert.rejects(() => fetchPanelPack("tok", {fetchImpl}), (error) => {
    assert.equal(error.kind, "no-panel-pack");
    assert.match(error.message, /Back up once more/);
    return true;
  });
});


test("a truncated pack shows nothing rather than half the rows", async () => {
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [{id: "ptr", name: LATEST}]}}))],
    [(url) => url.includes("alt=media"), (url) => (url.includes("ptr")
      ? reply(200, {body: JSON.stringify({
          file_id: "a", bytes: 1,
          panel_pack: {file_id: "pack", name: PANEL_PACK, bytes: 4096},
        })})
      : reply(200, {body: "short"}))],
  ]);

  await assert.rejects(() => fetchPanelPack("tok", {fetchImpl}), (error) => {
    assert.equal(error.kind, "truncated");
    assert.match(error.message, /Nothing is shown/);
    return true;
  });
});


// ---- what the sha256 in the pointer was always supposed to prove -------------
//
// The engine hashes the archive before the upload, `latest.json` carries that hex
// string, and until `verifyStored` existed nothing on either side ever compared
// it with anything. Each test below is a way a corrupted upload becomes `latest`
// and is discovered on the day it is needed.

test("a mangled upload never becomes the latest backup", async () => {
  const uploaded = [];
  const deleted = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: [{id: "old-pointer", name: LATEST}]}}))],
    [isStart, (_url, init) => {
      uploaded.push(JSON.parse(init.body).name);
      return reply(200, {headers: {Location: SESSION}});
    }],
    [isPut, () => reply(200, {body: {id: "up", name: "bundle.zip"}})],
    // Drive holds the right NUMBER OF BYTES and a different file, which is the
    // only case a size comparison cannot see.
    [isGetFile, () => reply(200, {body: {
      id: "up", size: "7", sha256Checksum: "b".repeat(64)}})],
    [(_url, init) => init.method === "DELETE",
      (url) => { deleted.push(url); return reply(204); }],
  ]);

  await assert.rejects(() => backUp("tok", {
    archive: new Blob(["1234567"]), name: "bundle.zip",
    manifest: {sha256: "a".repeat(64)}, fetchImpl,
  }), (error) => {
    assert.equal(error.kind, "upload-corrupt");
    return true;
  });

  assert.equal(uploaded.includes(LATEST), false,
    "the pointer was written for an archive Drive stored differently, and a " +
    "restoring machine follows the pointer");
  assert.deepEqual(deleted, [],
    "the previous pointer was deleted too, so the last good backup is now " +
    "unreachable as well");
});


test("a truncated upload is refused even when Drive reports no checksum", async () => {
  // The failure that actually happens. A short write is the one fault a size
  // comparison catches for free, and catching it must not depend on a digest.
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, () => reply(200, {body: {id: "up", name: "bundle.zip"}})],
    [isGetFile, () => reply(200, {body: {id: "up", size: "3"}})],
  ]);

  await assert.rejects(() => backUp("tok", {
    archive: new Blob(["1234567890"]), name: "bundle.zip", fetchImpl,
  }), (error) => {
    assert.equal(error.kind, "upload-truncated");
    return true;
  });
});


test("a matching digest is reported as a digest, not as a shrug", async () => {
  // A guard that cannot say what it checked is a guard that can stop checking
  // without anyone noticing.
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, () => reply(200, {body: {id: "up", name: "bundle.zip"}})],
    [isGetFile, () => reply(200, {body: {
      // Upper case on purpose: a comparison that does not case-fold would refuse
      // a perfectly good backup over Google's choice of hex case.
      id: "up", size: "5", sha256Checksum: "A".repeat(64)}})],
  ]);

  const result = await backUp("tok", {
    archive: new Blob(["12345"]), name: "bundle.zip",
    manifest: {sha256: "a".repeat(64)}, fetchImpl,
  });

  assert.equal(result.verified_by, "sha256");
});


test("a backup Drive will not describe is reported as unverified", async () => {
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, () => reply(200, {headers: {Location: SESSION}})],
    [isPut, () => reply(200, {body: {id: "up", name: "bundle.zip"}})],
    [isGetFile, undescribed],
  ]);

  const result = await backUp("tok", {
    archive: new Blob(["12345"]), name: "bundle.zip",
    manifest: {sha256: "a".repeat(64)}, fetchImpl,
  });

  assert.equal(result.verified_by, "none",
    "Drive sent neither a size nor a checksum and the result claimed a check " +
    "had happened");
});


test("the check happens after the archive and before the pointer", async () => {
  // ORDER, which is this module's whole doctrine. A verification that ran after
  // the pointer would prove the archive intact and leave `latest.json` already
  // naming it if it were not.
  const order = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (url.includes("mimeType")
      ? reply(200, {body: {files: [{id: "folder-1"}]}})
      : reply(200, {body: {files: []}}))],
    [isStart, (_url, init) => {
      order.push(`upload:${JSON.parse(init.body).name}`);
      return reply(200, {headers: {Location: SESSION}});
    }],
    [isPut, () => reply(200, {body: {id: "up", name: "bundle.zip"}})],
    [isGetFile, () => { order.push("verify"); return undescribed(); }],
  ]);

  await backUp("tok", {
    archive: new Blob(["a"]), name: "bundle.zip",
    panelPack: new Blob(["p"]), fetchImpl,
  });

  assert.deepEqual(order,
    ["upload:bundle.zip", "verify", `upload:${PANEL_PACK}`, `upload:${LATEST}`],
    "the upload was not checked between the archive arriving and the pointer " +
    "naming it");
});


test("verifyStored asks for the fields it compares, on one file", async () => {
  // A request that does not ASK for sha256Checksum gets a response without one,
  // and every comparison below it silently becomes "none". Drive's `fields` is
  // exactly the kind of parameter a later tidy-up drops.
  const asked = [];
  const fetchImpl = scripted([
    [isGetFile, (url) => { asked.push(url); return undescribed(); }],
  ]);

  await verifyStored("tok", "file-42", {bytes: 10, fetchImpl});

  assert.equal(asked.length, 1);
  assert.match(asked[0], /\/files\/file-42\?/);
  assert.match(asked[0], /sha256Checksum/);
  assert.match(asked[0], /size/);
});
