# ScrapeX — Support

*Last updated: 6 August 2026*

ScrapeX is maintained by **Muhammad Bayoumi**.

---

## Getting help

**Open an issue:**
[github.com/muhammadbayoumi/ScrapeX/issues](https://github.com/muhammadbayoumi/ScrapeX/issues)

That is the fastest route and the one worth using first: an issue is public, so
the answer helps whoever hits the same thing next, and it cannot be lost in a
mailbox.

---

## What to include, and why

ScrapeX runs entirely on your own machine, so nobody can look at your data to
work out what went wrong. Four things make the difference between a diagnosis
and a guess:

| | Where to find it |
|---|---|
| **The extension's version** | ScrapeX → Settings → About |
| **The engine's version** | ScrapeX → Engine → *Installed version* |
| **What you pressed, and what happened** | In your own words. "It did nothing" is a real and useful report. |
| **The message, exactly** | Copy the words. A paraphrase of an error is a different error. |

If the panel showed a card naming two version numbers, include both of them —
that card exists precisely so a report can carry the pair.

**Do not send your database or a backup.** They contain everything you have
collected, and nothing in a support conversation needs them. If a specific row
is the problem, one row is enough.

---

## Before you write

Three problems account for most of what goes wrong, and each says what it is on
screen:

**"The engine is not running."** ScrapeX has two halves. The panel is in Chrome;
the engine is a program on your computer. Start it from Settings, and the panel
will say so within a few seconds.

**"The extension and the engine speak different protocol versions."** One of the
two updated and the other did not. The card names which is behind and what to
do about it — Chrome updates the extension on its own schedule; the engine is
installed from its GitHub release.

**"Sign-in was closed before it finished."** Nothing changed and nothing broke.
Press *Continue with Google* again.

---

## What ScrapeX is, and what it is not

It collects published information from web pages you nominate, keeps it in a
database on your machine, and can back that up to your own Google Drive and
export it to Excel or Google Sheets.

It is **not** a service, and there is no account. If your machine is off,
nothing runs. That is by design: your data never sits on somebody else's
computer.

---

## Reporting something security-related

If you believe you have found a security problem, open an issue **without the
details** and say that you would rather share them privately; a private channel
will be arranged from there. Please do not post a working exploit in a public
issue.

---

## Privacy

What ScrapeX stores and what it never touches: [Privacy Policy](privacy-policy.md).
