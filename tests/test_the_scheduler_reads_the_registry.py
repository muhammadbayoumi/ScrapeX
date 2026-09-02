"""`R-78`: a source registered in `source_site` can be queued like any other.

WHY THIS FILE IS SHORT AND THAT IS THE POINT. The measurement `R-78` rests on is that
`jobs.py` asks a source for exactly three things -- `.get(key)`, `entry.base_url`, and a
`capture` callable -- and knows nothing about prices. **So the fix is a resolver, not a
second worker**, and what has to be proved is the resolver's contract rather than a new
scheduling path. If these pass and `tests/test_jobs.py` is untouched, the seven mechanisms
a contractor crawl now inherits -- host lanes, cross-job admission, pause and resume,
archive-before-rebuild, per-source failure isolation, the counters -- were never rewritten.

THE DEFECT THIS CLOSES, measured on his live engine and recorded as `REQ-45`:
`POST /api/jobs` validated against `load_manifest(sources.yaml)`, a FILE, so `muqawil_org`
-- which has lived in `source_site` since `0014` -- answered `404 unknown source_key`. Every
muqawil crawl to date, all 34,834 pages, ran from a terminal instead. `R-81` records why
that was not a workaround: he never uses one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.catalog import register_site
from scrapex.catalog_models import SiteCreate
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.sourceresolver import RegistrySource, SourceResolver, UnknownSource


class _Entry:
    """A manifest entry, reduced to the one attribute the worker reads off it."""

    def __init__(self, source_key: str, base_url: str):
        self.source_key = source_key
        self.base_url = base_url


class _Manifest:
    """`Manifest`'s contract as `jobs.py` uses it: `.get` raising `KeyError`."""

    def __init__(self, *entries: _Entry):
        self.sources = list(entries)

    def get(self, source_key: str) -> _Entry:
        for entry in self.sources:
            if entry.source_key == source_key:
                return entry
        raise KeyError(f"unknown source_key {source_key!r}")

    def resolve_by_url(self, url: str):
        return None


@pytest.fixture()
def connect(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        register_site(conn, SiteCreate(site_key="muqawil_org",
                                       display_name="Saudi Contractors Authority",
                                       base_url="https://muqawil.org"))
        conn.commit()
    finally:
        conn.close()
    return registry.engine.connect


def test_a_registry_source_resolves_where_the_file_said_404(connect):
    """THE DEFECT, DIRECTLY. `Manifest.get` raises for `muqawil_org` -- that raise IS the
    404 the route returned -- and the resolver answers instead."""
    manifest = _Manifest(_Entry("MADAR", "https://madar.example"))

    with pytest.raises(KeyError):
        manifest.get("muqawil_org")

    found = SourceResolver(manifest, connect).get("muqawil_org")

    assert isinstance(found, RegistrySource)
    # NORMALISED BY `register_site`, trailing slash and all -- asserted as stored rather
    # than as typed, because the worker reads this value and `urlsplit().netloc` is
    # indifferent to the slash while an equality test is not.
    assert found.base_url.rstrip("/") == "https://muqawil.org"


def test_the_manifest_still_wins_and_that_is_not_a_preference(connect):
    """A price key must keep resolving to its MANIFEST entry, which carries the charter,
    the locale and the connector. A `source_site` row carries none of those, so resolving
    a collision the other way would silently drop the extraction contract `SR-13`
    enforces."""
    conn = connect()
    try:
        # A COLLISION HAS TO BE CONSTRUCTED, and that is itself a finding: `SiteCreate`
        # refuses `MADAR` outright -- `^[a-z][a-z0-9_]{1,63}$` -- so the registry cannot
        # hold a manifest key in its own shape. The overlap is therefore narrow rather
        # than absent, and the precedence still has to be stated: a lowercase key could
        # exist in both.
        register_site(conn, SiteCreate(site_key="madar_shop", display_name="Madar",
                                       base_url="https://registry.example"))
        conn.commit()
    finally:
        conn.close()
    manifest = _Manifest(_Entry("madar_shop", "https://madar.example"))

    found = SourceResolver(manifest, connect).get("madar_shop")

    assert isinstance(found, _Entry)
    assert found.base_url == "https://madar.example"


def test_a_key_in_neither_registry_still_raises_a_lookup_error(connect):
    """AND IT MUST STILL RAISE BEFORE QUEUEING. The route catches `LookupError` to answer
    404; a resolver returning None would turn that clear refusal into an `AttributeError`
    deep inside the run -- the delayed failure `R-71` measured and `OP-92` records."""
    resolver = SourceResolver(_Manifest(_Entry("MADAR", "https://madar.example")), connect)

    with pytest.raises(UnknownSource):
        resolver.get("nothing_is_registered_as_this")

    with pytest.raises(LookupError):        # the route's own except clause
        resolver.get("nothing_is_registered_as_this")


def test_a_retired_registration_does_not_resolve(connect):
    """`0014` CLOSED the old `muqawil` row rather than deleting it. A resolver without the
    `valid_to IS NULL` predicate would queue a job against a registration somebody
    deliberately ended."""
    conn = connect()
    try:
        conn.execute("UPDATE source_site SET valid_to = '2026-08-30T00:00:00Z' "
                     " WHERE source_key = 'muqawil_org'")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(UnknownSource):
        SourceResolver(_Manifest(_Entry("MADAR", "https://x.example")),
                       connect).get("muqawil_org")


def test_the_politeness_host_is_readable_off_a_registry_source(connect):
    """`jobs.py:_host_of` does `manifest.get(key).base_url` inside a try/except and falls
    back to a unique string when it cannot. **A fallback would put muqawil in a lane of its
    own named `?0`** -- correct by luck, and wrong the moment two registry sources share a
    host. Reading a real `base_url` is what makes the lane real."""
    from urllib.parse import urlsplit

    found = SourceResolver(_Manifest(), connect).get("muqawil_org")

    host = urlsplit(found.base_url).netloc.lower().removeprefix("www.")
    assert host == "muqawil.org"


def test_the_resolver_does_not_widen_the_price_source_list(connect):
    """`app.py` builds `{entry.source_key: entry for entry in manifest.sources}` to render
    price cards. Widening `.sources` would put a contractor row into a list every consumer
    treats as price entries -- so the resolver widens `.get` and nothing else."""
    manifest = _Manifest(_Entry("MADAR", "https://madar.example"))

    assert [e.source_key for e in SourceResolver(manifest, connect).sources] == ["MADAR"]


# ---- and the route itself, which is the thing he could not press --------------

def test_the_route_queues_a_registry_source_instead_of_answering_404(tmp_path):
    """`REQ-45`, END TO END. This is the request the panel makes when the crawl button is
    pressed, and until now it answered `404 unknown source_key 'muqawil_org'` -- so the
    panel HID the button rather than offering one that fails.

    IT ONLY QUEUES, and that is the point of asserting `queued` rather than a result: the
    worker executes, and it is the SAME worker, with the same host lanes and the same
    admission gate. Nothing here is a second scheduling path.
    """
    import shutil

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    register_site(conn, SiteCreate(site_key="muqawil_org",
                                   display_name="Saudi Contractors Authority",
                                   base_url="https://muqawil.org"))
    conn.commit()
    conn.close()

    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    client = TestClient(create_app(db_path, manifest_path=manifest))

    posted = client.post("/api/jobs",
                         json={"source_keys": ["muqawil_org"], "run_mode": "update"})

    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "queued"


def test_the_route_still_refuses_a_key_no_registry_knows(tmp_path):
    """The 404 must survive. A route that accepted anything would turn a clear refusal
    into a job that fails inside the run -- `R-71`'s measured regression, `OP-92`."""
    import shutil

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)

    refused = TestClient(create_app(db_path, manifest_path=manifest)).post(
        "/api/jobs", json={"source_keys": ["no_such_source"], "run_mode": "update"})

    assert refused.status_code == 404
