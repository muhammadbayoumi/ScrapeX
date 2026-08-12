# The chooser page

`scrapex-picker.html` is the only part of ScrapeX that is **served from a web
server**. Everything else runs inside the extension or on your own machine.

## Why it exists at all

Google Picker is how `drive.file` reaches a spreadsheet ScrapeX did not create:
the owner picks a file, and Google grants access to that one file. Picker needs
`https://apis.google.com/js/api.js`.

Manifest V3 forbids an extension executing code fetched from a server. There is
no flag for this and no way around it inside the panel — so the chooser has to
live on an ordinary web origin, and this is it.

## Where it must be published

The panel opens exactly this address:

    https://muhammadbayoumi.github.io/mbiXsite/scrapex-picker.html

So the file belongs at `scrapex-picker.html` in the root of the **mbiXsite**
repository. Two things break if it moves:

- `PICKER_PAGE` in `extension/app.js` points at the old address.
- `externally_connectable` in `extension/manifest.json`, and `PICKER_ORIGIN` in
  `extension/background.js`, name the origin `https://muhammadbayoumi.github.io`.
  A different **host** — not merely a different path — means the page can no
  longer answer the extension at all.

A test binds those three together, so moving it breaks a test rather than the
button.

## The API key in the page

`API_KEY` is filled in, and it is **meant** to be readable. Picker requires the
key to reach the browser; there is no version of this that hides it.

What makes that safe is not secrecy but the two restrictions set on the key
itself, in Cloud Console → *Credentials* → the key:

- **API restrictions** → *Google Picker API*, and nothing else. It cannot touch
  Drive or Sheets; those are reached with an OAuth token, never with this key.
- **Application restrictions** → *Websites* →
  `https://muhammadbayoumi.github.io/*`.

Selecting *Websites* and adding no entry is not a restriction — the entry is.

An API key is not a credential here: it identifies the project for quota and
grants nothing. The honest limit of the second restriction is that a referrer
header is forgeable by anything that is not a browser, so the worst a copied key
buys is Picker quota on this project. No data, no access, no cost that matters.

Rotating it is one click on the key's page, then one line in this folder.

The Picker API must be **enabled** for the project before a key can even be
restricted to it — *APIs & Services* → *Library* →
[Google Picker API](https://console.cloud.google.com/apis/library/picker.googleapis.com).
Enabling an API is not a scope review and needs no approval from Google.

## What this page is trusted with, and what it is not

**No access token is ever in the URL.** An earlier version put one in the
fragment, on the true and irrelevant grounds that browsers do not send fragments
to servers. The reader that matters is local: `chrome.tabs.create` commits the
URL, and the committed URL reaches every extension holding the `tabs` permission
through `onCreated` and `onUpdated`. Erasing it in the page cannot help — the
delivery has already happened.

So the URL carries a **single-use nonce**. The page trades it back through the
extension's own message channel, which no other extension can read. The nonce is
spent by the first caller, refused for ever after, and expires inside the
chooser's own two-minute window; and it is worthless to anyone who cannot also
send from this page's origin.

The page uses the token it receives to draw the Picker and for nothing else. It
makes no API call of its own, stores nothing, and sends nothing anywhere except
one message to one extension id, containing a file id and a name.

The token is never returned. The panel opens the chosen file with its own token.

**Nothing secret may ever be added to this file.** It is readable by anyone, for
ever, including after it is deleted. Tests in
`tests/test_the_privacy_policy_is_true.py` refuse a client secret, a refresh
token, an access token, and a token passed in a query string.
