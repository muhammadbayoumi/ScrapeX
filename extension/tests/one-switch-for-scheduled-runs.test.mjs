// What the panel says about a source's schedule once its one Active switch lives on the
// Schedules row (#1596, D1 option 2). Read as source text and evaluated in a `vm`
// context, as `the-panel-says-where-each-rule-comes-from.test.mjs` does: app.js exports
// nothing.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

function lift(pattern, name) {
  const found = SOURCE.match(pattern);
  assert.ok(found, `${name} is no longer where this guard reads it from in app.js`);
  return found[0];
}
const fn = (name) => lift(new RegExp(`^function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`, "m"), name);
const WEEKDAYS = lift(/^const WEEKDAYS = \[[\s\S]*?\];/m, "WEEKDAYS");

function load(schedules) {
  return vm.runInNewContext(
    `${WEEKDAYS}\n${fn("scheduleLabel")}\n${fn("scheduledRunsOn")}\n${fn("scheduleSummary")}\n`
    + "({scheduleLabel, scheduledRunsOn, scheduleSummary});",
    {state: {schedules}});
}

const daily = {source_key: "SHOP", schedule_id: 1, enabled: 1, frequency: "daily",
               run_at: "09:00", weekday: null};

test("a schedule reads as its frequency and time, and none or manual as not scheduled", () => {
  const {scheduleLabel} = load(null);
  assert.equal(scheduleLabel(daily), "Daily 09:00");
  assert.equal(scheduleLabel({...daily, frequency: "weekly", weekday: 4, run_at: "06:30"}),
               "Weekly Friday 06:30");
  // The server's defaults where a field is missing: Monday, 09:00.
  assert.equal(scheduleLabel({frequency: "weekly"}), "Weekly Monday 09:00");
  assert.equal(scheduleLabel({...daily, frequency: "manual"}), "Not scheduled");
  assert.equal(scheduleLabel(undefined), "Not scheduled");
  assert.equal(scheduleLabel({}), "Not scheduled");
});

test("runs fire only with the source active and its schedule enabled", () => {
  const {scheduledRunsOn} = load(null);
  assert.equal(scheduledRunsOn({active: true}, daily), true);
  assert.equal(scheduledRunsOn({active: false}, daily), false);
  // The one schedule 0024 could not fold -- its source never registered -- stays off.
  assert.equal(scheduledRunsOn({active: true}, {...daily, enabled: 0}), false);
  // No schedule yet: the switch's state is the source's alone.
  assert.equal(scheduledRunsOn({active: true}, undefined), true);
});

test("the summary adds Off to a schedule that will not fire, and nothing when unread", () => {
  const schedules = new Map([["SHOP", daily], ["IDLE", {...daily, frequency: "manual"}]]);
  const {scheduleSummary} = load(schedules);
  assert.equal(scheduleSummary({source_key: "SHOP", active: true}), "Daily 09:00");
  assert.equal(scheduleSummary({source_key: "SHOP", active: false}), "Daily 09:00 · Off");
  assert.equal(scheduleSummary({source_key: "IDLE", active: false}), "Not scheduled");
  assert.equal(scheduleSummary({source_key: "NEW", active: true}), "Not scheduled");
  assert.equal(load(null).scheduleSummary({source_key: "SHOP", active: true}), "");
});
