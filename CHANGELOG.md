# Changelog

GENERATED from `scrapex/version.py` by `python -m scrapex.cli export-version`.
Do not hand-edit: the ledger is the truth and this file is its readable form,
and `tests/test_version.py` fails the build when the two disagree.

Each entry names the version a capability is GUARANTEED from and, where the
work predates this file, the commit that built it — evidence read out of
`git log`, never remembered. `docs/BACKLOG.md` §7 remains the session-level
record of what was done; this file answers a narrower question: which version
has it.

## 0.3.0

Minimum supported extension: `0.2.2`.

No new capabilities. Fixes and internal change only — an extension and an engine that spoke to each other before this version still do.


## 0.2.2

Minimum supported extension: `0.2.2`.

- **robots_per_source** (adf31b2) — Read what a site's robots.txt asks of a crawler, then decide per source: follow the tool default, obey that site, or write a rule for it alone. _Runs in: panel, engine._

## 0.2.0

Minimum supported extension: `0.2.2`.

- **compatibility_notice** (7ca7a75) — Be told, rather than left to find out, when the installed extension is older than the features the engine deploys. _Runs in: panel._
- **crawl_pace** (c63ec21) — Choose whether each site's requested crawl delay is honoured, and set the minimum seconds between requests and the request timeout. _Runs in: panel, engine._
- **crawl_parallel_sources** (63dc24b) — Crawl several different sites at the same time. Two sources on the SAME site still take turns, so no site is asked for more than before. _Runs in: panel, engine._
- **crawl_resume** (56a50d1) — Continue an interrupted crawl from the pages it already kept, without fetching any of them again. _Runs in: panel, engine._
- **display_method_and_unit** (55ae064) — Record how a site displays a product and what one unit of its price buys, so a per-metre price is never read as a per-piece one. _Runs in: engine._
- **source_admin** (412785b) — Edit, rename, stop tracking or erase a source from the panel, with a rename moving the rows in all nine tables in one transaction. _Runs in: panel, engine._
- **version_visibility** (7ca7a75) — See which version of the extension and which version of the engine are actually running, each named for the side it belongs to. _Runs in: panel, engine._
