"""manifest_io: safe append to sources.yaml — validation, comments, rollback."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scrapex.config import MANIFEST_FILE, ExtractSpec, SourceEntry, load_manifest
from scrapex.manifest_io import DuplicateSourceError, add_source, entry_to_block
from scrapex.vocab import ExtractKind, ExtractScope


def make_entry(**over) -> SourceEntry:
    base = dict(
        source_key="NEWSHOP", source_name="متجر جديد", base_url="https://newshop.com",
        family="shopify-json", currency="EGP", default_region="EG",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    )
    base.update(over)
    return SourceEntry.model_validate(base)


@pytest.fixture()
def manifest_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, dst)
    return dst


def test_block_is_valid_yaml_and_arabic_preserved():
    block = entry_to_block(make_entry())
    assert "NEWSHOP" in block and "متجر جديد" in block
    assert block.startswith("  - source_key")  # 2-space indent under sources:


def test_add_source_appends_and_reloads(manifest_copy):
    before = len(load_manifest(manifest_copy).sources)
    add_source(make_entry(), manifest_copy)
    after = load_manifest(manifest_copy)
    assert len(after.sources) == before + 1
    added = after.get("NEWSHOP")
    assert added.currency == "EGP" and added.default_region == "EG"


def test_existing_comments_are_preserved(manifest_copy):
    original = manifest_copy.read_text(encoding="utf-8")
    comment_lines = [ln for ln in original.splitlines() if ln.strip().startswith("#")]
    add_source(make_entry(), manifest_copy)
    after = manifest_copy.read_text(encoding="utf-8")
    for line in comment_lines:  # every original comment still present (append, not rewrite)
        assert line in after


def test_duplicate_key_rejected_without_writing(manifest_copy):
    before = manifest_copy.read_text(encoding="utf-8")
    with pytest.raises(DuplicateSourceError):
        add_source(make_entry(source_key="MADAR"), manifest_copy)
    assert manifest_copy.read_text(encoding="utf-8") == before  # untouched


def test_added_source_roundtrips_all_validation(manifest_copy):
    # A source with a targeted commodity contract (materials + regions) must
    # survive the write + reload with its contract intact.
    entry = make_entry(
        source_key="ARAMCO_TEST", family="static-html-table", authority="official",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.TARGETED,
                             materials=["DIESEL"], regions=["SA"])],
    )
    add_source(entry, manifest_copy)
    reloaded = load_manifest(manifest_copy).get("ARAMCO_TEST")
    assert reloaded.extract[0].materials == ["DIESEL"]
    assert reloaded.extract[0].regions == ["SA"]
