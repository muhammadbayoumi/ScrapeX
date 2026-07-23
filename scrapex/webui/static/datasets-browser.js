(() => {
  "use strict";

  const browser = document.querySelector("[data-dataset-browser]");
  if (!browser) return;
  const workspace = browser.closest(".data-workspace");
  const search = browser.querySelector("[data-dataset-search]");
  const list = browser.querySelector("[data-dataset-list]");
  const count = browser.querySelector("[data-dataset-count]");
  const empty = browser.querySelector("[data-dataset-empty]");
  const toggles = [...document.querySelectorAll(
    "[data-dataset-toggle], [data-grid-datasets-toggle]")];
  let choices = [...browser.querySelectorAll("[data-dataset-choice]")];
  let groups = [...browser.querySelectorAll("[data-dataset-group]")];

  function filterDatasets() {
    const query = search.value.trim().toLocaleLowerCase();
    let shown = 0;
    choices.forEach((choice) => {
      choice.hidden = Boolean(query) && !choice.dataset.search.includes(query);
      if (!choice.hidden) shown += 1;
    });
    groups.forEach((group) => {
      group.hidden = !group.querySelector("[data-dataset-choice]:not([hidden])");
    });
    count.textContent = `Showing ${shown} of ${choices.length} datasets`;
    empty.hidden = shown !== 0 || choices.length === 0;
  }

  function makeChoice(item) {
    const choice = document.createElement("a");
    choice.className = "dataset-choice" + (item.observations ? "" : " dataset-choice-pending");
    choice.href = "/source/" + encodeURIComponent(item.source_key);
    choice.dataset.datasetChoice = "";
    choice.dataset.search = `${item.source_name} ${item.source_key}`.toLocaleLowerCase();
    if (location.pathname === choice.pathname) choice.setAttribute("aria-current", "page");

    const name = document.createElement("span");
    name.className = "dataset-choice-name";
    name.textContent = item.source_key.replaceAll("_", " ");
    const localName = document.createElement("span");
    localName.className = "dataset-choice-local";
    localName.dir = "auto";
    localName.textContent = item.source_name;
    const meta = document.createElement("span");
    meta.className = "dataset-choice-meta";
    meta.textContent = item.observations
      ? `${Number(item.observations).toLocaleString()} prices` : "No records";
    choice.append(name, localName, meta);
    return choice;
  }

  function makeGroup(label, items) {
    if (!items.length) return null;
    const group = document.createElement("section");
    group.className = "dataset-group";
    group.dataset.datasetGroup = "";
    const heading = document.createElement("span");
    heading.className = "dataset-group-label";
    heading.textContent = label;
    group.append(heading, ...items.map(makeChoice));
    return group;
  }

  async function hydrateDatasets() {
    const placeholder = browser.querySelector("[data-dataset-placeholder]");
    try {
      const response = await fetch("/api/sources");
      if (!response.ok) throw new Error(String(response.status));
      const items = (await response.json()).sources || [];
      if (!items.length) {
        if (placeholder) placeholder.textContent = "No configured datasets yet.";
        filterDatasets();
        return;
      }
      const available = items.filter((item) => Number(item.observations) > 0);
      const configured = items.filter((item) => Number(item.observations) === 0);
      const nextGroups = [makeGroup("Available data", available),
                          makeGroup("Configured sources", configured)].filter(Boolean);
      list.replaceChildren(...nextGroups);
      choices = [...browser.querySelectorAll("[data-dataset-choice]")];
      groups = [...browser.querySelectorAll("[data-dataset-group]")];
      filterDatasets();
      const hydratedSelected = browser.querySelector(
        '[data-dataset-choice][aria-current="page"]');
      if (hydratedSelected) {
        list.scrollTop = Math.max(0, hydratedSelected.offsetTop - list.clientHeight / 2);
      }
    } catch (error) {
      if (placeholder) placeholder.textContent = "Could not load datasets. Refresh to retry.";
      count.textContent = "Dataset list unavailable";
    }
  }

  function setCollapsed(collapsed, remember = false) {
    workspace.classList.toggle("datasets-collapsed", collapsed);
    toggles.forEach((toggle) => {
      toggle.setAttribute("aria-expanded", String(!collapsed));
      if (toggle.matches("[data-dataset-toggle]")) {
        const action = collapsed ? "Expand dataset list" : "Collapse dataset list";
        toggle.setAttribute("aria-label", action);
        toggle.title = action;
      } else {
        toggle.classList.toggle("is-active", !collapsed);
      }
    });
    if (remember) {
      try { localStorage.setItem("scrapex-datasets-collapsed", String(collapsed)); }
      catch (error) { /* A blocked preference must never block the list. */ }
    }
  }

  search.addEventListener("input", filterDatasets);
  toggles.forEach((toggle) => toggle.addEventListener("click", () => {
    const willCollapse = !workspace.classList.contains("datasets-collapsed");
    setCollapsed(willCollapse, true);
    if (!willCollapse && toggle.matches("[data-grid-datasets-toggle]")
        && matchMedia("(max-width: 900px)").matches) {
      browser.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    }
  }));

  let startsCollapsed = false;
  try { startsCollapsed = localStorage.getItem("scrapex-datasets-collapsed") === "true"; }
  catch (error) { /* Use the open default. */ }
  if (matchMedia("(max-width: 900px)").matches
      && !document.querySelector("[data-grid-datasets-toggle]")) {
    startsCollapsed = false;
  }
  setCollapsed(startsCollapsed);

  if (choices.length) filterDatasets();
  else hydrateDatasets();
  const selected = browser.querySelector('[data-dataset-choice][aria-current="page"]');
  if (selected) list.scrollTop = Math.max(0, selected.offsetTop - list.clientHeight / 2);
})();
