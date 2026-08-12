importScripts("startup-trace.js");

// OPENING THE SIDE PANEL, AND THE COMPETING WRITE THAT WAS REMOVED.
//
// The rejected build called, at service-worker startup and without awaiting it:
//
//     await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: false});
//     await chrome.sidePanel.setOptions({enabled: true, path: "app.html"});
//
// On a COLD click there is no service worker yet, so Chrome starts one to
// deliver action.onClicked. Top-level code runs first, the two configuration
// calls go out, and the click handler's sidePanel.open() runs while the second
// one is still in flight — because setOptions sits behind an await. setOptions
// carries a `path`, and setting a path is what tells Chrome which document the
// panel shows. It therefore lands AFTER the panel has already been opened, on a
// panel that is already showing that same document.
//
// Neither call was needed. `side_panel.default_path` in the manifest already
// registers the global path, before any click, for every window. So the two
// calls added nothing and raced the one call that mattered.
//
// What is left is the rule: the manifest registers, the click opens, and
// sidePanel.open() is the FIRST and ONLY Chrome API call in the handler so no
// awaited work can spend the user gesture it requires.

const SIDE_PANEL_PATH = "app.html";

// WHICH OPENING STRATEGY THIS BUILD USES. Tested one at a time, never combined:
// combining them is what produced a build where nobody could say which
// mechanism actually opened the panel.
//
//   "explicit"  - Strategy B. No setPanelBehavior, no setOptions. Exactly one
//                 action.onClicked listener whose first Chrome call is
//                 sidePanel.open({windowId}). This is the shipping default.
//   "behavior"  - Strategy A. Chrome opens the panel itself from the action
//                 click via setPanelBehavior({openPanelOnActionClick: true}).
//                 The click listener then opens nothing at all.
//   "diagnostic"- Strategy B, but pointed at tests/diagnostic-panel.html: a
//                 static page with no CSS, no modules and no requests. Never
//                 reaches a package; see the note on DIAGNOSTIC_PANEL_PATH.
//
// Changed here, in source, rather than read from storage: MV3 requires event
// listeners to be registered synchronously at the top level, and a strategy
// that depends on an awaited storage read cannot honour that.
const OPENING_STRATEGY = "explicit";

// The diagnostic page lives under extension/tests/ because the release workflow
// deletes that directory from the package and then FAILS the build if it is
// still present. The page therefore cannot ship, and that is enforced by the
// existing gate rather than by remembering to remove it.
// THE BISECT. The minimal page paints immediately and app.html does not, so
// the cause is one of the six things app.html has and it does not: three
// render-blocking stylesheets and three synchronous head scripts. Each of these
// pages carries exactly one of those halves, so two runs say which half is
// guilty before anything is changed in production code.
const DIAGNOSTIC_PAGES = {
  diagnostic: "tests/diagnostic-panel.html",   // neither half — the control
  "diagnostic-styles": "tests/diagnostic-styles.html",   // stylesheets only
  "diagnostic-scripts": "tests/diagnostic-scripts.html", // head scripts only
  "diagnostic-both": "tests/diagnostic-both.html",       // both halves
  "diagnostic-nomodule": "tests/diagnostic-app-nomodule.html", // app.html - app.js
};
const DIAGNOSTIC_PANEL_PATH = DIAGNOSTIC_PAGES[OPENING_STRATEGY]
  || DIAGNOSTIC_PAGES.diagnostic;
const IS_DIAGNOSTIC = OPENING_STRATEGY in DIAGNOSTIC_PAGES;

const trace = globalThis.ScrapeXStartupTrace.createTrace(
  globalThis.ScrapeXStartupTrace.HOST_KEY,
);

function lastError() {
  try { return chrome.runtime.lastError?.message || null; } catch (_) { return null; }
}

trace.mark("service-worker-start", {
  strategy: OPENING_STRATEGY,
  path: IS_DIAGNOSTIC ? DIAGNOSTIC_PANEL_PATH : SIDE_PANEL_PATH,
});

// STRATEGY A ONLY. Chrome performs the opening itself, so there is nothing for
// the click handler to do and no gesture to preserve. This is the one strategy
// where a configuration call is legitimate, because it must be in place BEFORE
// the click rather than racing it.
if (OPENING_STRATEGY === "behavior") {
  chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).then(
    () => trace.mark("set-panel-behavior-resolved", {openPanelOnActionClick: true}),
    (error) => trace.mark("set-panel-behavior-failed", {
      message: error?.message || String(error),
    }),
  );
}

// STRATEGY "diagnostic" ONLY. Registered once, at worker start, long before any
// click — the ordering the production path deliberately no longer needs.
//
// RELOAD THE EXTENSION BEFORE THE FIRST DIAGNOSTIC CLICK. Pressing reload on
// chrome://extensions starts the worker immediately, so this setOptions has
// resolved long before any toolbar click. Clicking the icon on a cold worker
// instead would recreate the very race this branch removed from production, and
// the diagnostic would be measuring that race rather than the panel.
if (IS_DIAGNOSTIC) {
  chrome.sidePanel.setOptions({enabled: true, path: DIAGNOSTIC_PANEL_PATH}).then(
    () => trace.mark("set-panel-options-resolved", {path: DIAGNOSTIC_PANEL_PATH}),
    (error) => trace.mark("set-panel-options-failed", {
      message: error?.message || String(error),
    }),
  );
}

// EXACTLY ONE action.onClicked listener in the whole extension.
chrome.action.onClicked.addListener((tab) => {
  const windowId = tab?.windowId;
  trace.mark("action-click", {
    tabId: tab?.id ?? null,
    windowId: windowId ?? null,
    strategy: OPENING_STRATEGY,
  });

  // Strategy A: Chrome already opened the panel. Opening it again here would be
  // the second open attempt this investigation exists to rule out.
  if (OPENING_STRATEGY === "behavior") {
    trace.mark("side-panel-open-skipped", {reason: "chrome-opens-on-action-click"});
    return;
  }

  if (!Number.isInteger(windowId)) {
    trace.mark("side-panel-open-failed", {message: "The action has no window."});
    return;
  }

  const options = {windowId};
  try {
    // FIRST Chrome API call in this handler, synchronously, on every path. The
    // mark above touched only startup-trace's in-memory array; its storage
    // write is asynchronous and cannot land before this line.
    const opening = chrome.sidePanel.open(options);
    trace.mark("side-panel-open-request", {...options, lastError: lastError()});
    opening.then(
      () => trace.mark("side-panel-open-resolved", options),
      (error) => trace.mark("side-panel-open-failed", {
        ...options,
        message: error?.message || String(error),
        lastError: lastError(),
      }),
    );
  } catch (error) {
    trace.mark("side-panel-open-failed", {
      ...options,
      message: error?.message || String(error),
      lastError: lastError(),
    });
  }
});

// Chrome 141+ exposes the host's own opening event. It is evidence, never a
// startup dependency, so older supported Chrome versions simply omit this mark.
chrome.sidePanel.onOpened?.addListener((info) => {
  trace.mark("side-panel-on-opened", info);
});

// ---- the spreadsheet the owner chose, arriving from a web page --------------
//
// Google Picker cannot run in this panel: it loads apis.google.com/js/api.js,
// and MV3 forbids an extension executing code fetched from a server. So the
// chooser lives on an ordinary web origin (docs/picker/scrapex-picker.html,
// served from the owner's site) and hands back an id here.
//
// EVERYTHING FROM OUTSIDE IS UNTRUSTED, and `externally_connectable` narrows
// WHO may speak, never WHAT they may say. The origin is checked again below
// even though the manifest already restricts it — a match pattern is one
// character from being widened, and this listener is the last thing standing
// between a web page and the panel.
//
// It carries no token in either direction. The page was handed one to draw the
// Picker with; what returns is a file id and a name, and the panel opens that
// file with its own token exactly as it opens one it created.
const PICKER_ORIGIN = "https://muhammadbayoumi.github.io";

/**
 * Hand the page the access token it needs, once, in exchange for the nonce the
 * panel put in its URL.
 *
 * WHY THE TOKEN IS NOT SIMPLY IN THE URL. It was, and that was wrong. A
 * fragment is not sent to a server — which is true, and defends against the
 * wrong adversary. Locally a tab's URL is public: chrome.tabs.onCreated and
 * onUpdated hand it, fragment and all, to EVERY installed extension holding the
 * `tabs` permission. A live OAuth bearer token sitting there is readable by any
 * of them and usable from any machine for the rest of its hour.
 *
 * So the URL carries a nonce and nothing else. What a watching extension can
 * copy is a number that:
 *
 *   - is spent by the first caller and refused for ever after,
 *   - expires on its own within the chooser's own two-minute window,
 *   - is worthless without ALSO being able to send from the picker's origin,
 *     which needs a content script on that site — a far higher bar than the
 *     `tabs` permission that used to be sufficient.
 */
async function tradeNonceForToken(nonce) {
  if (typeof nonce !== "string" || !nonce) return null;

  const held = await chrome.storage.session.get("scrapexPickerHandoff");
  const handoff = held.scrapexPickerHandoff;
  if (!handoff || handoff.nonce !== nonce) return null;

  // SPENT ON SIGHT, before the expiry is even considered. An early return that
  // left the handoff in place would make a wrong guess free to repeat.
  await chrome.storage.session.remove("scrapexPickerHandoff");

  if (!handoff.expires || Date.now() > handoff.expires) return null;
  return handoff.token || null;
}

chrome.runtime.onMessageExternal.addListener((message, sender, respond) => {
  const origin = (sender && sender.origin) || "";
  if (origin !== PICKER_ORIGIN) {
    trace.mark("picker-message-refused", {origin});
    respond({ok: false});
    return false;
  }
  if (!message || typeof message.kind !== "string") {
    respond({ok: false});
    return false;
  }

  if (message.kind === "scrapex-picker-token") {
    tradeNonceForToken(message.nonce).then(
      (token) => {
        trace.mark("picker-token-handed", {granted: Boolean(token)});
        respond(token ? {ok: true, token} : {ok: false});
      },
      () => respond({ok: false}));
    return true;                     // the reply is asynchronous
  }

  if (message.kind !== "scrapex-picked-spreadsheet") {
    respond({ok: false});
    return false;
  }

  // A FILE ID AND NOTHING ELSE. Whatever else the page sent is dropped here
  // rather than forwarded, so a future field cannot arrive in the panel without
  // someone adding it deliberately on this line.
  const picked = {
    fileId: typeof message.fileId === "string" ? message.fileId : null,
    name: typeof message.name === "string" ? message.name : "",
  };
  trace.mark("picker-message", {picked: Boolean(picked.fileId)});

  // chrome.storage.session, not local: a choice the owner made a moment ago is
  // meaningless after the browser closes, and writing it to disk would keep a
  // record of a document nobody asked us to remember.
  //
  // The handoff dies with the choice too. Picking is the last thing the page
  // needs a token for, and one left behind is one that can still be traded.
  chrome.storage.session.set({scrapexPickedSpreadsheet: picked})
    .then(() => chrome.storage.session.remove("scrapexPickerHandoff"))
    .then(() => respond({ok: true}), () => respond({ok: false}));
  return true;                       // the reply is asynchronous
});

// RETRIEVING THE TRACE. Run scrapexTrace() in the service worker's console
// (chrome://extensions -> ScrapeX -> "service worker"). The two contexts write
// to separate keys, so this is where they are merged back onto one clock — the
// host's opening interval and the document's startup in a single ordered list.
globalThis.scrapexTrace = async function scrapexTrace() {
  const keys = [
    globalThis.ScrapeXStartupTrace.HOST_KEY,
    globalThis.ScrapeXStartupTrace.DOCUMENT_KEY,
  ];
  const stored = await chrome.storage.session.get(keys);
  const rows = [];
  for (const key of keys) {
    const where = key.endsWith("Host") ? "worker" : "document";
    for (const event of stored[key]?.events || []) rows.push({...event, where});
  }
  rows.sort((left, right) => left.epochMs - right.epochMs);
  const first = rows.length ? rows[0].epochMs : 0;
  return rows.map((row) => ({
    "+ms": Math.round((row.epochMs - first) * 10) / 10,
    where: row.where,
    event: row.name,
    detail: row.detail,
  }));
};

// On first install, open the onboarding page so the user immediately learns the
// ScrapeX engine (local Python) must be installed for the tool to work.
chrome.runtime.onInstalled.addListener((details) => {
  trace.mark("runtime-on-installed", {reason: details.reason});
  if (details.reason === "install") {
    chrome.tabs.create({url: chrome.runtime.getURL("onboarding.html")});
  }
});
