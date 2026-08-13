// Choosing a spreadsheet the owner already had.
//
// `drive.file` reaches two kinds of file: ones this extension created, and ones
// the owner HANDS it through Google Picker. Picker loads apis.google.com/js/api.js
// and MV3 forbids an extension executing code fetched from a server, so the
// chooser lives on an ordinary web origin and hands an id back through
// background.js's onMessageExternal listener.
//
// WHY THIS IS A MODULE. Two surfaces need it — the side panel, to pick the
// workbook exports are written into, and the Console, to pick the add-in's
// CONFIGURATION workbook. A second copy of a nonce handoff is a second place
// for the token rules to drift, and the token rules are the whole reason this
// flow is shaped the way it is.

//: Where the chooser lives. It cannot be a page in this extension: Google
//: Picker loads a remote script and MV3 forbids that.
export const PICKER_PAGE =
  "https://muhammadbayoumi.github.io/mbiXsite/scrapex-picker.html";

//: How long the panel waits for a choice, and how long the handoff carrying the
//: token stays tradeable. The same number deliberately: a handoff outliving the
//: wait would be a key left under a mat nobody is watching any more.
export const PICK_WINDOW_MS = 120_000;

/** One chooser at a time, per surface. */
const inFlight = new Set();

/**
 * Open the chooser and wait for what comes back.
 *
 * THE TOKEN DOES NOT TRAVEL IN THE URL. It did, in the fragment, defended by
 * the true and irrelevant fact that browsers do not send fragments to servers.
 * The reader that matters is local: chrome.tabs.create COMMITS the URL, and the
 * committed URL is delivered whole — fragment included — to every installed
 * extension holding the `tabs` permission. Erasing it in the page afterwards
 * cannot help; the delivery already happened.
 *
 * So the URL carries a nonce. background.js trades it, once, for the token.
 *
 * Returns `{fileId, name}` when a file was chosen, `null` when the owner
 * cancelled or the window closed, and throws only when it was never opened.
 */
export async function chooseSpreadsheet({
  token,
  surface = "panel",
  chromeApi = globalThis.chrome,
  windowMs = PICK_WINDOW_MS,
  now = () => Date.now(),
  newNonce = () => crypto.randomUUID(),
} = {}) {
  if (!token) throw new Error("no Google session");
  if (inFlight.has(surface)) throw new Error("a chooser is already open");

  const nonce = newNonce();
  await chromeApi.storage.session.set({
    scrapexPickerHandoff: {nonce, token, expires: now() + windowMs},
  });
  // Any earlier answer is not this question's. A stale one left here would be
  // read within the first second and returned as the owner's new choice.
  await chromeApi.storage.session.remove("scrapexPickedSpreadsheet");

  chromeApi.tabs.create({
    url: `${PICKER_PAGE}#n=${encodeURIComponent(nonce)}`
       + `&ext=${encodeURIComponent(chromeApi.runtime.id)}`,
  });

  inFlight.add(surface);
  const deadline = now() + windowMs;
  try {
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 1000));

      const held = await chromeApi.storage.session.get("scrapexPickedSpreadsheet");
      const picked = held.scrapexPickedSpreadsheet;
      if (picked) {
        await chromeApi.storage.session.remove("scrapexPickedSpreadsheet");
        return picked.fileId ? picked : null;
      }
      if (now() > deadline) {
        // The handoff dies with the wait. One left behind is a token that can
        // still be traded by whoever kept the nonce.
        await chromeApi.storage.session.remove("scrapexPickerHandoff");
        return null;
      }
    }
  } finally {
    inFlight.delete(surface);
  }
}

/** Whether a chooser is open for this surface — for a button that must wait. */
export function choosing(surface = "panel") {
  return inFlight.has(surface);
}
