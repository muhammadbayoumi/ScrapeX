(function () {
  "use strict";

  // The version is intentional: the sprite is expanded centrally and browsers
  // otherwise keep an older symbol set, leaving newly added icons blank.
  const ICON_SPRITE = "/static/material-icons/material-icons.svg?v=design-system-2";

  function escapeAttribute(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll('"', "&quot;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function icon(name, className = "", label = "") {
    if (!/^[a-z0-9-]+$/.test(name)) throw new TypeError("Invalid Material icon name");
    const classes = className ? " " + escapeAttribute(className) : "";
    const accessible = label
      ? `role="img" aria-label="${escapeAttribute(label)}"`
      : 'aria-hidden="true"';
    return `<svg class="sx-icon material-icon${classes}" ${accessible} focusable="false">` +
      `<use href="${ICON_SPRITE}#${name}"></use></svg>`;
  }

  function iconNode(name, className = "", label = "") {
    if (!/^[a-z0-9-]+$/.test(name)) throw new TypeError("Invalid Material icon name");
    const namespace = "http:" + "//www.w3.org/2000/svg";
    const glyph = document.createElementNS(namespace, "svg");
    glyph.classList.add("sx-icon", "material-icon");
    className.split(/\s+/).filter(Boolean).forEach((value) => glyph.classList.add(value));
    if (label) {
      glyph.setAttribute("role", "img");
      glyph.setAttribute("aria-label", label);
    } else {
      glyph.setAttribute("aria-hidden", "true");
    }
    glyph.setAttribute("focusable", "false");
    const use = document.createElementNS(namespace, "use");
    use.setAttribute("href", ICON_SPRITE + "#" + name);
    glyph.append(use);
    return glyph;
  }

  window.ScrapeXUI = Object.freeze({icon, iconNode});

  function setupWorkspace() {
    const root = document.documentElement;
    const topbar = document.querySelector(".topbar");
    const body = document.body;
    const toggle = document.querySelector(".sidebar-toggle");
    const backdrop = document.querySelector(".sidebar-backdrop");
    const navigation = document.querySelector(".wstabs");
    const sidebar = document.querySelector(".workspace-sidebar");
    const narrow = window.matchMedia("(max-width: 900px)");

    function measure() {
      const top = topbar ? topbar.getBoundingClientRect().height : 0;
      root.style.setProperty("--sticky-tabs", Math.round(top) + "px");
    }

    measure();
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(measure);
      if (topbar) observer.observe(topbar);
    } else {
      window.addEventListener("resize", measure);
    }

    if (!toggle || !navigation || !sidebar) return;
    body.classList.add("sidebar-ready");
    const sidebarPreference = "scrapex-navigation-hidden";

    function desktopPreference() {
      try {
        return window.localStorage.getItem(sidebarPreference) !== "true";
      } catch (error) {
        return true;
      }
    }

    function rememberDesktop(open) {
      try {
        window.localStorage.setItem(sidebarPreference, String(!open));
      } catch (error) {
        // A blocked preference must never block navigation.
      }
    }

    function setSidebar(open, remember) {
      body.classList.toggle("sidebar-open", narrow.matches && open);
      body.classList.toggle("sidebar-hidden", !narrow.matches && !open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Hide navigation" : "Show navigation");
      toggle.setAttribute("title", open ? "Hide navigation" : "Show navigation");
      sidebar.toggleAttribute("inert", !open);
      if (!open) sidebar.setAttribute("aria-hidden", "true");
      else sidebar.removeAttribute("aria-hidden");
      if (remember && !narrow.matches) rememberDesktop(open);
      if (open && narrow.matches) {
        const current = navigation.querySelector('[aria-current="page"]') ||
          navigation.querySelector("a");
        if (current) current.focus();
      }
    }

    toggle.addEventListener("click", function () {
      const open = narrow.matches
        ? !body.classList.contains("sidebar-open")
        : body.classList.contains("sidebar-hidden");
      setSidebar(open, true);
    });
    if (backdrop) {
      backdrop.addEventListener("click", function () {
        setSidebar(false, false);
        toggle.focus();
      });
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && body.classList.contains("sidebar-open")) {
        setSidebar(false, false);
        toggle.focus();
      }
    });
    function syncSidebarMode() {
      setSidebar(narrow.matches ? false : desktopPreference(), false);
    }
    if (narrow.addEventListener) narrow.addEventListener("change", syncSidebarMode);
    syncSidebarMode();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupWorkspace, {once: true});
  } else {
    setupWorkspace();
  }
})();
