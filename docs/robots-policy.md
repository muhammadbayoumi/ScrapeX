# robots.txt policy

**Owner decision — 2026-07-22.**

| robots.txt directive | Our behaviour | Why |
|---|---|---|
| `Crawl-delay` | **Enforced.** The site's asked-for pace replaces our own `min_interval` whenever it is longer, and the run's log says so. | Slowing down is never the wrong direction, and a manifest note that claims politeness must be a mechanism, not a comment. |
| `Disallow` | **Informational only — not enforced.** The path is crawled; the fact is disclosed once per host in the run's warnings. | Refusing outright could silently kill a source the owner relies on. The disclosure keeps the decision visible and revisitable per host; nothing happens behind the owner's back. |
| `Retry-After` (HTTP, not robots.txt — recorded here for completeness) | Honoured up to a **900 s ceiling**; hitting the ceiling is recorded in the run's warnings. | Honouring two minutes of a requested hour is the opposite of honouring it; sleeping a full hour inside a job is not viable either. |

Mechanism: `HttpFetcher._robots_for` in `scrapex/connectors/base.py` — robots.txt is
fetched lazily once per host (via the plain client: it does not count as a crawl
request), and every disclosure travels through `robots_warnings` →
`CaptureResult.warnings` → the job log, so none of this is silent.

Changing this policy = changing that method + its pins in
`tests/test_http_fetcher.py`, and updating this file.
