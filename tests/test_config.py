"""S5: the Harvest Manifest validator — including the real committed sources.yaml."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from scrapex.config import MANIFEST_FILE, Manifest, load_manifest
from scrapex.vocab import ConnectorFamily, ExtractScope


def entry(**overrides) -> dict:
    base = {
        "source_key": "MADAR",
        "source_name": "Madar",
        "base_url": "https://www.madar.com",
        "family": "magento-graphql",
        "extract": [{"kind": "product_prices"}],
    }
    base.update(overrides)
    return base


def test_committed_manifest_is_valid():
    """The real sources.yaml must always validate — this IS the CI gate."""
    manifest = load_manifest(MANIFEST_FILE)
    assert len(manifest.sources) >= 10
    gpp = manifest.get("GPP_ENERGY")
    # The owner's license decision is contract, not comment (T6 will test the guard):
    assert gpp.extract[0].scope == ExtractScope.LATEST_ONLY
    aramco = manifest.get("ARAMCO_FUEL_SA")
    # Probed live 2026-07-23 and promoted from TBD-probe to a real family.
    assert aramco.family == ConnectorFamily.ARAMCO_FUEL_PAGE
    assert aramco.extract[0].regions == ["SA"]  # feeds ONLY the Saudi rows


def test_every_committed_source_carries_an_english_name():
    """The manifest is where a site's names live, and the UNMARKED name is the
    English one — the primary display language. A source without it would show
    Arabic-only wherever it is listed, so "most of them" is not enough, and
    this asks every committed source rather than a sample."""
    manifest = load_manifest(MANIFEST_FILE)

    nameless = [s.source_key for s in manifest.sources if not s.source_name.strip()]
    assert nameless == [], f"no English name: {nameless}"
    # Two spellings the site itself uses, pinned so a rename here is deliberate.
    assert manifest.get("MADAR").source_name == "Madar"
    assert manifest.get("GPP_ENERGY").source_name == "Global Petrol Prices"
    # Both names are kept: the Arabic one is stored BESIDE the English one,
    # never in place of it. A TWO-WAY tripwire — renaming the keys without
    # swapping the values in sources.yaml leaves this green while every site's
    # Arabic name sits under the English-marked key.
    assert manifest.get("ELSEWEDYSHOP").source_name_ar == "السويدي شوب"
    assert manifest.get("ELSEWEDYSHOP").source_name == "Elsewedy Shop"


def test_a_source_may_have_no_arabic_name():
    """Optional by design — a site that answers in English only must not be
    unrepresentable in the manifest."""
    assert Manifest.model_validate({"sources": [entry()]}).get("MADAR").source_name_ar == ""


def test_a_source_may_NOT_have_no_english_name():
    """The other direction, which the old test left untested: English is the
    primary display language, so the unmarked name is required and a source
    without one must be REFUSED rather than listed under a blank heading."""
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [entry(source_name="")]})
    bare = entry()
    bare.pop("source_name")
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [bare]})


def test_no_source_is_active_without_a_shipped_connector():
    """The rule this always meant to enforce, restated for the Auto switch era.

    Activation is now a RUNTIME act the owner performs from the panel, and the
    flag lives in the committed manifest — so "everything starts inactive" is
    no longer true and no longer the point. What must never happen is a source
    active with no connector to run it: the scheduler would fire jobs that can
    only fail, forever, on a timer."""
    from scrapex.connectors.factory import _BUILDERS

    manifest = load_manifest(MANIFEST_FILE)
    orphaned = [s.source_key for s in manifest.sources
                if s.active and s.family not in _BUILDERS]
    assert orphaned == [], f"active without a connector: {orphaned}"


def test_duplicate_source_key_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        Manifest.model_validate({"sources": [entry(), entry()]})


def test_unknown_family_rejected():
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [entry(family="wordpress-magic")]})


def test_bad_region_rejected():
    # The manifest's `regions:` SCOPES a source; it is not the row's
    # country column, so it keeps its name and so does this message.
    with pytest.raises(ValidationError, match="region"):
        Manifest.model_validate(
            {"sources": [entry(extract=[{"kind": "commodity_price", "regions": ["Saudi"]}])]}
        )


def test_lowercase_source_key_rejected():
    with pytest.raises(ValidationError, match="UPPER_SNAKE_CASE"):
        Manifest.model_validate({"sources": [entry(source_key="madar")]})


def test_tbd_probe_cannot_be_active():
    """A3: no family until proven — an unprobed source cannot be activated."""
    with pytest.raises(ValidationError, match="TBD-probe"):
        Manifest.model_validate(
            {"sources": [entry(family="TBD-probe", active=True)]}
        )


def test_unknown_manifest_field_rejected():
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [entry(surprise="x")]})


def test_canary_bounds_validated():
    with pytest.raises(ValidationError):
        Manifest.model_validate({"sources": [entry(max_drop_pct=150)]})


def test_unknown_source_lookup_fails_loud():
    manifest = Manifest.model_validate({"sources": [entry()]})
    with pytest.raises(KeyError, match="NOPE"):
        manifest.get("NOPE")


def test_a_probe_placeholder_cannot_be_shipped_active():
    """"No family until proven" (A3), tested as a RULE rather than by pointing
    at whichever entry happens to be unprobed today.

    It used to assert TABLER was still TBD-probe. TABLER was removed from the
    manifest — it is an MIT icon library, not a shop — and a test that names a
    specific entry dies with that entry while the rule it guards lives on.
    """
    import pytest
    from pydantic import ValidationError

    from scrapex.config import SourceEntry

    fields = dict(source_key="UNPROBED", source_name="Unprobed",
                  source_name_ar="غير مفحوص", base_url="https://example.invalid",
                  family="TBD-probe", currency="EGP", default_region="EG",
                  vat_mode="incl",
                  extract=[{"kind": "product_prices", "scope": "census"}])

    # Inactive is fine: that is what a placeholder IS.
    assert SourceEntry.model_validate({**fields, "active": False}).family         == ConnectorFamily.TBD_PROBE

    # Active is refused, and the refusal says what to do about it.
    with pytest.raises(ValidationError) as caught:
        SourceEntry.model_validate({**fields, "active": True})
    assert "scrapex probe" in str(caught.value)


def test_no_source_holds_data_the_manifest_has_forgotten(tmp_path):
    """A source can be crawled and then lose its definition, and nothing said so.

    It happened: SPARK_ESHOP was crawled on 2026-08-03 — 1,789 products, 3,149
    offers, 3,149 observations, a successful run — and its manifest entry was
    deleted afterwards while the rows stayed, marked active. That is 22% of the
    warehouse belonging to a source no code could crawl, update or explain, and
    it was found by censusing the database rather than by anything failing.

    The manifest is the definition; the warehouse is the consequence. A
    consequence with no definition is not a small untidiness — every count
    includes it, every table shows it, and nothing can ever refresh it."""
    from scrapex import db as dbmod
    declared = {entry.source_key for entry in load_manifest(MANIFEST_FILE).sources}

    conn = dbmod.connect(tmp_path / "w.db")
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                 " source_name, base_url, platform, currency, timezone, authority, "
                 " active) VALUES (1,'GHOST','ش','G','http://g','shopify-json',"
                 "'EGP','UTC','shop',1)")
    conn.commit()

    stored = {row[0] for row in conn.execute(
        "SELECT source_key FROM source_site WHERE active = 1")}
    orphans = sorted(stored - declared)

    assert orphans == ["GHOST"], (
        "the check itself is broken — it should see exactly the source this "
        f"test invented, and it saw {orphans}")


def test_no_manifest_entry_declares_a_family_nothing_can_build():
    """An entry whose family has no connector is a promise the engine cannot
    keep. SIKA_EGYPT_DATASHEETS declared `datasheet-enrichment` for months with
    no builder anywhere — it read as work in progress and was really a dead
    entry, so the manifest said less than it appeared to.
    """
    from scrapex.connectors.factory import _BUILDERS
    from scrapex.vocab import ConnectorFamily

    manifest = load_manifest(MANIFEST_FILE)
    buildable = set(_BUILDERS) | {ConnectorFamily.TBD_PROBE}
    orphans = [s.source_key for s in manifest.sources if s.family not in buildable]
    assert orphans == [], f"declared families with no connector: {orphans}"
