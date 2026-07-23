(() => {
  "use strict";

  const browser = document.querySelector("[data-dataset-browser]");
  if (!browser) return;

  const menu = browser.closest("details");
  const trigger = menu && menu.querySelector(":scope > summary");
  const search = browser.querySelector("[data-dataset-search]");
  const choices = [...browser.querySelectorAll("[data-dataset-choice]")];
  const groups = [...browser.querySelectorAll("[data-dataset-group]")];
  const count = browser.querySelector("[data-dataset-count]");
  const empty = browser.querySelector("[data-dataset-empty]");

  function filter() {
    const term = (search?.value || "").trim().toLocaleLowerCase();
    let visible = 0;
    choices.forEach((choice) => {
      const match = !term || (choice.dataset.search || "").includes(term);
      choice.hidden = !match;
      if (match) visible += 1;
    });
    groups.forEach((group) => {
      group.hidden = !group.querySelector("[data-dataset-choice]:not([hidden])");
    });
    if (count) count.textContent = `Showing ${visible} of ${choices.length} datasets`;
    if (empty) empty.hidden = visible !== 0;
  }

  function syncExpanded() {
    if (trigger && menu) trigger.setAttribute("aria-expanded", String(menu.open));
  }

  search?.addEventListener("input", filter);
  filter();

  if (!menu || !trigger) return;
  syncExpanded();
  menu.addEventListener("toggle", () => {
    syncExpanded();
    if (!menu.open) return;
    requestAnimationFrame(() => {
      search?.focus({preventScroll: true});
      browser.querySelector('[aria-current="page"]')?.scrollIntoView({block: "nearest"});
    });
  });

  document.addEventListener("pointerdown", (event) => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !menu.open) return;
    event.preventDefault();
    menu.open = false;
    trigger.focus();
  });
})();
