"""THE shared parsing module (ENGINEERING.md Q2).

Money/digits/units normalization lives here and ONLY here. A connector that
parses prices locally fails review by definition — this is the producer-side
mirror of the add-in's SmartConverter lesson: one parser, or producers and
consumers drift.

All rules are invariant and explicit (Q5): no locale objects, no environment
sensitivity — the ar-SA culture bug in the add-in is the canonical
counter-example.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

# Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digit folding.
_DIGIT_MAP = {ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(a): str(i) for i, a in enumerate("۰۱۲۳۴۵۶۷۸۹")})
# Arabic decimal (٫) and thousands (٬) separators.
_DIGIT_MAP[ord("٫")] = "."
_DIGIT_MAP[ord("٬")] = ","

# Currency tokens stripped before numeric parsing. Explicit list (P5) — extend
# deliberately, never with a catch-all regex that could eat digits.
_CURRENCY_TOKENS = (
    "SAR", "EGP", "USD", "EUR", "AED", "KWD", "QAR",
    "ر.س", "ريال", "ج.م", "جنيه", "LE", "L.E.", "$", "€", "£",
)

_NUMERIC_KEEP = re.compile(r"[0-9.,\-]")


def fold_digits(text: str) -> str:
    """Fold Arabic-Indic digits and separators into ASCII equivalents."""
    return text.translate(_DIGIT_MAP)


def parse_money(raw: str | None) -> Decimal | None:
    """Parse a scraped price string into a Decimal, or None when absent.

    Handles (each pinned by an exact test, T2):
      '1,234.56'   -> 1234.56   (comma thousands, dot decimal)
      '1.234,56'   -> 1234.56   (dot thousands, comma decimal — EU style)
      '١٢٣٤٫٥٦'    -> 1234.56   (Arabic-Indic digits + Arabic decimal)
      '129.38 SAR' -> 129.38    (currency token stripped)
      '1,234'      -> 1234      (comma as thousands when no other separator)
      ''  / None   -> None
    Raises ValueError on text that contains no parseable number — silent
    None-on-garbage would hide connector defects (Q3/Q4).
    """
    if raw is None:
        return None
    text = fold_digits(raw).strip()
    if not text:
        return None
    for token in _CURRENCY_TOKENS:
        text = text.replace(token, "")
    text = "".join(ch for ch in text if _NUMERIC_KEEP.match(ch))
    if not text or not any(ch.isdigit() for ch in text):
        raise ValueError(f"no numeric content in price string {raw!r}")

    has_dot, has_comma = "." in text, "," in text
    if has_dot and has_comma:
        # The RIGHTMOST separator is the decimal mark; the other is thousands.
        if text.rindex(".") > text.rindex(","):
            text = text.replace(",", "")
        else:
            text = text.replace(".", "").replace(",", ".")
    elif has_comma:
        # Comma only: decimal if exactly one comma with 1-2 trailing digits
        # (e.g. '12,5'); otherwise thousands ('1,234' / '1,234,567').
        head, _, tail = text.rpartition(",")
        if text.count(",") == 1 and 1 <= len(tail) <= 2:
            text = head + "." + tail
        else:
            text = text.replace(",", "")
    # dot-only needs no treatment: '1234.56' and '1234' parse directly;
    # dot-thousands-only ('1.234') is ambiguous and resolved as DECIMAL — a
    # documented, tested choice: real price feeds we probed never emit bare
    # dot-thousands without a decimal part.

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable price string {raw!r} -> {text!r}") from exc


# "50كجم" / "50 kg" in a product's NAME: the site stating what one price buys.
# Arabic and Latin spellings both appear — madar writes it in Arabic, sikaegshop
# in English ("Sika Zinc Rich® -1 \"5 KG\"").
_STATED_KG = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:كجم|كغم|كغ|kg)", re.IGNORECASE)


def selling_unit_from(name: str, weight) -> tuple[str, str]:
    """(basis_quantity, unit) — ONLY when the site itself states the basis.

    The owner's rule: a price is never shown apart from the unit it is FOR,
    and the unit is read off the source, never guessed. Riyadh cement states
    it twice — weight=50 AND "50كجم" in the variant's name — so kg/50 is the
    basis. A steel angle carries weight=4.986, but that is the PIECE's mass:
    its name states dimensions in millimetres, no kg quantity, and its price
    is per piece — inventing "per 4.986 kg" would be exactly the guess this
    function refuses. Agreement between the stated name and the weight field
    is the test.

    Lives HERE, not in a connector, because two families need it (magento and
    custom-json) and connectors never import each other (A1). Unit parsing is
    this module's job by rule anyway (Q2).

    The agreement test earns its keep on real data: across sikaegshop's 87 live
    products (2026-07-25) 60 names state a kg quantity and 4 of those disagree
    with the weight field — product 218 is "Sika Latex®- 20 kg" with weight 5.
    Trusting either side alone would have published a basis the shop does not
    state; disagreement means we say nothing.
    """
    try:
        heavy = float(weight)
    except (TypeError, ValueError):
        return "", ""
    if not heavy:
        return "", ""
    found = _STATED_KG.search(name or "")
    if not found:
        return "", ""
    stated = float(found.group(1).replace(",", "."))
    if abs(stated - heavy) > 1e-6:
        return "", ""
    quantity = int(stated) if stated == int(stated) else stated
    return str(quantity), "kg"


def option_fingerprint(options: dict[str, str]) -> str:
    """Canonical variant-option fingerprint: sorted, lowercased, folded.

    'thickness_mm=12|width_mm=1220' — matches the owner's spec_fingerprint
    convention so source and canonical fingerprints compare directly.
    """
    parts = [
        f"{key.strip().lower()}={fold_digits(str(value)).strip().lower()}"
        for key, value in sorted(options.items())
    ]
    return "|".join(parts)


_NAME_NOISE = re.compile(r"[^\w؀-ۿ]+")  # keep word chars + Arabic letters


def normalize_name(text: str | None) -> str:
    """Canonical form of a product name for comparison (Q2: one implementation).

    Folds Arabic-Indic digits, lowercases, and reduces punctuation to single
    spaces. Arabic letters are preserved explicitly — a plain \\w class would
    survive here, but the intent is worth pinning: names are the ONE place where
    Arabic content drives matching.
    """
    if not text:
        return ""
    folded = fold_digits(str(text)).lower()
    return _NAME_NOISE.sub(" ", folded).strip()


def name_similarity(left: str | None, right: str | None) -> float:
    """0..1 similarity of two product names, order-insensitive.

    Token-set based (not raw string distance): sources reorder the same words
    constantly ('cement 50kg white' vs 'white cement 50kg') and that must not
    read as a different product.
    """
    a, b = set(normalize_name(left).split()), set(normalize_name(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def record_hash(payload: dict) -> str:
    """Deterministic content hash for idempotent ingest (F4).

    Canonical JSON (sorted keys, no whitespace variance) -> sha256 hex.
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
