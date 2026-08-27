"""What a source WOULD do, answered for every source type without doing any of it.

`REQ-45`, measured live: `POST /api/jobs` validates its key against
`app.state.manifest` — the twelve price sources of `sources.yaml` — and muqawil lives
in `site_profile`, so the crawl button answered
`404 {"detail": "unknown source_key 'contractors'"}`. `GET /api/table` and
`GET /api/fields` both learned to ask the dataset catalogue first; `POST /api/jobs`
never did.

So this route resolves a key in BOTH registries and a key known to either answers
200. It makes no request and no write, and both are GUARDED rather than promised:
`refuse_writes` installs a SQLite authorizer that denies every statement able to
change the warehouse, and the fetchers are never constructed.

WHAT IT DOES NOT DO. `--plan` is ADVERTISED with its request count and never run —
a route called "dry" that quietly made 114 requests is the naming defect this
repository keeps finding.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import contractors, passes
from .crawlscope import CrawlScope
from .directories import Directory
from .directories import get as get_directory
from .features import FeatureKey, is_enabled
from .sightings import coverage, departures, missing_ids, sighting_frequencies

#: Every authorizer action able to change the warehouse file. Temp objects are left
#: alone: they live in the temp database and cannot reach his data.
_DENIED = frozenset({
    sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_VIEW,
    sqlite3.SQLITE_CREATE_VTABLE,
    sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_INDEX,
    sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_DROP_VTABLE,
    sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_REINDEX, sqlite3.SQLITE_ANALYZE,
    sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
})


def refuse_writes(conn: sqlite3.Connection) -> None:
    """Make a write on this connection RAISE instead of happening.

    A comment saying "this path does not write" is not a guard: `disown_impostors`
    deletes when `dry_run=False`, so one wrong keyword on this path is destructive.
    The authorizer runs when a statement is PREPARED, so a denied write never
    executes at all — and it fails loudly, which is what turns the claim into a
    check.

    Installed after the connection is open, so the pragmas `db.connect` sets on the
    way in are untouched.
    """
    def authorize(action: int, arg1, arg2, database, trigger) -> int:
        return sqlite3.SQLITE_DENY if action in _DENIED else sqlite3.SQLITE_OK

    conn.set_authorizer(authorize)


@dataclass(frozen=True)
class Target:
    """The key, resolved. `kind` decides which half of the payload gets built."""

    source_key: str
    kind: str            # "price" | "dataset"
    registry: str        # which register knew the key
    display_name: str
    #: price only — the manifest entry.
    entry: object | None = None
    #: dataset only.
    site_key: str = ""
    dataset_keys: tuple[str, ...] = ()
    scope: CrawlScope | None = None
    crawl_slice: str = ""


def resolve(source_key: str, *, general: sqlite3.Connection, manifest) -> Target | None:
    """The key in both registries, or None when neither knows it.

    THE MANIFEST FIRST because it needs no query, and the two sets cannot collide:
    a price key is `^[A-Z][A-Z0-9_]{2,63}$` and a dataset key is lower-case with
    underscores — the same reasoning `/api/table` gives for asking the other way
    round.

    `site_profile` IS ASKED TOO, and not only `dataset_definition`. `scrapex
    contractors --source` names a SITE key (`muqawil_org`) while the panel's card
    carries a DATASET key (`contractors`); refusing one of the two would leave the
    same 404 the route exists to end.
    """
    try:
        entry = manifest.get(source_key)
    except KeyError:
        entry = None
    if entry is not None:
        return Target(source_key=source_key, kind="price", registry="sources.yaml",
                      display_name=entry.source_name, entry=entry)

    dataset = general.execute(
        "SELECT d.dataset_key, d.display_name, d.original_name, s.site_key, "
        "       s.crawl_scope, s.crawl_slice "
        "  FROM dataset_definition AS d "
        "  JOIN site_profile AS s ON s.site_profile_id = d.site_profile_id "
        " WHERE d.dataset_key = ? AND d.valid_to IS NULL LIMIT 1",
        (source_key,)).fetchone()
    if dataset is not None:
        return Target(
            source_key=source_key, kind="dataset", registry="dataset_definition",
            display_name=dataset[1] or dataset[2], site_key=dataset[3],
            dataset_keys=(dataset[0],), scope=CrawlScope(dataset[4]),
            crawl_slice=dataset[5] or "")

    site = general.execute(
        "SELECT site_profile_id, site_key, display_name, crawl_scope, crawl_slice "
        "  FROM site_profile WHERE site_key = ? AND valid_to IS NULL LIMIT 1",
        (source_key,)).fetchone()
    if site is None:
        return None
    owned = tuple(row[0] for row in general.execute(
        "SELECT dataset_key FROM dataset_definition "
        " WHERE site_profile_id = ? AND valid_to IS NULL ORDER BY dataset_key",
        (site[0],)))
    return Target(source_key=source_key, kind="dataset", registry="site_profile",
                  display_name=site[2], site_key=site[1], dataset_keys=owned,
                  scope=CrawlScope(site[3]), crawl_slice=site[4] or "")


def unknown_key_detail(source_key: str, *, manifest) -> str:
    """The 404's words. It names BOTH registries, because "unknown" was the whole
    complaint: the old message said `unknown source_key 'contractors'` about a key
    the warehouse held 17,304 rows for."""
    return (f"unknown source_key {source_key!r} — not in sources.yaml "
            f"({len(manifest.sources)} price sources), and not a dataset_key in "
            "dataset_definition or a site_key in site_profile")


def _directory_for(target: Target) -> Directory | None:
    try:
        return get_directory(target.site_key)
    except KeyError:
        return None


def _coverage(general: sqlite3.Connection, dataset_key: str) -> dict:
    """`scrapex/sightings.py`, called. NOT reimplemented.

    The same four functions `contractors.report_coverage` prints, so the route and
    the CLI cannot come to disagree about what coverage means — including the
    window, which is `contractors.default_window` for both. The audit's own finding
    was `dataset_table_payload` reimplementing `fields.hidden_columns` inline.
    """
    figure = coverage(general, dataset_key)
    window = contractors.default_window(general, dataset_key)
    body: dict = {
        "dataset_key": dataset_key,
        "seen": figure.seen, "stored": figure.stored, "missing": figure.missing,
        "fraction": figure.fraction, "sentence": str(figure),
        "frequencies": {str(times): count
                        for times, count in sighting_frequencies(
                            general, dataset_key).items()},
        "missing_sample": list(missing_ids(general, dataset_key,
                                           limit=contractors.COVERAGE_SAMPLE)),
    }
    if not window:
        body["departures"] = None
        body["departures_note"] = (
            "no sightings recorded for this dataset, so there is no window to "
            "measure departures against")
        return body
    left = departures(general, dataset_key, not_seen_since=window)
    body["departures"] = {"not_seen_since": window, "gone": len(left.gone),
                          "unsighted": len(left.unsighted), "sentence": str(left)}
    return body


def _impostors(general: sqlite3.Connection, directory: Directory | None) -> dict:
    """`contractors.disown_impostors(..., dry_run=True)`, which counts and returns.

    IT APPENDS ITS FINDING TO `~/.scrapex/contractors.log`, because `say` is how
    that module reports. That is the one side effect this route has and it touches
    no database.
    """
    if directory is None:
        # NOT THE SAME REASON as "no profile reader", and saying so cost a measurement:
        # site_key `muqawil` has a `site_profile` row and no `Directory`, and the first
        # draft told the owner it declares no profile reader — about a site nothing can
        # crawl at all.
        return {"count": None, "dataset_key": None, "dry_run": True,
                "reason": "no directory builder for this site (scrapex/directories.py), "
                          "so nothing can be checked against it"}
    if directory.profiles is None:
        return {"count": None, "dataset_key": None, "dry_run": True,
                "reason": "this site declares no profile reader, so it has no "
                          "profile rows to check"}
    return {"count": contractors.disown_impostors(general, directory, dry_run=True),
            "dataset_key": directory.profiles.dataset_key, "dry_run": True,
            "reason": None}


#: `generic_page_snapshot` carries no dataset column, and scoping through
#: `generic_ingestion` would miss exactly the pages `--details` stores and never
#: ingests. So the run is the warehouse's newest, and the payload says so.
_RUN_SCOPE = ("generic_page_snapshot has no dataset column, so this is the newest run "
              "in the warehouse rather than this dataset's own")

#: `R-52` ruled a generic crawl-run table (option B) and it is not built, so nothing
#: stored says whether a generic run finished. `R-55`: absence beats a placeholder — a
#: `false` here would read as "this run completed", which is `OP-68`'s false sentence.
_NO_RUN_STATUS = ("no stored fact says whether a generic run finished — R-52 ruled a "
                  "generic crawl-run table and it is not built")


def _dataset_last_run(general: sqlite3.Connection) -> dict:
    """The newest `crawl_run_ref` in `generic_page_snapshot`, and what it holds.

    `runs_recorded` and `pages_stored` are here because the newest run is often a
    stub: measured on the live warehouse 2026-08-27, the newest ref is `R` with **2
    pages** while the warehouse holds **57,041** pages over **141** refs. Without the
    two totals the block reads as "the last crawl stored 2 pages".
    """
    totals = general.execute(
        "SELECT COUNT(*), COUNT(DISTINCT crawl_run_ref) FROM generic_page_snapshot"
    ).fetchone()
    row = general.execute(
        "SELECT crawl_run_ref, COUNT(*), MIN(captured_at), MAX(captured_at) "
        "  FROM generic_page_snapshot WHERE crawl_run_ref IS NOT NULL "
        " GROUP BY crawl_run_ref ORDER BY MAX(captured_at) DESC LIMIT 1"
    ).fetchone()
    body = {"pages_stored": totals[0], "runs_recorded": totals[1],
            "scope_basis": _RUN_SCOPE, "partial": None}
    if row is None:
        body.update({"run_ref": None, "pages": 0, "captured_from": None,
                     "captured_to": None,
                     "partial_basis": "no crawl has stored a page under a run ref"})
        return body
    body.update({"run_ref": row[0], "pages": row[1], "captured_from": row[2],
                 "captured_to": row[3], "partial_basis": _NO_RUN_STATUS})
    return body


def _price_last_run(price: sqlite3.Connection, source_key: str) -> dict:
    """`crawl_run` for this source. `partial` is a real column here."""
    row = price.execute(
        "SELECT r.run_id, r.started_at, r.finished_at, r.status, r.requests_count, "
        "       r.rows_seen, r.errors_count "
        "  FROM crawl_run AS r JOIN source_site AS s ON s.source_id = r.source_id "
        " WHERE s.source_key = ? ORDER BY r.started_at DESC, r.run_id DESC LIMIT 1",
        (source_key,)).fetchone()
    if row is None:
        return {"run_ref": None, "started_at": None, "finished_at": None,
                "status": None, "requests": None, "rows_seen": None,
                "errors": None, "partial": None,
                "partial_basis": "this source has no crawl_run row yet"}
    return {"run_ref": str(row[0]), "started_at": row[1], "finished_at": row[2],
            "status": row[3], "requests": row[4], "rows_seen": row[5],
            "errors": row[6], "partial": row[3] == "partial",
            "partial_basis": "crawl_run.status"}


def _scope(target: Target) -> dict:
    """The scope, and the one refusal it causes, IN THE PAYLOAD.

    Measured: `crawl_scope` appears nowhere in `scrapex/webui/app.py` and nowhere in
    any `extension/*.js`, so it is settable only by editing the database — and
    `--details` refuses under `listing_only` and tells the owner in words to change
    it. Showing the value is not the setter; the setter is a separate item.
    """
    return {
        "site_key": target.site_key,
        "value": target.scope.value if target.scope else None,
        "values": [one.value for one in CrawlScope],
        "slice": target.crawl_slice,
        "settable_here": False,
        "note": "site_profile.crawl_scope is settable only in the database today. "
                "Under listing_only the profile-page pass refuses.",
    }


def dry_payload(source_key: str, *, general: sqlite3.Connection,
                price: sqlite3.Connection, manifest) -> dict | None:
    """Four blocks, and the fourth is the one the panel's menu is built from.

    None when neither registry knows the key — the caller turns that into a 404 with
    `unknown_key_detail`.
    """
    target = resolve(source_key, general=general, manifest=manifest)
    if target is None:
        return None

    body: dict = {
        "source_key": target.source_key,
        "kind": target.kind,
        "registry": target.registry,
        "display_name": target.display_name,
        # The route's OWN cost, stated so "dry" can be checked rather than trusted.
        "network_requests": 0,
        "writes": [],
    }
    if target.kind == "price":
        last = _price_last_run(price, target.source_key)
        body["scope"] = None
        body["coverage"] = []
        body["coverage_note"] = ("coverage is sighted-against-stored, which the "
                                 "sighting ledger holds for datasets only")
        body["impostors"] = {"count": None, "dataset_key": None, "dry_run": True,
                             "reason": "the impostor check compares a profile row "
                                       "against its listing card, which a price "
                                       "source has neither of"}
        body["last_run"] = last
        body["passes"] = [one.as_dict() for one in passes.price_passes(
            target.entry, last_requests=last["requests"])]
        return body

    directory = _directory_for(target)
    body["scope"] = _scope(target)
    body["coverage"] = [_coverage(general, key) for key in target.dataset_keys]
    body["impostors"] = _impostors(general, directory)
    body["last_run"] = _dataset_last_run(general)
    body["passes"] = [one.as_dict() for one in passes.directory_passes(
        directory, scope=target.scope, crawl_slice=target.crawl_slice,
        site_key=target.site_key,
        extraction_enabled=is_enabled(FeatureKey.GENERIC_EXTRACTION))]
    return body
