"""What one priced thing IS, and who said so.

The owner's complaint, in his words: «الوحدات احيانا ضمن الوصف او ضمن
الاختيارات variant — يعنى مثلا plywood دا وحدته sheet ولكن له ابعاد محددة
تختلف عن sheet اخر بابعاد اخرى. فى وحدات للمواسير ماسورة ولكن هناك ابعاد
مختلفة كأطوال وسمك وتخانة وضغط.»

Every case below is a real product from the live warehouse, quoted.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from scrapex.units import Charter, charter_for

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _sika() -> dict:
    manifest = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    sources = manifest["sources"] if isinstance(manifest, dict) and "sources" in manifest else manifest
    return next(s for s in sources if s.get("source_key") == "SIKAEGSHOP")


def test_a_source_with_no_charter_says_nothing_rather_than_guessing():
    """An absent charter is not a default and not an error: it means this
    source has not been studied. Ten of the eleven sources are in that state
    today, and a resolver that guessed for them would fill the warehouse with
    numbers nobody could defend — which is the situation this work exists to
    end, not to automate."""
    blank = charter_for({"source_key": "SOMETHING_NEW"})

    assert not blank
    assert blank.resolve({"product_name": "Cement bag 50 kg"}) is None


def test_the_diameter_in_the_name_is_not_the_selling_unit():
    """THE ACCEPTANCE TEST. «سيكا باكينج رود 1 سم» — the name states a
    number and a unit word, and reading them naively makes ONE CENTIMETRE the
    selling unit of a product the shop sells by the metre. This is the
    owner's original complaint in its smallest form.

    What saves it is not cleverness and — measured — not the thing I first
    claimed. My charter declared cm and mm as a separate "dimension scale"
    and that declaration changed ZERO of the 87 answers, so it was removed.
    Two plainer things do the work: cm is not in this site's `pack` list, so
    it is never a candidate at all; and the ranked witnesses then find «1
    Meter» one row lower."""
    charter = charter_for(_sika())

    resolution = charter.resolve({
        "product_name": "Sika Backing ® Rod 1 CM",
        "product_name_ar": "سيكا باكينج رود 1 سم",
        "attr_1": "1 Meter",
        "attr_1_ar": "1 متر",
    })

    assert resolution is not None
    assert (resolution.unit, resolution.basis) == ("m", "1")
    assert resolution.provenance == "stated_in_prose"
    assert resolution.witness == "attr_1@en/v1: 1 Meter"


def test_removing_the_pack_allow_list_breaks_exactly_that_case():
    """The rule-removal test, aimed at the rule that actually carries the
    weight. A charter test asserting only an outcome passes for the wrong
    reason as easily as the right one — and this file's first version proved
    it, by attributing the Backing Rod's rescue to a declaration that turned
    out to do nothing.

    Widen `pack` to admit cm and the diameter in the name wins immediately."""
    block = _sika()["unit_charter"]
    widened = Charter({**block, "scales": {"pack": list(block["scales"]["pack"]) + ["cm"]}})

    resolution = widened.resolve({
        "product_name": "Sika Backing ® Rod 1 CM",
        "attr_1": "1 Meter",
    })

    assert resolution is not None
    assert resolution.unit == "cm", (
        "with cm admitted as a selling unit the name wins and the rod is "
        "recorded as one centimetre — the owner's original complaint")
    assert resolution.unit != "m"


def test_the_name_settles_a_conflict_on_this_site_and_the_ruling_is_recorded():
    """Owner ruling 2026-08-02, after checking the page himself: «اسم المنتج
    يحسم كل شى بالنسبة لموقع سيكا (قاعدة لا تعمم)».

    Product 261 states 20 KG in its name, «20 كيلو» in the shop's authored
    spec row, and 1 in the platform's numeric weight field — the owner saw
    all three on the page. Today the platform field wins and the unit is
    dropped entirely. The ruling belongs to this source, so the test asserts
    it is written in this source's charter and nowhere shared."""
    sika = _sika()
    charter = charter_for(sika)

    first = charter.witnesses[0]
    assert first[0] == "product_name", (
        "the name is no longer the top witness for a site whose owner ruled "
        "that the name decides")
    assert "weight" in charter.corroborators, (
        "the platform's numeric field must be able to confirm and never to "
        "originate — it does not name its own unit")
    assert "weight" not in [w[0] for w in charter.witnesses]

    resolution = charter.resolve({
        "product_name": "Sika Creat 114 ® 20 KG",
        "product_name_ar": "سيكا كريت 114- 20 كيلو",
        "attr_3": "20 kg",
        "weight": "1",
    })
    assert (resolution.unit, resolution.basis) == ("kg", "20")


def test_the_arabic_name_alone_can_state_the_unit():
    """Bilingual capture is not decoration here. «سيكا لاتكس -5 كيلو» states
    the pack in Arabic, and a resolver that reads only English would drop it.
    Nothing is translated: «كيلو» is the word the shop wrote and reading it
    is capture."""
    charter = charter_for(_sika())

    resolution = charter.resolve({"product_name": None, "product_name_ar": "سيكا لاتكس -5 كيلو"})

    assert (resolution.unit, resolution.basis) == ("kg", "5")
    assert resolution.raw_lang == "ar"
    assert "كيلو" in resolution.witness


@pytest.mark.parametrize("name,unit,basis", [
    ("Sika Fiber Polypropylene 18mm ® 900 gm", "gm", "900"),
    ("Sika Flex Pro 3  Purform white 600 ml", "ml", "600"),
    ("Sika Swell 2010 10 Meter", "m", "10"),
    ("Sika Gard 701 W 20KG", "kg", "20"),
])
def test_a_dimension_before_a_pack_size_does_not_win_by_being_first(name, unit, basis):
    """"18mm ® 900 gm" is the shape that defeats any rule which simply takes
    the first number-and-unit it finds. Position does not decide it: "mm" is
    not a candidate at all, and the boundary after the unit word stops the
    "m" in "18mm" being read as a metre. What is left is the pack."""
    resolution = charter_for(_sika()).resolve({"product_name": name})

    assert (resolution.unit, resolution.basis) == (unit, basis)


def test_millilitres_are_not_metres():
    """Longest-first matching, asserted rather than assumed: "m" is a unit
    word and it is the head of "ml", so a naive alternation records a 600 ml
    tube as 600 metres."""
    resolution = charter_for(_sika()).resolve({"product_name": "Sealant 600 ml"})

    assert resolution.unit == "ml"


def test_every_resolution_can_name_the_field_it_was_read_from():
    """Migration 0058 makes the database refuse a unit with no witness. This
    asserts the resolver can always supply one — a unit whose origin cannot
    be stated is not a fact, it is a number someone typed, and the warehouse
    already holds 1,064 of those."""
    charter = charter_for(_sika())

    for fields in ({"product_name": "Sika Gard 701 W 20KG"},
                   {"product_name_ar": "سيكا لاتكس -5 كيلو"},
                   {"attr_1": "1 Meter"}):
        resolution = charter.resolve(fields)
        assert resolution.provenance
        assert resolution.witness
        assert resolution.raw and resolution.raw_lang
        # The witness names the field, the language, the charter version and
        # the literal text — enough to re-read the same statement later.
        assert "@" in resolution.witness and "/v" in resolution.witness
