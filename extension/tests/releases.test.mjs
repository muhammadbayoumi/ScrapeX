// "We don't know the latest engine" has several causes and only one is a fault.
//
// A single "unavailable" for all of them is how an owner learns to ignore the
// row: he cannot tell a rate limit that clears itself in an hour from a broken
// build, so he checks neither. Each branch here is a different sentence, and
// each is asserted separately.
//
// THE FEED IS A LIST, NOT `/releases/latest`, and one case here is the whole
// reason. The public site carries SEVERAL products — ScrapeX and the Excel
// add-in, with more to come — so `/releases/latest` answers with whatever was
// published last by anyone. An add-in release cut after an engine release would
// have made the panel say "no engine has been released yet" with complete
// confidence and no truth in it.
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

import { readLatestRelease, latestEngineRelease, RELEASES_API, PUBLIC_REPO,
         PUBLIC_HOME, CHECK_TIMEOUT_MS } from "../releases.js";

const HERE = dirname(fileURLToPath(import.meta.url));

const headers = (pairs = {}) => ({ get: (k) => pairs[k.toLowerCase()] ?? null });

const engine = (version, extra = {}) => ({
  tag_name: `engine-v${version}`,
  published_at: "2026-08-06T09:00:00Z",
  html_url: `https://github.com/${PUBLIC_REPO}/releases/tag/engine-v${version}`,
  assets: [{ name: "scrapex-engine.exe", browser_download_url: "https://x/e.exe",
             size: 24_000_000 }],
  ...extra,
});

test("a published engine release is read with its version and installer", () => {
  const r = readLatestRelease(200, [engine("0.4.0")], headers());

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
  assert.equal(r.installer.name, "scrapex-engine.exe");
  assert.equal(r.installer.bytes, 24_000_000);
});

test("another product's release does not hide the engine's", () => {
  // THE CASE THE SHARED SITE CREATED. GitHub returns the list newest first, so
  // an add-in release cut this morning sits above an engine release cut last
  // week. Reading only the first entry would report "no engine yet".
  const r = readLatestRelease(200, [
    { tag_name: "addinx-v2.1.0", assets: [] },
    { tag_name: "scrapex-v0.9.0", assets: [] },
    engine("0.4.0"),
  ], headers());

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
});

test("the NEWEST engine release wins when there are several", () => {
  const r = readLatestRelease(200, [engine("0.5.0"), engine("0.4.0")], headers());

  assert.equal(r.version, "0.5.0");
});

test("a draft or a pre-release is not offered to anyone", () => {
  // A draft is not published and a pre-release is not for the owner. Offering
  // either as "the latest" sends him to install something nobody released.
  const r = readLatestRelease(200, [
    engine("0.9.0", { draft: true }),
    engine("0.8.0", { prerelease: true }),
    engine("0.4.0"),
  ], headers());

  assert.equal(r.version, "0.4.0");
});

test("a release with no installer attached says so instead of promising one", () => {
  // Discovering this at the moment of pressing Install is the failure.
  const r = readLatestRelease(200, [engine("0.4.0", { assets: [] })], headers());

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
  assert.equal(r.installer, null);
});

test("a site with no releases at all is not an error", () => {
  const r = readLatestRelease(200, [], headers());

  assert.equal(r.state, "none");
  assert.match(r.detail, /No engine has been released yet/);
});

test("a site with releases but none of them the engine's says which", () => {
  // Not "no engine yet" and not an error: the feed answered, and what it said
  // was about a different product. Naming it is what stops the owner hunting
  // for a fault that is not there.
  const r = readLatestRelease(200, [
    { tag_name: "addinx-v2.1.0", assets: [] },
  ], headers());

  assert.equal(r.state, "none");
  assert.match(r.detail, /addinx-v2\.1\.0/);
  assert.match(r.detail, /different product/);
  assert.equal(r.version, undefined);
});

test("a 404 means the site cannot be seen, not that nothing is released", () => {
  // The LIST endpoint answers 200 with [] when there are no releases, so a 404
  // is the repository itself being unreachable — renamed, or private. The
  // distinction matters: one sends the owner to wait and the other to look.
  const r = readLatestRelease(404, null, headers());

  assert.equal(r.state, "unreadable");
  assert.match(r.detail, /renamed, or is not public/);
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

test("the check carries its own timeout, and asks the right site", async () => {
  // THE POINT OF THE SEPARATE TIMEOUT: a stalled third party must never be
  // able to delay the panel the owner opened. Asserted on the call rather than
  // by waiting four seconds for it.
  let seen = null;
  await latestEngineRelease(async (url, options) => {
    seen = { url, options };
    return { status: 200, headers: headers(),
             json: async () => [{ tag_name: "engine-v1.0.0", assets: [] }] };
  });

  assert.equal(seen.url, RELEASES_API);
  assert.ok(seen.url.includes(PUBLIC_REPO));
  assert.ok(seen.options.signal, "no abort signal, so a stalled fetch hangs the check");
  assert.equal(CHECK_TIMEOUT_MS, 4000);
});

test("the public home is named once and every url is built from it", () => {
  // Three hard-coded copies of a repository name is three chances to move two
  // of them.
  assert.ok(RELEASES_API.includes(PUBLIC_REPO));
  assert.equal(PUBLIC_HOME, `https://github.com/${PUBLIC_REPO}`);
  assert.ok(!PUBLIC_REPO.endsWith("/ScrapeX"),
    "the feed points at the source repository, which goes private before the " +
    "first release — every user would then be told no engine has ever shipped");
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
