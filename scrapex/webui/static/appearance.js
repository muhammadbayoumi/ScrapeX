(function () {
  "use strict";

  const STORAGE_KEY = "scrapex-appearance-v1";
  const SCHEMES = new Set(["light", "dark"]);
  const ACCENTS = new Set(["cyan", "blue", "violet", "rose", "orange", "green"]);
  const DEFAULTS = Object.freeze({mode: "follow", scheme: "light", accent: "cyan"});
  const schemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let current = read();

  function normalize(value) {
    const candidate = value && typeof value === "object" ? value : {};
    return {
      mode: candidate.mode === "manual" ? "manual" : "follow",
      scheme: SCHEMES.has(candidate.scheme) ? candidate.scheme : DEFAULTS.scheme,
      accent: ACCENTS.has(candidate.accent) ? candidate.accent : DEFAULTS.accent,
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
    if (value.mode === "manual") {
      root.dataset.theme = value.scheme;
      root.dataset.accent = value.accent;
    } else {
      root.removeAttribute("data-theme");
      root.removeAttribute("data-accent");
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
    if (value.mode === "follow") {
      return `Following Chrome · ${effectiveScheme(value)}`;
    }
    return `Manual · ${value.scheme} · ${value.accent}`;
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
        button.disabled = current.mode === "follow";
      });
      control.querySelectorAll("[data-appearance-status]").forEach((status) => {
        status.textContent = statusText();
      });
    });

    document.querySelectorAll("[data-appearance-quick-toggle]").forEach((button) => {
      const following = current.mode === "follow";
      const label = following ? "Use manual appearance" : "Follow Chrome appearance";
      button.classList.toggle("is-active", following);
      button.setAttribute("aria-pressed", String(following));
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
    });
  }

  function bindControls() {
    document.querySelectorAll("[data-appearance-mode]").forEach((button) => {
      button.addEventListener("click", () => set({mode: button.dataset.appearanceMode}));
    });
    document.querySelectorAll("[data-appearance-scheme]").forEach((button) => {
      button.addEventListener("click", () =>
        set({mode: "manual", scheme: button.dataset.appearanceScheme}));
    });
    document.querySelectorAll("[data-appearance-accent]").forEach((button) => {
      button.addEventListener("click", () =>
        set({mode: "manual", accent: button.dataset.appearanceAccent}));
    });
    document.querySelectorAll("[data-appearance-quick-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        if (current.mode === "follow") {
          set({mode: "manual", scheme: effectiveScheme()});
        } else {
          set({mode: "follow"});
        }
      });
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
