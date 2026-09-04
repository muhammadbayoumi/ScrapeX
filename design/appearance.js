/* One appearance engine — palette, mode and the first painted frame.
 *
 * AUTHORED IN design/appearance.js, and copied byte-for-byte into
 * extension/appearance.js and scrapex/webui/static/appearance.js by
 * tools/sync_design_assets.py. The extension and the packaged web workspace
 * cannot import from each other at runtime, so each needs its own copy.
 *
 * IF THE PATH ABOVE YOUR EDITOR IS NOT design/, THIS IS A GENERATED COPY.
 *
 * THIS FILE IS WHY THE WARNING EXISTS. The engine-poll backoff below was
 * written straight into extension/appearance.js — reviewed, correct, and
 * one `sync_design_assets.py` run away from being erased with no diff, no
 * failure and nothing to notice. It was caught by another pair of eyes, not by
 * anything in the repository. This header is the thing that catches it now.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "scrapex-appearance-v2";
  const LEGACY_STORAGE_KEY = "scrapex-appearance-v1";
  const SYNC_PATH = "/api/appearance";
  const SCHEMES = new Set(["light", "dark"]);
  // R-84: ONE COLOUR CHOICE. `brand` (WhatsApp) and `blue` (GitHub) were deleted on
  // 2026-08-31 -- «احذف الثلاثة وابق supabase وحده» -- together with device colours.
  // R-74 had made Supabase the baseline and named those three as exceptions ON it;
  // asked directly whether the exceptions survive, he removed them.
  //
  // A STORED CHOICE NEEDS NO MIGRATION, and that is why none was written.
  // `resolvePalette` already returns `DEFAULTS.palette` for an id it does not know,
  // so every appearance stored before today -- `whatsapp`, `github`, `brand`, `blue`
  // -- resolves to `supabase` on its own. The aliases below are kept for the same
  // reason they were built: they are what a stored record actually contains.
  const PALETTES = new Map([
    ["supabase", {
      id: "supabase",
      label: "Supabase",
      description: "Supabase console green, flat and bordered",
      colors: ["#131413", "#3ECF8E", "#85E0BA", "#FDFDFD"],
      themes: {light: {}, dark: {}},
    }],
  ]);
  // R-59 DECISION 3, BUILT. `whatsapp` and `github` are legacy compatibility
  // aliases for `brand` and `blue`. The ruling said so on 2026-08-09 and only
  // the aliases were ever enforced -- `scrapex/webui/app.py` refused any palette
  // outside those two names while the registry they alias did not exist, which
  // is what OP-82 recorded.
  //
  // THEY ARE NOT DECORATION: every appearance stored before today carries one of
  // these two ids, in localStorage and in the engine's `ui_appearance` setting.
  // Resolving them in normalize() is what stops an existing user's choice from
  // silently reverting to the default.
  // The four ids a stored record can carry, all resolving to the one that remains.
  // Naming them explicitly rather than letting resolvePalette's fallback swallow
  // them keeps the intent readable: these are not unknown ids, they are RETIRED ones.
  const PALETTE_ALIASES = new Map([
    ["whatsapp", "supabase"],
    ["github", "supabase"],
    ["brand", "supabase"],
    ["blue", "supabase"],
  ]);
  const DEFAULTS = Object.freeze({
    mode: "device",
    scheme: "light",
    // R-73: `supabase` is the default appearance, superseding R-59 decision 1's
    // `brand`.
    palette: "supabase",
    // AND THIS IS THE LINE THAT MAKES THE ONE ABOVE MEAN ANYTHING. It was `true`,
    // and apply() returns early on that branch after clearTheme() -- so the named
    // default palette was never applied for a user with no stored preference.
    // `github` was the default for as long as the setting existed and NOBODY
    // EVER SAW IT; a rename alone would have satisfied the request in the
    // register and changed nothing on screen.
    //
    // He asked for the numbers before deciding and then chose the flip. What it
    // costs, enumerated over normalize()'s own precedence rather than estimated:
    //
    //   no stored record at all          -> CHANGES. Sees supabase.
    //   v2 record, deviceColors either way -> unchanged, the stored boolean wins
    //   v1 record, followColors either way -> unchanged, the legacy key wins
    //   v1 record, neither key            -> unchanged, derived from `mode`
    //
    // ONE state of eight, and it is the only one that never expressed a choice.
    // No migration: normalize() already resolves every stored shape. No server
    // change: _appearance_value has no defaults and GET returns null when unset.
    //
    // What it also fixes, unasked: the fallback a fresh user actually got was
    // `tokens.css`'s :root teal -- the residue R-59 decision 2 calls "deprecated
    // ... migration debt" -- or the OS AccentColor where the browser exposes one.
    // The deprecated colour was the shipped default, not a leftover.
    //
    // AND R-84 DELETED IT ON 2026-08-31. The paragraph above is kept because C4
    // wants the history of a decision rather than its last state: the flip he
    // asked for the numbers on is what made `supabase` the colour a fresh install
    // actually painted, and four weeks later he removed the switch it flipped.
    // There is no `deviceColors` key any more -- normalize() below still READS a
    // stored one and discards it, which is what makes the removal migration-free.
    updatedAt: 0,
  });
  const THEME_PROPERTIES = Object.freeze([
    "bg", "surface", "surface-subtle", "surface-raised", "line", "line-strong",
    "text", "muted", "text-subtle", "chip", "accent", "accent-hover",
    "accent-active", "accent-ink", "accent-contrast", "accent-weak", "focus",
    "control-hover", "button-bg", "button-hover", "button-active",
    "button-text", "button-hover-text", "amber", "amber-weak", "red",
    "red-hover", "red-weak",
    "danger-contrast", "switch-track", "switch-track-hover",
    "switch-track-off", "switch-thumb", "switch-thumb-off", "shadow-color",
    "overlay",
  ]);
  // R-74 · THERE IS NO SECOND AXIS, AND THAT IS THE RULING.
  //
  // The 36 properties above are colours, and under R-74 a palette may set
  // NOTHING ELSE: «whatsapp, github الوان theme يمكن اختيارها بواسطة المستخدم
  // فتعدل على الالوان فقط لا تعدل على design system».
  //
  // R-73 added a DESIGN_PROPERTIES list here so a palette could carry radius,
  // typography, elevation and motion. It is removed rather than left unused,
  // because «واى تعارض معاها يلغى» and a mechanism whose whole purpose is "a
  // palette may change the design system" is the conflict itself.
  //
  // The design system did not go anywhere -- it moved to where it belongs.
  // design/tokens.css IS the Supabase design system now, so all four colour
  // choices sit on it, including device, which applies no palette at all. That
  // is what R-73's axis could not do: measured on the built engine, it gave the
  // system to `supabase` and left `brand`, `blue` and device on the old 9px
  // radius, 14px body and Segoe UI. Three of four.
  //
  // tests/test_a_palette_may_change_nothing_but_colour.py enforces this, and it
  // is worth saying why a TEST rather than a comment: the failure it catches is
  // silent. A `design` key added to a palette entry would simply be dashed into
  // a `--design` property whose value reads "[object Object]", and nothing about
  // the page would look broken enough to notice.
  const schemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let remoteBase = "";
  let pollTimer = null;
  let pushTimer = null;
  let current = read();

  // A stored or posted id resolved to a registry key. An alias resolves to what
  // it aliases; anything unknown falls back rather than throwing, which is what
  // keeps a modified extension from persisting a name this build cannot paint.
  function resolvePalette(id) {
    const aliased = PALETTE_ALIASES.get(id) || id;
    return PALETTES.has(aliased) ? aliased : DEFAULTS.palette;
  }

  function normalize(value) {
    const candidate = value && typeof value === "object" ? value : {};
    return {
      mode: candidate.mode === "manual" ? "manual" : "device",
      scheme: SCHEMES.has(candidate.scheme) ? candidate.scheme : DEFAULTS.scheme,
      // Resolving rather than testing membership is what carries R-59 decision
      // 3: a preference stored as `whatsapp` or `github` -- which is every
      // preference stored before today -- arrives here and comes out as `brand`
      // or `blue` instead of being dropped on the floor for the default.
      palette: resolvePalette(candidate.palette),
      // `deviceColors` and its v1 name `followColors` are READ AND DISCARDED. Every
      // appearance stored before 2026-08-31 carries one of them, and R-84 removed
      // the mode they selected; dropping the key here rather than rejecting the
      // record is the whole of the migration, and it is why there is no other.
      updatedAt: Number.isFinite(Number(candidate.updatedAt))
        ? Math.max(0, Number(candidate.updatedAt))
        : 0,
    };
  }

  function parseStored(raw) {
    try {
      return normalize(JSON.parse(raw));
    } catch (error) {
      return null;
    }
  }

  function read() {
    try {
      const saved = parseStored(window.localStorage.getItem(STORAGE_KEY));
      if (saved) return saved;
      const legacy = parseStored(window.localStorage.getItem(LEGACY_STORAGE_KEY));
      if (legacy) return legacy;
    } catch (error) {
      // Appearance remains available when browser storage is blocked.
    }
    return {...DEFAULTS};
  }

  function remember(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (error) {
      // Appearance remains optional when browser storage is blocked.
    }
  }

  function effectiveScheme(value = current) {
    return value.mode === "manual"
      ? value.scheme
      : (schemeQuery.matches ? "dark" : "light");
  }

  function dashed(entries) {
    return Object.fromEntries(entries.map(([key, value]) => [
      key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`),
      value,
    ]));
  }

  function themeFor(palette, scheme) {
    return dashed(Object.entries(palette.themes[scheme]));
  }

  function paletteFor(id) {
    // resolvePalette already guarantees a registry key, and normalize() runs on
    // every path into `current`. The `||` is kept because this is the line that
    // decides whether a mistake is a wrong colour or a dead module: apply() runs
    // at module scope, BEFORE window.ScrapeXAppearance is assigned, so a miss
    // here takes the whole IIFE down and every appearance control with it.
    return PALETTES.get(id) || PALETTES.get(DEFAULTS.palette);
  }

  function apply(value) {
    const root = document.documentElement;
    root.dataset.appearance = value.mode;
    // R-84 deleted device colours, so there is one colour mode and no attribute
    // to carry a second. `data-color-mode` is removed rather than pinned to
    // "manual": a stylesheet that still selects on it should stop matching, loudly.
    root.removeAttribute("data-color-mode");
    if (value.mode === "manual") root.dataset.theme = value.scheme;
    else root.removeAttribute("data-theme");


    root.dataset.palette = value.palette;
    const palette = paletteFor(value.palette);
    const theme = themeFor(palette, effectiveScheme(value));
    // Removal is meaningful, not a no-op: `supabase` declares no colours at all
    // because its colours ARE tokens.css's, so this loop removes all 36 and the
    // baseline shows through. `brand` and `blue` set the ones they override and
    // leave the rest to fall through the same way.
    THEME_PROPERTIES.forEach((property) => {
      if (theme[property]) root.style.setProperty(`--${property}`, theme[property]);
      else root.style.removeProperty(`--${property}`);
    });
  }

  function statusText(value = current) {
    const scheme = value.mode === "device"
      ? `Device ${effectiveScheme(value)}`
      : value.scheme;
    const color = paletteFor(value.palette).label;
    return `${scheme} \u00B7 ${color}`;
  }

  function paletteButton(palette) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "appearance-palette-tile";
    button.dataset.appearancePalette = palette.id;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", "false");
    button.setAttribute("aria-label", `${palette.label}: ${palette.description}`);

    const strip = document.createElement("span");
    strip.className = "appearance-palette-strip";
    strip.setAttribute("aria-hidden", "true");
    palette.colors.forEach((color) => {
      const swatch = document.createElement("i");
      swatch.style.setProperty("--palette-swatch", color);
      strip.appendChild(swatch);
    });

    const copy = document.createElement("span");
    copy.className = "appearance-palette-copy";
    const label = document.createElement("strong");
    label.textContent = palette.label;
    const description = document.createElement("small");
    description.textContent = palette.description;
    copy.append(label, description);
    button.append(strip, copy);
    return button;
  }

  function renderPaletteBrowser(container) {
    if (container.dataset.appearanceRendered === "true") return;
    container.dataset.appearanceRendered = "true";
    container.classList.add("appearance-palette-browser");

    const heading = document.createElement("div");
    heading.className = "appearance-palette-heading";
    const title = document.createElement("strong");
    title.textContent = "Colour style";
    const help = document.createElement("small");
    help.textContent = "A complete, tested theme for every surface and state";
    heading.append(title, help);

    const options = document.createElement("div");
    options.className = "appearance-palette-options";
    options.setAttribute("role", "radiogroup");
    options.setAttribute("aria-label", "Colour style");
    options.append(...[...PALETTES.values()].map(paletteButton));
    container.append(heading, options);
    bindPaletteActions(options);
  }

  function bindPaletteActions(scope = document) {
    scope.querySelectorAll("[data-appearance-palette]").forEach((button) => {
      if (button.dataset.appearanceBound === "true") return;
      button.dataset.appearanceBound = "true";
      button.addEventListener("click", () =>
        set({palette: button.dataset.appearancePalette}));
    });
  }

  function syncControls() {
    document.querySelectorAll("[data-appearance-control]").forEach((control) => {
      control.classList.toggle("is-device", current.mode === "device");
      control.querySelectorAll("[data-appearance-scheme-mode]").forEach((button) => {
        const choice = button.dataset.appearanceSchemeMode;
        const active = choice === "device"
          ? current.mode === "device"
          : current.mode === "manual" && current.scheme === choice;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      control.querySelectorAll("[data-appearance-palette]").forEach((button) => {
        const active = button.dataset.appearancePalette === current.palette;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-checked", String(active));
      });
      control.querySelectorAll("[data-appearance-status]").forEach((status) => {
        status.textContent = statusText();
      });
    });
  }

  function notify() {
    const detail = {...current, effectiveScheme: effectiveScheme()};
    listeners.forEach((listener) => listener(detail));
    window.dispatchEvent(new CustomEvent("scrapexappearancechange", {detail}));
  }

  function adopt(value, notifyChange = true) {
    current = normalize(value);
    remember(current);
    apply(current);
    syncControls();
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

  function set(patch) {
    const nextTimestamp = Math.max(Date.now(), current.updatedAt + 1);
    const result = adopt({...current, ...patch, updatedAt: nextTimestamp});
    schedulePush();
    return result;
  }

  // HOW MANY REFUSED CONNECTIONS BEFORE THIS STOPS ASKING. Measured on the
  // owner's machine with no engine running: this polled every 2 seconds for as
  // long as the panel stayed open, and each attempt wrote a red
  // ERR_CONNECTION_REFUSED to the console. Thirty-odd of them in the first
  // minute, none of which a reader can act on, burying the one line that
  // mattered. The engine being absent is a NORMAL state -- it is what every
  // user sees before they install it -- so the panel must be able to sit in it
  // quietly.
  //
  // Six is deliberate: about twelve seconds of retrying covers an engine that
  // is starting up, and stops well before the console becomes unreadable.
  // Polling resumes on focus and whenever `connect` is called again, so a user
  // who starts the engine is never left waiting on a dead poller.
  const QUIET_AFTER_FAILURES = 6;
  let consecutiveFailures = 0;

  function stopPolling(reason) {
    if (pollTimer === undefined) return;
    window.clearInterval(pollTimer);
    pollTimer = undefined;
    try { console.info(`[scrapex] appearance sync paused: ${reason}`); } catch (_) {}
  }

  async function pullRemote() {
    if (!remoteBase || document.visibilityState === "hidden") return false;
    try {
      const response = await fetch(`${remoteBase}${SYNC_PATH}`, {cache: "no-store"});
      consecutiveFailures = 0;
      if (!response.ok) return false;
      const body = await response.json();
      const remote = body?.appearance ? normalize(body.appearance) : null;
      if (remote && remote.updatedAt > current.updatedAt) {
        adopt(remote);
      } else if (!remote && current.updatedAt) {
        await pushRemote();
      } else if (remote && current.updatedAt > remote.updatedAt) {
        await pushRemote();
      }
      return true;
    } catch (error) {
      // The engine being unreachable is not an error to shout about; it is the
      // state every user is in before they install it.
      if (++consecutiveFailures >= QUIET_AFTER_FAILURES) {
        stopPolling(`the engine did not answer ${consecutiveFailures} times`);
      }
      return false;
    }
  }

  async function connect(baseUrl = "") {
    const clean = String(baseUrl || "").replace(/\/+$/, "");
    if (!clean) return false;
    remoteBase = clean;
    // Every call to connect is a fresh start: the user may have just launched
    // the engine, so a poller that gave up must come back.
    consecutiveFailures = 0;
    const connected = await pullRemote();
    window.clearInterval(pollTimer);
    pollTimer = window.setInterval(pullRemote, 2000);
    return connected;
  }

  function bindControls() {
    document.querySelectorAll("[data-appearance-palettes]").forEach(renderPaletteBrowser);
    document.querySelectorAll("[data-appearance-scheme-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        const choice = button.dataset.appearanceSchemeMode;
        if (choice === "device") set({mode: "device"});
        else set({mode: "manual", scheme: choice});
      });
    });
    bindPaletteActions();
    syncControls();
  }

  function subscribe(listener) {
    listeners.add(listener);
    return function unsubscribe() { listeners.delete(listener); };
  }

  apply(current);
  window.ScrapeXAppearance = Object.freeze({
    get: () => ({...current, effectiveScheme: effectiveScheme()}),
    set,
    connect,
    refresh: pullRemote,
    subscribe,
    palettes: [...PALETTES.values()].map(({id, label, description, colors}) => ({
      id, label, description, colors: [...colors],
    })),
    // Exposed so a caller can resolve a legacy id without duplicating the map,
    // and so the cross-surface allowlist test can read the registry rather than
    // a hand-copied list of names.
    aliases: Object.fromEntries(PALETTE_ALIASES),
    resolvePalette,
  });

  schemeQuery.addEventListener("change", () => {
    if (current.mode !== "device") return;
    apply(current);
    syncControls();
    notify();
  });
  window.addEventListener("storage", (event) => {
    if (![STORAGE_KEY, LEGACY_STORAGE_KEY].includes(event.key)) return;
    const saved = read();
    if (saved.updatedAt < current.updatedAt) return;
    adopt(saved);
  });
  // Focus is the user coming back, and quite possibly having just started the
  // engine. It resets the failure count and REVIVES the poller — calling
  // pullRemote alone would check once and leave a stopped interval stopped.
  window.addEventListener("focus", () => {
    consecutiveFailures = 0;
    if (remoteBase && pollTimer === undefined) {
      pollTimer = window.setInterval(pullRemote, 2000);
    }
    pullRemote();
  });
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
