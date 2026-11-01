"""Where a tender lands: the response it came from, the release, and what it compiles to.

ES-3: the shape is OCDS's own. A release is what a source said, and when; it is kept
whole in `tender_releases`, which a trigger makes append-only, and it is the history.
The typed tables (`tenders`, `tender_parties` and the rest) are the current state,
compiled from a process's releases by `compile_process`. They are rebuilt from the
releases, never edited on their own, so deleting and re-inserting them is the rule
here and not a shortcut. The award tables (`tender_awards`, its suppliers, contracts
and bids) are compiled here too once part 4 brings their writer; until then nothing
writes them, and an award notice's award stays in its release.

THIS MODULE KNOWS NO SOURCE. A site module (`scrapex/sites/worldbank.py`, the first)
turns what its site publishes into a `Release`; everything below reads OCDS and nothing
else. A second tender source writes a second site module and calls the same three
functions.

PERSONS NEVER ENTER THE HISTORY. His ruling on #1647: every person is kept, in
`tender_contact_points` and `tender_beneficial_owners`, outside the append-only table,
so a person can be removed later. A site module therefore hands them over beside the
payload (`Release.contacts`), never inside it, and `store_release` refuses a payload
that carries a contact point or beneficial owners anywhere in it.

The caller owns the transaction: every function here writes through the connection it
is given and commits nothing, so one job's response, release and compiled rows land
together or not at all, under the write lock the job already holds.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

import zstandard

#: The persons a contact point may name, and the only fields `tender_contact_points` has.
CONTACT_FIELDS = ("name", "job_title", "email", "telephone", "fax_number", "url")

#: THE ZSTD LEVEL FOR EVIDENCE. His decision on #1733, 2026-10-20: 12, the level
#: `snapshotbody.LEVEL` already chose "where the curve stops paying". Measured there on a
#: 1,000-notice body: level 19 was 15-24 times slower for 2-14% fewer bytes, and held the
#: write lock 2.8-6.8 s a response against 0.5-1.2 s. A stored body names its codec and
#: not its level, so changing this rewrites no row.
LEVEL = 12


@dataclass(frozen=True)
class Packed:
    """A response body compressed for `fetched_responses`, and its plain bytes' digest.

    MADE BEFORE THE WRITE LOCK IS TAKEN (#1733). Compressing is the slow part of keeping a
    response, and inside the transaction it held every other writer back for its length.
    """

    blob: bytes
    sha256: str


def pack(body: bytes) -> Packed:
    return Packed(zstandard.ZstdCompressor(level=LEVEL).compress(body),
                  hashlib.sha256(body).hexdigest())


@dataclass(frozen=True)
class Release:
    """One release, as a site module read it: the payload and what stands beside it."""

    #: The process's key at its source (`tender_processes.source_record_id`).
    process_key: str
    #: OCDS ocid, minted by the site module because the source publishes no OCDS.
    ocid: str
    #: OCDS release, without persons (`payload["id"]` is the release ref).
    payload: dict[str, Any]
    #: The source's project id (#1616 D1), when it has one.
    project_ref: str | None = None
    #: The source's own change stamp, RFC 3339 (#1616 D10).
    source_modified_at: str | None = None
    #: `{party_ref: {field: value}}` -- persons, kept out of the payload.
    contacts: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Stored:
    tender_process_id: int
    tender_release_id: int
    #: False when the same release (same ref, same payload) was already stored.
    new: bool


def store_response(conn: sqlite3.Connection, *, target_uri: str, status_code: int,
                   content_type: str, headers: dict[str, str], body: bytes | Packed,
                   crawl_job_id: int | None = None) -> int:
    """Keep one response as evidence (`fetched_responses`), compressed. Returns its id.

    `body` is the plain bytes, or what `pack` made of them before the caller took the
    write lock, which is how a collector hands it over."""
    packed = body if isinstance(body, Packed) else pack(body)
    cursor = conn.execute(
        "INSERT INTO fetched_responses (target_uri, status_code, content_type, headers, "
        "body, body_codec, body_sha256, crawl_job_id) VALUES (?,?,?,?,?,?,?,?)",
        (target_uri, status_code, content_type,
         json.dumps(dict(headers), ensure_ascii=False, sort_keys=True),
         packed.blob, "zstd", packed.sha256, crawl_job_id))
    return int(cursor.lastrowid)


def response_body(conn: sqlite3.Connection, fetched_response_id: int) -> bytes:
    """The body as it arrived, decompressed and checked against its digest."""
    row = conn.execute("SELECT body, body_codec, body_sha256 FROM fetched_responses "
                       "WHERE id = ?", (fetched_response_id,)).fetchone()
    if row is None:
        raise LookupError(f"no fetched response {fetched_response_id}")
    body, codec, digest = row[0], row[1], row[2]
    if codec != "zstd":
        raise ValueError(f"fetched response {fetched_response_id} has codec {codec!r}")
    plain = zstandard.ZstdDecompressor().decompress(body)
    if hashlib.sha256(plain).hexdigest() != digest:
        raise ValueError(f"fetched response {fetched_response_id} fails its own digest")
    return plain


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


#: Far above any real release and far below SQLite's own limit, past which `jsonb()` answers
#: `malformed JSON`: an `OperationalError`, which `worldbank_collect._keep` rightly reads as the
#: warehouse's fault, so one such notice would fail the job, and each later update on it too.
MAX_PAYLOAD_DEPTH = 64


def _assert_release_shape(release: Release) -> None:
    payload = release.payload
    for key in ("ocid", "id", "date", "tag"):
        if not payload.get(key):
            raise ValueError(f"release {payload.get('id')!r} has no {key!r}")
    if payload["ocid"] != release.ocid:
        raise ValueError(f"release {payload['id']!r} names ocid {payload['ocid']!r}, "
                         f"its process {release.ocid!r}")
    if not isinstance(payload["tag"], list):
        raise ValueError(f"release {payload['id']!r}: tag must be a list")
    # Wherever OCDS would put a person -- a contact point on any organisation (a party,
    # the buyer, a tenderer, a supplier) or a party's beneficial owners -- at any depth,
    # because once stored the history cannot be edited to take one out.
    stack: list[tuple[Any, int]] = [(payload, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, (dict, list)) and depth > MAX_PAYLOAD_DEPTH:
            raise ValueError(f"release {payload['id']!r} nests deeper than {MAX_PAYLOAD_DEPTH}")
        if isinstance(node, dict):
            carried = sorted({"contactPoint", "beneficialOwners"} & node.keys())
            if carried:
                raise ValueError(f"release {payload['id']!r} carries {carried} inside the "
                                 "payload; persons are kept beside it, in their own tables")
            stack.extend((value, depth + 1) for value in node.values())
        elif isinstance(node, list):
            stack.extend((value, depth + 1) for value in node)


def store_release(conn: sqlite3.Connection, *, source_site_id: int, release: Release,
                  fetched_response_id: int | None) -> Stored:
    """Keep one release, its process and its persons, then recompile the process.

    Idempotent: the same release read again (same ref, same payload) is not stored twice,
    and its persons are not written twice either. A release whose payload CHANGED is a
    new release with the same ref, which is how a revised notice enters the history.
    """
    _assert_release_shape(release)
    payload = release.payload
    found = conn.execute(
        "SELECT id FROM tender_processes WHERE source_site_id = ? AND source_record_id = ?",
        (source_site_id, release.process_key)).fetchone()
    if found is None:
        process_id = int(conn.execute(
            "INSERT INTO tender_processes (ocid, source_site_id, source_record_id, "
            "project_ref) VALUES (?,?,?,?)",
            (release.ocid, source_site_id, release.process_key,
             release.project_ref)).lastrowid)
    else:
        process_id = int(found[0])
        conn.execute(
            "UPDATE tender_processes SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
            "project_ref = coalesce(?, project_ref) WHERE id = ?",
            (release.project_ref, process_id))

    # THE DIGEST IS THE CANONICAL TEXT'S, and the column holds the same value as JSONB
    # (ES-6, migration 0026): `jsonb()` keeps a value's keys in the order given, so the
    # text read back with `json()` is this text again.
    canonical = _canonical(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    cursor = conn.execute(
        "INSERT OR IGNORE INTO tender_releases (tender_process_id, release_ref, released_at, "
        "source_modified_at, tags, language, payload, payload_sha256, fetched_response_id) "
        "VALUES (?,?,?,?,?,?,jsonb(?),?,?)",
        (process_id, payload["id"], payload["date"], release.source_modified_at,
         json.dumps(payload["tag"]), payload.get("language"), canonical, digest,
         fetched_response_id))
    new = cursor.rowcount == 1
    release_id = int(conn.execute(
        "SELECT id FROM tender_releases WHERE tender_process_id = ? AND release_ref = ? "
        "AND payload_sha256 = ?", (process_id, payload["id"], digest)).fetchone()[0])
    if new:
        for party_ref, contact in release.contacts.items():
            unknown = set(contact) - set(CONTACT_FIELDS)
            if unknown:
                raise ValueError(f"release {payload['id']!r}: contact fields {sorted(unknown)}")
            if any(contact.values()):
                conn.execute(
                    "INSERT INTO tender_contact_points (tender_release_id, party_ref, "
                    + ", ".join(CONTACT_FIELDS) + ") VALUES (?,?" + ",?" * len(CONTACT_FIELDS)
                    + ")", (release_id, party_ref,
                            *(contact.get(name) or None for name in CONTACT_FIELDS)))
    compile_process(conn, process_id)
    return Stored(process_id, release_id, new)


def _merged(earlier: dict[str, Any], later: dict[str, Any]) -> dict[str, Any]:
    """OCDS's record rule for one object: what a later release states replaces what an
    earlier one said, what it sets to null is removed, and what it leaves out stays. An
    award notice that names no deadline therefore keeps the deadline its invitation
    stated, while a draft's `status: None` leaves the tender with no status."""
    merged = dict(earlier)
    for key, value in later.items():
        if value is None:
            merged.pop(key, None)
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merged(merged[key], value)
        else:
            merged[key] = value
    return merged


def compile_process(conn: sqlite3.Connection, tender_process_id: int) -> None:
    """Rebuild one process's typed rows from its releases, oldest to newest.

    A notice its source revised is stored as several versions of ONE release (one
    `release_ref`), and only the newest version, by the source's own change stamp, is
    compiled: a field the revision stopped stating does not survive from the version
    it replaced. His ruling on #1658: the notice id stays the release id, where OCDS
    asks for an id unique within the ocid (ES-3 records the departure).

    The tender is every compiled release's `tender` merged in that order (`_merged`);
    an items list is replaced whole by the next release that states one. Parties,
    sectors and countries gather from every compiled release, a later release winning
    on the same party, code or country, because a revision restates them.
    """
    releases = [(int(row[0]), json.loads(row[1])) for row in conn.execute(
        "SELECT r.id, json(r.payload) FROM tender_releases r WHERE r.tender_process_id = ? "
        "AND r.id = (SELECT v.id FROM tender_releases v "
        "            WHERE v.tender_process_id = r.tender_process_id "
        "              AND v.release_ref = r.release_ref "
        "            ORDER BY coalesce(v.source_modified_at, '') DESC, v.id DESC LIMIT 1) "
        "ORDER BY r.released_at, coalesce(r.source_modified_at, ''), r.id",
        (tender_process_id,))]
    conn.execute("DELETE FROM tender_party_roles WHERE tender_party_id IN "
                 "(SELECT id FROM tender_parties WHERE tender_process_id = ?)",
                 (tender_process_id,))
    conn.execute("DELETE FROM tender_parties WHERE tender_process_id = ?", (tender_process_id,))
    conn.execute("DELETE FROM tender_items WHERE tender_process_id = ?", (tender_process_id,))
    conn.execute("DELETE FROM tender_classifications WHERE tender_process_id = ?",
                 (tender_process_id,))
    conn.execute("DELETE FROM tender_locations WHERE tender_process_id = ?",
                 (tender_process_id,))
    conn.execute("DELETE FROM tenders WHERE tender_process_id = ?", (tender_process_id,))

    parties: dict[str, dict[str, Any]] = {}
    classifications: dict[tuple[str, str], str | None] = {}
    locations: dict[str, dict[str, Any]] = {}
    tender: dict[str, Any] | None = None
    compiled_from: tuple[int, str] | None = None
    for release_id, payload in releases:
        for party in payload.get("parties", []):
            known = parties.setdefault(party["id"], {"roles": set()})
            known.update({k: v for k, v in party.items() if k != "roles"})
            known["roles"] |= set(party.get("roles", []))
        for item in payload.get("classifications", []):
            classifications[(item["scheme"], item["id"])] = item.get("description")
        for place in payload.get("locations", []):
            locations[place["sourceCountryCode"]] = place
        if "tender" in payload:
            tender = _merged(tender or {}, payload["tender"])
            compiled_from = (release_id, payload["date"])

    for ref, party in parties.items():
        identifier = party.get("identifier") or {}
        party_id = int(conn.execute(
            "INSERT INTO tender_parties (tender_process_id, party_ref, name, "
            "identifier_scheme, identifier_id, country_code) VALUES (?,?,?,?,?,?)",
            (tender_process_id, ref, party["name"], identifier.get("scheme"),
             identifier.get("id"), (party.get("address") or {}).get("countryCode"))).lastrowid)
        for role in sorted(party["roles"]):
            conn.execute("INSERT INTO tender_party_roles (tender_party_id, role) VALUES (?,?)",
                         (party_id, role))
    for (scheme, code), description in classifications.items():
        conn.execute("INSERT INTO tender_classifications (tender_process_id, scheme, code, "
                      "description) VALUES (?,?,?,?)",
                      (tender_process_id, scheme, code, description))
    for place in locations.values():
        conn.execute("INSERT INTO tender_locations (tender_process_id, country_code, "
                     "source_country_code, source_country_name) VALUES (?,?,?,?)",
                     (tender_process_id, place.get("countryCode"), place["sourceCountryCode"],
                      place.get("sourceCountryName")))
    if tender is None or compiled_from is None:
        return
    release_id, released_at = compiled_from
    value = tender.get("value") or {}
    period = tender.get("tenderPeriod") or {}
    conn.execute(
        "INSERT INTO tenders (tender_process_id, tender_ref, title, status, status_details, "
        "procurement_method, main_procurement_category, value_amount, value_currency, "
        "tender_period_end, tender_period_end_local_time, tender_period_end_zone, "
        "published_at, compiled_from_tender_release_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tender_process_id, tender.get("id"), tender.get("title"), tender.get("status"),
         tender.get("statusDetails"), tender.get("procurementMethod"),
         tender.get("mainProcurementCategory"), value.get("amount"), value.get("currency"),
         period.get("endDateLocal"), period.get("endTimeLocal"), period.get("endTimeZone"),
         released_at, release_id))
    for index, item in enumerate(tender.get("items", []), start=1):
        classification = item.get("classification") or {}
        conn.execute(
            "INSERT INTO tender_items (tender_process_id, item_ref, description, "
            "classification_scheme, classification_code) VALUES (?,?,?,?,?)",
            (tender_process_id, item.get("id") or str(index), item.get("description"),
             classification["scheme"], classification["id"]))
