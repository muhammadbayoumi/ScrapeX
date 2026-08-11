// A startup trace that SURVIVES a blank Side Panel.
//
// The defect this exists for is invisible to every tool that reports at the
// end: the panel host opens, the document stays blank, and nothing that waits
// for "startup finished" ever runs. So nothing here is buffered. Every mark is
// written to chrome.storage.session the moment it is made, and the record of an
// incomplete startup is exactly as retrievable as the record of a good one.
//
// The document and the service worker write to SEPARATE keys on purpose. One
// shared key read-modify-written from two contexts loses events precisely when
// both are busy, which is startup. Retrieval merges them on the clock.
//
// Classic script, no modules, no imports: it must run as the first thing in the
// document, before anything that could fail has a chance to.
(function (global) {
  "use strict";

  const DOCUMENT_KEY = "scrapexStartupTraceDocument";
  const HOST_KEY = "scrapexStartupTraceHost";
  // Enough to hold several startups; a trace that evicts the evidence is a
  // trace that reproduces the original problem in a new place.
  const MAX_EVENTS = 500;

  // The events that CANNOT happen while a blank panel sits untouched. Whichever
  // of these arrives first is the browser reacting to the owner's click outside
  // the panel — the single measurement this whole investigation was missing.
  const LIFECYCLE_EVENTS = new Set([
    "focus", "blur", "visibilitychange", "pageshow", "resize",
    "document-animation-frame-fired",
  ]);

  function createTrace(storageKey) {
    const events = [];
    const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    let sequence = 0;
    let writing = Promise.resolve();
    let sawLifecycleEvent = false;
    let listeners = [];

    function storageArea() {
      try {
        return global.chrome && global.chrome.storage && global.chrome.storage.session;
      } catch (_) {
        return undefined;
      }
    }

    // Writes are chained rather than fired in parallel: chrome.storage.session
    // resolves out of order under load, and the last writer would otherwise be
    // an older snapshot. The chain never rejects, so one failed write cannot
    // stop the next one.
    function persist() {
      const area = storageArea();
      if (!area) return writing;
      const snapshot = {runId, events: events.slice()};
      writing = writing.then(
        () => area.set({[storageKey]: snapshot}),
        () => area.set({[storageKey]: snapshot}),
      ).catch(() => {});
      return writing;
    }

    function clock() {
      const stamp = {dateNow: Date.now()};
      try {
        const perf = global.performance;
        if (perf && typeof perf.now === "function") {
          stamp.perfNow = perf.now();
          if (Number.isFinite(perf.timeOrigin)) {
            stamp.timeOrigin = perf.timeOrigin;
            stamp.epochMs = perf.timeOrigin + stamp.perfNow;
          }
        }
      } catch (_) {}
      if (!Number.isFinite(stamp.epochMs)) stamp.epochMs = stamp.dateNow;
      return stamp;
    }

    function mark(name, detail, overrides) {
      const entry = Object.assign({seq: ++sequence, name}, clock(), overrides || {});
      if (detail !== undefined) entry.detail = detail;
      // Also a performance mark, so the same timeline is readable in DevTools
      // without going through storage. The storage write remains the record
      // that survives; this is the convenience copy.
      try {
        if (detail === undefined) global.performance.mark(`scrapex:${name}`);
        else global.performance.mark(`scrapex:${name}`, {detail});
      } catch (_) {}
      events.push(entry);
      if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS);
      persist();

      // Recorded once, as its own mark, so reading the trace does not require
      // knowing which events are impossible during an untouched blank panel.
      if (!sawLifecycleEvent && LIFECYCLE_EVENTS.has(name)) {
        sawLifecycleEvent = true;
        mark("first-lifecycle-event-after-start", {event: name});
      }
      return entry;
    }

    function adopt(name, stamp, detail) {
      // A mark made in another context keeps ITS clock, not ours. Rewriting the
      // timestamp on arrival is how a delayed message becomes a fast startup.
      const overrides = {};
      if (stamp && Number.isFinite(stamp.epochMs)) overrides.epochMs = stamp.epochMs;
      if (stamp && Number.isFinite(stamp.dateNow)) overrides.dateNow = stamp.dateNow;
      if (stamp && Number.isFinite(stamp.perfNow)) overrides.perfNow = stamp.perfNow;
      if (stamp && Number.isFinite(stamp.timeOrigin)) overrides.timeOrigin = stamp.timeOrigin;
      return mark(name, detail, overrides);
    }

    function observe(target, type, describe) {
      if (!target || typeof target.addEventListener !== "function") return;
      const listener = (event) => {
        let detail;
        try { detail = describe ? describe(event) : undefined; } catch (_) {}
        mark(type, detail);
      };
      target.addEventListener(type, listener, true);
      listeners.push([target, type, listener]);
    }

    function stop() {
      listeners.forEach(([target, type, listener]) => {
        try { target.removeEventListener(type, listener, true); } catch (_) {}
      });
      listeners = [];
    }

    return {
      runId,
      storageKey,
      mark,
      adopt,
      observe,
      stop,
      events: () => events.slice(),
      flushed: () => writing,
    };
  }

  const api = {createTrace, DOCUMENT_KEY, HOST_KEY, MAX_EVENTS, LIFECYCLE_EVENTS};

  // Usable from a classic script in the panel, from the service worker, and
  // from `node --test` without a Chrome present.
  if (typeof module === "object" && module.exports) module.exports = api;
  global.ScrapeXStartupTrace = api;
})(typeof globalThis === "undefined" ? this : globalThis);
