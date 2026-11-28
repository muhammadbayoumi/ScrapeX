// One Google operation runs on a token asked for at that moment, and a 401 is
// renewed once, where it happened (#2028).
//
// WHAT HE MET, 2026-11-28: Manage account read his Drive with the token the
// panel was handed when it opened, an hour earlier, and said "Google refused
// the token". Chrome renews a token by itself -- for whoever asks again -- and
// nothing asked. Nor did a 401 drop the refused token from Chrome's cache, so a
// token Google had stopped accepting stayed the one Chrome handed back.
//
// `googleAccess` is the one place that rule lives. drive.js and sheets.js stay
// as they are: they take a token and a `fetchImpl`, and this hands them both.
// The panel's own screens are driven end to end in
// tests/test_a_google_call_asks_for_a_fresh_token.py; these pin the rule itself.
import { test } from "node:test";
import assert from "node:assert/strict";

import { googleAccess } from "../identity.js";

const DRIVE = "https://www.googleapis.com/drive/v3/files";
const SESSION = "https://upload.example.invalid/session/1";

/** A Google that refuses `dead` tokens and records every request it is sent. */
function google({ dead = [], status = null } = {}) {
  const sent = [];
  const fetchImpl = async (url, init = {}) => {
    const auth = (init.headers && (init.headers.Authorization
                                   || init.headers.authorization)) || "";
    const token = auth.replace(/^Bearer\s+/i, "");
    sent.push({ url, token, method: init.method || "GET" });
    if (status) return new Response("{}", { status });
    if (token && dead.includes(token)) {
      return new Response(JSON.stringify({ error: { code: 401 } }), { status: 401 });
    }
    return new Response("{}", { status: 200 });
  };
  return { fetchImpl, sent };
}

/** Chrome's silent answers, in order; each call takes the next. */
function mints(...answers) {
  const asked = [];
  const mint = async () => {
    asked.push(true);
    return answers.length ? answers.shift() : { state: "authorization-required" };
  };
  return { mint, asked };
}

const ok = (token) => ({ state: "ok", token });
const bearer = (token) => ({ headers: { Authorization: `Bearer ${token}` } });

test("the token is asked for when the operation starts, not remembered", async () => {
  const { mint, asked } = mints(ok("asked-now"));
  const { fetchImpl, sent } = google();

  const access = await googleAccess({ mint, fetchImpl });
  await access.fetch(DRIVE, bearer(access.token));

  assert.equal(access.state, "ok");
  assert.equal(asked.length, 1, "one silent ask per operation, before its first request");
  assert.equal(access.token, "asked-now");
  assert.deepEqual(sent.map((s) => s.token), ["asked-now"]);
});

test("a 401 drops the refused token, asks once more, and resends that request once",
  async () => {
    const dropped = [];
    const { mint } = mints(ok("cached-dead"), ok("asked-again"));
    const { fetchImpl, sent } = google({ dead: ["cached-dead"] });

    const access = await googleAccess({
      mint, drop: async (token) => { dropped.push(token); }, fetchImpl });
    const answer = await access.fetch(DRIVE, bearer(access.token));

    assert.equal(answer.status, 200);
    assert.deepEqual(dropped, ["cached-dead"],
      "the refused token stays in Chrome's cache, and every later ask hands it back");
    assert.deepEqual(sent.map((s) => s.token), ["cached-dead", "asked-again"]);
    assert.equal(access.token, "asked-again");
  });

test("the requests after a renewal carry the new token, though the caller wrote the old one",
  async () => {
    // drive.js builds each request's header from the token it was handed when
    // the operation began. A 625 MB read is 157 requests, and every one after
    // the renewal would otherwise be refused and renewed again.
    const { mint, asked } = mints(ok("first"), ok("second"));
    const { fetchImpl, sent } = google({ dead: ["first"] });

    const access = await googleAccess({ mint, fetchImpl });
    const began = access.token;
    await access.fetch(DRIVE, bearer(began));
    await access.fetch(`${DRIVE}?page=2`, bearer(began));
    await access.fetch(`${DRIVE}?page=3`, bearer(began));

    assert.deepEqual(sent.map((s) => s.token), ["first", "second", "second", "second"]);
    assert.equal(asked.length, 2, "renewed once, not once per request");
  });

test("a request refused again after its renewal is not tried a third time", async () => {
  const { mint, asked } = mints(ok("first"), ok("also-dead"));
  const { fetchImpl, sent } = google({ dead: ["first", "also-dead"] });

  const access = await googleAccess({ mint, fetchImpl });
  const answer = await access.fetch(DRIVE, bearer(access.token));

  assert.equal(answer.status, 401, "the 401 reaches drive.js, which names it unauthorized");
  assert.equal(sent.length, 2);
  assert.equal(asked.length, 2);
});

test("when nothing silent can renew it, the 401 stands and the refusal is kept", async () => {
  // Only now is he asked to sign in again, and the panel needs to know why.
  const { mint } = mints(ok("first"), { state: "authorization-required",
                                        detail: "Google access isn’t currently granted." });
  const { fetchImpl, sent } = google({ dead: ["first"] });

  const access = await googleAccess({ mint, fetchImpl });
  const answer = await access.fetch(DRIVE, bearer(access.token));

  assert.equal(answer.status, 401);
  assert.equal(sent.length, 1, "nothing to resend with");
  assert.equal(access.refusal.state, "authorization-required");
});

test("an operation whose first silent ask fails never reaches Google", async () => {
  const { mint } = mints({ state: "authorization-required" });
  const { fetchImpl, sent } = google();

  const access = await googleAccess({ mint, fetchImpl });

  assert.equal(access.state, "authorization-required");
  assert.equal(access.fetch, undefined, "there is no token to send");
  assert.equal(sent.length, 0);
});

test("a request with no bearer is sent as it is, and never renewed", async () => {
  // A resumable upload's chunks go to the session address and carry no token.
  const { mint, asked } = mints(ok("first"), ok("second"));
  const { fetchImpl, sent } = google({ status: 401 });

  const access = await googleAccess({ mint, fetchImpl });
  const answer = await access.fetch(SESSION, { method: "PUT", headers: {} });

  assert.equal(answer.status, 401);
  assert.deepEqual(sent.map((s) => s.token), [""]);
  assert.equal(asked.length, 1, "no renewal for a request that sent no token");
});

for (const status of [403, 404, 429, 500]) {
  test(`a ${status} is Google's answer, not a dead token, and is not renewed`, async () => {
    const { mint, asked } = mints(ok("first"), ok("second"));
    const { fetchImpl, sent } = google({ status });

    const access = await googleAccess({ mint, fetchImpl });
    const answer = await access.fetch(DRIVE, bearer(access.token));

    assert.equal(answer.status, status);
    assert.equal(sent.length, 1);
    assert.equal(asked.length, 1);
  });
}
