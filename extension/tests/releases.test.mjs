// "We don't know the latest engine" has several causes and only one is a fault.
//
// A single "unavailable" for all of them is how an owner learns to ignore the
// row: he cannot tell a check that will work tomorrow from a broken build, so
// he checks neither. Each branch here is a different sentence, and each is
// asserted separately.
//
// A MANIFEST FILE, NOT THE RELEASES API. This is the one thing taken wholesale
// from the Excel add-in's release path, which has polled its own version.json
// across seventy-six releases. Two reasons, and the second is the one that
// forced it:
//
//   * api.github.com allows SIXTY unauthenticated requests an hour PER IP.
//     One owner never notices. An office or a VPN behind a shared address
//     starts getting refusals that this code would report honestly and
//     uselessly, because nothing the owner can do fixes it.
//   * The hub carries SEVERAL products. Reading a list and filtering by tag
//     worked, but the manifest simply says which product it is about, and a
//     check is better than a convention.
//
// Everything is pure: a status and a body in, a verdict out. That is what makes
// the offline branch testable at all — a test that had to reach the network to
// prove what happens when the network is unreachable would be the least
// reliable test in the repository.

import { test } from "node:test";
import assert from "node:assert/strict";

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { readVersionManifest, latestEngineRelease, VERSION_MANIFEST,
         PUBLIC_REPO, PUBLIC_HOME, PRODUCT,
         CHECK_TIMEOUT_MS } from "../releases.js";

const HERE = dirname(fileURLToPath(import.meta.url));

const manifest = (version, extra = {}) => ({
  product: PRODUCT,
  version,
  tag: `engine-v${version}`,
  published_at: "2026-08-06T09:00:00Z",
  release_url: `https://github.com/${PUBLIC_REPO}/releases/tag/engine-v${version}`,
  minimum_extension_version: "0.2.0",
  protocol_version: 1,
  installer: {
    name: "scrapex-engine.exe",
    url: `https://github.com/${PUBLIC_REPO}/releases/download/engine-v${version}/scrapex-engine.exe`,
    bytes: 24_000_000,
    sha256: "a".repeat(64),
  },
  ...extra,
});

test("a published engine release is read with its version and installer", () => {
  const r = readVersionManifest(200, manifest("0.4.0"));

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
  assert.equal(r.installer.name, "scrapex-engine.exe");
  assert.equal(r.installer.bytes, 24_000_000);
  assert.equal(r.installer.sha256.length, 64);
});

test("the compatibility floor travels with the release, before anything is installed", () => {
  // THE REASON THE MANIFEST CARRIES MORE THAN A VERSION. Without these two
  // numbers the panel can only discover that a release refuses to talk to it
  // AFTER downloading and installing it. With them it can say so in the row.
  const r = readVersionManifest(200, manifest("0.4.0"));

  assert.equal(r.minimumExtension, "0.2.0");
  assert.equal(r.protocol, 1);
});

test("the add-in's manifest is not read as the engine's", () => {
  // THE CASE THE SHARED HUB CREATES. `Xadd-in/json/version.json` sits one
  // folder away and has the same shape. A path typo would otherwise produce a
  // confident, wrong version — the worst of the possible failures, because it
  // looks exactly like success.
  const r = readVersionManifest(200, {
    product: "mbix-addin", version: "1.0.1.76",
  });

  assert.equal(r.state, "unreadable");
  assert.match(r.detail, /mbix-addin/);
  assert.match(r.detail, /not the ScrapeX engine/);
  assert.equal(r.version, undefined);
});

test("a manifest that names no usable version is refused rather than shown", () => {
  // An empty string rendered into the row reads as "the latest engine is ",
  // and a four-part add-in version rendered there reads as an upgrade that
  // does not exist.
  for (const bad of ["", "1.0.1.76", "v0.4.0", "latest", null]) {
    const r = readVersionManifest(200, manifest("0.4.0", { version: bad }));
    assert.equal(r.state, "unreadable", `${bad} was accepted as a version`);
  }
});

test("a release with no installer attached says so instead of promising one", () => {
  // Discovering this at the moment of pressing Install is the failure.
  const r = readVersionManifest(200, manifest("0.4.0", { installer: null }));

  assert.equal(r.state, "ok");
  assert.equal(r.version, "0.4.0");
  assert.equal(r.installer, null);
});

test("no manifest at all means nothing has been released, and is not an error", () => {
  // THE STATE EVERY MACHINE IS IN BEFORE THE FIRST RELEASE, and the one the
  // old feed could not express: the list endpoint answered 200 with [], so a
  // 404 there meant the repository was unreachable. Here the file is simply
  // not written until the first release writes it, and its absence is the
  // true and complete answer.
  const r = readVersionManifest(404, null);

  assert.equal(r.state, "none");
  assert.match(r.detail, /No engine has been released yet/);
});

test("anything else is unreadable and names the number", () => {
  const r = readVersionManifest(500, null);

  assert.equal(r.state, "unreadable");
  assert.match(r.detail, /500/);
});

test("a 200 carrying something that is not a manifest is unreadable", () => {
  // What a proxy, a captive portal or a CDN error page actually returns: 200,
  // with HTML. `json()` fails, the reader is handed null, and the row must not
  // claim an engine.
  for (const body of [null, "<html>", 42, []]) {
    const r = readVersionManifest(200, body);
    assert.equal(r.state, "unreadable", `${JSON.stringify(body)} was accepted`);
  }
});

test("nobody answering is offline, and says the engine you have keeps working", async () => {
  const r = await latestEngineRelease(async () => { throw new Error("ENOTFOUND"); });

  assert.equal(r.state, "offline");
  assert.match(r.detail, /keeps working/);
});

test("the check carries its own timeout, asks the right file, and refuses a cache", async () => {
  // THE POINT OF THE SEPARATE TIMEOUT: a stalled third party must never be
  // able to delay the panel the owner opened. Asserted on the call rather than
  // by waiting four seconds for it.
  //
  // AND THE POINT OF `no-cache`: this file is REWRITTEN IN PLACE on every
  // release. A CDN copy of yesterday's would hide a release that exists, which
  // is the one failure the whole check exists to prevent.
  let seen = null;
  await latestEngineRelease(async (url, options) => {
    seen = { url, options };
    return { status: 200, json: async () => manifest("1.0.0") };
  });

  assert.equal(seen.url, VERSION_MANIFEST);
  assert.ok(seen.url.startsWith("https://raw.githubusercontent.com/"),
    "the check reads api.github.com, which allows sixty unauthenticated " +
    "requests an hour per IP — a shared address starts being refused");
  assert.ok(seen.url.includes(PUBLIC_REPO));
  assert.ok(seen.options.signal, "no abort signal, so a stalled fetch hangs the check");
  assert.equal(seen.options.cache, "no-cache");
  assert.equal(CHECK_TIMEOUT_MS, 4000);
});

test("the public home is named once and every url is built from it", () => {
  // Three hard-coded copies of a repository name is three chances to move two
  // of them.
  assert.ok(VERSION_MANIFEST.includes(PUBLIC_REPO));
  assert.equal(PUBLIC_HOME, `https://github.com/${PUBLIC_REPO}`);
  assert.ok(!PUBLIC_REPO.endsWith("/ScrapeX"),
    "the feed points at the source repository, which goes private before the " +
    "first release — every user would then be told no engine has ever shipped");
});

test("the manifest lets the extension reach the feed at all", () => {
  // WITHOUT THIS THERE IS NO SYMPTOM TO SEE. Chrome refuses the request, the
  // reader's own catch-all turns the refusal into "offline", and the Engines
  // page says the endpoint could not be reached — on a machine whose network
  // is perfectly fine. Every panel test still passes, because the harness stubs
  // fetch and never asks Chrome for permission.
  //
  // Caught by mutation: removing the host permission was SILENT across the
  // whole suite until this assertion existed.
  const shipped = JSON.parse(
    readFileSync(join(HERE, "..", "manifest.json"), "utf8"));
  const host = new URL(VERSION_MANIFEST).origin + "/*";

  assert.ok((shipped.host_permissions || []).includes(host),
    `manifest.host_permissions does not include ${host}, so Chrome refuses the ` +
    `release check and the page reports a network that is not broken`);
});
