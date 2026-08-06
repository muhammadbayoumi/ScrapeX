// "We don't know the latest engine" has four causes and only one is a fault.
//
// A single "unavailable" for all of them is how an owner learns to ignore the
// row: he cannot tell a rate limit that clears itself in an hour from a broken
// build, so he checks neither. Each branch here is a different sentence, and
// each is asserted separately.
//
// Everything is pure: a status, a body and headers in, a verdict out. That is
// what makes the offline and rate-limited branches testable at all — a test
// that had to reach GitHub to prove what happens when GitHub cannot be reached
// would be the least reliable test in the repository.

import { test } from "node:test";
import assert from "node:assert/strict";

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { readLatestRelease, latestEngineRelease, RELEASES_API, CHECK_TIMEOUT_MS }
  from "../releases.js";

const HERE = dirname(fileURLToPath(import.meta.url));

const headers = (pairs = {}) => ({ get: (k) => pairs[k.toLowerCase()] ?? null });

test("a published engine release is read with its version and installer", () => {
  const r = readLatestRelease(200, {
    tag_name: "engine-v0.4.0",
    published_at: "2026-08-06T09:00:00Z",
    html_url: "https://github.com/muhammadbayoumi/ScrapeX/releases/tag/engine-v0.4.0",
    assets: [{ name: "scrapex-engine.exe", browser_download_url: "https://x/e.exe",
               size: 24_000_000 }],
  }, headers());

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
  assert.equal(r.installer.name, "scrapex-engine.exe");
  assert.equal(r.installer.bytes, 24_000_000);
});

test("a release with no installer attached says so instead of promising one", () => {
  // Discovering this at the moment of pressing Install is the failure. A
  // release with nothing to install is a real state and belongs on the page.
  const r = readLatestRelease(200, { tag_name: "engine-v0.4.0", assets: [] }, headers());

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
  assert.equal(r.installer, null);
});

test("a repository with no releases is not an error", () => {
  // GitHub answers 404 on /releases/latest when nothing has been released.
  // That is the true and complete answer, and showing it in red would send the
  // owner to fix something that is working.
  const r = readLatestRelease(404, null, headers());

  assert.equal(r.state, "none");
  assert.match(r.detail, /No engine has been released yet/);
});

test("the extension's own release is not the engine's", () => {
  // Decision 21 gives the two products separate tags on one repository. A
  // `scrapex-v…` tag on this feed says nothing at all about the engine, and
  // reading its number as the engine's would be a confident wrong answer.
  const r = readLatestRelease(200, { tag_name: "scrapex-v0.9.0", assets: [] }, headers());

  assert.equal(r.state, "none");
  assert.match(r.detail, /not an engine release/);
  assert.equal(r.version, undefined);
});

test("a rate limit is told apart from a failure, because it clears itself", () => {
  const r = readLatestRelease(403, {}, headers({ "x-ratelimit-remaining": "0" }));

  assert.equal(r.state, "rate-limited");
  assert.match(r.detail, /nothing is wrong with the engine/);
});

test("a 403 that is not a rate limit is not called one", () => {
  const r = readLatestRelease(403, {}, headers({ "x-ratelimit-remaining": "57" }));

  assert.equal(r.state, "unreadable");
});

test("anything else is unreadable and names the number", () => {
  const r = readLatestRelease(500, null, headers());

  assert.equal(r.state, "unreadable");
  assert.match(r.detail, /500/);
});

test("nobody answering is offline, and says the engine you have keeps working", async () => {
  const r = await latestEngineRelease(async () => { throw new Error("ENOTFOUND"); });

  assert.equal(r.state, "offline");
  assert.match(r.detail, /keeps working/);
});

test("the check carries its own timeout, and asks the right repository", async () => {
  // THE POINT OF THE SEPARATE TIMEOUT: a stalled third party must never be
  // able to delay the panel the owner opened. Asserted on the call rather than
  // by waiting four seconds for it.
  let seen = null;
  await latestEngineRelease(async (url, options) => {
    seen = { url, options };
    return { status: 200, headers: headers(),
             json: async () => ({ tag_name: "engine-v1.0.0", assets: [] }) };
  });

  assert.equal(seen.url, RELEASES_API);
  assert.ok(seen.options.signal, "no abort signal, so a stalled fetch hangs the check");
  assert.equal(CHECK_TIMEOUT_MS, 4000);
});

test("the manifest lets the extension reach the feed at all", () => {
  // WITHOUT THIS THERE IS NO SYMPTOM TO SEE. Chrome refuses the request, the
  // reader's own catch-all turns the refusal into "offline", and the Engines
  // page says GitHub could not be reached — on a machine whose network is
  // perfectly fine. Every panel test still passes, because the harness stubs
  // fetch and never asks Chrome for permission.
  //
  // Caught by mutation: removing the host permission was SILENT across the
  // whole suite until this assertion existed.
  const manifest = JSON.parse(
    readFileSync(join(HERE, "..", "manifest.json"), "utf8"));
  const host = new URL(RELEASES_API).origin + "/*";

  assert.ok((manifest.host_permissions || []).includes(host),
    `manifest.host_permissions does not include ${host}, so Chrome refuses the ` +
    `release check and the page reports a network that is not broken`);
});
