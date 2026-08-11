// The ONE script of the minimal diagnostic page. It records its own execution
// and the lifecycle events that cannot occur while a blank panel sits untouched
// — and it does nothing else. No fetch, no storage read, no appearance, no
// requestAnimationFrame gate, no bootstrap.
//
// The static text above it is already on screen by the time this runs, or it
// never will be; this file cannot make it appear and deliberately does not try.
(function () {
  "use strict";

  const factory = globalThis.ScrapeXStartupTrace;
  const trace = factory.createTrace(factory.DOCUMENT_KEY);
  globalThis.ScrapeXPanelTrace = trace;

  function snapshot(extra) {
    let hasFocus = null;
    try { hasFocus = document.hasFocus(); } catch (_) {}
    return Object.assign({
      page: "diagnostic",
      readyState: document.readyState,
      visibilityState: document.visibilityState,
      hasFocus,
    }, extra || {});
  }

  trace.mark("document-first-script", snapshot({url: location.href}));

  const state = document.getElementById("script-state");
  if (state) state.textContent = "the one script ran";

  trace.observe(window, "pageshow", (event) => snapshot({persisted: event.persisted}));
  trace.observe(window, "focus", () => snapshot());
  trace.observe(window, "blur", () => snapshot());
  trace.observe(window, "resize", () => snapshot());
  trace.observe(document, "visibilitychange", () => snapshot());

  window.addEventListener("load", () => trace.mark("load", snapshot()), {once: true});

  // Requested purely as evidence of whether the compositor drives this
  // document. Nothing on this page waits for it.
  trace.mark("document-animation-frame-requested", snapshot());
  requestAnimationFrame((timestamp) => {
    trace.mark("document-animation-frame-fired", snapshot({timestamp}));
  });

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
})();
