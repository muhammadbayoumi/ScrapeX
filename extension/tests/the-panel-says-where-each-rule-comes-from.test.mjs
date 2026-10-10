// The source editor says where each crawl rule comes from, and saves his choices as
// numbers, to the warehouse (#1584, PR 3).
//
// His rulings: one system -- general rules on the Settings page, overridden per
// source; clearing a choice returns the field to what the source ships with; and the
// panel shows each value's origin: "From the source" (its sources.yaml entry or its
// directory), "Your general rule" or "Your choice". GET /api/sources/{key}/rules
// answers all three; this holds the panel's reading of it.
//
// READ AS SOURCE TEXT, like `the-robots-look-says-the-crawl-pauses.test.mjs`:
// `extension/app.js` exports nothing and touches `chrome.*` at module scope, so the
// functions are lifted out by name and evaluated in a `vm` context holding only what
// they read. Every lift is asserted, so a rename fails here loudly.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";
import { sourceMatches } from "../jobsview.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");
const HTML = readFileSync(join(HERE, "..", "app.html"), "utf8");

function lift(pattern, name) {
  const found = SOURCE.match(pattern);
  assert.ok(found, `${name} is no longer where this guard reads it from in app.js`);
  return found[0];
}
const fn = (name) => lift(new RegExp(`^(async )?function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`, "m"), name);
const constant = (name) => lift(new RegExp(`^const ${name} = \\{[\\s\\S]*?\\};`, "m"), name);

const PURE = [constant("RULE_ORIGINS"), constant("RULE_IDS"), constant("ROBOTS_WORDS"),
              fn("ruleNumber"), fn("ruleValueText"), fn("ruleGeneralText"),
              fn("ruleShipsOpinion"), fn("ruleOrigin"), fn("ruleChanges"),
              fn("sourceRulesForm"), fn("renderRuleField"), fn("holdRuleControls"),
              fn("renderSourceRules")].join("\n");

function load(context, extra = "", names = "ruleOrigin, ruleChanges") {
  return vm.runInNewContext(`${PURE}\n${extra}\n({${names}});`, context);
}

const GENERAL = {user_agent: "Mozilla/5.0 (Panel) Chrome/141", crawl_pace_s: 1.0,
                 obey_disallow: false};

// A price source that ships `obey` and a 3 s pace, no agent of its own.
function answer(overrides = {}) {
  return {
    source_key: "SHOP", kind: "price", general: GENERAL,
    agent_sent: GENERAL.user_agent,
    fields: {
      active: {value: false, shipped: false, origin: "source"},
      robots: {value: "obey", custom: null, shipped: "obey", shipped_custom: null,
               origin: "source"},
      user_agent: {value: null, shipped: null, origin: "general"},
      crawl_pace_s: {value: 3.0, shipped: 3.0, origin: "source"},
      ...overrides,
    },
  };
}

// ---- the sentence under each field ---------------------------------------------

test("a value the source ships says so, with the value", () => {
  const {ruleOrigin} = load({});
  assert.equal(ruleOrigin("robots", answer()),
               "From the source: obey this site's robots.txt.");
  assert.equal(ruleOrigin("crawl_pace_s", answer()),
               "From the source: 3 s between requests.");
});

test("a field the source is silent on follows his general rule, named with its value", () => {
  const {ruleOrigin} = load({});
  assert.equal(ruleOrigin("user_agent", answer()),
               `Your general rule (Settings): ${GENERAL.user_agent}.`);
});

test("his choice says what clearing it returns to: the source's value", () => {
  const {ruleOrigin} = load({});
  const chosen = answer({robots: {value: "default", custom: null, shipped: "obey",
                                  shipped_custom: null, origin: "choice"}});
  assert.equal(ruleOrigin("robots", chosen),
               "Your choice. Clearing it returns to the source's: obey this site's "
               + "robots.txt.");
});

test("his choice on a field the source is silent on returns to the general rule", () => {
  const {ruleOrigin} = load({});
  const chosen = answer({user_agent: {value: "HisAgent/2.0", shipped: null,
                                      origin: "choice"}});
  assert.equal(ruleOrigin("user_agent", chosen),
               "Your choice. Clearing it returns to your general rule (Settings): "
               + `${GENERAL.user_agent}.`);
});

test("the general robots rule is said as the Settings page has it", () => {
  const {ruleOrigin} = load({});
  const silent = answer({robots: {value: "default", custom: null, shipped: "default",
                                  shipped_custom: null, origin: "general"}});
  assert.match(ruleOrigin("robots", silent), /crawled and the run says so/);
  silent.general = {...GENERAL, obey_disallow: true};
  assert.match(ruleOrigin("robots", silent), /are not fetched/);
});

// ---- only what changed, and numbers as numbers --------------------------------

const untouched = (a) => ({
  active: a.kind === "price" ? a.fields.active.value : null,
  robots: a.fields.robots.value, enforce: false, delay: "",
  agent: a.fields.user_agent.origin === "general" ? "" : String(a.fields.user_agent.value ?? ""),
  pace: a.fields.crawl_pace_s.origin === "general" ? "" : String(a.fields.crawl_pace_s.value ?? ""),
});

test("a save that touched nothing sends nothing", () => {
  const {ruleChanges} = load({});
  assert.deepEqual({...ruleChanges(answer(), untouched(answer()))}, {});
});

test("a pace is sent as a number, not the text the field holds", () => {
  const {ruleChanges} = load({});
  const changes = ruleChanges(answer(), {...untouched(answer()), pace: "7.5"});
  assert.equal(typeof changes.crawl_pace_s, "number");
  assert.deepEqual({...changes}, {crawl_pace_s: 7.5});
});

test("a custom delay is sent as a number inside the rule", () => {
  const {ruleChanges} = load({});
  const changes = ruleChanges(answer(), {...untouched(answer()), robots: "custom",
                                         enforce: true, delay: "2"});
  assert.equal(changes.robots, "custom");
  assert.equal(typeof changes.robots_custom.crawl_delay_s, "number");
  assert.deepEqual({...changes.robots_custom}, {enforce_disallow: true, crawl_delay_s: 2});
});

test("what is not a number is sent as typed, never as null (which would clear)", () => {
  const {ruleChanges} = load({});
  const changes = ruleChanges(answer(), {...untouched(answer()), pace: "fast"});
  assert.equal(changes.crawl_pace_s, "fast");
});

test("emptying his chosen agent clears it; an empty field following a rule sends nothing", () => {
  const {ruleChanges} = load({});
  const chosen = answer({user_agent: {value: "HisAgent/2.0", shipped: null,
                                      origin: "choice"}});
  assert.deepEqual({...ruleChanges(chosen, {...untouched(chosen), agent: ""})},
                   {user_agent: null});
  assert.deepEqual({...ruleChanges(answer(), {...untouched(answer()), agent: ""})}, {});
});

test("a directory never sends `active`: no switch is drawn for it", () => {
  const {ruleChanges} = load({});
  const directory = {...answer(), kind: "directory"};
  assert.ok(!("active" in ruleChanges(directory, {...untouched(directory), active: null})));
});

test("leaving custom sends the new choice and no rule", () => {
  const {ruleChanges} = load({});
  const custom = answer({robots: {value: "custom", origin: "choice", shipped: "obey",
                                  shipped_custom: null,
                                  custom: {enforce_disallow: true, crawl_delay_s: 4}}});
  const changes = ruleChanges(custom, {...untouched(custom), robots: "obey"});
  assert.deepEqual({...changes}, {robots: "obey"});
});

// ---- drawing the answer ---------------------------------------------------------

function fakeDom() {
  const nodes = {};
  const focused = [];
  const node = (id) => (nodes[id] ??= {id, value: "", checked: false, placeholder: "",
                                       textContent: "", hidden: true, disabled: false,
                                       focus: () => focused.push(id)});
  const clears = Object.fromEntries(["active", "robots", "user_agent", "crawl_pace_s"]
    .map((field) => [field, {hidden: true}]));
  const document = {
    querySelector: (selector) => clears[selector.match(/data-clear-rule="([^"]+)"/)[1]],
  };
  return {nodes, node, clears, document, focused};
}

test("the answer is drawn with each sentence, and Clear only beside his choices", () => {
  const dom = fakeDom();
  const drawnRobots = [];
  const context = {$: dom.node, document: dom.document, state: {sources: []},
                   renderRobotsChoice: (source) => drawnRobots.push(source)};
  const {renderSourceRules} = load(context, "", "renderSourceRules");
  const chosen = answer({crawl_pace_s: {value: 9, shipped: 3.0, origin: "choice"}});

  renderSourceRules(chosen);

  assert.equal(context.state.sourceRules, chosen);
  assert.equal(dom.nodes["source-edit-pace"].value, "9");
  assert.equal(dom.nodes["source-edit-agent"].value, "", "a general agent is a placeholder");
  assert.equal(dom.nodes["source-edit-agent"].placeholder, GENERAL.user_agent);
  assert.match(dom.nodes["source-edit-pace-origin"].textContent, /^Your choice\./);
  assert.match(dom.nodes["source-edit-robots-origin"].textContent, /^From the source/);
  assert.match(dom.nodes["source-edit-agent-origin"].textContent, /^Your general rule/);
  assert.equal(dom.clears.crawl_pace_s.hidden, false);
  assert.equal(dom.clears.robots.hidden, true);
  assert.deepEqual({...drawnRobots[0]}, {robots: "obey", robots_custom: null});
  for (const id of ["robots", "robots-enforce", "robots-delay", "agent", "pace"]) {
    assert.equal(dom.nodes[`source-edit-${id}`].disabled, false, `${id} is still held`);
  }
});

test("the controls the answer fills are held until it arrives, then let go", () => {
  const dom = fakeDom();
  const context = {$: dom.node, document: dom.document, renderRobotsChoice: () => {},
                   state: {sources: [{source_key: "SHOP", implemented: true}],
                           editingSourceKey: "SHOP"}};
  const {holdRuleControls} = load(context, "", "holdRuleControls");

  holdRuleControls(true);
  for (const id of ["active", "robots", "robots-enforce", "robots-delay", "agent", "pace"]) {
    assert.equal(dom.nodes[`source-edit-${id}`].disabled, true, `${id} was not held`);
  }
  holdRuleControls(false);
  assert.equal(dom.nodes["source-edit-active"].disabled, false);
  context.state.sources[0].implemented = false;
  holdRuleControls(false);
  assert.equal(dom.nodes["source-edit-active"].disabled, true,
               "the switch of a source with no working connector was let go");
});

// ---- Clear: one field, its body null, focus kept on it ------------------------------

function clearer(field, cleared) {
  const dom = fakeDom();
  const posts = [];
  const said = [];
  const drawn = {sites: 0};
  const source = {source_key: "SHOP", active: true, implemented: true};
  const context = {
    $: dom.node, document: dom.document, icon: () => "", esc: (v) => String(v),
    out: (id, html) => said.push(html), renderRobotsChoice: () => {},
    renderSites: () => { drawn.sites += 1; }, renderSourceManager: () => {},
    state: {sources: [source], editingSourceKey: "SHOP", editingRulesKey: "SHOP",
            sourceRules: answer()},
    post: async (url, body) => { posts.push([url, body]); return cleared; },
  };
  const {clearSourceRule} = load(context, fn("clearSourceRule"), "clearSourceRule");
  return {clearSourceRule, dom, posts, said, drawn, source, context};
}

for (const [field, id] of [["active", "active"], ["robots", "robots"],
                           ["user_agent", "agent"], ["crawl_pace_s", "pace"]]) {
  test(`clearing ${field} sends {${field}: null}, redraws only it, and keeps focus there`,
       async () => {
    const cleared = answer();
    const {clearSourceRule, dom, posts} = clearer(field, cleared);
    // What he is typing elsewhere, unsaved: a Clear must not take it.
    const others = {active: "source-edit-active", user_agent: "source-edit-agent",
                    crawl_pace_s: "source-edit-pace"};
    for (const [other, input] of Object.entries(others)) {
      if (other !== field) dom.node(input).value = "typing";
    }

    await clearSourceRule(field);

    assert.deepEqual(posts.map(([url, body]) => [url, {...body}]),
                     [["/api/sources/SHOP/rules", {[field]: null}]]);
    assert.deepEqual(dom.focused, [`source-edit-${id}`]);
    for (const [other, input] of Object.entries(others)) {
      if (other !== field) assert.equal(dom.nodes[input].value, "typing", `${other} was redrawn`);
    }
    assert.match(dom.nodes[`source-edit-${id}-origin`].textContent,
                 /^(From the source|Your general rule)/);
  });
}

test("clearing the switch puts the source's value on its card, and the lists are redrawn", async () => {
  const cleared = answer();             // ships off
  const {clearSourceRule, source, drawn} = clearer("active", cleared);

  await clearSourceRule("active");

  assert.equal(source.active, false);
  assert.equal(drawn.sites, 1);
});

// ---- saving: the manifest's fields to /edit, his choices to /rules ------------------

function saver(answerNow, source, form, {legacy = false, refuse = null, reread = null,
                                          reply = answerNow, mode = null,
                                          modeNow = null} = {}) {
  const opened = mode || (legacy ? "legacy" : "rules");
  const posts = [];
  const said = [];
  const drawn = {sites: 0, editor: 0, reread: 0};
  const dom = fakeDom();
  Object.assign(dom.node("source-edit-name"), {value: source.source_name ?? ""});
  for (const [id, value] of Object.entries(form)) Object.assign(dom.node(id), value);
  const context = {
    $: dom.node, document: dom.document, icon: () => "", esc: (v) => String(v),
    out: (id, html) => said.push(html), renderSites: () => { drawn.sites += 1; },
    renderSourceManager: () => {}, renderRobotsChoice: () => {},
    renderSourceEditor: () => { drawn.editor += 1; },
    sourceRulesMode: () => modeNow || opened,
    scheduleSwitchOn: () => false,       // an engine whose editor still saves `active`
    capabilityRefusal: () => (opened === "rules" ? "" : "REFUSAL SENTENCE"),
    loadSourceRules: async () => { drawn.reread += 1; return reread; },
    state: {sources: [source], editingSourceKey: source.source_key,
            editingRulesKey: source.site_key || source.source_key, sourceRules: answerNow,
            sourceRulesMode: opened},
    post: async (url, body) => {
      posts.push([url, body]);
      if (refuse && url.endsWith(refuse)) throw new Error("a crawl is currently writing");
      return reply;
    },
  };
  const {saveSourceEditor} = load(context, fn("saveSourceEditor"), "saveSourceEditor");
  return {saveSourceEditor, posts, said, drawn, source};
}

test("a price source's crawl rules go to /rules as numbers, never to /edit", async () => {
  const source = {source_key: "SHOP", source_name: "Shop", fold_variants: false};
  const {saveSourceEditor, posts} = saver(answer(), source, {
    "source-edit-robots": {value: "custom"}, "source-edit-robots-enforce": {checked: true},
    "source-edit-robots-delay": {value: "2"}, "source-edit-pace": {value: "3"},
    "source-edit-name": {value: "Shop"}, "source-edit-cadence": {value: ""},
    "source-edit-vat": {value: ""},
  });

  await saveSourceEditor();

  const toEdit = posts.filter(([url]) => url.endsWith("/edit"));
  for (const [, body] of toEdit) {
    for (const field of ["robots", "robots_custom", "user_agent", "crawl_pace_s", "active"]) {
      assert.ok(!(field in body), `${field} was sent to /edit`);
    }
  }
  const [url, body] = posts.find(([u]) => u.endsWith("/rules"));
  assert.equal(url, "/api/sources/SHOP/rules");
  assert.deepEqual({...body.robots_custom}, {enforce_disallow: true, crawl_delay_s: 2});
  assert.ok(!("crawl_pace_s" in body), "an unchanged 3 s pace was sent again");
});

test("a directory card saves its site's rules and nothing to the manifest", async () => {
  const directory = {...answer(), kind: "directory", source_key: "muqawil_org",
                     fields: {...answer().fields,
                              robots: {value: "default", custom: null, shipped: "default",
                                       shipped_custom: null, origin: "general"},
                              crawl_pace_s: {value: null, shipped: null, origin: "general"}}};
  const card = {source_key: "contractors", site_key: "muqawil_org", kind: "dataset"};
  const {saveSourceEditor, posts} = saver(directory, card, {
    "source-edit-robots": {value: "obey"}, "source-edit-pace": {value: "5"},
  });

  await saveSourceEditor();

  assert.deepEqual(posts.map(([url]) => url), ["/api/sources/muqawil_org/rules"]);
  assert.deepEqual({...posts[0][1]}, {robots: "obey", crawl_pace_s: 5});
});

// ---- the markup the functions draw into ---------------------------------------------

test("every field has its origin line and its Clear button, and the pace is a number box", () => {
  for (const id of ["active", "robots", "agent", "pace"]) {
    assert.match(HTML, new RegExp(`id="source-edit-${id}-origin"`), id);
  }
  for (const field of ["active", "robots", "user_agent", "crawl_pace_s"]) {
    assert.match(HTML, new RegExp(`data-clear-rule="${field}"`), field);
  }
  assert.match(HTML, /<input id="source-edit-pace" type="number" min="0\.1" step="0\.1"/,
               "the pace steps as the Settings page's general pace does");
});

test("each Clear is named with its field, and the two seconds boxes are told apart", () => {
  const names = [...HTML.matchAll(/data-clear-rule="([^"]+)"\s+aria-label="([^"]+)"/g)];
  assert.deepEqual(names.map(([, field]) => field).sort(),
                   ["active", "crawl_pace_s", "robots", "user_agent"]);
  assert.equal(new Set(names.map(([, , label]) => label)).size, 4, "two Clears share a name");
  const label = (id) => HTML.match(new RegExp(`<label for="${id}">([^<]+)</label>`))[1];
  assert.notEqual(label("source-edit-robots-delay"), label("source-edit-pace"));
});

test("Save sits below the last card it saves, and the Automation card is a price card's", () => {
  const fetchCard = HTML.indexOf('aria-labelledby="source-edit-fetch-heading"');
  const save = HTML.indexOf('id="source-edit-save"');
  assert.ok(fetchCard > 0 && save > fetchCard, "Save is above a card it saves");
  assert.match(HTML, /aria-labelledby="source-edit-automation-heading"\s+data-price-only/);
});

test("the price-only parts of the editor are marked, so a directory card hides them", () => {
  const marked = HTML.match(/data-price-only/g) || [];
  assert.ok(marked.length >= 5, `only ${marked.length} parts are marked price-only`);
  assert.match(HTML, /aria-labelledby="source-edit-danger-heading" data-price-only/);
  assert.match(HTML, /aria-labelledby="source-edit-key-heading" data-price-only/);
  assert.match(fn("renderSourceEditor"), /\[data-price-only\][\s\S]*node\.hidden = !price/);
});


// What the save compares against: a price card whose details the form holds unchanged.
const UNCHANGED = {source_name: "Shop", source_name_ar: "", base_url: "", currency: "",
                   cadence: "", vat_mode: "", fold_variants: false};

test("saving the switch puts the engine's answer on the source's card, and redraws the lists",
     async () => {
  const source = {source_key: "SHOP", ...UNCHANGED, active: false};
  const {saveSourceEditor, posts, drawn} = saver(answer(), source, {
    "source-edit-active": {checked: true}, "source-edit-pace": {value: "3"},
    "source-edit-robots": {value: "obey"},
  }, {reply: answer({active: {value: true, shipped: false, origin: "choice"}})});

  await saveSourceEditor();

  assert.deepEqual(posts.map(([url, body]) => [url, {...body}]),
                   [["/api/sources/SHOP/rules", {active: true}]]);
  assert.equal(source.active, true, "the Auto chip still reads the old value");
  assert.equal(drawn.sites, 1);
});

// ---- half saved is said as half --------------------------------------------------------

test("a rename saved before his choices were refused says so, and redraws the lists",
     async () => {
  const source = {source_key: "SHOP", source_name: "Shop"};
  const {saveSourceEditor, posts, said, drawn} = saver(answer(), source, {
    "source-edit-name": {value: "Renamed"}, "source-edit-pace": {value: "9"},
  }, {refuse: "/rules"});

  await saveSourceEditor();

  assert.deepEqual(posts.map(([url]) => url),
                   ["/api/sources/SHOP/edit", "/api/sources/SHOP/rules"]);
  assert.match(said.at(-1), /The name and details were saved; your crawl choices were not: a crawl/);
  assert.equal(source.source_name, "Renamed");
  assert.equal(drawn.sites, 1, "the lists kept the old name");
});

// ---- the rules could not be read: the details still save, and Save reads again ------

test("unread rules do not stop the name saving, and Save reads them again", async () => {
  const source = {source_key: "SHOP", source_name: "Shop"};
  const {saveSourceEditor, posts, said, drawn} = saver(null, source, {
    "source-edit-name": {value: "Renamed"},
  });

  await saveSourceEditor();

  assert.deepEqual(posts.map(([url]) => url), ["/api/sources/SHOP/edit"]);
  assert.equal(drawn.reread, 1);
  assert.match(said.at(-1), /The name and details were saved\. How this source is crawled/);
  assert.equal(drawn.sites, 1);
});

test("rules read again on Save let the save finish", async () => {
  const source = {source_key: "SHOP", ...UNCHANGED};
  const {saveSourceEditor, posts, said, drawn} = saver(null, source, {
    "source-edit-pace": {value: "3"}, "source-edit-robots": {value: "obey"},
  }, {reread: answer()});

  await saveSourceEditor();

  assert.equal(drawn.reread, 1);
  assert.deepEqual(posts, [], "nothing changed, so nothing is sent");
  assert.match(said.at(-1), /Changes saved/);
});

// ---- an engine without /rules edits as the editor always did (§1.6, #1584) ----------

test("an engine without the rules routes saves the name and robots through /edit", async () => {
  const source = {source_key: "SHOP", source_name: "Shop", active: false, robots: "default",
                  robots_custom: null};
  const {saveSourceEditor, posts, said, drawn} = saver(null, source, {
    "source-edit-name": {value: "Renamed"}, "source-edit-robots": {value: "custom"},
    "source-edit-robots-enforce": {checked: true}, "source-edit-robots-delay": {value: "2"},
    "source-edit-active": {checked: true},
  }, {legacy: true});

  await saveSourceEditor();

  assert.deepEqual(posts.map(([url]) => url),
                   ["/api/sources/SHOP/edit", "/api/sources/SHOP/active"]);
  const edit = posts[0][1];
  assert.equal(edit.source_name, "Renamed");
  assert.equal(edit.robots, "custom");
  assert.deepEqual({...edit.robots_custom}, {enforce_disallow: true, crawl_delay_s: 2});
  assert.deepEqual({...posts[1][1]}, {active: true});
  assert.equal(source.active, true);
  assert.equal(drawn.reread, 0, "/rules was read from an engine that has none");
  assert.match(said.at(-1), /Changes saved/);
  assert.ok(!said.some((line) => /source_rules|Update the engine/.test(line)), said.join(" | "));
});

test("an engine without the rules routes is sent nothing when nothing changed", async () => {
  const source = {source_key: "SHOP", ...UNCHANGED, active: false, robots: "default",
                  robots_custom: null};
  const {saveSourceEditor, posts} = saver(null, source, {
    "source-edit-robots": {value: "default"},
  }, {legacy: true});

  await saveSourceEditor();

  assert.deepEqual(posts, []);
});

test("the editor asks once whether /rules exists, and reads it after emptying the result line",
     () => {
  const body = fn("renderSourceEditor");
  assert.match(body, /const mode = sourceRulesMode\(\);/);
  const emptied = body.lastIndexOf('out("source-edit-result", "")');
  const read = body.indexOf('if (mode === "rules") loadSourceRules(state.editingRulesKey)');
  assert.ok(emptied > 0 && read > emptied,
            "the rules are read before the result line is emptied, which wipes what they say");
  assert.match(body, /\[data-rules-only\][\s\S]*node\.hidden = legacy/);
});

// ---- old engine, or cannot tell: only a report that lacks the key is "old" ----------

function modeOf({refusal, report, status}) {
  const context = {capabilityRefusal: () => refusal, state: {versionReport: report,
                                                               versionStatus: status},
                   deployedFrom: (r) => (r && Array.isArray(r.capabilities)
                     ? Object.fromEntries(r.capabilities.map((c) => [c.key, c])) : null)};
  return vm.runInNewContext(`${fn("sourceRulesMode")}\nsourceRulesMode();`, context);
}
const WITH = {capabilities: [{key: "source_rules", since: "0.3.7"}]};
const WITHOUT = {capabilities: [{key: "crawl_parallel_sources", since: "0.3.0"}]};

test("an engine that deploys /rules gets the rules editor", () => {
  assert.equal(modeOf({refusal: "", report: WITH, status: "ready"}), "rules");
});

test("only an engine known to lack /rules gets the old editor", () => {
  assert.equal(modeOf({refusal: "not deployed", report: WITHOUT, status: "ready"}), "legacy");
  assert.equal(modeOf({refusal: "too old to say", report: null, status: "unsupported"}),
               "legacy", "an engine too old to report versions has no /rules either");
});

test("an engine that cannot be asked is refused, never guessed old", () => {
  for (const status of ["timeout", "unavailable", "pending"]) {
    assert.equal(modeOf({refusal: "cannot be confirmed", report: null, status}), "refused",
                 status);
  }
  // A new engine, and an extension older than the capability or of unknown version.
  assert.equal(modeOf({refusal: "needs extension 0.3.7", report: WITH, status: "ready"}),
               "refused");
});

test("an engine that cannot be asked saves the details only, and says why", async () => {
  const source = {source_key: "SHOP", source_name: "Shop", robots: "default"};
  const {saveSourceEditor, posts, said, drawn} = saver(null, source, {
    "source-edit-name": {value: "Renamed"}, "source-edit-robots": {value: "obey"},
  }, {mode: "refused"});

  await saveSourceEditor();

  assert.deepEqual(posts.map(([url]) => url), ["/api/sources/SHOP/edit"]);
  assert.ok(!("robots" in posts[0][1]), "robots went to an /edit that refuses it");
  assert.equal(drawn.reread, 0, "/rules was asked of an engine that cannot say it has it");
  assert.match(said.at(-1), /^The name and details were saved\. REFUSAL SENTENCE/);
});

for (const [opened, now] of [["rules", "legacy"], ["legacy", "rules"], ["rules", "refused"]]) {
  test(`an engine that went from ${opened} to ${now} while the editor was open is not written`,
       async () => {
    const source = {source_key: "SHOP", source_name: "Shop", active: false};
    const {saveSourceEditor, posts, said, drawn} = saver(answer(), source, {
      "source-edit-name": {value: "Renamed"}, "source-edit-pace": {value: "9"},
    }, {mode: opened, modeNow: now});

    await saveSourceEditor();

    assert.deepEqual(posts, []);
    assert.equal(drawn.editor, 1, "the editor was not redrawn for the engine now answering");
    assert.match(said.at(-1), /engine changed while this was open, so nothing was saved/);
  });
}

// ---- no automation switch for a dataset or directory card (his ruling, 2026-10-09) ---

function managerCards(sources, {switchOn = false, schedules = null} = {}) {
  const box = {innerHTML: "", querySelectorAll: () => []};
  const nodes = {"source-manager-list": box, "source-manager-count": {textContent: ""}};
  const context = {
    $: (id) => nodes[id], esc: (v) => String(v ?? ""), icon: () => "",
    state: {sources, sourceFilter: "", schedules},
    scheduleSwitchOn: () => switchOn,
    scheduleSummary: (s) => `Daily 09:00 for ${s.source_key}`,
    sourceIdentity: (s) => `<span>${s.source_key}</span>`,
    sourceDomain: () => "", openSourceEditor: () => {},
    sourceMatches,   // the Sources search's one rule, from jobsview.js
  };
  vm.runInNewContext(`${fn("renderSourceManager")}\nrenderSourceManager();`, context);
  return box.innerHTML.split("</article>");
}

test("a price card says its automation; a dataset or directory card says none", () => {
  const [price, dataset, directory] = managerCards([
    {source_key: "SHOP", implemented: true, active: true},
    {source_key: "contractors", site_key: "muqawil_org", kind: "dataset", implemented: true},
    {source_key: "oman_tenderboard", kind: "directory", implemented: true},
  ]);

  assert.match(price, /Automation on/);
  assert.doesNotMatch(dataset, /Automation/);
  assert.doesNotMatch(directory, /Automation/);
});

test("the run list draws the Auto switch for a price source only", () => {
  assert.match(fn("renderSites"),
               /const auto = ready && !s\.kind && scheduleSwitchOn\(\)[\s\S]*?: ready && !s\.kind \?/);
});

test("with the one switch a price card says its schedule; a dataset or directory none",
     () => {
  const sources = [
    {source_key: "SHOP", implemented: true, active: true},
    {source_key: "contractors", site_key: "muqawil_org", kind: "dataset", implemented: true},
  ];
  const [price, dataset] = managerCards(sources, {switchOn: true, schedules: new Map()});
  assert.match(price, /Daily 09:00 for SHOP/);
  assert.doesNotMatch(price, /Automation/);
  assert.doesNotMatch(dataset, /Daily/);
  // Schedules unread: nothing is drawn rather than a guess.
  const [unread] = managerCards(sources, {switchOn: true, schedules: null});
  assert.doesNotMatch(unread, /Daily|Automation/);
});
