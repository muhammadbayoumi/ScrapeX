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
  // Money in the shop's own convention — dot for thousands, comma for the
  // decimals ("1.433,39"), exactly how samehgabriel itself prints "3,8
  // كيلوجرام". Stored precision is PRESERVED, never padded or cut: GPP's
  // 0.404 must stay "0,404" — rounding it to two places would re-lose the
  // precision the local-currency work exists to keep.
  function formatMoney(raw) {
    const s = text(raw);
    if (!s || isNaN(Number(s))) return s;
    const negative = s.startsWith("-");
    const parts = (negative ? s.slice(1) : s).split(".");
    const grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (negative ? "-" : "") + grouped + (parts[1] ? "," + parts[1] : "");
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

  function applyFilters() {
    if (!table) return;
    table.setFilter([...active].map(([field, f]) => ({
      field,
      type: f.values ? "in" : "like",
      value: f.values ? f.values : f.text,
    })));
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
      label.textContent = column + ": " +
        (f.values ? f.values.length + " selected" : "contains " + f.text);
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

    const values = [...new Set(payload.rows.map((r) => r[field])
      .filter((v) => v !== "" && v !== null && v !== undefined))]
      .map(String).sort((a, b) => a.localeCompare(b, "en", {numeric: true}));

    const search = document.createElement("input");
    search.type = "search";
    search.placeholder = "Search…";
    search.setAttribute("aria-label", "Search values");
    box.append(search);

    const list = document.createElement("div");
    list.className = "setfilter-list";
    box.append(list);

    const chosen = new Set(active.get(field) && active.get(field).values
      ? active.get(field).values : values);

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

    function render() {
      const needle = search.value.trim().toLowerCase();
      const visible = needle
        ? values.filter((v) => v.toLowerCase().includes(needle))
        : values;
      list.replaceChildren();
      list.append(row("(Select all)", visible.every((v) => chosen.has(v)), (on) => {
        visible.forEach((v) => on ? chosen.add(v) : chosen.delete(v));
        render();
      }, true));
      // Bounded on purpose: a menu of 3,000 product names is a list nobody
      // scrolls. Search narrows it; the count says what is hidden.
      visible.slice(0, 500).forEach((v) => list.append(
        row(v, chosen.has(v), (on) => { on ? chosen.add(v) : chosen.delete(v); })));
      if (visible.length > 500) {
        const more = document.createElement("p");
        more.className = "hint";
        more.textContent = (visible.length - 500).toLocaleString() +
          " more — type to narrow the list";
        list.append(more);
      }
    }
    search.addEventListener("input", render);
    render();

    const actions = document.createElement("div");
    actions.className = "setfilter-actions";
    const apply = document.createElement("button");
    apply.type = "button";
    apply.textContent = "Apply";
    apply.addEventListener("click", () => {
      if (chosen.size === values.length) active.delete(field);
      else active.set(field, {values: [...chosen]});
      applyFilters();
      document.body.click();          // dismiss the popup
    });
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "ghost";
    reset.textContent = "Clear";
    reset.addEventListener("click", () => {
      active.delete(field);
      applyFilters();
      document.body.click();
    });
    actions.append(apply, reset);
    box.append(actions);
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
      {label: menuLabel("fit-screen", "Autosize This Column"), action: () => autosize(field)},
      {label: menuLabel("unfold-more", "Autosize All Columns"), action: autosizeAll},
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
    fields.forEach((field) => widths.delete(field));
    table.redraw(true);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!table || request !== autosizeRequest) return;
      fields.forEach((field) => {
        const column = table.getColumn(field);
        if (!column || column.getDefinition().resizable === false) return;
        column.setWidth(true);
        const measured = Math.max(
          GRID_MIN_COLUMN_WIDTH,
          Math.ceil(column.getWidth()),
          measureHeaderWidth(column)
        );
        column.setWidth(measured);
        widths.set(field, measured);
      });
      table.redraw(false);
    }));
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
    if (key === "effective_price") {
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
    if (key === "tax_label") {
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
        const candidates = [[rowData.product_url, "this product's own page"],
                            [state.tax_statement_url, "the source's own statement"]];
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
          link.title = (state.tax_label || "") + " — open " + what;
          return link;
        }
        const span = document.createElement("span");
        span.textContent = state.tax_short || "—";
        span.title = state.tax_label || "";
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
    if (key === "usd_price" || key === "previous_price" ||
        key === "min_price" || key === "max_price") {
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
        // Server-computed "+5.00 (+32.3%)" re-rendered in the shop's own
        // number convention.
        span.textContent = String(cell.getValue() || "").replace(
          /-?\d+\.\d+/g, (m) => formatMoney(m)).replace(/\((.*)\)/,
          (m, inner) => "(" + inner.replace(".", ",") + ")");
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
          ? String(value).replace(".", ",") + "%"
          : formatMoney(value);
        return span;
      };
    }
    if (key === "open") {
      // The arrow the owner missed: straight to the record on the site.
      return (cell) => {
        // product_url is already the most specific address the server has for
        // this row — the variation's own page where the source publishes one.
        // The grid does not choose; it opens what the row was given.
        const url = cell.getRow().getData().product_url;
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
        const url = text(data.official_source_url);
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
    if (table) { widthsFromTable(); table.destroy(); table = null; }

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
        widthGrow: col.key === "product_name" || col.key === "product_name_ar"
                   || col.key === "country_code_alpha2" ? 2 : 1,
      };
      // Numbers and dates read right-aligned; text reads from its own side.
      if (col.key === "effective_price") def.hozAlign = "right";
      if (col.key === "price_changed_on" || col.key === "last_confirmed_on" ||
          col.key === "was_price" || col.key === "discount" ||
          col.key === "discount_pct" ||
          col.key === "usd_price" || col.key === "previous_price" ||
          col.key === "price_change" || col.key === "min_price" ||
          col.key === "max_price" || col.key === "observations") {
        def.hozAlign = "right";
      }
      // Numeric sort for the ranking columns: a string sort would put 9 above
      // 11 and defeat the whole point of the USD column.
      if (col.key === "usd_price" || col.key === "previous_price" ||
          col.key === "min_price" || col.key === "max_price" ||
          col.key === "discount" || col.key === "discount_pct" ||
          col.key === "observations") {
        def.sorter = "number";
      }
      if (col.key === "open") {
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
        if (c.field === "effective_price") { c.topCalc = "avg"; c.topCalcParams = {precision: 2}; }
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
    const note = document.createElement("span");
    note.className = "muted";
    note.textContent = "Language:";
    wrap.append(note);
    const buttons = {};
    for (const [code, label] of [["en", "EN"], ["ar", "AR"]]) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = label;
      b.addEventListener("click", () => apply(code, true));
      buttons[code] = b;
      wrap.append(b);
    }
    host.append(wrap);
    function apply(code, save) {
      nameLang = code;
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
      for (const [c, b] of Object.entries(buttons)) {
        b.setAttribute("aria-pressed", String(c === nameLang));
        b.classList.toggle("pill", c === nameLang);
      }
      // The record open underneath is showing the other language's details;
      // leaving it as it was would make the switch look half-connected.
      if (save) redrawOpenPanel();
    }
    apply(nameLang, false);
  }

  function widthsFromTable() {
    try {
      table.getColumns().forEach((c) => {
        const f = c.getField();
        if (f) widths.set(f, c.getWidth());
      });
    } catch (err) { /* a rebuild mid-render is not worth failing over */ }
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
    return box;
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

  // Descriptions arrive as one string with newlines (the shop's own paragraph
  // breaks). Printing that into a table cell collapsed a datasheet into one
  // unreadable line; the breaks the source wrote are kept as paragraphs.
  function prose(value) {
    const box = el("div", "record-prose");
    String(value == null ? "" : value).split(/\r?\n/).forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      const paragraph = el("p", "", trimmed);
      paragraph.dir = "auto";
      box.appendChild(paragraph);
    });
    return box;
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

  function summaryDescription(details) {
    const descriptions = (details || []).filter((item) =>
      (item.group || "").toLowerCase() === "description");
    const paired = pairByLanguage(descriptions);
    return paired.map((item) => text(item.value)).filter(Boolean).join(" ");
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
    box.appendChild(media);

    const body = el("div", "selected-product-body");
    const titleRow = el("div", "selected-product-title-row");
    const name = el("h3", "selected-product-name",
      text(pickLang(row.product_name, row.product_name_ar) || offer.product_name || offer.product_name_ar || "Unnamed record"));
    name.dir = "auto";
    titleRow.appendChild(name);
    const live = safeUrl(row.product_url || offer.product_url || "");
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
    const description = summaryDescription(details);
    const short = el("p", "selected-product-description",
      description || (data ? "No short description was published for this product."
                           : "Loading product details…"));
    short.dir = "auto";
    body.appendChild(short);

    const meta = [row.sku || offer.sku || "", pickLang(row.category, row.category_ar)]
      .filter(Boolean).join(" · ");
    if (meta) {
      const line = el("p", "selected-product-meta", meta);
      line.dir = "auto";
      body.appendChild(line);
    }

    const price = el("div", "selected-product-price");
    price.appendChild(el("span", "selected-product-price-label", "Current price"));
    const value = el("strong", "");
    value.appendChild(money(row.effective_price, row.currency || offer.currency,
                            offer.unit || row.unit));
    price.appendChild(value);
    body.appendChild(price);

    const actions = el("div", "selected-product-actions");
    const detailsButton = el("button", "record-action record-action-primary", "View details");
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
    const detailSections = new Map([
      ["description", []],
      ["specifications", []],
      ["attachments", []],
      ["media", []],
    ]);
    const historySections = new Map([
      ["price", []],
      ["changes", []],
      ["observations", []],
    ]);

    const workspace = el("div", "record-product-workspace");
    const productGrid = el("div", "selected-product-grid is-single");
    const inspector = el("section", "record-inspector");
    inspector.hidden = true;
    inspector.setAttribute("aria-label", "Selected product information");

    const inspectorHead = el("header", "record-inspector-head");
    const inspectorTitle = el("div", "record-inspector-heading");
    inspectorTitle.appendChild(el("span", "record-selection-kicker", "Product record"));
    inspectorTitle.appendChild(el("h3", "", "Details"));
    inspectorHead.appendChild(inspectorTitle);
    const inspectorControls = el("div", "record-inspector-controls");
    const detailsTab = el("button", "record-inspector-tab", "Details");
    detailsTab.type = "button";
    const historyTab = el("button", "record-inspector-tab", "History");
    historyTab.type = "button";
    const closeInspector = el("button", "record-action record-action-subtle", "Close");
    closeInspector.type = "button";
    inspectorControls.append(detailsTab, historyTab, closeInspector);
    inspectorHead.appendChild(inspectorControls);
    inspector.appendChild(inspectorHead);

    const inspectorMain = el("div", "record-inspector-main");
    const inspectorNav = el("nav", "record-inspector-nav");
    inspectorNav.setAttribute("aria-label", "Product information sections");
    const inspectorContent = el("div", "record-inspector-content");
    inspectorMain.append(inspectorNav, inspectorContent);
    inspector.appendChild(inspectorMain);

    const summary = productSummaryCard(
      row,
      data,
      () => openInspector("details"),
      () => openInspector("history"));
    productGrid.appendChild(summary);
    workspace.append(productGrid, inspector);
    panel.appendChild(workspace);

    const detailDefinitions = [
      {key: "description", label: "Description", icon: "description"},
      {key: "specifications", label: "Specifications", icon: "tune"},
      {key: "attachments", label: "Attachments", icon: "insert-drive-file"},
      {key: "media", label: "Media", icon: "photo-camera"},
    ];
    const historyDefinitions = [
      {key: "price", label: "Price history", icon: "trending-up"},
      {key: "changes", label: "Changes", icon: "history"},
      {key: "observations", label: "Observations", icon: "schedule"},
    ];

    function setSummaryMode(view) {
      summary.querySelectorAll("[data-inspector-view]").forEach((button) => {
        const active = !inspector.hidden && button.dataset.inspectorView === view;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
    }

    function renderInspector(view, requestedKey) {
      const isHistory = view === "history";
      const definitions = isHistory ? historyDefinitions : detailDefinitions;
      const sections = isHistory ? historySections : detailSections;
      const firstWithContent = definitions.find((item) => sections.get(item.key).length);
      const validRequested = definitions.some((item) => item.key === requestedKey);
      const activeKey = validRequested
        ? requestedKey
        : (firstWithContent ? firstWithContent.key : definitions[0].key);
      inspector.dataset.view = view;
      inspectorTitle.querySelector("h3").textContent = isHistory ? "History" : "Details";
      detailsTab.classList.toggle("is-active", !isHistory);
      historyTab.classList.toggle("is-active", isHistory);
      detailsTab.setAttribute("aria-pressed", String(!isHistory));
      historyTab.setAttribute("aria-pressed", String(isHistory));
      setSummaryMode(view);
      inspectorNav.textContent = "";
      inspectorContent.textContent = "";

      definitions.forEach((item) => {
        const button = el("button", item.key === activeKey ? "is-active" : "");
        button.type = "button";
        button.title = item.label;
        button.setAttribute("aria-label", item.label);
        button.setAttribute("aria-pressed", String(item.key === activeKey));
        button.appendChild(materialIconElement(item.icon, "record-inspector-nav-icon"));
        button.addEventListener("click", () => renderInspector(view, item.key));
        inspectorNav.appendChild(button);
      });

      const active = definitions.find((item) => item.key === activeKey);
      const contentHead = el("header", "record-inspector-content-head");
      contentHead.appendChild(el("span", "record-selection-kicker",
        isHistory ? "Recorded over time" : "Collected from the source"));
      contentHead.appendChild(el("h4", "", active.label));
      if (isHistory) {
        const full = el("a", "record-action record-action-subtle", "Full record");
        full.href = "/source/" + encodeURIComponent(SOURCE) + "/offer/" + row.offer_id;
        contentHead.appendChild(full);
      }
      inspectorContent.appendChild(contentHead);
      const sectionCards = sections.get(activeKey);
      if (!sectionCards.length) {
        inspectorContent.appendChild(el("div", "record-inspector-empty",
          "No " + active.label.toLowerCase() + " are available for this product."));
        return;
      }
      const cards = el("div", "record-cards");
      sectionCards.forEach((section) => cards.appendChild(section));
      inspectorContent.appendChild(cards);
    }

    function openInspector(view) {
      openOfferMode = view;
      inspector.hidden = false;
      workspace.classList.add("has-inspector");
      panel.classList.add("has-expanded-details");
      renderInspector(view);
      inspector.scrollIntoView({behavior: "smooth", block: "nearest"});
    }

    function hideInspector() {
      openOfferMode = "record";
      inspector.hidden = true;
      workspace.classList.remove("has-inspector");
      panel.classList.remove("has-expanded-details");
      setSummaryMode("");
      summary.scrollIntoView({behavior: "smooth", block: "nearest"});
    }
    detailsTab.addEventListener("click", () => renderInspector("details"));
    historyTab.addEventListener("click", () => renderInspector("history"));
    closeInspector.addEventListener("click", hideInspector);

    // Name and classification in the language the toggle is set to, falling
    // back to the one the source published when it published only one.
    // The details the source printed for this product — colours, lengths,
    // categories, warranties — grouped as the page grouped them. Scraped
    // content throughout: names as text, URLs linked only when they parse.
    // The PICTURE leads — the same shape the sites themselves use, and the
    // same shape for every source (owner's ruling: one output, not one panel
    // per connector). Media is pulled out of the attribute groups below so it
    // can never end up buried under a table of text.
    if (details.length) {
      const gallery = el("div", "detail-gallery");
      let shown = 0;
      details.filter((d) => (d.group || "") === "Media" && d.url).forEach((d) => {
        const href = safeUrl(d.url);
        if (!href) return;                    // the spec list still names it
        const frame = document.createElement("a");
        frame.href = href;
        frame.target = "_blank";
        frame.rel = "noopener noreferrer";
        frame.title = text(d.value || "");
        const picture = document.createElement("img");
        picture.src = href;
        picture.alt = text(d.value || "");
        picture.loading = "lazy";
        picture.className = "detail-image";
        frame.appendChild(picture);
        gallery.appendChild(frame);
        shown += 1;
      });
      if (shown) {
        const box = card(shown === 1 ? "Picture" : "Pictures (" + shown + ")", "record-card-wide");
        box.appendChild(gallery);
        detailSections.get("media").push(box);
      }
    }

    if (details.length) {
      const groups = new Map();
      details.forEach((d) => {
        const key = d.group || "Details";
        // Media already leads the panel as pictures; listing the same rows
        // again as file names would be the record said twice.
        if (key === "Media" && d.url) return;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(d);
      });
      // Description first (it is what the product IS), then the measured
      // specifications, then the files. Any group a connector invents that this
      // list does not know about keeps its own card, after the known ones.
      const order = ["Description", "Specifications", "Specs", "Details", "Attachments"];
      const names = [...groups.keys()].sort((a, b) => {
        const rankA = order.indexOf(a), rankB = order.indexOf(b);
        return (rankA < 0 ? order.length : rankA) - (rankB < 0 ? order.length : rankB);
      });
      names.forEach((name) => {
        const items = groups.get(name);
        const paired = pairByLanguage(items);
        if (name === "Description") {
          const box = card("Description", "record-card-wide");
          paired.forEach((entry) => {
            // "DESCRIPTION / Description" said twice is the card title read
            // back to the reader; a label only earns a line when it adds one.
            const label = (entry.label || "").trim();
            if (label && label.toLowerCase() !== name.toLowerCase()) {
              box.appendChild(el("h4", "record-prose-title", label));
            }
            // One language — whichever the toggle is set to. This briefly
            // showed both, side by side, and the owner's answer was that the
            // switch exists precisely so the tables under the table do not
            // repeat the same paragraph in two languages.
            box.appendChild(prose(entry.value));
          });
          detailSections.get("description").push(box);
          return;
        }
        if (name === "Attachments") {
          const box = card("Attachments", "record-card-wide");
          box.appendChild(fileCards(paired));
          detailSections.get("attachments").push(box);
          return;
        }
        const box = card(name);
        box.appendChild(specList(paired));
        detailSections.get(name === "Media" ? "media" : "specifications").push(box);
      });
    }

    // Fields the owner moved OUT of the table (Choose Columns -> hide) are
    // shown here instead, so nothing is ever lost by tidying the grid: hide
    // moves a field into the details, show moves it back.
    const moved = payload.moved_to_details || [];
    if (moved.length && openOfferRow) {
      const box = card("Moved out of the table");
      box.appendChild(specList(moved.map((column) => ({
        label: column.label || column.key, value: text(openOfferRow[column.key]),
      }))));
      detailSections.get("specifications").push(box);
    }

    // The change-only timeline: the first price and each REAL move.
    const periods = data.periods || [];
    const timeline = card("Price changes", "record-card-wide");
    if (!periods.length) {
      timeline.appendChild(el("p", "muted", "No derived history yet for this record."));
    } else {
      timeline.appendChild(miniTable(
        ["From", "Until", "Price", "Why it opened"],
        periods.map((p) => [
          (p.first_detected_at || "").slice(0, 10),
          (p.closed_at || "").slice(0, 10) || "current",
          money(p.effective_price, p.currency, offer.unit),
          (p.opened_because || "").replace(/_/g, " "),
        ])));
    }
    historySections.get("price").push(timeline);

    const changes = data.changes || [];
    const feed = card("Changes", "record-card-wide");
    if (!changes.length) {
      feed.appendChild(el("p", "muted", "No change events recorded yet."));
    } else {
      feed.appendChild(miniTable(
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
    }
    historySections.get("changes").push(feed);

    const observations = data.observations || [];
    const recorded = card("What was recorded", "record-card-wide");
    if (!observations.length) {
      recorded.appendChild(el("p", "muted", "No observations recorded yet."));
    } else {
      recorded.appendChild(miniTable(
        ["Date", "Price", "Where it came from"],
        observations.map((o) => [
          o.business_date || "",
          money(o.effective_price, o.currency, offer.unit),
          o.provenance === "reported" ? "reported by the source" : "observed by a crawl",
        ])));
    }
    historySections.get("observations").push(recorded);

    if (mode === "details" || mode === "history") openInspector(mode);

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
    toolbar.querySelectorAll("[data-export]").forEach((button) =>
      button.addEventListener("click", () => {
        const kind = button.dataset.export;
        const name = SOURCE + "-" + new Date().toISOString().slice(0, 10);
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

  fetch("/api/table/" + encodeURIComponent(SOURCE))
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
    })
    .catch((err) => {
      if (note) {
        note.hidden = false;
        note.textContent = "Could not load the table: " + err.message;
      }
    });
})();
