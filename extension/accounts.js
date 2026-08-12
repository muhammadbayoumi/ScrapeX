// The accounts this browser REMEMBERS, and nothing else.
//
// PLATFORM-PLAN, the owner's ruling of 2026-08-05, stands unchanged: «الإضافة
// تملكه وتُعيره للمحرّك» — the extension owns the token and lends it to the
// engine, and NOTHING is written to disk here. Multi-account did not require
// breaking that. What is stored is a directory: who this browser has seen, so
// the panel can offer them by name. A token for any of them is minted at the
// moment it is needed and lives in memory only (see identity.js).
//
// The owner ruled on this directly on 2026-08-11, choosing the variant that
// keeps the 2026-08-05 ruling over the one that would have stored refresh
// tokens: «الصيغة الثالثة، بلا تخزين اعتمادات».
//
// WHY A DIRECTORY IS NOT A CREDENTIAL. Everything here — the account id, the
// display name, the address, the photo URL — is what Google already hands to
// any page the person is signed into, and what the panel already paints on
// screen. None of it authorises anything. `sanitiseAccount` below is what keeps
// that true as the file ages: it copies the four fields it knows by name and
// drops the rest, so a caller that one day passes a whole token response cannot
// quietly persist the token inside it.

/** The one storage key. Versioned, because the shape may move and a reader that
 *  meets an older shape must know rather than guess. */
export const ACCOUNTS_KEY = "scrapex-accounts-v1";

/** The fields a remembered account may carry. THIS LIST IS THE RULE — see the
 *  file comment. Adding to it is a decision about what lands on disk. */
const REMEMBERED_FIELDS = ["id", "name", "email", "picture"];

/** Copy the known fields, drop everything else.
 *
 * Returns null for anything that cannot be an account. An entry with no `id` is
 * not an account: the id is what a switch, a removal and a token request all
 * name, and a list holding one without would offer a row nothing can act on.
 */
export function sanitiseAccount(candidate) {
  if (!candidate || typeof candidate !== "object") return null;
  const id = typeof candidate.id === "string" ? candidate.id.trim() : "";
  if (!id) return null;
  const account = { id };
  for (const field of REMEMBERED_FIELDS) {
    if (field === "id") continue;
    const value = candidate[field];
    account[field] = typeof value === "string" ? value : "";
  }
  return account;
}

/** Read the directory, and never throw at a caller because storage was odd.
 *
 * A corrupt or half-written record reads as an EMPTY directory, not as an
 * error. The panel's job when it knows nobody is to offer sign-in, which is
 * exactly what it does on a fresh machine — so the recovery path is one the
 * product already has, rather than an error state built for this one case.
 */
export async function readAccounts({ storage = chrome.storage.local } = {}) {
  let record;
  try {
    const held = await storage.get(ACCOUNTS_KEY);
    record = held && held[ACCOUNTS_KEY];
  } catch (_) {
    record = null;
  }
  const rawList = record && Array.isArray(record.accounts) ? record.accounts : [];
  const accounts = [];
  const seen = new Set();
  for (const entry of rawList) {
    const account = sanitiseAccount(entry);
    // Duplicates are dropped rather than merged: two rows for one person is a
    // bug the person can see, and the later write is the fresher truth.
    if (!account || seen.has(account.id)) continue;
    seen.add(account.id);
    accounts.push(account);
  }
  const claimed = record && typeof record.currentId === "string" ? record.currentId : "";
  // A current id naming nobody is not carried forward. It would make the panel
  // paint a "current account" header for a row that is not in the list.
  const currentId = seen.has(claimed) ? claimed : "";
  return { accounts, currentId };
}

async function write(storage, accounts, currentId) {
  await storage.set({ [ACCOUNTS_KEY]: { accounts, currentId } });
  return { accounts, currentId };
}

/** Add an account, or refresh what is known about one already listed.
 *
 * The remembered entry is REPLACED, not merged: a name or a photo that changed
 * at Google is the truth, and a merge would keep the stale half of it. Position
 * in the list is kept, so the row a person is looking at does not jump when
 * their photo updates.
 *
 * Remembering an account also makes it current. Every path that reaches here —
 * first sign-in, adding a second account, re-authorising one that had lapsed —
 * is a path where the person just proved which account they meant.
 */
export async function rememberAccount(candidate, { storage = chrome.storage.local } = {}) {
  const account = sanitiseAccount(candidate);
  if (!account) return readAccounts({ storage });
  const { accounts } = await readAccounts({ storage });
  const at = accounts.findIndex((held) => held.id === account.id);
  if (at === -1) accounts.push(account);
  else accounts[at] = account;
  return write(storage, accounts, account.id);
}

/** Drop an account from the directory.
 *
 * This erases NOTHING but the row. No token is held to revoke, no crawl data is
 * touched, and the Google account is untouched — which is why the panel's copy
 * for it must not say "delete account". Ending a SESSION is a different verb and
 * a different function: see identity.js.
 */
export async function forgetAccount(id, { storage = chrome.storage.local } = {}) {
  const { accounts, currentId } = await readAccounts({ storage });
  const kept = accounts.filter((account) => account.id !== id);
  if (kept.length === accounts.length) return { accounts, currentId };
  // Losing the current account does not silently promote another one. Which
  // account you are acting as is a thing the person decides; guessing it here
  // would switch them somewhere they never asked to be.
  return write(storage, kept, currentId === id ? "" : currentId);
}

/** Point at a different remembered account.
 *
 * An id that is not in the directory is refused rather than stored, so the
 * record cannot come to name a row that does not exist.
 */
export async function setCurrentAccount(id, { storage = chrome.storage.local } = {}) {
  const { accounts, currentId } = await readAccounts({ storage });
  if (!accounts.some((account) => account.id === id)) {
    return { accounts, currentId };
  }
  return write(storage, accounts, id);
}

/** Stop acting as anyone, and keep everybody listed.
 *
 * THIS IS WHAT SIGNING OUT MEANS HERE, and it is not `forgetAccount`. Ending a
 * session leaves the account in the directory as a row that reads "Signed out"
 * with a Sign in beside it; that row is how a person comes back without hunting
 * for the address again. Removing it is a different verb, a different button,
 * and the only one that erases anything.
 *
 * No account is promoted to take its place. Which account the panel acts as is
 * the person's decision — see forgetAccount for the same reasoning.
 */
export async function clearCurrentAccount({ storage = chrome.storage.local } = {}) {
  const { accounts, currentId } = await readAccounts({ storage });
  if (!currentId) return { accounts, currentId };
  return write(storage, accounts, "");
}

/** The account the panel is acting as, or null when it is acting as nobody. */
export function currentAccount({ accounts, currentId }) {
  if (!currentId) return null;
  return accounts.find((account) => account.id === currentId) || null;
}

/** Everyone except the current account, in list order. */
export function otherAccounts({ accounts, currentId }) {
  return accounts.filter((account) => account.id !== currentId);
}
