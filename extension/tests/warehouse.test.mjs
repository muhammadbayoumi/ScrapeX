// The engine status says WHICH warehouse, pinned.
//
// For a whole working day the panel served a test database in `%TEMP%` —
// 880,640 bytes, every table empty — while the real 2.1 GB warehouse sat
// unopened beside it, and the card read Healthy throughout. The owner's own
// words are the brief: "users will not be able to understand or even notice
// problems like these when the tool ships". `engineStatusFromState()` is the one
// object `updateEngineStatus()` writes to BOTH surfaces, so the warehouse was put
// into it — and until this file nothing in the repository pinned that function at
// all, in any suite, on any branch.
//
// READ AS SOURCE TEXT, like esc() next door, and for the same reason:
// `extension/app.js` exports nothing and touches `chrome.*` at module scope, so
// importing it here would need a browser. Each piece is matched out by a regex
// that is itself asserted, so a function that is renamed or moved fails loudly
// here rather than leaving a guard that quietly tests a copy which has drifted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

// Every piece the status object is built from, in the order it has to be
// declared. The function shapes all end on a `}` in column 0 — every brace
// inside them is indented — so the lazy match stops at the end of the function
// and not at the end of a block within it.
const PIECES = [
  ["TEMPORARY_FOLDERS", /^const TEMPORARY_FOLDERS = new Set\(\[[^\]]*\]\);$/m],
  ["TEMPORARY_PREFIXES", /^const TEMPORARY_PREFIXES = \[[^\]]*\];$/m],
  ["warehouseSegments", /^const warehouseSegments = .*;$/m],
  ["temporaryFolderIn", /^function temporaryFolderIn\(path\) \{[\s\S]*?\n\}/m],
  ["runningEngineSummary", /^function runningEngineSummary\(\) \{[\s\S]*?\n\}/m],
  ["engineStatusFromState", /^function engineStatusFromState\(\) \{[\s\S]*?\n\}/m],
];

function extract(name, pattern) {
  const match = SOURCE.match(pattern);
  assert.ok(match, `${name} is no longer where this guard reads it from in app.js`);
  return match[0];
}

// `state` and `PROTOCOL_VERSION` arrive as PARAMETERS, so the extracted bodies
// close over whatever this file hands them instead of over the panel's live
// module scope — which is the only reason a page that opens a Chrome side panel
// can be exercised by `node --test` at all.
const summaryFor = (() => {
  const body = PIECES.map(([name, pattern]) => extract(name, pattern)).join("\n")
    + "\nreturn engineStatusFromState();";
  // eslint-disable-next-line no-new-func
  const run = new Function("state", "PROTOCOL_VERSION", body);
  return (over = {}) => run(Object.assign({
    engineState: "ready", engineUp: true, engineReachable: true,
    engineVersion: "0.3.0", engineProtocol: 1, protocolMismatch: false,
    warehousePath: "",
  }, over), 1);
})();

//: His warehouse, in the shape `GET /api/storage` reports it (`s.path`).
const HIS = "C:\\Users\\Owner\\.scrapex\\scrapex-engine.db";
//: What actually happened: `tempfile.mkdtemp(prefix="scrapex-tests-")` under the
//: Windows per-user temp folder, which is where `tests/conftest.py` puts it.
const THE_INCIDENT =
  "C:\\Users\\sapac\\AppData\\Local\\Temp\\scrapex-tests-7k2f9a\\scrapex-engine.db";

test("the state field the status reads from is still declared on `state`", () => {
  // The whole mechanism hangs off one field, and a status object built from a
  // property nothing sets would report "unknown" for ever without failing.
  assert.match(SOURCE, /^\s*warehousePath: "",$/m);
});

// ---- the ordinary case -----------------------------------------------------

test("a running engine still says exactly Running, and nothing else", () => {
  // AN EQUALITY, MIRRORING tests/test_panel_dom.py:4458, which reads
  // `text_of(page, "#engine-status") == "Running"`. The warehouse was put in
  // `detail` for this reason: the badge's one word is load-bearing.
  const summary = summaryFor({warehousePath: HIS});
  assert.equal(summary.text, "Running");
  assert.equal(summary.tone, "ok");
});

test("the ordinary case names the database under the word Running", () => {
  assert.equal(summaryFor({warehousePath: HIS}).detail,
               "Database: C:\\Users\\Owner\\.scrapex\\scrapex-engine.db");
});

test("a warehouse nothing has answered for yet claims nothing at all", () => {
  // Today's behaviour, kept: `GET /api/storage` may not have landed, or may have
  // failed outright. An empty detail is hidden by
  // `detail.classList.toggle("hidden", !summary.detail)`, so the row looks
  // exactly as it did before this change rather than showing a guess.
  const summary = summaryFor({warehousePath: ""});
  assert.equal(summary.text, "Running");
  assert.equal(summary.detail, "");
});


test("a path that already fits is never cut", () => {
  // The `…` must mean something. A prefix on a whole path would make it noise,
  // and noise on this line is what the incident was made of.
  assert.ok(!summaryFor({warehousePath: HIS}).detail.includes("…"),
            summaryFor({warehousePath: HIS}).detail);
});

test("a long path is named whole, because a short form could not tell two apart", () => {
  // THE SHORTENER THAT WAS HERE FIRST IS WHY THIS TEST IS. It kept the last two
  // segments, and on the layout the engine actually produces --
  // `~/.scrapex/engine/scrapex-engine.db`, stated at scrapex/db.py:39-40 -- those
  // two are CONSTANTS. Seven realistic warehouses across four drives rendered the
  // same line, and two different files were indistinguishable: the exact defect
  // the whole feature exists to remove, reintroduced by the line meant to present
  // it. The owner chose the whole path in both branches.
  const deep = "C:\\Users\\muhammad.bayoumi\\OneDrive - Company\\Documents\\"
    + "ScrapeX\\.scrapex\\engine\\scrapex-engine.db";
  const summary = summaryFor({warehousePath: deep});
  assert.equal(summary.text, "Running");
  assert.equal(summary.tone, "ok");
  assert.equal(summary.detail, `Database: ${deep}`);

  // AND TWO WAREHOUSES THAT DIFFER ONLY IN THEIR HEAD STILL READ DIFFERENTLY.
  // This is the assertion the old shape failed: it is not about length, it is
  // about whether the line answers "which database am I on".
  const onC = "C:\\Users\\sapac\\.scrapex\\engine\\scrapex-engine.db";
  const onE = "E:\\Old laptop restore\\sapac\\.scrapex\\engine\\scrapex-engine.db";
  assert.notEqual(summaryFor({warehousePath: onC}).detail,
                  summaryFor({warehousePath: onE}).detail);

  // A POSIX path is named whole too -- there is no separator logic left to get
  // wrong, which is the point of removing it.
  const posix = "/home/sapac/.scrapex/engine/scrapex-engine.db";
  assert.equal(summaryFor({warehousePath: posix}).detail, `Database: ${posix}`);

  // Nothing is ever elided, in any branch. The refusal below already printed in
  // full; now the ordinary line does too, and one rule cannot disagree with
  // itself.
  for (const path of [deep, onC, onE, posix]) {
    assert.ok(!summaryFor({warehousePath: path}).detail.includes("\u2026"),
              `an abbreviation survived for ${path}`);
  }
});

// ---- the case that happened ------------------------------------------------

test("the database in %TEMP% does not read as Running in an ok tone", () => {
  const summary = summaryFor({warehousePath: THE_INCIDENT});
  assert.notEqual(summary.text, "Running");
  assert.notEqual(summary.tone, "ok");
  assert.equal(summary.tone, "danger");
});

test("it says the data is not his, names the folder, and prints the path", () => {
  const summary = summaryFor({warehousePath: THE_INCIDENT});
  assert.equal(summary.text, "Temporary database");
  assert.match(summary.detail, /^Not your data\./);
  // THE OUTERMOST temporary folder is the one named: `Temp` is what makes
  // everything beneath it disposable, and the full path below carries
  // `scrapex-tests-7k2f9a` for anyone who wants the rest.
  assert.ok(summary.detail.includes("«Temp»"), summary.detail);
  // IN FULL, NOT SHORTENED. The failure was that he could not tell which file he
  // was on; abbreviating the sentence written to tell him would repeat it.
  assert.ok(summary.detail.includes(THE_INCIDENT), summary.detail);
  assert.ok(!summary.detail.includes("…"), summary.detail);
});

test("the badge text stays inside the length the row is known to hold", () => {
  // `.badge` is `white-space: nowrap` with no ellipsis (extension/
  // components.css), and the row already carries an icon tile, a version chip
  // and a chevron. Measured in the harness at a 360px panel: "Temporary
  // database" renders 138px wide and neither the badge nor the row overflows.
  // "Installed, not running" is the longest word this badge has ever shown, so
  // it is the ceiling a new one may not pass — a character count rather than a
  // pixel one, because this suite runs without a browser.
  assert.ok(summaryFor({warehousePath: THE_INCIDENT}).text.length
              <= "Installed, not running".length,
            summaryFor({warehousePath: THE_INCIDENT}).text);
});

test("every shape a temporary warehouse arrives in is caught", () => {
  const caught = {
    // The Windows per-user temp folder, which is what `%TEMP%` expands to.
    "C:\\Users\\sapac\\AppData\\Local\\Temp\\scrapex-engine.db": "Temp",
    // The machine-wide one, for an engine running as a service.
    "C:\\Windows\\Temp\\scrapex-engine.db": "Temp",
    // POSIX, for CI and for anyone running the engine on Linux.
    "/tmp/scrapex/scrapex-engine.db": "tmp",
    // TMPDIR MOVED SOMEWHERE NOT CALLED TEMP, which is how the same incident
    // would go unnoticed a second time. These two prefixes are what still
    // catches it: `tests/conftest.py` names its root `scrapex-tests-<random>`,
    // and pytest's `tmp_path` lives under `pytest-of-<user>`.
    "D:\\scratch\\scrapex-tests-7k2f9a\\scrapex-engine.db": "scrapex-tests-7k2f9a",
    "D:\\scratch\\pytest-of-sapac\\pytest-131\\scrapex-engine.db": "pytest-of-sapac",
  };
  for (const [path, folder] of Object.entries(caught)) {
    const summary = summaryFor({warehousePath: path});
    assert.equal(summary.tone, "danger", `${path} passed as an ordinary warehouse`);
    assert.ok(summary.detail.includes(`«${folder}»`),
              `${path} was refused without naming ${folder}: ${summary.detail}`);
  }
});

test("a legitimate path is never refused, which is the harder half", () => {
  // A BANNER THAT CRIES WOLF IS WORSE THAN NO BANNER, because it teaches him to
  // read past the one line in this panel that has to be believed. Every entry
  // here is a path that contains the letters of a temporary folder and is not
  // one.
  const legitimate = [
    HIS,
    // Substring matches, all of which a `path.includes("temp")` rule would have
    // refused: the word inside a longer folder name.
    "C:\\Users\\Owner\\Documents\\Templates\\scrapex-engine.db",
    "C:\\Users\\Contemporary\\.scrapex\\scrapex-engine.db",
    "C:\\Users\\Owner\\tempur-shop\\scrapex-engine.db",
    "C:\\Users\\Owner\\temp-archive\\scrapex-engine.db",
    // A FILE MAY BE CALLED ANYTHING, and the rule asks whether the database is
    // in a temporary PLACE — an answer taken from the file's own name is an
    // answer to a different question. The engine can be started against an
    // explicit database path, so `s.path` ends in whatever was chosen, and
    // SQLite files routinely carry no extension at all.
    "C:\\Users\\Owner\\.scrapex\\tmp.db",
    "C:\\Users\\Owner\\.scrapex\\tmp",
    "C:\\Users\\Owner\\.scrapex\\scrapex-tests-7k2f9a.db",
    // The harness's own minimal stub (tools/panel_harness.py), which has a drive
    // letter and a file and no folder between them.
    "C:/db.sqlite",
    // A folder that merely starts with one of the prefixes' first letters.
    "D:\\scratch\\pytest-results\\scrapex-engine.db",
  ];
  for (const path of legitimate) {
    const summary = summaryFor({warehousePath: path});
    assert.equal(summary.tone, "ok", `${path} was refused: ${summary.detail}`);
    assert.equal(summary.text, "Running", path);
  }
});

// ---- the branches that are not about the warehouse -------------------------

test("no other status branch is changed by a warehouse being known", () => {
  // Each of these four is asserted by name in tests/test_panel_dom.py. A path in
  // `state` must not leak into a card about an engine that is not running, where
  // it would describe a file nothing has open.
  const cases = [
    [{engineState: "checking"}, "Checking engine…", "neutral"],
    [{engineState: "ready", protocolMismatch: true, engineProtocol: 99},
     "Incompatible", "danger"],
    [{engineState: "timeout", engineUp: false}, "Check timed out", "warn"],
    [{engineState: "stopped", engineUp: false}, "Installed, not running", "warn"],
    [{engineState: "unavailable", engineUp: false, engineVersion: "",
      engineReachable: false}, "Not detected", "neutral"],
  ];
  for (const [over, text, tone] of cases) {
    const summary = summaryFor(Object.assign({warehousePath: THE_INCIDENT}, over));
    assert.equal(summary.text, text);
    assert.equal(summary.tone, tone);
    // NOT `includes("harvest.db")`, which is what this said first and could
    // never fail: THE_INCIDENT carries no such file name, so the assertion held
    // for every branch whatever the code did. What it means is that a branch
    // which is not running describes no warehouse -- so look for the things a
    // warehouse description is actually made of.
    for (const trace of [THE_INCIDENT, "Database:", "Temporary", "Not your data"]) {
      assert.ok(!summary.detail.includes(trace),
                `${text} is describing a warehouse (${trace}): ${summary.detail}`);
    }
  }
});

test("every branch returns the three keys both screens write", () => {
  // `updateEngineStatus` reads `text`, `tone` and `detail` off one object and
  // writes them to four elements. A branch returning `undefined` for `detail`
  // would print the word "undefined" into the row.
  const branches = [
    {}, {warehousePath: HIS}, {warehousePath: THE_INCIDENT},
    {engineState: "checking"}, {engineState: "timeout", engineUp: false},
    {engineState: "stopped", engineUp: false},
    {engineState: "unavailable", engineUp: false, engineVersion: "",
     engineReachable: false},
    {protocolMismatch: true, engineProtocol: 99},
  ];
  for (const over of branches) {
    const summary = summaryFor(over);
    assert.equal(typeof summary.text, "string", JSON.stringify(over));
    assert.equal(typeof summary.detail, "string", JSON.stringify(over));
    assert.ok(["ok", "warn", "danger", "neutral"].includes(summary.tone),
              `${summary.tone} is not a tone the panel renders`);
  }
});

// ---- where the path is fetched, which the object above cannot show ----------

test("the path is read from GET /api/storage, and only once", () => {
  // `/api/health` is what the panel polls, and its own comment refuses to carry
  // the path: it "would otherwise be re-sent every few seconds to answer a
  // question whose answer only changes when the engine restarts". These are
  // source-text assertions because the constraint is about WHEN a request
  // happens, which the returned object cannot show.
  const ask = extract("askWhichWarehouse",
                      /^async function askWhichWarehouse\(\) \{[\s\S]*?\n\}/m);
  assert.ok(ask.includes('api("/api/storage")'),
            "the path is being read from somewhere other than GET /api/storage");
  assert.ok(/if \(warehouseAsk\) return warehouseAsk;/.test(ask),
            "the once-per-engine guard is gone, so every draw refetches");
  // A REPLY THAT OUTLIVED ITS QUESTION MUST NOT PAINT. Dropping the held path
  // does not cancel a request already out, so the previous engine's answer can
  // still arrive — and a late answer is indistinguishable from a right one
  // unless the question it answered was numbered. Pinned as text because the
  // race needs a second engine and a request in flight to reproduce, and a
  // guard nobody can run is a guard that quietly goes away.
  assert.ok(ask.includes("if (!current()) return;"),
            "a stale reply can repaint the status with the old engine's warehouse");
});

test("it is asked by the screen that shows it, never by the health answer", () => {
  // MEASURED, NOT CHOSEN. Asking from `setStatus` — the one place `state.engineUp`
  // is written, and the obvious hook — put `GET /api/storage` on the startup path
  // and turned `test_panel_startup.py` red by name:
  //
  //   test_profile_startup_handles_healthy_and_stopped_engines_without_run_data
  //   AssertionError: startup read destination data it does not need to paint
  //   the shell
  //
  // That rule is the owner's, narrowed once for the reattach rather than
  // abandoned, and `/api/storage` is in its forbidden list (tests/
  // test_panel_startup.py:22). So the request hangs off the destination that
  // draws the answer, which is what `showView` already does for Settings.
  const setStatus = extract("setStatus", /^function setStatus\(engine\) \{[\s\S]*?\n\}/m);
  assert.ok(!setStatus.includes("askWhichWarehouse"),
            "the warehouse is asked for from the health path, which startup takes");
  assert.ok(setStatus.includes("forgetWarehouse()"),
            "a stopped or replaced engine keeps the last engine's warehouse");

  const renderEngines = extract("renderEngines",
                                /^async function renderEngines\(\) \{[\s\S]*?\n\}/m);
  assert.ok(renderEngines.includes("askWhichWarehouse()"),
            "nothing asks which warehouse when the screen that names it is drawn");

  // And the status object itself asks the engine nothing — it is rendered from
  // `state` on every repaint, including the ones a poll causes.
  const summary = extract("engineStatusFromState",
                          /^function engineStatusFromState\(\) \{[\s\S]*?\n\}/m);
  assert.ok(!summary.includes("await") && !summary.includes("api("),
            "the status summary now makes a request, so every repaint pays for it");
});

// ---- the four lines that keep the named warehouse from going stale ---------
//
// EVERY TEST ABOVE THIS LINE PINS WHAT THE STATUS SAYS ABOUT A PATH ALREADY IN
// `state`; none of them pins how that path gets there, gets replaced, or gets
// dropped. Measured by mutation: `forgetWarehouse` can stop clearing
// `state.warehousePath`, `whenBackendChanges(forgetWarehouse)` can be deleted,
// the restart path can stop forgetting, and `loadDatabase` can stop feeding
// `noteWarehouse` — four separate edits, and the whole suite stayed green
// through every one of them. Each produces the SAME failure this line was built
// to end: a path stated confidently about a file nothing has open.

// `forgetWarehouse` and `noteWarehouse` are RUN rather than read, because what
// they do to `state` is the behaviour. `warehouseGeneration` and `warehouseAsk`
// are module-scope `let`s in app.js, so they are declared into the extracted
// scope here and handed back for inspection.
const lifecycle = (() => {
  const body = "let warehouseGeneration = 0;\nlet warehouseAsk = null;\n"
    + extract("forgetWarehouse", /^function forgetWarehouse\(\) \{[\s\S]*?\n\}/m)
    + "\n"
    + extract("noteWarehouse", /^function noteWarehouse\(storage\) \{[\s\S]*?\n\}/m)
    + "\nreturn { forgetWarehouse, noteWarehouse,"
    + " generation: () => warehouseGeneration,"
    + " held: () => warehouseAsk, hold: (v) => { warehouseAsk = v; } };";
  // eslint-disable-next-line no-new-func
  //
  // `repaintRuntime` JOINED THE TWO OF THEM when the Settings runtime grid began
  // reading `state.warehousePath` as well. It is declared here ONLY so these
  // extractions still run: the bodies call it, and without the parameter
  // `new Function` would throw `ReferenceError` on the first test. It is a
  // no-op, and this file asserts NOTHING about it.
  //
  // WHICH MEANS THIS FILE DOES NOT GUARD THE REPAINT, and an earlier draft of
  // this comment claimed it did — that the day either function stopped calling
  // `repaintRuntime` these extractions would fail loudly. Measured, because a
  // guard asserted in prose is the one kind nobody re-runs: with BOTH
  // `repaintRuntime()` calls deleted from `noteWarehouse` and `forgetWarehouse`
  // in app.js, this file reported 18 tests, 18 pass, 0 fail — byte-identical
  // green. `extension/tests/healthy.test.mjs` is what goes red there (2 of its
  // 21), and it is the only thing that does.
  const make = new Function("state", "renderEngineStatusUI", "repaintRuntime", body);
  return (state, repaints) => make(state, () => { repaints.n += 1; }, () => {});
})();

test("forgetting the warehouse empties the path, the ask and the generation", () => {
  // `setStatus` calls this on a stopped engine AND on one that has just come
  // back, and the second is the dangerous half: the successor may be open on a
  // different file, so the predecessor's path must not survive the gap before
  // the new answer lands. A `forgetWarehouse` that moves the generation but
  // leaves the path is a no-op wearing the right name.
  const state = {warehousePath: HIS};
  const repaints = {n: 0};
  const it = lifecycle(state, repaints);
  it.hold(Promise.resolve());
  const before = it.generation();
  it.forgetWarehouse();
  assert.equal(state.warehousePath, "",
               "the previous engine's warehouse is still being stated");
  assert.equal(it.held(), null,
               "the next draw hands back the old engine's in-flight answer");
  assert.ok(it.generation() > before,
            "a reply already in flight cannot be told from a current one");
});

test("noting a warehouse stores the path, and repaints only when it moved", () => {
  const state = {warehousePath: ""};
  const repaints = {n: 0};
  const it = lifecycle(state, repaints);

  it.noteWarehouse({path: HIS});
  assert.equal(state.warehousePath, HIS);
  assert.equal(repaints.n, 1);

  // `loadDatabase` runs on every visit to the Database page. Repainting the
  // status row on each of them would be work for nothing.
  it.noteWarehouse({path: HIS});
  assert.equal(repaints.n, 1, "an unchanged path repaints the status anyway");

  // A RESTORE PUTS A DIFFERENT FILE WHERE THE ENGINE IS LOOKING, and this read
  // is what catches it — off a request the Database page already makes.
  it.noteWarehouse({path: "D:\\Backups\\.scrapex\\scrapex-engine.db"});
  assert.equal(state.warehousePath, "D:\\Backups\\.scrapex\\scrapex-engine.db");
  assert.equal(repaints.n, 2);

  // A body with no path is "the panel cannot say", which is the empty detail —
  // never the last path it happened to know.
  for (const empty of [{}, {path: ""}, {path: null}, null, undefined]) {
    it.noteWarehouse(empty);
    assert.equal(state.warehousePath, "",
                 `${JSON.stringify(empty)} left a warehouse named`);
  }
});

test("the three places a warehouse can change under a panel already open", () => {
  // SOURCE TEXT, because each is a wiring fact: reproducing them needs a second
  // engine, a backend switch, or a live restart, and a guard nobody can run is a
  // guard that quietly goes away. All three were unpinned, and all three
  // survived deletion with the suite green.

  // 1. A DIFFERENT BACKEND IS A DIFFERENT MACHINE. Without this the old path
  //    goes on being stated under the new engine's status.
  assert.match(SOURCE, /^whenBackendChanges\(forgetWarehouse\);$/m,
               "a backend switch keeps the previous machine's warehouse");

  // 2. THE PANEL'S OWN RESTART, which `setStatus` never sees: that wait polls
  //    `/api/health` directly, so the engine goes down and comes back without a
  //    health answer ever passing through the one place that forgets.
  assert.match(
    SOURCE,
    /say\("The engine is back\."\);[\s\S]{0,600}?forgetWarehouse\(\);\s*\n\s*await render\(\);/,
    "a restart repaints the status with the warehouse its predecessor had");

  // 3. RESTORE AND ADOPT-BUNDLE, the two panel actions that put a different file
  //    where the engine is looking. Both re-read `GET /api/storage` through
  //    `loadDatabase`, so the status line refreshes off a request already made.
  const loadDatabase = extract("loadDatabase",
                               /^async function loadDatabase\(\) \{[\s\S]*?\n\}/m);
  assert.ok(loadDatabase.includes("noteWarehouse(s)"),
            "a restored database is not picked up by the line that names it");
});
