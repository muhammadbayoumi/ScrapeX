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

const DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file";

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
/** The scopes a token actually carries, against the ones we asked for.
 *
 * GOOGLE LETS THE USER SAY NO TO ONE THING AND YES TO THE REST. The consent
 * screen puts `drive.file` behind its own checkbox, unticked, on a second page —
 * so the ordinary way to sign in is to tick nothing, and Chrome hands back a
 * perfectly valid token with two scopes instead of three.
 *
 * Nothing here used to look. The panel said "signed in", showed the name and
 * the picture, and the first backup failed with a 403 days later — the same
 * shape of failure this project keeps meeting: a partial state displayed as a
 * complete one.
 */
export function missingScopes(granted, wanted = SCOPES) {
  // Chrome only started passing grantedScopes in MV3, and an older build hands
  // back undefined. Undefined is NOT "nothing was granted" — it is "this
  // browser cannot tell us", and reporting a false refusal would be worse than
  // the silence it replaces.
  if (!Array.isArray(granted)) return null;
  const held = new Set(granted);
  return wanted.filter((scope) => !held.has(scope));
}

export function readTokenResult(token, lastError, grantedScopes) {
  if (token) {
    const missing = missingScopes(grantedScopes);
    if (missing && missing.length) {
      return {
        state: "partial", token, missing,
        // Named by what it COSTS, not by the scope string. "drive.file was not
        // granted" means nothing to the person reading it; "backups to Drive
        // will fail" is the sentence he can act on.
        detail: missing.includes(DRIVE_SCOPE)
          ? "Signed in, but Drive access was not granted — the checkbox on "
            + "Google's second screen was left unticked, so backups to Drive "
            + "will fail. Sign in again and tick it."
          : "Signed in, but Google did not grant everything ScrapeX asked for: "
            + missing.join(", "),
      };
    }
    return { state: "ok", token };
  }
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
      // The SECOND argument is the whole point: Chrome reports which scopes the
      // user actually agreed to, and this call has been throwing it away. It
      // survives the deadline wrapper unchanged — a token that arrives late is
      // still a token whose scopes have to be read.
      identity.getAuthToken({ interactive }, (token, grantedScopes) =>
        finish(readTokenResult(token, runtime.lastError, grantedScopes)));
    } catch (error) {
      finish({state: "failed", retryable: true,
              detail: (error && error.message) || "Chrome could not check the account."});
    }
  });
}

//: Google's own revocation endpoint. Fetching it is the ONLY way to end a
//: grant; `chrome.identity.removeCachedAuthToken` forgets Chrome's copy and
//: leaves the authorisation standing in the owner's Google account.
const REVOKE = "https://oauth2.googleapis.com/revoke";

/** End the grant at Google, not merely the copy in this browser.
 *
 * WHY THE OLD SIGN-OUT WAS NOT ONE. It called `removeCachedAuthToken` and
 * nothing else, so Google still saw an authorised app: signing in again handed
 * back a new token instantly, with no consent screen and no chance to choose a
 * different account. The owner noticed it as "sign in is suspiciously fast",
 * which is exactly what a grant that never ended looks like from outside.
 *
 * It also means a partial grant can never be repaired by signing out and in —
 * Google returns the same scopes it remembers agreeing to, silently, for ever.
 *
 * ORDER MATTERS. Revoke first, while the token is still valid; Chrome's cached
 * copy is dropped second, because a token removed from the cache is one this
 * function can no longer present to Google.
 */
export async function revokeToken(token, { identity = chrome.identity,
                                           fetchImpl = fetch } = {}) {
  if (!token) return { state: "ok", revoked: false };
  let revoked = false;
  let detail = "";
  try {
    const answer = await fetchImpl(REVOKE, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ token }).toString(),
    });
    // 200 is a revoked token. 400 is Google saying it was already invalid,
    // which is the same END STATE and must not be shown as a failure — the
    // grant is gone either way and the owner is not interested in which.
    revoked = answer.ok || answer.status === 400;
    if (!revoked) detail = `Google answered ${answer.status} to the revoke request.`;
  } catch (error) {
    detail = `Could not reach Google to end the session (${error && error.message
      ? error.message : error}).`;
  }
  // ALWAYS dropped, even when the revoke failed. Leaving Chrome holding a token
  // whose grant we tried to end is the worst of both: the panel looks signed
  // out and the browser is still carrying credentials.
  await forgetToken(token, { identity });
  return revoked ? { state: "ok", revoked: true }
                 : { state: "local-only", revoked: false, detail };
}

/** Make sure one scope is actually granted, asking Google again if it is not.
 *
 * THE RE-ASK IS THE WHOLE FUNCTION, and it needs one non-obvious step. Chrome
 * caches the token it already has, so calling `getAuthToken` again hands back
 * the SAME partial token without showing anyone anything — the consent screen
 * never appears and the caller concludes the user refused twice. The cached
 * token has to be dropped first; then Chrome has nothing to return and asks.
 *
 * Called at the moment a feature needs the scope, not at sign-in. A person who
 * never uses Drive is never asked about Drive, and one who does is asked when
 * the request means something to him rather than as the fifth item on a consent
 * screen he is skimming.
 */
export async function ensureScope(scope, { identity = chrome.identity,
                                           runtime = chrome.runtime } = {}) {
  const held = await getToken({ interactive: false, identity, runtime });
  if (held.state === "ok") return held;
  if (held.state !== "partial") return held;      // not signed in, or a real failure
  if (!held.missing.includes(scope)) {
    // Something else is missing, but not the thing being asked for. Not this
    // function's business to force a prompt for a scope nobody needs yet.
    return { ...held, state: "ok" };
  }

  await forgetToken(held.token, { identity });
  const again = await getToken({ interactive: true, identity, runtime });
  if (again.state === "partial" && again.missing.includes(scope)) {
    // Asked, and refused a second time. That is an ANSWER, and repeating the
    // prompt would be nagging — the caller says what cannot happen and stops.
    return { ...again, state: "refused" };
  }
  return again;
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
      // `sub` is Google's STABLE identifier for the account, and the only field
      // here that is safe to key a remembered account on. An address is not: a
      // person can change theirs, and Workspace admins reassign them — keying on
      // it would make one account silently become two rows, or worse, make a
      // renamed address land on somebody else's row. accounts.js requires this.
      id: typeof body.sub === "string" ? body.sub : "",
      name: typeof body.name === "string" ? body.name : "",
      email: typeof body.email === "string" ? body.email : "",
      // Google serves this from lh3.googleusercontent.com and the URL expires.
      // The panel treats a photo that fails to load as no photo, which is why
      // setProfileAvatar restores the account mark on `error`.
      picture: typeof body.picture === "string" ? body.picture : "",
    },
  };
}

// ---- more than one account -------------------------------------------------
//
// `getAuthToken` above can only ever speak for ONE account: the primary account
// of the Chrome profile. It takes no chooser and offers no way to name someone
// else, so an account SWITCHER cannot be built on it. `launchWebAuthFlow` can:
// it opens Google's own screen, and `login_hint` names which account to use.
//
// THE OWNER'S RULING OF 2026-08-11 chose the variant of this that keeps the
// 2026-08-05 ruling intact: «الصيغة الثالثة، بلا تخزين اعتمادات». So the flow
// here is the IMPLICIT one — `response_type=token`. It returns an access token
// and NO refresh token, which is exactly the point: there is no long-lived
// credential to store, accounts.js keeps a directory rather than a keyring, and
// a token for any account is minted at the moment it is needed.
//
// WHAT IT COSTS, said plainly: an access token lives about an hour and cannot be
// renewed offline. A silent mint (`prompt=none`) works only while Google's own
// session in this browser is alive. When it is not, the account is not broken —
// it is SIGNED OUT, which is a state the design already draws, and one click
// re-authorises it.
//
// WHY THE CODE FLOW IS NOT USED. Exchanging an authorization code at Google's
// token endpoint requires a client secret, and an extension cannot hold one: it
// ships to every user. PKCE removes the secret for installed apps, but the thing
// it buys is a REFRESH token — the credential this design deliberately declines
// to store. There is nothing to gain and a ruling to break.

/** Google's authorisation screen. */
const AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";

/** The Web-application OAuth client, which the extension does not have yet.
 *
 * NOT the client in manifest.json. That one is of type "Chrome Extension" and is
 * bound to `getAuthToken`; `launchWebAuthFlow` is refused against it. A second
 * client of type "Web application" has to be created in Google Cloud with this
 * extension's redirect URL — `chrome.identity.getRedirectURL()`, which resolves
 * to https://<extension-id>.chromiumapp.org/ — as an authorised redirect URI.
 *
 * IT IS EMPTY ON PURPOSE, and `authorize` refuses with `misconfigured` while it
 * is. A placeholder id would fail against Google with a message about the client
 * rather than about the thing that is actually missing, and the one failure the
 * owner cannot fix by trying again must not look like the ones he can.
 */
export const WEB_CLIENT_ID =
  "668111083414-p3485p5vjuc6uibagvhnoliapj61q1t5.apps.googleusercontent.com";

/**
 * Google stores the redirect URI WITHOUT a trailing slash; Chrome hands it over
 * WITH one. That one character is a `redirect_uri_mismatch`.
 *
 * MEASURED, not guessed. The owner created the client on 2026-08-12 and the JSON
 * Google produced records exactly:
 *
 *     "redirect_uris": ["https://<id>.chromiumapp.org"]
 *
 * while `chrome.identity.getRedirectURL()` with no path returns
 * `https://<id>.chromiumapp.org/`. Google matches this value literally and
 * refuses the pair, with an error naming the redirect rather than the slash —
 * so the one-character cause is invisible in the one message that mentions it.
 *
 * Normalised HERE rather than by asking the owner to re-add the URI with a
 * slash: the Console strips it when the path is empty, so that request would
 * have been impossible to satisfy. Chrome still catches the redirect, because it
 * intercepts anything under the extension's chromiumapp.org host.
 */
export function registeredRedirect(url) {
  return String(url || "").replace(/\/+$/, "");
}

/** Build the URL Google's screen is opened at.
 *
 * `prompt` is the whole difference between the two ways this is called. `none`
 * asks Google to answer from the session it already has and to refuse rather
 * than draw anything — that is the silent mint, and it must never open a window.
 * `select_account` is the interactive one, and it shows the chooser even when
 * Google could have answered silently: an ADD ANOTHER ACCOUNT button that
 * skipped the chooser and re-signed-in the account you already had would be
 * indistinguishable from a broken button.
 */
export function authUrl({ clientId, redirectUri, email = "", interactive = true,
                          scopes = SCOPES } = {}) {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: "token",
    scope: scopes.join(" "),
    // Carry forward anything this person already agreed to, so a second sign-in
    // does not quietly drop a scope they granted the first time.
    include_granted_scopes: "true",
    prompt: interactive ? "select_account" : "none",
  });
  // Which account this is FOR. Without it a silent request answers for whoever
  // Google considers default, and the panel would switch accounts by itself.
  if (email) params.set("login_hint", email);
  return `${AUTH_ENDPOINT}?${params.toString()}`;
}

/** Read what Google sent back to the redirect URL.
 *
 * The implicit flow puts its answer in the FRAGMENT, not the query, and errors
 * can arrive in either — so both are read. Every branch is a different sentence
 * for the same reason readTokenResult's are: a single "sign-in failed" teaches
 * the owner to press the button again and learn nothing.
 */
export function readRedirect(redirectUrl, lastError) {
  if (!redirectUrl) {
    const message = (lastError && lastError.message) || "";
    if (/did not approve|canceled|cancelled|closed/i.test(message)) {
      return { state: "declined",
               detail: "Sign-in was closed before it finished. Nothing changed." };
    }
    return { state: "failed",
             detail: message || "Chrome did not say why sign-in failed." };
  }

  let url;
  try { url = new URL(redirectUrl); }
  catch (_) {
    return { state: "failed", detail: "Google returned an unreadable answer." };
  }
  const fragment = new URLSearchParams(url.hash.replace(/^#/, ""));
  const error = fragment.get("error") || url.searchParams.get("error");

  if (error) {
    // THE ORDINARY REFUSAL, and it is not a failure. `prompt=none` asks Google
    // to answer without drawing anything; these four are Google saying "not
    // without the person". That is a SIGNED-OUT account, a state the panel
    // draws, and it must not be reported as something going wrong.
    if (/^(login_required|consent_required|interaction_required|account_selection_required)$/
        .test(error)) {
      return { state: "interaction-required", retryable: true,
               detail: "This account's Google session has ended. Sign in to use it again." };
    }
    if (error === "access_denied") {
      return { state: "declined",
               detail: "Sign-in was refused. Nothing changed." };
    }
    if (/^(invalid_client|unauthorized_client|invalid_request|redirect_uri_mismatch)$/
        .test(error)) {
      return { state: "misconfigured",
               detail: "Google refused the OAuth client in this build. The " +
                       "extension's redirect URL and the client in Google Cloud " +
                       "do not match." };
    }
    if (error === "admin_policy_enforced") {
      // A Workspace administrator blocked it. Pressing again cannot fix that,
      // and the person needs to know it is their organisation and not ScrapeX.
      return { state: "blocked-by-admin",
               detail: "This account's organisation blocks ScrapeX. Ask a " +
                       "Google Workspace administrator to allow it, or use " +
                       "another account." };
    }
    return { state: "failed", detail: `Google refused sign-in (${error}).` };
  }

  const token = fragment.get("access_token");
  if (!token) {
    return { state: "failed", detail: "Google's answer carried no token." };
  }

  // Same partial-grant reading as getAuthToken's, and deliberately the same
  // vocabulary: the consent screen's unticked Drive checkbox is one behaviour
  // and must not have two names depending on which flow met it. The implicit
  // flow always reports `scope`, so unlike Chrome's callback there is no
  // "this browser cannot tell us" case here.
  const granted = (fragment.get("scope") || "").split(" ").filter(Boolean);
  const missing = missingScopes(granted, SCOPES);
  if (missing && missing.length) {
    return {
      state: "partial", token, missing,
      detail: missing.includes(DRIVE_SCOPE)
        ? "Signed in, but Drive access was not granted — the checkbox on "
          + "Google's second screen was left unticked, so backups to Drive "
          + "will fail. Sign in again and tick it."
        : "Signed in, but Google did not grant everything ScrapeX asked for: "
          + missing.join(", "),
    };
  }
  return { state: "ok", token };
}

/** Get a token for ONE named account, silently when that is possible.
 *
 * `interactive: false` is the panel's ordinary path: it opens no window, and a
 * refusal is the answer rather than an error. Only a control the person pressed
 * is allowed to pass `true`.
 */
export async function authorize({ email = "", interactive = false,
                                  identity = chrome.identity,
                                  runtime = chrome.runtime,
                                  clientId = WEB_CLIENT_ID } = {}) {
  if (!clientId) {
    return { state: "misconfigured",
             detail: "This build has no Web OAuth client, so accounts cannot be "
                   + "added or switched. One has to be created in Google Cloud "
                   + "with this extension's redirect URL." };
  }

  let redirectUri;
  try { redirectUri = registeredRedirect(identity.getRedirectURL()); }
  catch (error) {
    return { state: "failed",
             detail: (error && error.message) || "Chrome would not name a redirect URL." };
  }

  const url = authUrl({ clientId, redirectUri, email, interactive });
  return new Promise((resolve) => {
    try {
      identity.launchWebAuthFlow({ url, interactive }, (redirectUrl) =>
        resolve(readRedirect(redirectUrl, runtime.lastError)));
    } catch (error) {
      resolve({ state: "failed", retryable: true,
                detail: (error && error.message) || "Chrome could not open sign-in." });
    }
  });
}

/** Sign out on this device: drop Chrome's cached token and forget it. */
export function forgetToken(token, { identity = chrome.identity } = {}) {
  return new Promise((resolve) => {
    if (!token) return resolve();
    identity.removeCachedAuthToken({ token }, () => resolve());
  });
}
