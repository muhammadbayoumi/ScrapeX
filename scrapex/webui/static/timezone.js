(function () {
  "use strict";

  // ---- ONE display time zone, shared by the side panel and the Workspace ----
  //
  // Spec 33 (issue #33) is DISPLAY-ONLY, and this module is where that promise
  // is kept. Nothing here writes a timestamp: the warehouse keeps every instant
  // as "%Y-%m-%dT%H:%M:%SZ" and scrapex/payload.py refuses a scraped_at that is
  // not UTC (contracts/fixtures/payload_invalid_timezone.json is that test's
  // vector), so a zone can only ever change what a screen SAYS.
  //
  // It is a byte-for-byte copy of scrapex/webui/static/timezone.js, exactly as
  // appearance.js is: a chrome-extension:// page and http://127.0.0.1 are
  // different origins and cannot share one file. A test fails if the two drift.
  //
  // There is ONE formatter in here and three thin adapters onto it, because
  // this codebase emits time in three ways — a Jinja template (data-utc
  // markup), an HTML string (markup()), and a built DOM node (node()). Each
  // ends up at the same format() call, and each leaves the raw UTC value in the
  // element, which is what makes both the immediate re-render (§6.10) and the
  // original-still-reachable rule (§6.12) fall out for free instead of needing
  // their own machinery.

  const STORAGE_KEY = "scrapex-timezone-v1";
  const SYNC_PATH = "/api/timezone";
  // A preference the owner edits perhaps twice a year does not deserve the
  // appearance module's 2s poll — especially while ten sources are crawling
  // and every GET opens a read connection. Five seconds still means the panel
  // and the page agree before he can look from one to the other.
  const POLL_MS = 5000;
  const UTC = "UTC";
  const LOCALE = "en-GB";  // UI text is English (bilingual rule); zone ids are never translated.

  // An INSTANT and nothing else. A calendar date ("2026-07-30", a
  // price_observation.business_date) is not a moment in time: shifting it into
  // another zone would either do nothing or silently move it a day, and it
  // would be reporting a fact the warehouse never recorded. Values that are not
  // instants pass through this module untouched, on purpose.
  // "T" and not a space: every producer in the engine writes the T form
  // (strftime('%Y-%m-%dT%H:%M:%SZ')), and the space form is not something
  // Date.parse is specified to handle — accepting it would mean guessing.
  const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$/;

  // Every shape any surface in the product asks for, declared once.
  const SHAPES = Object.freeze({
    datetime: {day: "numeric", month: "long", year: "numeric",
               hour: "numeric", minute: "2-digit", hour12: true},
    date: {day: "numeric", month: "long", year: "numeric"},
    time: {hour: "numeric", minute: "2-digit", hour12: true},
    // The compact form the panel's kept-pages line uses: a run that stopped is
    // identified by WHICH day, not by the year it happened in.
    short: {day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
            hour12: true},
  });

  const listeners = new Set();
  let remoteBase = "";
  let pollTimer = null;
  let pushTimer = null;
  let current = read();

  // ---- the zone, and how we arrived at it (§6.5, §6.11) ---------------------

  function usable(zone) {
    if (!zone || typeof zone !== "string") return false;
    try {
      new Intl.DateTimeFormat(LOCALE, {timeZone: zone});
      return true;
    } catch (error) {
      return false;   // RangeError: not a zone this browser's tz data knows.
    }
  }

  function detected() {
    try {
      const zone = new Intl.DateTimeFormat().resolvedOptions().timeZone;
      return usable(zone) ? zone : "";
    } catch (error) {
      return "";
    }
  }

  /** This machine's UTC offset as a zone, for a browser that names none.
   *
   * Etc/GMT signs are INVERTED against everything else in the world:
   * Etc/GMT-3 is UTC+3. getTimezoneOffset() is inverted the same way (it
   * returns -180 for UTC+3), so the two cancel and the sign is copied
   * straight across. Fixed offsets are the wrong PRIMARY configuration
   * (§6.4 — they cannot follow daylight saving), which is exactly why this is
   * the last step before giving up rather than an option in the selector.
   */
  function systemOffsetZone() {
    const minutes = new Date().getTimezoneOffset();
    if (!Number.isFinite(minutes) || minutes % 60 !== 0) return "";
    const hours = minutes / 60;
    if (hours === 0) return UTC;
    const zone = `Etc/GMT${hours > 0 ? "+" : "-"}${Math.abs(hours)}`;
    return usable(zone) ? zone : "";
  }

  /** Which zone is in force, which step of the chain produced it, and why.
   *
   * §6.11's order, in order: selected -> detected -> system -> UTC. It reports
   * the step rather than failing silently, and it NEVER writes: an unusable
   * saved zone stays saved exactly as the owner typed it, so fixing his tz
   * data restores his choice instead of finding it quietly overwritten.
   */
  function resolution(value = current) {
    const requested = value && value.zone ? String(value.zone) : "";
    if (requested && usable(requested)) {
      return {zone: requested, step: "selected", requested,
              note: `Times are shown in ${requested}, the zone you chose.`};
    }
    const rejected = requested
      ? `${requested} is not a time zone this browser can resolve, so it was ` +
        "not used — your saved choice is untouched. "
      : "";
    const local = detected();
    if (local) {
      return {zone: local, step: "detected", requested,
              note: `${rejected}Times are shown in ${local}, detected from this browser.`};
    }
    const offset = systemOffsetZone();
    if (offset) {
      return {zone: offset, step: "system", requested,
              note: `${rejected}No zone name was available, so times are shown at ` +
                    `this machine's own UTC offset (${offset}).`};
    }
    return {zone: UTC, step: "utc", requested,
            note: `${rejected}No time zone was available, so times are shown in UTC.`};
  }

  const zone = () => resolution().zone;

  /** Every zone the browser itself knows (§6.4) — never a hand-written list.
   *
   * A list typed into this file would start rotting the day a country moved its
   * clocks. When supportedValuesOf is missing the honest answer is a short list
   * of the zones we can actually name here, flagged as incomplete, rather than
   * 400 invented strings.
   */
  function zones() {
    let all = [];
    try {
      if (typeof Intl.supportedValuesOf === "function") {
        all = Intl.supportedValuesOf("timeZone") || [];
      }
    } catch (error) {
      all = [];
    }
    const complete = all.length > 0;
    const known = new Set(complete ? all : []);
    // The detected zone and the saved one must always be selectable, even if
    // this browser leaves them out of its own enumeration.
    [detected(), current.zone].forEach((extra) => {
      if (extra && usable(extra)) known.add(extra);
    });
    known.add(UTC);
    return {zones: [...known].sort(), complete};
  }

  // ---- the one formatter ----------------------------------------------------

  const isInstant = (value) =>
    typeof value === "string" && INSTANT.test(value.trim());

  function assemble(parts, wantsClock) {
    const get = (type) => {
      const found = parts.find((part) => part.type === type);
      return found ? found.value : "";
    };
    const day = [get("day"), get("month"), get("year")].filter(Boolean).join(" ");
    const hour = get("hour");
    const minute = get("minute");
    const clock = wantsClock && hour && minute ? `${hour}:${minute}` : "";
    // "am" in en-GB, and the issue's own example is "11:05 AM".
    const period = clock && get("dayPeriod")
      ? " " + get("dayPeriod").replace(/\./g, "").toUpperCase()
      : "";
    if (day && clock) return `${day}, ${clock}${period}`;
    return day || `${clock}${period}` || "";
  }

  /** A stored UTC instant, as the active zone shows it.
   *
   * Anything that is not an instant is returned exactly as it arrived. That is
   * not defensive padding: business_date columns and em-dash placeholders go
   * through the same call sites, and a formatter that guessed at them would be
   * inventing data on a display-only feature.
   */
  function format(value, mode = "datetime") {
    if (!isInstant(value)) return value == null ? "" : String(value);
    const ms = Date.parse(value.trim());
    if (!Number.isFinite(ms)) return String(value);
    const shape = SHAPES[mode] || SHAPES.datetime;
    const active = zone();
    try {
      const parts = new Intl.DateTimeFormat(LOCALE, {...shape, timeZone: active})
        .formatToParts(new Date(ms));
      return assemble(parts, shape.hour !== undefined);
    } catch (error) {
      // Unreachable through resolution() — but a formatter on a display-only
      // path must never be the reason a page fails to render.
      return String(value);
    }
  }

  /** The issue's own shape: "30 July 2026, 11:05 AM — Asia/Riyadh" (§6.8). */
  function label(value, mode = "datetime") {
    if (!isInstant(value)) return format(value, mode);
    return `${format(value, mode)} — ${zone()}`;
  }

  /** What the warehouse actually holds, for the tooltip (§6.12). */
  const original = (value) => `Stored as ${String(value).trim()} (UTC)`;

  // ---- the three adapters --------------------------------------------------

  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g,
    (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

  /** Fill one element that carries data-utc. The raw value stays in the
   *  attribute, so this is idempotent and can run again on every zone change
   *  without anything having to be fetched or re-derived. */
  function hydrate(element) {
    const raw = element.getAttribute("data-utc");
    if (!isInstant(raw)) return;   // leave an authored placeholder alone
    const mode = element.getAttribute("data-utc-format") || "datetime";
    const converted = element.getAttribute("data-utc-zone") === "show"
      ? label(raw, mode)
      : format(raw, mode);
    // An <option> cannot contain a child element, so the one call site whose
    // time is part of a longer label carries that label here instead. Without
    // it that site would need a formatter of its own, which is the duplication
    // this module exists to prevent.
    const shown = (element.getAttribute("data-utc-prefix") || "") + converted;
    if (element.textContent !== shown) element.textContent = shown;
    if (element.title !== original(raw)) element.title = original(raw);
    // <time datetime> stays the machine-readable UTC instant, never the
    // converted text — the same rule as the title, for anything parsing it.
    if (element.tagName === "TIME" && element.getAttribute("datetime") !== raw) {
      element.setAttribute("datetime", raw);
    }
  }

  /** Re-render every converted time under `root` from the data already in the
   *  DOM (§6.10: no refetch, and nothing about the data is touched). */
  function paint(root) {
    const scope = root || document;
    if (scope.nodeType === 1 && scope.hasAttribute("data-utc")) hydrate(scope);
    scope.querySelectorAll("[data-utc]").forEach(hydrate);
    // A caption clamped to one line loses its tail to an ellipsis, and the
    // recovery has to be the WHOLE line — a title that stops where the visible
    // text starts being interesting recovers nothing. The server cannot write
    // it here, because half the sentence is a time this module has not
    // converted yet, so the element asks to be titled and we do it after the
    // conversion, from the text the reader actually sees.
    scope.querySelectorAll("[data-clamped-title]").forEach((element) => {
      const whole = element.textContent.replace(/\s+/g, " ").trim();
      if (element.title !== whole) element.title = whole;
    });
    syncControls(scope);
  }

  /** For a surface that builds an HTML string. */
  function markup(value, mode = "datetime", options) {
    if (!isInstant(value)) return esc(value == null ? "" : value);
    const wantsZone = Boolean(options && options.zone);
    // The TEXT has to agree with the attribute. It read format() here while the
    // attribute said data-utc-zone="show", so a value shipped without its zone
    // and then grew one the first time anything re-painted it — the same
    // element saying two different things depending on when you looked.
    const shown = wantsZone ? label(value, mode) : format(value, mode);
    return `<time data-utc="${esc(value)}" data-utc-format="${esc(mode)}"` +
      `${wantsZone ? ' data-utc-zone="show"' : ""} datetime="${esc(value)}" ` +
      `title="${esc(original(value))}" dir="ltr">${esc(shown)}</time>`;
  }

  /** For a surface that builds DOM nodes. */
  function node(value, mode = "datetime", options) {
    if (!isInstant(value)) {
      const plain = document.createElement("span");
      plain.textContent = value == null ? "" : String(value);
      return plain;
    }
    const element = document.createElement("time");
    element.dir = "ltr";
    element.setAttribute("data-utc", value);
    element.setAttribute("data-utc-format", mode);
    if (options && options.zone) element.setAttribute("data-utc-zone", "show");
    hydrate(element);
    return element;
  }

  // ---- the preference: stored, shared, and never invented ------------------

  function normalize(value) {
    const candidate = value && typeof value === "object" ? value : {};
    // An empty zone is the DEFAULT STATE, not a missing value: it means "follow
    // whatever this browser detects", which is how §6.5 detects a default
    // without ever overwriting a choice the owner made.
    const raw = candidate.zone;
    return {
      zone: typeof raw === "string" ? raw.trim() : "",
      updatedAt: Number.isFinite(Number(candidate.updatedAt))
        ? Math.max(0, Number(candidate.updatedAt))
        : 0,
    };
  }

  function read() {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) return normalize(JSON.parse(saved));
    } catch (error) {
      // The zone stays optional when browser storage is blocked or corrupt.
    }
    return {zone: "", updatedAt: 0};
  }

  function remember(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (error) {
      // Same: a blocked localStorage costs persistence, never the page.
    }
  }

  function syncControls(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const state = resolution();
    scope.querySelectorAll("[data-time-zone-select]").forEach((select) => {
      // Assigning a value that has no matching <option> leaves the select on
      // "" — Detected — which is exactly what a saved zone this browser cannot
      // resolve should show, next to the note explaining why.
      if (select.value !== current.zone) select.value = current.zone;
    });
    scope.querySelectorAll("[data-time-zone-active]").forEach((element) => {
      element.textContent = state.zone;
    });
    scope.querySelectorAll("[data-time-zone-note]").forEach((element) => {
      element.textContent = state.note;
    });
    scope.querySelectorAll("[data-time-zone-step]").forEach((element) => {
      element.textContent = state.step;
    });
  }

  function notify() {
    const detail = resolution();
    listeners.forEach((listener) => listener(detail));
    window.dispatchEvent(new CustomEvent("scrapextimezonechange", {detail}));
  }

  function adopt(value, notifyChange = true) {
    current = normalize(value);
    remember(current);
    paint(document);
    if (notifyChange) notify();
    return {...current};
  }

  async function pushRemote() {
    if (!remoteBase || !current.updatedAt) return false;
    try {
      const response = await fetch(`${remoteBase}${SYNC_PATH}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(current),
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  function schedulePush() {
    if (!remoteBase) return;
    window.clearTimeout(pushTimer);
    pushTimer = window.setTimeout(pushRemote, 120);
  }

  /** Choose a zone. "" means "follow this browser's detected zone". */
  function set(nextZone) {
    const nextTimestamp = Math.max(Date.now(), current.updatedAt + 1);
    const result = adopt({zone: nextZone, updatedAt: nextTimestamp});
    schedulePush();
    return result;
  }

  async function pullRemote() {
    if (!remoteBase || document.visibilityState === "hidden") return false;
    try {
      const response = await fetch(`${remoteBase}${SYNC_PATH}`, {cache: "no-store"});
      if (!response.ok) return false;
      const body = await response.json();
      const remote = body && body.timezone ? normalize(body.timezone) : null;
      if (remote && remote.updatedAt > current.updatedAt) adopt(remote);
      else if (!remote && current.updatedAt) await pushRemote();
      else if (remote && current.updatedAt > remote.updatedAt) await pushRemote();
      return true;
    } catch (error) {
      return false;
    }
  }

  async function connect(baseUrl = "") {
    const clean = String(baseUrl || "").replace(/\/+$/, "");
    if (!clean) return false;
    remoteBase = clean;
    const connected = await pullRemote();
    window.clearInterval(pollTimer);
    pollTimer = window.setInterval(pullRemote, POLL_MS);
    return connected;
  }

  /** Fill a <select data-time-zone-select> from the browser's own zone list.
   *
   * Built as DOM rather than as markup: tests/test_vendor.py refuses a new
   * innerHTML assignment in any UI script, and it is right to — an option's
   * text should never be able to become live markup, whatever its source. */
  function bindSelect(select) {
    if (select.dataset.timeZoneBound === "true") return;
    select.dataset.timeZoneBound = "true";
    const {zones: all, complete} = zones();
    const local = detected();
    select.replaceChildren();
    // "" is the DEFAULT: follow whatever this browser detects (§6.5). It is
    // first because it is the state a fresh install is in.
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = local ? `Detected (${local})` : "Detected";
    select.append(auto);
    all.forEach((id) => {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = id;   // an IANA identifier is never translated
      select.append(option);
    });
    select.dataset.timeZoneComplete = String(complete);
    select.value = current.zone;
    select.addEventListener("change", () => set(select.value));
  }

  function bindControls() {
    document.querySelectorAll("[data-time-zone-select]").forEach(bindSelect);
    paint(document);
  }

  function subscribe(listener) {
    listeners.add(listener);
    return function unsubscribe() { listeners.delete(listener); };
  }

  window.ScrapeXTime = Object.freeze({
    get: () => ({...current}),
    set,
    zone,
    zones,
    resolution,
    detected,
    isInstant,
    format,
    label,
    markup,
    node,
    paint,
    connect,
    refresh: pullRemote,
    subscribe,
  });

  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) return;
    const saved = read();
    if (saved.updatedAt < current.updatedAt) return;
    adopt(saved);
  });
  window.addEventListener("focus", pullRemote);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") pullRemote();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindControls, {once: true});
  } else {
    bindControls();
  }

  if (/^https?:$/.test(window.location.protocol)) {
    connect(window.location.origin);
  }
})();
