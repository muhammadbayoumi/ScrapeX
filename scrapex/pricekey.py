"""What makes two prices comparable (spec: price-history storage semantics).

The owner-facing price history is a timeline of REAL price changes, not a daily
copy of an unchanged row. Deciding "did the price change?" needs a hash — and
the whole design turns on what goes into it.

**Everything that makes two prices non-comparable belongs in the key**, not just
the money:

    the money        price, currency, VAT basis
    the denomination unit of measure, region
    what is priced   manufacturer, country of origin, specification

50kg of cement from two different factories is not one price series. Neither is
15 USD/litre and 15 USD/gallon. If any of these differ, the earlier price is not
comparable to the later one and a new price period opens.

**Availability and stock are deliberately NOT here.** The owner wants the latest
state, not its history: a stock movement must never look like a price change.
They live in current state, updated in place, and generate no history at all.

**Fields are dynamic, because stores differ.** Most shops give no manufacturer;
almost none give a country of origin. A field that is absent contributes nothing
— it is not hashed as an empty string, which would be a value like any other.
Each observation therefore records WHICH fields its key was built from, and
comparison happens on the fields two observations share. That is what makes a
store starting to publish a manufacturer a moment where ScrapeX learns something,
rather than a day when every price in the warehouse appears to change.
"""
from __future__ import annotations

from dataclasses import dataclass

from .normalize import normalize_name, record_hash

# Bumped only when the MEANING of a field changes (a different normalizer, a
# renamed key). A bump re-baselines every offer instead of reporting a price
# change, because nothing about the price actually moved.
PRICE_KEY_VERSION = 1

# The money. Always present — a row without them cannot be ingested at all, so
# their absence is never a reason for two keys to be incomparable.
MONEY_FIELDS = ("effective", "regular", "sale", "currency", "vat")

# What is being priced, and in what terms. Present only when the source says so.
IDENTITY_FIELDS = ("region", "unit", "brand", "origin", "spec")

ALL_FIELDS = MONEY_FIELDS + IDENTITY_FIELDS


@dataclass(frozen=True)
class PriceKey:
    """A price hash plus the exact fields it was built from."""

    digest: str
    fields: tuple[str, ...]

    @property
    def field_list(self) -> str:
        """Stored beside the hash so a later reader knows what it covered."""
        return ",".join(self.fields)


def _text(value) -> str:
    """Normalized text, or "" when the source said nothing.

    Normalizing is what stops a corrected typo from opening a new price period:
    'Lafarge', 'lafarge ' and 'LAFARGE' are one manufacturer. Excluding the field
    would have been the cheap fix and the wrong one — it would also stop
    'Lafarge' and 'Titan' being told apart.
    """
    return normalize_name(value) if value else ""


def build(*, effective: str, regular: str = "", sale: str = "", currency: str = "",
          vat: int | str = 0, region: str = "", unit: str = "", brand: str = "",
          origin: str = "", spec: str = "") -> PriceKey:
    """The comparability key for one observation.

    Money values must arrive already canonical (see ingest._canon_amount): the
    cross-engine contract is that a hash only ever receives canonical strings,
    never language-native floats.
    """
    parts: dict[str, str] = {
        "v": str(PRICE_KEY_VERSION),
        "effective": effective,
        "regular": regular,
        "sale": sale,
        "currency": (currency or "").strip().upper(),
        "vat": "1" if str(vat) in {"1", "True", "true"} else "0",
    }
    present = list(MONEY_FIELDS)

    # A region of '*' means "this source does not divide by region" — that is an
    # absence, not a place, and hashing it would make it look like one.
    optional = {"region": "" if region.strip() == "*" else region.strip(),
                "unit": _text(unit), "brand": _text(brand),
                "origin": _text(origin), "spec": _text(spec)}
    for name, value in optional.items():
        if value:
            parts[name] = value
            present.append(name)

    return PriceKey(digest=record_hash(parts), fields=tuple(present))


def parse_fields(stored: str | None) -> tuple[str, ...]:
    """Read back a stored field list, tolerating rows written before it existed."""
    if not stored:
        return ()
    return tuple(f for f in stored.split(",") if f in ALL_FIELDS)


def comparable(earlier: tuple[str, ...], later: tuple[str, ...]) -> bool:
    """Were these two keys built from the same fields?

    When they were not, their digests cannot be compared: the later one may
    include a manufacturer the earlier one never had. The prices may well be
    identical.
    """
    return set(earlier) == set(later)


def narrowed(earlier: tuple[str, ...], later: tuple[str, ...]) -> tuple[str, ...]:
    """Fields the source used to publish and has stopped publishing.

    Worth surfacing as a data-quality note: it is not a price change, but it does
    mean ScrapeX now knows less about what it is comparing.
    """
    return tuple(sorted(set(earlier) - set(later)))


def widened(earlier: tuple[str, ...], later: tuple[str, ...]) -> tuple[str, ...]:
    """Fields the source has started publishing."""
    return tuple(sorted(set(later) - set(earlier)))
