// The robots look says, once and as a warning, that the crawl will pause.
//
// #1585: a robots.txt the site cannot serve (a 5xx, or no answer at all) PAUSES
// every crawl of the site -- RFC 9309 §2.3.1.4, `ES-2` in
// docs/ENGINEERING-SOURCES.md. The route reports it as `unreachable` and its
// summary says so. The box drew it in the plain style, and then repeated the same
// sentence under "On a disallowed path today:", which reads as if only those
// paths were affected.
//
// READ AS SOURCE TEXT, like `appearance-applies-only-colour.test.mjs`:
// `extension/app.js` exports nothing and touches `chrome.*` at module scope, so the
// one function is evaluated alone in a `vm` context holding only what it reads. The
// regex is asserted, so renaming the function fails loudly.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");
const BODY = SOURCE.match(/^async function lookAtRobots\(\) \{[\s\S]*?\n\}/m);
assert.ok(BODY, "lookAtRobots is no longer where this guard reads it from in app.js");

// `$`, `state` and `api` are the context's globals, standing in for the panel's.
const make = ($, state, api) =>
  vm.runInNewContext(`${BODY[0]}\nlookAtRobots;`, {$, state, api});

async function look(report) {
  const classes = new Set();
  const box = {
    textContent: "",
    classList: {toggle: (name, on) => (on ? classes.add(name) : classes.delete(name))},
  };
  const button = {disabled: false};
  const elements = {
    "source-edit-robots-report": box,
    "source-edit-robots-look": button,
  };
  const run = make((id) => elements[id], {editingSourceKey: "SHOP"},
                   async () => report);
  await run();
  return {text: box.textContent, warn: classes.has("warn"), button};
}

const PAUSE = "shop.test: robots.txt could not be reached (HTTP 503). RFC 9309 "
  + "§2.3.1.4 says a crawler must then treat the whole site as disallowed, so this "
  + "site's run is paused and none of its pages is fetched; press Resume once "
  + "robots.txt answers again";

test("an unreachable robots.txt is drawn as a warning", async () => {
  const shown = await look({
    summary: "shop.test: robots.txt could not be reached (HTTP 503) — a crawl of "
      + "this site pauses here; press Resume once robots.txt answers again (RFC 9309)",
    unreachable: true,
    would_block_everything: false,
    on_a_disallowed_path: {may_fetch: false, delay_s: null, reason: PAUSE},
  });

  assert.equal(shown.warn, true);
  assert.match(shown.text, /could not be reached/);
  assert.equal(shown.button.disabled, false);
});

test("the pause is said once, not again under the disallowed-path heading", async () => {
  const shown = await look({
    summary: "shop.test: robots.txt could not be reached (HTTP 503) — a crawl of "
      + "this site pauses here",
    unreachable: true,
    on_a_disallowed_path: {may_fetch: false, delay_s: null, reason: PAUSE},
  });

  assert.doesNotMatch(shown.text, /On a disallowed path today/);
  assert.equal(shown.text.match(/could not be reached/g).length, 1, shown.text);
});

test("a readable file still says what a disallowed path gets, unwarned", async () => {
  const shown = await look({
    summary: "shop.test: allows this source, asks for no delay",
    unreachable: false,
    would_block_everything: false,
    on_a_disallowed_path: {may_fetch: true, delay_s: null,
                           reason: "shop.test: allowed under the tool default"},
  });

  assert.equal(shown.warn, false);
  assert.match(shown.text, /On a disallowed path today: shop\.test: allowed/);
});

test("a 4xx is not a pause: it keeps the disallowed-path line and no warning", async () => {
  const shown = await look({
    summary: "shop.test: robots.txt could not be read (HTTP 403)",
    unreachable: false,
    would_block_everything: false,
    on_a_disallowed_path: {may_fetch: true, delay_s: null,
                           reason: "shop.test: HTTP 403 — nothing to obey"},
  });

  assert.equal(shown.warn, false);
  assert.match(shown.text, /On a disallowed path today/);
});

test("obeying a site that disallows everything still warns", async () => {
  const shown = await look({
    summary: "shop.test: disallows the pages this source crawls",
    unreachable: false,
    would_block_everything: true,
    on_a_disallowed_path: {may_fetch: false, delay_s: null, reason: "not fetched"},
  });

  assert.equal(shown.warn, true);
});
