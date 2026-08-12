// Switching between accounts, and the credential that is never asked for.
//
// getAuthToken speaks for exactly one account — the Chrome profile's primary —
// so the switcher is built on launchWebAuthFlow instead. The owner ruled on
// 2026-08-11 that it must not cost the 2026-08-05 ruling: no credential is
// stored, so the flow is the IMPLICIT one and there is no refresh token to keep.
// The first two tests are that ruling written as assertions.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  SCOPES, accountFor, authUrl, authorize, readRedirect, WEB_CLIENT_ID,
} from "../identity.js";

const DRIVE = "https://www.googleapis.com/auth/drive.file";
const CLIENT = "web-client.apps.googleusercontent.com";
const REDIRECT = "https://ekcgggphcfdbjgfkcmjagehfjhijeang.chromiumapp.org/";

const params = (url) => new URL(url).searchParams;

// Injected everywhere, because `runtime = chrome.runtime` is a DEFAULT
// PARAMETER: JavaScript evaluates it on every call that omits the argument, not
// only on the branch that reads it. Outside a browser that throws before the
// function body starts — including on the path that refuses early.
const RUNTIME = { lastError: null };

/** A chrome.identity that records the call instead of opening anything. */
function fakeIdentity(answer) {
  return {
    calls: [],
    getRedirectURL: () => REDIRECT,
    launchWebAuthFlow(options, callback) {
      this.calls.push(options);
      callback(typeof answer === "function" ? answer(options) : answer);
    },
  };
}

// ---- the ruling ------------------------------------------------------------

test("the flow never asks for a credential that would have to be stored", () => {
  const url = authUrl({ clientId: CLIENT, redirectUri: REDIRECT });
  // `code` is the response type that buys a refresh token — the long-lived
  // credential this design declines to hold. `token` is the one that does not.
  assert.equal(params(url).get("response_type"), "token");
  assert.doesNotMatch(url, /access_type=offline/,
    "offline access is a request for a refresh token");
  assert.doesNotMatch(url, /client_secret/,
    "a secret in a URL an extension builds is a secret shipped to every user");
});

test("a granted token is returned and nothing beside it is kept", () => {
  const answer = readRedirect(
    `${REDIRECT}#access_token=ya29.TOKEN&token_type=Bearer&expires_in=3599`
    + `&scope=${encodeURIComponent(SCOPES.join(" "))}`);
  assert.equal(answer.state, "ok");
  assert.equal(answer.token, "ya29.TOKEN");
  assert.deepEqual(Object.keys(answer).sort(), ["state", "token"],
    "the result grew a field, and the only fields here should be usable now");
});

// ---- naming which account --------------------------------------------------

test("a silent request names the account and refuses to draw anything", () => {
  const url = authUrl({ clientId: CLIENT, redirectUri: REDIRECT,
                        email: "owner@example.com", interactive: false });
  assert.equal(params(url).get("prompt"), "none",
    "a silent mint that may open a window is not silent");
  assert.equal(params(url).get("login_hint"), "owner@example.com",
    "without login_hint Google answers for whoever it considers default, and "
    + "the panel would switch accounts by itself");
});

test("adding an account always shows the chooser, even when Google could answer", () => {
  // An "Add another account" button that skipped the chooser would silently
  // re-sign-in the account you already had — indistinguishable from a button
  // that does nothing.
  const url = authUrl({ clientId: CLIENT, redirectUri: REDIRECT, interactive: true });
  assert.equal(params(url).get("prompt"), "select_account");
  assert.equal(params(url).get("login_hint"), null);
});

test("a second sign-in does not quietly drop a scope already granted", () => {
  const url = authUrl({ clientId: CLIENT, redirectUri: REDIRECT });
  assert.equal(params(url).get("include_granted_scopes"), "true");
  assert.equal(params(url).get("scope"), SCOPES.join(" "));
});

// ---- reading the answer ----------------------------------------------------

test("an ended Google session is a signed-out account, not a failure", () => {
  // `prompt=none` refusing is the ORDINARY case for a remembered account whose
  // browser session has lapsed. The design draws it as a signed-out row with a
  // Sign in button; reporting it as an error would put a warning in front of
  // something entirely normal.
  for (const error of ["login_required", "consent_required",
                       "interaction_required", "account_selection_required"]) {
    const answer = readRedirect(`${REDIRECT}#error=${error}`);
    assert.equal(answer.state, "interaction-required", error);
    assert.equal(answer.retryable, true, error);
  }
});

test("a refusal by the person is not a refusal by the machine", () => {
  assert.equal(readRedirect(`${REDIRECT}#error=access_denied`).state, "declined");
  assert.equal(readRedirect(null, { message: "The user closed the window" }).state,
               "declined");
});

test("an organisation's block says so, instead of looking like a retryable fault", () => {
  // Pressing again can never fix this one, and the person needs to know it is
  // their Workspace administrator and not ScrapeX.
  const answer = readRedirect(`${REDIRECT}#error=admin_policy_enforced`);
  assert.equal(answer.state, "blocked-by-admin");
  assert.match(answer.detail, /administrator/);
});

test("a wrong OAuth client is named as the thing trying again cannot fix", () => {
  for (const error of ["invalid_client", "unauthorized_client",
                       "invalid_request", "redirect_uri_mismatch"]) {
    assert.equal(readRedirect(`${REDIRECT}#error=${error}`).state, "misconfigured", error);
  }
});

test("a partial grant reads the same here as it does through getAuthToken", () => {
  // The unticked Drive checkbox is ONE behaviour. Two names for it, depending
  // on which flow happened to meet it, is how a product ends up explaining the
  // same thing two different ways.
  const without = SCOPES.filter((scope) => scope !== DRIVE);
  const answer = readRedirect(
    `${REDIRECT}#access_token=ya29.TOKEN&scope=${encodeURIComponent(without.join(" "))}`);
  assert.equal(answer.state, "partial");
  assert.deepEqual(answer.missing, [DRIVE]);
  assert.match(answer.detail, /backups to Drive will fail/);
  assert.equal(answer.token, "ya29.TOKEN", "the token still works for what WAS granted");
});

test("an answer carrying no token is a failure, not an empty success", () => {
  assert.equal(readRedirect(`${REDIRECT}#token_type=Bearer`).state, "failed");
  assert.equal(readRedirect("not a url at all").state, "failed");
});

test("an error in the query is read as well as one in the fragment", () => {
  // Google puts the implicit flow's answer in the fragment, but not every error
  // path does. Reading only one of the two turns a refusal into "no token".
  assert.equal(readRedirect(`${REDIRECT}?error=access_denied`).state, "declined");
});

// ---- the flow --------------------------------------------------------------

test("a build with no Web OAuth client refuses by name, before opening anything", async () => {
  const identity = fakeIdentity(`${REDIRECT}#access_token=ya29.TOKEN`);
  const answer = await authorize({ identity, runtime: RUNTIME, clientId: "" });
  assert.equal(answer.state, "misconfigured");
  assert.match(answer.detail, /Google Cloud/);
  assert.equal(identity.calls.length, 0,
    "Chrome was asked to open a flow that could not possibly succeed");
});

test("a build with no Web OAuth client refuses instead of guessing", () => {
  // This asserted `WEB_CLIENT_ID === ""` until 2026-08-12, when the owner
  // created the client. It was a sentinel, and it fell the moment it was
  // satisfied — which is what a sentinel is for.
  //
  // What is worth guarding now is the BEHAVIOUR it was protecting: an absent
  // client must still refuse by name rather than fail against Google with a
  // message about the client id. The constant is no longer empty, so the
  // refusal is exercised by passing an empty one in.
  assert.equal(typeof WEB_CLIENT_ID, "string");
  assert.notEqual(WEB_CLIENT_ID, "", "the client id is gone again");
});

test("the silent path passes its silence all the way to Chrome", async () => {
  const identity = fakeIdentity(`${REDIRECT}#access_token=ya29.TOKEN`
    + `&scope=${encodeURIComponent(SCOPES.join(" "))}`);
  const answer = await authorize({ identity, runtime: RUNTIME, clientId: CLIENT,
                                   email: "owner@example.com", interactive: false });
  assert.equal(answer.state, "ok");
  assert.equal(identity.calls[0].interactive, false,
    "launchWebAuthFlow was allowed to open a window during a silent check");
  assert.equal(params(identity.calls[0].url).get("prompt"), "none");
});

test("Chrome refusing to open the flow is reported, not thrown at the panel", async () => {
  const identity = {
    getRedirectURL: () => REDIRECT,
    launchWebAuthFlow() { throw new Error("no window available"); },
  };
  const answer = await authorize({ identity, runtime: RUNTIME, clientId: CLIENT });
  assert.equal(answer.state, "failed");
  assert.match(answer.detail, /no window available/);
});

// ---- the id the directory is keyed on --------------------------------------

test("the account carries Google's stable id, not just its address", async () => {
  // accounts.js keys every row on this. An address is not safe to key on: people
  // change theirs and Workspace admins reassign them, so one account would
  // silently become two rows — or a renamed address would land on someone
  // else's row.
  const fetchImpl = async () => ({
    ok: true, status: 200,
    json: async () => ({ sub: "110001", name: "Muhammad", email: "owner@example.com",
                         picture: "https://lh3.googleusercontent.com/x" }),
  });
  const result = await accountFor("ya29.TOKEN", fetchImpl);
  assert.equal(result.state, "ok");
  assert.equal(result.account.id, "110001");
  assert.equal(result.account.email, "owner@example.com");
});

test("an account response without an id is still an account, with an empty one", async () => {
  // Missing optional fields were always a successful response here, and this
  // must not become the one that throws. accounts.js refuses the empty id on
  // its own side, where the decision belongs.
  const fetchImpl = async () => ({
    ok: true, status: 200, json: async () => ({ name: "Muhammad" }),
  });
  const result = await accountFor("ya29.TOKEN", fetchImpl);
  assert.equal(result.state, "ok");
  assert.equal(result.account.id, "");
});


test("the redirect goes to Google exactly as Chrome produced it", async () => {
  // THE FIX THAT WAS WRONG, kept as a test so it is not re-attempted.
  //
  // The client Google created on 2026-08-12 recorded the bare host with no
  // trailing slash, because the Console strips one when the path is empty. The
  // first fix stripped the slash in code to match. Then the owner added the
  // slashed form to the client — at which point stripping is the thing that
  // breaks it.
  //
  // Chrome's value is canonical. Nothing normalises it, and a future tidy-up
  // that "helpfully" trims it fails here.
  const fromChrome = "https://ekcgggphcfdbjgfkcmjagehfjhijeang.chromiumapp.org/";
  const identity = fakeIdentity(`${fromChrome}#access_token=ya29.T`
    + `&scope=${encodeURIComponent(SCOPES.join(" "))}`);
  identity.getRedirectURL = () => fromChrome;

  await authorize({ identity, runtime: RUNTIME, clientId: CLIENT, interactive: true });

  const asked = new URL(identity.calls[0].url);
  assert.equal(asked.searchParams.get("redirect_uri"), fromChrome,
    "the redirect was altered on the way to Google; it must be sent verbatim, "
    + "and a mismatch is fixed in the Cloud Console rather than here");
});


test("the web client is set, and it is a client id rather than a secret", async () => {
  // A client id is public — the manifest already carries one. A client SECRET
  // is not, and the JSON Google hands over contains both side by side, which is
  // exactly how one ends up pasted into the wrong constant. The implicit flow
  // uses no secret at all; anything shaped like one here is a mistake.
  assert.match(WEB_CLIENT_ID, /\.apps\.googleusercontent\.com$/,
               "WEB_CLIENT_ID is not a Google client id");
  assert.equal(WEB_CLIENT_ID.startsWith("GOCSPX-"), false,
               "that is a client SECRET, not a client id — it must never be in "
               + "the extension, and the flow this file uses needs none");
});
