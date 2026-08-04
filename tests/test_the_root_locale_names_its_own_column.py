"""An English shop's English titles were filed as Arabic, on 1,789 products.

SPARK_ESHOP serves English at its root and has no /en locale at all — that URL
answers 404, verified live. The shopify connector had "this store answers in
Arabic" written into it as an assumption: it filed the root title into
product_name_ar unconditionally, then fetched /en to fill product_name. The
fetch failed, the note said "names stay single-language this run", and every
English title sat under a heading that says Arabic while the English column —
which config.py calls required — stayed empty on all 1,789.

Nothing failed. The crawl reported success, 3,149 rows.
"""

from __future__ import annotations

import pathlib

import pytest

from scrapex.connectors.shopify import _root_title


def test_an_english_shop_fills_the_english_column():
    """«ABB 1SDA100487R1 | XT5H 630 TMA 630-6300» is not Arabic. Filing it
    under the _ar heading is not incomplete data, it is a mislabelled fact —
    and the AR|EN switch then shows a reader English where it promised
    Arabic, which is worse than a blank."""
    row = _root_title("ABB 1SDA100487R1 | XT5H 630 TMA 630-6300", "en")

    assert row == {"product_name": "ABB 1SDA100487R1 | XT5H 630 TMA 630-6300"}
    assert "product_name_ar" not in row


def test_an_arabic_shop_still_fills_the_arabic_column():
    """ELSEWEDYSHOP genuinely serves Arabic at its root and English at /en —
    measured live: «كشاف واجهات400وات اضاءة ابيض IP 65» against "Luma
    floodlight 400W IP65 6500K", 0 of 3 titles identical. Nothing about that
    source may change."""
    row = _root_title("كشاف واجهات400وات اضاءة ابيض IP 65", "ar")

    assert row == {"product_name_ar": "كشاف واجهات400وات اضاءة ابيض IP 65"}
    assert "product_name" not in row


def test_the_default_is_arabic_because_that_is_what_every_source_assumed():
    """The field defaults rather than being required, and the default is the
    assumption that was already baked in — so no existing source changes
    behaviour by gaining a field it never declared. A default of "en" would
    silently rewrite eleven sources' columns."""
    from scrapex.config import SourceEntry

    entry = SourceEntry(source_key="TEST_SHOP", source_name="Test", base_url="http://x",
                        family="shopify-json", cadence="daily", authority="shop",
                        currency="EGP", default_region="EG", vat_mode="incl",
                        extract=[{"kind": "product_prices", "scope": "census"}])
    assert entry.default_language == "ar"


def test_a_language_the_project_does_not_capture_is_refused():
    """Two columns exist, so two languages are declarable. A third would name a
    column that is not there, and it would fail at the moment a crawl wrote
    into nothing rather than at the moment someone typed it."""
    from pydantic import ValidationError
    from scrapex.config import SourceEntry

    with pytest.raises(ValidationError):
        SourceEntry(source_key="TEST_SHOP", source_name="Test", base_url="http://x",
                    family="shopify-json", cadence="daily", authority="shop",
                    currency="EGP", default_region="EG", vat_mode="incl",
                    default_language="fr",
                    extract=[{"kind": "product_prices", "scope": "census"}])


def test_the_connector_asks_for_the_other_locale_not_always_english():
    """The second pass fetches whatever the root is NOT. Asking an
    English-rooted shop for /en is asking for a page that does not exist, and
    the 404 was read as "this shop has one language" rather than "I asked the
    wrong question"."""
    source = pathlib.Path(
        __import__("scrapex.connectors.shopify", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")

    assert 'other_locale = "ar" if source.default_language == "en"' in source, (
        "the connector asks for /en regardless of what the shop serves")
    assert "{base}/{locale}/products.json" in source, (
        "the second-locale URL is hardcoded to one language again")


def test_the_note_says_which_column_the_names_stayed_in():
    """The old note — "names stay single-language this run" — was true and
    useless. It is the one sentence that explained 1,789 mislabelled products,
    it was written to the job log, and it did not say the thing a reader
    needed: which column they are in."""
    source = pathlib.Path(
        __import__("scrapex.connectors.shopify", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")

    assert "column this run" in source
    assert "product_name" in source.split("locale unavailable")[1][:400], (
        "the warning still does not name the column the reader must look in")
