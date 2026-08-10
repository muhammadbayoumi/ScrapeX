# Brief for the mbiXsite session — adding ScrapeX to the site

Hand this whole file to the session that develops `muhammadbayoumi/mbiXsite`.
It is written to be pasted as-is.

---

## Who you are and what this is

You are working on **`muhammadbayoumi/mbiXsite`** — the public website for the
mbiX product family, served by GitHub Pages at
`https://muhammadbayoumi.github.io/mbiXsite/`.

The site today is entirely about **one** product: the mbiX Excel add-in. A
**second** product, **ScrapeX**, is about to have its first release, and the
site has to carry it. ScrapeX is a Chrome extension plus a local Windows engine:
it collects published prices from sites the user nominates into a database on
the user's own machine.

**The rule that governs everything below, from the owner directly:**

> «الموقع بيخدم كذا حاجة مش scrapeX فقط بيخدم برده addin-X يعنى هيبقى شامل
> products يعنى **متغيرش الى موجود ضيف عليه**»
>
> *The site serves several things, not only ScrapeX — it also serves the
> add-in, so it becomes a products site. **Do not change what exists; add to
> it.***

Every add-in page, string, style and link must still work exactly as it does
now when you are done. If making room for a second product requires touching a
shared file (the navbar, the footer, `links.json`), extend it — do not rewrite
it, and do not restructure the add-in's pages to fit a new abstraction.

---

## What is already there (verified, not assumed)

| | |
|---|---|
| **Stack** | Vite 5 + `vite-plugin-handlebars` partials, Bootstrap 5.3, SCSS, Bootstrap Icons |
| **Pages** | `index.html`, `about.html`, `install.html`, `help-center.html`, `join-newsletter.html` |
| **Partials** | `src/partials/navbar.html`, `src/partials/footer.html` |
| **Scripts** | `src/js/` — `main.js`, `i18n.js`, `navbar.js`, `links.js`, `version-loader.js`, `language-dropdown.js`, `animations.js` |
| **Styles** | `src/scss/` — twenty partials behind `main.scss`, including `_rtl.scss` |
| **Data** | `src/data/links.json` — every external URL, in one file |
| **i18n** | `data-i18n="key"` attributes resolved by `src/js/i18n.js`; English and Arabic, with RTL support already built |
| **Live version** | `src/js/version-loader.js` reads `endpoints.version_check` and fills `[data-version-url]` |

Two mechanisms already in place matter a great deal to this work, and **you
should reuse both rather than invent anything**:

1. **Every external URL lives in `src/data/links.json`.** Nothing is hard-coded
   in a page. Keep it that way.
2. **`version-loader.js` already polls a version manifest** at
   `https://raw.githubusercontent.com/muhammadbayoumi/mbiX-hub/main/Xadd-in/json/version.json`
   and already handles the CDN's five-minute cache with a minute-bucketed
   `?t=` key, with a timeout and a graceful fallback. Its comments explain why.
   **ScrapeX publishes a manifest of the same shape in the same repository**,
   one folder across — see the contract below.

---

## The work

### A · An install page for the ScrapeX extension — the main deliverable

A new page, alongside the add-in's `install.html` and **not replacing it**. Name
it whatever fits the site's conventions (`scrapex.html`, or
`install-scrapex.html` — your call, but say which you chose).

ScrapeX installs in **two halves**, and the page's whole job is to make that
plain, because a user who installs one and not the other sees a panel that
looks broken:

1. **The extension**, from the Chrome Web Store. *(The store link does not
   exist yet — see "What is not decided yet" below. Build the button and read
   its URL from `links.json` so it becomes real with a one-line change.)*
2. **The engine**, a single `scrapex-engine.exe`. **The extension downloads and
   installs it for you** from its own Engine page — that is the intended route
   and the page should say so first. Installing by hand also works: download,
   put it anywhere, run it.

Facts the page must state, all of them true and all of them checkable:

- **Windows only.** The engine is a PyInstaller build; there is no macOS or
  Linux binary.
- **No administrator rights.** It installs for one user, into
  `%LOCALAPPDATA%\ScrapeX\engine\`, and appears in *Apps & features* normally.
- **The binary is not code-signed.** SmartScreen will warn once on first run,
  and the user must choose *More info → Run anyway*. **Say this on the page,
  with the exact wording of the dialog.** A warning a user was told to expect
  is a detail; the same warning unannounced is the moment they stop installing.
  Publish the SHA-256 next to the download so it can be verified — the release
  ships one.
- **Nothing runs on a server.** No account, no subscription, no upload. If the
  machine is off, nothing runs.
- **Chrome (or a Chromium browser).** The panel is a Chrome side panel.

Use `[data-version-url]`-style hooks off the **ScrapeX** manifest so the
version number and the download link are never typed into the HTML. A
hard-coded version goes stale on the next release; the add-in's loader already
carries that lesson in a comment.

### B · A privacy policy page for ScrapeX

**The Chrome Web Store will not accept the listing without a public privacy
policy URL.** This is a hard blocker on ScrapeX's first release, and it is the
single most time-critical item in this brief.

The text is written and is **not yours to rewrite**. It lives in the ScrapeX
repository at `docs/privacy-policy.md` and is **verified by automated tests on
every build** — the tests assert that it names every OAuth scope the extension
actually requests, every host it can actually reach, and that its claim of "no
telemetry" holds against the shipped JavaScript. Editing the prose here would
silently break that guarantee.

So: **render it, do not retype it.** The ScrapeX release publishes the markdown
to the same public repository as its version manifest, at

```
https://raw.githubusercontent.com/muhammadbayoumi/mbiX-hub/main/ScrapeX/docs/privacy-policy.md
```

Fetch and render it (build-time or runtime — your call, state which), styled to
match the site. If you find a factual error in the text, **report it back
rather than fixing it locally**; the fix belongs upstream where the test lives.

### C · A support page for ScrapeX

Same arrangement, same reason: `ScrapeX/docs/support.md` in the hub. It tells a
user which two version numbers to include in a report and where the panel shows
them.

### D · Make the site legibly about *products*, minimally

Just enough that a visitor can tell there are two, and no more than that:

- The **navbar** gains a way to reach ScrapeX. If a products dropdown is the
  natural fit for the existing markup, use one; if a single link is less
  disruptive, use that. The add-in's own links must keep working and keep their
  current position.
- The **footer** gains ScrapeX's pages beside the add-in's.
- `links.json` gains a ScrapeX section. Suggested shape, matching what is
  already there:

```json
"scrapex": {
  "version_check": "https://raw.githubusercontent.com/muhammadbayoumi/mbiX-hub/main/ScrapeX/json/version.json",
  "releases":      "https://github.com/muhammadbayoumi/mbiX-hub/releases",
  "issues":        "https://github.com/muhammadbayoumi/mbiX-hub/issues",
  "webstore":      ""
}
```

- Both languages. Every string you add needs an **English and an Arabic**
  `data-i18n` entry, and the Arabic must be **written, not machine-translated**
  — the rest of the site is written Arabic and a translated page reads as one.
  If you are unsure of a term, leave the key and flag it rather than guessing.
- The **home page** should acknowledge the second product. Keep this small: the
  owner said add, not restructure.

### E · The manifest ScrapeX publishes — the contract

Written by ScrapeX's release workflow to
`ScrapeX/json/version.json` in `muhammadbayoumi/mbiX-hub`, beside the add-in's.
This is the real output of a real run:

```json
{
  "product": "scrapex-engine",
  "version": "0.2.0",
  "tag": "engine-v0.2.0",
  "published_at": "2026-08-08T07:21:59Z",
  "release_url": "https://github.com/muhammadbayoumi/mbiX-hub/releases/tag/engine-v0.2.0",
  "minimum_extension_version": "0.2.0",
  "protocol_version": 1,
  "installer": {
    "name": "scrapex-engine.exe",
    "url": "https://github.com/muhammadbayoumi/mbiX-hub/releases/download/engine-v0.2.0/scrapex-engine.exe",
    "bytes": 24000000,
    "sha256": "32eccd8c…"
  }
}
```

Notes that will save you a debugging session:

- **`product` is not decoration.** The add-in's manifest sits one folder away
  with a similar shape. Check `product === "scrapex-engine"` before rendering
  anything, or a path typo produces a confident, wrong version — which looks
  exactly like success.
- **The file does not exist until the first release.** Until then the URL
  **404s**, and that is the honest answer, not an error. The page must degrade
  the way `version-loader.js` already degrades: no version number invented, the
  download button pointing at the releases page.
- `minimum_extension_version` and `protocol_version` are for the extension's
  own compatibility check. The site can ignore them.

---

## What is not decided yet — do not invent these

Leave each as an empty string in `links.json`, with the UI already wired, and
**list them in your final report** so they can be filled in one edit:

1. **The Chrome Web Store URL.** The item does not exist yet. The extension ID
   is pinned and will be `ekcgggphcfdbjgfkcmjagehfjhijeang`, so the URL will
   almost certainly be
   `https://chromewebstore.google.com/detail/ekcgggphcfdbjgfkcmjagehfjhijeang`
   — but it is unconfirmed until the listing is created, so do not present it
   as live.
2. **The first release does not exist yet**, so the version manifest 404s
   today. The 404 path is therefore the state you can actually test, and the
   one most likely to be seen by a real visitor first. Test it deliberately.
3. **Whether ScrapeX gets its own domain or lives under this one.** Assume this
   one.

---

## Report back with these, exactly

The ScrapeX side has to be wired to whatever you build, and cannot be until it
knows:

1. **The final URL of the privacy policy page** — it goes in the Chrome Web
   Store listing and is a hard blocker.
2. **The final URL of the support page** — the same listing needs it.
3. **The final URL of the ScrapeX install page** — the extension's own Engine
   page will link to it.
4. Anything in the two markdown documents that you believe is wrong. Report,
   do not edit.

---

## Done means

- [ ] Every existing add-in page renders and behaves exactly as before — check
      this explicitly rather than assuming, including both languages and RTL.
- [ ] `npm run build` is clean, and the built site works from the Pages
      subpath (`/mbiXsite/`), not only from `npm run dev` at the root.
- [ ] The ScrapeX install page states: Windows only · no admin rights · the
      SmartScreen warning, in the dialog's own words · the two halves and that
      the extension installs the engine itself.
- [ ] No version number and no download URL is hard-coded in any HTML.
- [ ] The privacy and support pages render the upstream markdown; neither is
      retyped.
- [ ] With the manifest 404ing — which is today's real state — no page shows a
      broken version, an invented one, or a dead download link.
- [ ] Every new string exists in English and in written Arabic.
- [ ] No new external URL outside `links.json`.
