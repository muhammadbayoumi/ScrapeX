// The spreadsheet half of the owner's ruling, guarded.
//
// Most of these are properties gdrive.py had and its tests checked with mocked
// service clients. Two are not: the clear-before-write ordering, and RAW rather
// than USER_ENTERED. Both were in the Python and neither was asserted anywhere.

import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

import {
  ensureFolder, ensureSpreadsheet, openChosen, tabsOf, writeTab,
  MAX_EXPORT_ROWS,
} from "../sheets.js";

function reply(status, {body = null} = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {get: () => null},
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

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
const isCreate = (url, init) =>
  url.startsWith("https://www.googleapis.com/drive/v3/files?") &&
  init.method === "POST";


test("a spreadsheet is made once and found afterwards", async () => {
  const created = [];
  const fetchImpl = scripted([
    [isSearch, (url) => (created.length
      ? reply(200, {body: {files: [{id: "sheet-1", name: "ScrapeX Data"}]}})
      : reply(200, {body: {files: []}}))],
    [isCreate, (_url, init) => {
      created.push(JSON.parse(init.body).name);
      return reply(200, {body: {
        id: "sheet-1", name: "ScrapeX Data",
        webViewLink: "https://docs.google.com/spreadsheets/d/sheet-1/edit",
      }});
    }],
    [(url) => url.includes("/files/sheet-1"), () => reply(200, {body: {
      id: "sheet-1", name: "ScrapeX Data",
      webViewLink: "https://docs.google.com/spreadsheets/d/sheet-1/edit",
    }})],
  ]);

  const first = await ensureSpreadsheet("tok", "ScrapeX Data", {fetchImpl});
  const again = await ensureSpreadsheet("tok", "ScrapeX Data", {fetchImpl});

  assert.equal(first.created, true);
  assert.equal(again.created, false, "a second spreadsheet was made");
  assert.equal(created.length, 1);
  assert.equal(first.id, again.id);
});


test("the link comes from Drive rather than being assembled by hand", async () => {
  // gdrive.py built the URL from a template. That is correct today and is a
  // guess about a URL shape ScrapeX does not own; webViewLink is a field on a
  // response already being read.
  const fetchImpl = scripted([
    [isSearch, () => reply(200, {body: {files: []}})],
    [isCreate, () => reply(200, {body: {
      id: "s", name: "Book", webViewLink: "https://example.invalid/from-drive",
    }})],
  ]);

  const made = await ensureSpreadsheet("tok", "Book", {fetchImpl});

  assert.equal(made.url, "https://example.invalid/from-drive");
  const asked = fetchImpl.calls.find((c) => c.method === "POST");
  assert.match(asked.url, /webViewLink/,
               "the create request never asked for the link");
});


test("a tab is cleared before it is written", async () => {
  // THE ORDERING. An update alone overwrites only the cells it covers, so an
  // export with fewer rows than last time leaves the tail of the previous one
  // in place — and the owner reads a table whose bottom half is last week's
  // prices with nothing saying so.
  const order = [];
  const fetchImpl = scripted([
    [(url) => url.includes("fields=sheets"),
      () => reply(200, {body: {sheets: [{properties: {title: "prices"}}]}})],
    [(url) => url.endsWith(":clear"), () => { order.push("clear"); return reply(200, {body: {}}); }],
    [(_url, init) => init.method === "PUT", () => { order.push("write"); return reply(200, {body: {}}); }],
  ]);

  await writeTab("tok", "sheet-1", {
    tab: "prices", header: ["a"], rows: [["1"]], fetchImpl,
  });

  assert.deepEqual(order, ["clear", "write"],
    "the tab was written without being cleared first, or cleared after writing");
});


test("values are sent RAW, so a code beginning with = stays text", async () => {
  let sent = null;
  const fetchImpl = scripted([
    [(url) => url.includes("fields=sheets"),
      () => reply(200, {body: {sheets: [{properties: {title: "t"}}]}})],
    [(url) => url.endsWith(":clear"), () => reply(200, {body: {}})],
    [(_url, init) => init.method === "PUT", (url, init) => {
      sent = {url, body: JSON.parse(init.body)}; return reply(200, {body: {}});
    }],
  ]);

  await writeTab("tok", "s", {
    tab: "t", header: ["code"], rows: [["=SUM(A1)"], ["1-2"]], fetchImpl,
  });

  assert.match(sent.url, /valueInputOption=RAW/,
    "USER_ENTERED would turn a product code into a formula error and a " +
    "date-shaped string into a date");
  assert.deepEqual(sent.body.values, [["code"], ["=SUM(A1)"], ["1-2"]]);
});


test("a missing tab is added before anything is written to it", async () => {
  const added = [];
  const fetchImpl = scripted([
    [(url) => url.includes("fields=sheets"),
      () => reply(200, {body: {sheets: [{properties: {title: "other"}}]}})],
    [(url) => url.endsWith(":batchUpdate"), (_url, init) => {
      added.push(JSON.parse(init.body).requests[0].addSheet.properties.title);
      return reply(200, {body: {}});
    }],
    [(url) => url.endsWith(":clear"), () => reply(200, {body: {}})],
    [(_url, init) => init.method === "PUT", () => reply(200, {body: {}})],
  ]);

  await writeTab("tok", "s", {tab: "prices", header: ["a"], rows: [], fetchImpl});

  assert.deepEqual(added, ["prices"]);
});


test("too many rows is refused before a single cell is touched", async () => {
  const fetchImpl = scripted([]);   // any request at all throws

  await assert.rejects(() => writeTab("tok", "s", {
    tab: "t", header: ["a"],
    rows: Array.from({length: MAX_EXPORT_ROWS + 1}, () => ["x"]),
    fetchImpl,
  }), (error) => {
    assert.equal(error.kind, "too-many-rows");
    assert.match(error.message, /nothing was written/);
    return true;
  });
  assert.equal(fetchImpl.calls.length, 0, "a request went out anyway");
});


test("a name with an apostrophe does not break the search", async () => {
  // A workbook called O'Brien's is not a rare name, and an unescaped one turns
  // the query into a syntax error the owner cannot read.
  const fetchImpl = scripted([
    [isSearch, () => reply(200, {body: {files: []}})],
    [isCreate, () => reply(200, {body: {id: "s", name: "n", webViewLink: "u"}})],
  ]);

  await ensureFolder("tok", "O'Brien's \\ files", {fetchImpl});

  const query = new URL(fetchImpl.calls[0].url).searchParams.get("q");
  assert.ok(query.includes("O\\'Brien\\'s"), `not escaped: ${query}`);
  assert.ok(query.includes("\\\\"), `backslash not escaped: ${query}`);
});


test("a file the owner never chose is refused in their own terms", async () => {
  // drive.file cannot open a spreadsheet this app did not create and the owner
  // did not hand over. Google says 403; "permission denied" would send them to
  // check their account, which is not where the problem is.
  const fetchImpl = scripted([
    [() => true, () => reply(403, {body: {error: {message: "Insufficient permission"}}})],
  ]);

  await assert.rejects(() => openChosen("tok", "someone-elses", {fetchImpl}),
    (error) => {
      assert.equal(error.kind, "not-ours");
      assert.match(error.message, /only open spreadsheets it created/);
      return true;
    });
});


test("a chosen file that is not a spreadsheet is named, not written to", async () => {
  const fetchImpl = scripted([
    [() => true, () => reply(200, {body: {
      id: "d", name: "Budget.pdf", mimeType: "application/pdf", webViewLink: "u",
    }})],
  ]);

  await assert.rejects(() => openChosen("tok", "d", {fetchImpl}), (error) => {
    assert.equal(error.kind, "not-a-spreadsheet");
    assert.match(error.message, /Budget\.pdf/);
    return true;
  });
});


test("no token means no request", async () => {
  const fetchImpl = scripted([]);

  await assert.rejects(() => tabsOf("", "s", {fetchImpl}), (error) => {
    assert.equal(error.kind, "no-token");
    return true;
  });
  assert.equal(fetchImpl.calls.length, 0);
});


test("the sensitive spreadsheets scope is nowhere in the extension", async () => {
  // THE POINT OF THE WHOLE FILE. gdrive.py asked for it while claiming, two
  // lines above the list, that its choice avoided sensitive-scope review.
  // Google's own Sheets documentation lists drive.file as accepted, and
  // everything here touches only files this app made or the owner handed over.
  //
  // Asserted against the manifest and identity.js rather than left as a comment,
  // because the scope's whole cost is invisible until a store review.
  //
  // The first version read identity.js as TEXT and asked whether the scope
  // string appeared in it. CodeQL failed the build over that, correctly:
  // js/incomplete-url-substring-sanitization, "arbitrary hosts may come before
  // or after it". The rule is aimed at origin checks rather than at a test, but
  // the weakness it names is real here too — a substring search matches the
  // scope inside a comment, a URL that merely ends with it, or a longer scope
  // that contains it, and passes or fails for reasons that have nothing to do
  // with what the extension asks Google for.
  //
  // Importing the array and comparing elements is exact, and it reads the same
  // constant chrome.identity is handed rather than the file it lives in.
  const {SCOPES} = await import("../identity.js");
  const manifest = JSON.parse(readFileSync(
    new URL("../manifest.json", import.meta.url), "utf8"));

  const sensitive = "https://www.googleapis.com/auth/spreadsheets";
  assert.equal(manifest.oauth2.scopes.includes(sensitive), false,
    "the sensitive spreadsheets scope is back in the manifest");
  assert.equal(SCOPES.includes(sensitive), false,
    "the sensitive spreadsheets scope is back in identity.js");
  assert.ok(manifest.oauth2.scopes.includes(
    "https://www.googleapis.com/auth/drive.file"),
    "drive.file is gone, and nothing here can work without it");

  // The two lists are the same promise written twice — Chrome reads the
  // manifest, identity.js asks getAuthToken for its own array — so they must
  // agree, and neither being sensitive is only half the property.
  assert.deepEqual([...SCOPES].sort(), [...manifest.oauth2.scopes].sort(),
    "identity.js and the manifest ask Google for different things");
});


test("the Sheets host is declared in the manifest", async () => {
  // An extension cannot call a host it has not asked for, and the failure is a
  // network error with no explanation rather than a permission message.
  const manifest = JSON.parse(readFileSync(
    new URL("../manifest.json", import.meta.url), "utf8"));

  assert.ok(
    manifest.host_permissions.some((h) => h.startsWith("https://sheets.googleapis.com/")),
    "sheets.googleapis.com is not in host_permissions, so every call in " +
    "sheets.js fails before it leaves the panel");
});
