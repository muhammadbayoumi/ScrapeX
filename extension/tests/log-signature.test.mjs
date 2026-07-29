// The panel redraws its log on a 1.5-second poll, and rewriting innerHTML takes
// the selection away from whoever is trying to copy an error out of it. The
// redraw is now skipped when nothing changed, which is only safe if two
// DIFFERENT logs can never produce the same signature — so that is what this
// pins. Read out of app.js rather than imported: app.js touches chrome.* at
// module scope and would need a browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

const match = SOURCE.match(/function logSignatureOf\(entries\) \{[\s\S]*?\n\}/);
assert.ok(match, "logSignatureOf() is no longer where this guard reads it from");
// eslint-disable-next-line no-new-func
const logSignatureOf = new Function(`${match[0]}; return logSignatureOf;`)();

const line = (level, message) => ({ level, message });

test("an unchanged log has an unchanged signature", () => {
  const a = [line("info", "started"), line("warning", "3 pages skipped")];
  const b = [line("info", "started"), line("warning", "3 pages skipped")];
  assert.equal(logSignatureOf(a), logSignatureOf(b));
});

test("one new line changes it", () => {
  const before = [line("info", "started")];
  const after = [line("info", "started"), line("info", "done")];
  assert.notEqual(logSignatureOf(before), logSignatureOf(after));
});

test("the same message at a different level is a different log", () => {
  assert.notEqual(logSignatureOf([line("info", "x")]), logSignatureOf([line("error", "x")]));
});

test("reordering the same lines changes it", () => {
  const up = [line("info", "a"), line("info", "b")];
  const down = [line("info", "b"), line("info", "a")];
  assert.notEqual(logSignatureOf(up), logSignatureOf(down));
});

test("two different logs cannot collide by imitating the separator", () => {
  // The failure this optimisation could otherwise cause: a message that reads
  // like a joined pair would let one log impersonate another, and the panel
  // would stop showing a change that really happened.
  const one = [line("info", "a"), line("info", "b")];
  const two = [line("info", "ainfo b")];
  assert.notEqual(logSignatureOf(one), logSignatureOf(two));
});

test("an empty log has a signature of its own", () => {
  assert.equal(logSignatureOf([]), "");
  assert.notEqual(logSignatureOf([]), logSignatureOf([line("info", "")]));
});
