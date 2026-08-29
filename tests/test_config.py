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


def _warehouse(tmp_path, *source_keys):
    """A warehouse holding one active source_site row per key."""
    from scrapex import db as dbmod
    conn = dbmod.connect(tmp_path / "w.db")
    dbmod.migrate(conn)
    for i, key in enumerate(source_keys, start=1):
        conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                     " source_name, base_url, platform, currency, timezone, authority, "
                     " lifecycle) VALUES (?,?,'ش','G','http://g','shopify-json',"
                     "'EGP','UTC','shop','active')", (i, key))
    conn.commit()
    return conn


def test_a_source_the_manifest_has_forgotten_is_reported(tmp_path):
    """SPARK_ESHOP was crawled on 2026-08-03 — 1,789 products, 3,149 offers,
    3,149 observations, a successful run — and its manifest entry was deleted
    afterwards while the rows stayed, marked active. 22% of every offer in the
    warehouse belonged to a source no code could crawl, update or explain, and
    it was found by hand-censusing the database two days later.

    THIS TEST REPLACES ONE THAT COULD NOT FAIL. The first version inserted a
    row called GHOST into an empty temp database and asserted that GHOST came
    back — true for any manifest, including one with every source deleted. An
    adversarial review proved it by removing SPARK_ESHOP from the manifest and
    watching the two tests beside it go red while this one stayed green: the
    test named after the incident was the only one that could not see it.

    Worse, it checked nothing that shipped. No production code read
    source_site.active at all, so the "guard" was a query living in a test."""
    from scrapex import storage
    declared = load_manifest(MANIFEST_FILE).sources[0].source_key
    conn = _warehouse(tmp_path, declared, "SPARK_ESHOP_GONE")

    forgotten = storage.undeclared_sources(conn)

    assert forgotten == ["SPARK_ESHOP_GONE"]
    assert declared not in forgotten, (
        "a source the manifest DOES declare was reported as forgotten; the "
        "check is comparing against nothing")


def test_a_warehouse_whose_sources_are_all_declared_is_quiet(tmp_path):
    """The negative half, and the half the vacuous version never had: with
    every stored source declared, the answer is empty. Without this, a check
    that always returned its whole input would pass the test above."""
    from scrapex import storage
    keys = [entry.source_key for entry in load_manifest(MANIFEST_FILE).sources[:3]]

    assert storage.undeclared_sources(_warehouse(tmp_path, *keys)) == []


def test_the_warehouse_says_it_on_the_page_the_owner_already_opens(tmp_path):
    """A function nobody calls is the same defect one layer down. It rides
    storage.health(), which the Storage page runs on every visit — and `ok`
    stays true, because a forgotten source is not corruption."""
    from scrapex import storage
    _warehouse(tmp_path, "SPARK_ESHOP_GONE").close()

    verdict = storage.health(tmp_path / "w.db")

    assert verdict["ok"] is True
    assert verdict["undeclared_sources"] == ["SPARK_ESHOP_GONE"]
    assert "SPARK_ESHOP_GONE" in verdict["detail"]


def test_the_english_shop_declares_that_it_is_an_english_shop():
    """One line stands between this source and 1,789 mislabelled names again.

    spark-eshop serves English at its root — <html lang="en">, and every title
    reads like "Himel Variable Speed Drive VFD, 380V 3-Phase Motor Control" —
    and it has no /en locale at all; that URL answers 404, verified live. The
    connector defaults to assuming Arabic at the root, which is right for the
    eleven sources that were crawled under that assumption and wrong here.

    Without this declaration the crawl files English titles under the Arabic
    heading and leaves product_name — which this module calls required — empty
    on every row, and REPORTS SUCCESS. That is how the 3,149 rows already in
    the warehouse were written. Deleting this line would not fail anything; it
    would quietly recreate the defect on the next crawl."""
    spark = load_manifest(MANIFEST_FILE).get("SPARK_ESHOP")

    assert spark.default_language == "en"


def test_the_shop_with_no_definition_is_not_crawled_before_someone_says_so():
    """Restoring the entry gives 3,149 orphaned rows a definition. It does not
    endorse them: the manifest's own notes record that currency is UNKNOWN on
    all 3,149, country is '*' on all 3,149, and there are zero images. Active
    would mean the scheduler replaces them tonight without the owner deciding
    to."""
    assert load_manifest(MANIFEST_FILE).get("SPARK_ESHOP").active is False


def test_no_provenance_header_contradicts_the_source_beneath_it():
    """A header outlived the source it described, and sat above another one.

    `256cd27` removed SIKA_EGYPT_DATASHEETS and took ARAMCO_FUEL_SA's own header
    line with it, leaving Sika's — "probed: Sika Egypt corporate (AEM) —
    enrichment only, no prices" — directly above ARAMCO, a source whose whole
    purpose is the official monthly fuel PRICE. The register even asserted the
    stale header was gone while it was still in the file.

    NOTHING CAUGHT IT, and nothing would: measured 2026-08-05, deleting a
    provenance header outright leaves `validate-manifest` at exit 0 and
    `tests/test_config.py` fully green. A comment is invisible to every gate
    this project has.

    So the rule is deliberately narrow rather than "every source must have a
    header" — ten of the twelve do and two do not, and inventing a convention
    here would be a separate decision. This asserts only what cannot be true: a
    header that says the source below it has no prices, above a source that
    declares a price kind."""
    import re

    from scrapex.vocab import ExtractKind

    text = MANIFEST_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    priced = {ExtractKind.PRODUCT_PRICES.value, ExtractKind.COMMODITY_PRICE.value}
    manifest = load_manifest(MANIFEST_FILE)

    contradictions = []
    for index, line in enumerate(lines):
        key = re.match(r"\s*- source_key:\s*(\S+)", line)
        if not key:
            continue
        above = index - 1
        while above >= 0 and not lines[above].strip():
            above -= 1
        if above < 0:
            continue
        header = lines[above].strip()
        if not header.startswith("# ----"):
            continue
        says_no_prices = "no prices" in header.lower() or "enrichment only" in header.lower()
        kinds = {spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind)
                 for spec in manifest.get(key.group(1)).extract}
        if says_no_prices and kinds & priced:
            contradictions.append(f"{key.group(1)}: {header}")

    assert contradictions == [], (
        "a provenance header says its source has no prices while that source "
        f"declares a price kind: {contradictions}")

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
