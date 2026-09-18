// The panel tells the engine what browser it runs in, and the crawl uses it.
//
// The engine named this tool in every request — `ScrapeX/0.1 (+contact: owner)`
// — so every site a published installation touched was told who was crawling
// it. The name bought nothing back: "owner" is no address, and no site keys a
// robots rule to a name it has never seen. The engine's fallback is now a fixed
// Chrome string; this file covers the half that makes it the REAL one, so the
// agent follows Chrome's own updates instead of ageing into a signature, and a
// site watching one IP browse and crawl sees one agent rather than two.
//
// Two things are easy to get wrong here and both are tested:
//
//   * it must WRITE ONLY ON CHANGE. A POST costs the engine's write lock, which
//     a running crawl holds. Chrome's agent moves every few weeks, so comparing
//     first turns one write per panel open into a handful per year.
//   * it must never fail silently. If the report cannot be made the crawl still
//     names no tool — it falls back — so the failure is invisible in the result
//     and has to be recorded to be diagnosable at all.
//
// READ AS SOURCE TEXT, like `healthy.test.mjs` next door and for the same
// reason: `extension/app.js` exports nothing and touches `chrome.*` at module
// scope, so importing it here would need a browser. The regex is asserted, so
// renaming the function fails loudly rather than leaving a guard reading a copy
// that has drifted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

const PATTERN =
  /^async function reportBrowserUserAgent\(engineReady\) \{[\s\S]*?\n\}/m;
const BODY = SOURCE.match(PATTERN);
assert.ok(BODY, "reportBrowserUserAgent is no longer where this guard reads it "
  + "from in app.js");

// Extracted rather than stubbed, so the header value this file measures is
// byte-for-byte the one the panel sends. A hand-written formatter here would be
// a second copy of the rule, and a test of the wrong one.
const HINTS = SOURCE.match(/^function reportedClientHints\(\) \{[\s\S]*?\n\}/m);
assert.ok(HINTS, "reportedClientHints is no longer where this guard reads it "
  + "from in app.js");

const CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
  + "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36";
// The shape `navigator.userAgentData.brands` really has, GREASE entry and all.
const BRANDS = [
  {brand: "Chromium", version: "141"},
  {brand: "Google Chrome", version: "141"},
  {brand: "Not?A_Brand", version: "24"},
];
const HINTS_SENT = '"Chromium";v="141", "Google Chrome";v="141", '
  + '"Not?A_Brand";v="24"';

// `navigator` arrives as a PARAMETER and shadows the global, which is the only
// reason a function written for a Chrome side panel runs under `node --test`.
const panelFor = (() => {
  // eslint-disable-next-line no-new-func
  const make = new Function(
    "navigator", "api", "post", "markStartup", "capabilityRefusal",
    HINTS[0] + "\n" + BODY[0] + "\nreturn reportBrowserUserAgent;");
  return ({agent = CHROME, brands = BRANDS, stored, storedHints,
           refusal = "", fail = null, engineReady = Promise.resolve()} = {}) => {
    const posted = [];
    const marks = [];
    const bare = make(
      {userAgent: agent, userAgentData: brands ? {brands} : undefined},
      async () => {
        if (fail === "read") throw new Error("engine unreachable");
        if (stored === undefined && storedHints === undefined) return {settings: {}};
        return {settings: {
          crawl_browser_user_agent: {value: stored},
          crawl_browser_client_hints: {value: storedHints},
        }};
      },
      async (path, body) => {
        if (fail === "write") throw new Error("database is locked");
        posted.push({path, body});
      },
      (name, detail) => marks.push({name, detail}),
      () => refusal);
    return {report: () => bare(engineReady), posted, marks};
  };
})();

test("it tells the engine what browser this panel runs in", async () => {
  const panel = panelFor({stored: undefined});

  await panel.report();

  assert.equal(panel.posted.length, 1);
  assert.equal(panel.posted[0].path, "/api/settings");
  assert.deepEqual(panel.posted[0].body, {
    crawl_browser_user_agent: CHROME,
    crawl_browser_client_hints: HINTS_SENT,
  });
});

test("the hints are copied from the browser, never computed", async () => {
  // Chrome's GREASE entry — "Not?A_Brand" and its rotating siblings — exists so
  // that nobody can derive this list, and its version is not the browser's.
  // Building it from a version number would announce a browser that does not
  // exist, which is a sharper tell than the tool name this replaced.
  const panel = panelFor({stored: undefined, brands: [
    {brand: "Chromium", version: "152"},
    {brand: "Weird?Brand", version: "3"},
  ]});

  await panel.report();

  assert.equal(panel.posted[0].body.crawl_browser_client_hints,
    '"Chromium";v="152", "Weird?Brand";v="3"');
});

test("a browser with no userAgentData reports no hints rather than a guess", async () => {
  // Unavailable outside secure contexts and on non-Chromium engines. "" is
  // correct there: the engine then falls back to a value it knows is derived.
  const panel = panelFor({stored: undefined, brands: null});

  await panel.report();

  assert.equal(panel.posted[0].body.crawl_browser_client_hints, "");
  assert.equal(panel.posted[0].body.crawl_browser_user_agent, CHROME);
});

test("it writes nothing when the engine already holds both", async () => {
  // THE WRITE LOCK IS THE POINT. The engine is the single writer and a crawl
  // holds that lock for as long as it runs; a panel that POSTs on every open
  // would queue behind it to say nothing new.
  const panel = panelFor({stored: CHROME, storedHints: HINTS_SENT});

  await panel.report();

  assert.deepEqual(panel.posted, [],
    "the panel wrote an agent the engine already had, taking the write lock "
    + "to change nothing");
});

test("it reports again once Chrome has updated itself", async () => {
  // The other half of the test above: a guard that only ever refuses to write
  // would pass it and make the feature useless.
  const panel = panelFor({stored: CHROME.replace("141", "140"),
                          storedHints: HINTS_SENT});

  await panel.report();

  assert.equal(panel.posted.length, 1);
  assert.equal(panel.posted[0].body.crawl_browser_user_agent, CHROME);
});

test("stale hints alone are enough to report again", async () => {
  // BOTH, or neither. The hints describe the agent; leaving one behind is how
  // the engine ends up building headers for a browser it is not using.
  const panel = panelFor({stored: CHROME, storedHints: '"Chromium";v="140"'});

  await panel.report();

  assert.equal(panel.posted.length, 1,
    "the agent matched so nothing was sent, and the engine kept hints that "
    + "announce a different Chrome than the agent does");
  assert.equal(panel.posted[0].body.crawl_browser_client_hints, HINTS_SENT);
});

test("an engine too old for the key is asked first, not after a 400", async () => {
  // §1.6: an engine that does not know a setting answers 400 "unknown setting"
  // for the WHOLE request, which reads as a typo and is a version gap.
  const panel = panelFor({refusal: "«crawl_browser_user_agent» needs a newer engine"});

  await panel.report();

  assert.deepEqual(panel.posted, []);
  assert.equal(panel.marks.at(-1).name, "browser-agent-not-reported");
  // The gate's OWN sentence, not a summary of it. `capabilityRefusal` already
  // names both versions and what to do; recording "engine too old" instead
  // would throw that away and leave the owner with a fact he cannot act on.
  assert.match(panel.marks.at(-1).detail.reason, /crawl_browser_user_agent/);
});

test("a failed report is recorded, never swallowed", async () => {
  // It is not fatal — the crawl falls back to a Chrome string that still names
  // no tool — which is exactly why it would otherwise be invisible.
  const panel = panelFor({stored: undefined, fail: "write"});

  await panel.report();

  const last = panel.marks.at(-1);
  assert.equal(last.name, "browser-agent-not-reported");
  assert.match(last.detail.reason, /database is locked/);
});

test("a failed read is recorded too", async () => {
  const panel = panelFor({fail: "read"});

  await panel.report();

  assert.equal(panel.marks.at(-1).name, "browser-agent-not-reported");
  assert.match(panel.marks.at(-1).detail.reason, /engine unreachable/);
});

test("a browser that reports no agent is not reported as an empty one", async () => {
  // An EMPTY agent is not anonymity; it is a rarer signature than a name, and
  // `resolve_user_agent` would have had to defend against it.
  const panel = panelFor({agent: ""});

  await panel.report();

  assert.deepEqual(panel.posted, []);
});

test("it asks the version question only once the engine has answered", async () => {
  // THE RACE THIS CLOSES. `capabilityRefusal` reads engine state that
  // `render()` settles; idle time is independent of it. Reading it early gets
  // "cannot be checked", which refuses for a reason that is not true and leaves
  // the agent unreported on an engine that supports the key perfectly well.
  const order = [];
  let releaseEngine;
  const engineReady = new Promise((resolve) => { releaseEngine = resolve; });
  const panel = panelFor({stored: undefined, engineReady});

  const running = panel.report().then(() => order.push("reported"));
  await Promise.resolve();
  assert.deepEqual(panel.posted, [],
    "the agent was reported before the engine had answered, so the version "
    + "gate read a version nobody knew yet");

  order.push("engine answered");
  releaseEngine();
  await running;

  assert.deepEqual(order, ["engine answered", "reported"]);
  assert.equal(panel.posted.length, 1);
});

test("an engine that never answers is recorded, not awaited for ever", async () => {
  const panel = panelFor({
    engineReady: Promise.reject(new Error("engine did not start"))});

  await panel.report();

  assert.deepEqual(panel.posted, []);
  assert.equal(panel.marks.at(-1).name, "browser-agent-not-reported");
  assert.match(panel.marks.at(-1).detail.reason, /engine did not start/);
});

test("it is wired into startup, not left for the settings screen", async () => {
  // loadCrawlSettings only runs when that section is OPEN, so hanging the
  // report off it would mean an owner who never opens Settings crawls with the
  // fallback for ever.
  const idle = SOURCE.match(
    /function scheduleNonCriticalStartup\([\s\S]*?\n\}/m);
  assert.ok(idle, "scheduleNonCriticalStartup moved");
  assert.match(idle[0], /reportBrowserUserAgent\(enginePromise\)/,
    "the agent is no longer reported during startup with the engine's answer "
    + "to wait on — so it is either never sent, or sent before the version "
    + "gate can read a version");
  // THE CALL, pinned by its semicolon. Written without it this matched the
  // function's own DECLARATION — which carries the same two parameter names —
  // so removing the argument at the call site changed nothing here and the
  // guard reported green on the race it exists to catch.
  assert.match(SOURCE, /scheduleNonCriticalStartup\(backendPromise, enginePromise\);/,
    "init no longer hands the engine promise to the idle phase, so the wait "
    + "above resolves to undefined and the race is back");
});

test("no field writes the reported key", async () => {
  // It is REPORTED, not asked. A control for it would be a second way to set
  // one thing, and `crawl_user_agent` is already the owner's say.
  const markup = readFileSync(join(HERE, "..", "app.html"), "utf8");

  assert.ok(!markup.includes("crawl_browser_user_agent"),
    "the panel grew a field for the agent it reports about itself");
  assert.ok(markup.includes("crawl_user_agent"),
    "the owner's own agent field is gone, so he cannot override the report");
});

test("the placeholder no longer promises an honest agent", async () => {
  // It read "leave empty for the built-in honest agent" — a sentence that was
  // true of a string naming this tool and false of the one that replaced it.
  const markup = readFileSync(join(HERE, "..", "app.html"), "utf8");

  assert.ok(!markup.includes("built-in honest agent"),
    "the placeholder still describes the agent that was removed");
});
