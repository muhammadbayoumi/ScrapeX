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
  const DEFAULT_FEATURES = {tree: true, totals: false, rownum: false,
                            compact: false, wrap: false, stripe: false};
  let features = Object.assign({}, DEFAULT_FEATURES);
  try {
    const saved = JSON.parse(localStorage.getItem(FEATURE_KEY) || "null");
    if (saved) features = Object.assign(features, saved);
  } catch (err) { /* a corrupt preference must not stop the table loading */ }

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
    let line = active.size
      ? shown.toLocaleString() + " of " + all.toLocaleString() + " rows"
      : shown.toLocaleString() + " rows";
    if (payload && payload.truncated) {
      // Never let a prefix look like the whole. The filters below can only see
      // what was loaded, and the reader is told so plainly.
      line += " — loaded " + payload.returned.toLocaleString() + " of " +
              payload.total.toLocaleString() + "; filters search only what is loaded";
    }
    note.textContent = line;
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
  function columnMenu(event, column) {
    const field = column.getField();
    return [
      {label: "↑  Sort ascending", action: () => column.getTable().setSort(field, "asc")},
      {label: "↓  Sort descending", action: () => column.getTable().setSort(field, "desc")},
      {separator: true},
      {label: "📌  Pin to the left", action: () => setFrozen(field, true)},
      {label: "Unpin", action: () => setFrozen(field, false)},
      {separator: true},
      {label: "Fit this column to its content", action: () => autosize(field)},
      {label: "Fit every column", action: () => autosizeAll()},
      {separator: true},
      {label: "Hide this column", action: () => { column.hide(); remember(field, true); }},
      {label: "Show every column", action: showAll},
      {label: "Reset the layout", action: resetLayout},
    ];
  }

  // Pinning and autosizing rebuild the grid: Tabulator fixes `frozen` and
  // width at construction, so changing them means constructing again. Cheap at
  // these row counts, and it keeps one definition of a column rather than two.
  const frozen = new Set();
  const widths = new Map();

  function setFrozen(field, on) {
    on ? frozen.add(field) : frozen.delete(field);
    build();
  }
  function autosize(field) { widths.delete(field); build(); }
  function autosizeAll() { widths.clear(); build(); }
  function showAll() {
    payload.columns.forEach((c) => remember(c.key, false));
    location.reload();
  }
  function resetLayout() {
    frozen.clear();
    widths.clear();
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
        price.textContent = text(cell.getValue()) + " " + text(row.currency);
        box.append(price);
        // A price may lose its column but never its unit.
        if (row.unit) {
          const per = document.createElement("span");
          per.className = "per";
          per.textContent = " / " + row.unit;
          box.append(per);
        }
        return box;
      };
    }
    if (key === "tax_label") {
      // The verdict travels once per REGION, not per row — it is identical for
      // every row sharing one, and sending it per row cost a third of the
      // payload for nothing.
      return (cell) => {
        const state = payload.tax_by_region[cell.getRow().getData().region] || {};
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
    return undefined;
  }

  function build() {
    if (table) { widthsFromTable(); table.destroy(); table = null; }

    const columns = payload.columns.map((col) => {
      const def = {
        title: col.label,
        field: col.key,
        headerMenu: columnMenu,
        headerFilter: false,
        headerPopup: filterPopup,
        headerPopupIcon: "<span class='filter-icon' title='Filter this column'>⛛</span>",
        resizable: true,
        headerSort: true,
        minWidth: 90,
      };
      const formatter = formatterFor(col.key);
      if (formatter) def.formatter = formatter;
      if (frozen.has(col.key)) def.frozen = true;
      if (widths.has(col.key)) def.width = widths.get(col.key);
      return def;
    });

    columns.push({
      title: "", field: "offer_id", headerSort: false, resizable: false,
      width: 100, download: false,
      formatter: (cell) => {
        const link = document.createElement("a");
        link.href = "/source/" + encodeURIComponent(SOURCE) + "/offer/" + cell.getValue();
        link.textContent = "History";
        link.title = "Every price this offer has had";
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

    const options = {
      data: payload.rows,
      columns: columns,
      layout: "fitDataStretch",
      movableColumns: true,        // drag a header to build the table you want
      height: "34rem",             // virtual rendering keeps thousands smooth
      placeholder: "No rows match these filters.",
      // The owner's arrangement survives closing the browser.
      persistence: {sort: true, filter: false, columns: ["width", "visible"]},
      persistenceID: "scrapex-" + SOURCE,
    };

    // Nesting is decided by the SERVER from what the source actually publishes:
    // a commodity source reads as material -> countries, and a shop whose every
    // row shares one region has nothing to nest.
    if (features.tree && payload.tree && payload.tree.by) {
      options.groupBy = payload.tree.by;
      options.groupStartOpen = false;
      options.groupHeader = (value, count) =>
        text(value) + " <span class='muted'>· " + count + "</span>";
    }

    mount.classList.toggle("compact", !!features.compact);
    mount.classList.toggle("wrap", !!features.wrap);
    mount.classList.toggle("striped", !!features.stripe);

    table = new Tabulator(mount, options);
    table.on("tableBuilt", () => { applyFilters(); describe(); });
    table.on("dataFiltered", describe);
  }

  function widthsFromTable() {
    try {
      table.getColumns().forEach((c) => {
        const f = c.getField();
        if (f) widths.set(f, c.getWidth());
      });
    } catch (err) { /* a rebuild mid-render is not worth failing over */ }
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
      // The tree checkbox is only meaningful where the SERVER found something
      // to nest. Offering it on a table that cannot group would be a control
      // that does nothing, which is worse than one that is absent.
      if (name === "tree" && !(payload.tree && payload.tree.by)) {
        box.disabled = true;
        box.checked = false;
        box.closest("label").append(
          Object.assign(document.createElement("span"),
            {className: "muted", textContent: " — nothing to group here"}));
        return;
      }
      box.addEventListener("change", () => {
        features[name] = box.checked;
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
        if (note) note.textContent = "No records yet.";
        return;
      }
      build();
      wireExport();
      wireFeatures();
    })
    .catch((err) => {
      if (note) note.textContent = "Could not load the table: " + err.message;
    });
})();
