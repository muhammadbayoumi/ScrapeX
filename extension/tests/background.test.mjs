// The service worker's half of the startup trace: what the HOST did, written
// where it survives a panel that never paints.

import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const HOST_KEY = "scrapexStartupTraceHost";
const require = createRequire(import.meta.url);

function chromeHarness() {
  const calls = {
    actionListeners: [],
    configuration: [],
    openedListeners: [],
    installedListeners: [],
    externalListeners: [],
    open: [],
    storage: [],
    timeline: [],
  };

  const chrome = {
    action: {
      onClicked: {addListener(listener) { calls.actionListeners.push(listener); }},
    },
    runtime: {
      lastError: undefined,
      getURL(path) { return `chrome-extension://test/${path}`; },
      onInstalled: {
        addListener(listener) { calls.installedListeners.push(listener); },
      },
      // The chooser page's way back in. Absent from the harness, background.js
      // throws while loading and every test here fails describing `addListener`
      // rather than the worker.
      onMessageExternal: {
        addListener(listener) { calls.externalListeners.push(listener); },
      },
    },
    sidePanel: {
      async setPanelBehavior(options) {
        calls.configuration.push(["behavior", structuredClone(options)]);
      },
      async setOptions(options) {
        calls.configuration.push(["options", structuredClone(options)]);
      },
      open(options) {
        calls.timeline.push("open");
        calls.open.push(structuredClone(options));
        return Promise.resolve();
      },
      onOpened: {addListener(listener) { calls.openedListeners.push(listener); }},
    },
    storage: {
      session: {
        async set(value) {
          calls.timeline.push("storage");
          calls.storage.push(structuredClone(value));
        },
      },
    },
    tabs: {create() {}},
  };
  return {calls, chrome};
}

const nextTurn = () => new Promise((resolve) => setTimeout(resolve, 0));

async function loadBackground(t, chrome) {
  const originals = {
    chrome: globalThis.chrome,
    importScripts: globalThis.importScripts,
    trace: globalThis.ScrapeXStartupTrace,
  };
  globalThis.chrome = chrome;
  globalThis.importScripts = () => {
    delete require.cache[require.resolve("../startup-trace.js")];
    globalThis.ScrapeXStartupTrace = require("../startup-trace.js");
  };
  t.after(() => {
    for (const [key, value] of Object.entries(originals)) {
      const name = key === "trace" ? "ScrapeXStartupTrace" : key;
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  });
  // require(), not import(): Node caches a CommonJS file by path and ignores a
  // cache-busting query, so import() would reuse the first load and every later
  // test would assert against a worker that never ran again.
  delete require.cache[require.resolve("../background.js")];
  require("../background.js");
  await nextTurn();
}

test("the worker records that it started, and with which strategy", async (t) => {
  const {calls, chrome} = chromeHarness();
  await loadBackground(t, chrome);

  const trace = calls.storage.at(-1)[HOST_KEY];
  assert.equal(trace.events[0].name, "service-worker-start");
  assert.equal(trace.events[0].detail.strategy, "explicit");
  assert.equal(trace.events[0].detail.path, "app.html");
  assert.equal(calls.actionListeners.length, 1);
  assert.equal(calls.openedListeners.length, 1);
  assert.equal(calls.installedListeners.length, 1);
});

test("a toolbar click writes the whole opening interval to session storage",
  async (t) => {
    const {calls, chrome} = chromeHarness();
    await loadBackground(t, chrome);

    calls.timeline.length = 0;
    calls.actionListeners[0]({id: 41, windowId: 17});

    // open() runs before any storage write: the trace must never be the thing
    // that spends the user gesture.
    assert.equal(calls.timeline[0], "open");
    assert.deepEqual(calls.open, [{windowId: 17}]);
    await nextTurn();

    const trace = calls.storage.at(-1)[HOST_KEY];
    const names = trace.events.map((event) => event.name);
    assert.deepEqual(names.slice(-3), [
      "action-click", "side-panel-open-request", "side-panel-open-resolved",
    ]);
    for (const event of trace.events) {
      assert.ok(Number.isFinite(event.dateNow), `${event.name} has no Date.now()`);
      assert.ok(Number.isFinite(event.epochMs), `${event.name} has no epoch clock`);
    }
  });

test("a rejected open is recorded rather than swallowed", async (t) => {
  const {calls, chrome} = chromeHarness();
  chrome.sidePanel.open = () => {
    calls.timeline.push("open");
    return Promise.reject(new Error("Side panel is not available"));
  };
  await loadBackground(t, chrome);

  calls.actionListeners[0]({id: 41, windowId: 17});
  await nextTurn();

  const trace = calls.storage.at(-1)[HOST_KEY];
  const failure = trace.events.at(-1);
  assert.equal(failure.name, "side-panel-open-failed");
  assert.equal(failure.detail.message, "Side panel is not available");
});

test("the host trace and the document trace never share one storage key", () => {
  const factory = (() => {
    delete require.cache[require.resolve("../startup-trace.js")];
    return require("../startup-trace.js");
  })();
  // Two contexts read-modify-writing one key lose events exactly when both are
  // busy, which is startup. Retrieval merges them on the clock instead.
  assert.notEqual(factory.HOST_KEY, factory.DOCUMENT_KEY);
});
