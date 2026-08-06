// The compatibility rule exists in two languages and only one of them is
// Python. Nothing but a shared vector file can notice when the copies stop
// agreeing — and disagreement here is not a wrong pixel: it is the panel
// allowing a feature the engine will refuse, or refusing one it would have run.
//
// contracts/version-vectors.json is written by `python -m scrapex.cli
// export-version` from scrapex/version.py. Python asserts it reproduces the file
// (tests/test_version.py); this asserts the JavaScript copy does too. Same
// guardrail contract/parity/ puts under the normalize vectors.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { CAPABILITY_REPORTING_SINCE, capabilityProblem, isOlder,
         parseVersion } from "../version.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const VECTORS = JSON.parse(
  readFileSync(join(HERE, "..", "..", "contracts", "version-vectors.json"), "utf8"));

test("every frozen case produces the same sentence in both languages", () => {
  assert.ok(VECTORS.cases.length >= 4, "the vector file lost its cases");
  for (const c of VECTORS.cases) {
    const problem = capabilityProblem(c.key, {
      extensionVersion: c.extension_version,
      engineVersion: c.engine_version,
      deployed: c.deployed,
      updateInstructions: c.update_instructions,
    });
    assert.equal(problem, c.problem, `case "${c.name}" disagrees with Python`);
  }
});

test("the extension's manifest is its OWN number, and new enough to be run", () => {
  // THE ASSERTION THAT EXPIRED, and the reason this now asserts the opposite of
  // what it used to.
  //
  // It read `assert.equal(manifest.version, VECTORS.version)`, and
  // VECTORS.version is the ENGINE's number (scrapex/version.py: export_vectors
  // returns {"version": VERSION, ...}). That was right while both shipped from
  // one checkout. It stopped being right when the owner settled two release
  // paths — PLATFORM-PLAN Decision 21: the extension is tagged and uploaded to
  // the Chrome Web Store, the engine is tagged and published to GitHub
  // Releases, and NEITHER TRIGGERS THE OTHER.
  //
  // MEASURED, in both directions: bump only extension/manifest.json to 0.3.0,
  // which is exactly what a store release is, and this file failed with
  // `actual: '0.3.0', expected: '0.2.0'`. Bump only the engine and it failed
  // the other way. CI refused the release path the plan is built on, and the
  // Python side had already dropped this equality on 2026-08-05
  // (tests/test_version.py: test_the_extension_carries_its_own_number_and_may_differ).
  // The JavaScript copy never followed.
  //
  // What is still true, and is what this asserts instead: the manifest must
  // carry a real MAJOR.MINOR.PATCH — Chrome refuses anything else — and it must
  // not be older than the minimum the engine will talk to, because a build the
  // engine would refuse must never be the one uploaded to the store.
  const manifest = JSON.parse(readFileSync(join(HERE, "..", "manifest.json"), "utf8"));

  assert.match(manifest.version, /^\d+\.\d+\.\d+$/,
    "Chrome requires a numeric MAJOR.MINOR.PATCH in the manifest");
  assert.deepEqual(parseVersion(manifest.version).length, 3);
  assert.ok(!isOlder(manifest.version, VECTORS.minimum_extension_version),
    `the manifest says ${manifest.version}, older than the ` +
    `${VECTORS.minimum_extension_version} the engine will talk to — this build ` +
    `would be refused by the engine it ships beside`);
});

test("versions order numerically, not as text", () => {
  assert.ok(isOlder("0.9.0", "0.10.0"), "0.10.0 sorts before 0.9.0 as text");
  assert.ok(!isOlder("1.0.1", "1.0.0"));
  assert.ok(!isOlder("1.0.0", "1.0.0"));
  assert.deepEqual(parseVersion("1.2.3"), [1, 2, 3]);
});

test("a version that is not a version is refused, never read as very old", () => {
  // Treating an unreadable number as 0.0.0 would announce every feature as
  // missing and send the owner to reload an extension that is current.
  for (const bad of ["", "0.2", "0.2.0.1", "v0.2.0", "0.2.x"]) {
    assert.throws(() => parseVersion(bad), /not a ScrapeX version/);
  }
});


test("the reporting floor is the contract's, not a second opinion", () => {
  assert.equal(CAPABILITY_REPORTING_SINCE, VECTORS.capability_reporting_since,
    "extension/version.js and scrapex/version.py disagree about the first " +
    "version that reports capabilities; the remedy sentence would then name " +
    "a version one side does not believe in");
});

test("no refusal ever prescribes a version you already have", () => {
  // The owner's card said "Update the engine to 0.1.0" while showing 0.1.0
  // installed. A remedy that has already been carried out is not a remedy, and
  // every sentence these functions produce is a remedy.
  for (const c of VECTORS.cases) {
    const problem = capabilityProblem(c.key, {
      extensionVersion: c.extension_version,
      engineVersion: c.engine_version,
      deployed: c.deployed,
      updateInstructions: c.update_instructions || "",
    });
    if (!problem) continue;
    const told = problem.match(/[Uu]pdate the engine to ([0-9]+\.[0-9]+\.[0-9]+)/);
    if (!told) continue;
    assert.ok(isOlder(c.engine_version, told[1]),
      `"${c.name}" tells the owner to update the engine to ${told[1]} ` +
      `while it is already ${c.engine_version}`);
  }
});
