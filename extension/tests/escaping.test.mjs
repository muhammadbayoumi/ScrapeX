// The panel's XSS boundary, pinned.
//
// Every scraped or user-entered value the panel interpolates into markup goes
// through esc() — the file says so in its own header — so esc() is the single
// line standing between a shop's product name and the panel's DOM. Until now
// nothing in this repository ran a line of JavaScript except the contract
// parity vectors: there is no package.json and no test runner, and S2 has
// asked for one since the extension was written. node:test is built in, and
// the CI job beside this one already has Node, so this costs nothing.
//
// esc() is read out of app.js rather than imported: app.js is the panel's
// entry point and imports chrome.* at module scope, so importing it here would
// need a browser. Reading the ONE line under test keeps the guard honest about
// what it covers — if that line moves, this fails loudly rather than silently
// testing a copy that has drifted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

function loadEsc() {
  const match = SOURCE.match(/const esc = (\([\s\S]*?\}\[c\]\)\);)/);
  assert.ok(match, "esc() is no longer where this guard reads it from in app.js");
  // eslint-disable-next-line no-new-func
  return new Function(`return ${match[1].replace(/;$/, "")}`)();
}

const esc = loadEsc();

test("the five characters that can break out of markup are escaped", () => {
  assert.equal(esc(`&<>"'`), "&amp;&lt;&gt;&quot;&#39;");
});

test("a script tag in a product name cannot become a script tag", () => {
  const attack = '<script>alert("x")</script>';
  const escaped = esc(attack);
  assert.ok(!escaped.includes("<script"), escaped);
  assert.equal(escaped, "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;");
});

test("an attribute break-out is escaped, quote and all", () => {
  // The shape that matters most here: the panel builds attributes by
  // interpolation, so a value that closes the quote owns the element.
  assert.equal(esc('" onerror="alert(1)'), "&quot; onerror=&quot;alert(1)");
});

test("the ampersand is escaped FIRST, so nothing is double-decoded", () => {
  // &lt; must survive as &amp;lt; — escaping < before & would produce &lt;
  // which a browser renders as a literal <, undoing the escape.
  assert.equal(esc("&lt;script&gt;"), "&amp;lt;script&amp;gt;");
});

test("null and undefined are empty text, never the words null or undefined", () => {
  assert.equal(esc(null), "");
  assert.equal(esc(undefined), "");
});

test("zero and false are kept, because they are values a shop can publish", () => {
  assert.equal(esc(0), "0");
  assert.equal(esc(false), "false");
});

test("Arabic and every other unescaped character pass through untouched", () => {
  assert.equal(esc("سلك نحاس 12mm"), "سلك نحاس 12mm");
});
