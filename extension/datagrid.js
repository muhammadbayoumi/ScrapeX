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
// grouping, the tree, selection, column order, visibility and pinning. TanStack
// Virtual decides which rows are on screen. Neither draws anything, so this file
// draws: the header and its menus, the visible rows, resize handles, pinned
// columns, group bands, tree toggles and the footer. What a cell MEANS (a price
// with its unit, a tax verdict with its source) stays in grid.js, which hands
// this file a formatter per column and never touches the DOM it builds.
//
// The vendored modules are imported by path, because the extension and the
// engine both serve vendor/ beside this file and neither has a bundler.
import {
  columnFilteringFeature,
  columnGroupingFeature,
  columnOrderingFeature,
  columnPinningFeature,
  columnVisibilityFeature,
  constructTable,
  createExpandedRowModel,
  createFilteredRowModel,
  createGroupedRowModel,
  createSortedRowModel,
  rowExpandingFeature,
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
  columnFilteringFeature, columnGroupingFeature, columnOrderingFeature,
  columnPinningFeature, columnVisibilityFeature, constructTable,
  createExpandedRowModel, createFilteredRowModel, createGroupedRowModel,
  createSortedRowModel, rowExpandingFeature, rowSelectionFeature,
  rowSortingFeature, tableFeatures, storeReactivityBindings, Virtualizer,
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
  columnGroupingFeature,
  groupedRowModel: createGroupedRowModel(),
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  rowExpandingFeature,
  expandedRowModel: createExpandedRowModel(),
  rowSelectionFeature,
  columnVisibilityFeature,
  columnOrderingFeature,
  columnPinningFeature,
});

const DEFAULT_MIN_WIDTH = 40;
const DRAG_THRESHOLD = 5;
const SELECT_FORMATTER = "rowSelection";
const ROWNUM_FORMATTER = "rownum";
const text = (v) => (v === null || v === undefined) ? "" : String(v);

/** Whether a row's field holds `needle`, ignoring case and the needle's own
 * outer spaces. The one "like" rule: setFilter and the header's box both use it. */
const likeTest = (field, needle) => {
  const folded = text(needle).trim().toLowerCase();
  return (data) => text(data[field]).toLowerCase().includes(folded);
};

/* A BAND'S KEY IS ITS VALUE, ENCODED SO NO VALUE CAN SPELL ANOTHER BAND'S ID.
 * TanStack keys a band by the string of its value and nests it as
 * `parent>column:value` (createGroupedRowModel.js:69-70), so a scraped value
 * holding `>column:` could take another band's id, and null read as "null".
 * Encoded, every string value starts `j"` and ends at its first unescaped
 * quote, which no nested id can match. A field that is absent and one that is
 * null are one band: JSON, which the rows come from, has no undefined. */
const groupKey = (value) => "j" + JSON.stringify(value === undefined ? null : value);
const groupValue = (key) => JSON.parse(key.slice(1));

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

/** A value for a CSV cell, exactly as the previous renderer wrote one. */
function csvField(value) {
  let v = value;
  if (v === undefined) v = "";
  else if (typeof v === "object") v = v === null ? "" : JSON.stringify(v);
  return '"' + String(v).split('"').join('""') + '"';
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
  /** The width its header and its rows on screen need, in pixels. */
  measureContentWidth() { return this._grid._measureColumn(this._id); }
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

class GroupHandle {
  constructor(grid, row) {
    this._grid = grid;
    this._row = row;
  }

  getKey() { return groupValue(this._row.groupingValue); }
  getCount() { return this._row.leafRows.length; }
  /** The data rows the band holds, at every level beneath it. */
  getRows() { return this._row.leafRows.map((row) => new RowHandle(this._grid, row)); }
  isOpen() { return this._row.getIsExpanded(); }
}

// ---- the grid ----------------------------------------------------------------

/**
 * One grid drawn into `mount`.
 *
 * Column definition keys: title, field, formatter(cell) -> Node|string|
 * "rowSelection"|"rownum", titleFormatter(cell) -> Node|"rowSelection",
 * sorter {value(rowData), compare(a, b)} (a value of undefined is EMPTY and
 * sorts last in both directions), headerSort, headerMenu(event, column) ->
 * items, headerMenuIcon, headerPopup(event, column) -> Node, headerPopupIcon
 * (an icon is a Node or a function that returns one),
 * headerFilter ("input"), resizable, width, minWidth, widthGrow, hozAlign,
 * frozen ("left"|"right"), cssClass, visible, download, topCalc
 * ("avg"|"count"), topCalcParams {precision}.
 *
 * Table options: data, columns, columnDefaults, height, placeholder,
 * headerSortElement (an icon, as above), movableColumns,
 * selectableRows, footerElement, initialSort [{column, dir}], groupBy (an
 * array of field names or functions of the row), groupHeader (an array of
 * functions (value, count) -> Node), dataTree, dataTreeChildField,
 * dataTreeElementColumn, dataTreeChildIndent.
 */
export class DataGrid {
  constructor(mount, options) {
    if (!mount) throw new Error("DataGrid needs an element to draw into");
    this.element = mount;
    this.options = Object.assign({
      placeholder: "No rows.",
      movableColumns: false,
      selectableRows: false,
      dataTreeChildField: "_children",
      dataTreeChildIndent: 14,
    }, options || {});
    this._listeners = new Map();
    this._destroyed = false;
    this._popup = null;
    this._renderQueued = false;
    this._fixedWidths = new Map();
    this._widths = new Map();
    this._rowElements = new Map();
    this._suppressNextHeaderClick = false;
    this._resizing = null;
    this._lastSelection = null;
    this._lastFilters = null;
    this._renderedState = null;

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
    this.closePopups();
    if (this._unsubscribe) this._unsubscribe();
    if (this._unmountVirtualizer) this._unmountVirtualizer();
    if (this._resizeObserver) this._resizeObserver.disconnect();
    this._rowElements.clear();
    this.element.replaceChildren();
    this.element.classList.remove("dg", "dg-grouped", "dg-tree");
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
    this._renderedState = this._table.store.state;
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
    const sorted = this._table.getSortedRowModel().rows;
    if (!this._grouping().length) return sorted.map((row) => row.original);
    const out = [];
    const visit = (rows) => rows.forEach((row) => {
      if (row.getIsGrouped()) visit(row.subRows);
      else out.push(row.original);
    });
    visit(sorted);
    return out;
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

  /**
   * Narrow the rows: [{field, test(rowData) -> bool}] or
   * [{field, type: "like", value}]. A row with children stays while any child
   * passes, and its children are narrowed to those that pass.
   */
  setFilter(filters) {
    const next = (filters || []).filter((f) => f && this._defs.has(f.field)).map((f) => {
      if (typeof f.test === "function") return {id: f.field, value: {test: f.test}};
      return {id: f.field, value: {test: likeTest(f.field, f.value)}};
    });
    this._table.setColumnFilters(next);
    this._afterStateChange();
  }

  getSelectedRows() {
    return this._table.getSelectedRowModel().flatRows
      .filter((row) => !row.getIsGrouped())
      .map((row) => new RowHandle(this, row));
  }

  getGroups() {
    return this._table.getGroupedRowModel().rows
      .filter((row) => row.getIsGrouped())
      .map((row) => new GroupHandle(this, row));
  }

  /** Open or close every group band, at every level. */
  setAllGroupsOpen(open) {
    if (!this._grouping().length) return;
    if (!open) { this._table.setExpanded({}); this._afterStateChange(); return; }
    const expanded = {};
    const visit = (rows) => rows.forEach((row) => {
      if (row.getIsGrouped()) { expanded[row.id] = true; visit(row.subRows); }
    });
    visit(this._table.getGroupedRowModel().rows);
    this._table.setExpanded(expanded);
    this._afterStateChange();
  }

  /** The rows on screen as a file: "csv" or "json", named `filename`. */
  download(kind, filename) {
    const columns = this._displayColumnIds()
      .filter((id) => this._isVisible(id))
      .map((id) => this._defs.get(id))
      .filter((def) => def.download !== false && !this._isBuiltIn(def));
    const rows = this._exportRows();
    let body;
    let type;
    if (kind === "json") {
      body = JSON.stringify(rows.map((data) => {
        const out = {};
        columns.forEach((def) => { out[def.title || def.field] = data[def.field]; });
        return out;
      }), null, "\t");
      type = "application/json";
    } else {
      const lines = rows.map((data) => columns.map((def) => csvField(data[def.field])).join(","));
      lines.unshift(columns.map((def) => csvField(text(def.title))).join(","));
      body = lines.join("\n");
      type = "text/csv";
    }
    const url = URL.createObjectURL(new Blob([body], {type}));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
    return body;
  }

  closePopups() {
    if (!this._popup) return;
    const popup = this._popup;
    this._popup = null;
    popup.close();
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
    const order = this._table.atoms.columnOrder.get();
    const ids = order && order.length ? order : this._order;
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
    const childField = this.options.dataTreeChildField;
    const tree = !!this.options.dataTree;
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
        enableGrouping: true,
        // A band holds the rows whose FIELD is this value, as stored: grouping by
        // the sort value would fold every empty and every padded variant into
        // one band nobody asked for. A caller that wants a reading other than the
        // field passes a function in groupBy instead.
        getGroupingValue: (data) => groupKey(data[id]),
      };
    });

    const groupBy = Array.isArray(this.options.groupBy) ? this.options.groupBy : [];
    // A grouping that is a FUNCTION of the row gets a column of its own, which is
    // never drawn: it exists so TanStack can group by what the function reads.
    const grouping = [];
    groupBy.forEach((spec, index) => {
      if (typeof spec === "function") {
        const id = "__group" + index;
        columns.push({id, accessorFn: (data) => groupKey(text(spec(data))), enableSorting: false,
                      filterFn: () => true});
        grouping.push(id);
      } else if (this._defs.has(spec)) {
        grouping.push(spec);
      }
    });
    this._groupIds = grouping;

    const initialSort = (this.options.initialSort || [])
      .filter((entry) => entry && this._defs.has(entry.column) && this._canSort(entry.column))
      .slice(0, 1)
      .map((entry) => ({id: entry.column, desc: entry.dir === "desc"}));
    const visibility = {};
    this._order.forEach((id) => { if (this._defs.get(id).visible === false) visibility[id] = false; });
    grouping.filter((id) => id.startsWith("__group")).forEach((id) => { visibility[id] = false; });
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
      getRowId: (data, index, parent) => (parent ? parent.id + "." : "") + index,
      getSubRows: tree ? (data) => (Array.isArray(data[childField]) ? data[childField] : undefined)
                       : undefined,
      filterFromLeafRows: true,
      paginateExpandedRows: true,
      enableMultiSort: false,
      enableSortingRemoval: true,
      enableRowSelection: (row) => !row.getIsGrouped() && !!this.options.selectableRows,
      enableMultiRowSelection: true,
      enableSubRowSelection: false,
      groupedColumnMode: false,
      autoResetExpanded: false,
      initialState: {
        sorting: initialSort,
        grouping,
        columnVisibility: visibility,
        columnPinning: pinning,
        columnOrder: [],
        expanded: {},
      },
    });
    // The baselines change events are measured from: the state as built.
    this._lastSelection = this._table.atoms.rowSelection.get();
    this._lastFilters = this._table.atoms.columnFilters.get();
    this._unsubscribe = this._table.store.subscribe(() => this._queueRender()).unsubscribe;
  }

  _grouping() {
    return this._table.atoms.grouping.get() || [];
  }

  _afterStateChange() {
    if (this._destroyed) return;
    this._invalidateRows();
    this._renderHeader();
    this._renderBody();
    this._renderedState = this._table.store.state;
    this._emitChanges();
  }

  _queueRender() {
    if (this._renderQueued || this._destroyed) return;
    this._renderQueued = true;
    queueMicrotask(() => {
      this._renderQueued = false;
      if (this._destroyed) return;
      // DRAWN ONCE. _afterStateChange and redraw draw a change at once, so the
      // store's word that follows is about a state already on screen, and
      // drawing it again would throw away every row just drawn. The store's
      // state is a snapshot that is a new object only when something changed.
      if (this._table.store.state !== this._renderedState) {
        this._invalidateRows();
        this._renderHeader();
        this._renderBody();
        this._renderedState = this._table.store.state;
      }
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
    this._scroller.addEventListener("scroll", () => this.closePopups(), {passive: true});
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

  /** The widths `_layout` settled, given to every cell already drawn. */
  _placeWidths() {
    const total = px(this._totalWidth);
    this._header.style.width = total;
    this._body.style.width = total;
    this._header.querySelectorAll(".dg-col").forEach((cell) => this._placeCell(cell, cell.dataset.field));
    const ids = this._visibleColumnIds();
    this._header.querySelectorAll(".dg-calcs").forEach((row) => {
      Array.from(row.children).forEach((cell, index) => this._placeCell(cell, ids[index]));
    });
    this._rowElements.forEach((element) => {
      element.style.width = total;
      element.querySelectorAll(".dg-cell[data-field]").forEach((cell) => this._placeCell(cell, cell.dataset.field));
    });
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
    // Typing in a header filter redraws the header; the reader keeps typing.
    const focused = header.contains(document.activeElement) ? document.activeElement : null;
    const keep = focused && focused.closest(".dg-col") ? {
      field: focused.closest(".dg-col").dataset.field,
      className: focused.className,
      start: focused.selectionStart,
      end: focused.selectionEnd,
    } : null;
    header.replaceChildren();
    header.style.width = px(this._totalWidth);
    const row = document.createElement("div");
    row.className = "dg-row dg-header-row";
    row.setAttribute("role", "row");
    row.setAttribute("aria-rowindex", "1");
    const sorting = this._table.atoms.sorting.get() || [];
    for (const id of ids) row.append(this._headerCell(id, sorting));
    header.append(row);
    if (ids.some((id) => this._defs.get(id).topCalc)) header.append(this._calcRow(ids));
    const grouped = this._grouping().length > 0;
    const tree = !!this.options.dataTree;
    this.element.setAttribute("role", grouped || tree ? "treegrid" : "grid");
    this.element.classList.toggle("dg-grouped", grouped);
    this.element.classList.toggle("dg-tree", tree);
    this.element.setAttribute("aria-colcount", String(ids.length));
    if (this.options.selectableRows) this.element.setAttribute("aria-multiselectable", "true");
    this._headerRows = header.children.length;
    if (keep) {
      const cell = header.querySelector(`.dg-col[data-field="${CSS.escape(keep.field)}"]`);
      const again = cell && Array.from(cell.querySelectorAll("button, input"))
        .find((node) => node.className === keep.className);
      if (again) {
        again.focus({preventScroll: true});
        if (typeof keep.start === "number" && again.setSelectionRange) {
          try { again.setSelectionRange(keep.start, keep.end); } catch (err) { /* not a text box */ }
        }
      }
    }
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
      const label = text(def.title) || "column";
      if (typeof def.headerPopup === "function") {
        content.append(this._headerButton("filter", label, def.headerPopupIcon, (button, event) =>
          this._openPopup(button, def.headerPopup(event, new ColumnHandle(this, id)))));
      }
      if (typeof def.headerMenu === "function") {
        content.append(this._headerButton("menu", label, def.headerMenuIcon, (button, event) =>
          this._openMenu(button, def.headerMenu(event, new ColumnHandle(this, id)))));
      }
    }
    cell.append(content);
    if (def.headerFilter === "input") cell.append(this._headerFilterInput(id, def));
    if (def.resizable !== false && !this._isBuiltIn(def)) cell.append(this._resizeHandle(id, cell));

    if (sortable) {
      cell.addEventListener("click", (event) => {
        if (this._suppressNextHeaderClick) { this._suppressNextHeaderClick = false; return; }
        if (event.target.closest("button, input, .dg-resize-handle")) return;
        this._cycleSort(id);
      });
    }
    if (this.options.movableColumns && !this._isBuiltIn(def)) this._armColumnMove(cell, id);
    return cell;
  }

  _cycleSort(id) {
    const sorting = this._table.atoms.sorting.get() || [];
    const current = sorting.find((s) => s.id === id);
    if (!current) this.setSort(id, "asc");
    else if (!current.desc) this.setSort(id, "desc");
    else this.setSort();
  }

  _headerButton(kind, label, icon, open) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dg-header-button dg-header-" + kind;
    button.setAttribute("aria-label", "Open " + kind + " for " + label);
    button.setAttribute("aria-haspopup", kind === "menu" ? "menu" : "dialog");
    button.setAttribute("aria-expanded", "false");
    button.append(iconFrom(icon));
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const already = this._popup && this._popup.anchor === button;
      this.closePopups();
      if (!already) open(button, event);
    });
    return button;
  }

  _headerFilterInput(id, def) {
    const input = document.createElement("input");
    input.type = "search";
    input.className = "dg-header-input";
    input.setAttribute("aria-label", "Filter " + (text(def.title) || id));
    const current = (this._table.atoms.columnFilters.get() || []).find((f) => f.id === id);
    if (current && current.value && current.value.text) input.value = current.value.text;
    input.addEventListener("click", (event) => event.stopPropagation());
    input.addEventListener("input", () => {
      this._table.setColumnFilters((old) => {
        const rest = (old || []).filter((f) => f.id !== id);
        if (!input.value.trim()) return rest;
        return rest.concat({id, value: {text: input.value, test: likeTest(id, input.value)}});
      });
      this._invalidateRows();
      this._renderBody();
      this._emitChanges();
    });
    return input;
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

  _calcRow(ids) {
    const row = document.createElement("div");
    row.className = "dg-row dg-calcs";
    row.setAttribute("role", "row");
    row.setAttribute("aria-rowindex", "2");
    const values = this._table.getFilteredRowModel().rows.map((r) => r.original);
    for (const id of ids) {
      const def = this._defs.get(id);
      const cell = document.createElement("div");
      cell.className = "dg-cell";
      cell.setAttribute("role", "gridcell");
      this._placeCell(cell, id);
      cell.textContent = def.topCalc ? this._calc(def, values) : "";
      row.append(cell);
    }
    return row;
  }

  _calc(def, rows) {
    const values = rows.map((data) => data[def.field]);
    if (def.topCalc === "count") return String(values.filter((v) => v !== "" && v !== null && v !== undefined).length);
    if (def.topCalc === "avg") {
      const numbers = values.map((v) => (v === "" || v === null || v === undefined ? NaN : Number(v)))
        .filter((n) => !isNaN(n));
      if (!numbers.length) return "";
      const precision = def.topCalcParams && def.topCalcParams.precision !== undefined
        ? def.topCalcParams.precision : 2;
      const mean = numbers.reduce((sum, n) => sum + n, 0) / numbers.length;
      return String(parseFloat(precision === false ? mean : mean.toFixed(precision)));
    }
    return "";
  }

  // ---- resizing and moving columns --------------------------------------------

  _resizeHandle(id, cell) {
    const handle = document.createElement("div");
    // Every move of a drag redraws the header, so the handle that started it is
    // gone after the first: the one drawn in its place stays lit until the end.
    handle.className = "dg-resize-handle" + (this._resizing === id ? " is-active" : "");
    handle.setAttribute("aria-hidden", "true");
    handle.addEventListener("click", (event) => event.stopPropagation());
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = this._widths.get(id) || cell.getBoundingClientRect().width;
      const fixedBefore = this._fixedWidths.get(id);
      const rtl = getComputedStyle(this.element).direction === "rtl";
      this._resizing = id;
      handle.classList.add("is-active");
      // FOLLOWED ON THE DOCUMENT, NOT THE HANDLE. A listener on the handle heard
      // the first move and lost the rest when the redraw removed it, so a 60px
      // drag widened the column by 10.
      // ONE PLACEMENT A FRAME, AND NO ROW DRAWN AGAIN. A redraw per pointer move
      // dropped and drew every row on screen, and the totals over every row, for
      // a change that moves only widths: at 23,502 rows a move took 48 ms. The
      // cells already drawn take their new widths, and a wrapped row's new
      // height reaches the virtualizer through its own observer.
      let frame = 0;
      const move = (moveEvent) => {
        const delta = (moveEvent.clientX - startX) * (rtl ? -1 : 1);
        this._fixedWidths.set(id, Math.max(this._minWidth(id), Math.round(startWidth + delta)));
        if (frame) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          if (this._destroyed) return;
          this._layout();
          this._placeWidths();
        });
      };
      const end = () => {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", end);
        document.removeEventListener("pointercancel", end);
        if (frame) cancelAnimationFrame(frame);
        this._resizing = null;
        this._renderHeader();
        // A click on the handle is not a resize: the host saves what it hears
        // as a fixed width, and the column would stop sharing the frame.
        if (this._fixedWidths.get(id) !== fixedBefore) this._emit("columnResized", new ColumnHandle(this, id));
      };
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", end);
      document.addEventListener("pointercancel", end);
    });
    return handle;
  }

  /** Drag a header sideways to move its column, within its own pinned band. */
  _armColumnMove(cell, id) {
    cell.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      if (event.target.closest("button, input, .dg-resize-handle")) return;
      const startX = event.clientX;
      let dragging = false;
      let marker = null;
      let target = null;
      const band = () => this._visibleColumnIds().filter((other) =>
        this._pinSide(other) === this._pinSide(id) && !this._isBuiltIn(this._defs.get(other)));
      const move = (moveEvent) => {
        if (!dragging && Math.abs(moveEvent.clientX - startX) < DRAG_THRESHOLD) return;
        if (!dragging) {
          dragging = true;
          cell.classList.add("dg-col-moving");
          marker = document.createElement("div");
          marker.className = "dg-move-marker";
          this._header.append(marker);
        }
        target = null;
        const headerBox = this._header.getBoundingClientRect();
        for (const other of band()) {
          const otherCell = this._header.querySelector(`.dg-col[data-field="${CSS.escape(other)}"]`);
          if (!otherCell) continue;
          const box = otherCell.getBoundingClientRect();
          if (moveEvent.clientX < box.left + box.width / 2) { target = {id: other, after: false, x: box.left}; break; }
          target = {id: other, after: true, x: box.right};
        }
        if (target && marker) marker.style.insetInlineStart = px(target.x - headerBox.left);
      };
      const end = () => {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", end);
        document.removeEventListener("pointercancel", end);
        cell.classList.remove("dg-col-moving");
        if (marker) marker.remove();
        if (!dragging) return;
        this._suppressNextHeaderClick = true;
        setTimeout(() => { this._suppressNextHeaderClick = false; }, 0);
        if (target && target.id !== id) this._moveColumn(id, target.id, target.after);
      };
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", end);
      document.addEventListener("pointercancel", end);
    });
  }

  _moveColumn(id, targetId, after) {
    const order = this._displayColumnIds().filter((other) => other !== id);
    let index = order.indexOf(targetId);
    if (index < 0) return;
    if (after) index += 1;
    order.splice(index, 0, id);
    this._table.setColumnOrder(order);
    this.redraw();
    this._emit("columnMoved", new ColumnHandle(this, id));
  }

  _measureColumn(id) {
    const def = this._defs.get(id) || {};
    let widest = this._minWidth(id);
    const headerCell = this._header.querySelector(`.dg-col[data-field="${CSS.escape(id)}"]`);
    if (headerCell) {
      const content = headerCell.querySelector(".dg-col-content");
      const style = getComputedStyle(content);
      const padding = (parseFloat(style.paddingInlineStart) || 0) + (parseFloat(style.paddingInlineEnd) || 0);
      const gap = parseFloat(style.columnGap || style.gap) || 0;
      const items = Array.from(content.children);
      const itemsWidth = items.reduce((sum, item) =>
        sum + Math.max(item.scrollWidth, item.getBoundingClientRect().width), 0);
      widest = Math.max(widest, Math.ceil(padding + itemsWidth + gap * Math.max(0, items.length - 1)));
    }
    if (!this._isBuiltIn(def)) {
      this._body.querySelectorAll(`.dg-cell[data-field="${CSS.escape(id)}"]`).forEach((cell) => {
        const style = getComputedStyle(cell);
        const padding = (parseFloat(style.paddingInlineStart) || 0) + (parseFloat(style.paddingInlineEnd) || 0);
        let inner = 0;
        for (const child of cell.childNodes) {
          if (child.nodeType === Node.TEXT_NODE) {
            const range = document.createRange();
            range.selectNodeContents(child);
            inner += range.getBoundingClientRect().width;
          } else if (child.nodeType === Node.ELEMENT_NODE) {
            inner += Math.max(child.scrollWidth, child.getBoundingClientRect().width);
          }
        }
        widest = Math.max(widest, Math.ceil(inner + padding + 1));
      });
    }
    return widest;
  }

  // ---- popups and menus -------------------------------------------------------
  //
  // One at a time, closed by Escape, by a click anywhere outside, by scrolling
  // the table and by the table going away -- so nothing a column opened can
  // outlive the column, and opening a second one closes the first.

  _openPopup(anchor, content) {
    if (!(content instanceof Node)) return;
    const box = document.createElement("div");
    box.className = "dg-popup";
    box.setAttribute("role", "dialog");
    box.append(content);
    this._showFloating(anchor, box);
    const focusable = box.querySelector("input, button, select, textarea, [tabindex]");
    if (focusable) focusable.focus({preventScroll: true});
  }

  _openMenu(anchor, items, parent) {
    const menu = this._buildMenu(items || [], anchor);
    this._showFloating(anchor, menu, parent);
    const first = menu.querySelector(".dg-menu-item:not([disabled])");
    if (first) first.focus({preventScroll: true});
    return menu;
  }

  _buildMenu(items, anchor) {
    const menu = document.createElement("div");
    menu.className = "dg-menu";
    menu.setAttribute("role", "menu");
    for (const item of items) {
      if (!item) continue;
      if (item.separator) {
        const rule = document.createElement("div");
        rule.className = "dg-menu-separator";
        rule.setAttribute("role", "separator");
        menu.append(rule);
        continue;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "dg-menu-item";
      button.setAttribute("role", "menuitem");
      const label = typeof item.label === "function" ? item.label() : item.label;
      button.append(label instanceof Node ? label : document.createTextNode(text(label)));
      if (item.disabled) {
        button.disabled = true;
        button.classList.add("dg-menu-item-disabled");
      }
      if (Array.isArray(item.menu)) {
        button.setAttribute("aria-haspopup", "menu");
        button.classList.add("dg-menu-parent");
        const openChild = () => this._openSubmenu(button, item.menu, menu);
        button.addEventListener("click", (event) => { event.stopPropagation(); openChild(); });
        button.addEventListener("pointerenter", openChild);
      } else {
        button.addEventListener("pointerenter", () => this._closeSubmenu(menu));
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          if (item.disabled) return;
          this.closePopups();
          if (anchor && anchor.isConnected) anchor.focus({preventScroll: true});
          if (typeof item.action === "function") item.action(event);
        });
      }
      menu.append(button);
    }
    menu.addEventListener("keydown", (event) => this._menuKeys(event, menu));
    return menu;
  }

  _openSubmenu(parentItem, items, parentMenu) {
    if (parentMenu._child && parentMenu._child.parentItem === parentItem) return;
    this._closeSubmenu(parentMenu);
    const child = this._buildMenu(items, parentItem);
    child.classList.add("dg-submenu");
    document.body.append(child);
    const box = parentItem.getBoundingClientRect();
    this._position(child, box.right, box.top, box.left);
    parentMenu._child = {element: child, parentItem};
    parentItem.setAttribute("aria-expanded", "true");
    if (this._popup) this._popup.children.push(child);
  }

  _closeSubmenu(menu) {
    if (!menu._child) return;
    menu._child.parentItem.setAttribute("aria-expanded", "false");
    this._closeSubmenu(menu._child.element);
    menu._child.element.remove();
    menu._child = null;
  }

  _menuKeys(event, menu) {
    const items = Array.from(menu.querySelectorAll(":scope > .dg-menu-item:not([disabled])"));
    const index = items.indexOf(document.activeElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next = items[(index + step + items.length) % items.length];
      if (next) next.focus();
    } else if (event.key === "ArrowRight" && document.activeElement &&
               document.activeElement.classList.contains("dg-menu-parent")) {
      event.preventDefault();
      document.activeElement.click();
      const child = menu._child && menu._child.element.querySelector(".dg-menu-item:not([disabled])");
      if (child) child.focus();
    } else if (event.key === "ArrowLeft" && menu.classList.contains("dg-submenu")) {
      event.preventDefault();
      event.stopPropagation();
      const owner = this._popup && this._popup.element;
      const parentItem = owner && owner._child && owner._child.parentItem;
      if (owner) this._closeSubmenu(owner);
      if (parentItem) parentItem.focus();
    }
  }

  _showFloating(anchor, element) {
    document.body.append(element);
    const box = anchor.getBoundingClientRect();
    this._position(element, box.left, box.bottom + 4, null);
    anchor.setAttribute("aria-expanded", "true");
    const onPointer = (event) => {
      const inside = [element, ...popup.children].some((node) => node.contains(event.target));
      if (!inside && !anchor.contains(event.target)) this.closePopups();
    };
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      this.closePopups();
      if (anchor.isConnected) anchor.focus({preventScroll: true});
    };
    const popup = {
      anchor,
      element,
      children: [],
      close: () => {
        document.removeEventListener("pointerdown", onPointer, true);
        document.removeEventListener("click", onPointer, true);
        document.removeEventListener("keydown", onKey, true);
        anchor.setAttribute("aria-expanded", "false");
        popup.children.forEach((child) => child.remove());
        element.remove();
      },
    };
    this._popup = popup;
    // Escape at once: a key pressed the instant it opened must still close it.
    document.addEventListener("keydown", onKey, true);
    // The outside click next turn: the click that opened it is still travelling
    // to document, and would close it on the way.
    setTimeout(() => {
      if (this._popup !== popup) return;
      document.addEventListener("pointerdown", onPointer, true);
      document.addEventListener("click", onPointer, true);
    }, 0);
  }

  /** Place a floating element at (x, y), kept inside the viewport. */
  _position(element, x, y, flipX) {
    element.style.position = "fixed";
    element.style.left = "0px";
    element.style.top = "0px";
    const box = element.getBoundingClientRect();
    const maxX = window.innerWidth - box.width - 8;
    const maxY = window.innerHeight - box.height - 8;
    let left = x;
    if (left > maxX) left = flipX !== null && flipX !== undefined ? flipX - box.width : maxX;
    element.style.left = px(Math.max(8, left));
    element.style.top = px(Math.max(8, Math.min(y, maxY)));
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
      // The ordinal a row number shows: data rows only, in display order.
      const ordinals = new Map();
      let n = 0;
      rows.forEach((row) => { if (!row.getIsGrouped()) ordinals.set(row.id, ++n); });
      this._rowCache = {rows, ordinals};
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
      else if (fresh && !this._measuredRowHeight && !row.getIsGrouped()) {
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
    if (row.getIsGrouped()) {
      element.className = "dg-row dg-group";
      element.setAttribute("aria-expanded", String(row.getIsExpanded()));
      element.setAttribute("aria-level", String(row.depth + 1));
      element.append(this._groupBand(row));
      return element;
    }
    const ordinal = this._rowCache ? this._rowCache.ordinals.get(row.id) : index + 1;
    element.className = "dg-row" + (ordinal % 2 === 0 ? " dg-row-even" : " dg-row-odd");
    if (this.options.selectableRows) element.classList.add("dg-selectable");
    const selected = row.getIsSelected();
    element.classList.toggle("dg-selected", selected);
    if (this.options.selectableRows) element.setAttribute("aria-selected", String(selected));
    if (this.options.dataTree || this._grouping().length) {
      element.setAttribute("aria-level", String(row.depth + 1));
      if (row.subRows.length) element.setAttribute("aria-expanded", String(row.getIsExpanded()));
    }
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
    const treeColumn = this.options.dataTree &&
      (this.options.dataTreeElementColumn || this._visibleColumnIds().find((c) =>
        !this._isBuiltIn(this._defs.get(c)))) === id;
    if (treeColumn) {
      cell.classList.add("dg-tree-cell");
      cell.style.paddingInlineStart = "calc(var(--dg-cell-padding-inline, 0.75rem) + " +
        px(row.depth * this.options.dataTreeChildIndent) + ")";
      if (row.subRows.length) {
        const toggle = document.createElement("button");
        toggle.type = "button";
        const open = row.getIsExpanded();
        toggle.className = "dg-tree-toggle" + (open ? " is-open" : "");
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", open ? "Collapse" : "Expand");
        toggle.addEventListener("click", (event) => {
          event.stopPropagation();
          row.toggleExpanded();
          this._afterStateChange();
        });
        cell.append(toggle);
      } else if (row.depth > 0) {
        const spacer = document.createElement("span");
        spacer.className = "dg-tree-spacer";
        cell.append(spacer);
      }
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

  _groupBand(row) {
    const cell = document.createElement("div");
    cell.className = "dg-group-cell";
    cell.setAttribute("role", "gridcell");
    cell.style.paddingInlineStart = "calc(var(--dg-cell-padding-inline, 0.75rem) + " +
      px(row.depth * this.options.dataTreeChildIndent) + ")";
    const toggle = document.createElement("button");
    toggle.type = "button";
    const open = row.getIsExpanded();
    toggle.className = "dg-group-toggle" + (open ? " is-open" : "");
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Collapse group" : "Expand group");
    cell.append(toggle);
    const level = this._groupIds.indexOf(row.groupingColumnId);
    const headers = Array.isArray(this.options.groupHeader) ? this.options.groupHeader : [];
    const make = headers[level] || headers[0];
    const value = groupValue(row.groupingValue);
    const label = typeof make === "function"
      ? make(value, row.leafRows.length)
      : text(value) + " (" + row.leafRows.length + ")";
    cell.append(label instanceof Node ? label : document.createTextNode(text(label)));
    return cell;
  }

  _onBodyClick(event) {
    // The row is the body's own child that holds the click. A node a formatter
    // returns may carry any class, so a class does not find it.
    let rowElement = event.target;
    while (rowElement && rowElement.parentElement !== this._body) rowElement = rowElement.parentElement;
    if (!rowElement) return;
    // Every row drawn carries its own id, so one TanStack cannot find is a
    // defect, and its throw is left to be seen.
    const row = this._table.getRow(rowElement.dataset.rowId, true);
    if (row.getIsGrouped()) {
      row.toggleExpanded();
      this._afterStateChange();
      return;
    }
    if (!this.options.selectableRows) return;
    // A link, a button or a box in a cell is its own control, not a row click.
    if (event.target.closest("a, button, input, label, select, textarea")) return;
    row.toggleSelected(undefined, {selectChildren: false});
    this._afterStateChange();
  }

  /** The rows a download writes: what the filters keep, in display order, groups unrolled. */
  _exportRows() {
    const out = [];
    const visit = (rows) => rows.forEach((row) => {
      if (row.getIsGrouped()) { visit(row.subRows); return; }
      out.push(row.original);
      if (row.subRows.length) visit(row.subRows);
    });
    visit(this._table.getSortedRowModel().rows);
    return out;
  }
}

const grids = new WeakMap();

/** The grid drawn into an element (or a selector), for whoever holds only the page. */
DataGrid.find = function find(target) {
  const element = typeof target === "string" ? document.querySelector(target) : target;
  return element ? grids.get(element) : undefined;
};
