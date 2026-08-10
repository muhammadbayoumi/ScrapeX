import { fetchWithDeadline, STARTUP_DEADLINES } from "./startup.js";

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
 *
 * `spreadsheets` USED TO BE HERE AND WAS REMOVED BEFORE THE FIRST LISTING. It
 * is Google's one SENSITIVE scope in this set, and nothing in the codebase
 * called the Sheets API — it was declared for the Console, which is M7 and not
 * built. The store's own guidance is blunt about that: "Requesting an
 * unnecessary permission will result in this version being rejected."
 *
 * And it turns out not to be needed even when M7 arrives. `drive.file` already
 * grants read and write on any file the app CREATED, and on any file the user
 * hands it through the Google Picker — which covers both of Decision 28's
 * buttons, create-a-sheet and use-my-existing-sheet, without a sensitive scope.
 * That is better for the owner's users too: the consent screen says "files you
 * open with this app" instead of "see and edit all your spreadsheets".
 *
 * If the Picker route turns out not to reach some case at build time, the scope
 * comes back THEN, attached to a feature that exists and can be demonstrated.
 */
export const SCOPES = [
  "https://www.googleapis.com/auth/userinfo.email",
  "https://www.googleapis.com/auth/userinfo.profile",
  "https://www.googleapis.com/auth/drive.file",
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
    return { state: "authorization-required",
             detail: "Google access isn’t currently granted. Sign in with Google to try again." };
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
                           runtime = chrome.runtime,
                           timeoutMs = interactive
                             ? STARTUP_DEADLINES.interactiveToken
                             : STARTUP_DEADLINES.silentToken,
                           signal = null } = {}) {
  return new Promise((resolve) => {
    let settled = false;
    let timer = null;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", cancelled);
      resolve(result);
    };
    const cancelled = () => finish({
      state: "cancelled", retryable: true,
      detail: "The account check was cancelled.",
    });

    if (signal?.aborted) {
      cancelled();
      return;
    }
    if (signal) signal.addEventListener("abort", cancelled, {once: true});
    timer = setTimeout(() => finish({
      state: "timeout", retryable: true,
      detail: interactive
        ? "Google sign-in did not finish in time. Try again when you are ready."
        : "Chrome did not finish checking the account in time. Try again.",
    }), timeoutMs);

    try {
      identity.getAuthToken({ interactive }, (token) =>
        finish(readTokenResult(token, runtime.lastError)));
    } catch (error) {
      finish({state: "failed", retryable: true,
              detail: (error && error.message) || "Chrome could not check the account."});
    }
  });
}

/** The account behind a token: name, address and photo.
 *
 * Returns a discriminated result so callers can tell retryable lookup failures
 * from a token that Chrome needs to forget. Missing optional fields are still
 * a successful account response.
 */
export async function accountFor(token, fetchImpl = fetch, {signal = null} = {}) {
  let res;
  try {
    res = await fetchWithDeadline(fetchImpl, USERINFO, {
      headers: { Authorization: `Bearer ${token}` },
    }, STARTUP_DEADLINES.accountDetails, [signal]);
  } catch (error) {
    const name = error && error.name;
    if (name === "AbortError" || name === "TimeoutError") {
      return { state: "timeout", retryable: true,
               detail: "The account request timed out." };
    }
    return { state: "network", retryable: true,
             detail: "Could not reach Google." };
  }

  if (!res.ok) {
    if (res.status === 401) {
      return { state: "unauthorized", retryable: false,
               detail: "Google access isn’t currently granted." };
    }
    if (res.status === 403) {
      return { state: "forbidden", retryable: false,
               detail: "Google refused this account request." };
    }
    if (res.status === 429) {
      return { state: "rate-limited", retryable: true,
               detail: "Google is rate-limiting account requests." };
    }
    if (res.status >= 500) {
      return { state: "server", retryable: true,
               detail: "Google had a server error." };
    }
    return { state: "client", retryable: false,
             detail: `Google returned an error (${res.status}).` };
  }

  let body;
  try { body = await res.json(); }
  catch (_) {
    return { state: "malformed", retryable: false,
             detail: "Google returned an unreadable account response." };
  }

  return {
    state: "ok",
    account: {
      name: typeof body.name === "string" ? body.name : "",
      email: typeof body.email === "string" ? body.email : "",
      // Google serves this from lh3.googleusercontent.com and the URL expires.
      // The panel treats a photo that fails to load as no photo, which is why
      // setProfileAvatar restores the account mark on `error`.
      picture: typeof body.picture === "string" ? body.picture : "",
    },
  };
}

/** Sign out on this device: drop Chrome's cached token and forget it. */
export function forgetToken(token, { identity = chrome.identity } = {}) {
  return new Promise((resolve) => {
    if (!token) return resolve();
    identity.removeCachedAuthToken({ token }, () => resolve());
  });
}
