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
              fn("sourceRulesForm"), fn("renderSourceRules")].join("\n");

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
               "Your choice. Clearing it returns to your general rule (settings): "
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
  const node = (id) => (nodes[id] ??= {id, value: "", checked: false, placeholder: "",
                                       textContent: "", hidden: true});
  const clears = Object.fromEntries(["active", "robots", "user_agent", "crawl_pace_s"]
    .map((field) => [field, {hidden: true}]));
  const document = {
    querySelector: (selector) => clears[selector.match(/data-clear-rule="([^"]+)"/)[1]],
  };
  return {nodes, node, clears, document};
}

test("the answer is drawn with each sentence, and Clear only beside his choices", () => {
  const dom = fakeDom();
  const drawnRobots = [];
  const context = {$: dom.node, document: dom.document, state: {},
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
});

// ---- saving: the manifest's fields to /edit, his choices to /rules ------------------

function saver(answerNow, source, form) {
  const posts = [];
  const dom = fakeDom();
  Object.assign(dom.node("source-edit-name"), {value: source.source_name ?? ""});
  for (const [id, value] of Object.entries(form)) Object.assign(dom.node(id), value);
  const context = {
    $: dom.node, document: dom.document, icon: () => "", esc: (v) => String(v),
    out: () => {}, renderSites: () => {}, renderSourceManager: () => {},
    renderRobotsChoice: () => {},
    state: {sources: [source], editingSourceKey: source.source_key,
            editingRulesKey: source.site_key || source.source_key, sourceRules: answerNow},
    post: async (url, body) => { posts.push([url, body]); return answerNow; },
  };
  const {saveSourceEditor} = load(context, fn("saveSourceEditor"), "saveSourceEditor");
  return {saveSourceEditor, posts};
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
  assert.match(HTML, /<input id="source-edit-pace" type="number"/);
});

test("the price-only parts of the editor are marked, so a directory card hides them", () => {
  const marked = HTML.match(/data-price-only/g) || [];
  assert.ok(marked.length >= 5, `only ${marked.length} parts are marked price-only`);
  assert.match(HTML, /aria-labelledby="source-edit-danger-heading" data-price-only/);
  assert.match(HTML, /aria-labelledby="source-edit-key-heading" data-price-only/);
  assert.match(fn("renderSourceEditor"), /\[data-price-only\][\s\S]*node\.hidden = !price/);
});
