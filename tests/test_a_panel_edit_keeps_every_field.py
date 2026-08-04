"""Editing a source from the panel used to delete eight of its fields.

The owner's standing rule is that the extension is the control room — every
web feature must be reachable from it. Editing a source is, and the edit path
REPLACES the whole YAML block with one rebuilt from a hand-written list of
field names. Anything SourceEntry grew after that list was written fell out of
the file, silently, on the first edit:

    source_name_ar   every bilingual source's Arabic name
    default_language an English shop reverts to the Arabic default, and 1,789
                     product names are re-filed under the wrong column
    unit_charter     MADAR's per-source unit rules cease to exist
    brand api taxonomy user_agent tax

Nothing failed. The manifest still validated, because every one of those
fields is optional.

This test does not name those eight. It round-trips every source the project
actually ships and compares every field the model has, so a field added
tomorrow is covered without anyone remembering this file exists.
"""

from __future__ import annotations

import yaml
import pytest

from scrapex.config import MANIFEST_FILE, SourceEntry, load_manifest
from scrapex.manifest_io import entry_to_block

_SOURCES = load_manifest(MANIFEST_FILE).sources


@pytest.mark.parametrize("entry", _SOURCES, ids=lambda e: e.source_key)
def test_a_panel_edit_returns_the_source_unchanged(entry):
    """THE ONE THAT MATTERS. An edit is a replacement, so a field this cannot
    write is a field the edit deletes."""
    rebuilt = SourceEntry.model_validate(yaml.safe_load(entry_to_block(entry))[0])

    lost = [name for name in SourceEntry.model_fields
            if getattr(entry, name, None) != getattr(rebuilt, name, None)]

    assert lost == [], (
        f"editing {entry.source_key} from the panel would delete {lost} — the "
        "block is rebuilt from a list of field names, and these are not on it")


def test_the_charter_survives_because_it_is_the_expensive_one():
    """Named on its own because losing it is not a cosmetic loss: a charter is
    days of measurement against a live site, and it is the difference between
    «4 كجم/صندوق» being a box and being four kilograms."""
    madar = load_manifest(MANIFEST_FILE).get("MADAR")
    rebuilt = SourceEntry.model_validate(yaml.safe_load(entry_to_block(madar))[0])

    assert rebuilt.unit_charter is not None
    assert rebuilt.unit_charter == madar.unit_charter


def test_a_default_is_still_omitted_so_the_yaml_stays_short():
    """The fix must not turn every entry into a wall of nulls. A value equal to
    the model's own default round-trips to the same thing whether it is written
    or not, so it stays out."""
    plain = SourceEntry(source_key="PLAIN", source_name="Plain",
                        base_url="http://x", family="shopify-json", cadence="daily",
                        authority="shop", currency="EGP", default_region="EG",
                        vat_mode="incl",
                        extract=[{"kind": "product_prices", "scope": "census"}])
    block = yaml.safe_load(entry_to_block(plain))[0]

    assert "unit_charter" not in block
    assert "default_language" not in block, "the Arabic default does not need writing"
    assert SourceEntry.model_validate(block).default_language == "ar"
