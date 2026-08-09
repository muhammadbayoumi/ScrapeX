# The generic fetcher — the seam, before any site's parsing

M6 needs muqawil.org crawled automatically. Today nothing can: `scrapex/extract/`
**never fetches anything**. Verified 2026-08-08 — no `HttpFetcher`, no
`requests`, no `httpx`, no `urlopen` anywhere in it. Its only door is

```python
save_snapshot(conn, SnapshotCreate(source_url=..., html_content=...))
```

and the HTML is *handed* to it, today by the panel capturing the page the user is
looking at.

And `scrapex/connectors/` is the **price** pipeline:
`SiteConnector.fetch(source) → Iterable[ScrapedTable] → to_payload() →
FunnelPayload`. A muqawil connector written against that contract would compile,
pass its tests, and put nothing in the generic tables — the failure that looks
most like success.

So this is a new seam. **Design it before writing any muqawil parsing**: the
parsing is the easy half and the half that looks like progress; the seam is what
makes it work or quietly not.

---

## What must not be rebuilt

`connectors/base.py` already holds things that were expensive to get right, and
a generic fetcher that reimplements them will get them wrong differently:

| | why it matters here |
|---|---|
| `HttpFetcher` | pacing, retry, one user agent, conditional headers, a shared SSL context. muqawil is 860 listing pages — pacing is not optional |
| `declare_frontier` / `expect_requests` | what makes a crawl **interruptible** and its progress meaningful. A 34-hour crawl that cannot be paused is not a feature |
| `CrawlBlocked` / `CrawlInterrupted` | the vocabulary the runner already understands for "stopped" versus "refused" |

**Decision: reuse `HttpFetcher` unchanged.** The seam is a new protocol, not a
new transport.

---

## The protocol

`SiteConnector` returns `ScrapedTable`, which is a priced-offer shape. A generic
source has no offers — it has **pages**, and what a page means is decided later,
by the schema the owner approved. So the generic protocol yields pages:

```python
@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str
    #: "listing" or "detail". The walker needs to know which, because the scope
    #: gates them differently and only one of them can be paginated.
    kind: str


class PageSource(Protocol):
    """One site's knowledge, and nothing else.

    Everything a site does NOT decide — pacing, scope, interruption, where the
    HTML goes — lives in the walker below. A PageSource that reaches for the
    database or counts requests is doing the walker's job and will be the
    reason two sites behave differently for no reason.
    """

    site_key: str

    def listing_urls(self, base_url: str) -> Iterable[str]:
        """The listing pages, in order. muqawil: `?page=1..860`."""

    def detail_urls(self, page: FetchedPage) -> Iterable[str]:
        """The detail links this listing page points at."""

    def belongs_to_slice(self, page: FetchedPage, slice_of: str) -> bool:
        """Whether this listing row is in the slice the owner named.

        Answered from the LISTING page, which is the whole point: muqawil
        publishes city and grade there, so a slice can be selected without
        fetching a single detail page. A site that cannot answer this cannot
        offer LISTING_PLUS_SLICE, and should say so by raising.
        """
```

---

## The walker — where `CrawlScope` finally does something

M6a put `crawl_scope` and `crawl_slice` on `site_profile` and **nothing consumes
them yet**. This is the consumer, and it is the only one: a scope enforced in two
places is a scope enforced in neither.

```
read site_profile  →  scope + slice
        │
        ├── LISTING_ONLY        walk listing_urls, snapshot each, stop
        │
        ├── LISTING_PLUS_SLICE  walk listing_urls, snapshot each,
        │                       then detail_urls FILTERED by belongs_to_slice
        │
        └── FULL_THEN_LISTING   walk listing_urls, snapshot each,
                                then every detail_url
```

Three rules the walker owns, and no `PageSource` may override:

1. **Declare the frontier before fetching.** `declare_frontier(fetcher, n)` with
   the number the scope implies, so the run is interruptible and its progress
   is real rather than a spinner.
2. **Refuse `LISTING_PLUS_SLICE` with no slice.** `crawlscope.plan()` already
   raises `SliceRequired`; the walker must call it rather than reimplement the
   check, or the two will disagree one day.
3. **One page in, one `save_snapshot` out.** The walker never parses. Parsing is
   `scrapex/extract/`'s job and happens against a stored snapshot, which is what
   makes a bad parse re-runnable without re-fetching 860 pages.

---

## Where the HTML goes

Straight into `save_snapshot`, unchanged, one call per page.

This is the decision that keeps the crawl and the interpretation separate — and
it is worth stating because the tempting shortcut is to parse while fetching:

- A parse that turns out wrong is re-run against stored snapshots. **Nothing is
  re-fetched.** On a source measured at 34 hours that difference is the product.
- `generic_page_snapshot` is already immutable, enforced by triggers that
  survived the M5 collapse. Evidence that cannot be edited after the fact is
  what makes "the grade changed on this date" a claim and not an opinion.
- The existing capture flow — the user pressing a button on a page — becomes
  *the same path* with a different source of HTML. One pipeline, two doors.

---

## What is muqawil-specific, and it is small

Only the `PageSource`:

- `?page=N` up to the last page
- how a listing row's detail link is found
- how city and grade are read from a listing row, for `belongs_to_slice`

**Everything else is shared.** If a second entity site later needs its own
walker, that is the signal the seam was drawn in the wrong place — not a reason
to copy it.

---

## Suggested order

1. `FetchedPage` and `PageSource`, with a fake `PageSource` in tests. **No
   network.**
2. The walker, driven by that fake: all three scopes, the frontier declaration,
   the `SliceRequired` refusal, and one `save_snapshot` per page. Still no
   network.
3. The muqawil `PageSource`, against **saved HTML fixtures** — real pages,
   fetched once by hand and committed, so the parsing tests do not depend on the
   site being up or unchanged.
4. Only then, one live run behind `LISTING_ONLY`, which is fourteen minutes and
   is the honest way to discover what the fixtures got wrong.

Steps 1 and 2 carry all the risk and touch no network. Step 3 is the half that
looks like progress. Doing them in the other order is how a crawler ends up
correct against a site and wrong against the product.

---

## Open questions for the owner

- **Does a generic crawl belong in the same job queue as a price crawl?** They
  share pacing and interruption but not much else, and a 34-hour job sharing a
  queue with a 14-minute one is a scheduling decision, not a technical one.
- **What happens on the second run?** Lifecycle — appeared, confirmed,
  disappeared, returned — is the next milestone piece, and the walker needs to
  know whether it is founding a crawl or repeating one. It may be enough to ask
  `generic_ingestion`; **check before adding a column.**
