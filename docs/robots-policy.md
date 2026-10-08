# robots.txt policy

**Owner decision — 2026-07-22, and it is now a DEFAULT rather than the law.**

Since 2026-08-10 robots.txt is decided per source, in three steps:

1. **Look.** `GET /api/sources/{key}/robots` reads the site's file and says what
   it contains for THIS crawler at THIS base url — whether it names us by name,
   what delay it asks for, which lines touch this source, and the one fact that
   decides the answer: `would_block_everything`. On a site that disallows the
   pages a source is for, choosing *obey* does not make the crawl polite, it
   makes it EMPTY — and an empty crawl reports success.
2. **Choose.** `SourceEntry.robots` is `default`, `obey` or `custom`.
   `custom` carries `{enforce_disallow, crawl_delay_s}` and nothing else,
   because those are the only two powers robots.txt has over a crawler.
3. **Enforce.** `scrapex/robots.py` resolves the choice against the file;
   `HttpFetcher` acts on it and writes the sentence that explains whichever
   happened. A refusal RAISES `RobotsDisallowed` rather than skipping the page:
   a skipped page becomes an empty crawl that reports success.

The table below is what a source gets when it has said nothing — the setting
`crawl_obey_disallow`, which ships at `0`. It stayed the default deliberately:
flipping it would change what twelve reviewed sources collect without the owner
asking.

| robots.txt directive | Our behaviour | Why |
|---|---|---|
| `Crawl-delay` | **Enforced** while the tool-wide `crawl_honour_delay` switch is on. The site's asked-for pace replaces our own `min_interval` whenever it is longer, and the run's log says so. | Slowing down is never the wrong direction, and a manifest note that claims politeness must be a mechanism, not a comment. |
| `Disallow` | **Informational only — not enforced, and never a warning.** The path is crawled; the fact is disclosed once per host as a single **info-level** job-log line, only when a Disallow actually intersects a crawled path. | Refusing outright could silently kill a source the owner relies on, and a warning would dress a policy decision as a defect needing review. The info line keeps the decision visible and revisitable per host; nothing happens behind the owner's back. |
| `Retry-After` (HTTP, not robots.txt — recorded here for completeness) | Honoured up to a **900 s ceiling**; hitting the ceiling is recorded in the run's log. | Honouring two minutes of a requested hour is the opposite of honouring it; sleeping a full hour inside a job is not viable either. |

Whatever the choice (#1413):

- **An unreadable robots.txt** — any status but 200 or 404, or a failed request —
  is treated as if the site had none: the tool's own rules apply, under every
  choice including *obey*, and the run's log says once per host that the file
  could not be read and why. A 404 is "no file" and says nothing.
- **Under *obey*, the source's rule wins**: the site's Crawl-delay is applied even
  with `crawl_honour_delay` off, and the log line says that is why.
- **A *custom* `crawl_delay_s` is applied as set.** The site's Crawl-delay does not
  raise it; when the site asked for more, the log line names both numbers.
- The delay `GET /api/sources/{key}/robots` reports is `decide()`'s, and the
  fetcher applies that same answer — the two cannot disagree.

Mechanism: `HttpFetcher._robots_for` in `scrapex/connectors/base.py` — robots.txt is
fetched lazily once per host (via the plain client: it does not count as a crawl
request), and every disclosure travels through `robots_warnings` →
`CaptureResult.notes` → the job log at **info** level (data warnings stay at
warning level, on `CaptureResult.warnings`), so none of this is silent and none
of it masquerades as a defect.

Changing the DEFAULT = the `crawl_obey_disallow` setting, no code.
Changing what a single source does = its `robots:` key in the manifest, or the
panel's Robots panel on that source.
Changing the MECHANISM = `scrapex/robots.py` plus `HttpFetcher._request`, and
their pins in `tests/test_robots_is_the_owners_decision.py` and
`tests/test_http_fetcher.py` — and updating this file.
