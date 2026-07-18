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


def record_hash(payload: dict) -> str:
    """Deterministic content hash for idempotent ingest (F4).

    Canonical JSON (sorted keys, no whitespace variance) -> sha256 hex.
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
