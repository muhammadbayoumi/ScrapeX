/* AUTHORED IN design/datagrid.js, and copied byte-for-byte into
 * scrapex/webui/static/datagrid.js and extension/datagrid.js by tools/sync_design_assets.py.
 *
 * IF THE PATH ABOVE YOUR EDITOR IS NOT design/, THIS IS A GENERATED COPY, and
 * an edit made here is reverted by the next sync without a word. Edit the
 * design/ file and run the tool.
 */
// The grid's renderer: Supabase's Data Grid pattern, built on TanStack.
//
// TanStack Table owns the table's STATE and its row models: sorting, filtering,
// selection, visibility and pinning. TanStack Virtual decides which rows are on
// screen. Neither draws anything, so this file draws: the header, the visible
// rows, pinned columns and the footer. What a cell MEANS (a price
// with its unit, a tax verdict with its source) stays in grid.js, which hands
// this file a formatter per column and never touches the DOM it builds.
//
// The vendored modules are imported by path, because the extension and the
// engine both serve vendor/ beside this file and neither has a bundler.
import {
  columnFilteringFeature,
  columnPinningFeature,
  columnVisibilityFeature,
  constructTable,
  createFilteredRowModel,
  createSortedRowModel,
  rowSelectionFeature,
  rowSortingFeature,
  tableFeatures,
} from "./vendor/tanstack/table-core/index.js";
import { storeReactivityBindings } from "./vendor/tanstack/table-core/store-reactivity-bindings.js";
import {
  Virtualizer,
  elementScroll,
  measureElement,
  observeElementOffset,
  observeElementRect,
} from "./vendor/tanstack/virtual-core/index.js";

// SAID, NOT SILENT. TanStack's own checks for a missing feature are TypeScript
// types and development-only warnings, and this project has neither a type
// checker nor a development build. So the pieces are checked here, once, and a
// missing one stops the grid with its name instead of sorting nothing quietly.
const PIECES = {
  columnFilteringFeature, columnPinningFeature, columnVisibilityFeature,
  constructTable, createFilteredRowModel, createSortedRowModel,
  rowSelectionFeature, rowSortingFeature, tableFeatures,
  storeReactivityBindings, Virtualizer,
  elementScroll, measureElement, observeElementOffset, observeElementRect,
};
const missingPieces = Object.entries(PIECES)
  .filter(([, piece]) => piece === undefined || piece === null)
  .map(([name]) => name);
if (missingPieces.length) {
  throw new Error("The grid's library is incomplete: " + missingPieces.join(", ") + " did not load.");
}

const FEATURES = tableFeatures({
  coreReactivityFeature: storeReactivityBindings(),
  columnFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  rowSelectionFeature,
  columnVisibilityFeature,
  columnPinningFeature,
});

const DEFAULT_MIN_WIDTH = 40;
const SELECT_FORMATTER = "rowSelection";
const ROWNUM_FORMATTER = "rownum";
const text = (v) => (v === null || v === undefined) ? "" : String(v);

/** An icon the host hands over: a node (copied) or a function that makes one.
 *
 * Never markup: this file parses no HTML at all, so nothing a cell, a header or
 * an icon carries can become live markup on its way to the screen.
 */
function iconFrom(spec) {
  const node = typeof spec === "function" ? spec() : spec;
  if (!(node instanceof Node)) return document.createTextNode("");
  return typeof spec === "function" ? node : node.cloneNode(true);
}

function px(value) {
  return Math.round(value) + "px";
}

/** Read a CSS length the theme declares on an element, in pixels. */
function cssPixels(element, property, fallback) {
  const probe = document.createElement("div");
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  probe.style.height = "var(" + property + ")";
  element.appendChild(probe);
  const measured = probe.getBoundingClientRect().height;
  probe.remove();
  return measured > 0 ? measured : fallback;
}

// ---- the handles grid.js holds ---------------------------------------------
//
// The renderer keeps TanStack's objects to itself. What leaves it is a small,
// stable surface: a column, a row and a cell each answer only what grid.js and
// its tests ask of them.

class ColumnHandle {
  constructor(grid, id) {
    this._grid = grid;
    this._id = id;
  }

  getField() { return this._id; }
  getDefinition() { return this._grid._defs.get(this._id) || {}; }
  isVisible() { return this._grid._isVisible(this._id); }
  show() { this._grid._setVisible(this._id, true); }
  hide() { this._grid._setVisible(this._id, false); }
  getWidth() { return this._grid._widths.get(this._id) || 0; }
  /** Fix this column at `width` pixels (never below its minimum). */
  setWidth(width) { this._grid._setFixedWidth(this._id, width); }
  getElement() {
    return this._grid._header &&
      this._grid._header.querySelector(`.dg-col[data-field="${CSS.escape(this._id)}"]`);
  }
}

class RowHandle {
  constructor(grid, row) {
    this._grid = grid;
    this._row = row;
  }

  getData() { return this._row.original; }
  isSelected() { return this._row.getIsSelected(); }
}

class CellHandle {
  constructor(grid, row, field, element) {
    this._grid = grid;
    this._row = row;
    this._field = field;
    this._element = element;
  }

  getValue() { return this._row.original ? this._row.original[this._field] : undefined; }
  getField() { return this._field; }
  getRow() { return new RowHandle(this._grid, this._row); }
  getElement() { return this._element; }
}

// ---- the grid ----------------------------------------------------------------

/**
 * One grid drawn into `mount`.
 *
 * Column definition keys: title, field, formatter(cell) -> Node|string|
 * "rowSelection"|"rownum", titleFormatter(cell) -> Node|"rowSelection",
 * sorter {value(rowData), compare(a, b)} (a value of undefined is EMPTY and
 * sorts last in both directions), headerSort, width, minWidth, widthGrow,
 * hozAlign, frozen ("left"|"right"), cssClass, visible.
 *
 * Table options: data, columns, columnDefaults, height, placeholder,
 * headerSortElement (an icon: a Node or a function that returns one),
 * selectableRows, footerElement, initialSort [{column, dir}].
 */
export class DataGrid {
  constructor(mount, options) {
    if (!mount) throw new Error("DataGrid needs an element to draw into");
    this.element = mount;
    this.options = Object.assign({
      placeholder: "No rows.",
      selectableRows: false,
    }, options || {});
    this._listeners = new Map();
    this._destroyed = false;
    this._renderQueued = false;
    this._fixedWidths = new Map();
    this._widths = new Map();
    this._rowElements = new Map();
    this._lastSelection = null;
    this._lastFilters = null;

    this._prepareColumns();
    this._prepareTable();
    this._buildFrame();
    this._layout();
    this._renderHeader();
    this._startVirtualizer();
    this._renderBody();
    this._observeSize();
    grids.set(mount, this);

    // AFTER THE STACK UNWINDS, so a listener attached right after construction
    // still hears it -- and it is heard even by a grid destroyed in between,
    // because whoever waits for a build must never wait for ever.
    setTimeout(() => this._emit("tableBuilt"), 0);
  }

  // ---- public API -----------------------------------------------------------

  on(name, listener) {
    if (!this._listeners.has(name)) this._listeners.set(name, []);
    this._listeners.get(name).push(listener);
  }

  destroy() {
    if (this._destroyed) return;
    this._destroyed = true;
    if (this._unsubscribe) this._unsubscribe();
    if (this._unmountVirtualizer) this._unmountVirtualizer();
    if (this._resizeObserver) this._resizeObserver.disconnect();
    this._rowElements.clear();
    this.element.replaceChildren();
    this.element.classList.remove("dg");
    for (const attr of ["role", "aria-rowcount", "aria-colcount", "aria-multiselectable"]) {
      this.element.removeAttribute(attr);
    }
    if (grids.get(this.element) === this) grids.delete(this.element);
  }

  redraw() {
    if (this._destroyed) return;
    this._layout();
    this._renderHeader();
    this._invalidateRows();
    this._renderBody();
  }

  getColumn(field) {
    return this._defs.has(field) ? new ColumnHandle(this, field) : undefined;
  }

  getColumns() {
    return this._displayColumnIds().map((id) => new ColumnHandle(this, id));
  }

  /** Top-level rows: all of them, or ("active") those the filters keep. */
  getDataCount(mode) {
    if (mode === "active") return this._table.getFilteredRowModel().rows.length;
    return this.options.data.length;
  }

  /** The rows' data: all of it in payload order, or ("active") as displayed. */
  getData(mode) {
    if (mode !== "active") return this.options.data.slice();
    return this._table.getSortedRowModel().rows.map((row) => row.original);
  }

  getSorters() {
    const sorting = this._table.atoms.sorting.get() || [];
    return sorting.map((entry) => ({field: entry.id, dir: entry.desc ? "desc" : "asc"}));
  }

  /** Sort by one column, or clear the sort with no field. */
  setSort(field, dir) {
    if (!field || !this._defs.has(field) || !this._canSort(field)) {
      this._table.setSorting([]);
    } else {
      this._table.setSorting([{id: field, desc: dir === "desc"}]);
    }
    this._afterStateChange();
  }

  /** Narrow the rows: [{field, test(rowData) -> bool}] or [{field, type: "like", value}]. */
  setFilter(filters) {
    const next = (filters || []).filter((f) => f && this._defs.has(f.field)).map((f) => {
      if (typeof f.test === "function") return {id: f.field, value: {test: f.test}};
      const needle = text(f.value).toLowerCase();
      return {id: f.field, value: {test: (data) => text(data[f.field]).toLowerCase().includes(needle)}};
    });
    this._table.setColumnFilters(next);
    this._afterStateChange();
  }

  getSelectedRows() {
    return this._table.getSelectedRowModel().flatRows.map((row) => new RowHandle(this, row));
  }

  // ---- columns --------------------------------------------------------------

  _prepareColumns() {
    const defaults = this.options.columnDefaults || {};
    this._defs = new Map();
    this._order = [];
    for (const raw of this.options.columns || []) {
      const def = Object.assign({}, defaults, raw);
      // A column with no field is a built-in: the selection box or the row number.
      if (!def.field) def.field = def.formatter === SELECT_FORMATTER ? "__select" : "__rownum";
      this._defs.set(def.field, def);
      this._order.push(def.field);
      if (def.width !== undefined && def.width !== null) {
        this._fixedWidths.set(def.field, Number(def.width));
      }
    }
  }

  _isBuiltIn(def) {
    return def.formatter === SELECT_FORMATTER || def.formatter === ROWNUM_FORMATTER;
  }

  _canSort(id) {
    const def = this._defs.get(id);
    return !!def && def.headerSort !== false && !this._isBuiltIn(def);
  }

  _minWidth(id) {
    const def = this._defs.get(id) || {};
    return Number(def.minWidth || DEFAULT_MIN_WIDTH);
  }

  _isVisible(id) {
    const visibility = this._table.atoms.columnVisibility.get() || {};
    return visibility[id] !== false;
  }

  _setVisible(id, on) {
    if (!this._defs.has(id) || this._isVisible(id) === on) return;
    this._table.setColumnVisibility((old) => Object.assign({}, old, {[id]: on}));
    this.redraw();
  }

  /** Every column, in the order drawn: pinned at the start, then the middle, then the end. */
  _displayColumnIds() {
    const ids = this._order;
    const pinning = this._table.atoms.columnPinning.get() || {};
    const start = (pinning.start || []).filter((id) => this._defs.has(id));
    const end = (pinning.end || []).filter((id) => this._defs.has(id));
    const middle = ids.filter((id) => !start.includes(id) && !end.includes(id));
    return [...start, ...middle, ...end];
  }

  _visibleColumnIds() {
    return this._displayColumnIds().filter((id) => this._isVisible(id));
  }

  _pinSide(id) {
    const pinning = this._table.atoms.columnPinning.get() || {};
    if ((pinning.start || []).includes(id)) return "start";
    if ((pinning.end || []).includes(id)) return "end";
    return "";
  }

  _setFixedWidth(id, width) {
    if (!this._defs.has(id)) return;
    this._fixedWidths.set(id, Math.max(this._minWidth(id), Math.round(Number(width) || 0)));
    this.redraw();
  }

  // ---- the TanStack table -----------------------------------------------------

  _prepareTable() {
    const columns = this._order.map((id) => {
      const def = this._defs.get(id);
      const sorter = def.sorter || {};
      const value = typeof sorter.value === "function"
        ? sorter.value
        : (data) => {
          const raw = data[id];
          return raw === "" || raw === null || raw === undefined ? undefined : raw;
        };
      const compare = typeof sorter.compare === "function"
        ? sorter.compare
        : (a, b) => (a < b ? -1 : a > b ? 1 : 0);
      return {
        id,
        accessorFn: (data) => value(data),
        sortFn: (rowA, rowB, columnId) => compare(rowA.getValue(columnId), rowB.getValue(columnId)),
        // EMPTY IS LAST, both directions, on every column.
        sortUndefined: "last",
        sortDescFirst: false,
        enableSorting: this._canSort(id),
        filterFn: (row, columnId, filter) => !filter || filter.test(row.original),
      };
    });

    const initialSort = (this.options.initialSort || [])
      .filter((entry) => entry && this._defs.has(entry.column) && this._canSort(entry.column))
      .slice(0, 1)
      .map((entry) => ({id: entry.column, desc: entry.dir === "desc"}));
    const visibility = {};
    this._order.forEach((id) => { if (this._defs.get(id).visible === false) visibility[id] = false; });
    const pinning = {start: [], end: []};
    this._order.forEach((id) => {
      const side = this._defs.get(id).frozen;
      if (side === "right") pinning.end.push(id);
      else if (side) pinning.start.push(id);
    });

    this._table = constructTable({
      features: FEATURES,
      data: this.options.data,
      columns,
      getRowId: (data, index) => String(index),
      enableMultiSort: false,
      enableSortingRemoval: true,
      enableRowSelection: () => !!this.options.selectableRows,
      enableMultiRowSelection: true,
      initialState: {
        sorting: initialSort,
        columnVisibility: visibility,
        columnPinning: pinning,
      },
    });
    // The baselines change events are measured from: the state as built.
    this._lastSelection = this._table.atoms.rowSelection.get();
    this._lastFilters = this._table.atoms.columnFilters.get();
    this._unsubscribe = this._table.store.subscribe(() => this._queueRender()).unsubscribe;
  }

  _afterStateChange() {
    if (this._destroyed) return;
    this._invalidateRows();
    this._renderHeader();
    this._renderBody();
    this._emitChanges();
  }

  _queueRender() {
    if (this._renderQueued || this._destroyed) return;
    this._renderQueued = true;
    queueMicrotask(() => {
      this._renderQueued = false;
      if (this._destroyed) return;
      this._invalidateRows();
      this._renderHeader();
      this._renderBody();
      this._emitChanges();
    });
  }

  /** Tell listeners what changed since they last heard, once per change. */
  _emitChanges() {
    const filters = this._table.atoms.columnFilters.get();
    if (filters !== this._lastFilters) {
      this._lastFilters = filters;
      this._emit("dataFiltered");
    }
    const selection = this._table.atoms.rowSelection.get();
    if (selection !== this._lastSelection) {
      this._lastSelection = selection;
      const rows = this.getSelectedRows();
      this._emit("rowSelectionChanged", rows.map((row) => row.getData()), rows);
    }
  }

  _emit(name, ...args) {
    for (const listener of this._listeners.get(name) || []) {
      try {
        listener(...args);
      } catch (error) {
        // One listener failing must not stop the others, and must not vanish.
        setTimeout(() => { throw error; }, 0);
      }
    }
  }

  // ---- the frame ------------------------------------------------------------

  _buildFrame() {
    const mount = this.element;
    mount.replaceChildren();
    mount.classList.add("dg");
    if (this.options.height) mount.style.height = this.options.height;
    this._scroller = document.createElement("div");
    this._scroller.className = "dg-scroller";
    this._scroller.tabIndex = 0;
    this._header = document.createElement("div");
    this._header.className = "dg-header";
    this._header.setAttribute("role", "rowgroup");
    this._body = document.createElement("div");
    this._body.className = "dg-body";
    this._body.setAttribute("role", "rowgroup");
    this._placeholder = document.createElement("div");
    this._placeholder.className = "dg-placeholder";
    this._placeholder.textContent = this.options.placeholder;
    this._placeholder.hidden = true;
    this._scroller.append(this._header, this._body, this._placeholder);
    mount.append(this._scroller);
    if (this.options.footerElement) {
      this.options.footerElement.classList.add("dg-footer");
      mount.append(this.options.footerElement);
    }
    this._body.addEventListener("click", (event) => this._onBodyClick(event));
  }

  _observeSize() {
    if (typeof ResizeObserver !== "function") return;
    let lastWidth = Math.round(this._scroller.clientWidth);
    let queued = false;
    this._resizeObserver = new ResizeObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        if (this._destroyed) return;
        const width = Math.round(this._scroller.clientWidth);
        if (width < 1 || width === lastWidth) return;
        lastWidth = width;
        this.redraw();
      });
    });
    this._resizeObserver.observe(this._scroller);
  }

  // ---- layout: fit the columns to the width there is ------------------------
  //
  // A column with a width of its own keeps it. The others share what is left in
  // proportion to their widthGrow, and none goes below its minimum: when the
  // minimums do not fit, the table is wider than its frame and scrolls sideways,
  // honestly, rather than shrinking columns into slivers.
  _layout() {
    const ids = this._visibleColumnIds();
    const available = Math.max(0, this._scroller.clientWidth);
    const widths = new Map();
    let fixedTotal = 0;
    const flexible = [];
    for (const id of ids) {
      if (this._fixedWidths.has(id)) {
        const width = Math.max(this._minWidth(id), this._fixedWidths.get(id));
        widths.set(id, width);
        fixedTotal += width;
      } else {
        flexible.push(id);
      }
    }
    let remaining = Math.max(0, available - fixedTotal);
    let pending = flexible.slice();
    // Settle the columns whose share would fall under their minimum, then share again.
    for (;;) {
      const grow = pending.reduce((sum, id) => sum + this._grow(id), 0);
      if (!grow) break;
      const unit = remaining / grow;
      const under = pending.filter((id) => this._grow(id) * unit < this._minWidth(id));
      if (!under.length) {
        let used = 0;
        pending.forEach((id, index) => {
          const width = index === pending.length - 1
            ? Math.max(this._minWidth(id), remaining - used)
            : Math.floor(this._grow(id) * unit);
          widths.set(id, width);
          used += width;
        });
        break;
      }
      under.forEach((id) => {
        widths.set(id, this._minWidth(id));
        remaining = Math.max(0, remaining - this._minWidth(id));
      });
      pending = pending.filter((id) => !under.includes(id));
      if (!pending.length) break;
    }
    this._widths = widths;
    this._totalWidth = ids.reduce((sum, id) => sum + (widths.get(id) || 0), 0);
    // Sticky offsets for pinned columns, measured from their own edge.
    this._offsets = new Map();
    let start = 0;
    for (const id of ids) {
      if (this._pinSide(id) !== "start") continue;
      this._offsets.set(id, start);
      start += widths.get(id) || 0;
    }
    let end = 0;
    for (const id of ids.slice().reverse()) {
      if (this._pinSide(id) !== "end") continue;
      this._offsets.set(id, end);
      end += widths.get(id) || 0;
    }
  }

  _grow(id) {
    const def = this._defs.get(id) || {};
    return def.widthGrow === undefined ? 1 : Number(def.widthGrow) || 0;
  }

  _placeCell(cell, id) {
    // One width per cell; the stylesheet keeps cells from growing or shrinking.
    cell.style.width = px(this._widths.get(id) || this._minWidth(id));
    const side = this._pinSide(id);
    if (!side) return;
    cell.classList.add("dg-pinned", side === "start" ? "dg-pinned-start" : "dg-pinned-end");
    if (side === "start") cell.style.insetInlineStart = px(this._offsets.get(id));
    else cell.style.insetInlineEnd = px(this._offsets.get(id));
  }

  // ---- the header -------------------------------------------------------------

  _renderHeader() {
    if (this._destroyed) return;
    const ids = this._visibleColumnIds();
    const header = this._header;
    header.replaceChildren();
    header.style.width = px(this._totalWidth);
    const row = document.createElement("div");
    row.className = "dg-row dg-header-row";
    row.setAttribute("role", "row");
    row.setAttribute("aria-rowindex", "1");
    const sorting = this._table.atoms.sorting.get() || [];
    for (const id of ids) row.append(this._headerCell(id, sorting));
    header.append(row);
    this.element.setAttribute("role", "grid");
    this.element.setAttribute("aria-colcount", String(ids.length));
    if (this.options.selectableRows) this.element.setAttribute("aria-multiselectable", "true");
    this._headerRows = header.children.length;
    if (this._virtualizer) this._syncVirtualizer();
  }

  _headerCell(id, sorting) {
    const def = this._defs.get(id);
    const cell = document.createElement("div");
    cell.className = "dg-col" + (def.cssClass ? " " + def.cssClass : "");
    cell.dataset.field = id;
    cell.setAttribute("role", "columnheader");
    this._placeCell(cell, id);
    const sortable = this._canSort(id);
    if (sortable) cell.classList.add("dg-sortable");
    const entry = sorting.find((s) => s.id === id);
    cell.setAttribute("aria-sort", entry ? (entry.desc ? "descending" : "ascending") : "none");

    const content = document.createElement("div");
    content.className = "dg-col-content";
    if (def.titleFormatter === SELECT_FORMATTER) {
      content.append(this._selectAllBox());
    } else {
      const title = typeof def.titleFormatter === "function"
        ? def.titleFormatter({getValue: () => text(def.title), getColumn: () => new ColumnHandle(this, id)})
        : document.createTextNode(text(def.title));
      content.append(title instanceof Node ? title : document.createTextNode(text(title)));
      if (sortable) {
        const sort = document.createElement("span");
        sort.className = "dg-sort";
        sort.setAttribute("aria-hidden", "true");
        sort.append(iconFrom(this.options.headerSortElement));
        content.append(sort);
      }
    }
    cell.append(content);

    if (sortable) {
      cell.addEventListener("click", (event) => {
        // A control a title carries is its own, not a sort.
        if (event.target.closest("button, input")) return;
        this._cycleSort(id);
      });
    }
    return cell;
  }

  _cycleSort(id) {
    const sorting = this._table.atoms.sorting.get() || [];
    const current = sorting.find((s) => s.id === id);
    if (!current) this.setSort(id, "asc");
    else if (!current.desc) this.setSort(id, "desc");
    else this.setSort();
  }

  _selectAllBox() {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "dg-select";
    box.setAttribute("aria-label", "Select every row");
    const all = this._table.getIsAllRowsSelected();
    box.checked = all;
    box.indeterminate = !all && this._table.getIsSomeRowsSelected();
    box.addEventListener("click", (event) => event.stopPropagation());
    box.addEventListener("change", () => {
      this._table.toggleAllRowsSelected(box.checked);
      this._afterStateChange();
    });
    return box;
  }

  // ---- the rows ------------------------------------------------------------------

  _rows() {
    return this._table.getRowModel().rows;
  }

  _rowHeight() {
    if (this._measuredRowHeight) return this._measuredRowHeight;
    if (!this._estimatedRowHeight) {
      this._estimatedRowHeight = cssPixels(this.element, "--grid-row-height", 40);
    }
    return this._estimatedRowHeight;
  }

  _startVirtualizer() {
    // Wrapped rows are as tall as their text, so only they are measured one by one.
    this._wraps = this.element.classList.contains("wrap");
    this._virtualizer = new Virtualizer(this._virtualizerOptions());
    this._unmountVirtualizer = this._virtualizer._didMount();
    this._virtualizer._willUpdate();
  }

  _virtualizerOptions() {
    const rows = this._rows();
    return {
      count: rows.length,
      getScrollElement: () => this._scroller,
      estimateSize: () => this._rowHeight(),
      getItemKey: (index) => (rows[index] ? rows[index].id : index),
      overscan: 8,
      scrollMargin: this._header.offsetHeight,
      observeElementRect,
      observeElementOffset,
      scrollToFn: elementScroll,
      measureElement,
      indexAttribute: "data-index",
      onChange: () => this._renderBody(),
    };
  }

  _syncVirtualizer() {
    this._virtualizer.setOptions(this._virtualizerOptions());
    this._virtualizer._willUpdate();
  }

  _invalidateRows() {
    this._rowElements.forEach((element) => element.remove());
    this._rowElements.clear();
    this._rowCache = null;
  }

  _renderBody() {
    if (this._destroyed || !this._virtualizer) return;
    // Measuring a row can tell the virtualizer a size changed, which asks for
    // this again while it is still running. Finish, then run once more.
    if (this._inBody) { this._bodyAgain = true; return; }
    this._inBody = true;
    try {
      do {
        this._bodyAgain = false;
        this._paintBody();
      } while (this._bodyAgain && !this._destroyed);
    } finally {
      this._inBody = false;
    }
  }

  _paintBody() {
    const rows = this._rows();
    if (!this._rowCache || this._rowCache.rows !== rows) {
      this._invalidateRows();
      this._syncVirtualizer();
      this._rowCache = {rows};
    }
    const items = this._virtualizer.getVirtualItems();
    const margin = this._virtualizer.options.scrollMargin || 0;
    this._body.style.height = px(this._virtualizer.getTotalSize() - margin);
    this._body.style.width = px(this._totalWidth);
    this._placeholder.hidden = rows.length > 0;
    this.element.setAttribute("aria-rowcount", String(rows.length + (this._headerRows || 1)));
    const wanted = new Set();
    for (const item of items) {
      const row = rows[item.index];
      if (!row) continue;
      wanted.add(row.id);
      let element = this._rowElements.get(row.id);
      const fresh = !element;
      if (fresh) {
        element = this._drawRow(row, item.index);
        this._rowElements.set(row.id, element);
        this._body.append(element);
      }
      element.dataset.index = String(item.index);
      element.setAttribute("aria-rowindex", String(item.index + (this._headerRows || 1) + 1));
      element.style.transform = "translateY(" + px(item.start - margin) + ")";
      // EVERY ROW IS ONE HEIGHT unless long text wraps, so one row is measured and
      // the rest are placed by it. Measuring each new row as it scrolled in forced
      // a layout per row and cost a frame in twenty (#1342's measurement).
      if (fresh && this._wraps) this._virtualizer.measureElement(element);
      else if (fresh && !this._measuredRowHeight) {
        const height = element.getBoundingClientRect().height;
        if (height > 0) {
          this._measuredRowHeight = height;
          this._bodyAgain = true;
          this._virtualizer.measure();
        }
      }
    }
    for (const [id, element] of this._rowElements) {
      if (!wanted.has(id)) { element.remove(); this._rowElements.delete(id); }
    }
  }

  _drawRow(row, index) {
    const element = document.createElement("div");
    element.setAttribute("role", "row");
    element.style.width = px(this._totalWidth);
    element.dataset.rowId = row.id;
    // The ordinal a row number shows, in display order.
    const ordinal = index + 1;
    element.className = "dg-row" + (ordinal % 2 === 0 ? " dg-row-even" : " dg-row-odd");
    if (this.options.selectableRows) element.classList.add("dg-selectable");
    const selected = row.getIsSelected();
    element.classList.toggle("dg-selected", selected);
    if (this.options.selectableRows) element.setAttribute("aria-selected", String(selected));
    for (const id of this._visibleColumnIds()) element.append(this._drawCell(row, id, ordinal));
    return element;
  }

  _drawCell(row, id, ordinal) {
    const def = this._defs.get(id);
    const cell = document.createElement("div");
    cell.className = "dg-cell" + (def.cssClass ? " " + def.cssClass : "");
    cell.dataset.field = id;
    cell.setAttribute("role", "gridcell");
    if (def.hozAlign) cell.classList.add("dg-align-" + def.hozAlign);
    this._placeCell(cell, id);
    if (def.formatter === SELECT_FORMATTER) {
      const box = document.createElement("input");
      box.type = "checkbox";
      box.className = "dg-select";
      box.checked = row.getIsSelected();
      box.setAttribute("aria-label", "Select row");
      box.addEventListener("click", (event) => {
        event.stopPropagation();
        row.toggleSelected(box.checked, {selectChildren: false});
        this._afterStateChange();
      });
      cell.append(box);
      return cell;
    }
    if (def.formatter === ROWNUM_FORMATTER) {
      cell.textContent = String(ordinal);
      return cell;
    }
    let content;
    if (typeof def.formatter === "function") {
      content = def.formatter(new CellHandle(this, row, id, cell));
    } else {
      content = text(row.original[id]);
    }
    // A string is TEXT. Scraped values reach these cells, so nothing a formatter
    // returns as a string is ever parsed as markup.
    if (content instanceof Node) cell.append(content);
    else if (content !== undefined && content !== null && content !== "") {
      cell.append(document.createTextNode(String(content)));
    }
    return cell;
  }

  _onBodyClick(event) {
    const rowElement = event.target.closest(".dg-row");
    if (!rowElement || !this._body.contains(rowElement)) return;
    let row = null;
    try { row = this._table.getRow(rowElement.dataset.rowId, true); } catch (err) { return; }
    if (!row) return;
    if (!this.options.selectableRows) return;
    // A link, a button or a box in a cell is its own control, not a row click.
    if (event.target.closest("a, button, input, label, select, textarea")) return;
    row.toggleSelected(undefined, {selectChildren: false});
    this._afterStateChange();
  }
}

const grids = new WeakMap();

/** The grid drawn into an element (or a selector), for whoever holds only the page. */
DataGrid.find = function find(target) {
  const element = typeof target === "string" ? document.querySelector(target) : target;
  return element ? grids.get(element) : undefined;
};
