(function () {
  "use strict";

  const STORAGE_KEY = "scrapex-appearance-v1";
  const SCHEMES = new Set(["light", "dark"]);
  const GROUPS = Object.freeze([
    {
      id: "popular",
      label: "Popular",
      source: "Color Hunt",
      palettes: [
        {id: "popular-blush", label: "Blush", likes: 2643,
          colors: ["#FBEFEF", "#FFE2E2", "#F5CBCB", "#C5B3D3"]},
        {id: "popular-garden", label: "Garden", likes: 1288,
          colors: ["#FFEED6", "#A5AF79", "#827148", "#E8A07C"]},
        {id: "popular-coast", label: "Coast", likes: 1100,
          colors: ["#F9E8A2", "#B4E1EB", "#95BDD7", "#78A4CB"]},
      ],
    },
    {
      id: "light",
      label: "Light",
      source: "Color Hunt",
      palettes: [
        {id: "light-rose", label: "Rose mist", likes: 9721,
          colors: ["#FCF8F8", "#FBEFEF", "#F9DFDF", "#F5AFAF"]},
        {id: "light-candy", label: "Candy sky", likes: 7071,
          colors: ["#A8DF8E", "#F0FFDF", "#FFD8DF", "#FFAAB8"]},
        {id: "light-sage", label: "Soft sage", likes: 6669,
          colors: ["#F6F0D7", "#C5D89D", "#9CAB84", "#89986D"]},
      ],
    },
    {
      id: "dark",
      label: "Dark",
      source: "Color Hunt",
      palettes: [
        {id: "dark-harbour", label: "Harbour", likes: 11983,
          colors: ["#222831", "#393E46", "#948979", "#DFD0B8"]},
        {id: "dark-forest", label: "Night forest", likes: 11133,
          colors: ["#181C14", "#3C3D37", "#697565", "#ECDFCC"]},
        {id: "dark-plum", label: "Deep plum", likes: 10983,
          colors: ["#1A1A1D", "#3B1C32", "#6A1E55", "#A64D79"]},
      ],
    },
    {
      id: "warm",
      label: "Warm",
      source: "Color Hunt",
      palettes: [
        {id: "warm-coral", label: "Coral", likes: 7575,
          colors: ["#FEEAC9", "#FFCDC9", "#FDACAC", "#FD7979"]},
        {id: "warm-coffee", label: "Coffee", likes: 4671,
          colors: ["#FFF8F0", "#C08552", "#8C5A3C", "#4B2E2B"]},
        {id: "warm-peach", label: "Peach", likes: 4468,
          colors: ["#FFF7CD", "#FDC3A1", "#FB9B8F", "#F57799"]},
      ],
    },
    {
      id: "earth",
      label: "Earth",
      source: "Color Hunt",
      palettes: [
        {id: "earth-clay", label: "Clay", likes: 11788,
          colors: ["#FFCDB2", "#FFB4A2", "#E5989B", "#B5828C"]},
        {id: "earth-linen", label: "Linen", likes: 10061,
          colors: ["#F9F8F6", "#EFE9E3", "#D9CFC7", "#C9B59C"]},
        {id: "earth-moss", label: "Moss", likes: 9852,
          colors: ["#2C3930", "#3F4F44", "#A27B5C", "#DCD7C9"]},
      ],
    },
    {
      id: "cold",
      label: "Cold",
      source: "Color Hunt",
      palettes: [
        {id: "cold-ocean", label: "Ocean", likes: 7837,
          colors: ["#0F2854", "#1C4D8D", "#4988C4", "#BDE8F5"]},
        {id: "cold-ink", label: "Ink", likes: 6863,
          colors: ["#EFECE3", "#8FABD4", "#4A70A9", "#000000"]},
        {id: "cold-lagoon", label: "Lagoon", likes: 6311,
          colors: ["#1B3C53", "#234C6A", "#456882", "#D2C1B6"]},
      ],
    },
    {
      id: "coolors",
      label: "Coolors",
      source: "Coolors Trending",
      palettes: [
        {id: "coolors-sunset", label: "Sunset",
          colors: ["#264653", "#2A9D8F", "#E9C46A", "#E76F51"]},
        {id: "coolors-sand", label: "Sand",
          colors: ["#CCD5AE", "#E9EDC9", "#FEFAE0", "#D4A373"]},
        {id: "coolors-wave", label: "Wave",
          colors: ["#03045E", "#0077B6", "#00B4D8", "#CAF0F8"]},
      ],
    },
    {
      id: "apps",
      label: "Apps",
      source: "Application themes",
      palettes: [
        {
          id: "whatsapp",
          label: "WhatsApp",
          colors: ["#0B141A", "#005C4B", "#00A884", "#D9FDD3"],
          themes: {
            light: {
              bg: "#F0F2F5", surface: "#FFFFFF", surfaceSubtle: "#F7F8FA",
              surfaceRaised: "#FFFFFF", line: "#E9EDEF", lineStrong: "#D1D7DB",
              text: "#111B21", muted: "#54656F", textSubtle: "#667781",
              chip: "#E9EDEF", accent: "#008069", accentHover: "#017561",
              accentActive: "#006B5B", accentInk: "#00695C",
              accentContrast: "#FFFFFF", accentWeak: "#D9FDD3",
              focus: "#00A884", controlHover: "#F5F6F6",
            },
            dark: {
              bg: "#0B141A", surface: "#111B21", surfaceSubtle: "#182229",
              surfaceRaised: "#202C33", line: "#2A3942", lineStrong: "#3B4A54",
              text: "#E9EDEF", muted: "#8696A0", textSubtle: "#667781",
              chip: "#202C33", accent: "#00A884", accentHover: "#06CF9C",
              accentActive: "#008069", accentInk: "#06CF9C",
              accentContrast: "#0B141A", accentWeak: "#005C4B",
              focus: "#00A884", controlHover: "#2A3942",
            },
          },
        },
        {
          id: "github",
          label: "GitHub",
          colors: ["#0D1117", "#0969DA", "#4493F8", "#F0F6FC"],
          themes: {
            light: {
              bg: "#FFFFFF", surface: "#FFFFFF", surfaceSubtle: "#F6F8FA",
              surfaceRaised: "#FFFFFF", line: "#D1D9E0", lineStrong: "#818B98",
              text: "#1F2328", muted: "#59636E", textSubtle: "#818B98",
              chip: "#EFF2F5", accent: "#0969DA", accentHover: "#0860CA",
              accentActive: "#0757BA", accentInk: "#0969DA",
              accentContrast: "#FFFFFF", accentWeak: "#DDF4FF",
              focus: "#0969DA", controlHover: "#EFF2F5",
            },
            dark: {
              bg: "#0D1117", surface: "#151B23", surfaceSubtle: "#212830",
              surfaceRaised: "#262C36", line: "#3D444D", lineStrong: "#59636E",
              text: "#F0F6FC", muted: "#9198A1", textSubtle: "#7D8590",
              chip: "#212830", accent: "#4493F8", accentHover: "#58A6FF",
              accentActive: "#1F6FEB", accentInk: "#58A6FF",
              accentContrast: "#0D1117", accentWeak: "#1B3A5D",
              focus: "#4493F8", controlHover: "#262C36",
            },
          },
        },
      ],
    },
    {
      id: "custom",
      label: "Custom",
      source: "Your colour",
      palettes: [{id: "custom", label: "Custom", colors: ["#172554", "#4F7FC9", "#9DBAF0", "#EEF4FF"]}],
    },
  ]);

  const PALETTES = new Map(GROUPS.flatMap((group) =>
    group.palettes.map((palette) => [palette.id, {...palette, group: group.id}])));
  const DEFAULTS = Object.freeze({
    mode: "device",
    scheme: "light",
    palette: "popular-coast",
    deviceColors: true,
    customAccent: "#4F7FC9",
  });
  const THEME_PROPERTIES = Object.freeze([
    "bg", "surface", "surface-subtle", "surface-raised", "line", "line-strong",
    "text", "muted", "text-subtle", "chip", "accent", "accent-hover",
    "accent-active", "accent-ink", "accent-contrast", "accent-weak", "focus",
    "control-hover",
  ]);
  const LEGACY_PALETTES = Object.freeze({
    cyan: "popular-coast", blue: "cold-ocean", slate: "dark-harbour",
    indigo: "dark-plum", teal: "coolors-wave", green: "earth-moss",
    forest: "dark-forest", olive: "light-sage", gold: "warm-coffee",
    orange: "warm-peach", brown: "earth-linen", rose: "light-rose",
    burgundy: "earth-clay", plum: "dark-plum", violet: "popular-blush",
    custom: "custom",
  });
  const schemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let current = read();

  function normalize(value) {
    const candidate = value && typeof value === "object" ? value : {};
    const legacyPalette = LEGACY_PALETTES[candidate.accent];
    const palette = PALETTES.has(candidate.palette)
      ? candidate.palette
      : (legacyPalette || DEFAULTS.palette);
    const deviceColors = typeof candidate.deviceColors === "boolean"
      ? candidate.deviceColors
      : (typeof candidate.followColors === "boolean"
        ? candidate.followColors
        : candidate.mode !== "manual");
    return {
      mode: candidate.mode === "manual" ? "manual" : "device",
      scheme: SCHEMES.has(candidate.scheme) ? candidate.scheme : DEFAULTS.scheme,
      palette,
      deviceColors,
      customAccent: /^#[0-9a-f]{6}$/i.test(candidate.customAccent || "")
        ? candidate.customAccent.toUpperCase()
        : DEFAULTS.customAccent,
    };
  }

  function read() {
    try {
      return normalize(JSON.parse(window.localStorage.getItem(STORAGE_KEY)));
    } catch (error) {
      return {...DEFAULTS};
    }
  }

  function remember(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    } catch (error) {
      // Appearance is optional; blocked storage must never block the interface.
    }
  }

  function effectiveScheme(value = current) {
    return value.mode === "manual"
      ? value.scheme
      : (schemeQuery.matches ? "dark" : "light");
  }

  function rgb(hex) {
    const value = hex.replace("#", "");
    return [
      parseInt(value.slice(0, 2), 16),
      parseInt(value.slice(2, 4), 16),
      parseInt(value.slice(4, 6), 16),
    ];
  }

  function hex(values) {
    return `#${values.map((value) =>
      Math.round(Math.max(0, Math.min(255, value))).toString(16)
        .padStart(2, "0")).join("")}`.toUpperCase();
  }

  function mix(first, second, amount = .5) {
    const a = rgb(first);
    const b = rgb(second);
    return hex(a.map((value, index) => value * amount + b[index] * (1 - amount)));
  }

  function luminance(color) {
    const channels = rgb(color).map((value) => {
      const channel = value / 255;
      return channel <= .03928
        ? channel / 12.92
        : Math.pow((channel + .055) / 1.055, 2.4);
    });
    return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
  }

  function contrast(first, second) {
    const high = Math.max(luminance(first), luminance(second));
    const low = Math.min(luminance(first), luminance(second));
    return (high + .05) / (low + .05);
  }

  function readable(foreground, background, target = 4.5) {
    if (contrast(foreground, background) >= target) return foreground;
    const towards = luminance(background) > .45 ? "#000000" : "#FFFFFF";
    let result = foreground;
    for (let step = 1; step <= 20; step += 1) {
      result = mix(foreground, towards, 1 - step / 20);
      if (contrast(result, background) >= target) return result;
    }
    return towards;
  }

  function genericTheme(palette, scheme) {
    let colors = [...palette.colors];
    if (palette.id === "custom") {
      const selected = current.customAccent;
      colors = [
        mix(selected, "#000000", .55),
        selected,
        mix(selected, "#FFFFFF", .55),
        mix(selected, "#FFFFFF", .12),
      ];
    }
    colors.sort((first, second) => luminance(first) - luminance(second));
    const [dark, middleDark, middleLight, light] = colors;

    if (scheme === "dark") {
      const surface = mix(dark, "#171B21", .30);
      const accent = readable(middleLight, surface);
      return {
        bg: mix(dark, "#0F1216", .38),
        surface,
        surfaceSubtle: mix(middleDark, "#1C2128", .24),
        surfaceRaised: mix(middleDark, "#20262E", .20),
        line: mix(middleLight, "#2C333D", .22),
        lineStrong: mix(middleLight, "#434D5A", .35),
        text: readable(mix(light, "#E9EDF2", .16), surface, 7),
        muted: readable(mix(middleLight, "#A9B2BF", .20), surface, 4.5),
        textSubtle: readable(mix(middleDark, "#8994A3", .20), surface, 3.2),
        chip: mix(middleDark, "#242B34", .25),
        accent,
        accentHover: mix(accent, "#FFFFFF", .82),
        accentActive: mix(accent, "#000000", .82),
        accentInk: readable(accent, surface),
        accentContrast: readable("#0F1216", accent),
        accentWeak: mix(accent, surface, .16),
        focus: accent,
        controlHover: mix(middleDark, "#20262E", .22),
      };
    }

    const surface = mix(light, "#FFFFFF", .08);
    const accent = readable(dark, surface);
    return {
      bg: mix(light, "#FFFFFF", .18),
      surface,
      surfaceSubtle: mix(light, "#F9FAFB", .34),
      surfaceRaised: mix(light, "#FFFFFF", .10),
      line: mix(middleLight, "#DFE3E8", .30),
      lineStrong: mix(middleDark, "#C5CBD3", .35),
      text: readable(mix(dark, "#171A1F", .22), surface, 7),
      muted: readable(mix(middleDark, "#626C7A", .25), surface, 4.5),
      textSubtle: readable(mix(middleLight, "#7C8795", .18), surface, 3.2),
      chip: mix(light, "#EDF1F4", .35),
      accent,
      accentHover: mix(accent, "#000000", .88),
      accentActive: mix(accent, "#000000", .76),
      accentInk: readable(accent, surface),
      accentContrast: readable("#FFFFFF", accent),
      accentWeak: mix(accent, surface, .15),
      focus: accent,
      controlHover: mix(middleLight, "#F9FAFB", .10),
    };
  }

  function themeFor(palette, scheme) {
    const explicit = palette.themes?.[scheme];
    if (explicit) {
      return Object.fromEntries(Object.entries(explicit).map(([key, value]) => [
        key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`),
        value,
      ]));
    }
    return genericTheme(palette, scheme);
  }

  function clearTheme(root) {
    THEME_PROPERTIES.forEach((property) => root.style.removeProperty(`--${property}`));
  }

  function apply(value) {
    const root = document.documentElement;
    root.dataset.appearance = value.mode;
    root.dataset.colorMode = value.deviceColors ? "device" : "manual";
    root.style.setProperty("--custom-accent", value.customAccent);
    if (value.mode === "manual") {
      root.dataset.theme = value.scheme;
    } else {
      root.removeAttribute("data-theme");
    }
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

  function paletteLabel(id) {
    return PALETTES.get(id)?.label || id;
  }

  function statusText(value = current) {
    const scheme = value.mode === "device"
      ? `Device ${effectiveScheme(value)}`
      : value.scheme;
    const color = value.deviceColors ? "Device colors" : paletteLabel(value.palette);
    return `${scheme} \u00B7 ${color}`;
  }

  function paletteButton(palette) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "appearance-palette-tile";
    button.dataset.appearancePalette = palette.id;
    button.setAttribute("aria-pressed", "false");
    const rating = palette.likes ? `, ${palette.likes.toLocaleString()} likes` : "";
    button.setAttribute("aria-label", `${palette.label}${rating}`);
    button.title = `${palette.label}${rating}`;

    const strip = document.createElement("span");
    strip.className = "appearance-palette-strip";
    palette.colors.forEach((color) => {
      const swatch = document.createElement("i");
      swatch.style.setProperty("--palette-swatch", color);
      strip.appendChild(swatch);
    });
    const label = document.createElement("small");
    label.textContent = palette.label;
    button.append(strip, label);
    return button;
  }

  function customTile() {
    const label = document.createElement("label");
    label.className = "appearance-palette-tile appearance-custom-tile";
    label.title = "Choose a custom colour";
    const input = document.createElement("input");
    input.type = "color";
    input.dataset.appearanceCustomColor = "";
    input.value = current.customAccent;
    input.setAttribute("aria-label", "Choose a custom colour");
    const strip = document.createElement("span");
    strip.className = "appearance-palette-strip appearance-custom-strip";
    const swatch = document.createElement("i");
    strip.appendChild(swatch);
    const copy = document.createElement("small");
    copy.textContent = "Custom";
    label.append(input, strip, copy);
    return label;
  }

  function renderPaletteBrowser(container, index) {
    if (container.dataset.appearanceRendered === "true") return;
    container.dataset.appearanceRendered = "true";
    container.classList.add("appearance-palette-browser");
    const tabs = document.createElement("div");
    tabs.className = "appearance-palette-groups";
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Palette collections");
    const panel = document.createElement("div");
    panel.className = "appearance-palette-options";
    panel.setAttribute("role", "tabpanel");
    panel.id = `appearance-palette-panel-${index}`;

    let activeGroup = PALETTES.get(current.palette)?.group || GROUPS[0].id;
    const show = (groupId) => {
      const group = GROUPS.find((candidate) => candidate.id === groupId) || GROUPS[0];
      activeGroup = group.id;
      tabs.querySelectorAll("button").forEach((button) => {
        const active = button.dataset.appearanceGroup === activeGroup;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
      });
      panel.replaceChildren(...group.palettes.map(paletteButton));
      if (group.id === "custom") panel.replaceChildren(customTile());
      bindPaletteActions(panel);
      syncControls();
    };

    GROUPS.forEach((group) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.appearanceGroup = group.id;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", panel.id);
      button.textContent = group.label;
      button.addEventListener("click", () => show(group.id));
      tabs.appendChild(button);
    });
    container.append(tabs, panel);
    show(activeGroup);
  }

  function bindPaletteActions(scope = document) {
    scope.querySelectorAll("[data-appearance-palette]").forEach((button) => {
      if (button.dataset.appearanceBound === "true") return;
      button.dataset.appearanceBound = "true";
      button.addEventListener("click", () =>
        set({deviceColors: false, palette: button.dataset.appearancePalette}));
    });
    scope.querySelectorAll("[data-appearance-custom-color]").forEach((input) => {
      if (input.dataset.appearanceBound === "true") return;
      input.dataset.appearanceBound = "true";
      input.addEventListener("input", () =>
        set({deviceColors: false, palette: "custom", customAccent: input.value}));
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
        const active = button.dataset.appearancePalette === current.palette;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
        button.disabled = current.deviceColors;
      });
      control.querySelectorAll("[data-appearance-device-colors]").forEach((input) => {
        input.checked = current.deviceColors;
      });
      control.querySelectorAll("[data-appearance-custom-color]").forEach((input) => {
        input.value = current.customAccent;
        input.disabled = current.deviceColors;
        input.closest(".appearance-custom-tile")
          ?.classList.toggle("is-active", current.palette === "custom");
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

  function set(patch) {
    current = normalize({...current, ...patch});
    remember(current);
    apply(current);
    syncControls();
    notify();
    return {...current};
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
    subscribe,
    groups: GROUPS.map((group) => ({
      id: group.id,
      label: group.label,
      source: group.source,
      palettes: group.palettes.map(({id, label, colors, likes}) =>
        ({id, label, colors: [...colors], likes: likes || null})),
    })),
  });

  schemeQuery.addEventListener("change", () => {
    if (current.mode !== "device") return;
    apply(current);
    syncControls();
    notify();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== STORAGE_KEY) return;
    current = read();
    apply(current);
    syncControls();
    notify();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindControls, {once: true});
  } else {
    bindControls();
  }
})();
