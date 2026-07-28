// The Data page grid.
//
// Tabulator gives what a hand-built <table> cannot without months of work: a
// three-dot menu on every column head, drag to resize, drag to reorder, row
// grouping, and a layout that survives a reload. The owner asked for the AG Grid
// look; the features in those screenshots — set filter, row grouping with
// aggregation, the columns tool panel, Excel export — live in ag-grid-enterprise,
// whose npm licence field reads "Commercial". This builds the same shapes on the
// MIT library we already vendor.
//
// What Tabulator does NOT own: meaning. The unit still rides on the price, the
// tax verdict still carries where to read it, and the offer id still opens the
// real history page. Those came from earlier work and survive the new renderer
// because these formatters keep them.
(function () {
  "use strict";

  const mount = document.getElementById("grid");
  const note = document.getElementById("grid-note");
  const toolbar = document.getElementById("grid-toolbar");
  const viewport = mount && mount.closest("[data-grid-viewport]");
  if (!mount || typeof Tabulator !== "function") return;

  const SOURCE = mount.dataset.source;
  const text = (v) => (v === null || v === undefined) ? "" : String(v);
  // One numeric convention across the workspace: comma for thousands and dot
  // for decimals. Stored precision is preserved, never padded or rounded.
  function formatMoney(raw) {
    const s = text(raw);
    if (!s || isNaN(Number(s))) return s;
    const negative = s.startsWith("-");
    const parts = (negative ? s.slice(1) : s).split(".");
    const grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return (negative ? "-" : "") + grouped + (parts[1] ? "." + parts[1] : "");
  }
  // ---- ONE ordering for the whole page ---------------------------------------
  //
  // Tabulator's string sorter calls localeCompare with the BROWSER's locale.
  // Here that is en-US, where Arabic has no collation of its own and falls back
  // to the order Unicode happens to store the letters in: ء آ أ إ ا instead of
  // ء أ إ ا آ. Measured on this data, that diverges from Arabic order at the
  // fourth of 616 Madar names. It also has no numeric option, which is why Unit
  // read 10 kg, 12.5 kg, 14.3 kg, 16 kg, 2 kg — while the filter popup listed
  // the SAME column's values 2 kg, 2.5 kg, 2.9 kg, because it did its own
  // sorting with its own rules. One column, two orders, depending where you
  // looked at it.
  //
  // Declaring ar first gives Arabic its collation; Latin ordering comes out
  // byte-for-byte identical to the en collator (checked against the real
  // names), so English readers lose nothing.
  const COLLATOR = new Intl.Collator(["ar", "en"], {numeric: true});

  /** Compare as text, the way this page lists text everywhere else.
   *
   * alignEmptyValues lives INSIDE each of Tabulator's built-in sorters rather
   * than around them, so a replacement has to carry the empties contract
   * itself. Without it an ascending sort on a sparse column floods its first
   * screens with blanks — the exact complaint sorterParams was added to answer.
   */
  function textSorter(a, b, aRow, bRow, column, dir, params) {
    const left = text(a);
    const right = text(b);
    if (left && right) return COLLATOR.compare(left, right);
    let empty = left ? 1 : (right ? -1 : 0);
    const align = (params && params.alignEmptyValues) || "bottom";
    if ((align === "top" && dir === "desc") || (align === "bottom" && dir === "asc")) {
      empty = -empty;
    }
    return empty;
  }

  // ---- what a column actually READS ------------------------------------------
  //
  // Two columns show something other than their own field, and sorting and
  // filtering were both reading the field.
  //
  // Country prints "United Arab Emirates" and its field holds "AE", so sorting
  // put the UAE second of 169 countries and the filter popup offered a list of
  // ISO codes for rows whose names are the only thing on screen — you had to
  // know the code to filter by a country you could see.
  //
  // Tax prints "Incl. 15%" out of payload.tax_states[tax_ref]; its own field is
  // null on every row. Clicking that header cycled the arrow and moved nothing,
  // and its filter offered exactly one entry: "(Blanks)".
  //
  // One reader, used by the sorter, the filter list and the filter itself, so
  // all three agree with the cell.
  const DISPLAY_VALUE = {
    country_code_alpha2: (row) => text(row.country) || text(row.country_code_alpha2),
    tax: (row) => text(((payload.tax_states || [])[row.tax_ref] || {}).tax_short),
  };

  function readValue(field, row) {
    const reader = DISPLAY_VALUE[field];
    return reader ? reader(row) : asText(row[field]);
  }

  function displaySorter(field) {
    return (a, b, aRow, bRow, column, dir, params) => textSorter(
      readValue(field, aRow.getData()), readValue(field, bRow.getData()),
      aRow, bRow, column, dir, params);
  }

  /** The number a value STARTS with, for values that are not only a number. */
  function leadingNumber(raw) {
    const match = /^\s*([+-]?\d+(?:\.\d+)?)/.exec(text(raw));
    return match ? Number(match[1]) : NaN;
  }

  /** Order by the number in front, then by the words after it.
   *
   * "+5.00 (+32.3%)" is a sentence about a number. Compared as text the minus
   * is just a character and the digits behind it compare as unsigned
   * magnitudes, so ascending Price change listed the SMALLEST drop first and
   * buried the biggest one at the bottom of the negatives. The same rule fixes
   * measurements: 3.25 kg lands before 3.5 kg, which numeric collation alone
   * gets wrong because it compares the digit runs 25 and 5.
   */
  function measureSorter(a, b, aRow, bRow, column, dir, params) {
    const left = text(a);
    const right = text(b);
    if (left && right) {
      const leftNumber = leadingNumber(left);
      const rightNumber = leadingNumber(right);
      if (!isNaN(leftNumber) && !isNaN(rightNumber) && leftNumber !== rightNumber) {
        return leftNumber - rightNumber;
      }
      return COLLATOR.compare(left, right);
    }
    return textSorter(a, b, aRow, bRow, column, dir, params);
  }

  /** "number" if every value in the column is one, otherwise text.
   *
   * A column is numeric only when NOTHING in it is a word. One real word
   * settles it, because a numeric sorter would send every word to the same
   * place (NaN) and lose their order entirely.
   */
  function sorterFor(key) {
    if (DISPLAY_VALUE[key]) return displaySorter(key);
    let sawNumber = false;
    let sawText = false;
    let everyTextLeadsWithNumber = true;
    for (const row of payload.rows) {
      const value = row[key];
      if (value === "" || value === null || value === undefined) continue;
      if (typeof value === "number") { sawNumber = true; continue; }
      if (typeof value === "string" && !isNaN(Number(value))) { sawNumber = true; continue; }
      sawText = true;
      if (isNaN(leadingNumber(value))) { everyTextLeadsWithNumber = false; break; }
    }
    if (sawText) return everyTextLeadsWithNumber ? measureSorter : textSorter;
    return sawNumber ? "number" : textSorter;
  }

  const GRID_MIN_COLUMN_WIDTH = 128;
  // v2 intentionally forgets column widths and sort state saved by the older
  // grid. Those values could leave a header too narrow for its controls and a
  // saved sorter could make the first three-click cycle start mid-sequence.
  const PERSISTENCE_ID = "scrapex-grid-v3-" + SOURCE;
  const materialIcon = window.ScrapeXUI.icon;
  const materialIconElement = window.ScrapeXUI.iconNode;

  const FILTER_ICON = materialIcon("filter-list", "material-filter-icon");
  const MENU_ICON = materialIcon("more-vert", "material-menu-icon");
  const SORT_ICON = materialIcon("arrow-upward", "material-sort-icon");

  // ---- active filters, and the line that reports them ----------------------
  // Kept here rather than inside Tabulator so the page can SAY what is being
  // filtered. A grid that quietly shows fewer rows than it has is the same
  // failure as a filter that vanishes: the reader cannot tell.
  const active = new Map();
  let table = null;
  let payload = null;
  let viewportResizeTimer = null;
  let lastViewportWidth = 0;
  if (viewport && typeof ResizeObserver === "function") {
    const viewportObserver = new ResizeObserver((entries) => {
      const nextWidth = Math.round(entries[0].contentRect.width);
      clearTimeout(viewportResizeTimer);
      viewportResizeTimer = setTimeout(() => {
        if (!table || nextWidth < 1 || nextWidth === lastViewportWidth) return;
        lastViewportWidth = nextWidth;
        try { table.redraw(true); } catch (err) { /* a destroyed grid needs no redraw */ }
      }, 140);
    });
    viewportObserver.observe(viewport);
  }

  // Which features are on, per SOURCE. A commodity table and a shop table do
  // not want the same shape, so one global preference would be wrong for one of
  // them. localStorage rather than the database: this is how a table is DRAWN,
  // not what it means, and it should not survive into an export or a backup.
  // v2: the key is versioned because the defaults changed. A preference saved
  // under the old defaults would keep showing stripes the owner never asked
  // for, and "clear your browser storage" is not an answer.
  const FEATURE_KEY = "scrapex-features-v2-" + (mount.dataset.source || "");
  // Defaults chosen to leave the table looking EXACTLY as it did: no stripes,
  // no extra columns, standard spacing. Grouping is the one thing on by
  // default, and only where the server found something to group.
  const DEFAULT_FEATURES = {tree: true, rows: true, select: true, statusbar: true,
                            totals: false, rownum: false, compact: false,
                            wrap: false, stripe: false};
  let features = Object.assign({}, DEFAULT_FEATURES);
  // WHICH columns group the table, from outermost to innermost. Per source,
  // because the useful hierarchy for a fuel table (material, then country) is
  // not the useful hierarchy for a shop. The older preference was one plain
  // string; read it as a one-level group so the upgrade does not discard it.
  // v2: the vocabulary sweep renamed the columns these hold.
  const GROUP_KEY = "scrapex-groupby-v2-" + (mount.dataset.source || "");
  const TREE_KEY = "scrapex-treeby-v2-" + (mount.dataset.source || "");
  let groupedBy = [];
  let treeBy = "";
  function readGroups(raw) {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return [...new Set(parsed.filter((field) => typeof field === "string" && field))];
      }
    } catch (err) { /* the old value was deliberately not JSON */ }
    return [raw];
  }
  try {
    groupedBy = readGroups(localStorage.getItem(GROUP_KEY) || "");
    treeBy = localStorage.getItem(TREE_KEY) || "";
  } catch (err) { groupedBy = []; treeBy = ""; }
  try {
    const saved = JSON.parse(localStorage.getItem(FEATURE_KEY) || "null");
    if (saved) features = Object.assign(features, saved);
  } catch (err) { /* a corrupt preference must not stop the table loading */ }

  function remember_(key, value) {
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch (err) { /* private mode: it still works, it just forgets */ }
  }

  function rememberGroups() {
    remember_(GROUP_KEY, groupedBy.length ? JSON.stringify(groupedBy) : "");
  }

  function setGroup(field) {
    if (!field) groupedBy = [];
    else if (groupedBy.includes(field)) {
      groupedBy = groupedBy.filter((groupField) => groupField !== field);
    } else {
      groupedBy = groupedBy.concat(field);
    }
    // A grouped tree would show synthetic bands over rows that are already
    // nested — two hierarchies stacked, neither readable. Choosing one turns
    // the other off, visibly, rather than rendering the collision.
    if (groupedBy.length) { treeBy = ""; remember_(TREE_KEY, ""); }
    rememberGroups();
    build();
  }

  function setTree(field) {
    treeBy = field || "";
    if (treeBy) { groupedBy = []; rememberGroups(); }
    remember_(TREE_KEY, treeBy);
    build();
  }

  /** Fold flat rows into parent -> children on one column's value.
   *
   * The parent is a HEADING, not a promoted row: it carries the shared value
   * and a count, and every other cell is empty. Promoting the set's first row
   * instead — which is what this did first — made Andorra the face of DIESEL:
   * one arbitrary country's price sat on the branch as if it stood for all 169,
   * and that country then vanished from the list of children. An empty cell says
   * "no value here"; a real value in a heading row says something false.
   *
   * A value with a single row is left flat. A branch with one child is one more
   * click to see exactly what was already visible.
   */
  function nest(rows, field) {
    const buckets = new Map();
    rows.forEach((row) => {
      const key = row[field] == null ? "" : String(row[field]);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(row);
    });
    const out = [];
    let nested = false;
    buckets.forEach((set, key) => {
      if (set.length === 1) { out.push(set[0]); return; }
      nested = true;
      const parent = {_children: set, _branch: set.length};
      parent[field] = key;
      out.push(parent);
    });
    return nested ? out : [];      // nothing to nest is not a tree
  }

  function hide(field) {
    // Server only. A local column.hide() would persist in the browser and then
    // outvote the server for ever.
    remember(field, true).then(() => location.reload());
  }

  function saveFeatures() {
    try { localStorage.setItem(FEATURE_KEY, JSON.stringify(features)); }
    catch (err) { /* private mode: the table still works, it just forgets */ }
  }

  // A value the source left empty is still a value. 3,325 of Madar's 3,417 rows
  // have no Unit, and a popup that quietly omitted them turned "keep everything
  // except 2 kg" into a table of 88 rows — the blanks were not deselected, they
  // were never selectABLE. Blanks travel as "" and are shown under a name.
  const BLANK_VALUE = "";
  const BLANK_LABEL = "(Blanks)";
  const asText = (v) => (v === null || v === undefined) ? BLANK_VALUE : String(v);

  function applyFilters() {
    if (!table) return;
    // A FUNCTION filter, not Tabulator's "in". "in" compares with indexOf —
    // strict equality — against the popup's list, and everything the popup
    // holds is a string. So a numeric cell never matched its own value: ticking
    // 2 in Observations (115 rows carry it) filtered the table down to nothing,
    // and the same was true of Price, Min price and Max price. Comparing as
    // text on both sides is what the popup already promises the reader.
    table.setFilter([...active].map(([field, f]) => {
      if (!f.values) return {field, type: "like", value: f.text};
      const wanted = new Set(f.values.map(asText));
      return {field: (row) => wanted.has(readValue(field, row))};
    }));
    describe();
    paintChips();
  }

  function describe() {
    if (!table || !note) return;
    const shown = table.getDataCount("active");
    const all = table.getDataCount();
    const details = [];
    // The total already lives in the table footer. Repeat it below only when a
    // filter changes its meaning and the reader needs the before/after count.
    if (active.size) {
      details.push(shown.toLocaleString() + " of " + all.toLocaleString() + " rows");
    }
    if (payload && payload.truncated) {
      // Never let a prefix look like the whole. The filters below can only see
      // what was loaded, and the reader is told so plainly.
      details.push("Loaded " + payload.returned.toLocaleString() + " of " +
                   payload.total.toLocaleString() + "; filters search only what is loaded");
    }
    note.textContent = details.join(" — ");
    note.hidden = details.length === 0;
  }

  function paintChips() {
    const bar = document.getElementById("grid-chips");
    if (!bar) return;
    bar.replaceChildren();
    if (!active.size) return;
    active.forEach((f, field) => {
      const column = (payload.columns.find((c) => c.key === field) || {}).label || field;
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip pill";
      const label = document.createElement("span");
      // One chosen value is worth NAMING. "Unit: 1 selected" tells the reader
      // that something is filtered but not what, which is half a chip.
      const what = !f.values ? "contains " + f.text
        : f.values.length === 1
          ? "is " + (f.values[0] === BLANK_VALUE ? BLANK_LABEL : f.values[0])
          : f.values.length.toLocaleString() + " selected";
      label.textContent = column + ": " + what;
      chip.append(label);
      chip.insertAdjacentHTML("beforeend", materialIcon("close", "inline-icon"));
      chip.title = "Remove this filter";
      chip.addEventListener("click", () => { active.delete(field); applyFilters(); });
      bar.append(chip);
    });
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "chip";
    clear.textContent = "Clear all";
    clear.addEventListener("click", () => { active.clear(); applyFilters(); });
    bar.append(clear);
  }

  // ---- the filter popup: search, select all, checkboxes ---------------------
  // The shape the owner asked for by picture. Tabulator has no set filter, so it
  // is built here — which also means its wording and its behaviour are ours,
  // instead of inherited from a library's defaults.
  // Tabulator calls these with (event, component, onRendered) — NOT with the
  // component as `this`. Relying on `this` made both the menu and the filter
  // build nothing and fail silently, which looked exactly like an icon that
  // does not respond.
  function filterPopup(event, column) {
    const field = column.getField();
    const box = document.createElement("div");
    box.className = "setfilter";
    // Escape closes it. Tabulator binds its own escape handler, but the check
    // reads `27 == event.key` — a number against a string, which is false for
    // every key there is, so the popup could only ever be dismissed with the
    // mouse. Handling it here rather than patching the vendored file.
    box.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      dismissOpenHeaderPopups();
    });

    // Every value as TEXT, blanks included and listed first under their own
    // name, so the list accounts for every row in the column rather than for
    // the rows that happen to be filled in.
    const seen = new Set(payload.rows.map((r) => readValue(field, r)));
    const hasBlank = seen.delete(BLANK_VALUE);
    const values = [...seen].sort(COLLATOR.compare);
    if (hasBlank) values.unshift(BLANK_VALUE);
    const labelOf = (v) => v === BLANK_VALUE ? BLANK_LABEL : v;

    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Search…";
    search.setAttribute("aria-label", "Search values");
    box.append(search);

    const list = document.createElement("div");
    list.className = "setfilter-list";
    box.append(list);

    const chosen = new Set(active.get(field) && active.get(field).values
      ? active.get(field).values.map(asText) : values);

    const actions = document.createElement("div");
    actions.className = "setfilter-actions";
    const count = document.createElement("p");
    count.className = "hint setfilter-count";
    count.setAttribute("role", "status");
    const apply = document.createElement("button");
    apply.type = "button";
    apply.textContent = "Apply";
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "ghost";
    reset.textContent = "Clear";
    actions.append(apply, reset);

    function row(label, checked, onChange, strong) {
      const line = document.createElement("label");
      line.className = "setfilter-row" + (strong ? " strong" : "");
      const tick = document.createElement("input");
      tick.type = "checkbox";
      tick.checked = checked;
      tick.addEventListener("change", () => onChange(tick.checked));
      const span = document.createElement("span");
      span.dir = "auto";                       // scraped values are DATA
      span.textContent = label;
      line.append(tick, span);
      return line;
    }

    // The head checkbox has to ANSWER for the boxes under it. It did not: every
    // value row wrote to `chosen` and re-drew nothing, so "(Select all)" still
    // read as ticked with half the list unticked beneath it. Now it is synced
    // in place — not by re-rendering, which would throw away the scroll
    // position and the search focus mid-choice.
    let master = null;
    let shown = values;

    function syncHead() {
      const ticked = shown.reduce((n, v) => n + (chosen.has(v) ? 1 : 0), 0);
      if (master) {
        master.checked = shown.length > 0 && ticked === shown.length;
        master.indeterminate = ticked > 0 && ticked < shown.length;
      }
      // A filter that selects nothing would empty the table and say only "0 of
      // 3,417" — refusing it is kinder than performing it.
      apply.disabled = chosen.size === 0;
      apply.title = chosen.size === 0
        ? "Tick at least one value" : "";
      count.textContent = chosen.size === values.length
        ? "All " + values.length.toLocaleString() + " values"
        : chosen.size.toLocaleString() + " of " +
          values.length.toLocaleString() + " selected";
    }

    function render() {
      const needle = search.value.trim().toLowerCase();
      shown = needle
        ? values.filter((v) => labelOf(v).toLowerCase().includes(needle))
        : values;
      list.replaceChildren();
      const head = row(needle ? "(Select all search results)" : "(Select all)",
                       false, (on) => {
        shown.forEach((v) => on ? chosen.add(v) : chosen.delete(v));
        render();
      }, true);
      master = head.querySelector("input");
      list.append(head);
      // Bounded on purpose: a menu of 3,000 product names is a list nobody
      // scrolls. Search narrows it; the count says what is hidden.
      shown.slice(0, 500).forEach((v) => list.append(
        row(labelOf(v), chosen.has(v), (on) => {
          on ? chosen.add(v) : chosen.delete(v);
          syncHead();
        })));
      if (shown.length > 500) {
        const more = document.createElement("p");
        more.className = "hint";
        more.textContent = (shown.length - 500).toLocaleString() +
          " more — type to narrow the list";
        list.append(more);
      }
      if (!shown.length) {
        const none = document.createElement("p");
        none.className = "hint";
        none.textContent = "No value matches this search.";
        list.append(none);
      }
      syncHead();
    }

    // TYPING EMPTIES THE SELECTION (the owner's ask, 2026-07-28). Searching used
    // to narrow only what was DRAWN: the two matching values sat in front of you
    // with every unseen value still ticked behind them, so Apply filtered
    // nothing at all and the box looked broken. Entering a search now means
    // "start from nothing and pick out of these". Emptying the box again puts
    // back what was ticked before it, so a mistyped search costs nothing —
    // unless something was picked while searching, which is an answer, not an
    // accident, and is kept.
    let searching = false;
    let beforeSearch = null;
    search.addEventListener("input", () => {
      const now = search.value.trim() !== "";
      if (now && !searching) {
        beforeSearch = new Set(chosen);
        chosen.clear();
      } else if (!now && searching) {
        if (!chosen.size && beforeSearch) beforeSearch.forEach((v) => chosen.add(v));
        beforeSearch = null;
      }
      searching = now;
      render();
    });
    render();

    apply.addEventListener("click", () => {
      if (!chosen.size) return;
      if (chosen.size === values.length) active.delete(field);
      else active.set(field, {values: [...chosen]});
      applyFilters();
      document.body.click();          // dismiss the popup
    });
    reset.addEventListener("click", () => {
      active.delete(field);
      applyFilters();
      document.body.click();
    });
    box.append(count, actions);
    return box;
  }

  // ---- the three-dot menu ---------------------------------------------------
  function menuLabel(iconName, labelText) {
    const label = document.createElement("span");
    label.className = "grid-menu-label";
    const words = document.createElement("span");
    words.textContent = labelText;
    // "" means "no icon here" — pinMenu marks the ACTIVE pin state with a
    // check and leaves the others blank. The strict icon validator rightly
    // rejects an empty NAME, but rejecting it here threw inside columnMenu
    // and took the whole three-dot menu down with it, on every column. A
    // spacer keeps the blank rows aligned with their iconed siblings.
    const glyph = iconName
      ? materialIconElement(iconName, "grid-menu-icon")
      : Object.assign(document.createElement("span"),
                      {className: "sx-icon material-icon grid-menu-icon"});
    label.append(glyph, words);
    return label;
  }

  function pinMenu(field) {
    const side = pinned.get(field) || "";
    return [
      {label: menuLabel(side ? "" : "check", "No Pin"), action: () => setPinned(field, "")},
      {label: menuLabel(side === "left" ? "check" : "", "Pin Left"),
       action: () => setPinned(field, "left")},
      {label: menuLabel(side === "right" ? "check" : "", "Pin Right"),
       action: () => setPinned(field, "right")},
    ];
  }

  function columnMenu(event, column) {
    const field = column.getField();
    const title = text(column.getDefinition().title || field);
    const groupLevel = groupedBy.indexOf(field);
    const groupLabel = groupLevel >= 0
      ? "Remove " + title + " from Row Groups"
      : groupedBy.length
        ? "Add " + title + " as Group Level " + (groupedBy.length + 1)
        : "Group by " + title;
    const menu = [
      {label: menuLabel("arrow-upward", "Sort Ascending"),
       action: () => column.getTable().setSort(field, "asc")},
      {label: menuLabel("arrow-downward", "Sort Descending"),
       action: () => column.getTable().setSort(field, "desc")},
      {separator: true},
      {label: menuLabel("push-pin", "Pin Column"), menu: pinMenu(field)},
      {separator: true},
      // The owner's wording.
      {label: menuLabel("fit-screen", "Auto-fit column width"), action: () => autosize(field)},
      {label: menuLabel("unfold-more", "Auto-fit all column widths"), action: autosizeAll},
      {separator: true},
      {label: menuLabel(groupLevel >= 0 ? "check" : "view-stream", groupLabel),
       action: () => setGroup(field), disabled: !features.tree},
    ];
    if (groupedBy.length) {
      menu.push({label: menuLabel("view-stream", "Un-Group All"),
                 action: () => setGroup("")});
    }
    menu.push(
      {label: menuLabel(treeBy === field ? "check" : "account-tree", "Nest rows by this column"),
       action: () => setTree(treeBy === field ? "" : field), disabled: !features.rows},
      {separator: true},
      {label: menuLabel("view-column", "Choose Columns"), action: openColumnChooser},
      {label: menuLabel("restart-alt", "Reset Columns"), action: resetColumns}
    );
    if (groupedBy.length) {
      menu.push(
        {label: menuLabel("unfold-more", "Expand All Row Groups"),
         action: () => setAllGroupsOpen(true)},
        {label: menuLabel("unfold-less", "Collapse All Row Groups"),
         action: () => setAllGroupsOpen(false)}
      );
    }
    return menu;
  }

  function setAllGroupsOpen(open) {
    if (!table) return;
    function visit(group) {
      const children = typeof group.getSubGroups === "function" ? group.getSubGroups() : [];
      if (open) group.show();
      children.forEach(visit);
      if (!open) group.hide();
    }
    table.getGroups().forEach(visit);
  }

  // Pinning is fixed at construction time. A map keeps left and right distinct;
  // Tabulator treats frozen columns before the first normal column as left and
  // frozen columns after it as right, so build() orders those three bands.
  const pinned = new Map();
  const widths = new Map();
  // Carried across build()'s destroy/recreate, in initialSort's own shape.
  let sorters = [];
  let autosizeRequest = 0;

  function setPinned(field, side) {
    side ? pinned.set(field, side) : pinned.delete(field);
    build();
  }

  // Tabulator's fit-to-data calculation only considers the cells reliably. A
  // short column with a long title can therefore end up with an ellipsised
  // header after autosize. Measure the title and all of its visible controls as
  // flex items, including the gaps and the header padding, so the result fits
  // whichever is wider: the data or the complete header.
  function measureHeaderWidth(column) {
    const header = column.getElement && column.getElement();
    if (!header) return 0;
    const content = header.querySelector(".tabulator-col-content");
    const titleHolder = header.querySelector(".tabulator-col-title-holder");
    const label = header.querySelector(".grid-header-label");
    if (!content || !titleHolder || !label) return 0;

    const contentStyle = getComputedStyle(content);
    const holderStyle = getComputedStyle(titleHolder);
    const padding = (parseFloat(contentStyle.paddingInlineStart) || 0) +
                    (parseFloat(contentStyle.paddingInlineEnd) || 0);
    const gap = parseFloat(holderStyle.columnGap || holderStyle.gap) || 0;
    const items = Array.from(titleHolder.querySelectorAll(
      ":scope > .tabulator-col-title > *, :scope > .tabulator-col-sorter"
    ));
    const itemWidth = items.reduce((total, item) => {
      if (item === label) return total + Math.max(label.scrollWidth, label.getBoundingClientRect().width);
      return total + item.getBoundingClientRect().width;
    }, 0);
    return Math.ceil(padding + itemWidth + gap * Math.max(0, items.length - 1));
  }

  // Autosize must run after BOTH Tabulator and the browser have painted the
  // stable viewport. Measuring synchronously sometimes caught the old width;
  // fitColumns then immediately redistributed that provisional value and made
  // the command look random. The measured number is applied again explicitly,
  // so later fitColumns passes treat it as an owner's width rather than flex.
  function autosizeColumns(fields) {
    if (!table) return;
    const request = ++autosizeRequest;
    // A HIDDEN column cannot be measured. Its header carries display:none, so
    // every rectangle measureHeaderWidth reads comes back zero and
    // setWidth(true) has no rendered content to fit to. Measuring one anyway
    // produced the floor — 128px — and then RECORDED that as a width the owner
    // had chosen. So "Auto-fit all column widths" pinned the hidden AR name
    // column at 128 while every column beside it went to 182 and beyond, and
    // switching the language later revealed "Pr…" sitting among them: the
    // owner's report, on GPP_ENERGY, reproduced exactly. A column nobody can
    // see is left alone, keeping its flexible width until it is on screen and
    // can answer for itself.
    const measurable = fields.filter((field) => {
      const column = table.getColumn(field);
      return column && column.isVisible() &&
             column.getDefinition().resizable !== false;
    });
    if (!measurable.length) return;
    measurable.forEach((field) => widths.delete(field));
    table.redraw(true);
    // A TIMER, not requestAnimationFrame. rAF never fires while the tab is
    // hidden or the window is occluded/throttled — the measurement was
    // parked indefinitely and the command did nothing at all, which is the
    // other half of "sometimes it does not work". A timer always fires,
    // and 50ms is comfortably past the redraw it waits for.
    setTimeout(() => {
      if (!table || request !== autosizeRequest) return;
      measurable.forEach((field) => {
        const column = table.getColumn(field);
        if (!column || !column.isVisible()) return;
        column.setWidth(true);
        const measured = Math.max(
          GRID_MIN_COLUMN_WIDTH,
          Math.ceil(column.getWidth()),
          measureHeaderWidth(column)
        );
        column.setWidth(measured);
        widths.set(field, measured);
      });
      // A rebuild, not a redraw: the measured widths enter the column
      // DEFINITIONS (width + widthGrow 0), which is the only place a
      // fitColumns layout can never override them. redraw(false) left the
      // width as a live-table property that the next layout pass — a
      // window resize, a toggle, new data — re-stretched at will.
      build();
    }, 50);
  }
  function autosize(field) { autosizeColumns([field]); }
  function autosizeAll() {
    if (!table) return;
    autosizeColumns(table.getColumns().map((column) => column.getField()).filter(Boolean));
  }

  let chooserSaveQueue = Promise.resolve();
  let chooserSaveError = null;

  function updateFields(body) {
    chooserSaveQueue = chooserSaveQueue.catch(() => {}).then(async () => {
      const response = await fetch("/api/fields/" + encodeURIComponent(SOURCE), {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      chooserSaveError = null;
      return response.json();
    }).catch((error) => {
      chooserSaveError = error;
      throw error;
    });
    return chooserSaveQueue;
  }

  function openColumnChooser() {
    const existing = document.querySelector(".column-chooser-backdrop");
    if (existing) {
      const search = existing.querySelector("input[type=search]");
      if (search) search.focus();
      return;
    }

    let fields = [];
    let draggedKey = "";
    let dirty = false;
    let closing = false;
    chooserSaveQueue = Promise.resolve();
    chooserSaveError = null;

    const backdrop = document.createElement("div");
    backdrop.className = "column-chooser-backdrop";
    const panel = document.createElement("aside");
    panel.className = "column-chooser";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "column-chooser-title");

    const header = document.createElement("header");
    header.className = "column-chooser-header";
    const heading = document.createElement("h2");
    heading.id = "column-chooser-title";
    heading.textContent = "Choose Columns";
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "column-chooser-close";
    closeButton.setAttribute("aria-label", "Close column chooser");
    closeButton.append(materialIconElement("close", "column-chooser-icon"));
    header.append(heading, closeButton);

    const controls = document.createElement("div");
    controls.className = "column-chooser-controls";
    const selectAll = document.createElement("input");
    selectAll.type = "checkbox";
    selectAll.setAttribute("aria-label", "Show all columns");
    const searchBox = document.createElement("label");
    searchBox.className = "column-chooser-search";
    searchBox.append(materialIconElement("search", "column-chooser-icon"));
    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Search columns";
    search.setAttribute("aria-label", "Search columns");
    searchBox.append(search);
    controls.append(selectAll, searchBox);

    // TWO zones, because the owner's question about a field is not "is it
    // ticked" but "where does it live": in the table, or in the record's
    // details. Dragging between them IS the move (and the checkbox stays as
    // its keyboard-and-screen-reader equivalent, never a second mechanism —
    // both write the same is_hidden through the same endpoint).
    const list = document.createElement("div");
    list.className = "column-chooser-list";
    list.setAttribute("role", "list");
    const zones = {};
    for (const [zone, title, hint] of [
      ["table", "In the table", "Columns of the grid, in this order."],
      ["details", "In the details", "Shown under the table when a row is selected."],
    ]) {
      const section = document.createElement("section");
      section.className = "column-chooser-zone";
      section.dataset.zone = zone;
      const label = document.createElement("h3");
      label.textContent = title;
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = hint;
      const body = document.createElement("div");
      body.className = "column-chooser-zone-body";
      body.dataset.zoneBody = zone;
      section.append(label, note, body);
      list.append(section);
      zones[zone] = body;
    }
    // A THIRD zone, for facts that are not columns yet. Madar's export already
    // carries 64 columns pivoted straight out of the details table, because
    // Magento publishes its facet list and those rows get flagged. Sika's shop
    // publishes no facets, so none of its 18 attribute codes could ever rise —
    // the machine was never the obstacle, the owner just had no say in it.
    const promoteZone = document.createElement("section");
    promoteZone.className = "column-chooser-zone";
    promoteZone.dataset.zone = "promote";
    promoteZone.hidden = true;
    const promoteTitle = document.createElement("h3");
    promoteTitle.textContent = "Details you can promote";
    const promoteHint = document.createElement("p");
    promoteHint.className = "muted";
    promoteHint.textContent =
      "Facts this source publishes that are not columns yet. Tick one to make it " +
      "a real column, in the table and the export. Untick to send it back.";
    const promoteBody = document.createElement("div");
    promoteBody.className = "column-chooser-zone-body";
    promoteZone.append(promoteTitle, promoteHint, promoteBody);
    list.append(promoteZone);

    function renderPromotable(attributes) {
      promoteBody.replaceChildren();
      const offer = (attributes || []).filter((a) => !a.by_the_site);
      promoteZone.hidden = offer.length === 0;
      for (const attribute of offer) {
        const row = document.createElement("label");
        // Its OWN grid. .column-chooser-row lays out three tracks for a row
        // that drags — checkbox, a 2rem handle, then the name — and these rows
        // have no handle, so the label was being squeezed into the 2rem track
        // and printed straight over the count beside it ("Image577 of 763").
        row.className = "column-chooser-row column-chooser-promote-row";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.checked = !!attribute.promoted;
        const name = document.createElement("span");
        name.className = "column-chooser-name";
        name.dir = "auto";
        name.textContent = attribute.label;
        // The count BEFORE the choice: an attribute two products carry is a
        // column of blanks, and that is worth seeing in advance, not after.
        const count = document.createElement("span");
        count.className = "muted column-chooser-count";
        count.textContent = `${attribute.products} of ${attribute.of_products}`;
        box.addEventListener("change", () => {
          box.disabled = true;
          status.textContent = "Saving…";
          fetch("/api/promotable/" + encodeURIComponent(SOURCE), {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({attribute_code: attribute.attribute_code,
                                  promote: box.checked}),
          }).then((response) => {
            if (!response.ok) throw new Error("promote failed");
            return response.json();
          }).then((body) => {
            dirty = true;
            attribute.promoted = box.checked;
            renderPromotable(body.attributes);
            status.textContent = "Saved. Close to refresh the grid.";
          }).catch(() => {
            box.checked = !box.checked;
            status.textContent = "Could not change that column. Try again.";
          }).finally(() => { box.disabled = false; });
        });
        row.append(box, name, count);
        promoteBody.append(row);
      }
    }

    fetch("/api/promotable/" + encodeURIComponent(SOURCE))
      .then((response) => (response.ok ? response.json() : {attributes: []}))
      .then((body) => renderPromotable(body.attributes))
      .catch(() => { promoteZone.hidden = true; });

    const status = document.createElement("p");
    status.className = "column-chooser-status muted";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = "Loading columns…";
    panel.append(header, controls, list, status);
    backdrop.append(panel);
    document.body.append(backdrop);

    function fieldLabel(field) {
      const tableColumn = payload.columns.find((column) => column.key === field.field_key);
      const raw = text(field.display_name || (tableColumn && tableColumn.label) ||
                       field.label || field.original_name || field.field_key);
      // Hidden columns are absent from payload.columns, and many connectors use
      // machine keys as their original names. Humanise only that fallback; an
      // explicit display name remains exactly what the owner wrote.
      if (field.display_name || tableColumn) return raw;
      return raw.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
    }

    function syncMasterCheckbox() {
      const visible = fields.filter((field) => !field.is_hidden).length;
      selectAll.checked = fields.length > 0 && visible === fields.length;
      selectAll.indeterminate = visible > 0 && visible < fields.length;
    }

    function saySaving(promise) {
      status.textContent = "Saving…";
      promise.then(() => {
        if (!chooserSaveError) status.textContent = "Saved. Close to refresh the grid.";
      }).catch(() => {
        status.textContent = "Could not save the column changes. Try again.";
      });
    }

    function saveOrder() {
      dirty = true;
      saySaving(updateFields({order: fields.map((field) => field.field_key)}));
    }

    function moveField(key, targetKey, after) {
      if (!key || key === targetKey) return;
      const from = fields.findIndex((field) => field.field_key === key);
      if (from < 0) return;
      const moved = fields.splice(from, 1)[0];
      let to = fields.findIndex((field) => field.field_key === targetKey);
      if (to < 0) { fields.splice(from, 0, moved); return; }
      if (after) to += 1;
      fields.splice(to, 0, moved);
      saveOrder();
      render();
    }

    function moveToZone(key, zone) {
      const field = fields.find((item) => item.field_key === key);
      if (!field) return;
      const hidden = zone === "details";
      if (field.is_hidden === hidden) return;
      field.is_hidden = hidden;
      dirty = true;
      syncMasterCheckbox();
      saySaving(updateFields({field_key: key, hidden}));
      render();
    }

    function render() {
      const query = search.value.trim().toLocaleLowerCase();
      Object.values(zones).forEach((body) => body.replaceChildren());
      const matching = fields.filter((field) =>
        !query || fieldLabel(field).toLocaleLowerCase().includes(query));
      matching.forEach((field) => {
        const row = document.createElement("div");
        row.className = "column-chooser-row";
        row.dataset.field = field.field_key;
        row.draggable = true;
        row.setAttribute("role", "listitem");

        const visible = document.createElement("input");
        visible.type = "checkbox";
        visible.checked = !field.is_hidden;
        visible.setAttribute("aria-label", "Keep " + fieldLabel(field) + " in the table");
        visible.addEventListener("change", () =>
          moveToZone(field.field_key, visible.checked ? "table" : "details"));

        const handle = document.createElement("button");
        handle.type = "button";
        handle.className = "column-chooser-handle";
        handle.setAttribute("aria-label", "Move " + fieldLabel(field));
        handle.title = "Drag to reorder, or between the two lists to move this "
          + "field. Keyboard: Arrow Up/Down to reorder, Arrow Left/Right to move.";
        handle.append(materialIconElement("drag-indicator", "column-chooser-icon"));
        handle.addEventListener("keydown", (event) => {
          // Across the zones with Left/Right — the same move the drag makes,
          // for a keyboard. A control only a mouse can reach is not a control.
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            moveToZone(field.field_key, event.key === "ArrowLeft" ? "table" : "details");
            return;
          }
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
          event.preventDefault();
          const at = fields.indexOf(field);
          const target = fields[at + (event.key === "ArrowUp" ? -1 : 1)];
          if (!target) return;
          moveField(field.field_key, target.field_key, event.key === "ArrowDown");
          const movedHandle = [...list.querySelectorAll(".column-chooser-row")]
            .find((item) => item.dataset.field === field.field_key)?.querySelector("button");
          if (movedHandle) movedHandle.focus();
        });

        const name = document.createElement("span");
        name.className = "column-chooser-name";
        name.textContent = fieldLabel(field);
        row.append(visible, handle, name);
        row.addEventListener("dragstart", (event) => {
          draggedKey = field.field_key;
          row.classList.add("is-dragging");
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", draggedKey);
        });
        row.addEventListener("dragover", (event) => {
          if (!draggedKey || draggedKey === field.field_key) return;
          event.preventDefault();
          row.classList.toggle("drop-after", event.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2);
          row.classList.toggle("drop-before", !row.classList.contains("drop-after"));
        });
        row.addEventListener("dragleave", () => row.classList.remove("drop-before", "drop-after"));
        row.addEventListener("drop", (event) => {
          event.preventDefault();
          const after = event.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2;
          const dragged = fields.find((item) => item.field_key === draggedKey);
          const key = draggedKey;
          draggedKey = "";
          if (dragged && dragged.is_hidden !== field.is_hidden) {
            // Dropped among the OTHER zone's rows: that is the move, and the
            // position within the zone follows from the order save below.
            moveToZone(key, field.is_hidden ? "details" : "table");
          }
          moveField(key, field.field_key, after);
        });
        row.addEventListener("dragend", () => {
          draggedKey = "";
          list.querySelectorAll(".column-chooser-row").forEach((item) =>
            item.classList.remove("is-dragging", "drop-before", "drop-after"));
        });
        zones[field.is_hidden ? "details" : "table"].append(row);
      });
      for (const [zone, body] of Object.entries(zones)) {
        if (body.children.length) continue;
        const empty = document.createElement("p");
        empty.className = "column-chooser-empty muted";
        empty.textContent = query ? "No columns match this search."
          : zone === "details" ? "Drag a column here to move it out of the table."
          : "Every column is in the details.";
        body.append(empty);
      }
      syncMasterCheckbox();
    }

    // Dropping on the ZONE (not on a row) is how an empty list — and the space
    // below the last row — accepts a field.
    for (const [zone, body] of Object.entries(zones)) {
      body.addEventListener("dragover", (event) => {
        if (!draggedKey) return;
        event.preventDefault();
        body.classList.add("is-drop-target");
      });
      body.addEventListener("dragleave", () => body.classList.remove("is-drop-target"));
      body.addEventListener("drop", (event) => {
        event.preventDefault();
        body.classList.remove("is-drop-target");
        const key = draggedKey;
        draggedKey = "";
        moveToZone(key, zone);
      });
    }

    async function closeChooser() {
      if (closing) return;
      closing = true;
      closeButton.disabled = true;
      if (dirty) status.textContent = "Finishing changes…";
      try { await chooserSaveQueue; } catch (error) {
        closing = false;
        closeButton.disabled = false;
        status.textContent = "Could not save the column changes. Try again.";
        return;
      }
      document.removeEventListener("keydown", escapeChooser);
      if (dirty) location.reload();
      else backdrop.remove();
    }

    function escapeChooser(event) {
      if (event.key === "Escape") closeChooser();
    }
    closeButton.addEventListener("click", closeChooser);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeChooser();
    });
    document.addEventListener("keydown", escapeChooser);
    search.addEventListener("input", render);
    selectAll.addEventListener("change", () => {
      const hidden = !selectAll.checked;
      fields.filter((field) => field.is_hidden !== hidden).forEach((field) => {
        field.is_hidden = hidden;
        dirty = true;
        saySaving(updateFields({field_key: field.field_key, hidden: hidden}));
      });
      render();
    });

    fetch("/api/fields/" + encodeURIComponent(SOURCE))
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("HTTP " + response.status)))
      .then((data) => {
        if (!document.body.contains(panel)) return;
        fields = (data.fields || []).map((field) => Object.assign({}, field));
        status.textContent = fields.length ? "Drag columns to reorder them." : "No columns are available.";
        render();
        search.focus();
      })
      .catch(() => { status.textContent = "Could not load the columns. Try again."; });
  }

  function resetColumns() {
    pinned.clear();
    widths.clear();
    groupedBy = [];
    treeBy = "";
    // Clear the BROWSER's memory too. A reset that only wrote to the server is
    // how a hidden column became unrecoverable in the first place.
    try {
      localStorage.removeItem(GROUP_KEY);
      localStorage.removeItem(TREE_KEY);
      localStorage.removeItem("tabulator-scrapex-" + SOURCE + "-columns");
      localStorage.removeItem("tabulator-scrapex-" + SOURCE + "-sort");
      localStorage.removeItem("tabulator-" + PERSISTENCE_ID + "-columns");
      // The keys this page used before the vocabulary sweep bumped them.
      // Left behind they are harmless but permanent — a reset that leaves
      // orphans is not a reset.
      localStorage.removeItem("scrapex-groupby-" + SOURCE);
      localStorage.removeItem("scrapex-treeby-" + SOURCE);
      localStorage.removeItem("tabulator-scrapex-grid-v2-" + SOURCE + "-columns");
    } catch (err) { /* nothing to clear */ }
    fetch("/api/fields/" + encodeURIComponent(SOURCE), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({reset: true}),
    }).then(() => location.reload()).catch(() => location.reload());
  }

  function remember(field, hidden) {
    // Hiding persists through the SAME endpoint the side panel uses, so the
    // choice survives a reload instead of living only in this tab.
    return fetch("/api/fields/" + encodeURIComponent(SOURCE), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({field_key: field, hidden: hidden}),
    }).catch(() => {});
  }

  // ---- cell rendering: the meaning earlier slices established ---------------
  /** Add "(n)" to a tree HEADING's cell, leaving every real row untouched.
   *
   * The count is the one thing a heading can state truthfully — its other cells
   * are empty precisely because no single value stands for the set. Without it
   * a closed branch gives no reason to open it.
   */
  function branchCount(inner) {
    return (cell, params, done) => {
      const branch = cell.getRow().getData()._branch;
      const body = inner ? inner(cell, params, done) : text(cell.getValue());
      if (!branch) return body;
      const wrap = document.createElement("span");
      wrap.dir = "auto";
      if (body instanceof Node) wrap.append(body);
      else wrap.append(document.createTextNode(String(body == null ? "" : body)));
      const count = document.createElement("span");
      count.className = "muted";
      count.textContent = " (" + branch.toLocaleString() + ")";
      wrap.append(count);
      return wrap;
    };
  }

  function formatterFor(key) {
    if (key === "product_name_ar" || key === "variant_ar" ||
        key === "product_name" || key === "variant") {
      return (cell) => {
        const span = document.createElement("span");
        span.dir = "auto";
        span.textContent = text(cell.getValue());
        return span;
      };
    }
    if (key === "country_code_alpha2") {
      return (cell) => {
        const row = cell.getRow().getData();
        const span = document.createElement("span");
        span.textContent = row.country || row.country_code_alpha2 || "—";
        if (row.country && row.country_code_alpha2) {
          const code = document.createElement("span");
          code.className = "code";
          code.textContent = row.country_code_alpha2;
          span.append(code);
        }
        return span;
      };
    }
    if (key === "price") {
      return (cell) => {
        const row = cell.getRow().getData();
        const box = document.createElement("span");
        const price = document.createElement("span");
        price.className = "price";
        price.textContent = formatMoney(cell.getValue()) + " " + text(row.currency);
        box.append(price);
        // A price may lose its column but never its unit.
        if (row.unit) {
          const per = document.createElement("span");
          per.className = "per";
          per.textContent = " / " + row.unit;
          box.append(per);
        }
        // The price before the discount, struck through beside the current one
        // — the owner's asked-for shape. <s> is structural, so a screen reader
        // announces it as deleted text rather than relying on the strike line.
        if (row.was_price) {
          const was = document.createElement("s");
          was.className = "muted";
          was.dir = "ltr";
          was.textContent = " " + formatMoney(row.was_price) + " " + text(row.currency);
          was.title = "Price before the discount";
          box.append(was);
        }
        return box;
      };
    }
    if (key === "tax") {
      // The verdict travels once per distinct (region, material) pair and each
      // row carries only an index. Keyed by region alone, gasoline and
      // natural-gas rows wore the diesel page's link — the owner's report.
      return (cell) => {
        const state = (payload.tax_states || [])[cell.getRow().getData().tax_ref] || {};
        // A verdict WITH a statement is clickable — it opens the page the
        // sentence lives on, wearing the amber-underline signature. A verdict
        // with nothing to open is plain words: same colour family for the
        // unverified state, but no underline, because underline means "press
        // me" on this page and nothing may wear it idly (owner rule).
        // WHERE the link goes (owner's report 2026-07-25: "the link showing
        // excl. 14% is fixed, and each product surely has its own"). The rule
        // is per region, but the PROOF is per product: sika's 14% appears when
        // you open THIS item's page and put it in the cart, so a single
        // shop-wide cart URL on 87 rows sends the owner to a page that says
        // nothing about the row they clicked. The row's own product page wins;
        // the rule's published statement is the fallback for a source whose
        // evidence really is one page (a fuel authority's tax notice), and the
        // tooltip always names which of the two you are about to open.
        const rowData = cell.getRow().getData();
        const candidates = [[rowData.product_link, "this product's own page"],
                            [state.tax_statement, "the source's own statement"]];
        let safe = "";
        let what = "";
        for (const [candidate, describes] of candidates) {
          try {
            const parsed = new URL(candidate || "");
            if (parsed.protocol === "http:" || parsed.protocol === "https:") {
              safe = parsed.href;
              what = describes;
              break;
            }
          } catch (err) { /* try the next one */ }
        }
        if (safe) {
          const link = document.createElement("a");
          link.className = "grid-action";
          link.href = safe;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = state.tax_short || "—";
          link.title = (state.tax || "") + " — open " + what;
          return link;
        }
        const span = document.createElement("span");
        span.textContent = state.tax_short || "—";
        span.title = state.tax || "";
        if (state.tax_verified === false) span.className = "unverified";
        return span;
      };
    }
    if (key === "availability") {
      return (cell) => {
        const value = text(cell.getValue());
        const badge = document.createElement("span");
        // Status is spelled out, never carried by colour alone.
        badge.className = "badge" + (value === "in_stock" ? " ok"
                                   : value === "out_of_stock" ? " off" : "");
        badge.textContent = value === "in_stock" ? "In stock"
                          : value === "out_of_stock" ? "Out of stock" : "Unknown";
        return badge;
      };
    }
    if (key === "price_usd") {
      // The owner's standing rule (2026-07-26): a converted number is NEVER
      // shown without the rate used AND the date of that rate. The cell used to
      // print a bare figure, which is the number pretending to be a fact.
      return (cell) => {
        const span = document.createElement("span");
        span.dir = "ltr";
        span.textContent = formatMoney(cell.getValue());
        const row = cell.getRow().getData();
        if (row.usd_rate) {
          const at = row.usd_rate_as_of ? " on " + row.usd_rate_as_of : "";
          const via = row.usd_rate_source === "google_finance"
            ? " (google.com/finance)" : "";
          span.title = "converted at " + row.usd_rate + " " +
            (row.currency || "") + " per USD" + at + via;
          span.classList.add("has-rate-note");
        } else if (cell.getValue()) {
          // A figure with no rate behind it cannot be explained, so it is not
          // shown as one.
          span.title = "no exchange rate recorded for this currency";
        }
        return span;
      };
    }
    if (key === "price_trade") {
      // The trade tier is a price and has to read like one. It reached
      // BROWSE_COLUMNS without ever reaching this file, so on the sources that
      // quote one it would render as a bare left-aligned "1433.39" beside a
      // Price cell reading "1,433.39 EGP / liter" — the same quantity twice,
      // looking like two different kinds of thing. No source in the workspace
      // publishes it today, so this is written from the column's definition
      // rather than from a row on screen.
      return (cell) => {
        const value = cell.getValue();
        if (value === "" || value === null || value === undefined) return "";
        const row = cell.getRow().getData();
        const span = document.createElement("span");
        span.dir = "ltr";
        span.textContent = formatMoney(value) + (row.currency ? " " + text(row.currency) : "") +
          (row.unit ? " / " + row.unit : "");
        return span;
      };
    }
    if (key === "price_previous" || key === "price_min" || key === "price_max") {
      return (cell) => {
        const span = document.createElement("span");
        span.dir = "ltr";
        span.textContent = formatMoney(cell.getValue());
        return span;
      };
    }
    if (key === "price_change") {
      return (cell) => {
        const span = document.createElement("span");
        span.dir = "ltr";
        // Server-computed "+5.00 (+32.3%)" uses the workspace convention too.
        span.textContent = String(cell.getValue() || "").replace(
          /-?\d+\.\d+/g, (m) => formatMoney(m));
        return span;
      };
    }
    if (key === "discount" || key === "discount_pct") {
      // TWO columns, as the export has always had: the amount saved and the
      // percentage. One cell reading "-84.67 (-7.0%)" could be sorted by
      // neither, which is the only reason a column exists (owner's ask). The
      // server sends both numbers; this only renders them.
      return (cell) => {
        const value = cell.getValue();
        if (value === "" || value === null || value === undefined) return "";
        const span = document.createElement("span");
        span.dir = "ltr";
        span.textContent = key === "discount_pct"
          ? String(value).replace(",", ".") + "%"
          : formatMoney(value);
        return span;
      };
    }
    if (key === "product_link") {
      // The arrow the owner missed: straight to the record on the site.
      return (cell) => {
        // product_link is already the most specific address the server has for
        // this row — the variation's own page where the source publishes one.
        // The grid does not choose; it opens what the row was given.
        const url = cell.getRow().getData().product_link;
        if (!url) return "";
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.className = "grid-action";
        link.title = "Open this record on the site";
        link.insertAdjacentHTML("beforeend", materialIcon("open-in-new", "inline-icon"));
        return link;
      };
    }
    if (key === "official_source") {
      // The official body the SOURCE names for its figure — scraped content,
      // so it is set as textContent (never HTML) and the URL becomes a link
      // only when it parses as http(s); anything else renders as plain text.
      return (cell) => {
        const name = text(cell.getValue());
        if (!name) return "";
        const data = cell.getRow().getData();
        const url = text(data.official_source_link);
        let safe = "";
        try {
          const parsed = new URL(url);
          if (parsed.protocol === "http:" || parsed.protocol === "https:") safe = parsed.href;
        } catch (err) { /* not a URL — show the name without a link */ }
        if (!safe) {
          const span = document.createElement("span");
          span.dir = "auto";
          span.textContent = name;
          return span;
        }
        const link = document.createElement("a");
        link.className = "grid-action";
        link.href = safe;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.dir = "auto";
        link.textContent = name;
        link.title = safe;
        return link;
      };
    }
    return undefined;
  }

  // A real element around the title lets CSS place the four header parts as
  // four intentional flex items: label, sort arrow, filter, menu. Tabulator
  // otherwise leaves the label as an anonymous text node and absolutely parks
  // the sorter at the far edge, where it reads as detached from the label.
  function headerLabel(cell) {
    const label = document.createElement("span");
    label.className = "grid-header-label";
    // Tabulator substitutes the literal string "&nbsp;" for an empty column
    // title, to keep the header row's height. Setting that through textContent
    // printed those six characters as the heading of the arrow column — the
    // owner read "&nbsp;" above the link to the product. That column has no
    // title on purpose, so an empty title stays empty.
    const value = text(cell.getValue());
    label.textContent = value === "&nbsp;" ? "" : value;
    return label;
  }

  function build() {
    if (table) { widthsFromTable(); sortFromTable(); table.destroy(); table = null; }

    // A column can be hidden from Choose Columns while it is part of a saved
    // hierarchy. Drop only unavailable levels; the remaining levels keep their
    // order and still form a valid group rather than making Tabulator group by
    // a field that is no longer in the table.
    const availableFields = new Set(payload.columns.map((column) => column.key));
    const validGroups = groupedBy.filter((field) => availableFields.has(field));
    // treeBy went through no such filter. A renamed or absent field made
    // nest() bucket every row under "" — one branch, blank heading.
    if (treeBy && !availableFields.has(treeBy)) { treeBy = ""; remember_(TREE_KEY, ""); }
    // Whichever name column this source fills; the other is legitimately
    // absent when the site publishes one language.
    const nameField = availableFields.has("product_name") ? "product_name"
                                                          : "product_name_ar";
    if (validGroups.length !== groupedBy.length) {
      groupedBy = validGroups;
      rememberGroups();
    }

    const columns = payload.columns.map((col) => {
      const def = {
        title: col.label,
        field: col.key,
        headerMenu: columnMenu,
        headerMenuIcon: MENU_ICON,
        headerFilter: false,
        headerPopup: filterPopup,
        headerPopupIcon: FILTER_ICON,
        resizable: true,
        headerSort: true,
        // The third click removes the sorter. With no active sorter Tabulator
        // renders the rows in the payload's original order again.
        headerSortTristate: true,
        // Empties sort LAST in both directions, on every column. Without this
        // a sparse column (Unit holds 89 values across 3,398 madar rows)
        // floods the first screens with blanks on ascending sort — the owner
        // read that, reasonably, as "sorting does not work".
        sorterParams: {alignEmptyValues: "bottom"},
        // A ceiling as well as a floor: without one, fitColumns hands a short
        // column like Unit the same share as a long one like Record.
        //
        // And an OWNER'S width opts out of the sharing entirely. This was
        // the whole "Autosize sometimes works" mystery: fitColumns
        // re-stretches every column with widthGrow >= 1 on every layout
        // pass, so an autosized width held only while the columns
        // overflowed the viewport — the moment there was spare room, the
        // very next pass quietly re-inflated it, and the command looked
        // random. A width the owner set (by autosize or by dragging) is a
        // decision, not a suggestion for the layout to spend.
        widthGrow: widths.has(col.key) ? 0
                   : col.key === "product_name" || col.key === "product_name_ar"
                   || col.key === "country_code_alpha2" ? 2 : 1,
      };
      // Numbers and dates read right-aligned; text reads from its own side.
      if (col.key === "price") def.hozAlign = "right";
      if (col.key === "price_changed_on" || col.key === "last_confirmed_on" ||
          col.key === "price_trade" || col.key === "discount" ||
          col.key === "discount_pct" ||
          col.key === "price_usd" || col.key === "price_previous" ||
          col.key === "price_change" || col.key === "price_min" ||
          col.key === "price_max" || col.key === "observations") {
        def.hozAlign = "right";
      }
      // Which sorter, decided from the WHOLE column. This was a hand-written
      // list of key names, and a list of key names rots: the vocabulary sweep
      // renamed columns and any entry that stopped matching silently became a
      // text sort, putting 9 above 11 in exactly the column the entry existed
      // to protect. Left to itself Tabulator is no safer — it guesses by
      // sampling activeRows[0] and nothing else, so a single empty cell at the
      // top of a column of numbers hands the whole column to the text sorter
      // for the rest of the session. Reading the column decides it correctly
      // whatever anything is called.
      def.sorter = sorterFor(col.key);
      if (col.key === "product_link") {
        def.headerSort = false;
        def.download = false;
        def.headerMenu = undefined;
        def.headerPopup = undefined;
        def.width = 56;
        def.resizable = false;
      }
      let formatter = formatterFor(col.key);
      // On the column a tree nests by, a heading row must say how many rows it
      // hides — whichever column that is. Wrapping here rather than teaching
      // every formatter about trees keeps the count in exactly one place.
      if (col.key === treeBy) formatter = branchCount(formatter);
      if (formatter) def.formatter = formatter;
      if (pinned.has(col.key)) def.frozen = true;
      if (widths.has(col.key)) def.width = widths.get(col.key);
      return def;
    });

    // There is NO History column. Selecting a row opens the record underneath,
    // price story included, so a column whose only job was to open the same
    // container was a second door into a room the row already opens (the
    // owner's ruling, and the same reason the Details column went). The full
    // page at /source/<key>/offer/<id> still exists and is still linked from
    // the record's own header, for bookmarking and middle-click.

    if (features.rownum) {
      columns.unshift({title: "#", field: "__n", width: 56, headerSort: false,
                       resizable: false, download: false,
                       formatter: "rownum"});
    }
    if (features.totals) {
      // A total only where a total MEANS something. Summing prices across
      // different currencies and units would be a number with no referent, so
      // the count is what is shown for anything that is not plainly additive.
      columns.forEach((c) => {
        if (c.field === "price") { c.topCalc = "avg"; c.topCalcParams = {precision: 2}; }
        else if (c.field === nameField) c.topCalc = "count";
      });
    }

    // Frozen columns at the outside edges become true left/right pins in
    // Tabulator. Keeping the History action in the middle ensures a right pin
    // really reaches the right edge instead of stopping one column early.
    const orderedColumns = [
      ...columns.filter((column) => pinned.get(column.field) === "left"),
      ...columns.filter((column) => !pinned.has(column.field)),
      ...columns.filter((column) => pinned.get(column.field) === "right"),
    ];

    // Selecting several rows was already possible and had NO affordance saying
    // so: no checkbox, no select-all, and clicking a second row looked like it
    // had replaced the first. A visible box per row (and one in the header for
    // all of them) is what makes multi-select a feature instead of a secret.
    if (features.select) {
      orderedColumns.unshift({
        formatter: "rowSelection", titleFormatter: "rowSelection",
        hozAlign: "center", headerHozAlign: "center", headerSort: false,
        width: 44, minWidth: 44, resizable: false, download: false, frozen: true,
        cssClass: "grid-select-column",
        headerMenu: undefined, headerPopup: undefined,
      });
    }

    // A compact summary belongs inside the table frame, not as another toolbar
    // below it. Build it with DOM nodes so the counts remain text-only and the
    // theme can style the shape without inheriting Tabulator's hardcoded skin.
    const footer = document.createElement("div");
    footer.className = "grid-footer-summary";
    footer.setAttribute("role", "status");
    footer.setAttribute("aria-live", "polite");
    function footerStat(labelText) {
      const stat = document.createElement("span");
      stat.className = "grid-footer-stat";
      const label = document.createElement("span");
      label.className = "grid-footer-label";
      label.textContent = labelText + ":";
      const value = document.createElement("strong");
      value.className = "grid-footer-value";
      value.textContent = "0";
      stat.append(label, value);
      footer.append(stat);
      return {stat, value};
    }
    const footerTotal = footerStat("Total Rows");
    const footerSelected = footerStat("Selected");
    function updateFooter() {
      if (!table) return;
      const selected = table.getSelectedRows().length;
      footerTotal.value.textContent = table.getDataCount("active").toLocaleString();
      footerSelected.value.textContent = selected.toLocaleString();
      footerSelected.stat.hidden = selected === 0;
    }

    const options = {
      data: payload.rows,
      columns: orderedColumns,
      // fitColumns, not fitDataStretch: the table should fill the width it has
      // and no more. fitDataStretch sized every column to its widest possible
      // content and then stretched, which pushed the total past the container —
      // a horizontal scrollbar, Curation cut off, and a wide dead gap in every
      // header between the icons and the sort arrow.
      layout: "fitColumns",
      layoutColumnsOnNewData: false,
      // fitColumns alone will shrink columns without limit to avoid overflowing,
      // so a table with many columns became a row of unreadable slivers and no
      // scrollbar — the width was "fitted" by destroying the content. A floor
      // means the columns stay legible and the table overflows honestly, which
      // is what the horizontal scrollbar below is for.
      columnDefaults: {minWidth: GRID_MIN_COLUMN_WIDTH, titleFormatter: headerLabel},
      headerSortElement: SORT_ICON,
      columnHeaderSortMulti: false,
      // Tabulator measures the full width and does not subtract the vertical
      // scrollbar, so the last column is cut by exactly its width. Telling it
      // the gutter exists is cheaper than fighting the layout afterwards.
      renderVerticalBuffer: 300,
      movableColumns: true,        // drag a header to build the table you want
      height: "100%",              // the stable frame owns the visible row area
      placeholder: "No rows match these filters.",
      // Selection is not complete without visible feedback. Keep the summary
      // inside the table whenever either the status bar or row selection is on.
      footerElement: (features.statusbar || features.select) ? footer : undefined,
      selectableRows: !!features.select,
      selectableRowsPersistence: false,
      // WIDTH only, never VISIBLE. Persisting visibility here created two
      // sources of truth that fought each other: the server said show Country,
      // the browser's saved layout said hide it, the browser won, and "Show
      // every column" — which only writes to the server — could not bring it
      // back. A column disappeared and nothing in the interface could recover
      // it. Which columns exist and which are shown is the SERVER's answer.
      // Loading a saved column order after orderedColumns would put a right pin
      // back in its old middle position. Pinning is session-only already, so
      // while it is active the in-memory widths win and persisted order waits
      // until every column is unpinned again.
      persistence: pinned.size ? false : {columns: ["width"]},
      persistenceID: PERSISTENCE_ID,
    };

    // The sort the reader chose has to survive the rebuild. build() destroys
    // and re-creates the table for grouping, nesting, pinning, autosize and
    // every switch in the features panel, and the new instance came up
    // unsorted every time — so grouping by Brand quietly threw away "sort by
    // SKU ascending", with nothing on screen to say it had. A column that is
    // no longer in the table is dropped rather than handed to Tabulator, which
    // would only warn and sort by nothing.
    const survivingSort = sorters.filter((s) => availableFields.has(s.column));
    if (survivingSort.length) options.initialSort = survivingSort;

    // GROUPING: a synthetic parent BAND above the rows, carrying the value and
    // a count. The feature switch decides only whether grouping is AVAILABLE;
    // the column decides what it groups by. The server used to supply a guess
    // here, which meant switching the feature on silently grouped the table by
    // a column nobody chose — the switch appeared to do two things at once.
    if (features.tree && groupedBy.length) {
      options.groupBy = groupedBy.slice();
      options.groupStartOpen = false;
      options.groupHeader = groupedBy.map(() => (value, count) =>
        text(value) + " <span class='muted'>(" + count + ")</span>");
    }

    // TREE: not grouping. There is no extra band — the parent IS a row of the
    // table, and its children are indented inside the SAME first column behind
    // a ⊟ toggle. Grouping answers "how many rows share this value"; a tree
    // answers "which rows sit under this one". They are different questions, so
    // they are different controls, and only one may be on at a time.
    if (features.rows && treeBy) {
      const nested = nest(payload.rows, treeBy);
      if (nested.length) {
        options.data = nested;
        options.dataTree = true;
        options.dataTreeChildField = "_children";
        options.dataTreeStartExpanded = false;
        options.dataTreeChildIndent = 14;
        // The toggle belongs on the column being nested by, not on whichever
        // column happens to be first after the owner drags the headers around.
        options.dataTreeElementColumn = treeBy;
      }
    }

    mount.classList.toggle("compact", !!features.compact);
    mount.classList.toggle("wrap", !!features.wrap);
    mount.classList.toggle("striped", !!features.stripe);

    table = new Tabulator(mount, options);
    table.on("tableBuilt", () => {
      guardHeaderButtons();
      wireLanguageToggle();
      applyFilters();
      describe();
      updateFooter();
      // fitColumns divides the width measured BEFORE the vertical scrollbar
      // exists, so the last column is cut by exactly its width — 15px, enough
      // to add a horizontal scrollbar nobody asked for. One redraw once the
      // rows are in remeasures against the real client width.
      requestAnimationFrame(() => { try { table.redraw(true); } catch (err) {} });
    });
    table.on("dataFiltered", () => { describe(); updateFooter(); });
    // Dragging a column edge is the other way an owner sets a width, and it
    // has to be recorded as one. widthsFromTable() no longer sweeps up every
    // column, so without this a dragged width would be forgotten at the next
    // rebuild and the column would spring back to whatever fitColumns wanted.
    table.on("columnResized", (column) => {
      const field = column.getField();
      if (field) widths.set(field, Math.round(column.getWidth()));
    });
    table.on("rowSelectionChanged", (data, rows) => {
      updateFooter();
      // ONE container under the table, opened by SELECTING a row (the owner's
      // ruling): Details first — they are what the record IS and barely move —
      // then the history, which only grows. Deselecting closes it, so the
      // panel always describes the row that is actually chosen. Select more
      // than one and the same container answers the question that selecting
      // several rows asks: how do they compare.
      const chosen = rows.map((row) => row.getData()).filter((row) => row.offer_id);
      if (!chosen.length) { closeOfferPanel(); return; }
      if (chosen.length > 1) {
        nextSelectionPanelMode = null;
        renderSelectedCardsPanel(chosen);
        return;
      }
      const requestedMode = nextSelectionPanelMode || "record";
      nextSelectionPanelMode = null;
      openOfferPanel(chosen[0].offer_id, requestedMode, chosen[0]);
    });
  }

  // ---- AR | EN: which language the whole page is in -------------------------
  // A bilingual source stores BOTH names (the owner's rule: extracted once,
  // flipped without re-extracting). The toggle swaps VISIBILITY between the
  // two name columns rather than rewriting one column's contents, so sort,
  // filter and export each keep working on exactly the column they name.
  //
  // It governs the RECORD PANEL as well (owner's ruling): printing Arabic and
  // English side by side in the tables under the table is the same fact twice,
  // not more detail. So the choice lives here, at module scope, and the open
  // panel is redrawn when it changes.
  //
  // English is the default. The interface is English, and the owner's rule is
  // that English is the primary display language; a stored preference from
  // before that ruling is honoured, because it was made deliberately.
  const LANG_KEY = "scrapex-name-lang-" + (mount.dataset.source || "");
  let nameLang = "en";
  try { nameLang = localStorage.getItem(LANG_KEY) || "en"; } catch (err) { nameLang = "en"; }

  function wireLanguageToggle() {
    // The server declares which columns pair (reports.BILINGUAL_COLUMNS), so
    // this flips names, category and every level at once and never carries a
    // field list of its own.
    const pairs = Object.entries(payload.bilingual || {});
    if (!pairs.length) return;
    if (document.getElementById("grid-lang-toggle")) return;
    const host = document.querySelector(".data-grid-commandbar");
    if (!host) return;
    const wrap = document.createElement("div");
    wrap.id = "grid-lang-toggle";
    wrap.className = "grid-lang-toggle";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Display language");
    wrap.appendChild(materialIconElement("language", "grid-lang-icon"));
    const note = document.createElement("span");
    note.className = "visually-hidden";
    note.textContent = "Display language";
    wrap.appendChild(note);
    const segments = document.createElement("span");
    segments.className = "grid-lang-segments";
    const buttons = {};
    for (const [code, label, title] of [
      ["en", "EN", "Show English fields"],
      ["ar", "AR", "Show Arabic fields"],
    ]) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "grid-lang-option";
      b.textContent = label;
      b.title = title;
      b.setAttribute("aria-label", title);
      b.addEventListener("click", () => apply(code, true));
      buttons[code] = b;
      segments.appendChild(b);
    }
    wrap.appendChild(segments);
    host.append(wrap);
    function apply(code, save) {
      nameLang = code === "ar" ? "ar" : "en";
      segments.dataset.activeLang = nameLang;
      if (save) { try { localStorage.setItem(LANG_KEY, code); } catch (err) {} }
      for (const [arabic, english] of pairs) {
        // Belt and braces. The server already gates `bilingual` to pairs
        // where BOTH sides are present; without this the toggle could hide
        // the only column with content and show one that does not exist,
        // then write that choice to localStorage and keep the table
        // nameless across reloads.
        if (!table.getColumn(arabic) || !table.getColumn(english)) continue;
        for (const [key, on] of [[arabic, code === "ar"], [english, code === "en"]]) {
          const column = table.getColumn(key);
          if (!column) continue;
          try { on ? column.show() : column.hide(); } catch (err) {}
        }
      }
      // A sort on the column that just went out of view keeps ordering the
      // table from behind it: the rows arrive in an order the reader cannot
      // account for, and no visible column carries an arrow to explain it.
      // The counterpart column is the same fact in the other language, so the
      // sort moves there and the table keeps the order it was asked for.
      try {
        const [current] = table.getSorters();
        if (current && current.field) {
          const hiddenSide = (arabic, english) => code === "ar" ? english : arabic;
          const shownSide = (arabic, english) => code === "ar" ? arabic : english;
          const moved = pairs.find(([arabic, english]) =>
            current.field === hiddenSide(arabic, english));
          if (moved) table.setSort(shownSide(moved[0], moved[1]), current.dir);
        }
      } catch (err) { /* an unsorted table has nothing to move */ }
      for (const [c, b] of Object.entries(buttons)) {
        b.setAttribute("aria-pressed", String(c === nameLang));
      }
      // The record open underneath is showing the other language's details;
      // leaving it as it was would make the switch look half-connected.
      if (save) redrawOpenPanel();
    }
    apply(nameLang, false);
  }

  // ---- one row per product, or one per variation ----------------------------
  //
  // samehgabriel sells 18 products in 6 colours each, so the table showed 108
  // rows that differed only by colour. This folds a product's SAME-PRICED
  // variations into one row and lists them together. It is a DISPLAY rule: the
  // warehouse keeps every row the site published, and a product priced
  // differently per colour correctly stays several rows.
  //
  // It reloads rather than redrawing, and that is deliberate. The fold changes
  // the row COUNT and adds a column, and the fold itself is computed on the
  // server so the page, the API and the export cannot disagree about what a row
  // means. Rebuilding a live Tabulator around a different shape is where the
  // half-updated states come from; a reload has one shape and no doubt.
  const FOLD_KEY = "scrapex-fold-variants-" + (mount.dataset.source || "");

  function wireFoldToggle() {
    // Offered only where it would do something. A source with nothing to fold
    // gets no control, rather than a control that changes nothing.
    if (!payload.foldable && !payload.fold_variants) return;
    if (document.getElementById("grid-fold-toggle")) return;
    const host = document.querySelector(".data-grid-commandbar");
    if (!host) return;
    const wrap = document.createElement("div");
    wrap.id = "grid-fold-toggle";
    wrap.className = "grid-lang-toggle grid-fold-toggle";
    wrap.setAttribute("role", "group");
    wrap.setAttribute("aria-label", "Rows per product");
    wrap.appendChild(materialIconElement("layers", "grid-lang-icon"));
    const note = document.createElement("span");
    note.className = "visually-hidden";
    note.textContent = "Rows per product";
    wrap.appendChild(note);
    const segments = document.createElement("span");
    segments.className = "grid-lang-segments grid-fold-segments";
    segments.dataset.activeFold = payload.fold_variants ? "on" : "off";
    for (const [state, label, title] of [
      ["off", "ALL", "One row per variation, as the site publishes them"],
      ["on", "ONE", "Group a product's same-priced variations into one row"],
    ]) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "grid-lang-option";
      b.textContent = label;
      b.title = title;
      b.setAttribute("aria-label", title);
      b.setAttribute("aria-pressed",
                     String((state === "on") === Boolean(payload.fold_variants)));
      b.addEventListener("click", () => {
        if ((state === "on") === Boolean(payload.fold_variants)) return;
        try { localStorage.setItem(FOLD_KEY, state); } catch (err) {}
        location.reload();
      });
      segments.appendChild(b);
    }
    wrap.appendChild(segments);
    host.append(wrap);
  }

  // ---- why the header's two buttons only worked SOMETIMES -------------------
  //
  // movableColumns arms a column DRAG on mousedown anywhere in a header and
  // starts it 250ms later. The three-dot menu and the filter icon sit inside
  // that header, and both Tabulator's handlers and ours stop only the CLICK.
  // So pressing either of them a shade slowly began a column move instead: the
  // header was re-rendered under the cursor, the very button being pressed left
  // the document, and no click event was ever delivered. Measured on this page:
  // a 120ms press opens the menu, a 400ms press leaves the button detached and
  // opens nothing. That is the whole of "the table's functions work sometimes
  // and sometimes not" — not the actions, the way in.
  //
  // Captured on the HEADER, so it runs before the column's own mousedown
  // listener and the drag timer is never armed for these two buttons. Dragging
  // a column by its title is untouched, and so is the resize handle.
  // ---- one popup at a time --------------------------------------------------
  //
  // Tabulator's popup (the filter list) and its menu (the three dots) are two
  // independent modules. Neither knows the other exists; each closes itself
  // only when a click or a mousedown reaches document.body, where it binds a
  // blur listener. Tabulator's own button handler calls stopPropagation on the
  // CLICK — it has to, or pressing the button would sort the column — so the
  // mousedown was the only event that still travelled to body, and the guard
  // above stops that one too. Opening the filter and then the menu therefore
  // drew both, one over the other (the owner's report).
  //
  // Blurring through Tabulator's OWN listener rather than deleting the element
  // is what runs its cleanup: unbinding the six document listeners the popup
  // left behind and clearing the module's rootPopup reference.
  function dismissOpenHeaderPopups() {
    const OPEN = ".tabulator-popup-container, .tabulator-menu";
    if (!document.querySelector(OPEN)) return;
    document.body.dispatchEvent(new MouseEvent("mousedown"));
    document.body.dispatchEvent(new MouseEvent("click"));
    // Tabulator binds those blur listeners on a 100ms timer AFTER the popup
    // opens. Reaching the other button inside that window found nothing
    // listening, so the first popup stayed. Nothing was bound in that case,
    // which means there is no cleanup owed and removing the element is the
    // whole of the job — and Popup.hide() null-checks parentNode, so the
    // module's own later hide stays safe.
    document.querySelectorAll(OPEN).forEach((node) => node.remove());
  }

  function guardHeaderButtons() {
    const header = mount.querySelector(".tabulator-header");
    if (!header || header.dataset.buttonsGuarded) return;
    header.dataset.buttonsGuarded = "1";
    const hold = (event) => {
      const target = event.target;
      if (!target || !target.closest) return;
      if (!target.closest(".tabulator-header-popup-button")) return;
      event.stopPropagation();
      // Before the button's own click opens the next one. mousedown precedes
      // click, so the outgoing popup is gone before the incoming one is built.
      dismissOpenHeaderPopups();
    };
    header.addEventListener("mousedown", hold, true);
    header.addEventListener("touchstart", hold, true);
  }

  // Refresh only the widths the owner ALREADY owns.
  //
  // This captured EVERY column on every rebuild, and that one line is what
  // made "fit" stop working. `widths` is the record of decisions — a column
  // the owner autofitted or dragged — and a column in it is built with
  // widthGrow 0 so no layout pass may spend it. Capturing all fifty columns
  // turned the whole table into decisions nobody made: grouping by Brand, a
  // command with nothing to say about widths, left all 50 at widthGrow 0
  // (measured), and from that moment fitColumns had nothing left to
  // distribute. Resizing the window, hiding a column, switching AR|EN — none
  // of it could re-fit anything ever again, in a table that overflows its
  // viewport by design.
  function widthsFromTable() {
    try {
      table.getColumns().forEach((c) => {
        const f = c.getField();
        if (f && widths.has(f)) widths.set(f, c.getWidth());
      });
    } catch (err) { /* a rebuild mid-render is not worth failing over */ }
  }

  // getSorters() reports `field`; initialSort expects `column`. Translating
  // here rather than at the call site keeps the shape mismatch in one place.
  function sortFromTable() {
    try {
      sorters = table.getSorters()
        .filter((s) => s && s.field)
        .map((s) => ({column: s.field, dir: s.dir}));
    } catch (err) { /* nothing sorted, or a table mid-teardown */ }
  }

  // ---- the History panel: one offer's story, under the table ----------------
  //
  // Everything scraped is set through textContent — a product name containing
  // markup must render as text, never run. Numbers and dates get dir=ltr so an
  // RTL page cannot mirror "20.5 -> 21.0" into "21.0 <- 20.5".
  let openOfferId = null;
  let openOfferMode = "history";

  function el(tag, className, textValue) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (textValue !== undefined) node.textContent = textValue;
    return node;
  }

  function miniTable(headers, rows) {
    const wrap = el("div", "tablewrap record-table-wrap");
    const table = document.createElement("table");
    table.className = "record-mini-table";
    const head = table.createTHead().insertRow();
    headers.forEach((h) => head.appendChild(el("th", "", h)));
    const body = table.createTBody();
    rows.forEach((cells) => {
      const row = body.insertRow();
      cells.forEach((value) => {
        const cell = row.insertCell();
        if (value instanceof Node) { cell.appendChild(value); return; }
        cell.textContent = text(value);
        cell.dir = "auto";
      });
    });
    wrap.appendChild(table);
    return wrap;
  }

  function money(amount, currency, unit) {
    const span = el("span", "", amount == null || amount === "" ? "—"
      : formatMoney(amount) + (currency ? " " + currency : "") + (unit ? " / " + unit : ""));
    span.dir = "ltr";
    return span;
  }

  let openOfferRow = null;
  let nextSelectionPanelMode = null;
  // What the panel on screen was drawn FROM, so a language switch can redraw it
  // without another round trip. Exactly one of the two is ever set.
  let openOfferData = null;
  let openSelectedRows = null;

  function redrawOpenPanel() {
    const panel = document.getElementById("offer-panel");
    if (!panel || panel.hidden) return;
    if (openSelectedRows) { renderSelectedCardsPanel(openSelectedRows); return; }
    if (openOfferData && openOfferId) {
      renderOfferPanel(panel, openOfferData, openOfferId, openOfferMode);
    }
  }

  function openOfferPanel(offerId, mode, rowData) {
    const panel = document.getElementById("offer-panel");
    if (!panel) return;
    mode = mode || "history";
    openOfferRow = rowData || null;
    if (openOfferId === offerId && openOfferMode === mode && !panel.hidden) {
      if (mode === "record") return;           // re-selecting the same row
      closeOfferPanel();                       // same row, same ask = close
      return;
    }
    openOfferId = offerId;
    openOfferMode = mode;
    panel.hidden = false;
    panel.textContent = "";
    panel.className = "record-panel is-loading";
    panel.appendChild(el("p", "muted", "Loading this record…"));
    fetch("/api/offer/" + encodeURIComponent(SOURCE) + "/" + offerId)
      .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
      .then((data) => {
        if (openOfferId === offerId && openOfferMode === mode) {
          renderOfferPanel(panel, data, offerId, mode);
        }
      })
      .catch((err) => {
        if (openOfferId !== offerId || openOfferMode !== mode) return;
        panel.textContent = "";
        panel.className = "record-panel";
        panel.appendChild(el("p", "err",
          "Couldn't load this record's history (" + err.message + ")."));
      });
    panel.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  function closeOfferPanel() {
    const panel = document.getElementById("offer-panel");
    if (!panel) return;
    panel.hidden = true;
    panel.textContent = "";
    openOfferId = null;
    openOfferData = null;
    openSelectedRows = null;
  }

  // ---- the record panel: one product, shaped the way its own page is shaped -
  //
  // The first version printed EVERY fact through the same two-column
  // "Attribute | Value" table under a bare heading, so a product arrived as
  // four identical grey grids: the picture, the datasheet, the specifications
  // and the price story all looked like the same kind of thing. They are not.
  // A record is sections of UNLIKE content — images, a specification list,
  // prose, downloadable files, a timeline — and each is now a card that shows
  // its content the way the source's own page shows it. Same output for every
  // source (the owner's ruling); a card appears only where that source
  // actually stated something, so nothing renders an empty frame.

  // The value in the language on show, or the only one there is. Never blank
  // because one side of a pair is missing — a source that publishes a single
  // language must still fill the cell.
  function pickLang(english, arabic) {
    const first = nameLang === "ar" ? arabic : english;
    const second = nameLang === "ar" ? english : arabic;
    return text(first) || text(second);
  }

  function safeUrl(raw) {
    try {
      const parsed = new URL(raw);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
    } catch (err) { /* not a URL — callers fall back to plain text */ }
    return "";
  }

  function card(titleText, className) {
    const box = el("article", "record-card" + (className ? " " + className : ""));
    if (titleText) {
      const heading = el("header", "record-card-head");
      heading.appendChild(el("span", "record-card-marker"));
      heading.appendChild(el("h3", "record-card-title", titleText));
      box.appendChild(heading);
    }
    box.appendChild(el("div", "record-card-body"));
    return box;
  }

  // Every inspector section uses the same fixed-heading, scrolling-body shell.
  // Description prose, definition lists, attachments and history tables differ
  // only in what they place inside this shared body.
  function cardBody(box) {
    return box.lastElementChild;
  }

  // AR + EN are ONE fact in two languages, not two facts. Connectors keep them
  // in separate rows under paired codes (description / description_en), and the
  // server sends the code, so the pairing is the connector's declaration rather
  // than a guess made from the text.
  //
  // The panel then shows ONE of them — whichever the table's AR|EN toggle is
  // set to (the owner's ruling: the switch governs both surfaces, and printing
  // both languages in the tables under the table is repetition, not detail).
  // A pair whose chosen side the source never published falls back to the side
  // it did publish: a missing translation must show the fact, not a blank.
  function pairByLanguage(items) {
    const byCode = new Map();
    items.forEach((d) => { if (d.code) byCode.set(d.code, d); });
    const used = new Set();
    const entries = [];
    const strip = (label) => (label || "").replace(/\s*\((EN|AR)\)\s*$/i, "");
    items.forEach((d) => {
      if (used.has(d)) return;
      const code = d.code || "";
      // The unmarked code is English, `_ar` is Arabic (0039). slice(0, -3)
      // works on either suffix -- they are the same length -- but the
      // INTENT is what moved, so read it as written.
      const arabic = code.endsWith("_ar") ? d : byCode.get(code + "_ar");
      const english = code.endsWith("_ar") ? byCode.get(code.slice(0, -3)) : d;
      if (english && arabic && english !== arabic && !used.has(english) && !used.has(arabic)) {
        used.add(english);
        used.add(arabic);
        const chosen = nameLang === "en" ? english : arabic;
        const other = chosen === english ? arabic : english;
        const side = chosen.value ? chosen : other;
        entries.push({label: strip(side.label) || strip(chosen.label) || strip(other.label),
                      value: side.value, url: side.url || other.url,
                      unit: side.unit || other.unit,
                      numeric: side.numeric || other.numeric});
        return;
      }
      used.add(d);
      entries.push({label: strip(d.label), value: d.value,
                    url: d.url, unit: d.unit, numeric: d.numeric});
    });
    return entries;
  }

  // A definition list, not a table: one fact per line, label left, value right,
  // exactly like the "Specifications" card the shops themselves print.
  function specList(entries) {
    const list = el("dl", "spec-list");
    entries.forEach((entry) => {
      const row = el("div", "spec-row");
      const label = el("dt", "", text(entry.label || ""));
      label.dir = "auto";
      const value = el("dd", "");
      const href = safeUrl(entry.url || "");
      // The unit the source stated travels with the number, so "50" is not
      // left for the reader to guess at — but only when the printed value does
      // not already carry it ("5 kg" must not become "5 kg kg").
      let shown = text(entry.value);
      if (entry.unit && shown && !shown.toLowerCase().includes(String(entry.unit).toLowerCase())) {
        shown = shown + " " + entry.unit;
      }
      let primary;
      if (href) {
        primary = document.createElement("a");
        primary.href = href;
        primary.target = "_blank";
        primary.rel = "noopener noreferrer";
        primary.textContent = shown;
      } else {
        primary = el("span", "", shown);
      }
      primary.dir = "auto";
      value.appendChild(primary);
      row.append(label, value);
      list.appendChild(row);
    });
    return list;
  }

  // Descriptions arrive as one string with newlines. Preserve real paragraphs,
  // turn source bullet glyphs into a semantic list, and remove headings that
  // merely repeat the section title already visible above the card.
  function prose(value, skippedHeadings) {
    const box = el("div", "record-prose");
    const skipped = new Set((skippedHeadings || []).map((item) =>
      String(item).trim().toLowerCase()));
    let list = null;
    String(value == null ? "" : value).split(/\r?\n/).forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      if (skipped.has(trimmed.toLowerCase())) return;
      const bullet = trimmed.match(/^[•▪■□●◦‣∙·\uf0a7\-–—]\s*(.+)$/);
      if (bullet) {
        if (!list) {
          list = el("ul", "record-prose-list");
          box.appendChild(list);
        }
        const item = el("li", "", bullet[1]);
        item.dir = "auto";
        list.appendChild(item);
        return;
      }
      list = null;
      const isSectionHeading = /[A-Z]/.test(trimmed) &&
        !/[a-z]/.test(trimmed) && trimmed.length <= 72 &&
        !/[.!?]$/.test(trimmed);
      if (isSectionHeading) {
        const heading = el("h5", "record-prose-section-title", trimmed);
        heading.dir = "auto";
        box.appendChild(heading);
        return;
      }
      const paragraph = el("p", "", trimmed);
      paragraph.dir = "auto";
      box.appendChild(paragraph);
    });
    return box;
  }

  function keywordSection(entries) {
    const section = el("section", "record-detail-subsection");
    const first = entries.find((entry) => text(entry.value)) || entries[0] || {};
    const title = text(first.label) || "Keywords";
    const heading = el("h4", "record-detail-subsection-title", title);
    heading.dir = "auto";
    section.appendChild(heading);
    const keywords = el("div", "record-keywords");
    const terms = text(first.value).split(/[,;\r\n]+/).map((term) => term.trim())
      .filter(Boolean);
    terms.forEach((term) => {
      const chip = el("span", "record-keyword", term);
      chip.dir = "auto";
      keywords.appendChild(chip);
    });
    if (!terms.length) keywords.appendChild(el("span", "muted", "No keywords recorded."));
    section.appendChild(keywords);
    return section;
  }

  function fileSize(bytes) {
    const size = Number(bytes);
    if (!isFinite(size) || size <= 0) return "";
    if (size < 1024) return size + " B";
    if (size < 1024 * 1024) return (size / 1024).toFixed(0) + " KB";
    return (size / (1024 * 1024)).toFixed(1) + " MB";
  }

  // Datasheets and other non-image files: a card each, with the size the API
  // states and one obvious control. (The shop's own page shows "0 Bytes" for
  // every attachment — its bug; the API carries the true size and we print it.)
  function fileCards(items) {
    const wrap = el("div", "file-cards");
    items.forEach((d) => {
      const href = safeUrl(d.url || "");
      const box = el("div", "file-card");
      const name = el("span", "file-name", text(d.value || d.label || "file"));
      name.dir = "auto";
      box.appendChild(name);
      const meta = [d.label && d.label !== d.value ? d.label : "", fileSize(d.numeric)]
        .filter(Boolean).join(" · ");
      if (meta) box.appendChild(el("span", "file-meta", meta));
      if (href) {
        const open = document.createElement("a");
        open.href = href;
        open.target = "_blank";
        open.rel = "noopener noreferrer";
        open.className = "file-open";
        open.textContent = "Open";
        box.appendChild(open);
      }
      wrap.appendChild(box);
    });
    return wrap;
  }

  function shortDescription(details) {
    const descriptions = (details || []).filter((item) =>
      (item.group || "").toLowerCase() === "description");
    let shortRows = descriptions.filter((item) =>
      (item.code || "").toLowerCase().startsWith("short_description"));
    const hasSeparateFullDescription = descriptions.some((item) =>
      (item.code || "").toLowerCase().startsWith("full_description"));
    if (!shortRows.length && hasSeparateFullDescription) {
      shortRows = descriptions.filter((item) =>
        ["description", "description_ar"].includes((item.code || "").toLowerCase()));
    }
    const paired = pairByLanguage(shortRows);
    const first = paired.find((item) => text(item.value));
    return first ? text(first.value) : "";
  }

  function deepestCategoryLevel(row) {
    const levels = Object.keys(row || {}).map((key) => {
      const match = /^category_l(\d+)(?:_ar)?$/.exec(key);
      return match ? Number(match[1]) : 0;
    }).filter(Boolean).sort((a, b) => b - a);
    for (const level of [...new Set(levels)]) {
      const value = pickLang(row["category_l" + level], row["category_l" + level + "_ar"]);
      if (value) return value;
    }
    return "";
  }

  function displayProductName(value) {
    return text(value).replace(/\s+/g, " ").trim().replace(
      /-\s*(\d+(?:[.,]\d+)?)\s*(ml|l|kg|g)\s*$/i,
      (match, amount, unit) => " · " + amount + " " + unit);
  }

  function productSummaryCard(row, data, onDetails, onHistory) {
    const offer = (data && data.offer) || {};
    const details = (data && data.details) || [];
    const box = el("article", "selected-product-card");
    const media = el("div", "selected-product-media");
    const imageStage = el("div", "selected-product-image-stage");
    media.appendChild(imageStage);
    const images = details
      .filter((item) => (item.group || "") === "Media" && safeUrl(item.url))
      .map((item) => ({url: safeUrl(item.url), alt: text(item.value || "")}));
    if (images.length) {
      const main = document.createElement("img");
      main.src = images[0].url;
      main.alt = images[0].alt;
      main.loading = "lazy";
      imageStage.appendChild(main);
      const count = el("span", "selected-product-image-count", "1 / " + images.length);
      imageStage.appendChild(count);
      if (images.length > 1) {
        const thumbs = el("div", "selected-product-thumbs");
        let current = 0;
        const showImage = (index) => {
          current = (index + images.length) % images.length;
          main.src = images[current].url;
          main.alt = images[current].alt;
          count.textContent = (current + 1) + " / " + images.length;
          thumbs.querySelectorAll("button").forEach((item, itemIndex) =>
            item.classList.toggle("is-active", itemIndex === current));
        };
        const previous = el("button", "selected-product-image-nav is-previous", "‹");
        previous.type = "button";
        previous.setAttribute("aria-label", "Previous product image");
        previous.addEventListener("click", () => showImage(current - 1));
        const next = el("button", "selected-product-image-nav is-next", "›");
        next.type = "button";
        next.setAttribute("aria-label", "Next product image");
        next.addEventListener("click", () => showImage(current + 1));
        imageStage.append(previous, next);
        images.forEach((image, index) => {
          const thumb = el("button", index === 0 ? "is-active" : "");
          thumb.type = "button";
          thumb.setAttribute("aria-label", "Show image " + (index + 1));
          const picture = document.createElement("img");
          picture.src = image.url;
          picture.alt = "";
          picture.loading = "lazy";
          thumb.appendChild(picture);
          thumb.addEventListener("click", () => showImage(index));
          thumbs.appendChild(thumb);
        });
        media.appendChild(thumbs);
      }
    } else {
      const empty = el("div", "selected-product-image-empty",
        data ? "No product image" : "Loading product image…");
      imageStage.appendChild(empty);
    }
    if (images.length) box.appendChild(media);

    const body = el("div", "selected-product-body");
    const titleRow = el("div", "selected-product-title-row");
    const name = el("h3", "selected-product-name", displayProductName(
      pickLang(row.product_name, row.product_name_ar) ||
      pickLang(offer.product_name, offer.product_name_ar) ||
      offer.name || "Unnamed record"));
    name.dir = "auto";
    titleRow.appendChild(name);
    const live = safeUrl(row.product_link || offer.product_link || "");
    if (live) {
      const visit = el("a", "selected-product-site-link");
      visit.href = live;
      visit.target = "_blank";
      visit.rel = "noopener noreferrer";
      visit.title = "Open on site";
      visit.setAttribute("aria-label", "Open product on site");
      visit.appendChild(materialIconElement("open-in-new", "selected-product-site-icon"));
      titleRow.appendChild(visit);
    }
    body.appendChild(titleRow);
    const description = shortDescription(details);
    if (description) {
      const short = el("p", "selected-product-description", description);
      short.dir = "auto";
      body.appendChild(short);
    }

    const categoryLevel = deepestCategoryLevel(row);
    if (categoryLevel) {
      const category = el("div", "selected-product-category");
      category.appendChild(el("span", "selected-product-category-label", "Category"));
      const value = el("strong", "selected-product-category-value", categoryLevel);
      value.dir = "auto";
      category.appendChild(value);
      body.appendChild(category);
    }

    const currentPrice = row.price !== undefined && row.price !== null && row.price !== ""
      ? row.price
      : row.effective_price;
    const price = el("div", "selected-product-price");
    price.appendChild(el("span", "selected-product-price-label", "Current price"));
    const value = el("strong", "");
    value.appendChild(money(currentPrice, row.currency || offer.currency,
                            offer.unit || row.unit));
    price.appendChild(value);
    body.appendChild(price);

    const actions = el("div", "selected-product-actions");
    const detailsButton = el("button", "record-action", "Details");
    detailsButton.type = "button";
    detailsButton.dataset.inspectorView = "details";
    detailsButton.disabled = !data;
    detailsButton.addEventListener("click", () => onDetails(data, row, detailsButton));
    actions.appendChild(detailsButton);
    const historyButton = el("button", "record-action", "History");
    historyButton.type = "button";
    historyButton.dataset.inspectorView = "history";
    historyButton.disabled = !data;
    historyButton.addEventListener("click", () =>
      (onHistory || onDetails)(data, row, historyButton));
    actions.appendChild(historyButton);
    body.appendChild(actions);
    box.appendChild(body);
    return box;
  }

  function renderOfferPanel(panel, data, offerId, mode) {
    panel.textContent = "";
    panel.className = "record-panel";
    openOfferData = data;
    openSelectedRows = null;
    const offer = data.offer || {};
    const row = openOfferRow || {};
    const details = data.details || [];
    // ONE table drives three things that used to be three lists: which buttons
    // the inspector rail carries, in what order, and which button a group's
    // card lands under. They drifted the moment the vocabulary grew to seven --
    // Store and Site metadata had no button and were being stacked under
    // Specifications, three headings deep in one column.
    //
    // Order is a display judgement: what the product IS, then the properties
    // measured of it, then what is known about it, then how THIS store handles
    // it, then facts about the page rather than the product, then the files.
    //
    // "Details" is not a group -- it is the fallback below for a row that
    // arrived without one. ("Specs" was a real group until 0043 merged it into
    // Specifications; kept here so an un-recrawled source still lands somewhere
    // rather than growing a card of its own.) Media is absent on purpose: the
    // product card already owns the gallery.
    const DETAIL_SECTIONS = [
      {key: "description", label: "Description", icon: "description",
       groups: ["Description"]},
      {key: "specifications", label: "Specifications", icon: "tune",
       groups: ["Specifications", "Specs", "Details"]},
      {key: "more-information", label: "More information", icon: "info",
       groups: ["More information"]},
      // shopping-cart, not storage: this is the shop's handling of the product.
      {key: "store", label: "Store", icon: "shopping-cart",
       groups: ["Store"]},
      // dns is the sprite's site/domain glyph. NOT "language" -- that is the
      // AR/EN toggle a few centimetres away in this same panel.
      {key: "site-metadata", label: "Site metadata", icon: "dns",
       groups: ["Site metadata"]},
      {key: "attachments", label: "Attachments", icon: "insert-drive-file",
       groups: ["Attachments"]},
    ];
    const HISTORY_SECTIONS = [
      {key: "price", label: "Price history", icon: "trending-up"},
      {key: "changes", label: "Changes", icon: "history"},
      {key: "observations", label: "Observations", icon: "schedule"},
    ];
    const sectionForGroup = (name) =>
      (DETAIL_SECTIONS.find((s) => s.groups.includes(name)) || {}).key
        || "specifications";
    const detailSections = new Map(DETAIL_SECTIONS.map((s) => [s.key, []]));
    const historySections = new Map(HISTORY_SECTIONS.map((s) => [s.key, []]));
    // One schema drives ordering, icons, availability and click behaviour for
    // both primary views. Only populated groups reach the rail, without
    // duplicating Details and History branches.
    const INSPECTOR_VIEWS = [
      {key: "details", label: "Details", icon: "view-stream",
       definitions: DETAIL_SECTIONS, sections: detailSections},
      {key: "history", label: "History", icon: "history",
       definitions: HISTORY_SECTIONS, sections: historySections},
    ];

    const workspace = el("div", "record-product-workspace");
    const productGrid = el("div", "selected-product-grid is-single");
    const inspector = el("section", "record-inspector");
    inspector.setAttribute("aria-label", "Selected product information");
    inspector.setAttribute("aria-hidden", "true");
    inspector.inert = true;

    const inspectorMain = el("div", "record-inspector-main");
    const inspectorNav = el("nav", "record-inspector-nav");
    inspectorNav.setAttribute("aria-label", "Product information sections");
    const inspectorContent = el("div", "record-inspector-content");
    inspectorMain.append(inspectorNav, inspectorContent);
    inspector.appendChild(inspectorMain);

    const summary = productSummaryCard(
      row,
      data,
      () => toggleInspector("details"),
      () => toggleInspector("history"));
    productGrid.appendChild(summary);
    workspace.append(productGrid, inspector);
    panel.appendChild(workspace);

    function setSummaryMode(view) {
      summary.querySelectorAll("[data-inspector-view]").forEach((button) => {
        const active = workspace.classList.contains("has-inspector") &&
          button.dataset.inspectorView === view;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
        button.setAttribute("aria-expanded", String(active));
      });
    }

    function inspectorNavButton(item, active, onClick, className) {
      const button = el("button", (className || "") + (active ? " is-active" : ""));
      button.type = "button";
      button.title = item.label;
      button.setAttribute("aria-label", item.label);
      button.setAttribute("aria-pressed", String(active));
      button.appendChild(materialIconElement(item.icon, "record-inspector-nav-icon"));
      button.addEventListener("click", onClick);
      return button;
    }

    function renderInspector(view, requestedKey) {
      const selectedView = INSPECTOR_VIEWS.find((item) => item.key === view)
        || INSPECTOR_VIEWS[0];
      const definitions = selectedView.definitions;
      const sections = selectedView.sections;
      const populated = definitions.filter((item) => sections.get(item.key).length);
      const validRequested = populated.some((item) => item.key === requestedKey);
      const activeKey = validRequested
        ? requestedKey
        : (populated[0] ? populated[0].key : "");
      inspector.dataset.view = selectedView.key;
      setSummaryMode(selectedView.key);
      inspectorNav.textContent = "";
      inspectorContent.textContent = "";

      const modeGroup = el("div",
        "record-inspector-nav-group record-inspector-nav-primary");
      INSPECTOR_VIEWS.forEach((item) => {
        modeGroup.appendChild(inspectorNavButton(
          item,
          item.key === selectedView.key,
          () => renderInspector(item.key),
          "record-inspector-nav-mode"));
      });
      inspectorNav.appendChild(modeGroup);
      if (populated.length) {
        const divider = el("span", "record-inspector-nav-divider");
        divider.setAttribute("role", "separator");
        inspectorNav.appendChild(divider);
        const sectionGroup = el("div",
          "record-inspector-nav-group record-inspector-nav-sections");
        populated.forEach((item) => {
          sectionGroup.appendChild(inspectorNavButton(
            item,
            item.key === activeKey,
            () => renderInspector(selectedView.key, item.key),
            "record-inspector-nav-section"));
        });
        inspectorNav.appendChild(sectionGroup);
      }

      if (!activeKey) {
        inspectorContent.appendChild(el("div", "record-inspector-empty",
          "No " + selectedView.label.toLowerCase() + " are available for this product."));
        if (selectedView.key === "history") inspectorContent.appendChild(fullRecordAction());
        return;
      }
      const sectionCards = sections.get(activeKey);
      const cards = el("div", "record-cards");
      sectionCards.forEach((section) => cards.appendChild(section));
      inspectorContent.appendChild(cards);
      if (selectedView.key === "history") inspectorContent.appendChild(fullRecordAction());
    }

    function fullRecordAction() {
      const footer = el("footer", "record-inspector-footer");
      const full = el("a", "record-action record-action-subtle", "Full record");
      full.href = "/source/" + encodeURIComponent(SOURCE) + "/offer/" + row.offer_id;
      footer.appendChild(full);
      return footer;
    }

    function toggleInspector(view) {
      const open = workspace.classList.contains("has-inspector");
      if (open && inspector.dataset.view === view) {
        hideInspector();
        return;
      }
      openOfferMode = view;
      inspector.inert = false;
      inspector.setAttribute("aria-hidden", "false");
      workspace.classList.add("has-inspector");
      panel.classList.add("has-expanded-details");
      renderInspector(view);
    }

    function hideInspector() {
      openOfferMode = "record";
      inspector.inert = true;
      inspector.setAttribute("aria-hidden", "true");
      workspace.classList.remove("has-inspector");
      panel.classList.remove("has-expanded-details");
      setSummaryMode("");
    }

    // Name and classification in the language the toggle is set to, falling
    // back to the one the source published when it published only one.
    // The details the source printed for this product — colours, lengths,
    // categories, warranties — grouped as the page grouped them. Scraped
    // content throughout: names as text, URLs linked only when they parse.
    if (details.length) {
      const groups = new Map();
      details.forEach((d) => {
        const key = d.group || "Details";
        // The product card already owns the complete gallery. Repeating media
        // inside the inspector wastes the space reserved for product facts.
        if (key === "Media") return;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(d);
      });
      // Order comes from DETAIL_SECTIONS, so the card order and the rail order
      // cannot disagree. A group a connector invents that the table does not
      // know sorts last and lands under Specifications rather than vanishing.
      const order = DETAIL_SECTIONS.flatMap((s) => s.groups);
      const names = [...groups.keys()].sort((a, b) => {
        const rankA = order.indexOf(a), rankB = order.indexOf(b);
        return (rankA < 0 ? order.length : rankA) - (rankB < 0 ? order.length : rankB);
      });
      // One definition, used by two branches: keywords sit under Site metadata
      // since 0046, but a source that has not been re-crawled still has them
      // filed under Description, and both must render them as chips.
      const isKeywordRow = (item) => {
        const code = (item.code || "").toLowerCase();
        const label = (item.label || "").trim().toLowerCase();
        return code.startsWith("keywords") || label === "keywords";
      };
      names.forEach((name) => {
        const items = groups.get(name);
        if (name === "Description") {
          const fullRows = items.filter((item) =>
            (item.code || "").toLowerCase().startsWith("full_description"));
          const keywordRows = items.filter(isKeywordRow);
          const withoutShortOrKeywords = items.filter((item) =>
            !(item.code || "").toLowerCase().startsWith("short_description") &&
            !isKeywordRow(item));
          const paired = pairByLanguage(fullRows.length
            ? fullRows
            : (withoutShortOrKeywords.length ? withoutShortOrKeywords : items));
          const databaseTitle = text((paired.find((entry) =>
            text(entry.label)) || {}).label);
          const box = card(databaseTitle, "record-card-wide record-card-prose");
          const body = cardBody(box);
          paired.forEach((entry, index) => {
            const label = (entry.label || "").trim();
            if (index > 0 && label &&
                label.toLowerCase() !== databaseTitle.toLowerCase()) {
              body.appendChild(el("h4", "record-prose-title", label));
            }
            body.appendChild(prose(entry.value, databaseTitle ? [databaseTitle] : []));
          });
          const keywords = pairByLanguage(keywordRows);
          if (keywords.length) body.appendChild(keywordSection(keywords));
          detailSections.get("description").push(box);
          return;
        }
        if (name === "Attachments") {
          const paired = pairByLanguage(items);
          const box = card(name, "record-card-wide");
          cardBody(box).appendChild(fileCards(paired));
          detailSections.get("attachments").push(box);
          return;
        }
        const box = card(name);
        const body = cardBody(box);
        // Keywords are search terms, not a measurement, and read far better as
        // chips than as a value in a two-column list. They were rendered that
        // way inside Description until 0046 refiled them under Site metadata —
        // the rendering follows the fact, not the heading it used to sit under,
        // or the move would have quietly cost the owner the better view.
        // Split BEFORE pairing: pairByLanguage returns display entries and does
        // not carry `code` through, so after it the ar/en pair is unidentifiable.
        const keywordRows = items.filter(isKeywordRow);
        const rest = items.filter((item) => !isKeywordRow(item));
        if (rest.length) body.appendChild(specList(pairByLanguage(rest)));
        if (keywordRows.length) {
          body.appendChild(keywordSection(pairByLanguage(keywordRows)));
        }
        detailSections.get(sectionForGroup(name)).push(box);
      });
    }

    // Fields the owner moved OUT of the table (Choose Columns -> hide) are
    // shown here instead, so nothing is ever lost by tidying the grid: hide
    // moves a field into the details, show moves it back.
    const moved = payload.moved_to_details || [];
    if (moved.length && openOfferRow) {
      const box = card("Moved out of the table");
      cardBody(box).appendChild(specList(moved.map((column) => ({
        label: column.label || column.key, value: text(openOfferRow[column.key]),
      }))));
      detailSections.get("specifications").push(box);
    }

    // The change-only timeline: the first price and each REAL move.
    const periods = data.periods || [];
    if (periods.length) {
      const timeline = card("Price changes", "record-card-wide");
      const timelineBody = cardBody(timeline);
      timelineBody.appendChild(miniTable(
        ["From", "Until", "Price", "Why it opened"],
        periods.map((p) => [
          (p.first_detected_at || "").slice(0, 10),
          (p.closed_at || "").slice(0, 10) || "current",
          money(p.price, p.currency, offer.unit),
          (p.opened_because || "").replace(/_/g, " "),
        ])));
      historySections.get("price").push(timeline);
    }

    const changes = data.changes || [];
    if (changes.length) {
      const feed = card("Changes", "record-card-wide");
      const feedBody = cardBody(feed);
      feedBody.appendChild(miniTable(
        ["Detected", "What", "Previous", "New", "Change"],
        changes.map((c) => {
          const when = el("span", "muted", (c.detected_at || "").slice(0, 16).replace("T", " "));
          when.dir = "ltr";
          return [
            when,
            c.field_label || "",
            c.display_previous || "—",
            (c.display_new || "—") + (c.unit && c.field_label === "price" ? " / " + c.unit : ""),
            c.display_change || "—",
          ];
        })));
      historySections.get("changes").push(feed);
    }

    const observations = data.observations || [];
    if (observations.length) {
      const recorded = card("What was recorded", "record-card-wide");
      const recordedBody = cardBody(recorded);
      recordedBody.appendChild(miniTable(
        ["Date", "Price", "Where it came from"],
        observations.map((o) => [
          o.business_date || "",
          money(o.price, o.currency, offer.unit),
          o.provenance === "reported" ? "reported by the source" : "observed by a crawl",
        ])));
      historySections.get("observations").push(recorded);
    }

    if (mode === "details" || mode === "history") toggleInspector(mode);

    panel.focus({preventScroll: true});
    panel.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  // ---- more than one row selected: one product card per selected row --------
  function renderSelectedCardsPanel(rowsData) {
    const panel = document.getElementById("offer-panel");
    if (!panel) return;
    openOfferId = null;
    panel.hidden = false;
    panel.textContent = "";
    panel.className = "record-panel is-multi";

    openSelectedRows = rowsData;
    openOfferData = null;
    const productGrid = el("div", "selected-product-grid");
    panel.appendChild(productGrid);
    const selection = rowsData;
    const focusRecord = (row, view) => {
      let component = null;
      try {
        component = table.getRows().find((candidate) =>
          candidate.getData().offer_id === row.offer_id);
        nextSelectionPanelMode = view;
        table.deselectRow();
        if (component) component.select();
      } catch (err) { /* the direct open below is the safe fallback */ }
      if (!component) {
        nextSelectionPanelMode = null;
        openOfferPanel(row.offer_id, view, row);
      }
    };
    rowsData.forEach((row) => {
      const placeholder = productSummaryCard(row, null, () => {}, () => {});
      productGrid.appendChild(placeholder);
      fetch("/api/offer/" + encodeURIComponent(SOURCE) + "/" + row.offer_id)
        .then((response) => response.ok
          ? response.json()
          : Promise.reject(new Error("HTTP " + response.status)))
        .then((data) => {
          if (openSelectedRows !== selection || !placeholder.isConnected) return;
          placeholder.replaceWith(productSummaryCard(
            row,
            data,
            () => focusRecord(row, "details"),
            () => focusRecord(row, "history")));
        })
        .catch(() => {
          if (openSelectedRows !== selection || !placeholder.isConnected) return;
          placeholder.classList.add("has-error");
          const empty = placeholder.querySelector(".selected-product-image-empty");
          const description = placeholder.querySelector(".selected-product-description");
          if (empty) empty.textContent = "No product image";
          if (description) description.textContent = "Product details are unavailable right now.";
        });
    });
    panel.focus({preventScroll: true});
    panel.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  // ---- export ---------------------------------------------------------------
  function wireExport() {
    if (!toolbar) return;
    const menu = toolbar.querySelector(".grid-export-menu");
    const trigger = menu && menu.querySelector(".grid-export-trigger");
    const closeMenu = () => {
      if (!menu) return;
      menu.open = false;
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    };
    if (menu && trigger) {
      menu.addEventListener("toggle", () =>
        trigger.setAttribute("aria-expanded", String(menu.open)));
      menu.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !menu.open) return;
        event.preventDefault();
        closeMenu();
        trigger.focus();
      });
      document.addEventListener("click", (event) => {
        if (menu.open && !menu.contains(event.target)) closeMenu();
      });
    }
    toolbar.querySelectorAll("[data-export]").forEach((button) =>
      button.addEventListener("click", () => {
        const kind = button.dataset.export;
        const name = SOURCE + "-" + new Date().toISOString().slice(0, 10);
        closeMenu();
        // CSV and JSON are THIS VIEW: your filters, your column order, your
        // hidden columns. Exporting something other than what is on screen is
        // how a spreadsheet and a screen start disagreeing.
        if (kind === "csv") table.download("csv", name + ".csv");
        else if (kind === "json") table.download("json", name + ".json");
        // Excel is the WHOLE RECORD, and it comes from the server. Two reasons.
        // The browser cannot build it: the details, the price history and the
        // provenance are not in the grid. And it never could — this called
        // Tabulator's xlsx writer, which needs a SheetJS library that has never
        // been vendored here, so the button logged a console error and produced
        // no file at all, silently, for as long as it has existed.
        else if (kind === "xlsx") window.location = "/export/" + encodeURIComponent(SOURCE) + ".xlsx";
      }));
  }

  function wireFeatures() {
    const panel = document.getElementById("grid-features");
    if (!panel) return;
    panel.querySelectorAll("[data-feature]").forEach((box) => {
      const name = box.dataset.feature;
      box.checked = !!features[name];
      box.addEventListener("change", () => {
        features[name] = box.checked;
        // These two switches say whether the capability is OFFERED, and nothing
        // more. Turning one off must therefore also drop a choice made while it
        // was on, or the table would stay grouped by a control that is now off.
        if (name === "tree" && !box.checked && groupedBy.length) {
          groupedBy = [];
          rememberGroups();
        }
        if (name === "rows" && !box.checked && treeBy) { treeBy = ""; remember_(TREE_KEY, ""); }
        saveFeatures();
        build();
      });
    });
    // Behave like a compact tool popup: Escape and an outside click close it,
    // while the native summary remains the only open/close control.
    panel.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        panel.removeAttribute("open");
        panel.querySelector("summary").focus();
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (panel.open && !panel.contains(event.target)) panel.removeAttribute("open");
    });
  }

  // No stored answer means "whatever this source is set to", so the parameter
  // is left off entirely rather than sent as a false that would override it.
  let foldChoice = null;
  try { foldChoice = localStorage.getItem("scrapex-fold-variants-" + SOURCE); }
  catch (err) { foldChoice = null; }
  fetch("/api/table/" + encodeURIComponent(SOURCE)
        + (foldChoice === "on" ? "?fold=1" : foldChoice === "off" ? "?fold=0" : ""))
    .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
    .then((data) => {
      payload = data;
      if (!payload.rows.length) {
        if (note) { note.hidden = false; note.textContent = "No records yet."; }
        return;
      }
      build();
      wireExport();
      wireFeatures();
      wireFoldToggle();
    })
    .catch((err) => {
      if (note) {
        note.hidden = false;
        note.textContent = "Could not load the table: " + err.message;
      }
    });
})();
