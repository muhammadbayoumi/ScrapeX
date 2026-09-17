// `Healthy` has to earn the word.
//
// For a whole working day the panel served an empty 880,640-byte test database
// in `%TEMP%` while the real 2.1 GB warehouse sat unopened, and the Databases
// row on Settings said Healthy throughout. It was computed from one boolean —
// `databases.ok`, which asks only "did the files open" — and that boolean was
// TRUE. Nothing lied; the sentence the panel assembled out of a true fact was
// false. The owner's words are the brief: "users will not be able to understand
// or even notice problems like these when the tool ships".
//
// #992 closed the Engines half: that screen now names the warehouse and refuses
// a scratch folder as "Temporary database". This file is the other half, and
// until it existed the two screens CONTRADICTED each other — Settings calling a
// path Healthy while Engines called the same path "Not your data", in the same
// panel, at the same moment.
//
// READ AS SOURCE TEXT, like `warehouse.test.mjs` next door and for the same
// reason: `extension/app.js` exports nothing and touches `chrome.*` at module
// scope, so importing it here would need a browser. Each piece is matched out by
// a regex that is itself asserted, so a function that is renamed or moved fails
// loudly here rather than leaving a guard that quietly tests a copy which has
// drifted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = join(HERE, "..", "app.js");
const SOURCE = readFileSync(APP, "utf8");

function extract(name, pattern) {
  const match = SOURCE.match(pattern);
  assert.ok(match, `${name} is no longer where this guard reads it from in app.js`);
  return match[0];
}

// Every piece the Settings runtime grid is built from, in the order it has to be
// declared. The function shapes all end on a `}` in column 0 — every brace
// inside them is indented — so a lazy match stops at the end of the function and
// not at the end of a block within it.
//
// `esc` AND `icon` ARE EXTRACTED RATHER THAN STUBBED, so the markup this file
// measures is byte-for-byte the markup the panel writes. A hand-written escaper
// here would be a second copy of the rule, and a test that renders through the
// wrong one is a test of the wrong page.
const PIECES = [
  ["esc", /^const esc = \(v\) => String[\s\S]*?\}\[c\]\)\);$/m],
  ["ICON_SPRITE", /^const ICON_SPRITE = ".*";$/m],
  ["icon", /^const icon = \(name, className = ""\) =>[\s\S]*?<\/svg>`;$/m],
  ["TEMPORARY_FOLDERS", /^const TEMPORARY_FOLDERS = new Set\(\[[^\]]*\]\);$/m],
  ["TEMPORARY_PREFIXES", /^const TEMPORARY_PREFIXES = \[[^\]]*\];$/m],
  ["warehouseSegments", /^const warehouseSegments = .*;$/m],
  ["temporaryFolderIn", /^function temporaryFolderIn\(path\) \{[\s\S]*?\n\}/m],
  ["schemaIsBehind", /^const schemaIsBehind = .*;$/m],
  ["COMPONENTS", /^const COMPONENTS = \[[\s\S]*?\n\];$/m],
  ["renderRuntime", /^function renderRuntime\(engine\) \{[\s\S]*?\n\}/m],
  ["repaintRuntime", /^function repaintRuntime\(\) \{[\s\S]*?\n\}/m],
  ["runningEngineSummary", /^function runningEngineSummary\(\) \{[\s\S]*?\n\}/m],
  ["forgetWarehouse", /^function forgetWarehouse\(\) \{[\s\S]*?\n\}/m],
  ["noteWarehouse", /^function noteWarehouse\(storage\) \{[\s\S]*?\n\}/m],
];

// ONE SCOPE FOR ALL OF THEM, because the thing under test is precisely that they
// share one: the Databases row reads `state.warehousePath`, which `noteWarehouse`
// writes and `forgetWarehouse` clears, and the row has to be repainted when it
// moves. Testing them apart would miss the wiring, which is the half that was
// missing.
//
// `state` arrives as a PARAMETER, and `$` is the only piece of DOM — so the one
// page that opens a Chrome side panel can be exercised by `node --test` at all.
// `lastHealth`, `warehouseGeneration` and `warehouseAsk` are module-scope `let`s
// in app.js, declared into the extracted scope here and handed back for
// inspection.
const panelFor = (() => {
  const body = "let lastHealth = null;\nlet warehouseGeneration = 0;\n"
    + "let warehouseAsk = null;\n"
    + PIECES.map(([name, pattern]) => extract(name, pattern)).join("\n")
    + "\nreturn { COMPONENTS, renderRuntime, repaintRuntime, runningEngineSummary,"
    + " forgetWarehouse, noteWarehouse, temporaryFolderIn, schemaIsBehind,"
    + " held: () => lastHealth, generation: () => warehouseGeneration };";
  // eslint-disable-next-line no-new-func
  const make = new Function("state", "$", "renderEngineStatusUI", body);
  return (over = {}) => {
    const state = Object.assign({warehousePath: ""}, over);
    const grid = {html: null};
    const asked = [];
    const box = {
      set innerHTML(value) { grid.html = value; },
      get innerHTML() { return grid.html; },
    };
    const statusRepaints = {n: 0};
    const api = make(state, (id) => { asked.push(id); return box; },
                     () => { statusRepaints.n += 1; });
    return Object.assign(api, {state, grid, asked, statusRepaints});
  };
})();

//: His warehouse, in the shape `GET /api/storage` reports it (`s.path`), on the
//: layout the engine actually produces — `~/.scrapex/engine/scrapex-engine.db`,
//: stated at `scrapex/db.py:39-40`. NOT `harvest.db`, which that same file says
//: is not the warehouse: a fixture written against a layout the product does not
//: produce has cost this repository an afternoon already.
const HIS = "C:\\Users\\Owner\\.scrapex\\engine\\scrapex-engine.db";
//: What actually happened: `tempfile.mkdtemp(prefix="scrapex-tests-")` under the
//: Windows per-user temp folder, which is where `tests/conftest.py` puts it.
const THE_INCIDENT =
  "C:\\Users\\sapac\\AppData\\Local\\Temp\\scrapex-tests-7k2f9a\\scrapex-engine.db";

//: One pending migration, in the shape the engine sends it
//: (`scrapex/webui/app.py`, the `schema_lag` block).
const BEHIND = {
  pending: ["0043_add_source_weight.sql"],
  fix: "press Upgrade database on the Database page",
  message: "1 migration(s) on disk are not applied to this database.",
};

// A health answer with every question answered YES. Each test below turns
// exactly one of them to no.
const ALL_WELL = {running: true, databases: {ok: true, detail: ""}, schema_lag: null};

/** The Databases row's verdict, for one health answer and one warehouse path. */
function databases(engine = {}, path = HIS) {
  const panel = panelFor({warehousePath: path});
  const row = panel.COMPONENTS.find(([label]) => label === "Databases");
  assert.ok(row, "the Databases row is gone from COMPONENTS");
  return row[2](Object.assign({}, ALL_WELL, engine));
}

// ---- the five cases, exactly as they render -------------------------------

test("all four questions yes is the only thing that says Healthy", () => {
  assert.deepEqual(databases(), {text: "Healthy", tone: "ready"});
});

test("a warehouse inside a scratch folder is not Healthy", () => {
  // THE ENGINES SCREEN'S OWN WORDS, and that is the point of choosing them: two
  // screens, minutes apart, must not need reconciling.
  assert.deepEqual(databases({}, THE_INCIDENT),
                   {text: "Temporary database", tone: "warning"});
});

test("a schema behind the code is not Healthy", () => {
  assert.deepEqual(databases({schema_lag: BEHIND}),
                   {text: "Behind the engine", tone: "warning"});
});

test("databases that did not open are not Healthy, and the engine says why", () => {
  // The engine's own detail is the only sentence here that can name the fault,
  // so it is passed through whole — the one verdict in this row with no length
  // ceiling.
  assert.deepEqual(
    databases({databases: {ok: false, detail: "marketlens: file is not a database"}}),
    {text: "Needs attention — marketlens: file is not a database", tone: "warning"});
});

test("a path nothing has answered for yet claims nothing, and is not Healthy", () => {
  // `GET /api/storage` is a different request from the health poll: it may not
  // have landed, or may have failed outright. Saying Healthy here would be
  // claiming the file is his without having read its name — the incident. The
  // tone is `neutral`, the grey tile, because an unanswered question is not a
  // fault and a red one on every Settings open would teach him to read past it.
  assert.deepEqual(databases({}, ""), {text: "Open — path unknown", tone: "neutral"});
});

test("a worker that is not alive has answered nothing about the databases", () => {
  // Unchanged from before this file, and it is the fourth question: `running` is
  // `worker_alive` from `/api/health` (extension/engine.js).
  assert.deepEqual(databases({running: false}), {text: "Unknown", tone: "warning"});
  // AND IT OUTRANKS EVERY OTHER ANSWER, including a path that would otherwise be
  // refused: a dead worker holds no database open, so there is nothing in a
  // temporary folder to warn about.
  assert.deepEqual(databases({running: false}, THE_INCIDENT),
                   {text: "Unknown", tone: "warning"});
});

test("an engine that reported no databases block keeps the narrower word", () => {
  // A build from before the block existed said nothing about its databases, so
  // neither does this — and `Ready` is not `Healthy`, which is what the branch
  // is for. Unchanged behaviour, pinned because the reordering above moved it.
  assert.deepEqual(databases({databases: null}), {text: "Ready", tone: "ready"});
  assert.deepEqual(databases({databases: undefined}), {text: "Ready", tone: "ready"});
  // AND IT IS STILL "Ready" WITH NO PATH, which is the one place that word
  // outranks "Open — path unknown": an engine that never described its databases
  // is already making no claim, so there is no claim for a missing path to
  // qualify.
  assert.deepEqual(databases({databases: null}, ""), {text: "Ready", tone: "ready"});
});

test("an old build is refused by the facts the panel holds on its own", () => {
  // THE HOLE THE BRANCH ORDER COULD HAVE LEFT, and it is the original defect
  // taking the oldest door. The old code returned "Ready" the instant the
  // `databases` block was missing — so had that branch stayed first, an engine
  // from before the block existed would wear a GREEN tile on Settings while the
  // Engines screen called the very same path "Not your data".
  //
  // Neither fact below is the engine's to withhold by being old: the path comes
  // from `GET /api/storage` and the lag from `schema_lag`, and both arrive
  // whatever the health payload says about databases.
  assert.deepEqual(databases({databases: null}, THE_INCIDENT),
                   {text: "Temporary database", tone: "warning"});
  assert.deepEqual(databases({databases: null, schema_lag: BEHIND}),
                   {text: "Behind the engine", tone: "warning"});
  // AND A FAILED OPEN STILL OUTRANKS THE PATH, in the other direction: the
  // engine's own detail is the more specific answer, so a database that did not
  // open is named as that even when it sits in a scratch folder.
  assert.deepEqual(
    databases({databases: {ok: false, detail: "file is not a database"}}, THE_INCIDENT),
    {text: "Needs attention — file is not a database", tone: "warning"});
});

// ---- the claim the whole issue is about ------------------------------------

test("every single one of the four questions can take Healthy away", () => {
  // THIS IS THE ISSUE, IN ONE LOOP. `Healthy` was one boolean; it is now the
  // conjunction of four, and a branch that stopped being consulted would show up
  // here as a `false` that still reads Healthy.
  const breaks = [
    ["the worker is alive", {running: false}, HIS],
    ["the databases opened", {databases: {ok: false, detail: "unreadable"}}, HIS],
    ["the schema matches", {schema_lag: BEHIND}, HIS],
    ["the file is not disposable", {}, THE_INCIDENT],
    ["the path is known at all", {}, ""],
  ];
  for (const [question, engine, path] of breaks) {
    const verdict = databases(engine, path);
    assert.notEqual(verdict.text, "Healthy", `${question} is false and it says Healthy`);
    assert.notEqual(verdict.tone, "ready",
                    `${question} is false and the tile is still green: ${verdict.text}`);
  }
  // AND THE CONVERSE, which is the harder half: with all four true it must still
  // say the word, or the row has merely become a different kind of useless.
  assert.deepEqual(databases(), {text: "Healthy", tone: "ready"});
});

test("the two screens cannot disagree about the same warehouse", () => {
  // THE CONTRADICTION THIS FILE CLOSED. `#engine-status-badge` (Engines, from
  // #992) and `#components` (Settings, this change) are different elements on
  // different screens fed by different functions, and for one commit they
  // answered differently about one path: "Temporary database" there, "Healthy"
  // here. `updateEngineStatus`'s own comment states the principle — one summary,
  // two screens, so the row can never say Running over a banner that says Not
  // detected — and a second screen must not be how it comes back.
  for (const path of [
    THE_INCIDENT,
    "C:\\Users\\sapac\\AppData\\Local\\Temp\\scrapex-engine.db",
    "/tmp/scrapex/scrapex-engine.db",
    "D:\\scratch\\pytest-of-sapac\\pytest-131\\scrapex-engine.db",
  ]) {
    const panel = panelFor({warehousePath: path, engineUp: true, engineState: "ready",
                            protocolMismatch: false});
    const engines = panel.runningEngineSummary();
    const settings = databases({}, path);
    assert.equal(engines.tone, "danger", `Engines passed ${path}`);
    assert.notEqual(settings.tone, "ready",
                    `Engines refused ${path} while Settings called it ${settings.text}`);
  }
  // AND A LEGITIMATE PATH IS ACCEPTED BY BOTH, because a banner that cries wolf
  // is worse than no banner: it teaches him to read past the one row that has to
  // be believed. `Templates` and `Contemporary` contain the letters of a
  // temporary folder and are not one.
  for (const path of [
    HIS,
    "C:\\Users\\Owner\\Documents\\Templates\\scrapex-engine.db",
    "C:\\Users\\Contemporary\\.scrapex\\scrapex-engine.db",
    "C:\\Users\\Owner\\.scrapex\\tmp.db",
  ]) {
    const panel = panelFor({warehousePath: path, engineUp: true, engineState: "ready",
                            protocolMismatch: false});
    assert.equal(panel.runningEngineSummary().tone, "ok", `Engines refused ${path}`);
    assert.deepEqual(databases({}, path), {text: "Healthy", tone: "ready"},
                     `Settings refused ${path}`);
  }
});

// ---- the tone, which is the trap one layer down ----------------------------

// The rule the renderer used to apply, kept here as the thing being disproved.
// Anything it did not match rendered GREEN.
const oldTone = (value) => (/Stopped|Unknown|Needs attention/i.test(value)
  ? "warning"
  : /Optional/i.test(value) ? "neutral" : "ready");

test("the tone is carried by the verdict, not read back out of its words", () => {
  // THE RENDERER USED TO GUESS, and it guessed wrong in BOTH directions on the
  // verdicts this change adds — which is the argument for a property over a
  // pattern better than either direction alone.
  //
  // GREEN WHERE IT SHOULD BE RED: neither of these two contains one of the three
  // hard-coded words, so a rule whose fall-through is "ready" would have painted
  // the accent tile on a refusal — the exact defect this file exists to remove,
  // reproduced by the line meant to present it.
  for (const text of ["Temporary database", "Behind the engine"]) {
    assert.equal(oldTone(text), "ready",
                 `${text} already matched the old rule, so it proves nothing here`);
    assert.notEqual(databases({}, THE_INCIDENT).tone, "ready");
  }
  // AND RED WHERE IT SHOULD BE GREY, which is the half a careful choice of words
  // could not have fixed: "Open — path unknown" contains "unknown", so the old
  // rule would have fired the red tile at a panel that is merely waiting for a
  // reply. A warning on every Settings open before `/api/storage` lands is how a
  // warning becomes furniture.
  assert.equal(oldTone("Open — path unknown"), "warning");
  assert.equal(databases({}, "").tone, "neutral");

  // Read from the renderer itself: the words are gone from it, and the tone it
  // writes comes off the object.
  const renderer = extract("renderRuntime",
                           /^function renderRuntime\(engine\) \{[\s\S]*?\n\}/m);
  assert.ok(!renderer.includes("/Stopped|Unknown|Needs attention/i"),
            "the tone is being inferred from the text again");
  assert.ok(/const \{text, tone\} = fn\(engine\);/.test(renderer),
            "the renderer no longer takes the tone from the verdict it was given");
});

/** The one `<article>` in the grid whose label is `label`. */
function tile(html, label) {
  const found = String(html).split("<article ")
    .filter((piece) => piece.includes(`<strong>${label}</strong>`));
  assert.equal(found.length, 1, `${label} is not a single tile in the grid`);
  return `<article ${found[0]}`;
}

test("a refused warehouse paints the red tile, in the markup the panel writes", () => {
  // THE END OF THE WIRE, not the verdict object: `.engine-component[data-tone=
  // "warning"]` is the rule that paints red and `[data-tone="ready"]` the one
  // that paints green (extension/app.css) — `neutral`, like anything else, gets
  // the plain grey tile. A verdict with the right tone and a renderer that drops
  // it on the floor is the same screen the owner had.
  const panel = panelFor({warehousePath: THE_INCIDENT});
  panel.renderRuntime(Object.assign({}, ALL_WELL));
  assert.deepEqual(panel.asked, ["components"], "the grid was written somewhere else");
  const painted = tile(panel.grid.html, "Databases");
  assert.ok(painted.includes('data-tone="warning"'), painted);
  assert.ok(painted.includes("<small>Temporary database</small>"), painted);
  assert.ok(painted.includes("icons/material-icons.svg#storage"), painted);

  // And the ordinary case is the green one, so the assertion above is about the
  // path and not about the renderer always saying warning.
  const ordinary = panelFor({warehousePath: HIS});
  ordinary.renderRuntime(Object.assign({}, ALL_WELL));
  const green = tile(ordinary.grid.html, "Databases");
  assert.ok(green.includes('data-tone="ready"'), green);
  assert.ok(green.includes("<small>Healthy</small>"), green);
});

test("the other four rows say and wear exactly what they always did", () => {
  // THE REFACTOR'S OWN RISK. Four rows had their tone inferred and now state it,
  // and a transcription slip there would repaint a row nobody was looking at.
  // Both halves of each, because `Stopped` and `Unknown` were the words that the
  // old regex matched — the ones most likely to be dropped in the move.
  const expected = [
    ["Core service", {text: "Running", tone: "ready"}, {text: "Stopped", tone: "warning"}],
    ["Python runtime", {text: "Ready", tone: "ready"}, {text: "Unknown", tone: "warning"}],
    ["HTTP fetcher", {text: "Ready", tone: "ready"}, {text: "Unknown", tone: "warning"}],
    ["Browser automation", {text: "Optional", tone: "neutral"},
     {text: "Optional", tone: "neutral"}],
  ];
  const panel = panelFor({warehousePath: HIS});
  for (const [label, up, down] of expected) {
    const row = panel.COMPONENTS.find(([name]) => name === label);
    assert.ok(row, `${label} has gone from the runtime grid`);
    assert.deepEqual(row[2]({running: true}), up, label);
    assert.deepEqual(row[2]({running: false}), down, label);
  }
  // FIVE ROWS, NOT FOUR PLUS WHATEVER: a row added without a tone would render
  // `data-tone="undefined"` and take the grey tile in silence.
  assert.equal(panel.COMPONENTS.length, 5);
  for (const [label, , fn] of panel.COMPONENTS) {
    for (const engine of [{running: true}, {running: false},
                          Object.assign({}, ALL_WELL)]) {
      const verdict = fn(engine);
      assert.equal(typeof verdict.text, "string", label);
      assert.ok(["ready", "warning", "neutral"].includes(verdict.tone),
                `${label} wears ${verdict.tone}, which no rule in app.css paints`);
    }
  }
});

test("the engine's detail is escaped before it reaches the grid", () => {
  // The panel renders what the engine hands it, and `databases.detail` carries a
  // file path a crawl can influence. `esc` is extracted from app.js above rather
  // than written here, so this measures the panel's own escaper.
  const panel = panelFor({warehousePath: HIS});
  panel.renderRuntime(Object.assign({}, ALL_WELL, {
    databases: {ok: false, detail: '<img src=x onerror="alert(1)">'}}));
  const painted = tile(panel.grid.html, "Databases");
  assert.ok(!painted.includes("<img"), painted);
  assert.ok(painted.includes("&lt;img"), painted);
});

test("every verdict fits the cell, which clips in silence", () => {
  // MEASURED, at the 360px panel `tests/test_panel_dom.py` opens, with the
  // "Engine connection" accordion expanded: `.engine-component-copy small` is
  // 172px wide, `white-space: nowrap` with `text-overflow: ellipsis` and no
  // scrollbar — so a verdict that does not fit is CUT with nothing to say so.
  // 20 capital Ms reported scrollWidth 198 against clientWidth 172 and clipped;
  // "Open — path unknown xxxx" at 24 characters of ordinary text reported 172
  // and did not. So the ceiling below is text-shaped rather than a proof of fit:
  // it is what stops a verdict being lengthened without re-measuring.
  //
  // THE ENGINE'S OWN FAILURE DETAIL IS THE ONE EXCEPTION and is deliberately
  // uncapped: it is the payload, the row is red either way, and the Database
  // page states it in full.
  const capped = [
    databases(), databases({}, THE_INCIDENT), databases({schema_lag: BEHIND}),
    databases({}, ""), databases({running: false}), databases({databases: null}),
  ];
  for (const verdict of capped) {
    assert.ok(verdict.text.length <= 24,
              `"${verdict.text}" is ${verdict.text.length} characters; re-measure `
              + "the cell before lengthening it");
  }
});

// ---- the wiring, which the verdict above cannot show -----------------------

test("the path arriving repaints the row that judges it", () => {
  // THE HALF THAT WAS MISSING, AND IT IS NOT VISIBLE IN THE VERDICT. The grid is
  // painted by the health poll; the path arrives from `GET /api/storage`, later
  // and on its own schedule. Without a repaint the tile kept whatever it was
  // last painted with — a scratch folder reading Healthy until something else
  // happened to ask the engine a question.
  const panel = panelFor({warehousePath: ""});
  panel.renderRuntime(Object.assign({}, ALL_WELL));
  assert.ok(tile(panel.grid.html, "Databases").includes("Open — path unknown"));

  panel.noteWarehouse({path: THE_INCIDENT});
  assert.equal(panel.state.warehousePath, THE_INCIDENT);
  const after = tile(panel.grid.html, "Databases");
  assert.ok(after.includes("<small>Temporary database</small>"), after);
  assert.ok(after.includes('data-tone="warning"'), after);

  // AND THE OTHER DIRECTION, which is the one a restore takes: a good path
  // landing over a refused one must clear the refusal, or the warning becomes
  // permanent furniture.
  panel.noteWarehouse({path: HIS});
  assert.ok(tile(panel.grid.html, "Databases").includes("<small>Healthy</small>"));
});

test("dropping the path drops the verdict with it", () => {
  // `forgetWarehouse` runs on a stopped engine, on one that has just come back,
  // on a backend pointed at a different machine, and on the panel's own restart.
  // Only the first of those is followed by a `renderRuntime` from `setStatus`;
  // the other three would have left "Healthy" standing on Settings about a file
  // this panel had just admitted it no longer knows.
  const panel = panelFor({warehousePath: HIS});
  panel.renderRuntime(Object.assign({}, ALL_WELL));
  assert.ok(tile(panel.grid.html, "Databases").includes("<small>Healthy</small>"));

  const before = panel.generation();
  panel.forgetWarehouse();
  assert.equal(panel.state.warehousePath, "");
  assert.ok(panel.generation() > before);
  const after = tile(panel.grid.html, "Databases");
  assert.ok(after.includes("<small>Open — path unknown</small>"), after);
  assert.ok(after.includes('data-tone="neutral"'), after);
});

test("a repaint before the first health answer touches nothing", () => {
  // `whenBackendChanges(forgetWarehouse)` is registered at module scope and can
  // fire before any engine has answered. A repaint that reached for the DOM with
  // no health answer to paint would throw there, in the one place nothing is
  // watching.
  const panel = panelFor({warehousePath: HIS});
  assert.equal(panel.held(), null);
  panel.repaintRuntime();
  assert.equal(panel.grid.html, null, "the grid was painted from no health answer");
  assert.deepEqual(panel.asked, [], "the DOM was reached for with nothing to write");
});

test("Settings learns the path from the read it was already making", () => {
  // SOURCE TEXT, because the constraint is about WHICH request answers this and
  // when — which the rendered row cannot show. `state.warehousePath` was filled
  // ONLY by `renderEngines`, and `#components` is on Settings: an owner who
  // opened Settings first had a row judging a path nothing had fetched. The fix
  // costs no request at all — `loadStorage` already reads `/api/storage` on every
  // entry to Settings and threw the path away.
  const loadStorage = extract("loadStorage",
                              /^async function loadStorage\(\) \{[\s\S]*?\n\}/m);
  assert.ok(loadStorage.includes('api("/api/storage")'),
            "loadStorage no longer reads the route that carries the path");
  assert.ok(loadStorage.includes("noteWarehouse(s)"),
            "the free refresh is back on the floor: Settings judges a path it "
            + "never asked for");
  // AND IT IS STILL CALLED ON ENTRY TO SETTINGS, which is what makes it free.
  assert.match(SOURCE, /if \(name === "settings"\) \{[\s\S]*?loadStorage\(\);/,
               "Settings stopped loading storage on entry");
  // NOT A SECOND REQUEST. `askWhichWarehouse` is the Engines screen's ask and is
  // guarded once per engine; adding a call here would put `/api/storage` on a
  // second schedule for the same answer.
  assert.ok(!loadStorage.includes("askWhichWarehouse"),
            "Settings asks for the warehouse a second time");
});

test("the row and the schema banner ask one question, not two", () => {
  // DRY WHERE IT DECIDES A VERDICT. `renderSchemaLag` draws the banner that names
  // the pending migrations; this row refuses to call a lagging database Healthy.
  // Two hand-written copies of `lag.pending.length` are two chances for Settings
  // to reassure over a banner that is warning.
  const banner = extract("renderSchemaLag",
                         /^function renderSchemaLag\(lag\) \{[\s\S]*?\n\}/m);
  assert.ok(banner.includes("if (!schemaIsBehind(lag))"),
            "the banner has its own copy of the lag test again");
  const panel = panelFor();
  // The predicate itself, over the shapes the engine actually sends.
  assert.equal(panel.schemaIsBehind(null), false);
  assert.equal(panel.schemaIsBehind(undefined), false);
  assert.equal(panel.schemaIsBehind({}), false);
  assert.equal(panel.schemaIsBehind({pending: []}), false);
  assert.equal(panel.schemaIsBehind(BEHIND), true);
});

// ---- the file itself -------------------------------------------------------

test("app.js parses at all", () => {
  // NOTHING IN THIS SUITE NOTICED A BROKEN app.js UNTIL THIS TEST. Measured:
  // appending `function deliberatelyBroken( {` to extension/app.js and running
  // `node --test extension/tests/*.test.mjs` reported "tests 498, pass 498,
  // fail 0" — every guard here reads the file as TEXT and extracts the regions
  // it pins, so a syntax error anywhere outside them is invisible. The panel
  // would have been dead on every screen. `tests/test_panel_dom.py` catches it,
  // and that suite is `importorskip("playwright")`: on a machine without the
  // browser installed, a completely unloadable panel passed everything that ran.
  //
  // Node's own binary, no dependency, and a copy under `.mjs` so it is parsed as
  // the module app.js is rather than as a script.
  const dir = mkdtempSync(join(tmpdir(), "scrapex-app-syntax-"));
  const copy = join(dir, "app.mjs");
  try {
    writeFileSync(copy, SOURCE, "utf8");
    execFileSync(process.execPath, ["--check", copy], {stdio: "pipe"});
  } catch (error) {
    assert.fail(`extension/app.js does not parse: ${
      (error.stderr && error.stderr.toString()) || error.message}`);
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
});
