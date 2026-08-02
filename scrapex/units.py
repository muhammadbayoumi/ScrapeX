"""What one priced thing IS, decided from a per-source charter.

The owner asked for a precise analysis and, more importantly, for a METHOD:
«كل موقع ندخله المفروض نشوف طريقة معينة لقياس وتحديد وحداته ونطور الأمر مع
الوقت». He has hundreds of sites waiting. So the decision cannot live in
Python branches — a branch per site is not a method, it is a pile.

It lives in `sources.yaml`, under the source, as data the owner reads and
approves. This module is the machine that carries a charter out. It knows
nothing about any particular shop.

THE THREE THINGS A CHARTER DECLARES

  witnesses      the fields that may STATE a unit, in rank order, each with
                 its language and what kind of statement it is
  corroborators  fields that may confirm and may never originate — the
                 platform's own numeric weight is one: it is a logistics
                 figure that does not name its unit at all (sikaegshop's
                 "kg" is written in OUR code, not on the site)
  scales.pack    which measurement units can be a SELLING unit here — an
                 allow-list, so anything unlisted is not a candidate

The pack list is what answers the owner's original complaint. «سيكا باكينج
رود 1 سم» carries a number and a unit word in its name, and a rule that
reads them makes one centimetre the selling unit of a product sold by the
metre. cm is simply not on sikaegshop's list, so the name states nothing the
charter can use and the ranked witnesses find «1 Meter» one row lower.

`scales.dimension` also exists — a list of units to strike out of a text
before reading it — and sikaegshop does not use it. It was in the first draft
of that charter, described as the thing that saved the Backing Rods, and
measuring it over all 87 products showed it changed ZERO answers: the
allow-list and the word boundary below were already doing the work. It is
kept as a capability because a site that expresses a dimension in a
pack-scale word will need it; it is not declared where it earns nothing,
because a rule that carries nothing reads like a guarantee and is not one.

WHAT COMES BACK, AND WHY IT IS FOUR THINGS AND NOT ONE

A unit that cannot name where it came from is not a fact, it is a number
someone typed. So a Resolution carries the unit, the quantity, the kind of
statement it was, and the literal text that was read — and the database
refuses a unit that arrives without the last two (migration 0058).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# The unit words the project understands, mapped to the vocabulary in
# `selling_unit`. Arabic spellings are DATA the sites publish, not
# translations: «كيلو» is what the shop wrote, and reading it is capture,
# not interpretation. Longest-first matching happens in _pattern_for.
UNIT_WORDS: dict[str, tuple[str, ...]] = {
    "kg":    ("kg", "kgs", "كجم", "كيلوجرام", "كيلوغرام", "كيلو"),
    "gm":    ("gm", "gms", "g", "gram", "grams", "جرام", "غرام", "جم"),
    "ml":    ("ml", "mls", "millilitre", "milliliter", "مليلتر", "ملي", "مل"),
    "liter": ("liter", "litre", "liters", "litres", "ltr", "l", "لتر"),
    "m":     ("m", "meter", "metre", "meters", "metres", "mtr", "متر", "امتار", "أمتار"),
    "tonne": ("tonne", "tonnes", "ton", "tons", "طن"),
    "piece": ("piece", "pieces", "pcs", "pc", "قطعة", "قطع", "حبة"),
    "mm":    ("mm", "millimetre", "millimeter", "مم", "ملم"),
    "cm":    ("cm", "centimetre", "centimeter", "سم"),
}

# What each unit is CALLED, in both languages. ingest writes these when it
# creates a vocabulary row, because a unit with no words shows the owner a code
# the moment he switches the interface to Arabic. Arabic here is the ordinary
# term, not a translation of the English word — «طن» is what the sites say.
UNIT_NAMES: dict[str, tuple[str, str]] = {
    "kg":    ("kilogram", "كيلوجرام"),
    "gm":    ("gram", "جرام"),
    "ml":    ("millilitre", "مليلتر"),
    "liter": ("litre", "لتر"),
    "m":     ("metre", "متر"),
    "tonne": ("tonne", "طن"),
    "piece": ("piece", "قطعة"),
    "mm":    ("millimetre", "مليمتر"),
    "cm":    ("centimetre", "سنتيمتر"),
    "kWh":   ("kilowatt hour", "كيلوواط ساعة"),
}

# Which vocabulary entry a word belongs to, built once.
_WORD_TO_UNIT = {word: unit for unit, words in UNIT_WORDS.items() for word in words}

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


@dataclass(frozen=True)
class Resolution:
    """One offer's unit, and the statement it was read from."""

    unit: str
    quantity: float
    provenance: str
    witness: str
    raw: str
    raw_lang: str

    @property
    def basis(self) -> str:
        """The quantity as the warehouse writes it — no trailing .0 on whole
        numbers, because "20" is what the shop said and "20.0" is not."""
        whole = int(self.quantity)
        return str(whole) if self.quantity == whole else str(self.quantity)


class Charter:
    """A source's declared way of reading its own units.

    Constructed from the manifest block, never from code. An absent charter
    is not an error and not a default: it means this source has not been
    studied yet, and `resolve` returns None rather than guessing. Guessing is
    the failure mode the whole design exists to prevent.
    """

    def __init__(self, block: dict | None) -> None:
        block = block or {}
        self.version = int(block.get("version") or 1)
        self.witnesses = tuple(
            (w["field"], w.get("lang", "und"), w.get("provenance", "stated_field"))
            for w in block.get("witnesses", ()))
        self.corroborators = tuple(c["field"] for c in block.get("corroborators", ()))
        scales = block.get("scales") or {}
        self.pack = tuple(scales.get("pack", ()))
        self.dimension = tuple(scales.get("dimension", ()))

    def __bool__(self) -> bool:
        return bool(self.witnesses and self.pack)

    def resolve(self, fields: dict[str, str | None]) -> Resolution | None:
        """Ask each witness in turn; the first that speaks decides.

        `fields` maps the names used in the charter to whatever the connector
        read. A field the connector did not capture is simply silent — a
        charter naming a field that does not exist yet is a charter written
        ahead of its connector, which is allowed and which the dry run
        reports.
        """
        if not self:
            return None
        for field, lang, provenance in self.witnesses:
            text = fields.get(field)
            if not text:
                continue
            found = self._read(str(text))
            if found is None:
                continue
            quantity, unit, literal = found
            return Resolution(
                unit=unit,
                quantity=quantity,
                provenance=provenance,
                witness=f"{field}@{lang}/v{self.version}: {literal}",
                raw=literal,
                raw_lang=lang,
            )
        return None

    def _read(self, text: str) -> tuple[float, str, str] | None:
        """The first pack-scale quantity in this text.

        "Sika Fiber Polypropylene 18mm ® 900 gm" is the shape that defeats a
        rule which simply takes the first number-and-unit it finds. Two things
        stop it, and neither is clever: "mm" is not on this site's pack list,
        and the boundary after the unit word refuses to let the "m" in "18mm"
        stand for a metre. What survives is the pack.

        Nothing here ranks or scores. The site's own words are read in the
        order the site wrote them, and only the words it declared can be a
        unit are eligible.
        """
        cleaned = unicodedata.normalize("NFKC", text).translate(_ARABIC_DIGITS)
        if self.dimension:
            cleaned = self._pattern_for(self.dimension).sub(" ", cleaned)
        match = self._pattern_for(self.pack).search(cleaned)
        if not match:
            return None
        number = float(match.group(1).replace(",", "."))
        word = match.group(2).lower()
        unit = _WORD_TO_UNIT.get(word)
        if unit is None or unit not in self.pack:
            return None
        return number, unit, match.group(0).strip()

    @staticmethod
    def _pattern_for(units: tuple[str, ...]) -> re.Pattern[str]:
        words: list[str] = []
        for unit in units:
            words.extend(UNIT_WORDS.get(unit, (unit,)))
        # Longest first, or "m" would match the head of "ml" and a 600 ml
        # tube would be recorded as 600 metres.
        words.sort(key=len, reverse=True)
        alternatives = "|".join(re.escape(word) for word in words)
        # No \b after an Arabic word: the Arabic letters are word characters
        # and a following Arabic letter would be swallowed, so a right-hand
        # boundary is asserted as "not a letter" instead.
        return re.compile(
            r"(\d+(?:[.,]\d+)?)\s*(" + alternatives + r")(?![^\W\d_])",
            re.IGNORECASE | re.UNICODE)


def charter_for(source: dict | None) -> Charter:
    """The charter declared by a manifest entry, or an empty one."""
    return Charter((source or {}).get("unit_charter"))
