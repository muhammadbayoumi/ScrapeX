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
    // THE FIRST APPEARANCE THAT IS A DESIGN SYSTEM RATHER THAN A PALETTE, under
    // R-71. Everything above this entry sets colour and nothing else; the
    // `design` block below is the axis that entry added, and Supabase is the
    // reason it had to exist -- their system's identity is carried at least as
    // much by a 6px radius, a 450 text weight and the absence of shadow as by
    // the green.
    //
    // PUBLISHED vs DERIVED, because Supabase publishes far less than it looks.
    // Their docs site lists token NAMES with no values. The stepped ramps
    // (brand-200..600, warning-*, destructive-*) and the `scale` neutral ramp
    // are real HSL literals in packages/{ui,config}. Every SEMANTIC colour --
    // background, card, popover, muted, border, foreground, primary, warning,
    // destructive -- is computed at runtime in OKLCH from about ten scalar
    // inputs, so no hex exists to copy and each was derived by evaluating their
    // own expressions. A comment marks which is which, value by value, so a
    // later session can tell a quotation from a calculation.
    //
    // THREE VALUES DELIBERATELY DIVERGE, each because their own value fails a
    // guard this repository already enforces (measured, not assumed):
    //   * focus -- their ring is --primary at 55% alpha, which flattens to
    //     #98E3C0 and is 1.47:1 on their own background. The guard needs 3:1.
    //   * lineStrong -- their --border-stronger is 1.57:1 (light) and 1.53:1
    //     (dark) against their own card. The guard needs 3:1.
    //   * amber -- their --warning is oklch(0.68 0.14 75) and 2.68:1 on their
    //     own published warning-300 tint. The guard needs 4.5:1, so the hue and
    //     chroma are held and only the lightness moves, to 0.52.
    // Their brand green is 1.99:1 on white, which is why accentContrast is
    // near-black in BOTH schemes rather than white in one of them.
    ["supabase", {
      id: "supabase",
      label: "Supabase",
      description: "Supabase console green, flat and bordered",
      colors: ["#131413", "#3ECF8E", "#85E0BA", "#FDFDFD"],
      // Scheme-independent: shape, type and motion do not change with the
      // scheme. Elevation does, and lives in the themes below.
      design: {
        // Their effective ramp is 2/4/6/8/12/16. `rounded-md` = 6px is the
        // universal control radius (431 files) and 8px the container ceiling;
        // 16px appears in 19. NOT the 10px from apps/ui-library -- that is a
        // separate shadcn registry product with a grey focus ring.
        radiusXs: "0.125rem", radiusSm: "0.25rem", radius: "0.375rem",
        radiusLg: "0.5rem", radiusXl: "0.75rem", radiusSheet: "1rem",
        // Supabase migrated OFF the proprietary Circular: the live stack across
        // studio, www and design-system is Inter + Manrope + Source Code Pro,
        // all OSS. The `Circular, custom-font` stack still in packages/config is
        // a dead self-referential var() fallback, which is where third-party
        // token extractors still get the Circular claim from.
        //
        // NOTHING IS FETCHED. The faces are named first and the existing system
        // stack is kept behind them, so a machine that has Inter uses it and one
        // that does not is unchanged. "Noto Sans Arabic" STAYS in every stack --
        // this product is read and written in Arabic and neither Inter nor
        // Manrope covers it.
        font: "Inter, \"Segoe UI\", system-ui, -apple-system, "
          + "BlinkMacSystemFont, \"Noto Sans Arabic\", sans-serif",
        fontHeading: "Manrope, Inter, \"Segoe UI\", system-ui, "
          + "\"Noto Sans Arabic\", sans-serif",
        fontMono: "\"Source Code Pro\", ui-monospace, \"Cascadia Code\", "
          + "Consolas, monospace",
        // Their scale is shifted about 2px down from stock Tailwind, under their
        // own comment "font sizing and weights optimized for Inter". Measured
        // against this repository's ramp, SEVEN of the eight steps already
        // agree -- 12/13/16/18/22/28 are identical. The one real move is the
        // body size: their text-base is 15px where --fs is 14px. Saying so
        // beats restating six unchanged numbers as if they were a change.
        fs: "0.9375rem",
        // --font-weight-normal is 450, not 400, and there is no bold anywhere in
        // their system: `strong` is downgraded to 500 and the ceiling is Manrope
        // 600 on headings. So --fw-heavy drops from 700 to 600 -- deliberately
        // removing a weight rather than adding one.
        fwRegular: "450", fwHeavy: "600",
        // Exactly two curves, and they are used by meaning rather than by size:
        // one for things that appear, one for things that travel.
        durFast: "0.1s", dur: "0.15s", durSlow: "0.25s",
        ease: "cubic-bezier(0.16, 1, 0.3, 1)",
        easeTravel: "cubic-bezier(0.87, 0, 0.13, 1)",
        focusRingWidth: "2px", focusRingOffset: "2px",
        // NOT overridden, and each for a stated reason rather than by omission:
        //   * spacing -- their scale is Tailwind's 4px base, which is already
        //     this repository's --sp-* ramp value for value. Nothing to change.
        //   * control heights and --touch-target -- their medium control is
        //     ~38px against this repository's 40px, and the panel holds a 48px
        //     floor that a design-system swap must not quietly lower.
        //   * --radius-pill -- 999px is pill geometry, not a design choice.
      },
      themes: {
        light: {
          bg: "#FDFDFD",                  // --background          derived
          surface: "#FFFFFF",             // --card                derived
          surfaceSubtle: "#F6F6F6",       // --muted               derived
          surfaceRaised: "#FFFFFF",       // --popover             derived
          line: "#E9E9E9",                // --border              derived
          lineStrong: "#8F8F8F",          // diverges; see header
          text: "#030303",                // --foreground          derived
          muted: "#464646",               // --muted-foreground    derived
          textSubtle: "#696969",          // --tertiary-foreground derived
          chip: "#F3F3F3",                // --accent              derived
          accent: "#3FCF8E",              // brand-default light   PUBLISHED
          accentHover: "#65D8A4",         // brand/80 flat         derived
          accentActive: "#8EE8BD",        // brand-400/80 flat     derived
          accentInk: "#097C4F",           // brand-600 light       PUBLISHED
          accentContrast: "#030303",      // --primary-foreground  derived
          accentWeak: "#D3F8E4",          // brand-200 light       PUBLISHED
          focus: "#097C4F",               // diverges; see header
          controlHover: "#F3F3F3",
          amber: "#965900",               // diverges; see header
          amberWeak: "#FFF4D5",           // warning-300 light     PUBLISHED
          red: "#AB413E",                 // --destructive light   derived
          redHover: "#8E332F",            // the same hue, pressed derived
          redWeak: "#FFF0EE",             // destructive-300 light PUBLISHED
          dangerContrast: "#FFF9F8",      // --destructive-fg      derived
          switchTrack: "#16B674",         // brand-500 light       PUBLISHED
          switchTrackHover: "#097C4F",    // brand-600 light       PUBLISHED
          switchTrackOff: "#FFFFFF",
          // A WHITE thumb cannot sit on this green -- #FFFFFF on brand-500 is
          // 2.63:1 and the guard needs 2.9. Near-black is the same call
          // accentContrast already makes, for the same reason.
          switchThumb: "#030303",
          switchThumbOff: "#8F8F8F",
          // Their scrim is published exactly: dialog.tsx is `bg-black/40`, the
          // same in both schemes. Shadow is NOT published -- they define zero
          // shadow tokens and lean on an opaque plate plus a 1px border.
          shadowColor: "rgb(3 3 3 / 0.06)",
          overlay: "rgb(0 0 0 / 0.40)",
          design: {
            // Their Dialog is `border shadow-md dark:shadow-xs` -- the border is
            // unconditional and the shadow is the part that gets dropped. Even
            // their box-shadow utilities draw a 1px line at zero blur. So these
            // are flatter than this repository's defaults by design, not by
            // accident, and --shadow-lg finally derives from --shadow-color
            // instead of the literal it carried.
            shadowXs: "0 1px 2px var(--shadow-color)",
            shadowSm: "0 1px 3px var(--shadow-color)",
            shadowLg: "0 8px 24px var(--shadow-color)",
          },
        },
        dark: {
          bg: "#131413",                  // --background          derived
          surface: "#181A19",             // --card                derived
          surfaceSubtle: "#1A1B1A",       // --muted               derived
          surfaceRaised: "#1B1D1C",       // --popover             derived
          line: "#232423",                // --border              derived
          lineStrong: "#707070",          // scale-900 dark        PUBLISHED
          text: "#EDEFEE",                // --foreground          derived
          muted: "#BCBDBC",               // --muted-foreground    derived
          textSubtle: "#989A99",          // --tertiary-foreground derived
          chip: "#1E1F1E",                // --accent              derived
          accent: "#3ECF8E",              // brand-default dark    PUBLISHED
          accentHover: "#85E0BA",         // brand-600 dark        PUBLISHED
          accentActive: "#16B674",        // brand-500 light reused derived
          accentInk: "#3ECF8E",           // brand-default dark    PUBLISHED
          accentContrast: "#131413",      // --primary-foreground  derived
          accentWeak: "#002918",          // brand-300 dark        PUBLISHED
          focus: "#3ECF8E",               // brand-default dark    PUBLISHED
          controlHover: "#1E1F1E",
          amber: "#F2AF48",               // --warning dark        derived
          amberWeak: "#341C00",           // warning-300 dark      PUBLISHED
          red: "#FA8880",                 // --destructive dark    derived
          redHover: "#FDA49D",            // the same hue, lighter derived
          redWeak: "#3B1813",             // destructive-300 dark  PUBLISHED
          dangerContrast: "#090504",      // --destructive-fg      derived
          switchTrack: "#3ECF8E",         // brand-default dark    PUBLISHED
          switchTrackHover: "#85E0BA",    // brand-600 dark        PUBLISHED
          switchTrackOff: "#181A19",
          switchThumb: "#131413",
          switchThumbOff: "#707070",
          shadowColor: "rgb(0 0 0 / 0.40)",
          overlay: "rgb(0 0 0 / 0.40)",
          design: {
            // Dropped three steps from light, which is what their Dialog does.
            shadowXs: "0 1px 1px var(--shadow-color)",
            shadowSm: "0 1px 2px var(--shadow-color)",
            shadowLg: "0 4px 16px var(--shadow-color)",
          },
        },
      },
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
  // THE SECOND AXIS, added by R-71, and the reason it exists is a count: every
  // one of the 36 THEME_PROPERTIES above is a colour. Shape 0, typography 0,
  // spacing 0, elevation 0, motion 0. So an appearance could not carry a design
  // system, only a palette -- and "not colours only" was the request.
  //
  // These are the non-colour custom properties an appearance may override. They
  // are a SUBSET of design/tokens.css on purpose: of the 71 properties the
  // registry could not previously reach, three must stay unreachable by a
  // recorded decision (the Sign-in-with-Google values, fixed by Google's
  // branding rules and guarded by their own test), --radius-pill is geometry
  // rather than style, and --sp-* and the control heights are left to
  // tokens.css so an appearance cannot quietly lower the panel's 48px touch
  // floor.
  //
  // A palette declares these in one of two places, and the split is meaningful:
  // `palette.design` for what does not change with the scheme (shape, type,
  // motion) and `palette.themes[scheme].design` for what does (elevation --
  // Supabase drops its shadow in dark and keeps its border).
  const DESIGN_PROPERTIES = Object.freeze([
    "radius-xs", "radius-sm", "radius", "radius-lg", "radius-xl",
    "radius-sheet",
    "font", "font-heading", "font-mono",
    "fs-2xs", "fs-xs", "fs-sm", "fs", "fs-md", "fs-lg", "fs-xl", "fs-2xl",
    "fw-regular", "fw-medium", "fw-bold", "fw-heavy",
    "lh-tight", "lh", "lh-relaxed",
    "shadow-xs", "shadow-sm", "shadow-lg",
    "dur-fast", "dur", "dur-slow", "ease", "ease-travel",
    "focus-ring-width", "focus-ring-offset",
  ]);
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
    // `design` is the scheme's non-colour block and is read by designFor, not
    // here. Without this filter it would be dashed into a `--design` property
    // whose value is "[object Object]".
    return dashed(Object.entries(palette.themes[scheme])
      .filter(([key]) => key !== "design"));
  }

  // Scheme-independent first, then the scheme's own overrides on top. A palette
  // that declares neither returns {} and every DESIGN_PROPERTY is removed rather
  // than set, which is how the two colour-only palettes keep tokens.css's shape
  // and type untouched.
  function designFor(palette, scheme) {
    return dashed([
      ...Object.entries(palette.design || {}),
      ...Object.entries(palette.themes[scheme].design || {}),
    ]);
  }

  function clearTheme(root) {
    THEME_PROPERTIES.forEach((property) => root.style.removeProperty(`--${property}`));
    DESIGN_PROPERTIES.forEach((property) => root.style.removeProperty(`--${property}`));
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

    if (value.deviceColors) {
      root.removeAttribute("data-palette");
      clearTheme(root);
      return;
    }

    root.dataset.palette = value.palette;
    const palette = paletteFor(value.palette);
    const scheme = effectiveScheme(value);
    const theme = themeFor(palette, scheme);
    const design = designFor(palette, scheme);
    THEME_PROPERTIES.forEach((property) => {
      if (theme[property]) root.style.setProperty(`--${property}`, theme[property]);
      else root.style.removeProperty(`--${property}`);
    });
    DESIGN_PROPERTIES.forEach((property) => {
      if (design[property]) root.style.setProperty(`--${property}`, design[property]);
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
