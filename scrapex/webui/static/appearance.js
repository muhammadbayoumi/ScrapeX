(function () {
  "use strict";

  const STORAGE_KEY = "scrapex-appearance-v1";
  const SCHEMES = new Set(["light", "dark"]);
  const ACCENTS = new Set([
    "cyan", "blue", "slate", "indigo", "teal", "green", "forest", "olive",
    "gold", "orange", "brown", "rose", "burgundy", "plum", "violet", "custom",
  ]);
  const DEFAULTS = Object.freeze({
    mode: "follow",
    scheme: "light",
    accent: "cyan",
    followColors: true,
    customAccent: "#4f7fc9",
  });
  const schemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let current = read();

  function normalize(value) {
    const candidate = value && typeof value === "object" ? value : {};
    return {
      mode: candidate.mode === "manual" ? "manual" : "follow",
      scheme: SCHEMES.has(candidate.scheme) ? candidate.scheme : DEFAULTS.scheme,
      accent: ACCENTS.has(candidate.accent) ? candidate.accent : DEFAULTS.accent,
      followColors: typeof candidate.followColors === "boolean"
        ? candidate.followColors
        : candidate.mode !== "manual",
      customAccent: /^#[0-9a-f]{6}$/i.test(candidate.customAccent || "")
        ? candidate.customAccent
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

  function apply(value) {
    const root = document.documentElement;
    root.dataset.appearance = value.mode;
    root.dataset.colorMode = value.followColors ? "follow" : "manual";
    root.style.setProperty("--custom-accent", value.customAccent);
    if (value.mode === "manual") {
      root.dataset.theme = value.scheme;
    } else {
      root.removeAttribute("data-theme");
    }
    if (value.followColors) {
      root.removeAttribute("data-accent");
    } else {
      root.dataset.accent = value.accent;
    }
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

  function statusText(value = current) {
    if (value.mode === "follow" && value.followColors) {
      return `Following Chrome · ${effectiveScheme(value)}`;
    }
    const theme = value.mode === "follow" ? "Chrome theme" : value.scheme;
    const colour = value.followColors ? "Chrome colours" : value.accent;
    return `${theme} · ${colour}`;
  }

  function syncControls() {
    document.querySelectorAll("[data-appearance-control]").forEach((control) => {
      control.classList.toggle("is-following", current.mode === "follow");
      control.querySelectorAll("[data-appearance-mode]").forEach((button) => {
        const active = button.dataset.appearanceMode === current.mode;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      control.querySelectorAll("[data-appearance-scheme]").forEach((button) => {
        const active = button.dataset.appearanceScheme === current.scheme;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
        button.disabled = current.mode === "follow";
      });
      control.querySelectorAll("[data-appearance-accent]").forEach((button) => {
        const active = button.dataset.appearanceAccent === current.accent;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
        button.disabled = current.followColors;
      });
      control.querySelectorAll("[data-appearance-scheme-mode]").forEach((button) => {
        const choice = button.dataset.appearanceSchemeMode;
        const active = choice === "follow"
          ? current.mode === "follow"
          : current.mode === "manual" && current.scheme === choice;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      control.querySelectorAll("[data-appearance-follow-colors]").forEach((input) => {
        input.checked = current.followColors;
      });
      control.querySelectorAll("[data-appearance-custom-color]").forEach((input) => {
        input.value = current.customAccent;
        input.disabled = current.followColors;
        input.closest(".appearance-custom-tile")
          ?.classList.toggle("is-active", current.accent === "custom");
      });
      control.querySelectorAll("[data-appearance-status]").forEach((status) => {
        status.textContent = statusText();
      });
    });

  }

  function bindControls() {
    document.querySelectorAll("[data-appearance-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.dataset.appearanceMode;
        set({mode, followColors: mode === "follow"});
      });
    });
    document.querySelectorAll("[data-appearance-scheme]").forEach((button) => {
      button.addEventListener("click", () =>
        set({mode: "manual", scheme: button.dataset.appearanceScheme}));
    });
    document.querySelectorAll("[data-appearance-accent]").forEach((button) => {
      button.addEventListener("click", () =>
        set({followColors: false, accent: button.dataset.appearanceAccent}));
    });
    document.querySelectorAll("[data-appearance-scheme-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        const choice = button.dataset.appearanceSchemeMode;
        if (choice === "follow") {
          set({mode: "follow"});
        } else {
          set({mode: "manual", scheme: choice});
        }
      });
    });
    document.querySelectorAll("[data-appearance-follow-colors]").forEach((input) => {
      input.addEventListener("change", () => set({followColors: input.checked}));
    });
    document.querySelectorAll("[data-appearance-custom-color]").forEach((input) => {
      input.addEventListener("input", () =>
        set({followColors: false, accent: "custom", customAccent: input.value}));
    });
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
  });

  schemeQuery.addEventListener("change", () => {
    if (current.mode !== "follow") return;
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
