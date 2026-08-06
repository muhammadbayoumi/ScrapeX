// Who is signed in, and the token the engine borrows.
//
// PLATFORM-PLAN, the owner's ruling of 2026-08-05: «الإضافة تملكه وتُعيره
// للمحرّك» — the EXTENSION owns the token and lends it to the engine. Chrome
// holds it, refreshes it and scopes it to this extension's own OAuth client;
// nothing is written to disk here, and the engine never sees a refresh token.
//
// chrome.identity.getAuthToken is the whole mechanism. It is not a
// general-purpose OAuth flow and deliberately so: it can only ever return a
// token for the client id in this manifest, which is why the client id being
// public is safe by design. A Chrome Extension OAuth client has no secret —
// the file Google hands you when you create one contains none.

/** The scopes this extension asks for, and why each is here.
 *
 *  userinfo.email / userinfo.profile  the account's own name, address and
 *      photo — what the Profile button wears once someone is signed in.
 *      Both non-sensitive.
 *  drive.file  per-file access to what ScrapeX ITSELF creates. Non-sensitive,
 *      never needs Google's review, and it is the whole of Decision 20's
 *      promise: "only the files it creates. It never asks for the rest of
 *      your Drive."
 *  spreadsheets  full Sheets access, and the one SENSITIVE scope here. It is
 *      needed only to write into a spreadsheet the owner made by hand rather
 *      than one ScrapeX created. In Testing mode it costs nothing; if the
 *      Console ends up creating its own sheet, this can be dropped and the
 *      app never needs review at all.
 */
export const SCOPES = [
  "https://www.googleapis.com/auth/userinfo.email",
  "https://www.googleapis.com/auth/userinfo.profile",
  "https://www.googleapis.com/auth/drive.file",
  "https://www.googleapis.com/auth/spreadsheets",
];

const USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo";

/**
 * Turn Chrome's callback shape into one a caller can act on.
 *
 * `chrome.identity` reports failure by leaving the token undefined and setting
 * `chrome.runtime.lastError`, and a caller that only checked the token would
 * turn "the owner closed the consent window" into "signed in as undefined".
 * Every branch here is a different sentence for the same reason the release
 * feed's are: a single "sign-in failed" teaches the owner to press it again
 * and learn nothing.
 */
export function readTokenResult(token, lastError) {
  if (token) return { state: "ok", token };
  const message = (lastError && lastError.message) || "";
  if (/did not approve|canceled|closed/i.test(message)) {
    return { state: "declined",
             detail: "Sign-in was closed before it finished. Nothing changed." };
  }
  if (/OAuth2 not granted or revoked/i.test(message)) {
    return { state: "revoked",
             detail: "This account's access was revoked. Sign in again to restore it." };
  }
  if (/bad client id|invalid client/i.test(message)) {
    // The one failure the owner cannot fix by trying again, so it must not
    // look like the ones he can.
    return { state: "misconfigured",
             detail: "Chrome refused the OAuth client in this build. The " +
                     "extension's ID and the client in Google Cloud do not match." };
  }
  return { state: "failed",
           detail: message || "Chrome did not say why sign-in failed." };
}

/** Ask Chrome for a token. `interactive` false checks silently on open. */
export function getToken({ interactive = true, identity = chrome.identity,
                           runtime = chrome.runtime } = {}) {
  return new Promise((resolve) => {
    identity.getAuthToken({ interactive }, (token) =>
      resolve(readTokenResult(token, runtime.lastError)));
  });
}

/** The account behind a token: name, address and photo. */
export async function accountFor(token, fetchImpl = fetch) {
  try {
    const res = await fetchImpl(USERINFO, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) return null;
    const body = await res.json();
    return {
      name: typeof body.name === "string" ? body.name : "",
      email: typeof body.email === "string" ? body.email : "",
      // Google serves this from lh3.googleusercontent.com and the URL expires.
      // The panel treats a photo that fails to load as no photo, which is why
      // setProfileAvatar restores the account mark on `error`.
      picture: typeof body.picture === "string" ? body.picture : "",
    };
  } catch (_) {
    // A signed-in owner with no network is still signed in. Returning null
    // says "the photo and name are unknown", never "you are signed out".
    return null;
  }
}

/** Sign out on this device: drop Chrome's cached token and forget it. */
export function forgetToken(token, { identity = chrome.identity } = {}) {
  return new Promise((resolve) => {
    if (!token) return resolve();
    identity.removeCachedAuthToken({ token }, () => resolve());
  });
}
