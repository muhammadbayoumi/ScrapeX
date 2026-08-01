/* One split button, for every surface that needs one.
 *
 * The dataset Export control invented this pattern — a primary action beside a
 * <details> menu of secondary ones — and the Activity panel's log control is the
 * same shape. Rather than write it twice (the DRY the owner asked for by name),
 * the behaviour lives here and both the web grid and the extension panel call
 * it. It is a CLASSIC script, not a module, so it sets one global the way
 * appearance.js does — the two surfaces cannot import from each other at runtime,
 * so a shared file copied into both is the only reuse they can share.
 *
 * The markup contract (styled by .split-button in components.css):
 *   <div class="split-button">
 *     <button class="split-button-primary" data-split-action="PRIMARY">…</button>
 *     <details class="split-button-menu">
 *       <summary class="split-button-trigger" aria-haspopup="menu"
 *                aria-expanded="false">▾</summary>
 *       <div class="split-button-options" role="menu">
 *         <button class="split-button-option" data-split-action="X" role="menuitem">…</button>
 *       </div>
 *     </details>
 *   </div>
 *
 * wire(root, onAction) hands every clicked [data-split-action] to onAction and
 * then closes the menu. The caller owns what each action DOES — download a file,
 * copy to the clipboard — because that is the part that genuinely differs; the
 * open/close/aria/escape/outside-click dance is the part that does not, and the
 * part a second copy would get subtly wrong.
 */
(function () {
  "use strict";

  function wire(root, onAction) {
    if (!root || root.dataset.splitWired) return;
    root.dataset.splitWired = "1";
    const menu = root.querySelector(".split-button-menu");
    const trigger = menu && menu.querySelector(".split-button-trigger");

    const close = () => {
      if (!menu) return;
      menu.open = false;
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    };

    if (menu && trigger) {
      // The <details> is the source of truth for open/closed; aria only ever
      // mirrors it, so a click on the summary and a programmatic close agree.
      menu.addEventListener("toggle", () =>
        trigger.setAttribute("aria-expanded", String(menu.open)));
      menu.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !menu.open) return;
        event.preventDefault();
        close();
        trigger.focus();
      });
      // An outside click closes it. Registered on the document, guarded to this
      // menu, so several split buttons on one page never fight over the event.
      document.addEventListener("click", (event) => {
        if (menu.open && !menu.contains(event.target)) close();
      });
    }

    root.querySelectorAll("[data-split-action]").forEach((button) =>
      button.addEventListener("click", (event) => {
        close();
        if (typeof onAction === "function") onAction(button.dataset.splitAction, button, event);
      }));
  }

  window.ScrapeXSplitButton = { wire };
})();
