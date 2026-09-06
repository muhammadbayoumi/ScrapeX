// The request path is RUN here, not read.
//
// Everything else that guards this file is a source-text check: it can see that
// `throwOnHttpError: false` appears inside `raw()`, and it cannot see whether
// `request()` still honours the flag. MEASURED: replace the flag's read with
// `const throwOnHttpError = true;` and the whole repository stays green — 444
// node tests and every python guard — while `raw()` starts throwing on the 404s
// its two callers exist to interpret.
//
// WHAT BREAKS WHEN IT DOES. `upgradeDatabaseFromPanel` reads a 404 from
// /api/databases/upgrade as "this engine is too old" rather than as a failure,
// and the runtime-repair wiring does the same for /api/native/status. Under a
// throwing `raw()` neither reaches its branch, so an old engine is reported as a
// generic HTTP error and the owner is told nothing he can act on.
//
// backend.js binds `window.fetch` at import, so `window` is installed before the
// dynamic import below; a static import would hoist above the stub and throw.

import {test} from "node:test";
import assert from "node:assert/strict";

globalThis.window = globalThis;
globalThis.fetch = async () => new Response(null, {status: 500});

const backend = await import("../backend.js");
const {api, bytes, raw, activateBackend} = backend;

/** An engine that answers whatever the test says, and records what it was sent. */
function engine(reply) {
  const seen = [];
  globalThis.fetch = async (url, options = {}) => {
    seen.push({url: String(url), method: options.method || "GET"});
    return reply(String(url), options);
  };
  activateBackend("http://127.0.0.1:9");
  return seen;
}

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: {"content-type": "application/json"},
});

test("raw() hands back a 404 instead of throwing, which is the whole reason it exists",
     async () => {
  engine(() => json({detail: "no such route"}, 404));

  const response = await raw("/api/native/status");

  assert.equal(response.status, 404,
    "raw() threw or swallowed the status, so a caller cannot tell "
    + "'this engine is too old' from 'the request failed'");
  assert.equal(response.ok, false);
});

test("api() rejects on a 404 and carries the engine's own reason", async () => {
  engine(() => json({detail: "no bundle has been built"}, 404));

  await assert.rejects(() => api("/api/bundle/archive"), (error) => {
    assert.equal(error.status, 404);
    assert.equal(error.kind, "http");
    assert.equal(error.message, "no bundle has been built",
      "the engine's `detail` was dropped, leaving a status number and no cause "
      + "-- which is the defect this path was extracted to fix");
    return true;
  });
});

test("api() falls back to the status text when the body is not JSON", async () => {
  engine(() => new Response("<html>502</html>",
                            {status: 502, statusText: "Bad Gateway"}));

  await assert.rejects(() => api("/api/health"),
    (error) => error.status === 502 && error.kind === "http");
});

test("bytes() returns a body that is not JSON, and rejects when the engine refuses",
     async () => {
  engine(() => new Response(new Uint8Array([1, 2, 3]), {status: 200}));
  const blob = await bytes("/api/bundle/panel-pack");
  assert.equal(blob.size, 3, "the zip came back empty or as JSON");

  engine(() => json({detail: "the warehouse is locked"}, 500));
  await assert.rejects(() => bytes("/api/bundle/panel-pack"),
    (error) => error.status === 500 && error.message === "the warehouse is locked");
});

test("a 2xx is never an error, including the ones that are not 200", async () => {
  // `res.ok` covers 200-299. Pinned because a later change reads a 206 as the
  // SUCCESS case for a byte range, and a status check written as `=== 200`
  // would break it silently.
  //
  // Through `bytes()`, NOT `raw()`. The first version of this test used `raw()`,
  // which opts out of the status check entirely -- so it could not have failed
  // whatever `request()` did, and the mutation `res.status !== 200` sailed past
  // it. Found by running that mutation rather than by reading the test.
  engine(() => new Response(new Uint8Array([7]), {status: 206}));

  const body = await bytes("/api/bundle/archive");

  assert.equal(body.size, 1,
    "a 206 was treated as a failure, so a byte range cannot be read at all");
});

test("every request reaches the engine at its active address", async () => {
  const seen = engine(() => json({ok: true}));

  await api("/api/health");

  assert.equal(seen.length, 1);
  assert.ok(seen[0].url.startsWith("http://127.0.0.1:9/api/"),
    `the request went to ${seen[0].url} rather than through the active backend`);
});
