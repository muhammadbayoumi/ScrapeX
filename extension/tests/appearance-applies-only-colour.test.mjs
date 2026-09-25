// A palette may change nothing but colour (R-74), and apply() is what makes that true at
// runtime: it walks THEME_PROPERTIES, the colour allowlist, never the palette's own keys
// (#404). The one palette the registry holds declares no colours, so the real loop and a
// loop over Object.keys(theme) behave the same on it; this test gives apply() a palette
// the registry does not hold, carrying a colour key and a non-colour one.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SOURCE = readFileSync(new URL("../appearance.js", import.meta.url), "utf8");
const REGISTRY = "const PALETTES = new Map([";
const PROBE = `["zz-probe", {id: "zz-probe", label: "Probe", description: "Probe",
  colors: [], themes: {light: {accent: "#123456", borderRadius: "99px"}, dark: {}}}],`;

function runWithProbePalette() {
  assert.equal(SOURCE.split(REGISTRY).length, 2, "the palette registry is no longer declared once");
  const set = new Map();
  const removed = new Set();
  const root = {
    dataset: {},
    style: {
      setProperty: (name, value) => { set.set(name, value); removed.delete(name); },
      removeProperty: (name) => { removed.add(name); set.delete(name); },
    },
    removeAttribute() {},
  };
  const stored = JSON.stringify({ mode: "manual", scheme: "light", palette: "zz-probe" });
  const window = {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    localStorage: { getItem: () => stored, setItem() {} },
    // The extension's own origin: on http(s) the file connects to the engine and fetches.
    location: { protocol: "chrome-extension:", origin: "chrome-extension://probe" },
    addEventListener() {},
  };
  const document = { documentElement: root, querySelectorAll: () => [], addEventListener() {} };
  window.document = document;
  vm.runInNewContext(SOURCE.replace(REGISTRY, `${REGISTRY}\n${PROBE}`), {
    window, document, console, setTimeout, clearTimeout,
  });
  return { set, removed, palette: root.dataset.palette };
}

test("apply() sets a colour a palette declares", () => {
  const { set, palette } = runWithProbePalette();
  assert.equal(palette, "zz-probe", "the probe palette was not the one applied");
  assert.equal(set.get("--accent"), "#123456");
});

test("apply() never sets a key a palette declares that is not a colour", () => {
  const { set } = runWithProbePalette();
  assert.equal(set.has("--border-radius"), false,
    "a palette's borderRadius reached the page: apply() is walking the palette's keys, not THEME_PROPERTIES");
});

test("apply() clears every colour the palette does not declare, so the baseline shows through", () => {
  const { removed } = runWithProbePalette();
  for (const name of ["--bg", "--text", "--red-hover", "--overlay"]) {
    assert.ok(removed.has(name), `${name} was left set by an earlier palette`);
  }
  assert.equal(removed.has("--accent"), false);
});
