"""How a stored page is encoded, and how to read one back.

`docs/STORAGE.md`, on the owner's instruction — «ليست الفكرة ضغط الملفات بل دراسة
نشوف احنا بنسحب اى ولية وبنحتفظ باية ولية وما الفائدة». The study's answer was to
retain everything and pay almost nothing for it, and this module is the "almost
nothing".

WHY NOT ZLIB, WHICH `DEC-9` RECOMMENDED, AND WHY THAT WAS THE INTERESTING PART.
`DEC-9` measured zlib at 15.6× and credited the ratio to "a near-identical skeleton
repeated 864 times". The skeleton is near-identical — 40 stored listing pages differ
only in their pagination block and one locale-switch href — but **zlib never sees
it**: its window is 32 KB and a skeleton is 121 KB, so page 1 is out of view before
page 2 begins. Measured three ways on the same 40 pages:

    one skeleton, zlib-9 .................... 18 KB
    ten skeletons concatenated, zlib-9 ...... 175 KB   = 9.84x the cost of one
    all 40 pages as ONE zlib block .......... 15.8x    = no better than separately

So the cross-page redundancy that made the corpus look compressible was left
entirely on the table.

WHY A DICTIONARY AND NOT A BLOCK. Those same 40 pages reach **219×** as a single
zstd block — but a block is a CHAIN, and row 700 cannot depend on row 699 still
existing. A database column may not have that property. `zstd` with one real page as
a RAW dictionary reaches **187× on listings and 46× on profiles** at 3.5 ms a page,
and every row stays independently decompressible. 618 MB of listings becomes 3.3 MB;
3.95 GB of profiles becomes 87 MB.

WHY RAW AND NOT TRAINED. `zstd.train_dict` was measured too, at 110 KB and 512 KB,
and reached 19.7× against the raw page's 187×. A trained dictionary is built for many
small samples; this corpus is a handful of very large near-duplicates, and the best
dictionary for a page that is 97% skeleton is a page.

WHY THIS IS NOT A FLAG. `scrapex/features.py` already carries the lesson: a
capability with no production caller is a claim, not a mechanism. `snapshotcrawl`
calls this on the path that fetches the 36,548 pages the study is about.
"""
from __future__ import annotations

import sqlite3
from urllib.parse import urlparse

from compression import zstd

#: `html_content` is the page, exactly as it arrived. Every row written before
#: 2026-08-20 is this, and stays this — `trg_generic_page_snapshot_immutable_update`
#: forbids rewriting them and is worth more than the 607 MB a backfill would save.
PLAIN = "plain"

#: `html_content` holds zstd frames compressed against the raw page in
#: `snapshot_dictionary`, which `html_dict_id` names.
ZSTD_RAW_DICT = "zstd-raw-dict"

#: MEASURED, not chosen. Level 3 gives 146×, level 12 gives 187× at 3.5 ms a page,
#: and level 19 gives 186× at 19.6 ms — slightly WORSE for 5.6× the time. 12 is
#: where the curve stops paying.
LEVEL = 12


class UnknownCodec(RuntimeError):
    """This row says it is encoded in a way this build cannot read.

    Its own class, and it RAISES rather than returning the bytes, because the
    alternative is handing a caller a compressed frame that it will parse as HTML
    and find no tables in. That failure would surface as "the page has no data",
    which is the wrong thing to go looking for.
    """


def label_for(source_url: str, kind: str | None = None) -> str:
    """Which dictionary this page belongs with: host plus page kind.

    PER KIND AND NOT PER HOST, because the study measured a same-kind dictionary at
    187× on listings and 46× on profiles. muqawil's listing page is 363 KB of
    directory chrome and its profile page is 119 KB of a different layout; one
    dictionary covering both would be worse than either, and the cost of keeping
    them apart is one row in a table.
    """
    host = urlparse(source_url).netloc.lower() or "unknown-host"
    return f"{host}/{kind or 'page'}"


def _dictionary(conn: sqlite3.Connection, label: str, seed: str) -> tuple[int, bytes]:
    """The dictionary for this label, creating it from `seed` if there is none.

    THE FIRST PAGE OF A CLASS BECOMES ITS DICTIONARY. It is not the theoretically
    best choice — a median page would be — but choosing a median needs a corpus that
    does not exist at the moment the first page arrives, and the alternative designs
    all end with a second dictionary and a migration of everything compressed against
    the first. A page compressed against itself also costs almost nothing, so the
    seed row is not a wasted one.
    """
    row = conn.execute(
        "SELECT dict_id, body FROM snapshot_dictionary WHERE label = ? LIMIT 1",
        (label,),
    ).fetchone()
    if row is not None:
        return int(row[0]), bytes(row[1])
    cursor = conn.execute(
        "INSERT INTO snapshot_dictionary (label, body) VALUES (?,?)",
        (label, seed.encode("utf-8")),
    )
    return int(cursor.lastrowid), seed.encode("utf-8")


def encode(
    conn: sqlite3.Connection, html: str, *, label: str | None,
) -> tuple[object, str, int | None]:
    """`(value, codec, dict_id)` ready for the INSERT.

    `label=None` means store it as it is, which is what every caller that has not
    opted in gets — including the engine's own save-a-page endpoint, where one page
    saved by hand has no class to belong to and nothing to gain.

    IT REFUSES TO MAKE A PAGE BIGGER. A short page can compress to more bytes than
    it started with, and a codec that is a pessimisation on some rows and an
    optimisation on others is a codec nobody can reason about. The comparison is
    made on the real bytes rather than assumed from the ratio measured on 363 KB
    listing pages.
    """
    if label is None:
        return html, PLAIN, None

    plain = html.encode("utf-8")
    dict_id, body = _dictionary(conn, label, html)
    packed = zstd.compress(plain, LEVEL, zstd_dict=zstd.ZstdDict(body, is_raw=True))
    if len(packed) >= len(plain):
        return html, PLAIN, None
    return packed, ZSTD_RAW_DICT, dict_id


def _field(row, name: str, default=None):
    """One column of a row, whether the row is a `sqlite3.Row` or a mapping.

    NOT `name in row`, which lint suggests and which would be a real defect here:
    `sqlite3.Row` iterates its VALUES, so `"html_codec" in row` asks whether any
    column happens to hold that string. `sqlite3.Row` raises IndexError for a name
    it does not have, and a mapping raises KeyError; both mean the same thing.
    """
    try:
        return row[name]
    except (IndexError, KeyError):
        return default


def decode(conn: sqlite3.Connection, row) -> str:
    """The page as the site served it, whatever the row did to store it.

    THE ONE PLACE THAT KNOWS. Every reader of a snapshot body goes through here, so
    a codec added later is one function to teach rather than a search for
    `html_content` across the codebase — which is the search that would miss one.
    """
    codec = _field(row, "html_codec", PLAIN)
    if codec == PLAIN:
        return row["html_content"]
    if codec == ZSTD_RAW_DICT:
        dict_id = _field(row, "html_dict_id")
        found = conn.execute(
            "SELECT body FROM snapshot_dictionary WHERE dict_id = ? LIMIT 1",
            (dict_id,),
        ).fetchone()
        if found is None:
            # Should be impossible: the dictionary table forbids DELETE for
            # exactly this reason. Said out loud anyway, because "impossible"
            # here means someone dropped the trigger.
            raise UnknownCodec(
                f"snapshot {_field(row, 'page_snapshot_id')} was compressed against "
                f"dictionary {dict_id}, which is not in this database. The page "
                "cannot be read and its plaintext is not stored anywhere else.")
        body = bytes(found[0])
        return zstd.decompress(
            bytes(row["html_content"]), zstd_dict=zstd.ZstdDict(body, is_raw=True),
        ).decode("utf-8")
    raise UnknownCodec(
        f"snapshot {_field(row, 'page_snapshot_id')} is stored as {codec!r}, which this "
        "build cannot decode. Do not treat the stored bytes as HTML.")
