# ScrapeX — Privacy Policy

*Last updated: 6 August 2026*

ScrapeX is a Chrome extension and a companion program, **ScrapeX-Engine**, that
run on your own computer. This policy describes every piece of data either of
them touches, and it is short because there is not much to describe.

---

## The short version

**ScrapeX has no servers.** There is no ScrapeX account, no ScrapeX database in
the cloud, and nowhere for your data to be sent to us — because there is no
"us" to send it to. Everything the extension collects is written to a file on
your own machine, and the only place it ever travels to is **your own Google
Drive**, when you ask for a backup.

**We collect nothing.** Not analytics, not crash reports, not usage counts, not
your email address. The extension contains no telemetry of any kind.

---

## What is stored, and where

| What | Where it lives | Who can read it |
|---|---|---|
| The pages and prices you collect | A SQLite database in your user folder | You |
| Your settings and preferences | The same database | You |
| Backups you ask for | **Your** Google Drive, in a folder ScrapeX creates | You |
| Your Google sign-in token | Held by **Chrome**, not by ScrapeX | Chrome, and Google |

Nothing in that table leaves your computer unless you press a button that says
it will.

---

## Google sign-in, and what it is for

Signing in with Google is **optional**. ScrapeX works without it; you simply
cannot back up to Drive or write to a Google Sheet until you do.

When you sign in, Chrome — not ScrapeX — obtains and holds the access token.
ScrapeX asks Chrome for it when it needs to make a request and never writes it
to disk. Signing out, or removing ScrapeX's access from your
[Google Account permissions page](https://myaccount.google.com/permissions),
revokes it immediately.

### The permissions ScrapeX asks for, and why each one

| Permission | Why |
|---|---|
| `userinfo.email`, `userinfo.profile` | To show which account is signed in — your name, address and picture, on the panel's own Profile page. Nothing is stored and nothing is sent anywhere. |
| `drive.file` | To create and update **only the files ScrapeX itself creates**. Google enforces this per file: ScrapeX is structurally unable to read the rest of your Drive, whether or not it wanted to. |
| `spreadsheets` | To write your collected data into a Google Sheet — either one ScrapeX created, or one you point it at yourself. |

ScrapeX never asks for full Drive access, never reads your mail, and never
touches a file it did not create or that you did not explicitly hand it.

---

## What ScrapeX does on the web

The engine fetches the public web pages of the sites **you** add, in order to
read the information you asked it to collect. It identifies itself in its
request headers, honours each site's requested crawl delay unless you change
that setting, and does not attempt to sign in to any site or read anything
behind a login.

### Every other address ScrapeX contacts

Besides the sites you add, the extension can reach exactly two hosts, and only
these two:

| Host | What for |
|---|---|
| `api.github.com` | Asking whether a newer engine has been published. The request carries no information about you at all. |
| `www.googleapis.com` | Google's own endpoints — the name and picture of the signed-in account, and Drive when you back up. Nothing is sent here unless you have signed in, and nothing beyond what the permissions above describe. |

The engine itself talks to the sites you added, and to `127.0.0.1` — which is
your own computer.

---

## What ScrapeX never does

- It does not send your collected data anywhere except your own Google Drive,
  and only when you ask.
- It does not report anything about you, your machine, or your usage to anyone.
- It does not sell, share, or transfer data to any third party. There is no
  third party.
- It does not use your data to train anything.
- It does not include advertising or trackers of any kind.

---

## Deleting your data

Because everything is on your own machine, deleting it is entirely in your
hands:

1. **The collected data** — ScrapeX → Settings → Storage → *Start fresh*, or
   simply delete the database folder. ScrapeX will tell you exactly where it is.
2. **Backups in Drive** — delete the *ScrapeX backups* folder from your Google
   Drive like any other folder.
3. **Google access** — remove ScrapeX from your
   [Google Account permissions](https://myaccount.google.com/permissions).
4. **The extension itself** — remove it from `chrome://extensions`. The engine
   is removed from Windows' *Apps & features* like any other program.

Nothing survives those four steps, because there is nowhere else for anything
to be.

---

## Children

ScrapeX is a tool for collecting and comparing published business data. It is
not directed at children and collects nothing about anyone who uses it.

---

## Changes to this policy

If this policy changes, the new version replaces this page and the date at the
top changes with it. Every version is public at
[github.com/muhammadbayoumi/mbiXsite](https://github.com/muhammadbayoumi/mbiXsite),
including its full history.

---

## Contact

Questions, problems and requests: see [Support](support.md).
