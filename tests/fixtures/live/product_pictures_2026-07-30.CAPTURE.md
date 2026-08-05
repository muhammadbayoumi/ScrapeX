# Live capture — the pictures a page publishes but its JSON-LD does not, 2026-07-30

Two product pages, one per server-rendered family, captured for
`tests/test_product_pictures.py`. Both were fetched anonymously, one request
each, ≥1.2 s apart from every other request in the session, and both answered
**HTTP 200**. Nothing was retried and neither site was asked for anything it
disallows: `advancedcastle.com/robots.txt` allows `/products/` (it disallows
`/api/`, `/cart` and the review paths), and `alsweed.sa/robots.txt` allows `/`
with no crawl delay addressed to anyone.

The user agents are the ones the crawl itself uses: the Chrome string
`sources.yaml` declares for ADVANCEDCASTLE, which 403s generic clients, and
`ScrapeX/0.1 (+contact: owner)` for ALSWEED, which does not.

**No image file was downloaded.** The URL is the record.

## Why these two products

Each was picked off a full-catalogue census (below) as the page that pins the
most claims at once, so a single fixture can carry a test rather than four.

### `advancedcastle_product_pictures_2026-07-30.trimmed.html`

`GET https://advancedcastle.com/products/لمبة-تحذير-فلاشر` — 555,707 bytes,
trimmed to 9,917. Kept byte-for-byte: the `hreflang` alternates, the
`<script type="application/ld+json">` Product block, the page's own
`var productImages` bootstrap, and the theme's `#product-images` gallery.

- Its JSON-LD names **3** pictures; its own bootstrap names **6**.
- The picture the JSON-LD calls the product's `image` is **not** the one the
  shop shows first — true on 44 of the catalogue's 168 products.
- **5 of the 6** carry the merchant's own `alt_text`, and one carries none, so
  the same fixture covers the label and the fall-back to the file name.
- The gallery markup is kept alongside the bootstrap deliberately: it is what a
  `carousel-img` reader would have matched, and keeping it lets the test show
  the two routes name the same pictures at different addresses.

### `alsweed_product_pictures_2026-07-30.trimmed.html`

`GET https://alsweed.sa/ar/كرسي-افرنجي-مقاس-30-سم/p448819456` — 263,073 bytes,
trimmed to 9,133. Kept byte-for-byte: the Product JSON-LD and the slider's
slide anchors.

- Its JSON-LD names **1** picture; the slider names **8**.
- The JSON-LD's picture is the **eighth** slide, not the first.
- The slides carry **3 different** `data-caption` values, so the per-picture
  label is real on this shop and not one string repeated.
- Every slide after the first has `src="…/s-empty.png"` — the lazy-load
  placeholder. It is kept on purpose: reading `<img src>` would have stored one
  placeholder as several pictures, which is why the reader takes the anchor's
  `href`. A test asserts the trap is still in the fixture.

## The censuses these came from

Both were full passes, not samples, and both are the evidence for the numbers
in the PR. One request per product, ≥1.2 s apart, honest UA, and the script
stops the moment a site answers 403 or 429. Neither did.

> **SCOPE OF THE TABLE BELOW: the early sample, not the finished census.** It
> is kept because it is what the two fixtures were captured against. The
> whole-catalogue figures live in `salla.py`'s header and are larger: 1,231 of
> 1,233 products, 1,170 JSON-LD pictures against 3,322 slide pictures, 1,160
> byte-identical and 10 YouTube thumbnails. Two numbers for one measurement is
> a contradiction only when neither says which measurement it is.
>
> **The ADVANCEDCASTLE column does not ship in this branch.** Its zid reader was
> split out and held: re-checked 2026-08-05, that site's sitemap now lists 2
> product URLs, 8 of 8 stored product links answer 404, and the URL this fixture
> was captured from is itself 404. The measurement below was true when taken and
> is not true of the site today, so the half that rested on it is not merged.

| | ADVANCEDCASTLE (not shipping) | ALSWEED |
|---|---|---|
| products | 168 of 168 | 1,233 (one URL per product; the sitemap lists each twice) |
| JSON-LD pictures | 435 | measured per product, ~1 each |
| the page's own list | 493 | ~3× the JSON-LD |
| JSON-LD URLs that are string-equal to a gallery/slide URL | **0** | **270 of 270** |
| JSON-LD pictures the page's list does not have | 6 | 5 (all YouTube thumbnails) |

The two rows at the bottom are why identity is per-connector: advancedcastle
publishes one picture at five addresses, so the URL cannot identify it and the
image uuid does; alsweed publishes each picture at exactly one address, and its
JSON-LD URL is byte-identical to the slide's `href`, so there the URL is right.

## What was NOT captured, and why

- **No `/api/` request to either store.** advancedcastle's robots.txt disallows
  `/api/`, so a Zid platform API is off the table on politeness grounds even
  where one exists. The in-page bootstrap answers the same question for free.
- **No English page for ALSWEED.** The salla connector fetches one page per
  product; asking for a second locale to read English captions would double
  every crawl, and this project's politeness budget is a stated value. The
  Arabic caption is captured as published and never translated.
- **No ELBUROJ capture.** It is `active: false` and asks for a 10-second crawl
  delay, so a 3,441-product census would be ~9.5 hours of knocking. It runs the
  same connector as ALSWEED and is expected to behave the same; that is stated
  as an expectation, not measured, and is the one ceiling in this work that a
  future crawl should confirm rather than assume.
