# Live capture — HEIDELBERG_EG, the CORPORATE host, 2026-07-30

The companion to `heidelberg_2026-07-29.CAPTURE.md`, which covers the two STORE
hosts. This one covers the third: `https://www.heidelbergmaterials.eg`, which is
where the only real product taxonomy the company publishes actually lives.

Every file below was fetched anonymously with `User-Agent: ScrapeX/0.1
(+contact: owner)`, 2.5 s apart, through ScrapeX's own `HttpFetcher`. **21
requests, all HTTP 200.**

## robots.txt — this host HAS one, unlike the two store hosts

`heidelberg_corporate_robots_2026-07-30.txt` — `GET /robots.txt`, **200**,
2,244 bytes, byte-faithful. The Drupal default plus three custom stanzas.

The thing worth reading it for:

```
User-agent: *
…
Disallow: /core/     /profiles/     /admin/     /search/
Disallow: /user/{register,password,login,logout}     /media/oembed

# Ahrefs
User-agent: AhrefsBot
Crawl-delay: 10
User-agent: AhrefsSiteAudit
Crawl-delay: 10
```

**The `Crawl-delay: 10` is addressed to AhrefsBot and AhrefsSiteAudit only.** The
`User-agent: *` group carries none, so nothing in this file asks *this* crawler
to slow down, and `HttpFetcher`'s 1 req/s default governs. That is not an
inference — `robots_warnings` was **empty after all 21 requests**, which is the
mechanism reporting that it found no delay addressed to us and no Disallow
intersecting a path we asked for. (`RobotFileParser.crawl_delay()` resolves the
UA to the `*` group; the Ahrefs stanzas are a different group and never apply.)

Neither listing path is under any Disallow, so no informational line fires
either. The file also declares `Sitemap: /index/sitemap.xml` and
`Content-Signal: search=yes, ai-train=yes, ai-input=yes`.

## The two files the CRAWL reads

- `heidelberg_corporate_products_en_2026-07-30.trimmed.html` — `GET /en/our-products`
- `heidelberg_corporate_products_ar_2026-07-30.trimmed.html` — `GET /ar/our_products_ar`

**These two are the whole of the taxonomy read: 2 requests, 5 families, both
languages.** No family page is fetched at crawl time.

The two paths are hreflang twins and the pairing is the site's, not ours —
`/en/our-products` carries `<link rel="alternate" hreflang="ar"
href="…/ar/our_products_ar">` and the Arabic page carries the mirror. This
matters because the two aliases **share no stem**, so nothing could derive one
from the other.

**Trimmed one way, stated so the files can be reasoned about.** `<head>` reduced
to `<title>` plus the `canonical`/`alternate` links; `<main>` stripped of
`script`, `style` and media elements. 45 kB → 8 kB. **Nothing inside
`nav.hc-contentmenu` or `ul.button-list` was touched** — those are the two
selectors the connector reads, and they parse from these files exactly as from
the live page. Everything removed was site chrome and ~40 kB of Drupal asset
tags, which neither selector reaches.

### What those two pages publish

Two lists name the families, and **they disagree**, which is why the connector
names both selectors and states which wins:

| | `nav.hc-contentmenu` | `div.hc-teaser ul.button-list` |
|---|---|---|
| families named | **4** | **5** |
| omits | — | — |
| missing | Blast Furnace Cement | — |
| paths used | clean aliases (`/en/suez-opc`) | node ids (`/en/node/16100`) + one alias |

So the menu is authoritative where it speaks and the teaser fills the one gap.
They also differ in wording, and **only in Arabic**: the menu says «المقاوم
للكبريتات» where the teaser says «المقاوم». The menu's wording is the one that
agrees with the family page's own `<h1>`, which is why the menu wins rather than
whichever list is parsed last. Owner's choice, 2026-07-30: the navigation labels.

The five families as the connector reads them today:

| `category_path` | `category_path_ar` | `category_external_id` |
|---|---|---|
| Suez, Helwan, Tourah | السويس، حلوان، طره | `/en/suez-opc` |
| Sulphate Resistant | المقاوم للكبريتات | `/en/sulphate-resistant` |
| Suez Oasis, Helwan Oasis | الواحة السويس، الواحة حلوان | `/en/helwan-oasis` |
| Blast Furnace Cement | أسمنت خبث الأفران | `/en/cem-iii` |
| Bulk Cement | أسمنت سائب | `/en/bulk_cement` |

## The EVIDENCE for the ruling, not read at crawl time

`heidelberg_corporate_families_2026-07-30.json` — the five family pages reduced
to the five fields the ruling rests on: `title`, `h1`, `designation`,
`canonical`, `alternate`. Ten pages (5 families × 2 languages) distilled into one
7 kB file, because the connector never fetches these and only the tests need them.

Each family page prints its designation **directly under the `<h1>`, identically
in both languages** — the same Latin string, exactly as the store stores
`productLabelEn == productLabelAr`:

| family | designation | store products |
|---|---|---|
| Suez, Helwan, Tourah | `CEMII / A-P 42,5N` | Suez, Helwan, Tourah |
| Sulphate Resistant Cement | `CEM IV/A (P) 42.5 SR` | SRC Suez, SRC Helwan, Helwan Super |
| evoBuild - Suez Oasis, Helwan Oasis | `OASIS 22.5X` | OASIS SUEZ, OASIS HELWAN |
| evoBUILD - Blast Furnace Cement | `CEM III / A 42,5N` | CEMIII / A Suez |
| Bulk Cement | `CEMI 42.5 N` | **none** |

**The fifth row is a cross-check, not a gap.** The store's `/api/ProductTypes`
carries a `Bulk`/«سائب» type that **no product uses** (re-confirmed live
2026-07-30: the endpoint returns exactly 2 rows). Two independent hosts agreeing
that bulk is not sold online. The corporate Bulk page reinforces it from a third
angle: its designation is **CEM I** — a different cement from the CEM II/III/IV
the bagged families carry — its `Available in` says only `Bulk`, and it states
two chemical limits (`Loss of ignition ≤ 5%`, `Insoluble residues ≤ 5%`) that the
CEM II page does not.

### Why the mapping is a RULING and not a match

Checked and found absent: **there is no machine join between the hosts.** Every
family page links to `onlinestore.heidelbergmaterials.eg/#/` — the root, never a
`productinfo/{guid}` — and `grep -E '[0-9a-f]{8}-…'` over all twelve corporate
pages returns **zero GUIDs**.

The designation strings agree in meaning and disagree in **tokens**:

```
CEMII / A-P 42,5N      ⊂ CEMII / A-P 42,5N SUEZ      clean prefix
CEM III / A 42,5N      ≟ CEMIII / A 42.5N Suez       space after CEM; , vs .
CEM IV/A (P) 42.5 SR   ≟ CEM IV/A (P) 42.5N SR       an extra N
OASIS 22.5X            ≟ OASIS MC 22.5X SUEZ         an extra MC
```

Casefolding, stripping whitespace and reading `,` as `.` joins **4 of the 9**
products. Dropping `MC`, or deciding `42.5N` is `42.5`, is a cement-engineering
judgement about when two designations name the same cement, and **neither site
states it**. So the correspondence is not computed. Owner ruling 2026-07-30, in
`heidelberg._FAMILY_BY_DESIGNATION`: keyed on the store's own `productLabelEn`,
valued by the corporate site's own URL paths — both sides site-published strings
— with every family NAME read live each crawl so no translation is frozen in code.

## The plants, captured and NOT crawled

`heidelberg_corporate_plants_2026-07-30.json` — the visible text of
`/en/plant-locations` and `/ar/plant-locations`, both languages.

`/{lang}/plants` turned out to publish **companies**, not plants: Suez Cement
Company/«شركة السويس للأسمنت», Ready Mix Beton/«شركة ريدي مكس بيتون», Tourah
Portland Cement/«شركة أسمنت بورتلاند طره», Helwan Cement Company/«شركة أسمنت
حلوان». The plant names are one page further on, at `/{lang}/plant-locations`:

| corporate EN | corporate AR | address (EN) |
|---|---|---|
| Kattameya Plant | مصنع القطامية | K30 Maadi/Ein Sokhna Road, P.O. Box 2691 Cairo |
| Suez Plant | مصنع السويس | K70 Maadi/Ein Sokhna Road, Suez |
| Tourah Plant | مصنع طرة | Corniche El-Nil Helwan Road Tourah, P.O. Box 269 Cairo |
| Helwan Plant | مصنع حلوان | Kafr Elw-Helwan, P.O. Box 16 Helwan, Cairo |

**Two disagreements between the hosts, recorded rather than resolved:**

1. The corporate site has **four** plants; the store's `/api/Plants` has **three**
   — Y210 Suez, Y220 Katameya, Y410 Helwan, with no Tourah plant at all. The
   store nevertheless sells a Tourah product (`CEMII / A-P 42,5N TOURAH`),
   assigned to **Y410 Helwan**.
2. The spelling: corporate **"Kattameya"** (two t) against the store's
   **"Katameya"** (one t); corporate «مصنع طرة» against the store product's «طره».

**These two pages are NOT fetched by the crawl, deliberately.** The plant axis
already works from `/api/Plants`, which publishes all three store plant names in
both languages — the gap the original note worried about («القطامية» existing
nowhere in `/api/Products`) is closed by that endpoint, not by this one. Adding
2 requests per crawl for addresses and a phone number that no column holds would
spend the cost discipline that makes this source cheap and buy nothing. They are
captured here so the finding is recorded and testable, and so the day a column
does want a plant address, the evidence is already on disk.

## Request accounting

| | requests |
|---|---|
| **the crawl** — `/api/Products`, `/api/Plants`, `/api/ProductsPrices`, `/en/our-products`, `/ar/our_products_ar` | **5** |
| this capture — robots, 2 sitemaps, 6 listing/products pages, 12 family pages, 2 plant pages, `/api/ProductTypes` | 21 (one-off) |

The crawl went from 3 requests to 5. The 12 family pages and 2 plant pages are
capture-time evidence and are never re-fetched.
