"""What a random sample of stored profile pages PUBLISHES, against what we stored.

ISSUE 546. The standing claim -- "the site publishes nothing we do not read" -- rested
on 1,200 of 34,834 pages that were the FIRST 1,200 snapshot ids, which is the lowest
contractor ids and not a sample. And `undeclared_cards` has a stated blind spot: a
text-only card cannot be told from the contractor's own name card, so a whole new
section could be published and never reported.

WHY THIS IS A DIFFERENT INSTRUMENT AND NOT THE PARSER AGAIN. Asking `read_profile` what
a page carries answers with the labels we declared, so it can only ever agree with
itself. This reads EVERY `info-box` label and EVERY card title -- declared or not, text
or table -- and compares them against the row that page produced. That is what separates
the two answers his question needs:

    the label is absent from the page          -> the SITE does not publish it
    the label carries a value, the row is empty -> WE do not read it

READ-ONLY, AND NO NETWORK. Everything comes off `generic_page_snapshot`, decoded through
`snapshotbody.decode` like any other reader.

    python -m tools.profile_card_census --size 2000 --seed 546
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup  # noqa: E402

from scrapex import snapshotbody  # noqa: E402
from scrapex.extract.muqawil import (  # noqa: E402
    DEFAULT_MAP_PIN,
    PROFILE_CARDS,
    PROFILE_FIELDS,
    _boxes,
    _card,
    _text,
    read_cards,
    read_coordinates,
)

#: Labels that belong to a LISTING card and never to a profile's own info block. A
#: stored "profile" carrying these is the contractors listing, which is what muqawil
#: answers with when an id no longer resolves -- at HTTP 200 and ~373 KB against a
#: profile's ~118 KB. Taken from `CARD_FIELDS`' own labels rather than guessed.
LISTING_ONLY_LABELS = frozenset({"Status", "City - Region", "Main Contractor",
                                 "Sub Contractor"})

#: The card whose values reach the flat row as `self_build_price_*`, named by its key
#: rather than its title so a re-worded heading does not silently empty this census.
SELF_BUILD_KEY = "self_build_prices"
CONTRACT_COUNTS_KEY = "contract_counts"


def declared_card_titles() -> frozenset[str]:
    return frozenset(title for card in PROFILE_CARDS for title in card.titles)


def _titles_of(key: str) -> frozenset[str]:
    return frozenset(title for card in PROFILE_CARDS if card.key == key
                     for title in card.titles)


@dataclass
class PageFacts:
    """What one stored page publishes, read without asking what we declared."""

    #: `label -> how many boxes carried a NON-EMPTY value`, every label on the page.
    valued: dict[str, int] = field(default_factory=dict)
    #: `label -> how many boxes carried the label at all`, empty value included.
    seen: dict[str, int] = field(default_factory=dict)
    #: `(title, carries_data)` once per distinct title.
    cards: tuple[tuple[str, bool], ...] = ()
    #: Whether the page places a REAL pin: a pair that is neither zero-halved nor
    #: the site's default. `read_coordinates() is not None` was the first probe here
    #: and it reported 299 of 299 pages against 42 stored rows -- a 257-page "gap"
    #: that is a documented REFUSAL, not a miss. `merge_locales` declines to promote
    #: `DEFAULT_MAP_PIN` because the site emits the centre of Riyadh identically for
    #: 14,621 contractors, so it carries no information about any of them. A census
    #: whose probe measures a proxy instead of the fact reports the parser's
    #: judgement as its defect.
    has_coordinates: bool = False
    #: Whether the self-build card carries a PRICED ROW, not merely whether the card
    #: is published. Same lesson: `read_self_build_prices` records "the card is on
    #: 713 of 2,419 pages and carries rows on 163", so a contractor in the programme
    #: who has not priced it has the card and no rows. Both are real states.
    has_self_build_row: bool = False
    #: Distinct contractor ids the page links to, which is how a listing gives itself
    #: away: a profile links to itself and nobody else.
    linked_ids: frozenset[str] = frozenset()

    @property
    def is_a_listing(self) -> bool:
        """A page carrying a listing card's own labels is not a profile page."""
        return any(label in LISTING_ONLY_LABELS for label in self.seen)

    def has_card(self, key: str) -> bool:
        wanted = _titles_of(key)
        return any(title in wanted and carries for title, carries in self.cards)


_LINK = None


def census_page(html: str) -> PageFacts:
    """One page's facts. PURE, so the tests can drive it with the committed fixtures."""
    global _LINK
    if _LINK is None:
        import re
        _LINK = re.compile(r"/contractors/(\d+)(?:/|\b)")
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, int] = collections.Counter()
    valued: dict[str, int] = collections.Counter()
    for label, value in _boxes(soup):
        seen[label] += 1
        if value.strip():
            valued[label] += 1
    titles: dict[str, bool] = {}
    for title, carries in read_cards(html):
        # ANY carrying instance wins: the same title can appear twice, and a census
        # that let the last one decide would report a data card as text-only.
        titles[title] = titles.get(title, False) or carries
    pin = read_coordinates(html)
    return PageFacts(
        seen=dict(seen), valued=dict(valued),
        cards=tuple(titles.items()),
        has_coordinates=bool(pin and pin[0] and pin[1] and pin != DEFAULT_MAP_PIN),
        has_self_build_row=_carries_a_priced_row(html),
        linked_ids=frozenset(_LINK.findall(html)),
    )


def _carries_a_priced_row(html: str) -> bool:
    """A self-build card with at least one row whose value cell is filled.

    READ OFF THE TABLE AND NOT THROUGH `read_self_build_prices`, which is the whole
    point of this file: that function maps the label to a declared tier and RAISES on
    an undeclared one, so asking it would answer with what we declared. This asks the
    page.
    """
    card = _card(html, SELF_BUILD_KEY)
    if card is None:
        return False
    for row in card.select("tr"):
        cells = row.select("td")
        if len(cells) >= 2 and _text(cells[1]).strip():
            return True
    return False


@dataclass
class Census:
    pages: int = 0
    listings: int = 0
    #: `label -> [pages where it carried a value, pages where it appeared]`
    labels: dict[str, list[int]] = field(default_factory=dict)
    #: `title -> [pages, pages where it carried data]`
    cards: dict[str, list[int]] = field(default_factory=dict)
    with_coordinates: int = 0
    #: `field -> [page has it, row has it, page yes and row no]`
    against_rows: dict[str, list[int]] = field(default_factory=dict)


def _bump(store: dict[str, list[int]], key: str, *, at: int) -> None:
    slot = store.setdefault(key, [0, 0, 0][:3])
    slot[at] += 1


def _profile_rows(conn: sqlite3.Connection) -> dict[str, dict]:
    """Every stored profile row, by contractor id."""
    rows = conn.execute(
        "SELECT r.data_json FROM generic_record AS r JOIN dataset_definition AS d "
        "  ON d.dataset_definition_id = r.dataset_definition_id "
        " WHERE d.dataset_key = 'contractor_profiles'")
    out = {}
    for (blob,) in rows:
        record = json.loads(blob)
        found = record.get("contractor_id")
        if found:
            out[str(found)] = record
    return out


def _sample(conn: sqlite3.Connection, *, size: int, seed: int) -> list[sqlite3.Row]:
    """A RANDOM sample, seeded so the same warehouse gives the same sample twice.

    ONE PAGE PER CONTRACTOR, ENGLISH ONLY. The two locales publish the same boxes by
    design -- the Arabic values are taken by position from the English labels -- so
    counting both would double every figure and tell nobody anything new.
    """
    rows = conn.execute(
        "SELECT page_snapshot_id, source_url FROM generic_page_snapshot "
        " WHERE instr(source_url, '/en/contractors/') > 0 "
        "   AND instr(source_url, '/143') > 0 "
        " GROUP BY source_url").fetchall()
    random.seed(seed)
    return random.sample(rows, min(size, len(rows)))


#: What a profile row should carry when the page publishes the thing, paired with the
#: probe that decides whether the page publishes it. The point of the pairing is the
#: THIRD column of `against_rows`: page yes and row no is OUR gap and nothing else is.
_AGAINST_ROWS = (
    ("latitude", lambda facts: facts.has_coordinates),
    ("address", lambda facts: bool(facts.valued.get("Address"))),
    ("activity", lambda facts: bool(facts.valued.get("Activity"))),
    ("organization_mobile_number",
     lambda facts: bool(facts.valued.get("Organization Mobile Number"))),
    ("self_build_price_under_five_projects",
     lambda facts: facts.has_self_build_row),
    ("model_contract_count", lambda facts: facts.has_card(CONTRACT_COUNTS_KEY)),
)


def run(conn: sqlite3.Connection, *, size: int, seed: int) -> Census:
    picked = _sample(conn, size=size, seed=seed)
    stored = _profile_rows(conn)
    out = Census()
    for row in picked:
        full = conn.execute(
            "SELECT * FROM generic_page_snapshot WHERE page_snapshot_id = ?",
            (row["page_snapshot_id"],)).fetchone()
        facts = census_page(snapshotbody.decode(conn, full))
        out.pages += 1
        if facts.is_a_listing:
            # COUNTED AND SKIPPED. Its labels are another document's, so folding them
            # into the label census would report listing columns as profile fields.
            out.listings += 1
            continue
        for label in facts.seen:
            _bump(out.labels, label, at=1)
            if facts.valued.get(label):
                _bump(out.labels, label, at=0)
        for title, carries in facts.cards:
            _bump(out.cards, title, at=0)
            if carries:
                _bump(out.cards, title, at=1)
        out.with_coordinates += bool(facts.has_coordinates)
        record = stored.get(next(iter(facts.linked_ids), ""), None)
        if len(facts.linked_ids) == 1 and record is not None:
            for name, probe in _AGAINST_ROWS:
                page_has = bool(probe(facts))
                row_has = bool(str(record.get(name) or "").strip())
                slot = out.against_rows.setdefault(name, [0, 0, 0])
                slot[0] += page_has
                slot[1] += row_has
                slot[2] += page_has and not row_has
    return out


def _report(out: Census) -> str:
    lines = [f"pages read {out.pages:,} · of those NOT profiles {out.listings:,} "
             f"({100 * out.listings / max(out.pages, 1):.1f}%)",
             f"pages with a coordinate pair {out.with_coordinates:,}", "",
             "== labels: valued / seen, over the profile pages =="]
    declared = set(PROFILE_FIELDS)
    profiles = out.pages - out.listings
    for label, (valued, seen, _) in sorted(
            out.labels.items(), key=lambda one: -one[1][1]):
        mark = "declared" if label in declared else "NOT DECLARED"
        lines.append(f"   {label[:40]:<40} {valued:>6,}/{seen:<6,} "
                     f"{100 * valued / max(profiles, 1):>5.1f}%  {mark}")
    lines += ["", "== cards: pages / of those carrying data =="]
    known = declared_card_titles()
    for title, (pages, carrying, _) in sorted(
            out.cards.items(), key=lambda one: -one[1][0]):
        if pages < 2:
            continue                      # the contractor's own name card
        mark = "declared" if title in known else "NOT DECLARED"
        lines.append(f"   {title[:44]:<44} {pages:>6,} pages, {carrying:>6,} "
                     f"with data  {mark}")
    lines += ["", "== the page against the row: page has it / row has it / OUR GAP =="]
    for name, (page_has, row_has, gap) in out.against_rows.items():
        lines.append(f"   {name[:40]:<40} page {page_has:>5,}  row {row_has:>5,}  "
                     f"gap {gap:>5,}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=546)
    parser.add_argument("--db", default=os.path.expanduser(
        "~/.scrapex/engine/scrapex-engine.db"))
    args = parser.parse_args(argv)
    # READ-ONLY, AND SAID IN THE URI. This tool measures his live warehouse and must
    # not be able to write to it even by mistake.
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        print(_report(run(conn, size=args.size, seed=args.seed)))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
