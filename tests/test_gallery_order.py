"""Issue #35 — the shop chose which picture leads, and the read threw it away.

Every connector ranks a product's pictures and records the rank the only place
the row format offers: inside `attribute_code` (`image`, `image_1`, `image_2`…).
Both readers in `reports.py` then sorted by `attribute_group, attribute_label,
raw_value`, and all six connectors write the identical label "Image" — so group
tied, label tied, and the effective sort key was the FILE NAME, alphabetically.
The card renders the first row it is handed (`grid.js` productSummaryCard), so
the main picture was the one whose file happened to sort first.

WHY A CAPTURED FIXTURE, AND WHY THIS ONE
----------------------------------------
`fixtures/live/elsewedyshop_gallery_order_2026-08-01.json`, captured from the
live shop (see the CAPTURE note beside it). Three products, chosen because a
fixture whose two orders AGREE proves nothing — it passes with the defect fully
in place, which is how six connectors could each carefully rank their pictures
and nobody noticed the ranking never arrived:

  8931923394860   7 pictures. The shop leads with `FHSDK47-6.jpg`, which sorts
                  SEVENTH OF SEVEN alphabetically. The shop's first is the
                  alphabetically LAST — the two orders disagree maximally.
  9718091219244   3 pictures whose two orders agree. Guards the other
                  direction: the fix must not be "reverse it" or "shuffle".
  10157311557932  1 picture. The common case, which has no ordering question
                  and must come out untouched.

Nothing here downloads an image; the URL is the record.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.shopify import ShopifyConnector
from scrapex.ingest import ingest_payloads
from scrapex.reports import export_details_table, product_attributes, stated_order
from scrapex.vocab import DetailGroup, ExtractKind, ExtractScope

FIXTURE = (Path(__file__).parent / "fixtures" / "live"
           / "elsewedyshop_gallery_order_2026-08-01.json")

# The product the shop and the alphabet disagree about, and the two guards.
DISAGREES = "8931923394860"
AGREES = "9718091219244"
ONE_PICTURE = "10157311557932"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _product(product_id: str) -> dict:
    for product in _payload()["products"]:
        if str(product["id"]) == product_id:
            return product
    raise AssertionError(f"{product_id} is not in the fixture")


def _file_names(product: dict) -> list[str]:
    return [str(i["src"]).rsplit("/", 1)[-1].split("?")[0]
            for i in product["images"]]


def _entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ELSEWEDYSHOP", source_name="Elsewedy",
        base_url="https://elsewedyshop.com", family="shopify-json",
        currency="EGP", default_region="EG", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT,
                             scope=ExtractScope.CENSUS)]))


def _tables():
    """The connector run over the captured bytes — no request is made."""
    body = _payload()

    class _Resp:
        def __init__(self, payload): self._payload = payload
        def json(self): return self._payload

    class _Fetcher:
        def get(self, url, **kwargs):
            first = "page=1" in url and "/en/" not in url
            return _Resp(body if first else {"products": []})

    return list(ShopifyConnector(_Fetcher()).fetch(_entry()))


@pytest.fixture
def warehouse():
    """The SECOND crawl, not the first ingest.

    Production is never a fresh database. Ingesting twice also proves the fix
    does not quietly depend on rows arriving in insertion order — the upsert on
    the second pass is free to touch them in any order it likes.
    """
    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    payloads = [t.to_payload() for t in _tables()]
    first = ingest_payloads(conn, _entry(), payloads)
    assert first.errors == [], first.errors[:3]
    second = ingest_payloads(conn, _entry(), payloads)
    assert second.errors == [], second.errors[:3]
    yield conn
    conn.close()


def _offer_of(conn: sqlite3.Connection, product_id: str) -> int:
    row = conn.execute(
        "SELECT so.offer_id FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.external_product_id = ? LIMIT 1", (product_id,)).fetchone()
    assert row, f"product {product_id} never reached the warehouse"
    return row[0]


def _gallery(conn: sqlite3.Connection, product_id: str) -> list[dict]:
    """Exactly what the card is handed: the Media rows, in the order given.

    `grid.js` filters `group === "Media"` and renders `images[0]`, adding no
    sort of its own — so this list IS the gallery, and its head IS the main
    picture the owner sees.
    """
    return [d for d in product_attributes(conn, _offer_of(conn, product_id))
            if d["group"] == DetailGroup.MEDIA.value and d["url"]]


# ---------------------------------------------------------------------------
# The fixture has to be able to fail. Checked, not assumed.
# ---------------------------------------------------------------------------
def test_the_fixture_actually_disagrees_or_this_whole_file_proves_nothing():
    """A gallery already in alphabetical order passes with the defect intact."""
    names = _file_names(_product(DISAGREES))

    assert len(names) == 7
    assert names != sorted(names), "fixture cannot detect an alphabetical sort"
    assert names[0] == sorted(names)[-1], (
        "the shop's own first picture must be the alphabetically LAST, so a "
        f"filename sort is unmistakable: {names}")


# ---------------------------------------------------------------------------
# THE DEFECT — the card
# ---------------------------------------------------------------------------
def test_the_card_leads_with_the_picture_the_shop_leads_with(warehouse):
    """The one the issue is about. Fails on `ORDER BY … raw_value`, which hands
    the card `FHSDK47-1_2.jpg` — the alphabetically first — as the main."""
    shop = [i["src"] for i in _product(DISAGREES)["images"]]

    gallery = _gallery(warehouse, DISAGREES)

    assert gallery[0]["url"] == shop[0], (
        "the card is showing a picture the shop did not choose: "
        f"{gallery[0]['url']} instead of {shop[0]}")


def test_the_whole_gallery_is_the_shops_sequence_not_just_its_head(warehouse):
    """Fixing only `[0]` would leave the thumbnails and the ‹ › arrows walking
    the pictures in filename order behind a correct-looking main image."""
    shop = [i["src"] for i in _product(DISAGREES)["images"]]

    gallery = _gallery(warehouse, DISAGREES)

    assert [g["url"] for g in gallery] == shop
    assert [g["code"] for g in gallery] == \
        ["image"] + [f"image_{n}" for n in range(1, len(shop))]


def test_the_rank_is_decoded_as_a_number_not_compared_as_text(warehouse):
    """`ORDER BY attribute_code` is lexicographic: `image_10` would land before
    `image_2`, and bare `image` after both. Ten pictures is where a text sort
    and a positional one part company, and no live fixture here has ten."""
    product_id = _offer_of(warehouse, ONE_PICTURE)
    row = warehouse.execute(
        "SELECT sp.source_product_id FROM source_product sp "
        "JOIN source_variant sv ON sv.source_product_id = sp.source_product_id "
        "JOIN source_offer so ON so.source_variant_id = sv.source_variant_id "
        "WHERE so.offer_id = ?", (product_id,)).fetchone()
    for n in range(1, 12):
        warehouse.execute(
            "INSERT INTO source_product_attribute (source_product_id, "
            " attribute_code, attribute_label, raw_value, value_url, "
            " attribute_group) VALUES (?,?,?,?,?,?)",
            (row[0], f"image_{n}", "Image", f"z{n}.jpg",
             f"https://elsewedyshop.com/x/z{n}.jpg", DetailGroup.MEDIA.value))

    codes = [g["code"] for g in _gallery(warehouse, ONE_PICTURE)]

    assert codes == ["image"] + [f"image_{n}" for n in range(1, 12)], codes
    assert codes.index("image_2") < codes.index("image_10")


# ---------------------------------------------------------------------------
# THE DEFECT — the export, which had no third sort key at all
# ---------------------------------------------------------------------------
def test_the_export_hands_over_the_same_sequence_as_the_card(warehouse):
    """`export_details_table` ordered by group and label only, so the pictures
    came out in whatever order SQLite happened to produce. A spreadsheet that
    disagrees with the screen about which picture is first is the same defect
    filed twice."""
    header, rows = export_details_table(warehouse, "ELSEWEDYSHOP")
    name = _product(DISAGREES)["title"]
    url_at = header.index("value_url")
    exported = [r[url_at] for r in rows
                if r[header.index("group")] == DetailGroup.MEDIA.value
                and name in (r[0], r[1])]

    assert exported == [i["src"] for i in _product(DISAGREES)["images"]]
    assert exported == [g["url"] for g in _gallery(warehouse, DISAGREES)]


# ---------------------------------------------------------------------------
# What the fix must not disturb
# ---------------------------------------------------------------------------
def test_one_picture_is_one_picture_and_nothing_about_it_moves(warehouse):
    """475 of the 750 products on the captured pages publish exactly one. There
    is no ordering question there and the fix must not invent one."""
    gallery = _gallery(warehouse, ONE_PICTURE)

    assert len(gallery) == 1
    assert gallery[0]["code"] == "image"
    assert gallery[0]["url"] == _product(ONE_PICTURE)["images"][0]["src"]


def test_a_gallery_the_alphabet_already_agreed_with_comes_out_unchanged():
    """The fix is "restore the shop's order", not "reverse the old one"."""
    names = _file_names(_product(AGREES))
    assert names == sorted(names), "this guard needs an agreeing gallery"

    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    payloads = [t.to_payload() for t in _tables()]
    ingest_payloads(conn, _entry(), payloads)
    try:
        gallery = _gallery(conn, AGREES)
        assert [g["url"] for g in gallery] == \
            [i["src"] for i in _product(AGREES)["images"]]
    finally:
        conn.close()


def test_no_two_media_rows_of_one_product_hold_the_same_url(warehouse):
    """MADAR shipped `image` and `image_1` pointing at one picture on 576
    products (fixed at capture, commit 105189c). Reading the rank back must not
    reintroduce it from the other end — this read renumbers nothing, and this
    is the assertion that says so out loud."""
    for product_id in (DISAGREES, AGREES, ONE_PICTURE):
        gallery = _gallery(warehouse, product_id)
        urls = [g["url"] for g in gallery]
        codes = [g["code"] for g in gallery]
        assert len(set(urls)) == len(urls), f"{product_id} stores one URL twice"
        assert len(set(codes)) == len(codes), f"{product_id} reuses a code"


def test_an_attribute_carrying_no_number_is_ordered_exactly_as_before(warehouse):
    """The new key decodes a rank out of the code. A code that states none —
    `sku`, `brand`, `color` — must yield the same rank for every row, so
    `raw_value` goes on deciding those and nothing outside the gallery moves.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE spa (attribute_code TEXT, raw_value TEXT)")
    conn.executemany("INSERT INTO spa VALUES (?,?)",
                     [("color", "red"), ("color", "amber"), ("color", "blue")])

    ranked = [r[0] for r in conn.execute(
        f"SELECT raw_value FROM spa ORDER BY {stated_order('spa')}, raw_value")]
    plain = [r[0] for r in conn.execute(
        "SELECT raw_value FROM spa ORDER BY raw_value")]

    assert ranked == plain == ["amber", "blue", "red"]
    conn.close()
