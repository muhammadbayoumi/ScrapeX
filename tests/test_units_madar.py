"""What one thing is, when the shop names a container and what is in it.

MADAR's own option values say «4 كجم/صندوق» and "1000 Pcs/Box" — a box you buy
and four kilograms you get. Eighteen offers are stored today as kg with a basis
of 3 or 4, which is this warehouse choosing one of the shop's two facts and
throwing away the other.
"""

from __future__ import annotations

import json
import pathlib

import yaml

from scrapex.units import Charter, charter_for

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _madar() -> dict:
    manifest = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    sources = manifest["sources"] if isinstance(manifest, dict) and "sources" in manifest else manifest
    return next(s for s in sources if s.get("source_key") == "MADAR")


def test_the_container_is_the_unit_and_its_contents_are_kept_beside_it():
    """«4 كجم/صندوق» — verbatim from a live MADAR option value.

    The box is what one price buys. The four kilograms are what is in it. Both
    are published, so both are stored, and price-per-kg becomes arithmetic over
    two stated facts instead of a rewrite of one."""
    charter = charter_for(_madar())

    resolution = charter.resolve({
        "variant_axes_ar": json.dumps({"المقاس": "4 كجم/صندوق"}, ensure_ascii=False),
    })

    assert resolution is not None
    assert (resolution.unit, resolution.basis) == ("box", "1")
    assert (resolution.content_quantity, resolution.content_unit) == (4.0, "kg")
    assert resolution.raw == "4 كجم/صندوق"
    assert resolution.raw_lang == "ar"


def test_the_english_spelling_of_the_same_fact_reads_the_same():
    """"1000 Pcs/Box" is the same statement in the other language, on 22 of the
    52. The Arabic axis is asked first because it is the site's own, and either
    resolves to the same canonical box."""
    resolution = charter_for(_madar()).resolve({
        "variant_axes": json.dumps({"Size": "1000 Pcs/Box"}),
    })

    assert (resolution.unit, resolution.basis) == ("box", "1")
    assert (resolution.content_quantity, resolution.content_unit) == (1000.0, "piece")


def test_a_size_on_the_same_axis_is_not_read_as_a_container():
    """The axis that holds "1000 Pcs/Box" also holds "1-1/2\"" — the same
    «number / something» shape, meaning a fraction of an inch.

    What refuses it is the reader requiring LETTERS on both sides of the slash,
    not the container list: a fraction never reaches the list at all. I claimed
    the opposite in three places and the measurement corrected it."""
    charter = charter_for(_madar())

    for size in ('1-1/2"', "1 1/2", "1-1/4\"", "2 1/2"):
        assert charter.resolve({"variant_axes": json.dumps({"Size": size})}) is None, (
            f"{size!r} is a size and was read as a container")


def test_without_the_container_list_one_box_becomes_two_units():
    """The rule-removal test, aimed at what the list ACTUALLY does.

    MADAR writes «صندوق» on the Arabic axis and "box" on the English one for
    the same box. The list maps both to one code. Measured without it: 16
    offers under «صندوق» and 24 under "box" — two selling units for one shop's
    container, and two prices for the same product that no longer compare."""
    block = _madar()["unit_charter"]

    class _AcceptAnyWord(dict):
        def get(self, key, default=None):
            return key                      # every word is its own container

    without = Charter(block)
    without.containers = _AcceptAnyWord()

    arabic = without.resolve({"variant_axes_ar": json.dumps(
        {"المقاس": "4 كجم/صندوق"}, ensure_ascii=False)})
    english = without.resolve({"variant_axes": json.dumps({"Size": "4 Kg/Box"})})

    assert arabic.unit != english.unit, (
        "removing the list changed nothing, so the list is not what unifies "
        "the two languages and this test guards nothing")

    with_list = charter_for(_madar())
    assert with_list.resolve({"variant_axes_ar": json.dumps(
        {"المقاس": "4 كجم/صندوق"}, ensure_ascii=False)}).unit == "box"
    assert with_list.resolve({"variant_axes": json.dumps(
        {"Size": "4 Kg/Box"})}).unit == "box"


def test_madar_declares_no_weight_witness_and_the_reason_is_written_down():
    """The first draft of this charter read weight + storeConfig's weight_unit
    and would have resolved 3,480 of 3,537 offers. It was withdrawn, and the
    withdrawal is the finding.

    Measured over all 6,764 MADAR observations: price/weight has a median of
    3.46, a 99th percentile of 1,253 and a maximum of 38,923; within single
    products, Steel Square Tube runs 2.81 to 374.72. A price of 38,923 "per
    kilogram" is not a price per kilogram, so `weight` is the quoting basis for
    some products and a piece mass for others — which is what magento.py says
    in writing, and what the owner ruled on 2026-07-29: «الحقائق الخام فقط».

    A store-wide weight_unit is the shop saying "my weight numbers are in kg".
    It is not the shop saying what one of THIS product is."""
    charter = charter_for(_madar())

    assert all(shape == "container" for shape in charter.shapes), (
        "MADAR gained a witness that is not a container; if it reads `weight`, "
        "it is asserting a unit for thousands of rows the shop never gave one")

    # And the state that would have been resolved stays silent, as ruled.
    assert charter.resolve({"weight": "1000", "weight_unit": "kg"}) is None


def test_a_source_charter_change_cannot_reach_another_source():
    """MADAR's charter is MADAR's. sikaegshop resolves from a product name and
    knows nothing about containers; the two must not leak into each other."""
    manifest = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    sources = manifest["sources"] if isinstance(manifest, dict) and "sources" in manifest else manifest
    sika = charter_for(next(s for s in sources if s.get("source_key") == "SIKAEGSHOP"))

    assert not sika.containers, "sikaegshop declares containers it has no use for"
    assert charter_for(_madar()).witnesses[0][0].startswith("variant_axes")
    assert sika.witnesses[0][0] == "product_name"
