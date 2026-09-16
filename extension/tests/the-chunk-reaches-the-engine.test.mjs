// The one request in the panel that sends BYTES to the engine.
//
// `sendBundleChunk` is the whole wire between the half that holds the Google
// token and the half that holds the disk. Nothing else in backend.js posts a
// body that is not JSON, and the merge gate over #959 found this half of the
// path with no test at all.

import {test} from "node:test";
import assert from "node:assert/strict";

/** The panel's module graph needs a window and a backend address before it
 *  loads, which is why this file stubs both rather than importing first. */
async function withFakeEngine(answer) {
  const calls = [];
  globalThis.window = globalThis.window || {};
  globalThis.window.fetch = async (url, options = {}) => {
    calls.push({url: String(url), options});
    return answer;
  };
  globalThis.fetch = globalThis.window.fetch;
  globalThis.AbortController = globalThis.AbortController || class {
    constructor() { this.signal = {}; }
    abort() {}
  };
  const backend = await import("../backend.js");
  backend.activateBackend("http://127.0.0.1:8000");
  return {backend, calls};
}

function reply(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    headers: {get: () => null},
    json: async () => body,
  };
}

test("the offset, the size and the digest travel with the bytes", async () => {
  const {backend, calls} = await withFakeEngine(
    reply(200, {received: 64, total: 128, complete: false}));

  const said = await backend.sendBundleChunk(new Blob([new Uint8Array(64)]),
                                             {offset: 0, total: 128,
                                              sha256: "b".repeat(64)});

  assert.deepEqual(said, {received: 64, total: 128, complete: false});
  const sent = calls[calls.length - 1];
  assert.match(sent.url, /\/api\/storage\/receive-bundle\?/);
  assert.match(sent.url, /offset=0/);
  assert.match(sent.url, /total=128/);
  assert.match(sent.url, new RegExp("sha256=" + "b".repeat(64)));
  assert.equal(sent.options.method, "POST");
  assert.equal(sent.options.headers["content-type"], "application/octet-stream");
  assert.ok(sent.options.body instanceof Blob,
            "the piece was serialised instead of being sent as bytes");
});

test("the engine's own refusal reaches the caller, with its status", async () => {
  // THE PART A BARE `fetch` THREW AWAY, which backend.js records at length: a
  // request that moves half a gigabyte is the one that most needs to say why it
  // failed. Here the 409 is also the resume signal -- it names the offset the
  // engine is actually at.
  const {backend} = await withFakeEngine(reply(409, {
    detail: "This transfer is at 4096 bytes, not 0. Send from there, or start "
          + "again from zero."}));

  await assert.rejects(
    () => backend.sendBundleChunk(new Blob([new Uint8Array(8)]),
                                  {offset: 0, total: 128, sha256: "c".repeat(64)}),
    (error) => {
      assert.equal(error.status, 409);
      assert.match(error.message, /at 4096 bytes/);
      return true;
    });
});
