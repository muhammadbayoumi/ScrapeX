// The archive must not be spliced together out of two different backups.
//
// `/api/bundle/archive` re-resolves "the newest zip on disk" on EVERY request
// (scrapex/webui/app.py:3253). Uploading 541,531,989 bytes takes ~130 requests
// over minutes, so a second panel window taking a backup mid-upload finishes a
// new build and every later chunk comes from a DIFFERENT file. The length guard
// cannot see it: when the new archive is longer, every chunk is still exactly
// the size asked for, the total still matches what the pointer records, and the
// check button then reports the spliced result as complete. It would be found
// at restore, which is the worst possible time.
//
// These are the first tests in this repository that run backend.js rather than
// read it, and the first that send a Range header at all. backend.js binds
// `window.fetch` at import, so `window` is installed before the dynamic import
// below -- a static import would hoist above the stub and throw.

import {test} from "node:test";
import assert from "node:assert/strict";

globalThis.window = globalThis;
globalThis.fetch = async () => new Response(null, {status: 500});

const backend = await import("../backend.js");
const {sourceFor, range, activateBackend} = backend;

const MB = 1024 * 1024;

/** An engine holding one archive at a time, which a test may swap under it. */
function engine(builds, first) {
  const state = {name: first, asked: []};
  globalThis.fetch = async (url, options = {}) => {
    const headers = options.headers || {};
    const build = builds[state.name];
    state.asked.push({url: String(url), headers: {...headers}});
    const wants = /bytes=(\d+)-(\d+)/.exec(headers.Range || "");
    // Starlette answers the WHOLE body when If-Range no longer matches, which
    // is the behaviour this fix leans on. Measured on starlette 1.3.1:
    // FileResponse._should_use_range compares against etag or last-modified.
    // `{etag: undefined}` would set the LITERAL string "undefined", which is a
    // validator as far as the code under test can tell -- so an engine that
    // sends none must send none.
    const validator = build.etag ? {etag: build.etag} : {};
    const stale = headers["If-Range"] && headers["If-Range"] !== build.etag;
    if (!wants || stale || !build.ranges) {
      return new Response(new Uint8Array(Math.min(build.size, 8)), {
        status: 200, headers: validator,
      });
    }
    const start = Number(wants[1]);
    const end = Math.min(Number(wants[2]) + 1, build.size);
    return new Response(new Uint8Array(Math.max(0, end - start)), {
      status: 206,
      headers: {
        "content-range": `bytes ${start}-${end - 1}/${build.size}`,
        ...validator,
      },
    });
  };
  return state;
}

const A = {size: 541531989, etag: '"build-a"', ranges: true};
const B = {size: 560000000, etag: '"build-b"', ranges: true};

test("the size comes from the engine's Content-Range, and the probe asks for one byte",
     async () => {
  const state = engine({a: A}, "a");
  activateBackend("http://127.0.0.1:9");

  const source = await sourceFor("/api/bundle/archive");

  assert.equal(source.size, 541531989);
  assert.equal(state.asked[0].headers.Range, "bytes=0-0",
    "the probe must not download the archive to find out how long it is");
});

test("every chunk carries If-Range, so the engine can refuse to splice", async () => {
  const state = engine({a: A}, "a");
  activateBackend("http://127.0.0.1:9");

  const source = await sourceFor("/api/bundle/archive");
  await source.chunk(0, 4 * MB);

  assert.equal(state.asked[1].headers["If-Range"], '"build-a"',
    "without If-Range the engine serves byte N of whatever archive is newest "
    + "NOW, and this side cannot tell that from byte N of the one it started on");
});

test("A REBUILD UNDER THE UPLOAD IS REFUSED, and the refusal names what to do",
     async () => {
  // The exact scenario: chunks are flowing from build A when a second window's
  // backup finishes build B, which is LONGER -- so every length check still
  // passes and only the pinned representation can catch it.
  const state = engine({a: A, b: B}, "a");
  activateBackend("http://127.0.0.1:9");

  const source = await sourceFor("/api/bundle/archive");
  await source.chunk(0, 4 * MB);
  state.name = "b";

  await assert.rejects(
    () => source.chunk(4 * MB, 8 * MB),
    (error) => error.kind === "changed-under-upload"
               && /Take the backup again/.test(error.message));
});

test("and it is refused even when the engine sends no validator at all", async () => {
  // Second, independent catch: the total on every 206. An engine whose etag
  // survives a rebuild, or which sends none, still cannot slip a different file
  // past a length it never agreed to.
  const noEtag = {size: 541531989, etag: undefined, ranges: true};
  const grown = {size: 560000000, etag: undefined, ranges: true};
  const state = engine({a: noEtag, b: grown}, "a");
  activateBackend("http://127.0.0.1:9");

  const source = await sourceFor("/api/bundle/archive");
  state.name = "b";

  await assert.rejects(
    () => source.chunk(0, 4 * MB),
    (error) => error.kind === "changed-under-upload"
               && /541531989/.test(error.message) && /560000000/.test(error.message));
});

test("the old length check alone would have accepted the splice", async () => {
  // Proves the guard above is load-bearing rather than decorative: the chunk
  // that gets refused is FULL LENGTH, so `chunk.size !== wanted` -- everything
  // this code had before -- sees nothing wrong with it.
  const state = engine({a: A, b: B}, "a");
  activateBackend("http://127.0.0.1:9");

  const source = await sourceFor("/api/bundle/archive");
  state.name = "b";
  const spliced = await range("/api/bundle/archive", 0, 4 * MB);

  assert.equal(spliced.size, 4 * MB,
    "the chunk from the WRONG archive is exactly the size asked for, which is "
    + "why a length check cannot be the only guard");
});

test("an engine that will not serve ranges says so by kind, so the panel can fall back",
     async () => {
  const state = engine({a: {size: 4096, etag: '"x"', ranges: false}}, "a");
  activateBackend("http://127.0.0.1:9");

  await assert.rejects(
    () => sourceFor("/api/bundle/archive"),
    (error) => error.kind === "no-range" && error.status === 200);
});

test("last-modified stands in when the engine sends no etag", async () => {
  globalThis.fetch = async (url, options = {}) => {
    const headers = options.headers || {};
    if (headers.Range === "bytes=0-0") {
      return new Response(new Uint8Array(1), {
        status: 206,
        headers: {
          "content-range": "bytes 0-0/100",
          "last-modified": "Thu, 03 Sep 2026 13:17:06 GMT",
        },
      });
    }
    assert.equal(headers["If-Range"], "Thu, 03 Sep 2026 13:17:06 GMT",
      "Starlette accepts either validator; dropping this one leaves engines "
      + "that send no etag with no protection at all");
    return new Response(new Uint8Array(50), {
      status: 206, headers: {"content-range": "bytes 0-49/100"},
    });
  };
  activateBackend("http://127.0.0.1:9");

  const source = await sourceFor("/api/bundle/archive");
  const chunk = await source.chunk(0, 50);
  assert.equal(chunk.size, 50);
});
