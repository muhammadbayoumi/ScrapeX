// 6.RibbonControls — what the owner's users can click, and the blanks that
// silently make sure they cannot.

import test from "node:test";
import assert from "node:assert/strict";

import { checkRibbonControlRow, effectiveControlKey, effectiveActionClass,
  buildsAMenu, splitActionTag, rendersNowhere, controlSwitchedOff }
  from "../ribboncontrols-rules.js";

const ROW = {
  ITEM_KEY: "matExport", CONTROL_KEY: "mnuMaterial", REGION: "GLOBAL",
  PARENT_KEY: "", ORDER: "10", ACTION_CLASS: "Export", ACTION_TAG: "T_UNITS",
  MENU_LAYOUT: "", LABEL: "Export rates", ICON: "",
};
const VIEWS = [{VIEW_KEY: "RATES", ENTITY_KEY: "T_UNITS"},
               {VIEW_KEY: "ITEMS", ENTITY_KEY: "T_ITEMS"}];
const DEFINITIONS = [{ENTITY_KEY: "T_UNITS"}, {ENTITY_KEY: "T_ITEMS"}];

const check = (over = {}, others = []) =>
  checkRibbonControlRow({...ROW, ...over}, others, VIEWS, DEFINITIONS);
const on = (found, field) => found.filter((f) => f.field === field);

// ---- the Critical ----------------------------------------------------------

test("a control with no key is Critical and stops the row", () => {
  const found = check({ITEM_KEY: "", ACTION_CLASS: "Nonsense"});
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Critical");
});

// ---- the blank that renders nowhere ----------------------------------------

test("a blank CONTROL_KEY becomes a control that does not exist", () => {
  const found = on(check({CONTROL_KEY: ""}), "CONTROL_KEY");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /mnuDynamic/);
  assert.match(found[0].detail, /NOWHERE/);
  assert.ok(rendersNowhere(check({CONTROL_KEY: ""})));
});

test("mnuExport is NOT sheet-driven and must not be accepted", () => {
  const found = on(check({CONTROL_KEY: "mnuExport"}), "CONTROL_KEY");
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /built in code|not among them/i);
});

test("a real control key in the wrong case still matches", () => {
  assert.deepEqual(on(check({CONTROL_KEY: "MNUMATERIAL"}), "CONTROL_KEY"), []);
});

test("the two buttons are controls too, not just the menus", () => {
  for (const key of ["btnDiesel", "btnLiquidBitumen"]) {
    assert.deepEqual(on(check({CONTROL_KEY: key}), "CONTROL_KEY"), [],
      `${key} is wired with BindButton and was refused`);
  }
});

// ---- ACTION_CLASS ----------------------------------------------------------

test("the retired spellings the add-in's OWN comments still offer are named", () => {
  for (const [dead, live] of Object.entries(
      {ExportEntity: "Export", ExportService: "Export",
       DownloadService: "Download", OpenView: "ViewList"})) {
    const found = on(check({ACTION_CLASS: dead}), "ACTION_CLASS");
    assert.equal(found[0].severity, "Error", dead);
    assert.match(found[0].fix, new RegExp(live));
    assert.match(found[0].detail, /doc comments/i,
      "an author copying from the add-in's docs is not told why it is wrong");
  }
});

test("an unknown class is the button that throws when pressed", () => {
  const found = on(check({ACTION_CLASS: "ViewList x2"}), "ACTION_CLASS");
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /Unknown Action/);
});

test("all eight classes are accepted", () => {
  for (const name of ["Export", "Download", "Stream", "UpdateTable",
                      "Menu", "Library", "ExportTree", "ViewList"]) {
    const row = name === "Menu" ? {ACTION_CLASS: name, ACTION_TAG: ""}
                                : {ACTION_CLASS: name};
    assert.deepEqual(on(check(row), "ACTION_CLASS"), [], name);
  }
});

test("a blank ACTION_CLASS means Export, applied in two places", () => {
  assert.equal(effectiveActionClass({}), "Export");
  assert.deepEqual(on(check({ACTION_CLASS: ""}), "ACTION_CLASS"), []);
});

// ---- ACTION_TAG ------------------------------------------------------------

test("Menu must carry no tag and everything else must", () => {
  assert.equal(on(check({ACTION_CLASS: "Menu", ACTION_TAG: "T_UNITS"}),
                  "ACTION_TAG")[0].severity, "Warning");
  assert.equal(on(check({ACTION_TAG: ""}), "ACTION_TAG")[0].severity, "Error");
  assert.deepEqual(on(check({ACTION_CLASS: "Menu", ACTION_TAG: ""}),
                      "ACTION_TAG"), []);
});

test("a view key that misses exports the WHOLE table and says nothing", () => {
  const found = on(check({ACTION_TAG: "T_UNITS|GHOST"}), "ACTION_TAG");
  assert.equal(found[0].severity, "Error");
  assert.equal(found[0].code, "SILENT_DROP");
  assert.match(found[0].detail, /FULL table/);
});

test("a view of the WRONG entity is applied rather than refused", () => {
  const found = on(check({ACTION_TAG: "T_UNITS|ITEMS"}), "ACTION_TAG");
  assert.match(found[0].detail, /belongs to T_ITEMS/);
});

test("a real entity and view pair is silent", () => {
  assert.deepEqual(on(check({ACTION_TAG: "T_UNITS|RATES"}), "ACTION_TAG"), []);
});

test("splitActionTag takes one pipe at most, entity first", () => {
  assert.deepEqual(splitActionTag("T_UNITS"), {entity: "T_UNITS", view: ""});
  assert.deepEqual(splitActionTag("T_UNITS|RATES"),
                   {entity: "T_UNITS", view: "RATES"});
});

// ---- PARENT_KEY ------------------------------------------------------------

const PARENT = {ITEM_KEY: "matMenu", CONTROL_KEY: "mnuMaterial",
                ACTION_CLASS: "Menu", ACTION_TAG: ""};

test("a parent under a DIFFERENT control orphans the child in silence", () => {
  const found = on(check({PARENT_KEY: "matMenu"},
                         [{...PARENT, CONTROL_KEY: "mnuLabor"}]), "PARENT_KEY");
  assert.equal(found[0].severity, "Error");
  assert.equal(found[0].code, "SILENT_DROP");
});

test("a parent that is a leaf never enumerates its children", () => {
  const found = on(check({PARENT_KEY: "matMenu"},
                         [{...PARENT, ACTION_CLASS: "Export"}]), "PARENT_KEY");
  assert.match(found[0].detail, /never enumerated/);
});

test("self-parenting is the add-in's own Critical", () => {
  const found = on(check({PARENT_KEY: "matExport"}), "PARENT_KEY");
  assert.equal(found[0].severity, "Critical");
  assert.equal(found[0].code, "ERR_CIRCULAR");
});

test("a LONGER ring passes every check the add-in makes, and is caught here", () => {
  // A -> B -> A. RibbonControlEntity only refuses a row parented to ITSELF.
  const found = on(check({ITEM_KEY: "A", PARENT_KEY: "B"},
                         [{ITEM_KEY: "B", PARENT_KEY: "A",
                           CONTROL_KEY: "mnuMaterial", ACTION_CLASS: "Menu",
                           ACTION_TAG: ""}]), "PARENT_KEY");
  const ring = found.find((f) => f.code === "ERR_CIRCULAR");
  assert.ok(ring, "A -> B -> A was not detected");
  assert.match(ring.detail, /own ancestor/);
});

test("a good parent is silent", () => {
  assert.deepEqual(on(check({PARENT_KEY: "matMenu"}, [PARENT]), "PARENT_KEY"), []);
});

// ---- REGION, ORDER, MENU_LAYOUT, ICON --------------------------------------

test("a region token that is not two letters pollutes the dropdown", () => {
  const found = on(check({REGION: "EGY"}), "REGION");
  assert.equal(found[0].severity, "Warning");
  assert.match(found[0].detail, /dropdown/);
});

test("a comma-separated region list is accepted", () => {
  assert.deepEqual(on(check({REGION: "EG, SA"}), "REGION"), []);
});

test("a blank region is GLOBAL and the add-in warns rather than assume", () => {
  assert.equal(on(check({REGION: ""}), "REGION")[0].severity, "Warning");
});

test("ORDER that does not parse becomes zero and sorts to the front", () => {
  assert.match(on(check({ORDER: "ten"}), "ORDER")[0].detail, /becomes 0/);
  assert.equal(on(check({ORDER: "-5"}), "ORDER")[0].severity, "Warning");
  assert.deepEqual(on(check({ORDER: ""}), "ORDER"), []);
});

test("MENU_LAYOUT refuses NUMBERS even when they name a defined value", () => {
  const found = on(check({ACTION_CLASS: "Menu", ACTION_TAG: "",
                          MENU_LAYOUT: "2"}), "MENU_LAYOUT");
  assert.match(found[0].detail, /REFUSED/);
});

test("Tiles is a live spelling and is kept", () => {
  assert.deepEqual(on(check({ACTION_CLASS: "Menu", ACTION_TAG: "",
                             MENU_LAYOUT: "Tiles"}), "MENU_LAYOUT"), []);
});

test("a layout on a click row has no effect and says so", () => {
  const found = on(check({MENU_LAYOUT: "Grouped"}), "MENU_LAYOUT");
  assert.equal(found[0].code, "NOT_APPLIED");
});

test("ICON is checked for format traps only, never a vocabulary", () => {
  assert.deepEqual(on(check({ICON: "fuel.svg"}), "ICON"), []);
  assert.deepEqual(on(check({ICON: "Mso:FileSave"}), "ICON"), []);
  assert.match(on(check({ICON: " fuel.svg"}), "ICON")[0].detail, /whitespace/);
  assert.match(on(check({ICON: "../x.svg"}), "ICON")[0].detail, /traversal/);
  assert.equal(on(check({ICON: "x".repeat(201)}), "ICON")[0].severity, "Error");
});

// ---- the whole row ---------------------------------------------------------

test("helpers apply the add-in's defaults", () => {
  assert.equal(effectiveControlKey({}), "mnuDynamic");
  assert.equal(buildsAMenu("library"), true);
  assert.equal(buildsAMenu("Export"), false);
  assert.equal(controlSwitchedOff({}), false);
  assert.equal(controlSwitchedOff({IS_ACTIVE: "غلط"}), true);
});

test("a clean row says nothing at all", () => {
  assert.deepEqual(check({}), []);
});

test("every finding names its field and carries a code", () => {
  const found = check({CONTROL_KEY: "", ACTION_CLASS: "OpenView",
                       ACTION_TAG: "T_GHOST|GHOST", REGION: "EGY",
                       ORDER: "x", ICON: " a.."});
  assert.ok(found.length >= 5, `only ${found.length}`);
  for (const f of found) {
    assert.ok(f.field, "a finding with no field cannot be shown beside a cell");
    assert.ok(f.code, `${f.field} has no code`);
    assert.ok(f.detail);
  }
});
