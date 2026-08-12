// The directory of remembered accounts, and the one thing it must never hold.
//
// Multi-account arrived on 2026-08-11 WITHOUT breaking the owner's ruling of
// 2026-08-05 that nothing is written to disk. The account list is a directory —
// names and addresses the panel already paints — and the token for any of them
// is minted when needed and kept in memory. The first test below is that ruling
// written as an assertion: it is the one failure here that is not a bug but a
// broken promise.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ACCOUNTS_KEY, clearCurrentAccount, currentAccount, forgetAccount,
  otherAccounts, readAccounts, rememberAccount, sanitiseAccount,
  setCurrentAccount,
} from "../accounts.js";

/** A chrome.storage.local that keeps what it is given, and can be made to fail. */
function fakeStorage(seed = undefined) {
  const held = seed === undefined ? {} : { [ACCOUNTS_KEY]: seed };
  return {
    writes: 0,
    failGet: false,
    async get(key) {
      if (this.failGet) throw new Error("storage is unavailable");
      return key in held ? { [key]: held[key] } : {};
    },
    async set(patch) {
      this.writes += 1;
      Object.assign(held, patch);
    },
    raw: () => held[ACCOUNTS_KEY],
  };
}

const OWNER = { id: "1001", name: "Muhammad", email: "owner@example.com",
                picture: "https://lh3.googleusercontent.com/owner" };
const SECOND = { id: "1002", name: "MBi", email: "mbi@example.com", picture: "" };

// ---- the ruling ------------------------------------------------------------

test("a token handed in with an account never reaches storage", async () => {
  // The realistic accident: a caller passes the whole thing it just received
  // from Google — profile fields AND credentials in one object — because that
  // is the object it happens to be holding. sanitiseAccount copies the four
  // fields it knows BY NAME, so this cannot become a credential store by
  // someone being careless one afternoon.
  const storage = fakeStorage();
  await rememberAccount({
    ...OWNER,
    access_token: "ya29.SECRET", refresh_token: "1//SECRET",
    id_token: "eyJSECRET", expires_in: 3599,
  }, { storage });

  const written = JSON.stringify(storage.raw());
  assert.doesNotMatch(written, /SECRET/,
    `a credential reached disk: ${written}`);
  assert.deepEqual(Object.keys(storage.raw().accounts[0]).sort(),
    ["email", "id", "name", "picture"],
    "an unknown field survived the copy, so the field list is no longer the rule");
});

test("sanitiseAccount refuses anything that cannot be acted on", () => {
  // An id is what a switch, a removal and a token request all name. A row
  // without one is a row every button on it would fail against.
  assert.equal(sanitiseAccount(null), null);
  assert.equal(sanitiseAccount("1001"), null);
  assert.equal(sanitiseAccount({ name: "No id" }), null);
  assert.equal(sanitiseAccount({ id: "   " }), null, "whitespace is not an id");
  assert.deepEqual(sanitiseAccount({ id: " 1001 " }).id, "1001");
  // Missing optional fields are still an account: Google may return no photo.
  assert.deepEqual(sanitiseAccount({ id: "1001" }),
    { id: "1001", name: "", email: "", picture: "" });
});

// ---- reading ---------------------------------------------------------------

test("a browser that has seen nobody reads as an empty directory", async () => {
  const held = await readAccounts({ storage: fakeStorage() });
  assert.deepEqual(held, { accounts: [], currentId: "" });
});

test("storage that throws reads as empty rather than throwing at the panel", async () => {
  // The panel's job when it knows nobody is to offer sign-in — a path the
  // product already has. Turning a storage fault into an exception would take
  // down renderAccount instead, and the person would meet a blank card.
  const storage = fakeStorage();
  storage.failGet = true;
  assert.deepEqual(await readAccounts({ storage }),
    { accounts: [], currentId: "" });
});

test("a half-written record does not become half a directory", async () => {
  const storage = fakeStorage({ accounts: "not-a-list", currentId: 7 });
  assert.deepEqual(await readAccounts({ storage }),
    { accounts: [], currentId: "" });
});

test("entries that are not accounts are dropped, and duplicates with them", async () => {
  const storage = fakeStorage({
    accounts: [OWNER, null, { name: "no id" }, { ...OWNER, name: "stale copy" }, SECOND],
    currentId: OWNER.id,
  });
  const held = await readAccounts({ storage });
  assert.deepEqual(held.accounts.map((a) => a.id), [OWNER.id, SECOND.id]);
  assert.equal(held.accounts[0].name, "Muhammad",
    "the later duplicate won, so the list order is not stable under a re-read");
});

test("a current id naming nobody is not carried forward", async () => {
  // Otherwise the panel paints a current-account header for a row that is not
  // in the list — the shape of failure this project keeps meeting: a partial
  // state displayed as a complete one.
  const storage = fakeStorage({ accounts: [OWNER], currentId: "9999" });
  assert.equal((await readAccounts({ storage })).currentId, "");
});

// ---- writing ---------------------------------------------------------------

test("remembering an account adds it and makes it current", async () => {
  const storage = fakeStorage();
  const held = await rememberAccount(OWNER, { storage });
  assert.deepEqual(held.accounts.map((a) => a.id), [OWNER.id]);
  assert.equal(held.currentId, OWNER.id);
});

test("remembering again replaces the entry and keeps its place in the list", async () => {
  // A name or a photo that changed at Google is the truth; a merge would keep
  // the stale half. The POSITION is kept so the row someone is looking at does
  // not jump while they are looking at it.
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await rememberAccount(SECOND, { storage });
  const held = await rememberAccount({ ...OWNER, name: "Muhammad Bayoumi", picture: "" },
                                     { storage });

  assert.deepEqual(held.accounts.map((a) => a.id), [OWNER.id, SECOND.id],
    "the refreshed account moved instead of staying where it was");
  assert.equal(held.accounts[0].name, "Muhammad Bayoumi");
  assert.equal(held.accounts[0].picture, "",
    "the old photo survived a replace, so this is a merge and not a replace");
  assert.equal(held.currentId, OWNER.id, "re-authorising did not make it current");
});

test("an account that cannot be acted on is not remembered", async () => {
  const storage = fakeStorage();
  const held = await rememberAccount({ name: "no id" }, { storage });
  assert.deepEqual(held, { accounts: [], currentId: "" });
  assert.equal(storage.writes, 0, "storage was written for a row nothing can act on");
});

// ---- forgetting ------------------------------------------------------------

test("forgetting a row removes it and promotes nobody", async () => {
  // Which account you are acting as is the person's decision. Promoting the
  // next one in the list would move them somewhere they never asked to be, and
  // the panel would look signed in as someone they did not pick.
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await rememberAccount(SECOND, { storage });
  await setCurrentAccount(OWNER.id, { storage });

  const held = await forgetAccount(OWNER.id, { storage });
  assert.deepEqual(held.accounts.map((a) => a.id), [SECOND.id]);
  assert.equal(held.currentId, "", "forgetting the current account switched us to another one");
});

test("forgetting a row that is not current leaves the current one alone", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await rememberAccount(SECOND, { storage });

  const held = await forgetAccount(OWNER.id, { storage });
  assert.equal(held.currentId, SECOND.id);
});

test("forgetting someone who was never here writes nothing", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  const before = storage.writes;
  await forgetAccount("9999", { storage });
  assert.equal(storage.writes, before);
});

// ---- signing out, which is not forgetting ----------------------------------

test("signing out keeps the account listed and stops acting as it", async () => {
  // The whole difference between the two destructive-looking verbs. A signed-out
  // account stays as a row someone can come back through; only Remove erases.
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await rememberAccount(SECOND, { storage });

  const held = await clearCurrentAccount({ storage });
  assert.deepEqual(held.accounts.map((a) => a.id), [OWNER.id, SECOND.id],
    "signing out dropped a row that should have stayed");
  assert.equal(held.currentId, "");
});

test("signing out when acting as nobody writes nothing", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await clearCurrentAccount({ storage });
  const before = storage.writes;
  await clearCurrentAccount({ storage });
  assert.equal(storage.writes, before);
});

test("signing back in makes the same account current again", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await clearCurrentAccount({ storage });
  const held = await rememberAccount(OWNER, { storage });
  assert.equal(held.currentId, OWNER.id);
  assert.equal(held.accounts.length, 1, "coming back created a second row");
});

// ---- switching -------------------------------------------------------------

test("switching to a remembered account moves the current id", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await rememberAccount(SECOND, { storage });
  const held = await setCurrentAccount(OWNER.id, { storage });
  assert.equal(held.currentId, OWNER.id);
});

test("switching to someone who is not in the directory is refused", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  const held = await setCurrentAccount("9999", { storage });
  assert.equal(held.currentId, OWNER.id,
    "the record now names a row the panel cannot show");
});

// ---- reading the shape the card needs --------------------------------------

test("the card can name the current account and everyone else", async () => {
  const storage = fakeStorage();
  await rememberAccount(OWNER, { storage });
  await rememberAccount(SECOND, { storage });
  const held = await readAccounts({ storage });

  assert.equal(currentAccount(held).id, SECOND.id);
  assert.deepEqual(otherAccounts(held).map((a) => a.id), [OWNER.id]);
});

test("acting as nobody is a state the card can ask about", async () => {
  const held = { accounts: [OWNER], currentId: "" };
  assert.equal(currentAccount(held), null);
  assert.deepEqual(otherAccounts(held).map((a) => a.id), [OWNER.id],
    "with no current account every row is an 'other' row");
});
