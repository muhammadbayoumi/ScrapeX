// Google lets a person say yes to one thing and no to another, and the panel
// used to be unable to tell.
//
// The consent screen puts `drive.file` behind its own checkbox, UNTICKED, on a
// second page. So the ordinary way to sign in is to tick nothing — Chrome hands
// back a perfectly valid token carrying two scopes instead of three, and every
// screen said "signed in" while the thing that needed the third scope was
// already doomed. The owner met this exact screen on 2026-08-10.
//
// Two behaviours are pinned here: the panel can SEE a partial grant, and it can
// ASK AGAIN when something actually needs the missing scope.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  SCOPES, SIGNIN_WORDS, ensureScope, fullText, getToken, missingScopes, readTokenResult,
  revokeToken, signsIn,
} from "../identity.js";

const DRIVE = "https://www.googleapis.com/auth/drive.file";
const EVERYTHING = [...SCOPES];
const WITHOUT_DRIVE = SCOPES.filter((scope) => scope !== DRIVE);

// ---- seeing it -------------------------------------------------------------

test("a full grant is not reported as partial", () => {
  const result = readTokenResult("tok", null, EVERYTHING);
  assert.equal(result.state, "ok");
  assert.equal(result.missing, undefined);
});

test("a grant missing Drive is reported, and named by what it costs", () => {
  const result = readTokenResult("tok", null, WITHOUT_DRIVE);

  assert.equal(result.state, "partial");
  assert.deepEqual(result.missing, [DRIVE]);
  // What happened, then what to do (#1544): never the scope string, which means
  // nothing to the person reading it.
  assert.equal(result.title, SIGNIN_WORDS.driveTitle);
  assert.equal(result.detail, SIGNIN_WORDS.driveDetail);
  assert.doesNotMatch(fullText(result), /drive\.file|googleapis/,
    `a scope URL reached the copy: ${fullText(result)}`);
  assert.equal(result.token, "tok", "the token is still usable for what WAS granted");
});

test("a browser that cannot report scopes is not read as a refusal", () => {
  // Chrome only began passing grantedScopes in MV3. `undefined` means "this
  // browser cannot tell us", and turning that into "Drive was refused" would
  // put a false warning in front of every user on an older build — worse than
  // the silence it replaces.
  const result = readTokenResult("tok", null, undefined);

  assert.equal(result.state, "ok");
  assert.equal(missingScopes(undefined), null);
});

test("a failure is still a failure, whatever the scopes say", () => {
  const result = readTokenResult(undefined, { message: "bad client id" }, EVERYTHING);
  assert.equal(result.state, "misconfigured");
});

test("a Chrome with no Google account is not read as a failure", () => {
  // WHY THIS IS NOT `failed`. The panel shows `failed` even on the silent check
  // it runs on every open, so a browser nobody has signed into met the panel
  // with Chrome's raw error string printed across it — having pressed nothing.
  // A profile with no account is the ordinary first state, not a fault.
  const result = readTokenResult(
    undefined, { message: "The user is not signed in." }, EVERYTHING);

  assert.equal(result.state, "no-chrome-account");
  assert.doesNotMatch(fullText(result), /user is not signed in/i,
    `Chrome's raw message reached the copy: ${fullText(result)}`);
  // What Chrome said and no more (#1544): "not signed in to Google", not "has no
  // account", which the message does not prove.
  assert.equal(result.title, SIGNIN_WORDS.noChromeAccountTitle);
  assert.equal(result.detail, SIGNIN_WORDS.noChromeAccountDetail);
});

test("an unexplained refusal is still reported, and still carries Chrome's words", () => {
  // THE OTHER HALF OF THE FIX, and the reason it is one branch and not a
  // deletion: `failed` is visible on the silent check ON PURPOSE (#152), so a
  // panel that cannot check the account says why instead of sitting blank.
  // Narrowing one known message must not buy that silence back.
  const result = readTokenResult(
    undefined, { message: "Something Chrome has never said before." }, EVERYTHING);

  assert.equal(result.state, "failed");
  assert.equal(result.detail, "Something Chrome has never said before.");
});

test("a grant without Drive is not a sign-in (#858, his option a)", () => {
  // Every feature sign-in unlocks needs drive.file, so a grant without it unlocks
  // nothing. One rule decides it, for the sign-in path, the switcher and the chooser.
  assert.equal(signsIn(readTokenResult("tok", null, WITHOUT_DRIVE)), false);
  assert.equal(signsIn(readTokenResult("tok", null, EVERYTHING)), true);
  assert.equal(signsIn(readTokenResult("tok", null, undefined)), true,
    "a browser that cannot report scopes is not refused");
  assert.equal(signsIn({ state: "ok" }), false, "an ok with no token signs nobody in");
  assert.equal(signsIn(null), false);
});

test("a slot with no title of its own still says what failed", () => {
  assert.equal(fullText({ title: "Drive access was not granted", detail: "Sign in again." }),
               "Drive access was not granted. Sign in again.");
  assert.equal(fullText({ detail: "Google sign-in did not finish. Nothing changed." }),
               "Google sign-in did not finish. Nothing changed.");
  assert.equal(fullText(null), "");
});

test("offline is read from Chrome's own words, and only from them", () => {
  // Chromium: identity_constants.h kAuthFailure "OAuth2 request failed: " followed by
  // google_service_auth_error.cc "Connection failed (%d).".
  const offline = readTokenResult(
    undefined, { message: "OAuth2 request failed: Connection failed (-106)." }, EVERYTHING);
  assert.equal(offline.state, "offline");
  assert.equal(offline.detail, SIGNIN_WORDS.offline);
  // A message no branch reads stays Chrome's, whatever the network does (#857): an
  // "offline" read from anything else would be a branch broader than its case.
  const other = readTokenResult(
    undefined, { message: "The user turned off browser signin" }, EVERYTHING);
  assert.equal(other.state, "failed");
  assert.equal(other.detail, "The user turned off browser signin");
  assert.equal(other.title, SIGNIN_WORDS.checkFailedTitle);
});

test("a refusal and Chrome's network cancel are read alike, and claim no cause", () => {
  // "The user did not approve access." covers a closed window and a refusal; and
  // `/canceled/` also catches "OAuth2 request failed: Request canceled." (#857).
  for (const message of ["The user did not approve access.",
                         "OAuth2 request failed: Request canceled."]) {
    const result = readTokenResult(undefined, { message }, EVERYTHING);
    assert.equal(result.state, "declined", message);
    assert.equal(result.detail, SIGNIN_WORDS.declined);
    assert.doesNotMatch(result.detail, /closed|refused/, "the words claim a cause");
  }
});

test("Chrome's answer after the deadline is still delivered (#2005)", async () => {
  // #152 dropped it, and the panel said the check had not finished while Chrome
  // had finished, holding a valid token his next press then received at once.
  let late = null;
  const identity = {
    getAuthToken(_options, done) { setTimeout(() => done("tok", EVERYTHING), 40); },
  };
  const first = await getToken({ interactive: false, identity, runtime: { lastError: null },
                                 timeoutMs: 5, onLate: (answer) => { late = answer; } });
  assert.equal(first.state, "timeout");
  assert.equal(late, null, "the late answer was delivered before it arrived");
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(late && late.state, "ok", "Chrome's late token was dropped");
  assert.equal(late.token, "tok");
});

test("an answer that comes in time is not delivered twice", async () => {
  let late = null;
  const identity = { getAuthToken(_options, done) { done("tok", EVERYTHING); } };
  const first = await getToken({ interactive: false, identity, runtime: { lastError: null },
                                 timeoutMs: 50, onLate: (answer) => { late = answer; } });
  assert.equal(first.state, "ok");
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(late, null);
});

// ---- asking again ----------------------------------------------------------

function chromeThatGrants(first, second) {
  const removed = [];
  let call = 0;
  return {
    removed,
    prompts: () => call,
    identity: {
      getAuthToken(_options, done) {
        call += 1;
        done("tok" + call, call === 1 ? first : second);
      },
      removeCachedAuthToken({ token }, done) {
        removed.push(token);
        done();
      },
    },
    runtime: { lastError: null },
  };
}

test("asking for a missing scope drops the cached token first", async () => {
  // WITHOUT THIS THE PROMPT NEVER APPEARS. Chrome answers from its cache, so a
  // second getAuthToken returns the same partial token and the consent screen
  // is never shown — the caller then reports a refusal nobody was asked about.
  const fake = chromeThatGrants(WITHOUT_DRIVE, EVERYTHING);

  const result = await ensureScope(DRIVE,
    { identity: fake.identity, runtime: fake.runtime });

  assert.equal(result.state, "ok");
  assert.deepEqual(fake.removed, ["tok1"],
    "the partial token was not dropped, so Chrome answered from cache");
  assert.equal(fake.prompts(), 2);
});

test("a scope already granted is not re-requested", async () => {
  const fake = chromeThatGrants(EVERYTHING, EVERYTHING);

  const result = await ensureScope(DRIVE,
    { identity: fake.identity, runtime: fake.runtime });

  assert.equal(result.state, "ok");
  assert.equal(fake.prompts(), 1, "the user was asked about a scope he had already given");
  assert.deepEqual(fake.removed, []);
});

test("refusing twice is an answer, and is not asked a third time", async () => {
  const fake = chromeThatGrants(WITHOUT_DRIVE, WITHOUT_DRIVE);

  const result = await ensureScope(DRIVE,
    { identity: fake.identity, runtime: fake.runtime });

  assert.equal(result.state, "refused",
    "a second refusal is reported as an answer, not retried for ever");
  assert.equal(fake.prompts(), 2, "the user was asked more than twice");
});

test("a scope nobody asked about does not force a prompt", async () => {
  // Something else is missing, but not the thing this caller needs. Prompting
  // here would interrupt a person for a permission his action does not use.
  const fake = chromeThatGrants([SCOPES[0]], EVERYTHING);

  const result = await ensureScope(SCOPES[0],
    { identity: fake.identity, runtime: fake.runtime });

  assert.equal(result.state, "ok");
  assert.equal(fake.prompts(), 1);
});

// ---- signing out has to mean it ---------------------------------------------

function chromeWithRevoke(answer) {
  const removed = [];
  const calls = [];
  return {
    removed, calls,
    identity: {
      removeCachedAuthToken({ token }, done) { removed.push(token); done(); },
    },
    fetchImpl: async (url, options) => {
      calls.push({ url, body: options && options.body });
      if (answer instanceof Error) throw answer;
      return { ok: answer === 200, status: answer };
    },
  };
}

test("signing out ends the grant at Google, not just the copy here", async () => {
  // THE DEFECT THE OWNER FOUND BY FEEL: sign out, sign in, and it was instant.
  // That is what a grant that never ended looks like from outside — and it also
  // means a partial consent can never be repaired, because Google keeps handing
  // back the scopes it remembers.
  const fake = chromeWithRevoke(200);

  const result = await revokeToken("tok",
    { identity: fake.identity, fetchImpl: fake.fetchImpl });

  assert.equal(result.revoked, true);
  assert.equal(fake.calls.length, 1, "Google was never asked to revoke anything");
  assert.match(fake.calls[0].url, /oauth2\.googleapis\.com\/revoke/);
  assert.match(fake.calls[0].body, /token=tok/);
  assert.deepEqual(fake.removed, ["tok"], "Chrome is still holding the token");
});

test("a token Google already considers invalid is a success, not a failure", () => {
  // 400 means "there is nothing to revoke". The END STATE is what the owner
  // cares about, and it is the same one.
  return revokeToken("tok", chromeWithRevoke(400)).then((result) => {
    assert.equal(result.state, "ok");
  });
});

test("a revoke that could not be sent still drops the local token, and says so", async () => {
  // Leaving Chrome holding a token whose grant we tried to end is the worst of
  // both: the panel looks signed out and the browser still carries credentials.
  const fake = chromeWithRevoke(new Error("offline"));

  const result = await revokeToken("tok",
    { identity: fake.identity, fetchImpl: fake.fetchImpl });

  assert.equal(result.state, "local-only");
  assert.deepEqual(fake.removed, ["tok"], "the local token survived a failed revoke");
  assert.match(result.detail, /Could not reach Google/);
  // The grant stands, so that is the title: not "signed out on this computer", which
  // the next open would undo (#1544).
  assert.equal(result.title, SIGNIN_WORDS.revokeFailedTitle);
});

test("signing out with no token asks Google nothing", async () => {
  const fake = chromeWithRevoke(200);
  const result = await revokeToken("", { identity: fake.identity, fetchImpl: fake.fetchImpl });
  assert.equal(result.revoked, false);
  assert.equal(fake.calls.length, 0);
});
