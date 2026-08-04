"""«المقاس: 3.25 Kg» — the shop saying what one of these is, read at last.

74 MADAR offers carried a unit nobody could source. The owner ran a full
rebuild on 2026-08-04 expecting it to settle them, because migration 0060 and I
had both recorded that a re-crawl was the fix. All 74 came back identical:
re-fetching cannot teach a charter to look at a field it was never pointed at.

The field was there the whole time. The container witnesses already read
variant_axes for «4 كجم/صندوق»; the same option value on other products says
«3.25 Kg», and nothing read it as a weight.

Measured on the live warehouse before the charter was touched: 55 legacy rows
gain a witness with NO NUMBER CHANGING, 32 unit-less offers gain a unit the
shop states, 0 container readings are altered and 0 stored units contradicted.
"""

from __future__ import annotations

import json

import pytest

from scrapex.config import MANIFEST_FILE, load_manifest
from scrapex.units import Charter


@pytest.fixture(scope="module")
def madar() -> Charter:
    entry = load_manifest(MANIFEST_FILE).get("MADAR")
    return Charter(json.loads(entry.unit_charter.model_dump_json()))


def _axes(**pairs) -> dict:
    """A row as the connector hands it over: six fields, axes as a JSON blob."""
    return {"weight": "", "weight_unit": "", "product_name": "", "product_name_ar": "",
            "variant_axes": json.dumps(pairs, ensure_ascii=False), "variant_axes_ar": ""}


def test_a_size_axis_stating_a_weight_is_read(madar):
    """Offer 1642's sibling rows said 3.25 kg and could not say who told them.
    The axis had said it all along."""
    r = madar.resolve(_axes(Size="3.25 Kg"))

    assert r is not None, "«المقاس» states the weight and the charter still ignores it"
    assert (r.unit, r.quantity) == ("kg", 3.25)
    assert r.provenance == "stated_field"


def test_the_arabic_axis_answers_in_its_own_language(madar):
    """Bilingual capture is the standing rule; a reading carries which language
    answered so «3 كجم» is visibly the Arabic field, not a translation."""
    row = {"weight": "", "weight_unit": "", "product_name": "", "product_name_ar": "",
           "variant_axes": "", "variant_axes_ar": json.dumps({"المقاس": "3 كجم"},
                                                             ensure_ascii=False)}
    r = madar.resolve(row)

    assert r is not None and (r.unit, r.quantity) == ("kg", 3.0)
    assert r.raw_lang == "ar"


def test_a_container_still_outranks_a_bare_weight(madar):
    """THE RANKING THAT MATTERS. «4 كجم/صندوق» is a box you buy and four
    kilograms you get. The container witness is ranked first precisely so this
    new one cannot demote a box back to the four kilograms 0060 rescued it
    from. Measured over 3,550 live offers: zero container readings altered."""
    row = {"weight": "", "weight_unit": "", "product_name": "", "product_name_ar": "",
           "variant_axes": "",
           "variant_axes_ar": json.dumps({"المقاس": "4 كجم/صندوق"}, ensure_ascii=False)}
    r = madar.resolve(row)

    assert r is not None
    assert r.unit == "box", "the box became four kilograms again"
    assert r.content_quantity == 4.0 and r.content_unit == "kg"


@pytest.mark.parametrize("axis", [
    {"amperage": "20A"}, {"amperage": "20 A"}, {"gangs": "1 Gang"},
    {"Poles": "1P"}, {"Feature": "2BB"}, {"Size": "8 In"},
])
def test_a_word_that_is_not_a_measurement_can_never_be_a_selling_unit(madar, axis):
    """DEFENCE ONE — units.py's own vocabulary. Amperes, gangs, poles, bearing
    counts and inches are not measurements this project knows, so no charter
    can admit them however its pack list is written. These option values are
    real and counted live: amperage on 54 offers, gangs on 190."""
    assert madar.resolve(_axes(**axis)) is None


def test_a_real_measurement_that_is_not_a_selling_unit_here_is_refused(madar):
    """DEFENCE TWO — the pack allow-list, and the one that can be widened by
    mistake. A millimetre IS a measurement; it is not what one of these is. 57
    live offers carry «Size: 20 mm».

    I first wrote that the allow-list refused the amperage cases too. It does
    not — they never reach it. Two mechanisms, and only this one is a list
    someone can edit."""
    assert madar.resolve(_axes(Size="20 mm")) is None
    assert madar.resolve(_axes(Size="18 cm")) is None


def test_a_tonne_of_steel_is_a_thing_this_shop_sells(madar):
    """tonne IS on the pack list, so «Size: 1 Ton» resolves. Recorded because it
    is a consequence of this charter that a reader should not have to discover
    from the data."""
    r = madar.resolve(_axes(Size="1 Ton"))

    assert r is not None and (r.unit, r.quantity) == ("tonne", 1.0)


def test_a_dimension_and_a_weight_together_take_the_weight(madar):
    """Option values carry several axes at once. The pack list picks the one
    that can be a selling unit and leaves the rest alone."""
    r = madar.resolve(_axes(Size="500 g", Feature="Wooden Handle"))

    assert r is not None and (r.unit, r.quantity) == ("gm", 500.0)


def test_the_charter_still_answers_nothing_where_the_shop_says_nothing(madar):
    """3,411 of MADAR's offers state no unit anywhere, and the owner's ruling is
    that the column stays empty rather than being filled by inference —
    «الحقائق الخام فقط»."""
    assert madar.resolve(_axes(Color="White")) is None
    assert madar.resolve(_axes(**{"Cement Type": "Sulphate Resistant Cement"})) is None
