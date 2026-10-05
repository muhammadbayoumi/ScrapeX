"""The light file: what the Data page shows, written beside every backup (#1199).

WHAT IT IS. Two files beside each bundle the Back up button builds, sharing its stamp:

    scrapex-bundle-<stamp>-light.gz     one gzip member per part
    scrapex-bundle-<stamp>-light.json   the index: where each part is, and its digests

A part is the exact body a route answers today, built by that route's own reader and
serialised the way FastAPI serialises a route with no response model. So a reader with
no engine (#1200) draws the same table, opens the same record card and filters by the
same activity tree as the engine's own page:

    price    table          GET /api/table/{key}?fold=0
             table-folded   GET /api/table/{key}?fold=1, when folding changes anything
             cards          GET /api/offer/{key}/{offer_id}, one line per row of `table`
    dataset  table          GET /api/table/{key}?site_key={site}
             taxonomy       GET /api/taxonomy/{key}, when the dataset has a tree
             selected       per node, the records the table's filter keeps for it

ONE FILE OF INDEPENDENT MEMBERS, NOT ONE FILE PER SOURCE. RFC 1952 lets gzip members
follow one another, so the file is still gzip, and a browser inflates one part with
`blob.slice(offset, offset + bytes)` through `DecompressionStream("gzip")`, which it
has built in. A card part is inflated only when a row's card is opened. One file is one
upload, one checksum and one name for a pointer to hold, as `bundle.PANEL_PACK` argues.

NO SQL OF ITS OWN, for the reason `bundle.py` gives: every part comes from a reader the
engine already serves from, so the copy cannot drift from the page.

READ-ONLY, ONE SNAPSHOT. The database is opened with `?mode=ro`, escaped into the URI
(`storage.row_counts` says why), inside one read transaction, so every part describes
the same warehouse even if a caller hands it a live file. It takes no lock and writes
nothing to the warehouse. Never call it while holding `db.write_lock`: it reads for
about 50 s on his warehouse (#1206, with migration 0021's indexes).

A TABLE THAT FAILS IS A FAULT, NOT A FAILED FILE. Its bytes are cut back off the parts
file, it is named in `faults` with its error, and the other tables are still written.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from . import reports, taxonomy
from .bundle import PARTIAL_SUFFIX, sha256_of
from .extract import service as extract_service
from .payload import utc_now_iso
from .version import VERSION

#: The light file's own layout, separate from `bundle.BUNDLE_FORMAT`, which his ruling
#: of 2026-10-05 kept at 1 because nothing inside the zip changed. A reader refuses a
#: format it does not know. Adding a part does not move this; removing or reshaping
#: one does, because an older reader would then half-read the file.
LIGHT_FORMAT = 1

PARTS_SUFFIX = "-light.gz"
INDEX_SUFFIX = "-light.json"

#: Level 6, as the bundle and the panel pack use (`bundle.py`).
_LEVEL = 6
#: zlib's gzip framing: a header with no file name and a zero mtime, so two writes of
#: one warehouse produce the same bytes.
_GZIP = 31


@dataclass
class LightReport:
    parts_path: Path
    index_path: Path
    index: dict[str, Any]

    @property
    def faults(self) -> list[dict[str, Any]]:
        return self.index["faults"]


def _serialiser() -> Callable[[Any], bytes]:
    """The engine's own serialisation of a route with no response model.

    IMPORTED HERE, NOT AT THE TOP. FastAPI is the `[ui]` extra, and the light file
    exists only where the engine that serves these routes runs.
    """
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    return lambda payload: JSONResponse(content=jsonable_encoder(payload)).body


def _member(out: BinaryIO, chunks: Iterable[bytes], *, lines: bool = False) -> dict:
    """Write one gzip member to `out`, and say where it is and what it holds.

    STREAMED. A card part is one line per row, 19,218 cards on his warehouse, and
    each is compressed as it arrives, so the writer never holds a source's cards.
    """
    offset = out.tell()
    packer = zlib.compressobj(_LEVEL, zlib.DEFLATED, _GZIP)
    digest = hashlib.sha256()
    raw = count = 0

    def put(data: bytes) -> None:
        if data:
            out.write(data)
            digest.update(data)

    for chunk in chunks:
        raw += len(chunk)
        count += 1
        put(packer.compress(chunk))
    put(packer.flush())
    described = {"offset": offset, "bytes": out.tell() - offset,
                 "sha256": digest.hexdigest(), "raw_bytes": raw}
    if lines:
        described["lines"] = count
    return described


def _rows_of(table: dict, where: str) -> list[dict]:
    """The table's rows, after asserting the shape the page reads."""
    if not isinstance(table.get("rows"), list) or not isinstance(table.get("columns"), list):
        raise TypeError(f"{where}: the table has no rows or columns list")
    return table["rows"]


def _cards(conn, source_key: str, rows: list[dict],
           serialise: Callable[[Any], bytes]) -> Iterator[bytes]:
    """One record card per row, in row order, as `GET /api/offer` answers it."""
    seen: set[int] = set()
    for row in rows:
        offer_id = row.get("offer_id")
        if not isinstance(offer_id, int) or offer_id in seen:
            raise ValueError(f"{source_key}: a row's offer_id is {offer_id!r}, "
                             "missing or repeated")
        seen.add(offer_id)
        card = reports.offer_card(conn, source_key, offer_id)
        if card is None:
            raise LookupError(f"{source_key}: offer {offer_id} is in the table "
                              "and has no card")
        yield serialise(card) + b"\n"


def _price(conn, entry, out: BinaryIO, serialise) -> dict:
    key = entry.source_key
    table = reports.table_payload(conn, key, fold_variants=False)
    rows = _rows_of(table, key)
    parts = {"table": _member(out, [serialise(table)])}
    if table.get("foldable"):
        folded = reports.table_payload(conn, key, fold_variants=True)
        _rows_of(folded, key)
        parts["table-folded"] = _member(out, [serialise(folded)])
    parts["cards"] = _member(out, _cards(conn, key, rows, serialise), lines=True)
    return {"kind": "price", "site_key": key, "key": key,
            "name": entry.source_name, "name_ar": entry.source_name_ar or "",
            # The page's default, from the manifest, as the route reads it.
            "fold_variants": bool(entry.fold_variants), "folded_into": None,
            "rows": len(rows), "total": table.get("total"),
            "truncated": bool(table.get("truncated")),
            "foldable": bool(table.get("foldable")), "parts": parts}


def _dataset(conn, listed: dict, folded_into: str | None, out: BinaryIO,
             serialise) -> dict:
    key, site = listed["dataset_key"], listed["site_key"]
    table = extract_service.dataset_table_payload(conn, key, site_key=site)
    if table is None:
        # The listing shows it and the resolver refuses it (#1361). The route would
        # fall through to an empty price table; a copy says what happened instead.
        raise LookupError(f"{site}/{key}: listed, and its table resolves to nothing")
    rows = _rows_of(table, f"{site}/{key}")
    parts = {"table": _member(out, [serialise(table)])}
    tree = taxonomy.dataset_taxonomy(conn, key)
    if tree["groups"]:
        parts["taxonomy"] = _member(out, [serialise(tree)])
        nodes = [node["node_id"] for group in tree["groups"] for node in group["nodes"]]
        nodes += [group["undeclared"]["node_id"] for group in tree["groups"]
                  if group["undeclared"]]
        selected = taxonomy.selected_by_node(
            conn, listed["dataset_definition_id"], nodes)
        parts["selected"] = _member(out, [serialise(selected)])
    return {"kind": "dataset", "site_key": site, "key": key,
            "name": listed["display_name"] or listed["original_name"], "name_ar": "",
            "fold_variants": False, "folded_into": folded_into,
            "rows": len(rows), "total": table.get("total"),
            "truncated": bool(table.get("truncated")), "foldable": False,
            "parts": parts}


def write(database: Path | str, out_prefix: Path | str, *,
          price_sources: Sequence[Any]) -> LightReport:
    """Write `<out_prefix>-light.gz` and `<out_prefix>-light.json` from `database`.

    `price_sources` is the manifest's list, the one `/api/sources` walks. The datasets
    are `extract_service.listed_datasets`, the one list the Data page uses, so the copy
    carries exactly the tables the page would offer.

    Each file is written under a `.part` name and renamed once whole, so neither name
    ever holds a half-written file. Anything that stops the whole write, rather than
    one table, removes both `.part` files and propagates.
    """
    serialise = _serialiser()
    prefix = str(out_prefix)
    parts_path, index_path = Path(prefix + PARTS_SUFFIX), Path(prefix + INDEX_SUFFIX)
    parts_building = parts_path.with_name(parts_path.name + PARTIAL_SUFFIX)
    index_building = index_path.with_name(index_path.name + PARTIAL_SUFFIX)

    tables: list[dict] = []
    faults: list[dict] = []
    conn = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("BEGIN")
        schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
        listed = extract_service.listed_datasets(conn)
        folds = extract_service.dataset_folds(
            conn, [one["dataset_key"] for one in listed])
        plan: list[tuple[str, str, str, Callable[[BinaryIO], dict]]] = [
            ("price", entry.source_key, entry.source_key,
             lambda out, entry=entry: _price(conn, entry, out, serialise))
            for entry in price_sources]
        plan += [
            ("dataset", one["site_key"], one["dataset_key"],
             lambda out, one=one: _dataset(
                 conn, one, folds.get(one["dataset_key"]), out, serialise))
            for one in listed]
        with open(parts_building, "wb") as out:
            for kind, site_key, key, build in plan:
                start = out.tell()
                try:
                    tables.append(build(out))
                except Exception as error:
                    # ONE TABLE FAILING NEVER KILLS THE FILE, and it is never
                    # swallowed: its bytes are cut off and it is named, with the
                    # error, where the panel reads it.
                    out.seek(start)
                    out.truncate()
                    faults.append({"kind": kind, "site_key": site_key, "key": key,
                                   "problem": f"{type(error).__name__}: {error}"})
        index = {
            "light_format": LIGHT_FORMAT,
            "engine_version": VERSION,
            "schema_version": int(schema_version),
            "generated_at": utc_now_iso(),
            "parts_file": {"name": parts_path.name,
                           "bytes": parts_building.stat().st_size,
                           "sha256": sha256_of(parts_building)},
            "tables": tables,
            "faults": faults,
        }
        index_building.write_text(
            json.dumps(index, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        parts_building.replace(parts_path)
        index_building.replace(index_path)
    except BaseException:
        parts_building.unlink(missing_ok=True)
        index_building.unlink(missing_ok=True)
        raise
    finally:
        conn.rollback()
        conn.close()
    return LightReport(parts_path=parts_path, index_path=index_path, index=index)
