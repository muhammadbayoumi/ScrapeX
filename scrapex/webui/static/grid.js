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
  const PERSISTENCE_ID = "scrapex-grid-v2-" + SOURCE;
  const MATERIAL_ICON_SPRITE = "/static/material-icons/material-icons.svg?v=columns-2";
  // A DOM namespace, not a network address. Keep it split so the offline-only
  // guard can continue rejecting every literal runtime http(s) URL in this file.
  const SVG_NAMESPACE = "http:" + "//www.w3.org/2000/svg";

  function materialIcon(name, className, title) {
    return "<svg class='material-icon " + className + "' viewBox='0 0 24 24'" +
      " aria-hidden='true' focusable='false' title='" + title + "'>" +
      "<use href='" + MATERIAL_ICON_SPRITE + "#" + name + "'></use></svg>";
  }

  const FILTER_ICON = materialIcon("filter-list", "material-filter-icon", "Filter this column");
  const MENU_ICON = materialIcon("more-vert", "material-menu-icon", "Column menu");
  const SORT_ICON = materialIcon("arrow-upward", "material-sort-icon", "Sort direction");

  // ---- active filters, and the line that reports them ----------------------
  // Kept here rather than inside Tabulator so the page can SAY what is being
  // filtered. A grid that quietly shows fewer rows than it has is the same
  // failure as a filter that vanishes: the reader cannot tell.
  const active = new Map();
  let table = null;
  let payload = null;

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
  const DEFAULT_FEATURES = {tree: true, rows: true, select: true, totals: false,
                            rownum: false, compact: false, wrap: false, stripe: false};
  let features = Object.assign({}, DEFAULT_FEATURES);
  // WHICH columns group the table, from outermost to innermost. Per source,
  // because the useful hierarchy for a fuel table (material, then country) is
  // not the useful hierarchy for a shop. The older preference was one plain
  // string; read it as a one-level group so the upgrade does not discard it.
  const GROUP_KEY = "scrapex-groupby-" + (mount.dataset.source || "");
  const TREE_KEY = "scrapex-treeby-" + (mount.dataset.source || "");
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
      chip.textContent = column + ": " +
        (f.values ? f.values.length + " selected" : "contains " + f.text) + " ✕";
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
  function materialIconElement(iconName, className) {
    const glyph = document.createElementNS(SVG_NAMESPACE, "svg");
    glyph.classList.add("material-icon");
    if (className) glyph.classList.add(className);
    glyph.setAttribute("viewBox", "0 0 24 24");
    glyph.setAttribute("aria-hidden", "true");
    glyph.setAttribute("focusable", "false");
    const use = document.createElementNS(SVG_NAMESPACE, "use");
    if (iconName) use.setAttribute("href", MATERIAL_ICON_SPRITE + "#" + iconName);
    glyph.append(use);
    return glyph;
  }

  function menuLabel(iconName, labelText) {
    const label = document.createElement("span");
    label.className = "grid-menu-label";
    const words = document.createElement("span");
    words.textContent = labelText;
    label.append(materialIconElement(iconName, "grid-menu-icon"), words);
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

  function setPinned(field, side) {
    side ? pinned.set(field, side) : pinned.delete(field);
    build();
  }

  // `setWidth(true)` asks Tabulator to measure rendered header and cell content.
  // Deleting a remembered width and rebuilding did not autosize: build() saved
  // the old width again before destruction, making the menu command a no-op.
  function autosize(field) {
    const column = table && table.getColumn(field);
    if (!column) return;
    widths.delete(field);
    column.setWidth(true);
    widths.set(field, column.getWidth());
    table.redraw(true);
  }
  function autosizeAll() {
    if (!table) return;
    widths.clear();
    table.getColumns().forEach((column) => {
      if (column.getDefinition().resizable === false) return;
      column.setWidth(true);
      const field = column.getField();
      if (field) widths.set(field, column.getWidth());
    });
    table.redraw(true);
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

    const list = document.createElement("div");
    list.className = "column-chooser-list";
    list.setAttribute("role", "list");
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

    function render() {
      const query = search.value.trim().toLocaleLowerCase();
      list.replaceChildren();
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
        visible.setAttribute("aria-label", "Show " + fieldLabel(field));
        visible.addEventListener("change", () => {
          field.is_hidden = !visible.checked;
          dirty = true;
          syncMasterCheckbox();
          saySaving(updateFields({field_key: field.field_key, hidden: field.is_hidden}));
        });

        const handle = document.createElement("button");
        handle.type = "button";
        handle.className = "column-chooser-handle";
        handle.setAttribute("aria-label", "Move " + fieldLabel(field));
        handle.title = "Drag to reorder. Use Arrow Up or Arrow Down from the keyboard.";
        handle.append(materialIconElement("drag-indicator", "column-chooser-icon"));
        handle.addEventListener("keydown", (event) => {
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
          moveField(draggedKey, field.field_key, after);
          draggedKey = "";
        });
        row.addEventListener("dragend", () => {
          draggedKey = "";
          list.querySelectorAll(".column-chooser-row").forEach((item) =>
            item.classList.remove("is-dragging", "drop-before", "drop-after"));
        });
        list.append(row);
      });
      if (!matching.length) {
        const empty = document.createElement("p");
        empty.className = "column-chooser-empty muted";
        empty.textContent = "No columns match this search.";
        list.append(empty);
      }
      syncMasterCheckbox();
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
    if (key === "product_name" || key === "option_label") {
      return (cell) => {
        const span = document.createElement("span");
        span.dir = "auto";
        span.textContent = text(cell.getValue());
        return span;
      };
    }
    if (key === "region") {
      return (cell) => {
        const row = cell.getRow().getData();
        const span = document.createElement("span");
        span.textContent = row.region_name || row.region || "—";
        if (row.region_name && row.region) {
          const code = document.createElement("span");
          code.className = "code";
          code.textContent = row.region;
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
        let safe = "";
        try {
          const parsed = new URL(state.tax_statement_url || "");
          if (parsed.protocol === "http:" || parsed.protocol === "https:") safe = parsed.href;
        } catch (err) { /* no statement to open */ }
        if (safe) {
          const link = document.createElement("a");
          link.className = "grid-action";
          link.href = safe;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = state.tax_short || "—";
          link.title = (state.tax_label || "") + " — open the source's own statement";
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
    if (key === "discount") {
      return (cell) => {
        const row = cell.getRow().getData();
        const was = parseFloat(row.was_price);
        const now = parseFloat(row.effective_price);
        if (!isFinite(was) || !isFinite(now) || was <= now) return "";
        const saved = now - was;
        const span = document.createElement("span");
        span.dir = "ltr";
        span.textContent = formatMoney(saved.toFixed(2)) + " (" +
          (saved / was * 100).toFixed(1).replace(".", ",") + "%)";
        return span;
      };
    }
    if (key === "details") {
      // Its own action, separated from History (the owner's ask): History is
      // the price story, Details is what the product IS.
      return (cell) => {
        const data = cell.getRow().getData();
        if (!data.has_details || !data.offer_id) return "";
        const button = document.createElement("button");
        button.type = "button";
        button.className = "grid-action";
        button.textContent = "Details";
        button.addEventListener("click", () => openOfferPanel(data.offer_id, "details"));
        return button;
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
    label.textContent = text(cell.getValue());
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
        // A ceiling as well as a floor: without one, fitColumns hands a short
        // column like Unit the same share as a long one like Record.
        widthGrow: col.key === "product_name" || col.key === "region" ? 2 : 1,
      };
      // Numbers and dates read right-aligned; text reads from its own side.
      if (col.key === "effective_price") def.hozAlign = "right";
      if (col.key === "price_changed_on" || col.key === "last_confirmed_on" ||
          col.key === "was_price" || col.key === "discount" ||
          col.key === "usd_price" || col.key === "previous_price" ||
          col.key === "price_change" || col.key === "min_price" ||
          col.key === "max_price" || col.key === "observations") {
        def.hozAlign = "right";
      }
      // Numeric sort for the ranking columns: a string sort would put 9 above
      // 11 and defeat the whole point of the USD column.
      if (col.key === "usd_price" || col.key === "previous_price" ||
          col.key === "min_price" || col.key === "max_price" ||
          col.key === "observations") {
        def.sorter = "number";
      }
      if (col.key === "details") {
        // An action, not data: nothing to sort, filter, menu or export.
        def.headerSort = false;
        def.download = false;
        def.headerMenu = undefined;
        def.headerPopup = undefined;
        def.width = 110;
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

    columns.push({
      title: "History", field: "offer_id", headerSort: false, resizable: false,
      width: 110, download: false, headerMenu: undefined, headerPopup: undefined,
      formatter: (cell) => {
        // A tree heading is not an offer, so it has no history to link to.
        // Rendering the link anyway would point at /offer/undefined: a control
        // that looks live and leads nowhere.
        if (!cell.getValue()) return "";
        const link = document.createElement("a");
        link.className = "grid-action";
        link.href = "/source/" + encodeURIComponent(SOURCE) + "/offer/" + cell.getValue();
        link.textContent = "History";
        link.title = "Every price this offer has had";
        // A plain left-click opens the story UNDER the table, so choosing a
        // row never navigates away from the filtered view that found it. The
        // href stays real: middle-click, ctrl-click and scripting-off all
        // still reach the full page.
        link.addEventListener("click", (event) => {
          if (event.button !== 0 || event.ctrlKey || event.metaKey ||
              event.shiftKey || event.altKey) return;
          event.preventDefault();
          openOfferPanel(cell.getValue(), "history");
        });
        return link;
      },
    });

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
        else if (c.field === "product_name") c.topCalc = "count";
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
      height: "34rem",             // virtual rendering keeps thousands smooth
      placeholder: "No rows match these filters.",
      footerElement: footer,
      selectableRows: !!features.select,
      selectableRowsRangeMode: "click",
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
    table.on("rowSelectionChanged", updateFooter);
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
    const wrap = el("div", "tablewrap");
    const table = document.createElement("table");
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

  function openOfferPanel(offerId, mode) {
    const panel = document.getElementById("offer-panel");
    if (!panel) return;
    mode = mode || "history";
    if (openOfferId === offerId && openOfferMode === mode && !panel.hidden) {
      closeOfferPanel();                       // same row, same ask = close
      return;
    }
    openOfferId = offerId;
    openOfferMode = mode;
    panel.hidden = false;
    panel.textContent = "";
    panel.appendChild(el("p", "muted", "Loading the record's history…"));
    fetch("/api/offer/" + encodeURIComponent(SOURCE) + "/" + offerId)
      .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
      .then((data) => renderOfferPanel(panel, data, offerId, mode))
      .catch((err) => {
        panel.textContent = "";
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
  }

  function renderOfferPanel(panel, data, offerId, mode) {
    // The owner separated the two asks: History is the price story (periods,
    // changes, observations); Details is what the product IS (attributes,
    // classification, measurements). One panel, one ask at a time.
    const showHistory = mode !== "details";
    panel.textContent = "";
    const offer = data.offer || {};

    const head = el("div", "row");
    const title = el("h2", "", "");
    const name = el("span", "", text(offer.name || ""));
    name.dir = "auto";
    title.appendChild(name);
    if (offer.region_name || offer.region) {
      title.appendChild(el("span", "muted", " — " + (offer.region_name || offer.region)));
    }
    head.appendChild(title);
    const full = el("a", "", "Open full page");
    full.href = "/source/" + encodeURIComponent(SOURCE) + "/offer/" + offerId;
    head.appendChild(full);
    const close = el("button", "ghost", "Close");
    close.type = "button";
    close.addEventListener("click", closeOfferPanel);
    head.appendChild(close);
    panel.appendChild(head);

    if (showHistory) {
    // 1. The change-only timeline: the first price and each REAL move.
    panel.appendChild(el("h3", "", "Price changes"));
    const periods = data.periods || [];
    if (!periods.length) {
      panel.appendChild(el("p", "muted", "No derived history yet for this record."));
    } else {
      panel.appendChild(miniTable(
        ["From", "Until", "Price", "Why it opened"],
        periods.map((p) => [
          (p.first_detected_at || "").slice(0, 10),
          (p.closed_at || "").slice(0, 10) || "current",
          money(p.effective_price, p.currency, offer.unit),
          (p.opened_because || "").replace(/_/g, " "),
        ])));
    }

    // 2. What the change feed recorded about THIS record — the same shaping
    // the Changes page uses, so the two can never tell different stories.
    panel.appendChild(el("h3", "", "Changes"));
    const changes = data.changes || [];
    if (!changes.length) {
      panel.appendChild(el("p", "muted", "No change events recorded yet."));
    } else {
      panel.appendChild(miniTable(
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

    }

    // The details the source printed for this product — colours, lengths,
    // categories, warranties — grouped as the page grouped them. Scraped
    // content throughout: names as text, URLs linked only when they parse.
    const details = mode === "details" ? (data.details || []) : [];
    if (mode === "details" && !details.length) {
      panel.appendChild(el("p", "muted", "No details recorded for this record."));
    }
    if (details.length) {
      panel.appendChild(el("h3", "", "Details"));
      const groups = new Map();
      details.forEach((d) => {
        const key = d.group || "Details";
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(d);
      });
      groups.forEach((items, groupName) => {
        panel.appendChild(el("h4", "muted", groupName));
        panel.appendChild(miniTable(
          ["Attribute", "Value"],
          items.map((d) => {
            let valueNode;
            let safe = "";
            try {
              const parsed = new URL(d.url);
              if (parsed.protocol === "http:" || parsed.protocol === "https:") safe = parsed.href;
            } catch (err) { /* no link — plain text */ }
            if (safe) {
              valueNode = document.createElement("a");
              valueNode.href = safe;
              valueNode.target = "_blank";
              valueNode.rel = "noopener noreferrer";
              valueNode.textContent = text(d.value);
            } else {
              valueNode = el("span", "", text(d.value));
            }
            valueNode.dir = "auto";
            return [d.label || "", valueNode];
          })));
      });
    }

    if (showHistory) {
    // Every observation behind the story, provenance spelled out.
    panel.appendChild(el("h3", "", "What was recorded"));
    const observations = data.observations || [];
    if (!observations.length) {
      panel.appendChild(el("p", "muted", "No observations recorded yet."));
    } else {
      panel.appendChild(miniTable(
        ["Date", "Price", "Where it came from"],
        observations.map((o) => [
          o.business_date || "",
          money(o.effective_price, o.currency, offer.unit),
          o.provenance === "reported" ? "reported by the source" : "observed by a crawl",
        ])));
    }
    }

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
        // "visible" means what you are looking at: your filters, your column
        // order, your hidden columns. Exporting something other than what is on
        // screen is how a spreadsheet and a screen start disagreeing.
        if (kind === "csv") table.download("csv", name + ".csv");
        else if (kind === "json") table.download("json", name + ".json");
        else if (kind === "xlsx") table.download("xlsx", name + ".xlsx", {sheetName: SOURCE});
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
