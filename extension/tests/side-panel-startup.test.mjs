// The owner opened the Side Panel, saw nothing for fifteen seconds, and only
// got content by clicking the WEB PAGE OUTSIDE the panel. Every test in this
// file is written so that it still fails when that click never happens —
// simulating it is what let the defect through in the first place.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));
const extensionDir = join(here, "..");
const read = (name) => readFileSync(join(extensionDir, name), "utf8");
const require = createRequire(import.meta.url);

const DOCUMENT_KEY = "scrapexStartupTraceDocument";
const HOST_KEY = "scrapexStartupTraceHost";

function loadTraceFactory() {
  delete require.cache[require.resolve("../startup-trace.js")];
  return require("../startup-trace.js");
}

/** A chrome.storage.session that records every write, in order. */
function sessionStorage() {
  const writes = [];
  const area = {
    async set(value) {
      writes.push(structuredClone(value));
    },
  };
  return {writes, area};
}

/**
 * The service-worker environment, recording the ORDER of every Chrome API call
 * so "open() is first" is a fact rather than a comment.
 */
function workerHarness() {
  const calls = {
    apiOrder: [],
    actionListeners: [],
    installedListeners: [],
    openedListeners: [],
    configuration: [],
    open: [],
    tabs: [],
  };
  const {writes, area} = sessionStorage();
  calls.storage = writes;

  const chrome = {
    action: {
      onClicked: {
        addListener(listener) { calls.actionListeners.push(listener); },
      },
    },
    runtime: {
      lastError: undefined,
      getURL: (path) => `chrome-extension://test/${path}`,
      onInstalled: {
        addListener(listener) { calls.installedListeners.push(listener); },
      },
    },
    sidePanel: {
      async setPanelBehavior(options) {
        calls.apiOrder.push("sidePanel.setPanelBehavior");
        calls.configuration.push(["behavior", structuredClone(options)]);
      },
      async setOptions(options) {
        calls.apiOrder.push("sidePanel.setOptions");
        calls.configuration.push(["options", structuredClone(options)]);
      },
      open(options) {
        calls.apiOrder.push("sidePanel.open");
        calls.open.push(structuredClone(options));
        return Promise.resolve();
      },
      onOpened: {
        addListener(listener) { calls.openedListeners.push(listener); },
      },
    },
    storage: {
      session: {
        async set(value) {
          calls.apiOrder.push("storage.session.set");
          return area.set(value);
        },
      },
    },
    tabs: {
      create(options) {
        calls.apiOrder.push("tabs.create");
        calls.tabs.push(structuredClone(options));
      },
    },
  };
  return {calls, chrome};
}

async function loadBackground(t, chrome) {
  const originalChrome = globalThis.chrome;
  const originalImport = globalThis.importScripts;
  const originalTrace = globalThis.ScrapeXStartupTrace;
  globalThis.chrome = chrome;
  // The worker loads startup-trace.js with importScripts; Node has no such
  // global, so the harness performs the same load.
  globalThis.importScripts = () => {
    globalThis.ScrapeXStartupTrace = loadTraceFactory();
  };
  t.after(() => {
    if (originalChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = originalChrome;
    if (originalImport === undefined) delete globalThis.importScripts;
    else globalThis.importScripts = originalImport;
    if (originalTrace === undefined) delete globalThis.ScrapeXStartupTrace;
    else globalThis.ScrapeXStartupTrace = originalTrace;
  });
  // require(), not import(): Node caches a CommonJS file by path and ignores a
  // cache-busting query, so import() would silently reuse the first load and
  // every later assertion would pass against a worker that never ran.
  delete require.cache[require.resolve("../background.js")];
  require("../background.js");
  await new Promise((resolve) => setTimeout(resolve, 0));
}

// ---------------------------------------------------------------------------
// Opening strategy: registration, and nothing competing with it
// ---------------------------------------------------------------------------

test("the panel path is registered by the manifest, before any click", () => {
  const manifest = JSON.parse(read("manifest.json"));
  assert.equal(manifest.side_panel.default_path, "app.html");
  assert.ok(manifest.permissions.includes("sidePanel"));
});

test("no configuration call competes with the open on the shipping path", async (t) => {
  const {calls, chrome} = workerHarness();
  await loadBackground(t, chrome);

  // setOptions carries the path. Issued at worker start it lands AFTER a cold
  // click's open(), re-pointing a panel that is already showing that document.
  // The manifest already registered the path, so there is nothing to configure.
  assert.deepEqual(calls.configuration, [],
    "the service worker configured the side panel while a click could be opening it");
});

test("exactly one action.onClicked listener exists in the whole extension", async (t) => {
  const {calls, chrome} = workerHarness();
  await loadBackground(t, chrome);
  assert.equal(calls.actionListeners.length, 1);

  // A second opener anywhere else is a second open attempt per click.
  const sources = ["background.js", "app.js", "identity.js", "engine.js",
                   "transport.js", "startup.js", "startup-bootstrap.js"];
  for (const name of sources) {
    assert.equal(read(name).includes("action.onClicked"), name === "background.js",
      `${name} registers a competing action.onClicked listener`);
  }
});

test("one toolbar click produces exactly one open attempt", async (t) => {
  const {calls, chrome} = workerHarness();
  await loadBackground(t, chrome);
  const click = calls.actionListeners[0];

  assert.equal(click({id: 41, windowId: 17}), undefined);
  assert.deepEqual(calls.open, [{windowId: 17}]);

  click({id: 42, windowId: 17});
  assert.equal(calls.open.length, 2, "a second click must open exactly once more");
});

test("sidePanel.open is the first Chrome API call the click handler makes", async (t) => {
  const {calls, chrome} = workerHarness();
  await loadBackground(t, chrome);
  calls.apiOrder.length = 0;

  calls.actionListeners[0]({id: 41, windowId: 17});

  // Anything before it — a storage write, a setOptions, an awaited read — spends
  // the user gesture that sidePanel.open() requires.
  assert.equal(calls.apiOrder[0], "sidePanel.open",
    `a Chrome call preceded open(): ${calls.apiOrder.join(" -> ")}`);

  // The runtime order above cannot see a call that is merely QUEUED before
  // open() — an awaited read, or a promise-returning API whose effect lands
  // later. So the handler's source is checked too: the first `chrome.` it
  // mentions must be the open, and it must not await anything beforehand.
  const source = read("background.js");
  const start = source.indexOf("chrome.action.onClicked.addListener");
  assert.ok(start > -1);
  const handler = source.slice(start, source.indexOf("\n});", start));
  const firstChromeCall = handler.slice(handler.indexOf("(tab) => {"))
    .match(/chrome\.[A-Za-z.]+/);
  assert.equal(firstChromeCall?.[0], "chrome.sidePanel.open",
    `the handler's first Chrome API is ${firstChromeCall?.[0]}, not the open`);
  assert.ok(!/\bawait\b/.test(handler),
    "the click handler awaits before opening, which spends the user gesture");
});

test("a click with no window records the refusal instead of opening", async (t) => {
  const {calls, chrome} = workerHarness();
  await loadBackground(t, chrome);

  calls.actionListeners[0]({id: 41});
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(calls.open, []);
  const trace = calls.storage.at(-1)[HOST_KEY];
  assert.equal(trace.events.at(-1).name, "side-panel-open-failed");
});

// ---------------------------------------------------------------------------
// The trace must survive a startup that never completes
// ---------------------------------------------------------------------------

test("every mark is persisted as it happens, not buffered until startup ends", async () => {
  const factory = loadTraceFactory();
  const {writes, area} = sessionStorage();
  const originalChrome = globalThis.chrome;
  globalThis.chrome = {storage: {session: area}};
  try {
    const trace = factory.createTrace(DOCUMENT_KEY);
    trace.mark("document-first-script", {readyState: "loading"});
    trace.mark("animation-frame-requested", {});
    // Startup stops here. Nothing else will ever run.
    await trace.flushed();

    assert.equal(writes.length, 2, "a mark was buffered instead of written");
    assert.deepEqual(
      writes.at(-1)[DOCUMENT_KEY].events.map((event) => event.name),
      ["document-first-script", "animation-frame-requested"],
    );
  } finally {
    if (originalChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = originalChrome;
  }
});

test("each persisted mark carries both Date.now() and performance.now()", async () => {
  const factory = loadTraceFactory();
  const {writes, area} = sessionStorage();
  const originalChrome = globalThis.chrome;
  globalThis.chrome = {storage: {session: area}};
  try {
    const trace = factory.createTrace(DOCUMENT_KEY);
    trace.mark("document-first-script", {});
    await trace.flushed();
    const event = writes.at(-1)[DOCUMENT_KEY].events[0];
    assert.ok(Number.isFinite(event.dateNow), "no Date.now() timestamp");
    assert.ok(Number.isFinite(event.perfNow), "no performance.now() timestamp");
    assert.ok(Number.isFinite(event.epochMs), "no common-clock timestamp");
  } finally {
    if (originalChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = originalChrome;
  }
});

test("a trace written without any storage present still never throws", () => {
  const factory = loadTraceFactory();
  const originalChrome = globalThis.chrome;
  delete globalThis.chrome;
  try {
    const trace = factory.createTrace(DOCUMENT_KEY);
    assert.doesNotThrow(() => trace.mark("document-first-script", {}));
    assert.equal(trace.events().length, 1);
  } finally {
    if (originalChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = originalChrome;
  }
});

// ---------------------------------------------------------------------------
// The click OUTSIDE the panel: the signal, and its absence
// ---------------------------------------------------------------------------

test("the first lifecycle event after start is recorded once, and named", async () => {
  const factory = loadTraceFactory();
  const {writes, area} = sessionStorage();
  const originalChrome = globalThis.chrome;
  globalThis.chrome = {storage: {session: area}};
  try {
    const trace = factory.createTrace(DOCUMENT_KEY);
    trace.mark("document-first-script", {});
    // The owner clicks the web page outside the panel. Whatever the browser
    // delivers first is the answer this investigation needed.
    trace.mark("focus", {});
    trace.mark("visibilitychange", {});
    await trace.flushed();

    const names = writes.at(-1)[DOCUMENT_KEY].events.map((event) => event.name);
    const marks = names.filter((name) => name === "first-lifecycle-event-after-start");
    assert.equal(marks.length, 1, "the key signal was recorded more than once");

    const recorded = writes.at(-1)[DOCUMENT_KEY].events
      .find((event) => event.name === "first-lifecycle-event-after-start");
    assert.deepEqual(recorded.detail, {event: "focus"});
  } finally {
    if (originalChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = originalChrome;
  }
});

test("with no focus, blur, visibilitychange or click at all, the trace is still complete",
  async () => {
    const factory = loadTraceFactory();
    const {writes, area} = sessionStorage();
    const originalChrome = globalThis.chrome;
    globalThis.chrome = {storage: {session: area}};
    try {
      const trace = factory.createTrace(DOCUMENT_KEY);
      // Exactly the owner's fifteen untouched seconds.
      trace.mark("document-first-script", {readyState: "loading", hasFocus: false});
      trace.mark("dom-content-loaded", {readyState: "interactive"});
      trace.mark("animation-frame-requested", {});
      trace.mark("fallback-timer-fired", {actualDelayMs: 251});
      await trace.flushed();

      const names = writes.at(-1)[DOCUMENT_KEY].events.map((event) => event.name);
      assert.ok(names.includes("document-first-script"));
      assert.ok(names.includes("fallback-timer-fired"));
      assert.ok(!names.includes("first-lifecycle-event-after-start"),
        "a lifecycle event was recorded although nothing was ever clicked");
      // The absence of a frame and of a paint, both retrievable, IS the finding.
      assert.ok(!names.includes("animation-frame-fired"));
      assert.ok(!names.includes("first-contentful-paint"));
    } finally {
      if (originalChrome === undefined) delete globalThis.chrome;
      else globalThis.chrome = originalChrome;
    }
  });

// ---------------------------------------------------------------------------
// The static shell: visible without JavaScript, network, focus or a frame
// ---------------------------------------------------------------------------

test("the initial HTML carries a visible shell that no script has to reveal", () => {
  const html = read("app.html");
  const profile = html.match(/<section id="view-profile"[^>]*>/);
  assert.ok(profile, "the Profile view is gone from the initial HTML");
  assert.ok(!/\bclass="[^"]*\bhidden\b/.test(profile[0]),
    "the only initially visible view starts hidden");

  // Real words, in the file, before any script runs.
  assert.ok(html.includes("Welcome to ScrapeX"));
  assert.ok(html.includes("Checking your account"));

  // The shell must not be created by JavaScript.
  assert.ok(/<div class="profile-stage"/.test(html));
  assert.ok(!/<body[^>]*\b(hidden|style="[^"]*display:\s*none)/.test(html),
    "the document body starts hidden");
  assert.ok(!/<main[^>]*\bclass="[^"]*\bhidden\b/.test(html),
    "the main element starts hidden");
});

test("no stylesheet hides the document until a script marks it ready", () => {
  for (const name of ["tokens.css", "components.css", "app.css"]) {
    const css = read(name);
    // A shell revealed by a class or attribute that only JS can set is a shell
    // that stays invisible when JS never gets a frame.
    assert.ok(!/\b(html|body)\s*(?::not\([^)]*\))?\s*\{[^}]*\b(visibility\s*:\s*hidden|display\s*:\s*none|opacity\s*:\s*0)/.test(css),
      `${name} hides the document before scripts run`);
    assert.ok(!/\[data-shell-interactive[^\]]*\]|\.js-ready|\.not-ready/.test(css),
      `${name} gates painting on a JavaScript-set readiness hook`);
  }
});

test("the trace scripts load first, and app.js is not in the markup at all", () => {
  const html = read("app.html");
  const trace = html.indexOf("startup-trace.js");
  const bootstrap = html.indexOf("startup-bootstrap.js");
  const firstStylesheet = html.indexOf("<link rel=\"stylesheet\"");

  assert.ok(trace > -1 && bootstrap > trace,
    "the trace must be loaded before the bootstrap that uses it");
  assert.ok(bootstrap < firstStylesheet,
    "a stylesheet is fetched before the document records that it started");

  // THE ORDERING THAT REPLACED "bootstrap BEFORE app.js". app.js is no longer
  // in the markup: Chrome reveals the Side Panel only after `load`, and a
  // hidden document's resource loading is deprioritised, so a module graph in
  // front of `load` keeps the panel hidden which keeps the graph slow. Measured
  // on the owner's Chrome: every piece of our own work finished at 825ms and
  // `load` still did not fire until 2024ms; the same page in a visible tab goes
  // from DOMContentLoaded to load in 17ms.
  //
  // Putting the module tag back would restore the blank panel, so this asserts
  // its ABSENCE rather than its position.
  assert.ok(!/<script[^>]*src="app\.js"/.test(html),
    "app.js is loaded from the markup again, which puts the whole module graph "
    + "in front of `load` and leaves the Side Panel blank until the user clicks "
    + "somewhere outside it");
  assert.ok(html.includes("boot-app.js"),
    "nothing appends app.js after `load`, so the panel would paint and then "
    + "never become interactive");
});

// ---------------------------------------------------------------------------
// Stalled Account and Engine work must never hold the shell
// ---------------------------------------------------------------------------

test("an Account request that never answers ends at its own deadline", async () => {
  const {fetchWithDeadline, STARTUP_DEADLINES, isTimeoutError} =
    await import("../startup.js");
  const never = (_input, {signal}) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), {once: true});
  });
  assert.ok(Number.isFinite(STARTUP_DEADLINES.accountDetails));
  await assert.rejects(
    fetchWithDeadline(never, "/oauth2/v3/userinfo", {}, 25),
    (error) => isTimeoutError(error),
  );
});

test("an Engine request that never answers ends at its own deadline", async () => {
  const {fetchWithDeadline, deadlineForLocalRequest, isTimeoutError} =
    await import("../startup.js");
  const never = (_input, {signal}) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), {once: true});
  });
  assert.ok(deadlineForLocalRequest("/api/health") > 0);
  await assert.rejects(
    fetchWithDeadline(never, "/api/health", {}, 25),
    (error) => isTimeoutError(error),
  );
});

test("a hidden document does not wait for a frame, or for a timer either", async () => {
  const {afterNextPaint} = await import("../startup.js");
  const originalDocument = globalThis.document;
  globalThis.document = {visibilityState: "hidden"};
  let frameRequested = false;
  try {
    // MEASURED, TWICE, ON THE OWNER'S MACHINE. The side panel document is
    // created with visibilityState "hidden": rAF was requested at 28ms and did
    // not fire until 2372ms, the moment Chrome finally marked the document
    // visible. The timer fallback does not rescue it, because timers are
    // throttled in a hidden document too — a 250ms fallback fired at 767ms in
    // one run and 1131ms in another.
    //
    // This asserted `source === "timer"`, which meant startup still paid that
    // throttled wait: the shell was ready at 168ms and sat behind ~785ms of it.
    // Nothing here can make Chrome paint sooner. What it can do is not be the
    // reason the panel is still empty once Chrome does show it.
    const result = await afterNextPaint({
      timeoutMs: 20_000,               // deliberately huge: if it is consulted
      requestFrame: () => {             // at all, this test hangs rather than
        frameRequested = true;          // passing by accident
        return 5;
      },
      cancelFrame: () => {},
    });
    assert.equal(result.source, "hidden");
    assert.equal(frameRequested, false,
      "a frame was requested for a hidden document, which cannot service one");
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
});

// ---------------------------------------------------------------------------
// No second round of requests when the panel is finally touched
// ---------------------------------------------------------------------------

test("no lifecycle listener re-runs the Account or Engine startup work", () => {
  const source = read("app.js");
  // handlePanelVisibility owns the job poll and nothing else. A listener that
  // calls loadAccount() or render() turns the owner's outside click into a
  // second startup, which is how a masked defect looks fixed.
  const handler = source.slice(source.indexOf("function handlePanelVisibility"));
  const body = handler.slice(0, handler.indexOf("\n}\n") + 3);
  assert.ok(!/\bloadAccount\s*\(/.test(body),
    "a visibility change restarts the Account check");
  assert.ok(!/\brender\s*\(\s*\)/.test(body),
    "a visibility change restarts the Engine check");

  for (const event of ["pageshow", "focus"]) {
    const pattern = new RegExp(`addEventListener\\(\\s*"${event}"[^)]*loadAccount`, "s");
    assert.ok(!pattern.test(source), `a ${event} listener restarts the Account check`);
  }
});

// ---------------------------------------------------------------------------
// The diagnostic page is a diagnostic, and cannot become a product surface
// ---------------------------------------------------------------------------

test("the minimal diagnostic page stays minimal", () => {
  const html = read("tests/diagnostic-panel.html");
  assert.ok(html.includes("SIDE PANEL DOCUMENT STARTED"));
  assert.ok(!/<link\b/.test(html), "the diagnostic page pulled in a stylesheet");
  assert.ok(!/type="module"/.test(html), "the diagnostic page pulled in a module");
  // Comments come out first, so a commented-out example cannot be misread as the
  // page hiding something.
  //
  // TO A FIXPOINT, not once, because removing a comment can CREATE one that the
  // single pass has already read past. Measured, not reasoned about:
  //
  //     "<!<!-- -->-- hidden -->"   one pass -> "<!-- hidden -->"
  //                                 fixpoint -> ""
  //
  // The pass removes the inner `<!-- -->`, and the two halves left either side
  // of it close up into a comment nothing will look at again. Here that leaks
  // the word `hidden` into the text scanned below, so a commented-out example
  // would be reported as the page hiding something — this test failing for a
  // reason that is not true, which is the failure mode it exists to prevent in
  // the page.
  //
  // CodeQL flags it as js/incomplete-multi-character-sanitization. It is right
  // to, even though this input is a file in this repository and nothing is ever
  // rendered from it: what makes one pass safe here is where the input comes
  // from, and that stops being true the day someone points this at something
  // else.
  let markup = html;
  let previous;
  do {
    previous = markup;
    markup = markup.replace(/<!--[\s\S]*?-->/g, "");
  } while (markup !== previous);
  assert.ok(!/\bhidden\b|display:\s*none|visibility:\s*hidden|opacity:\s*0/.test(markup),
    "the diagnostic page hides something");

  // The same idea for the script, but a `//` strip has to fail in the opposite
  // direction to the one above. `//` is not only a comment marker, it is also
  // the middle of every URL, and deleting to end of line deletes real code:
  //
  //     open("http://x"); fetch("/y");   ->   open("http:
  //
  // `fetch(` is now absent from the text scanned below and the assertion passes
  // for a page that plainly does fetch. That is the guard quietly ceasing to
  // guard, which is worse than the guard being wrong out loud — and a URL is
  // exactly what the person who adds the first request to this page will type.
  //
  // So: drop a whole-line comment always, and drop a trailing one only on a
  // line carrying no quote at all. A comment that merely mentions `fetch(`
  // beside a string now fails this test loudly and someone moves the comment;
  // a real `fetch(` can no longer be swallowed by the thing meant to find it.
  //
  // Deliberately NOT to a fixpoint, unlike the markup above. That loop is there
  // because removing `<!-- -->` can join its two sides into a new comment; this
  // regex runs to end of line, so the character after every removal is `\n` and
  // two `/` can never be brought together. Measured over 20k random strings of
  // `/`, `"`, `*`, `(`, newline and `fetch`: a second pass changed 0 of them.
  // A loop here would be copied ritual, not a fix, and CodeQL does not ask for
  // one — js/incomplete-multi-character-sanitization cannot fire on this shape.
  //
  // There is deliberately no `/* */` strip. That page uses `//` only — measured,
  // `grep -c '/\*'` over it is 0 — so such a strip has nothing to remove and one
  // way to be wrong: a `/*` inside a string literal deletes forward to the next
  // `*/`, which is the same silent hiding of real code as above, arriving by a
  // second door. If a block comment is ever added there and this test fails on a
  // word inside it, write it as `//` lines; do not bring the strip back.
  const script = read("tests/diagnostic-panel.js")
    .split("\n")
    .map((line) => {
      if (/^\s*\/\//.test(line)) return "";
      if (/["'`]/.test(line)) return line;
      return line.replace(/\/\/.*$/, "");
    })
    .join("\n");
  assert.ok(!/\bfetch\s*\(/.test(script), "the diagnostic page makes a request");
  assert.ok(!/loadAccount|engine|appearance/i.test(script),
    "the diagnostic page runs product startup work");
  assert.ok(!/chrome\.runtime\.sendMessage/.test(script),
    "the diagnostic page depends on a service worker being awake");
});

test("the diagnostic page cannot reach a package", () => {
  // extension/tests/ is deleted by the release workflow, which then fails the
  // build if the directory survived. Living there is the enforcement.
  const workflow = readFileSync(
    join(extensionDir, "..", ".github", "workflows", "release-extension.yml"), "utf8");
  assert.ok(workflow.includes("rm -rf build/scrapex/tests"));
  assert.ok(workflow.includes("tests are in the package"));
  assert.ok(read("background.js").includes("tests/diagnostic-panel.html"),
    "the diagnostic path moved out of the directory that is stripped");
});

test("the shipping build uses the explicit opening strategy", () => {
  const source = read("background.js");
  assert.ok(/const OPENING_STRATEGY = "explicit";/.test(source),
    "a diagnostic or experimental opening strategy is about to ship");
});

test("app.js starts even though DOMContentLoaded is long past when it arrives", () => {
  // THE DEFECT THIS EXISTS FOR, found by the owner within a minute of the fix
  // above. boot-app.js appends app.js when `load` fires, so DOMContentLoaded has
  // already been and gone. app.js waited on that event unconditionally, its
  // listener was never called, and the panel painted instantly and then did
  // NOTHING -- every control dead, no engine check, no account.
  //
  // Half a fix that turns a blank panel into a dead one is not an improvement,
  // and the ordering test above cannot see it: the markup is correct in both
  // cases. This reads the entry point instead.
  const source = read("app.js");

  assert.ok(/document\.readyState/.test(source),
    "app.js does not check readyState, so it cannot tell whether "
    + "DOMContentLoaded is still coming or already gone");
  assert.ok(!/^document\.addEventListener\("DOMContentLoaded"/m.test(source),
    "app.js waits on DOMContentLoaded unconditionally at the top level. "
    + "boot-app.js appends it after `load`, so that event never fires again "
    + "and nothing in the panel ever starts");
});
