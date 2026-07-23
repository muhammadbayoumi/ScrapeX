"""S5: the Harvest Manifest validator — including the real committed sources.yaml."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from scrapex.config import MANIFEST_FILE, Manifest, load_manifest
from scrapex.vocab import ConnectorFamily, ExtractScope


def entry(**overrides) -> dict:
    base = {
        "source_key": "MADAR",
        "source_name": "المدار",
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
    assert manifest.get("TABLER").family == ConnectorFamily.TBD_PROBE


def test_every_committed_source_carries_an_english_name():
    """The manifest is where a site's names live, so the English one lives here
    too. A source without it shows Arabic-only wherever it is listed, while the
    table beside it flips AR|EN on demand — so "most of them" is not enough,
    and this asks every committed source rather than a sample."""
    manifest = load_manifest(MANIFEST_FILE)

    nameless = [s.source_key for s in manifest.sources if not s.source_name_en.strip()]
    assert nameless == [], f"no English name: {nameless}"
    # Two spellings the site itself uses, pinned so a rename here is deliberate.
    assert manifest.get("MADAR").source_name_en == "Madar"
    assert manifest.get("GPP_ENERGY").source_name_en == "Global Petrol Prices"
    # Both names are kept: the English one is stored BESIDE the Arabic one,
    # never in place of it.
    assert manifest.get("ELSEWEDYSHOP").source_name == "السويدي شوب"


def test_a_source_may_have_no_english_name():
    """Optional by design — a site that answers in one language only must not
    be unrepresentable in the manifest."""
    assert Manifest.model_validate({"sources": [entry()]}).get("MADAR").source_name_en == ""


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
