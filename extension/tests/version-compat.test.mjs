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

import { capabilityProblem, isOlder, parseVersion } from "../version.js";

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

test("the extension's own manifest is the version the file describes", () => {
  // The panel reads chrome.runtime.getManifest() and nothing else. If that file
  // fell behind, every verdict computed above would be computed about a version
  // nobody is running.
  const manifest = JSON.parse(readFileSync(join(HERE, "..", "manifest.json"), "utf8"));
  assert.equal(manifest.version, VECTORS.version);
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
