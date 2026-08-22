# Chrome Web Store listing — ScrapeX 0.2.2

Draft for the owner to review, edit and paste. Every claim here is checked
against what the extension actually declares — the permissions and scopes below
are read from `extension/manifest.json`, not remembered — because a listing that
promises something the manifest does not do is the one thing a reviewer is
looking for.

**Visibility:** Unlisted · **Publish target:** Trusted testers (Decision 6).

---

## Single purpose

Chrome requires one sentence, and it is the field a reviewer reads first. A
purpose that sounds like two products is the commonest rejection.

> ScrapeX collects published product and price information from websites the
> user chooses, and stores it in a database on the user's own computer.

---

## Short description

Max 132 characters. Counted, not estimated: this one is **105**.

> Collect published prices from sites you choose into a database on your own
> computer. Nothing is uploaded.

*(A second option, **123** characters, if you prefer leading with the tracking:)*

> Track published prices from the sites you choose. Everything stays in a
> database on your own machine — nothing is uploaded.

---

## Detailed description

> **ScrapeX collects published prices into a database on your own computer.**
>
> You choose the sites. ScrapeX visits their public pages, reads the product and
> price information they publish, and keeps it in a database on your machine —
> not on anybody's server. If your computer is off, nothing runs.
>
> **What it does**
>
> - Collects published product and price information from sites you add.
> - Keeps the history, so you can see when a price changed and what it was
>   before.
> - Exports to Excel, or to a Google Sheet you choose.
> - Backs up to your own Google Drive, when you ask it to.
>
> **How it is built**
>
> ScrapeX is two halves. This extension is the panel you work in. The second
> half is **ScrapeX-Engine**, a separate program that runs on your own computer
> and does the collecting — it is what holds your database.
>
> **You download and run ScrapeX-Engine yourself.** The panel links to it and
> shows you the steps; it cannot and does not install anything, run anything, or
> update anything on your machine. It only talks to the program once you have
> installed it, and tells you plainly when the two are out of step instead of
> failing quietly.
>
> Windows only, for now. The engine needs no administrator rights.
>
> **What it does not do**
>
> - It does not send your collected data anywhere except your own Google Drive,
>   and only when you ask.
> - It contains no analytics, no telemetry and no advertising.
> - It does not sign in to any website on your behalf, and reads nothing behind
>   a login.
> - There is no account and no subscription. It is not a service.
>
> Privacy policy: https://muhammadbayoumi.github.io/mbiXsite/scrapex-privacy.html
> Support: https://muhammadbayoumi.github.io/mbiXsite/scrapex-support.html

---

## Permission justifications

One field per permission, and each has to say **why this extension cannot work
without it**. "It is needed" is what gets a listing sent back.

### `nativeMessaging`

**The one that gets read hardest**, because it is the permission that reaches
outside the browser. Be specific and do not soften it.

> ScrapeX stores data in a database on the user's own computer rather than on a
> server. A browser extension cannot write to a local database or run a crawl on
> a schedule, so the collecting is done by a separate program, ScrapeX-Engine.
>
> **THE USER RUNS THAT PROGRAM THEMSELVES.** This extension can start the
> download when the user presses Download, and it does nothing else to the file:
> it does not install it, does not execute it, and cannot update it. Running the
> downloaded file is the user's own action, taken outside the browser.
>
> Updates afterwards are the Engine's own affair, not this extension's: the
> Engine checks the published release feed, fetches an update itself, and
> verifies it against the SHA-256 the release publishes before replacing
> anything. The panel only shows what the Engine reports and asks whether to go
> ahead.
>
> Native messaging is how this panel exchanges data with that program once the
> user has installed it — the same arrangement password managers and hardware
> wallets use. Nothing is sent to any remote host through this channel: the
> other end is a program on the same machine, and the panel refuses to talk to
> it at all if its version does not match this extension's.

### `downloads`

**Added in 0.2.2, and it replaced something worse.** Before it, pressing
Download opened the release URL in a new tab and the panel let go — no progress,
no completion, no way to tell whether a 70 MB file had arrived. On a slow
connection that is a button that appears to do nothing.

> ScrapeX-Engine is a separate program the user installs on their own computer.
> When the user presses **Download engine**, this permission is what lets the
> panel start that one download, show its progress, and then reveal the finished
> file in the user's Downloads folder.
>
> It is used for exactly one file — the published ScrapeX-Engine release from the
> project's own GitHub release page — and only in response to that press. The
> panel never reads the contents of any downloaded file, never touches downloads
> it did not start, and never runs anything. Installing the Engine is the user's
> own action.

### `storage`

> Remembers the user's own settings — the sites they added, crawl pacing,
> display preferences, time zone and backup schedule — between sessions. No
> collected data is kept here; that lives in the local database.

### `sidePanel`

> The entire interface is a side panel. Without this permission there is no user
> interface at all.

### `activeTab`

> When the user presses "Test site" or adds the page they are looking at,
> ScrapeX reads the current tab's address to work out which site it is and
> whether it can be read. It is used only in response to that press, never in
> the background.

### `tabs`

> The panel is opened next to the page being worked on and needs to know which
> tab it belongs to, so the panel follows the user's tab rather than showing
> another one's state.

### `identity`

> Used only for "Sign in with Google", which the user starts. It is what obtains
> permission to write a backup to the user's own Google Drive and to export to a
> Google Sheet they choose. ScrapeX works without signing in; the sign-in buys
> Drive and Sheets and nothing else.

---

## Host permission justifications

### `http://127.0.0.1/*` and `http://localhost/*`

> ScrapeX-Engine runs on the user's own machine and serves its data over
> loopback. This is how the panel reads the database. It never leaves the
> computer.

### `https://raw.githubusercontent.com/muhammadbayoumi/mbiX-hub/*`

> Reads one small file that says which version of ScrapeX-Engine is the newest,
> so the panel can tell the user an update exists. It is a plain public file
> fetch and carries no information about the user.

### `https://oauth2.googleapis.com/revoke*`

Ending the Google session when the user presses Sign out. Without it, "sign out"
would only forget the key held in this browser and leave ScrapeX authorised in
the user's Google account — so a shared computer would keep the account
connected, and a user could never sign in as somebody else.

### `https://www.googleapis.com/oauth2/v3/*`

> The name, address and picture of the signed-in account, shown on the panel's
> Profile page. One endpoint and no more. Nothing is sent to it but the token
> Chrome already holds.

### `https://www.googleapis.com/drive/v3/*`

> Finding, listing and downloading the user's own backups. Narrowed to the Drive
> API path rather than the whole of googleapis.com. The permission behind it is
> Google's `drive.file`, which reaches only files this extension created and
> files the user hands it — it is structurally unable to read anything else in
> their Drive.

### `https://www.googleapis.com/upload/drive/v3/*`

> Sending a backup up. Drive's upload endpoint is a separate address from the
> one above, and the upload is resumable so the panel can show real progress on
> a file of tens of megabytes.

### `https://sheets.googleapis.com/v4/*`

> Writing the user's exported rows into a spreadsheet — one tab per source. The
> same `drive.file` limit applies: a spreadsheet ScrapeX created, or one the
> user chose for it, and no other. ScrapeX does **not** request Google's
> `spreadsheets` permission, which is the one that would let an app read and
> edit every spreadsheet the user owns.

---

## OAuth scope justifications

The Google consent screen asks for these separately from the store.

| scope | why |
|---|---|
| `userinfo.email` | To show which account is signed in, so the user can tell whose Drive a backup went to. |
| `userinfo.profile` | The account's name and picture, shown in the panel so the signed-in account is visible at a glance. |
| `drive.file` | To write backups to the user's own Drive. **This scope only ever sees files ScrapeX itself created** — it cannot read anything else in the user's Drive. |

**`spreadsheets` IS NOT REQUESTED AND MUST NOT BE DECLARED.** It was removed
from `extension/identity.js` before the first listing, and this table said
otherwise for long enough to matter: declaring a scope the manifest does not
request is the fastest way to fail review, and the store's own guidance is
blunt — "Requesting an unnecessary permission will result in this version being
rejected." Read the scopes off `extension/identity.js`; a table is a copy and
copies drift.

**Note for the privacy-practices form:** every scope above is NON-SENSITIVE.
`drive.file` sees only files ScrapeX created or the user hands it through the
Google Picker, so this listing needs no Google verification even if it stops
being unlisted — which is why the sensitive scope was dropped rather than
carried.

---

## Data usage disclosures

Answer these consistently with the privacy policy, which is tested against the
manifest on every build.

- **Does it collect personally identifiable information?** No — except the
  signed-in account's own name, email and picture, which are shown to the user
  and never sent anywhere.
- **Health information?** No. **Financial information?** No — ScrapeX reads
  published shop prices, not the user's own payments.
- **Authentication information?** No. ScrapeX never asks for or stores a
  password for any site.
- **Personal communications, location, web history, user activity?** No.
- **Website content?** **Yes** — the published pages of the sites the user
  explicitly adds. This is the product's purpose and must be declared.
- **Do you sell or transfer data to third parties?** No.
- **Do you use it for anything unrelated to the single purpose?** No.
- **Do you use it to determine creditworthiness or for lending?** No.

---

## Still needed from the owner

- [ ] **One screenshot, 1280×800.** The panel with real data is the honest
      choice — but check it for anything you do not want public: source keys,
      supplier names, the shape of your own price data.
- [ ] Category and language for the listing.
- [ ] The store item ID, once created — **compare it against the pinned key's
      id `ekcgggphcfdbjgfkcmjagehfjhijeang` before anything else.** If they
      differ, Google sign-in will break in the published build only.
