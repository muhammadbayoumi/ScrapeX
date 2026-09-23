/**
 * `finishEstimate` shipped with no test at all, and the gate's second pass proved it:
 * deleting its new early return left 557 of 557 green.
 *
 * WHY IT HAD NONE, AND WHY THAT IS NOT A REASON. `finishEstimate` lives in `app.js`,
 * which exports nothing — it is the panel's runtime, loaded by a script tag. The repo
 * already solved that for the Settings grid: `healthy.test.mjs` reads `app.js` as text,
 * pulls named functions out by regex, and runs them in a scope it builds. This is the
 * same harness pointed at one more function.
 *
 * WHAT IT GUARDS. The estimate divides the requests still owed by an observed rate, and
 * two things about it are load-bearing and neither is obvious:
 *
 *   - PAST THE DECLARED COUNT there is nothing honest to say. `declare_frontier`
 *     declares ONE read of the partition; `_crawl_one_cell` is allowed ten for any cell
 *     over 31 pages, and the Oman register is 471. Measured on the repo's own harness:
 *     declared 47, spent 137. The old `Math.max(0, expected - requests)` made the
 *     remainder zero and printed `~0s left` for every one of those 90 requests.
 *   - NO FALLBACK TO THE WALL CLOCK, which is what `recentRate()` returning null means.
 *     A missing number beats one that is ten times wrong.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "app.js"), "utf8");

function extract(name, pattern) {
  const match = SOURCE.match(pattern);
  assert.ok(match, `${name} is no longer where this guard reads it from in app.js`);
  return match[0];
}

// The function shape ends on a `}` in column 0 — every brace inside it is indented —
// so a lazy match stops at the end of the function and not at a block within it.
const FINISH_ESTIMATE = extract(
  "finishEstimate", /^function finishEstimate\(job\) \{[\s\S]*?^\}/m);
const FMT_DURATION = extract(
  "fmtDuration", /^function fmtDuration\([\s\S]*?^\}/m);

/** Build `finishEstimate` over a stated rate, so no clock and no module state.
 *
 * `new Function` is how `healthy.test.mjs` already runs extracted `app.js` functions,
 * disable comment and all: `app.js` is the panel's runtime and exports nothing, so the
 * alternative is not testing it — which is the state the gate found this function in.
 */
function estimator(rate) {
  // eslint-disable-next-line no-new-func
  const build = new Function(
    "recentRate",
    `${FMT_DURATION}\n${FINISH_ESTIMATE}\nreturn finishEstimate;`);
  return build(() => rate);
}

test("past the declared count it says nothing rather than ~0s left", () => {
  // The heavy-cell case: the crawl has spent more than one read of the partition and
  // is still going. `Math.max(0, ...)` printed `~0s left` here, for most of the crawl.
  const estimate = estimator(1.0);
  assert.equal(estimate({ fetch: { expected: 47, requests: 137, basis: "declared" } }), "",
    "the panel claimed the crawl was finishing while it kept fetching");
  // And exactly AT the declaration, which is the boundary the guard is written on.
  assert.equal(estimate({ fetch: { expected: 47, requests: 47, basis: "declared" } }), "");
});

test("below the declared count it still answers", () => {
  // 900 owed at 1/s is 15 minutes. The guard must not have swallowed the whole feature.
  const estimate = estimator(1.0);
  const said = estimate({ fetch: { expected: 943, requests: 43, basis: "declared" } });
  assert.match(said, /left$/, `it said ${JSON.stringify(said)}`);
  assert.match(said, /15m/, `900 requests at 1/s is 15 minutes; it said ${said}`);
  assert.ok(!said.includes("about"),
    "a DECLARED count is a count, so the estimate does not hedge it with 'about'");
});

test("an estimated denominator is hedged and a declared one is not", () => {
  const estimate = estimator(1.0);
  const guessed = estimate({ fetch: { expected: 943, requests: 43, basis: "estimate" } });
  assert.ok(guessed.includes("about"),
    `an estimate must say so: ${JSON.stringify(guessed)}`);
});

test("no rate means no estimate, and never a wall-clock one", () => {
  // `recentRate()` returns null while the window holds fewer than two points, and after
  // a sleep — which is the whole reason the wall clock was removed.
  for (const rate of [null, 0, -1]) {
    assert.equal(
      estimator(rate)({ fetch: { expected: 943, requests: 43, basis: "declared" } }), "",
      `a rate of ${rate} produced an estimate`);
  }
});

test("no denominator, or too few requests, means no estimate", () => {
  const estimate = estimator(1.0);
  assert.equal(estimate({ fetch: { requests: 43 } }), "",
    "an estimate was drawn against no denominator at all");
  assert.equal(estimate({ fetch: { expected: 943, requests: 1 } }), "",
    "one request is not a rate");
  assert.equal(estimate({}), "", "a job with no fetch block produced an estimate");
});
