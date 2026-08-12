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

## Before it will work

`API_KEY` in the page is **empty on purpose**. Picker requires an API key, and
the page says so plainly rather than failing against Google with a message about
a placeholder.

To create one: Google Cloud Console → *APIs & Services* → *Credentials* →
*Create credentials* → *API key*. Then restrict it, on the key's own page:

- **API restrictions** → the *Google Picker API* only.
- **Application restrictions** → *Websites* → `https://muhammadbayoumi.github.io/*`.

An unrestricted key in a public page is a key anyone can spend the project's
quota with. Restricted to one API and one site, a copied key is worth nothing.

The Picker API must also be enabled for the project, in *APIs & Services* →
*Library*. Enabling an API is not a scope review and needs no approval from
Google — it takes effect in about a minute.

## What this page is trusted with, and what it is not

It is handed a Google access token in the URL **fragment**, uses it to draw the
Picker, and erases it from the address bar immediately. It makes no API call of
its own, stores nothing, and sends nothing anywhere except one message to one
extension id, containing a file id and a name.

The token is never returned. The panel opens the chosen file with its own token.

**Nothing secret may ever be added to this file.** It is readable by anyone, for
ever, including after it is deleted. Tests in
`tests/test_the_privacy_policy_is_true.py` refuse a client secret, a refresh
token, an access token, and a token passed in a query string.
