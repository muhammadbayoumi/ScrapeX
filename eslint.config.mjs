// The JavaScript half of the gate. Its Python half lives in pyproject.toml, and
// the reasoning is the same in both: a chosen rule set, every exception carrying
// a reason, and no dependency the repository does not already need.
//
// NO package.json, ON PURPOSE. `.github/workflows/ci.yml` says it out loud about
// the node test runner -- "no package.json, no dependencies" -- and that is worth
// keeping: this repository ships a Chrome extension whose whole security story is
// that it has no third-party JavaScript in it. CI installs eslint for the length
// of one step, pinned, and nothing is added to what gets packaged.
//
// The globals are listed by hand rather than pulled from the `globals` package,
// for the same reason: one more dependency to lint 11,000 lines is a bad trade,
// and being explicit about what each area is allowed to reach for is a feature.
// A file that suddenly needs `chrome` outside extension/ should have to say so.

const BROWSER = {
  window: "readonly", document: "readonly", console: "readonly",
  fetch: "readonly", URL: "readonly", URLSearchParams: "readonly",
  setTimeout: "readonly", clearTimeout: "readonly",
  setInterval: "readonly", clearInterval: "readonly",
  requestAnimationFrame: "readonly", localStorage: "readonly",
  sessionStorage: "readonly", location: "readonly", navigator: "readonly",
  alert: "readonly", confirm: "readonly", getComputedStyle: "readonly",
  CustomEvent: "readonly", Event: "readonly", FormData: "readonly",
  Blob: "readonly", FileReader: "readonly", AbortController: "readonly",
  IntersectionObserver: "readonly", MutationObserver: "readonly",
  ResizeObserver: "readonly", DOMParser: "readonly", Image: "readonly",
  structuredClone: "readonly", crypto: "readonly", btoa: "readonly",
  atob: "readonly", TextEncoder: "readonly", TextDecoder: "readonly",
  cancelAnimationFrame: "readonly", queueMicrotask: "readonly",
  // The startup instrumentation's whole vocabulary. `first-contentful-paint`
  // from a PerformanceObserver is the only thing in the trace that claims an
  // actual paint — every other mark says when OUR code ran, which is a
  // different question and was answered as if it were the same one twice.
  performance: "readonly", PerformanceObserver: "readonly",
  CSS: "readonly", Node: "readonly", MouseEvent: "readonly",
  AbortSignal: "readonly", DecompressionStream: "readonly",
  TextDecoderStream: "readonly", HTMLElement: "readonly",
  // Loaded from static/vendor/ by a <script> tag, so it is a global here and
  // named rather than waved through: a typo'd vendor name must still fail.
  Tabulator: "readonly",
  // Defined by timezone.js, which app.js's page loads before it as a classic
  // script. Listing it is the only way `no-undef` can tell this apart from a
  // function that does not exist -- which is exactly the defect this gate
  // found in app.js (`el`).
  ScrapeXTime: "readonly",
};

const EXTENSION = { ...BROWSER, chrome: "readonly" };

const NODE = {
  console: "readonly", process: "readonly", Buffer: "readonly",
  __dirname: "readonly", __filename: "readonly", URL: "readonly",
  TextEncoder: "readonly", TextDecoder: "readonly", fetch: "readonly",
  setTimeout: "readonly", structuredClone: "readonly",
};

// Apps Script runs on Google's own runtime, where these are provided.
const APPS_SCRIPT = {
  console: "readonly", SpreadsheetApp: "readonly", UrlFetchApp: "readonly",
  PropertiesService: "readonly", Utilities: "readonly", Logger: "readonly",
  HtmlService: "readonly", ScriptApp: "readonly", Session: "readonly",
  CacheService: "readonly", LockService: "readonly", DriveApp: "readonly",
};

const RULES = {
  // THE ONES THAT CATCH DEFECTS. Every one of these is a bug that ships
  // silently in a language with no compiler.
  "no-undef": "error",                    // a typo'd name is a runtime crash
  // caughtErrors: "none" -- `catch (err) {}` where err goes unread is not a
  // defect, it is a deliberate best-effort read, and there are 60 of them. The
  // rule's value is unused LOCALS and unused IMPORTS, which stay on.
  "no-unused-vars": ["error", { args: "none", caughtErrors: "none",
                                varsIgnorePattern: "^_" }],
  "no-dupe-keys": "error",                // the second one silently wins
  "no-dupe-args": "error",
  "no-dupe-else-if": "error",
  "no-duplicate-case": "error",
  "no-unreachable": "error",
  "no-fallthrough": "error",
  "no-self-assign": "error",
  "no-self-compare": "error",
  "no-constant-condition": ["error", { checkLoops: true }],
  // "except-parens", not "always": `while ((match = pattern.exec(text)))` is
  // THE way to walk a global regex in JavaScript, and the extra parentheses are
  // the language's own way of saying the assignment is deliberate.
  "no-cond-assign": ["error", "except-parens"],
  "no-unsafe-negation": "error",
  "no-unsafe-optional-chaining": "error",
  "no-sparse-arrays": "error",
  "no-async-promise-executor": "error",
  "use-isnan": "error",
  "valid-typeof": "error",
  "no-implied-eval": "error",
  "no-eval": "error",
  "no-new-func": "error",
  "no-prototype-builtins": "error",
  "no-var": "error",                      // `var` hoisting has bitten this file set
  "eqeqeq": ["error", "smart"],           // "smart" still allows == null

  // NOT ENABLED, each for a reason:
  // - require-atomic-updates: 20 hits, every one of the form `state.x = await
  //   f()` in a panel whose handlers do not run concurrently. The rule cannot
  //   see that, and a rule that is wrong 20 times out of 20 teaches people to
  //   stop reading the output.
  // - no-console: the extension's console output IS its diagnostics, and the
  //   panel has no other place to say what happened on a user's machine.
  // - camelcase: the contract carries snake_case column names verbatim from
  //   the database; renaming them at the boundary is how a column silently
  //   stops matching.
  // - no-empty: `catch {}` after a best-effort read is deliberate in several
  //   places and each already carries a comment saying so.
};

export default [
  // GLOBAL, and it has to be: an `ignores` beside a `files` key only narrows
  // that one block. Vendored bytes are not ours to lint — holding a minified
  // third-party bundle to this project's rules reports a thousand findings
  // nobody can act on, which is how a linter gets turned off.
  { ignores: ["scrapex/webui/static/vendor/**", "extension/vendor/**"] },
  {
    files: ["extension/**/*.js", "extension/**/*.mjs"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: EXTENSION },
    rules: RULES,
  },
  {
    // The MV3 service worker, which manifest.json declares WITHOUT
    // `"type": "module"` — so it is a classic worker script, and
    // `importScripts` is the only way it can reach startup-trace.js.
    //
    // Named here and not in EXTENSION on purpose, in this file's own spirit: a
    // panel script that reaches for `importScripts` is a bug, and listing the
    // global one directory wide would stop it being one.
    files: ["extension/background.js"],
    languageOptions: {
      sourceType: "script",
      globals: { ...EXTENSION, importScripts: "readonly" },
    },
  },
  {
    // Loaded THREE ways, which is the point of it: a classic <script> on the
    // panel's pages, `importScripts` in the service worker, and `require` under
    // `node --test`. Its last two lines are the detection that lets one file do
    // that, and `module` is defined in exactly one of the three — which is what
    // the `typeof` guard in front of it is checking.
    files: ["extension/startup-trace.js"],
    languageOptions: {
      sourceType: "script",
      globals: { ...EXTENSION, module: "writable" },
    },
  },
  {
    files: ["scrapex/webui/static/**/*.js"],
    ignores: ["scrapex/webui/static/vendor/**", "extension/vendor/**"],
    languageOptions: { ecmaVersion: 2023, sourceType: "script", globals: BROWSER },
    rules: RULES,
  },
  {
    // The extension's own node:test files run on node, not in a page.
    files: ["extension/tests/**/*.mjs", "extension/tests/**/*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: NODE },
    rules: RULES,
  },
  {
    // …but not everything in that directory is a test. The diagnostic pages of
    // the Side Panel bisect live there because extension/tests/ is the one
    // directory the release workflow deletes and then fails the build over, so
    // nothing in it can ship. They are ordinary classic browser scripts loaded
    // by a <script> tag, and lining them up with node's globals reported the
    // browser's own `performance` as undefined.
    files: ["extension/tests/diagnostic-*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "script", globals: EXTENSION },
    rules: RULES,
  },
  {
    files: ["contract/**/*.mjs", "contract/**/*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: NODE },
    rules: RULES,
  },
  {
    files: ["apps_script/**/*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "script", globals: APPS_SCRIPT },
    rules: RULES,
  },
];
