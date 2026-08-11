// The Side Panel document's own half of the startup trace.
//
// This runs before the stylesheets, before app.js, and before anything that can
// throw. It writes straight to chrome.storage.session through startup-trace.js,
// so a document that never paints still leaves a complete record behind.
//
// MV3 forbids inline scripts on extension pages (`script-src 'self'`), so this
// is a separate file rather than an inline block. It is still the first script
// the document executes.
(function () {
  "use strict";

  const factory = globalThis.ScrapeXStartupTrace;
  if (!factory) return;
  const trace = factory.createTrace(factory.DOCUMENT_KEY);
  globalThis.ScrapeXPanelTrace = trace;

  function snapshot(extra) {
    let hasFocus = null;
    try { hasFocus = document.hasFocus(); } catch (_) {}
    return Object.assign({
      readyState: document.readyState,
      visibilityState: document.visibilityState,
      hasFocus,
    }, extra || {});
  }

  // The earliest extension-owned timestamp in the document. Chrome does not
  // hand the toolbar click to the panel, so the gap between the service
  // worker's `side-panel-open-request` and this mark IS the host's opening
  // interval — the measurement that was missing.
  trace.mark("document-first-script", snapshot({url: location.href}));

  document.addEventListener("DOMContentLoaded",
    () => trace.mark("dom-content-loaded", snapshot()), {once: true});
  window.addEventListener("load",
    () => trace.mark("load", snapshot()), {once: true});

  // Captured through startup-trace's own observer so the first one to arrive is
  // recorded as `first-lifecycle-event-after-start`. On a blank untouched
  // panel none of these can fire on their own: whichever appears is the
  // browser reacting to the owner clicking outside the panel.
  trace.observe(window, "pageshow", (event) => snapshot({persisted: event.persisted}));
  trace.observe(window, "focus", () => snapshot());
  trace.observe(window, "blur", () => snapshot());
  trace.observe(window, "resize", () => snapshot({
    width: window.innerWidth, height: window.innerHeight,
  }));
  trace.observe(document, "visibilitychange", () => snapshot());

  // Whether the renderer ever offers this document a frame, recorded as a
  // request and a firing rather than as a single "it worked". A request with no
  // matching firing is the signature of a document the compositor is not
  // driving.
  try {
    trace.mark("document-animation-frame-requested", snapshot());
    requestAnimationFrame((timestamp) => {
      trace.mark("document-animation-frame-fired", snapshot({timestamp}));
    });
  } catch (_) {}

  // An independent clock that does not depend on the compositor at all. If the
  // timer fires and the frame never does, the document is running and simply
  // not being painted.
  const timerRequestedAt = Date.now();
  trace.mark("fallback-timer-requested", snapshot({delayMs: 250}));
  setTimeout(() => {
    trace.mark("fallback-timer-fired", snapshot({
      actualDelayMs: Date.now() - timerRequestedAt,
    }));
  }, 250);

  // first-contentful-paint is the browser's own word for "pixels reached the
  // screen". Its ABSENCE in a trace is the finding: the document ran, and
  // nothing was ever painted.
  try {
    const observer = new PerformanceObserver((list) => {
      const paint = list.getEntries()
        .find((entry) => entry.name === "first-contentful-paint");
      if (!paint) return;
      trace.mark("first-contentful-paint", snapshot({startTime: paint.startTime}), {
        epochMs: performance.timeOrigin + paint.startTime,
      });
      observer.disconnect();
    });
    observer.observe({type: "paint", buffered: true});
  } catch (_) {}

  window.addEventListener("error", (event) => {
    trace.mark("document-error", snapshot({
      message: String(event.message || ""),
      source: String(event.filename || ""),
      line: event.lineno || 0,
    }));
  });
  window.addEventListener("unhandledrejection", (event) => {
    let message = "";
    try { message = String(event.reason && event.reason.message || event.reason || ""); }
    catch (_) {}
    trace.mark("document-unhandled-rejection", snapshot({message}));
  });
})();
