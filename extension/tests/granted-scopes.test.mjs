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

import { SCOPES, ensureScope, missingScopes, readTokenResult, revokeToken }
  from "../identity.js";

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
  assert.match(result.detail, /backups to Drive will fail/,
    `the message names the scope instead of the consequence: ${result.detail}`);
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
});

test("signing out with no token asks Google nothing", async () => {
  const fake = chromeWithRevoke(200);
  const result = await revokeToken("", { identity: fake.identity, fetchImpl: fake.fetchImpl });
  assert.equal(result.revoked, false);
  assert.equal(fake.calls.length, 0);
});
