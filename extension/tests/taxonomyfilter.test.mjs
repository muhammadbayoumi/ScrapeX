// The Data page's taxonomy filter, driven with the shapes the engine really sends
// and with the ones it must never be broken by.
//
// ISSUE 543. The numbers in these tests are his: 214 interest nodes over 17,811
// contractors, 398,933 memberships, and a level-1 node called `No Data` held by
// 9,001 of them — larger than `Construction of buildings` at 7,634.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  filterSummary, modeLabel, selectionQuery, treeFrom, undeclaredLine,
} from "../taxonomyfilter.js";

const GROUP = {
  group_key: "interests",
  scheme: { scheme_id: 1, name: "Interests", name_ar: "الأنشطة" },
  undeclared: { node_id: 111, level: 1, name: "No Data",
                name_ar: "لا يوجد بيانات", held: 9001 },
  nodes: [
    { node_id: 11, parent_node_id: null, level: 1, name: "Specialized", held: 6564 },
    { node_id: 1, parent_node_id: null, level: 1, name: "Buildings", held: 7634 },
    { node_id: 14, parent_node_id: 11, level: 2, name: "Electrical", held: 4578 },
    { node_id: 22, parent_node_id: 11, level: 2, name: "Plumbing", held: 4000 },
    { node_id: 30, parent_node_id: 14, level: 3, name: "Wiring", held: 4070 },
  ],
};

test("the tree nests on parent_node_id and puts the biggest category first", () => {
  const roots = treeFrom(GROUP);

  assert.deepEqual(roots.map((n) => n.node_id), [1, 11],
    "roots are not ordered by how many contractors hold them");
  const specialized = roots.find((n) => n.node_id === 11);
  assert.deepEqual(specialized.children.map((n) => n.node_id), [14, 22]);
  assert.deepEqual(specialized.children[0].children.map((n) => n.node_id), [30]);
});

test("a node whose parent is missing becomes a root rather than vanishing", () => {
  // THE UNDECLARED NODE IS SEPARATED OUT OF `nodes` BY THE ENGINE, so anything
  // pointing at it has no parent in this list. Dropping such a node would hide
  // it silently, and only for the contractors the site says least about.
  const orphaned = { ...GROUP, nodes: [
    ...GROUP.nodes, { node_id: 99, parent_node_id: 111, level: 2, name: "Orphan", held: 5 },
  ] };

  const ids = treeFrom(orphaned).map((n) => n.node_id);
  assert.ok(ids.includes(99), `the orphaned node was dropped: ${ids}`);
});

test("the undeclared line names the count and refuses to be a category", () => {
  const said = undeclaredLine(GROUP);

  assert.match(said, /9,001 contractors have not declared/);
  assert.match(said, /not in the list below/,
    "the line does not say why the node is absent from the tree");
  assert.equal(treeFrom(GROUP).some((n) => n.node_id === 111), false,
    "the undeclared node reached the tree");
  assert.equal(undeclaredLine({ nodes: [] }), "",
    "a group with nothing undeclared still printed a line");
});

test("the selection reaches the engine sorted, deduplicated and mode-named", () => {
  assert.equal(selectionQuery([22, 11, 22], "any"), "&nodes=11,22&nodes_mode=any");
  assert.equal(selectionQuery([11], "ALL"), "&nodes=11&nodes_mode=all");
  assert.equal(selectionQuery([], "all"), "", "an empty selection sent a filter");
  // HOSTILE INPUT: these came off a page and out of a URL.
  assert.equal(selectionQuery(["11", 0, -3, null, "abc", 7.5], "any"),
    "&nodes=11&nodes_mode=any");
  assert.equal(selectionQuery([11], "anything else"), "&nodes=11&nodes_mode=any",
    "an unknown mode did not fall back to the widening one");
});

test("the mode is said in words, because two letters are a guess", () => {
  assert.match(modeLabel("all"), /ALL/);
  assert.match(modeLabel("any"), /ANY/);
  assert.match(modeLabel(undefined), /ANY/);
});

test("the summary carries what the filter left AND what it started from", () => {
  const said = filterSummary({
    total: 2340, population: 17811, filtered_by: { nodes: [11, 46], mode: "all" } });

  assert.match(said, /2,340 of 17,811 rows/,
    `a filtered count without its population reads as lost rows: ${said}`);
  assert.match(said, /2 activities chosen/);
  assert.match(said, /matching all of them/);
  assert.equal(filterSummary({ total: 17811, population: 17811, filtered_by: {} }), "",
    "an unfiltered table printed a filter summary");
  assert.match(filterSummary({ total: 6564, population: 17811,
                               filtered_by: { nodes: [11], mode: "any" } }),
    /1 activity chosen/, "one activity was called activities");
});
