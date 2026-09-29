// What the Data page MAKES of a `/api/taxonomy` payload — and nothing else.
//
// PURE, for the same reason datatable.js is: data.js cannot be imported under
// `node --test` because it reads `window.location` and starts loading the moment
// it is imported. Everything here can be driven with hostile input instead.
//
// ISSUE 543. 407,384 memberships are stored on his warehouse — 398,933 interests
// over 17,811 contractors, average 22.9 each — and until this file nothing read
// them: `taxonomy.memberships` has no caller in `scrapex/` outside its tests, so
// a contractor's own activities were invisible on every screen he has.
//
// WHY THE FILTER IS NOT THE GRID'S. Tabulator filters what it holds, and it
// cannot hold this: putting each row's memberships in the payload is 407,384
// strings beside a 17,811-row table — several times the table itself. So the
// selection goes back to the engine as node ids and SQL narrows the rows.

/**
 * The groups as trees, each node carrying its children and its held count.
 *
 * NESTED HERE RATHER THAN IN THE ENGINE, because the wire shape is the flat list
 * with `parent_node_id` — which is what the table itself stores, and re-deriving
 * the nesting in SQL would put the tree's shape in two places.
 *
 * A NODE WHOSE PARENT IS MISSING IS A ROOT, not a dropped node. The engine
 * separates the undeclared node out of `nodes`, so any node that pointed at it
 * would otherwise vanish with it — silently, and only for the contractors the
 * site says nothing about.
 */
export function treeFrom(group) {
  const nodes = (group?.nodes || []).filter((node) => node && node.node_id != null);
  const byId = new Map(nodes.map((node) => [node.node_id, { ...node, children: [] }]));
  const roots = [];
  for (const node of byId.values()) {
    const parent = node.parent_node_id == null ? null : byId.get(node.parent_node_id);
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  // HELD DESCENDING, THEN BY NAME. The first thing he sees is the biggest real
  // category, and two nodes holding the same number keep a stable order between
  // reloads rather than whatever the map iteration gave.
  const order = (list) => {
    list.sort((a, b) => (b.held - a.held)
      || String(a.name_ar || a.name || "").localeCompare(String(b.name_ar || b.name || "")));
    list.forEach((node) => order(node.children));
    return list;
  };
  return order(roots);
}

/**
 * The line above the tree for the contractors the site declares nothing about —
 * his ruling of 2026-09-08: a state, said in a line, not a category in the tree.
 *
 * IT NAMES A COUNT AND NOT A CATEGORY. On his warehouse `No Data` is a level-1
 * node held by 9,001 contractors, larger than `Construction of buildings` at
 * 7,634 — so a tree that kept it would open with a fake category as its biggest.
 * Deleting the rows was the other option and he refused it: 9,001 contractors
 * having declared nothing is a fact about them, and dropping it would make them
 * indistinguishable from 9,001 nobody has fetched.
 */
export function undeclaredLine(group) {
  const held = group?.undeclared?.held;
  if (!held) return "";
  return `${Number(held).toLocaleString()} contractors have not declared an `
    + "activity — the site publishes “No Data” for them, which is a state and not "
    + "a category, so it is not in the list below.";
}

/**
 * The query the table route takes for a selection, or "" for none.
 *
 * ANY OR ALL, AND THE CALLER HAS TO SAY. There is no default worth guessing:
 * "any" widens and adds up, "all" narrows hard and can answer zero from two
 * reasonable picks, and he asked for a toggle rather than one fixed meaning.
 */
export function selectionQuery(nodeIds, mode) {
  const chosen = nodesOf(nodeIds);
  if (!chosen.length) return "";
  return `&nodes=${chosen.join(",")}&nodes_mode=${modeOf(mode)}`;
}

/**
 * ONE READING OF A SELECTION, for the three places a selection is spelled: the
 * table request above, and the page's own address below, written and read back.
 * Node ids are positive integers, each once, ascending; the mode is `all` or else
 * `any`, the widening one.
 */
function nodesOf(nodeIds) {
  return [...new Set((Array.isArray(nodeIds) ? nodeIds : [])
    .map((one) => Number(one))
    .filter((one) => Number.isInteger(one) && one > 0))].sort((a, b) => a - b);
}

function modeOf(mode) {
  return String(mode).toLowerCase() === "all" ? "all" : "any";
}

/**
 * The selection a page address carries, in the names the table route takes.
 *
 * READ ONCE, WHEN THE PAGE OPENS (#1198). The grid reloads the page after a
 * column change, a Reset columns and a fold change, and a reload keeps only what
 * is in the address, so the address is where a selection has to live.
 */
export function selectionFrom(search) {
  const params = new URLSearchParams(String(search || ""));
  return {
    nodes: nodesOf(String(params.get("nodes") || "").split(",")),
    mode: modeOf(params.get("nodes_mode")),
  };
}

/**
 * The page address with this selection in it, every other parameter kept.
 *
 * AN EMPTY SELECTION TAKES BOTH PARAMETERS OUT, so a cleared filter leaves the
 * address the panel opened. The commas stay commas: they are legal in a query,
 * and an address that reads `nodes=11,22` is one a person can check.
 */
export function selectionUrl(href, nodeIds, mode) {
  const url = new URL(String(href));
  const chosen = nodesOf(nodeIds);
  if (chosen.length) {
    url.searchParams.set("nodes", chosen.join(","));
    url.searchParams.set("nodes_mode", modeOf(mode));
  } else {
    url.searchParams.delete("nodes");
    url.searchParams.delete("nodes_mode");
  }
  url.search = url.searchParams.toString().replaceAll("%2C", ",");
  return url.href;
}

/**
 * What the toggle means, in words, so the control is not two letters and a guess.
 */
export function modeLabel(mode) {
  return String(mode).toLowerCase() === "all"
    ? "holds ALL of the chosen activities"
    : "holds ANY of the chosen activities";
}

/**
 * What a selection left, or "" when nothing is chosen.
 *
 * BOTH NUMBERS, ALWAYS. A filter that leaves 12 rows of 17,811 and says only
 * "12 rows" reads as a dataset that lost seventeen thousand of them — which is
 * exactly how he read a blocked job as nothing working (#778).
 */
export function filterSummary(payload) {
  const chosen = payload?.filtered_by?.nodes || [];
  if (!chosen.length) return "";
  const total = Number(payload?.total ?? 0);
  const population = Number(payload?.population ?? total);
  const mode = String(payload?.filtered_by?.mode || "any").toLowerCase() === "all"
    ? "all" : "any";
  return `${total.toLocaleString()} of ${population.toLocaleString()} rows · `
    + `${chosen.length} ${chosen.length === 1 ? "activity" : "activities"} chosen, `
    + `matching ${mode === "all" ? "all of them" : "any of them"}`;
}
