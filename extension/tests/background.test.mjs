import { test } from "node:test";
import assert from "node:assert/strict";

const TRACE_KEY = "scrapexSidePanelStartupTrace";

function chromeHarness() {
  const calls = {
    actionListeners: [],
    configuration: [],
    messageListeners: [],
    openedListeners: [],
    open: [],
    storage: [],
    timeline: [],
  };

  const chrome = {
    action: {
      onClicked: {
        addListener(listener) { calls.actionListeners.push(listener); },
      },
    },
    runtime: {
      getURL(path) { return `chrome-extension://test/${path}`; },
      onInstalled: {addListener() {}},
      onMessage: {
        addListener(listener) { calls.messageListeners.push(listener); },
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
      onOpened: {
        addListener(listener) { calls.openedListeners.push(listener); },
      },
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

function nextTurn() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

test("the toolbar explicitly opens one preconfigured global panel", async (t) => {
  const originalChrome = globalThis.chrome;
  const {calls, chrome} = chromeHarness();
  globalThis.chrome = chrome;
  t.after(() => {
    if (originalChrome === undefined) delete globalThis.chrome;
    else globalThis.chrome = originalChrome;
  });

  await import(`../background.js?host-opening=${Date.now()}`);
  await nextTurn();

  assert.deepEqual(calls.configuration, [
    ["behavior", {openPanelOnActionClick: false}],
    ["options", {enabled: true, path: "app.html"}],
  ]);
  assert.equal(calls.actionListeners.length, 1);
  assert.equal(calls.messageListeners.length, 1);
  assert.equal(calls.openedListeners.length, 1);

  const actionClick = calls.actionListeners[0];
  const returned = actionClick({id: 41, windowId: 17});

  // open() is called before the click callback returns. No awaited setup can
  // consume Chrome's user gesture, and one click produces exactly one request.
  assert.equal(returned, undefined);
  assert.deepEqual(calls.open, [{windowId: 17}]);
  assert.equal(calls.timeline[0], "open");
  await nextTurn();

  let trace = calls.storage.at(-1)[TRACE_KEY];
  assert.deepEqual(
    trace.events.slice(-3).map((event) => event.name),
    ["action-click", "side-panel-open-request", "side-panel-open-resolved"],
  );

  calls.messageListeners[0]({
    type: "scrapex-side-panel-startup-event",
    event: {
      name: "document-start",
      at: 1234,
      detail: {visibilityState: "hidden", hasFocus: false},
    },
  }, {url: "chrome-extension://test/app.html"});
  await nextTurn();

  trace = calls.storage.at(-1)[TRACE_KEY];
  assert.equal(trace.events.at(-1).name, "document-start");
  assert.equal(trace.events.at(-1).at, 1234);
  assert.deepEqual(trace.events.at(-1).detail, {
    visibilityState: "hidden",
    hasFocus: false,
    documentUrl: "chrome-extension://test/app.html",
  });
  assert.equal(calls.open.length, 1);
});
