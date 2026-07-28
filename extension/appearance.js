(function () {
  "use strict";

  const STORAGE_KEY = "scrapex-appearance-v2";
  const LEGACY_STORAGE_KEY = "scrapex-appearance-v1";
  const SYNC_PATH = "/api/appearance";
  const SCHEMES = new Set(["light", "dark"]);
  const PALETTES = new Map([
    ["whatsapp", {
      id: "whatsapp",
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
    ["github", {
      id: "github",
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
  ]);
  const DEFAULTS = Object.freeze({
    mode: "device",
    scheme: "light",
    palette: "github",
    deviceColors: true,
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
  const schemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let remoteBase = "";
  let pollTimer = null;
  let pushTimer = null;
  let current = read();

  function normalize(value) {
    const candidate = value && typeof value === "object" ? value : {};
    return {
      mode: candidate.mode === "manual" ? "manual" : "device",
      scheme: SCHEMES.has(candidate.scheme) ? candidate.scheme : DEFAULTS.scheme,
      palette: PALETTES.has(candidate.palette) ? candidate.palette : DEFAULTS.palette,
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

  function themeFor(palette, scheme) {
    const explicit = palette.themes[scheme];
    return Object.fromEntries(Object.entries(explicit).map(([key, value]) => [
      key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`),
      value,
    ]));
  }

  function clearTheme(root) {
    THEME_PROPERTIES.forEach((property) => root.style.removeProperty(`--${property}`));
  }

  function apply(value) {
    const root = document.documentElement;
    root.dataset.appearance = value.mode;
    root.dataset.colorMode = value.deviceColors ? "device" : "manual";
    if (value.mode === "manual") root.dataset.theme = value.scheme;
    else root.removeAttribute("data-theme");

    if (value.deviceColors) {
      root.removeAttribute("data-palette");
      clearTheme(root);
      return;
    }

    root.dataset.palette = value.palette;
    const palette = PALETTES.get(value.palette) || PALETTES.get(DEFAULTS.palette);
    const theme = themeFor(palette, effectiveScheme(value));
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
      : PALETTES.get(value.palette).label;
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

  async function pullRemote() {
    if (!remoteBase || document.visibilityState === "hidden") return false;
    try {
      const response = await fetch(`${remoteBase}${SYNC_PATH}`, {cache: "no-store"});
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
      return false;
    }
  }

  async function connect(baseUrl = "") {
    const clean = String(baseUrl || "").replace(/\/+$/, "");
    if (!clean) return false;
    remoteBase = clean;
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
