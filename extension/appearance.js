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
  const PALETTES = new Map([
    ["brand", {
      id: "brand",
      label: "WhatsApp",
      description: "WhatsApp application green",
      colors: ["#121B21", "#35AA65", "#43D36D", "#F7F5F3"],
      themes: {
        light: {
          bg: "#F7F5F3", surface: "#FFFFFF", surfaceSubtle: "#F7F5F3",
          surfaceRaised: "#FFFFFF", line: "#E5E5E5", lineStrong: "#959393",
          text: "#0A0A0A", muted: "#666666", textSubtle: "#707070",
          chip: "#F7F5F3", accent: "#35AA65", accentHover: "#2E9D5B",
          accentActive: "#278F52", accentInk: "#18864B",
          accentContrast: "#0A0A0A", accentWeak: "#DBFDD5",
          focus: "#278F52", controlHover: "#F0EEEC",
          buttonBg: "#43D36D", buttonHover: "#1C1E21",
          buttonActive: "#121B21", buttonText: "#0A0A0A",
          buttonHoverText: "#FFFFFF",
          amber: "#8A5A00", amberWeak: "#FFF2C2",
          red: "#B3002F", redHover: "#970028", redWeak: "#FCE5EA",
          dangerContrast: "#FFFFFF",
          switchTrack: "#35AA65", switchTrackHover: "#2E9D5B",
          switchTrackOff: "#FFFFFF", switchThumb: "#FFFFFF",
          switchThumbOff: "#959393",
          shadowColor: "rgb(11 20 26 / 0.12)",
          overlay: "rgb(11 20 26 / 0.42)",
        },
        dark: {
          bg: "#121B21", surface: "#182229", surfaceSubtle: "#20272B",
          surfaceRaised: "#202C33", line: "#2A3942", lineStrong: "#667781",
          text: "#FFFFFF", muted: "#AEBAC1", textSubtle: "#8696A0",
          chip: "#202C33", accent: "#43D36D", accentHover: "#52DC79",
          accentActive: "#35AA65", accentInk: "#43D36D",
          accentContrast: "#0B141A", accentWeak: "#103B2A",
          focus: "#43D36D", controlHover: "#2A3942",
          buttonBg: "#43D36D", buttonHover: "#FFFFFF",
          buttonActive: "#F7F5F3", buttonText: "#0A0A0A",
          buttonHoverText: "#0A0A0A",
          amber: "#FFD279", amberWeak: "#3A2D13",
          red: "#FF7892", redHover: "#FF91A6", redWeak: "#3A1722",
          dangerContrast: "#121B21",
          switchTrack: "#35AA65", switchTrackHover: "#2E9D5B",
          switchTrackOff: "#182229", switchThumb: "#FFFFFF",
          switchThumbOff: "#959393",
          shadowColor: "rgb(0 0 0 / 0.42)",
          overlay: "rgb(0 0 0 / 0.68)",
        },
      },
    }],
    ["blue", {
      id: "blue",
      label: "GitHub",
      description: "Focused developer neutral",
      colors: ["#0D1117", "#0969DA", "#4493F8", "#F0F6FC"],
      themes: {
        light: {
          bg: "#FFFFFF", surface: "#FFFFFF", surfaceSubtle: "#F6F8FA",
          surfaceRaised: "#FFFFFF", line: "#D1D9E0", lineStrong: "#818B98",
          text: "#1F2328", muted: "#59636E", textSubtle: "#656D76",
          chip: "#EFF2F5", accent: "#0969DA", accentHover: "#0860CA",
          accentActive: "#0757BA", accentInk: "#0969DA",
          accentContrast: "#FFFFFF", accentWeak: "#DDF4FF",
          focus: "#0969DA", controlHover: "#EFF2F5",
          amber: "#9A6700", amberWeak: "#FFF8C5",
          red: "#CF222E", redHover: "#A40E26", redWeak: "#FFEBE9",
          dangerContrast: "#FFFFFF",
          switchTrack: "#0969DA", switchTrackHover: "#0860CA",
          switchTrackOff: "#FFFFFF", switchThumb: "#FFFFFF",
          switchThumbOff: "#818B98",
          shadowColor: "rgb(31 35 40 / 0.12)",
          overlay: "rgb(31 35 40 / 0.42)",
        },
        dark: {
          bg: "#0D1117", surface: "#151B23", surfaceSubtle: "#212830",
          surfaceRaised: "#262C36", line: "#3D444D", lineStrong: "#6E7781",
          text: "#F0F6FC", muted: "#9198A1", textSubtle: "#7D8590",
          chip: "#212830", accent: "#4493F8", accentHover: "#58A6FF",
          accentActive: "#1F6FEB", accentInk: "#58A6FF",
          accentContrast: "#0D1117", accentWeak: "#1B3A5D",
          focus: "#4493F8", controlHover: "#262C36",
          amber: "#D29922", amberWeak: "#3B2E0B",
          red: "#F85149", redHover: "#FF7B72", redWeak: "#3C1618",
          dangerContrast: "#0D1117",
          switchTrack: "#4493F8", switchTrackHover: "#1F6FEB",
          switchTrackOff: "#151B23", switchThumb: "#FFFFFF",
          switchThumbOff: "#818B98",
          shadowColor: "rgb(0 0 0 / 0.42)",
          overlay: "rgb(0 0 0 / 0.68)",
        },
      },
    }],
    // R-72 · SUPABASE IS THE BASELINE, SO THIS ENTRY DECLARES NO COLOURS.
    //
    // «design system هو supabase ولكن قد ضفنا له استثناء 3 palette الوان واتساب
    // وجت هب و device» -- the design system IS Supabase, and WhatsApp, GitHub and
    // device are three COLOUR exceptions on top of it. So Supabase is not one
    // option among three: it is what design/tokens.css declares, and every other
    // choice is an override of its colours only.
    //
    // WHICH MEANS THERE IS NOTHING TO PUT HERE. Its colours are the `:root` and
    // dark-block colours in tokens.css. Repeating them would be the same values
    // in two files with nothing keeping them equal -- and the entry above exists
    // precisely because `brand` DOES differ from the baseline.
    //
    // The entry is not empty of purpose. It makes Supabase SELECTABLE, so a user
    // who tried WhatsApp can come back; it gives the tile its label and swatches;
    // and it puts `supabase` in `data-palette`, so the DOM says which of the four
    // colour choices is in force. apply() removes all 36 colour properties for
    // it, and removal is exactly what "fall through to the baseline" means.
    //
    // R-71 built the opposite and it was wrong: a `design` block here gave the
    // design system to this palette and to NOBODY ELSE. Measured on the built
    // engine -- `brand`, `blue` and device colours all fell back to the
    // pre-Supabase 9px radius, 14px body and Segoe UI. Three of four.
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
  const PALETTE_ALIASES = new Map([
    ["whatsapp", "brand"],
    ["github", "blue"],
  ]);
  const DEFAULTS = Object.freeze({
    mode: "device",
    scheme: "light",
    // R-71: `supabase` is the default appearance, superseding R-59 decision 1's
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
    // "Device colours" REMAINS AVAILABLE and is one click away in the panel; this
    // changes which way the switch starts, not whether it exists.
    deviceColors: false,
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
  // R-72 · THERE IS NO SECOND AXIS, AND THAT IS THE RULING.
  //
  // The 36 properties above are colours, and under R-72 a palette may set
  // NOTHING ELSE: «whatsapp, github الوان theme يمكن اختيارها بواسطة المستخدم
  // فتعدل على الالوان فقط لا تعدل على design system».
  //
  // R-71 added a DESIGN_PROPERTIES list here so a palette could carry radius,
  // typography, elevation and motion. It is removed rather than left unused,
  // because «واى تعارض معاها يلغى» and a mechanism whose whole purpose is "a
  // palette may change the design system" is the conflict itself.
  //
  // The design system did not go anywhere -- it moved to where it belongs.
  // design/tokens.css IS the Supabase design system now, so all four colour
  // choices sit on it, including device, which applies no palette at all. That
  // is what R-71's axis could not do: measured on the built engine, it gave the
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
      deviceColors: typeof candidate.deviceColors === "boolean"
        ? candidate.deviceColors
        : (typeof candidate.followColors === "boolean"
          ? candidate.followColors
          : candidate.mode !== "manual"),
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

  function clearTheme(root) {
    THEME_PROPERTIES.forEach((property) => root.style.removeProperty(`--${property}`));
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
    root.dataset.colorMode = value.deviceColors ? "device" : "manual";
    if (value.mode === "manual") root.dataset.theme = value.scheme;
    else root.removeAttribute("data-theme");

    // Device colours: no palette, so every colour override is removed and the
    // page falls through to design/tokens.css. Under R-72 that is not a
    // degraded state -- tokens.css IS the Supabase design system, so shape,
    // typography, elevation and motion are exactly what they are under every
    // other choice, and only the colours come from the operating system.
    if (value.deviceColors) {
      root.removeAttribute("data-palette");
      clearTheme(root);
      return;
    }

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
    const color = value.deviceColors
      ? "Device colours"
      : paletteFor(value.palette).label;
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
        set({deviceColors: false, palette: button.dataset.appearancePalette}));
    });
  }

  function syncControls() {
    document.querySelectorAll("[data-appearance-control]").forEach((control) => {
      control.classList.toggle("is-device", current.mode === "device");
      control.classList.toggle("is-device-colors", current.deviceColors);
      control.querySelectorAll("[data-appearance-scheme-mode]").forEach((button) => {
        const choice = button.dataset.appearanceSchemeMode;
        const active = choice === "device"
          ? current.mode === "device"
          : current.mode === "manual" && current.scheme === choice;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      control.querySelectorAll("[data-appearance-palette]").forEach((button) => {
        const active = button.dataset.appearancePalette === current.palette
          && !current.deviceColors;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-checked", String(active));
      });
      control.querySelectorAll("[data-appearance-device-colors]").forEach((input) => {
        input.checked = current.deviceColors;
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
    document.querySelectorAll("[data-appearance-device-colors]").forEach((input) => {
      input.addEventListener("change", () => set({deviceColors: input.checked}));
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
