# ScrapeX — the pluggable-crawler-backend map (§8.3 of the old Master Plan)

> **SUPERSEDED 2026-08-27, and cut to the one section that is still cited.**
>
> This file was a 523-line plan titled *"From Owner Tool to Public, Decentralized Price
> Tracker"*. `BACKLOG`'s Appendix B called it **stale and misleading**, and
> [R-32](archive/RULINGS.md#r-32--scrapex-is-a-collection-platform-price-is-one-category-and-filing-it-as-the-whole-thing-was-a-mistake)
> calls that title a mistake in full: ScrapeX collects in categories and price is one of
> them. Its **Topology A** decision is answered by
> [R-48](archive/RULINGS.md#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports)
> and [R-50](archive/RULINGS.md#r-50--the-engine-is-a-helper-to-the-extension-and-any-task-the-extension-can-do-moves-to-it),
> not by it.
>
> **It could not simply be deleted:** §8.3 is cited by name from `extension/app.html`,
> `extension/app.js`, `extension/releases.js` and `tests/test_panel_dom.py`. That section is
> below, verbatim. **Everything else — §1 to §7, §8.1-8.8 except this table, §9 — is at
> `git show d6f4967:docs/MASTER-PLAN.md`**, which is also what every
> `MASTER-PLAN.md:<line>` citation in `spikes/opfs-sqlite/FINDINGS.md` and
> `docs/code-maps/` refers to.
>
> **The table is candidates, not commitments.** Nothing here is built: `0` of the six
> non-native backends exists in the tree, which `docs/ENGINE-ROLE-MEASURED.md` measured.

### 8.3 Initial backend map — candidates, not commitments

| Candidate | Natural role inside ScrapeX | Integration shape | Licence note to verify per pinned release |
|---|---|---|---|
| **ScrapeX Native** | Known site families and highest-confidence price extraction | In-process reference adapter | ScrapeX MIT; remains the default where a proven connector exists |
| **Scrapy** | Mature structured spiders and large static crawls | Isolated Python worker | BSD-3-Clause |
| **Crawlee** | Persistent queues, sessions, proxies, HTTP and Playwright crawling | Prefer evaluating the official Python implementation first; Node sidecar remains possible | Apache-2.0 |
| **Crawl4AI** | Clean Markdown/documents and AI/RAG-oriented extraction | Isolated Python worker or local service | Apache-2.0 repository; attribution text and transitive dependencies still require review |
| **Firecrawl** | Optional self-hosted or hosted scraping/crawling API | Separate HTTP provider/sidecar, never copied into core by default | Primarily AGPL-3.0; some SDK/UI directories are MIT — legal review required before distribution or service exposure |
| **Katana** | Fast URL, route, form, and JavaScript-endpoint discovery | Versioned Go binary or container adapter | MIT |
| **Heritrix** | Web-scale archival crawling and WARC production | Separate Java/container archival pack | Apache-2.0, with some files/dependencies under other licences |

Scrapy and Crawlee overlap, as do Crawl4AI and Firecrawl. Overlap is not by
itself a reason to ship both. A backend is added when its measured capability is
materially better for a real ScrapeX job, not because its repository is popular.
