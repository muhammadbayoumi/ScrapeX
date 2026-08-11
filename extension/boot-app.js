// THE PANEL PAINTS FIRST, AND THEN THE APPLICATION STARTS.
//
// Chrome creates the Side Panel document HIDDEN and only reveals it after
// `load`. Measured on the owner's Chrome 151, twice, with the panel left
// untouched:
//
//     load 1259.4ms -> visibilitychange(visible) 1268.3ms    +8.9ms
//     load 2363.5ms -> visibilitychange(visible) 2370.0ms    +6.5ms
//
// And a hidden document has its resource loading deprioritised, so `load`
// arrives late — which keeps the panel hidden, which keeps loading slow. The
// third trace, taken after startup.js stopped waiting for a frame that a hidden
// document never gets, makes the deadlock plain: every piece of our own work had
// finished at 825ms, and `load` still did not fire until 2024ms with nothing of
// ours running in between. The same page in an ordinary visible tab goes from
// DOMContentLoaded to load in SEVENTEEN milliseconds.
//
// So the module graph is not slow. It is slow *because* the panel is hidden, and
// the panel is hidden *until* it finishes. The only way out is to stop `load`
// depending on it.
//
// The owner proved the remedy before it was written: app.html with this one
// script tag removed painted on the first click, while app.html unchanged did
// not. The shell needs no JavaScript to be correct — it is static markup, and a
// separate measurement of the whole ancestor chain found nothing that hides it —
// so nothing is lost by letting it reach the screen on its own.
//
// A separate file rather than an inline listener because MV3 forbids inline
// scripts on extension pages. `defer` so it does not block the parser; it is
// two hundred bytes and adds nothing measurable to `load`.
//
// THE TRADE, stated plainly: the panel becomes visible before it is
// interactive. A person may see the shell for a moment before the buttons
// respond. That is strictly better than the alternative they reported — a blank
// panel that stays blank until they click somewhere else entirely.
window.addEventListener("load", () => {
  const module = document.createElement("script");
  module.type = "module";
  module.src = "app.js";
  document.body.appendChild(module);
}, {once: true});
