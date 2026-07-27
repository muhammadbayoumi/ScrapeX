(() => {
  "use strict";

  const payload = document.getElementById("data-model-payload");
  const viewport = document.getElementById("model-viewport");
  if (!payload || !viewport) return;

  const model = JSON.parse(payload.textContent);
  const plane = document.getElementById("model-plane");
  const stage = document.getElementById("model-stage");
  const canvas = document.getElementById("model-lines");
  const inspector = document.getElementById("model-inspector");
  const databaseSelect = document.getElementById("model-database");
  const layerSelect = document.getElementById("model-layer");
  const searchInput = document.getElementById("model-search");
  const emptyState = document.getElementById("model-empty");
  const cards = [...stage.querySelectorAll(".model-table")];

  const CARD_WIDTH = 304;
  const CARD_HEIGHT = 228;
  const LANE_WIDTH = 344;
  const LANE_HEAD = 54;
  const GAP_Y = 22;
  const PAD = 32;
  const MIN_SCALE = .42;
  const MAX_SCALE = 1.35;
  const GROUP_COLOR_TOKENS = {
    source: "--diagram-source",
    general: "--diagram-general",
    pricing: "--diagram-pricing",
    unified: "--diagram-unified",
    operations: "--diagram-operations",
    other: "--diagram-other",
  };

  const databases = new Map(model.databases.map((database) => [database.key, database]));
  const tableById = new Map();
  model.databases.forEach((database) =>
    database.tables.forEach((table) => {
      table.searchText = [
        table.name,
        table.purpose,
        table.group,
        ...table.fields.map((field) => `${field.name} ${field.type}`),
      ].join(" ").toLowerCase();
      tableById.set(table.id, table);
    }));

  const state = {
    database: databaseSelect.value,
    layer: "all",
    search: "",
    selected: null,
    scale: 1,
    width: 0,
    height: 0,
  };

  const esc = (value) => String(value ?? "").replace(
    /[&<>"']/g,
    (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;",
      '"': "&quot;", "'": "&#39;",
    }[character]),
  );

  function groupColor(group) {
    const token = GROUP_COLOR_TOKENS[group] || GROUP_COLOR_TOKENS.other;
    return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  }

  function activeDatabase() {
    return databases.get(state.database);
  }

  function populateLayers() {
    const database = activeDatabase();
    layerSelect.innerHTML = [
      '<option value="all">All layers</option>',
      ...database.groups.map((group) =>
        `<option value="${esc(group.key)}">${esc(group.title)}</option>`),
    ].join("");
    state.layer = "all";
    layerSelect.value = "all";
  }

  function visibleTables() {
    const term = state.search.trim().toLowerCase();
    return activeDatabase().tables.filter((table) =>
      (state.layer === "all" || table.group_key === state.layer) &&
      (!term || table.searchText.includes(term)));
  }

  function setScale(nextScale, preserveCenter = true) {
    const previous = state.scale;
    const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / previous;
    const centerY = (viewport.scrollTop + viewport.clientHeight / 2) / previous;
    state.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
    stage.style.transform = `scale(${state.scale})`;
    plane.style.width = `${Math.max(viewport.clientWidth, state.width * state.scale)}px`;
    plane.style.height = `${Math.max(viewport.clientHeight, state.height * state.scale)}px`;
    if (preserveCenter) {
      viewport.scrollLeft = centerX * state.scale - viewport.clientWidth / 2;
      viewport.scrollTop = centerY * state.scale - viewport.clientHeight / 2;
    }
  }

  function fitModel() {
    if (!state.width || !state.height) return;
    const horizontal = (viewport.clientWidth - 28) / state.width;
    const vertical = (viewport.clientHeight - 28) / state.height;
    setScale(Math.min(1, horizontal, vertical), false);
    viewport.scrollTo({left: 0, top: 0, behavior: "smooth"});
  }

  function layoutModel({fit = false} = {}) {
    const database = activeDatabase();
    const visible = visibleTables();
    const visibleIds = new Set(visible.map((table) => table.id));
    const groups = database.groups
      .map((group) => ({
        ...group,
        tables: visible.filter((table) => table.group_key === group.key),
      }))
      .filter((group) => group.tables.length);

    stage.querySelectorAll(".model-lane-title").forEach((element) => element.remove());
    cards.forEach((card) => {
      const table = tableById.get(card.dataset.nodeId);
      const shown = table && visibleIds.has(table.id);
      card.classList.toggle("hidden", !shown);
      card.classList.remove("is-selected", "is-dimmed");
      if (shown) {
        card.style.setProperty(
          "--lane-color", groupColor(table.group_key));
      }
    });

    const maxRows = Math.max(1, ...groups.map((group) => group.tables.length));
    state.width = Math.max(
      PAD * 2 + groups.length * LANE_WIDTH,
      viewport.clientWidth / state.scale,
    );
    state.height = Math.max(
      PAD * 2 + LANE_HEAD + maxRows * (CARD_HEIGHT + GAP_Y),
      viewport.clientHeight / state.scale,
    );
    stage.style.width = `${state.width}px`;
    stage.style.height = `${state.height}px`;

    groups.forEach((group, groupIndex) => {
      const x = PAD + groupIndex * LANE_WIDTH;
      const heading = document.createElement("div");
      heading.className = "model-lane-title";
      heading.textContent = group.title;
      heading.style.left = `${x}px`;
      heading.style.top = `${PAD}px`;
      heading.style.setProperty(
        "--lane-color", groupColor(group.key));
      stage.appendChild(heading);

      group.tables.forEach((table, rowIndex) => {
        const card = stage.querySelector(`[data-node-id="${table.id}"]`);
        card.style.left = `${x}px`;
        card.style.top = `${PAD + LANE_HEAD + rowIndex * (CARD_HEIGHT + GAP_Y)}px`;
      });
    });

    stage.classList.add("is-ready");
    emptyState.classList.toggle("hidden", visible.length !== 0);
    setScale(state.scale, false);
    requestAnimationFrame(() => {
      applySelection();
      drawRelationships();
      if (fit) fitModel();
    });
  }

  function relationNodeId(database, table) {
    return `${database}:${table}`;
  }

  function directNeighbours(table) {
    const database = activeDatabase();
    const neighbours = new Set();
    database.relationships.forEach((relation) => {
      if (relation.from_table === table.name) {
        neighbours.add(relationNodeId(database.key, relation.to_table));
      }
      if (relation.to_table === table.name) {
        neighbours.add(relationNodeId(database.key, relation.from_table));
      }
    });
    return neighbours;
  }

  function applySelection() {
    const selected = state.selected ? tableById.get(state.selected) : null;
    const neighbours = selected ? directNeighbours(selected) : new Set();
    cards.forEach((card) => {
      if (card.classList.contains("hidden")) return;
      const isSelected = selected && card.dataset.nodeId === selected.id;
      const isRelated = selected && neighbours.has(card.dataset.nodeId);
      card.classList.toggle("is-selected", Boolean(isSelected));
      card.classList.toggle("is-dimmed", Boolean(selected && !isSelected && !isRelated));
    });
  }

  function pointFor(card, otherCard, oneSide) {
    const left = card.offsetLeft;
    const top = card.offsetTop;
    const right = left + card.offsetWidth;
    const centerY = top + card.offsetHeight / 2;
    const otherCenter = otherCard.offsetLeft + otherCard.offsetWidth / 2;
    const ownCenter = left + card.offsetWidth / 2;
    if (Math.abs(otherCenter - ownCenter) < 20) {
      return {x: right, y: centerY, label: oneSide ? "1" : "âˆ—", side: 1};
    }
    const side = otherCenter > ownCenter ? 1 : -1;
    return {
      x: side > 0 ? right : left,
      y: centerY,
      label: oneSide ? "1" : "âˆ—",
      side,
    };
  }

  function drawRelationships() {
    const ratio = window.devicePixelRatio || 1;
    canvas.style.width = `${state.width}px`;
    canvas.style.height = `${state.height}px`;
    canvas.width = Math.ceil(state.width * ratio);
    canvas.height = Math.ceil(state.height * ratio);
    const context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    context.clearRect(0, 0, state.width, state.height);

    const styles = getComputedStyle(document.documentElement);
    const normal = styles.getPropertyValue("--line").trim();
    const accent = styles.getPropertyValue("--accent").trim();
    const label = styles.getPropertyValue("--muted").trim();
    const selected = state.selected ? tableById.get(state.selected) : null;

    activeDatabase().relationships.forEach((relation) => {
      const childId = relationNodeId(relation.database, relation.from_table);
      const parentId = relationNodeId(relation.database, relation.to_table);
      const child = stage.querySelector(`[data-node-id="${childId}"]`);
      const parent = stage.querySelector(`[data-node-id="${parentId}"]`);
      if (!child || !parent ||
          child.classList.contains("hidden") || parent.classList.contains("hidden")) return;

      const one = pointFor(parent, child, true);
      const many = pointFor(child, parent, false);
      const highlighted = selected &&
        (selected.id === childId || selected.id === parentId);
      const direction = one.side === many.side ? one.side : 0;
      const reach = direction ? 54 * direction : 0;
      const middleX = direction
        ? Math.max(one.x, many.x) + reach
        : (one.x + many.x) / 2;

      context.beginPath();
      context.moveTo(one.x, one.y);
      context.bezierCurveTo(
        direction ? middleX : middleX,
        one.y,
        direction ? middleX : middleX,
        many.y,
        many.x,
        many.y,
      );
      context.strokeStyle = highlighted ? accent : normal;
      context.lineWidth = highlighted ? 2 : 1.25;
      context.globalAlpha = selected && !highlighted ? .35 : .9;
      context.stroke();
      context.globalAlpha = 1;

      context.fillStyle = highlighted ? accent : label;
      context.font = "600 12px ui-monospace, Consolas, monospace";
      context.fillText(one.label, one.x + (one.side > 0 ? 7 : -14), one.y - 5);
      context.fillText(many.label, many.x + (many.side > 0 ? 7 : -14), many.y - 5);
    });
  }

  function relationshipRows(table) {
    const database = activeDatabase();
    const rows = [];
    database.relationships.forEach((relation) => {
      if (relation.from_table === table.name) {
        rows.push(
          `<li><code>${esc(relation.from_column)}</code> <b>âˆ— â†’ 1</b> ` +
          `<code>${esc(relation.to_table)}.${esc(relation.to_column)}</code>` +
          `<small>This table carries the foreign key.</small></li>`);
      } else if (relation.to_table === table.name) {
        rows.push(
          `<li><code>${esc(relation.to_column)}</code> <b>1 â† âˆ—</b> ` +
          `<code>${esc(relation.from_table)}.${esc(relation.from_column)}</code>` +
          `<small>The related table carries the foreign key.</small></li>`);
      }
    });
    return rows.length
      ? rows.join("")
      : '<li><span class="muted">No direct foreign-key relationship.</span></li>';
  }

  function inspectTable(table) {
    state.selected = table.id;
    const fields = table.fields.map((field) => `
      <li>
        <span class="model-column-key">
          ${field.primary_key ? '<span class="key-badge pk">PK</span>' : ""}
          ${field.foreign_keys.length ? '<span class="key-badge fk">FK</span>' : ""}
          <code>${esc(field.name)}</code>
        </span>
        <small>${esc(field.type || "value")}</small>
      </li>`).join("");
    inspector.innerHTML = `
      <div class="model-inspector-content">
        <header class="model-inspector-header">
          <span class="page-eyebrow">${esc(table.group)}</span>
          <h3>${esc(table.name)}</h3>
          <p>${esc(table.purpose || "Live system table.")}</p>
          <div class="model-inspector-meta">
            <span><strong>${Number(table.rows).toLocaleString()}</strong><small>Rows</small></span>
            <span><strong>${table.column_count}</strong><small>Columns</small></span>
          </div>
        </header>
        <section class="model-inspector-section">
          <h4>Columns</h4>
          <ul class="model-column-list">${fields}</ul>
        </section>
        <section class="model-inspector-section">
          <h4>Direct relationships</h4>
          <ul class="model-relationship-list">${relationshipRows(table)}</ul>
        </section>
      </div>`;
    applySelection();
    drawRelationships();
  }

  cards.forEach((card) => {
    const open = () => inspectTable(tableById.get(card.dataset.nodeId));
    card.addEventListener("click", open);
    card.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      open();
    });
  });

  databaseSelect.addEventListener("change", () => {
    state.database = databaseSelect.value;
    state.selected = null;
    populateLayers();
    layoutModel({fit: true});
    inspector.innerHTML = `
      <div class="model-inspector-empty">
        <span class="model-inspector-mark" aria-hidden="true">â†’</span>
        <h3>Select a table</h3>
        <p>Its purpose, columns, and direct relationships will appear here.</p>
      </div>`;
  });
  layerSelect.addEventListener("change", () => {
    state.layer = layerSelect.value;
    state.selected = null;
    layoutModel({fit: true});
  });
  searchInput.addEventListener("input", () => {
    state.search = searchInput.value;
    state.selected = null;
    layoutModel();
  });
  document.getElementById("model-zoom-in").addEventListener(
    "click", () => setScale(state.scale + .12));
  document.getElementById("model-zoom-out").addEventListener(
    "click", () => setScale(state.scale - .12));
  document.getElementById("model-fit").addEventListener("click", fitModel);

  let pan = null;
  viewport.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".model-table")) return;
    pan = {
      x: event.clientX,
      y: event.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.classList.add("is-panning");
    viewport.setPointerCapture(event.pointerId);
  });
  viewport.addEventListener("pointermove", (event) => {
    if (!pan) return;
    viewport.scrollLeft = pan.left - (event.clientX - pan.x);
    viewport.scrollTop = pan.top - (event.clientY - pan.y);
  });
  const stopPan = (event) => {
    if (!pan) return;
    pan = null;
    viewport.classList.remove("is-panning");
    if (viewport.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId);
    }
  };
  viewport.addEventListener("pointerup", stopPan);
  viewport.addEventListener("pointercancel", stopPan);
  viewport.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setScale(state.scale + (event.deltaY < 0 ? .08 : -.08));
  }, {passive: false});

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => layoutModel(), 120);
  });
  window.addEventListener("scrapexappearancechange", () => layoutModel());

  populateLayers();
  layoutModel({fit: true});
})();
