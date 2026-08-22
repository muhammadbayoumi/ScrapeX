"""Two machines' warehouses become one, and only one machine may hold it at a time.

HIS RULING, 2026-08-22: both machines have developed muqawil, so the databases must be
merged, with **Drive as the single source of truth for DATA** while the repository stays
the single source of truth for CODE. Neither file may be copied over the other — each
holds work the other does not, and `R-24` says upgrade rather than replace.

THE MERGE IS DEFINABLE BECAUSE THE NATURAL KEYS EXIST, and that was measured before any of
this was written:

    generic_page_snapshot   20,379 rows, 20,379 distinct (source_url, content_hash)
    dataset_sighting        UNIQUE (dataset_key, external_id) in the schema
    generic_record          UNIQUE (dataset_definition_id, record_key) in the schema

Without those, a merge would mean remapping every autoincrement primary key and every
foreign key pointing at it — both machines hold a `page_snapshot_id = 1` for a different
page. That is `OP-30` at a much larger scale, and it is why "just merge them" is not an
operation until the keys are named.

ONLY THE EVIDENCE IS MERGED. Snapshots and sightings are the two things that cannot be
recomputed: a snapshot is a page as it was fetched, and a sighting is what the site showed
and when. **Everything else is rebuilt by `--approve` with no network** — records,
revisions, ingestions, the taxonomy and its memberships. That single decision is what keeps
this tractable: no primary key is ever remapped, because nothing that carries one travels.

AND THE OPERATION IS COMMUTATIVE AND IDEMPOTENT, which is what makes his plan safe:
downloading, merging, uploading and merging again converges instead of drifting. **Every
column merges with `min` or `max` and none with `+`** — a sum is neither, and the first
version of this used one for `seen_count`. Measured before it was fixed: three merges of
the same file took one id from 4 to 8 to 12 to 16 while this paragraph claimed otherwise.

THE PANEL ALREADY DOES THE UPLOAD, AND THE WRONG BUTTON IS NEXT TO THE RIGHT ONE.
`scrapex/bundle.py` builds a bundle containing `warehouse.db` — taken through sqlite3's own
backup API — and `extension/drive.js` uploads it resumably into a `ScrapeX backups` folder
with a `latest.json` pointer and three kept. The panel's buttons are `drive-backup` and
`drive-restore`, and the engine has no Google of its own by his ruling of 2026-08-11.

**AND THE WARNING THAT USED TO STAND HERE NAMED THE WRONG CONTROL — corrected 2026-08-22,
not deleted, per `C5`.** This paragraph said in capitals that `drive-restore` REPLACES the
live warehouse and must never be pressed on the other machine. It does not. That button is
wired to `fetchFromDrive` (`extension/app.js`), whose own comment reads *"DOWNLOADED, NOT
RESTORED"*, whose sentence ends *"It is not installed — this only checks it is there"*, and
whose label in `extension/app.html` is *"Fetch the latest backup"*. Nothing on the panel's
path reaches `registry.engine.restore`.

So the warning was guarding a control that is safe while the destructive one had no guard
at all: **`scrapex restore-database`**, a shipped subcommand that took a path and displaced
his only copy with nothing asked. It now requires the phrase `cli.RESTORE_PHRASE`, and the
refusal names THIS command as the alternative, because that is the whole of `R-43`: restore
replaces, merge adds. Nothing is erased either way — `EngineDatabase.restore` moves the
current file to `<stem>.replaced-<stamp>.db` — but the file stops being the LIVE one, and
the next crawl writes into the copy that arrived from Drive.

So the flow is: **backup** here, download there, and **merge** — never restore.

THE LOCK IS THE PART HIS PLAN WAS MISSING. Download → work → upload has nothing stopping
both machines doing it on the same day, and the second upload silently wins — Drive keeps
versions but cannot merge them. So a warehouse records which machine currently holds it,
and this module refuses to merge into a copy that somebody else holds.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

HOLDER = "checkout_holder"
HELD_AT = "checkout_at"


class NotYours(RuntimeError):
    """Somebody else holds this warehouse, so writing to it would lose their work."""


class NotMergeable(ValueError):
    """The two files cannot be merged, and the reason is named rather than guessed at."""


@dataclass
class Merged:
    """What one merge changed, per table, both directions named.

    COUNTS AND NOT A BOOLEAN, because "it worked" is not a report a person can act on:
    a merge that added 12,000 snapshots and one that added none are both successes and
    completely different news.
    """

    dictionaries_added: int = 0
    snapshots_added: int = 0
    sightings_added: int = 0
    sightings_updated: int = 0
    #: Datasets whose derived rows are now stale and must be rebuilt by `--approve`.
    rebuild: tuple[str, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        lines = [
            f"dictionaries      {self.dictionaries_added:,}",
            f"snapshots added   {self.snapshots_added:,}",
            f"sightings added   {self.sightings_added:,}",
            f"sightings updated {self.sightings_updated:,}",
        ]
        if self.rebuild:
            lines.append(
                "NOW REBUILD THE DERIVED ROWS — nothing here wrote one. Run "
                "`scrapex contractors --approve --run-ref <ref>` for each run whose "
                f"pages arrived; the datasets affected are {', '.join(self.rebuild)}. "
                "It costs no network: that is what the fetch/interpret seam is for.")
        else:
            lines.append("nothing arrived, so nothing needs re-approving")
        return "\n".join(lines)


def holder(conn: sqlite3.Connection) -> str | None:
    """Which machine holds this warehouse, or `None` if nobody has claimed it.

    `scrapex_meta` AND NOT A NEW TABLE, for the reason `account.py` already gives about
    `account_owner`: it holds exactly this kind of fact, and a key/value row needs no
    migration — so a warehouse from before this feature answers `None` rather than
    failing to open.
    """
    row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ? LIMIT 1",
                       (HOLDER,)).fetchone()
    return str(row[0]) if row and row[0] else None


def claim(conn: sqlite3.Connection, machine: str) -> None:
    """Take the warehouse for this machine. Refuses if somebody else holds it.

    RE-CLAIMING YOUR OWN IS ALLOWED and does not fail, because a session that crashed
    mid-merge must be able to pick the same copy back up. Taking one somebody ELSE holds
    is refused, and the message names them — the whole point is that the loser of a race
    finds out from a refusal rather than from missing data a week later.
    """
    if not machine.strip():
        raise NotMergeable("a claim needs a machine name; an empty one holds nothing")
    current = holder(conn)
    if current is not None and current != machine:
        raise NotYours(
            f"{current!r} holds this warehouse. Merging into it would overwrite work "
            f"that machine has not uploaded yet. Have it run `--release` first, or take "
            f"it deliberately with `--force` if you know it is finished.")
    for key, value in ((HOLDER, machine), (HELD_AT, _now(conn))):
        conn.execute(
            "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def release(conn: sqlite3.Connection) -> None:
    """Give the warehouse back, so the other machine may claim it."""
    conn.execute("DELETE FROM scrapex_meta WHERE key IN (?,?)", (HOLDER, HELD_AT))
    conn.commit()


def _now(conn: sqlite3.Connection) -> str:
    return str(conn.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now')").fetchone()[0])


def _carry_dictionaries(conn: sqlite3.Connection) -> int:
    """The compression dictionaries travel too, and they are not derived data.

    THE ONE APPARENT EXCEPTION TO "ONLY THE EVIDENCE TRAVELS", and it stops being an
    exception once stated properly: a `zstd-raw-dict` body is UNREADABLE without the exact
    page it was compressed against, and that page is stored nowhere else. So a dictionary
    IS evidence — it is part of how the snapshot is written down. `scrapex/snapshotbody.py`
    reaches the same conclusion from the other side, which is why `snapshot_dictionary`
    forbids UPDATE and DELETE: losing one loses every page compressed against it, silently,
    with no repair.

    MATCHED ON THE BODY, NEVER ON THE LABEL. A dictionary is seeded from the first page of
    its kind that a machine happens to fetch, so `muqawil.org/listing` names one
    298,954-byte page here and a different one there. `label` is UNIQUE, so an arriving
    dictionary whose label is taken but whose body is new gets a suffixed label rather than
    being dropped — dropping it would leave its pages unreadable, and overwriting is
    forbidden by the trigger anyway.
    """
    ours = {bytes(body) for (body,) in conn.execute(
        "SELECT body FROM snapshot_dictionary")}
    labels = {label for (label,) in conn.execute(
        "SELECT label FROM snapshot_dictionary")}
    added = 0
    for label, body in conn.execute(
            "SELECT label, body FROM other.snapshot_dictionary ORDER BY dict_id"):
        if bytes(body) in ours:
            continue
        wanted, n = label, 2
        while wanted in labels:
            wanted, n = f"{label}#{n}", n + 1
        conn.execute("INSERT INTO snapshot_dictionary (label, body) VALUES (?,?)",
                     (wanted, body))
        labels.add(wanted)
        ours.add(bytes(body))
        added += 1
    return added


def _no_page_lost_its_dictionary(conn: sqlite3.Connection) -> None:
    """A compressed page that names no dictionary is a page that no longer exists.

    CHECKED INSIDE THE TRANSACTION, so a failure rolls the merge back instead of reporting
    a success for somebody to discover later. The remap above is a lookup that may yield
    NULL, and SQLite accepts NULL there because the column is nullable for the sake of
    'plain' rows. That is the one way this can lose data quietly, so it is the one thing
    asserted afterwards.
    """
    orphans = conn.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot "
        " WHERE html_codec <> 'plain' AND html_dict_id IS NULL").fetchone()[0]
    if orphans:
        raise NotMergeable(
            f"{orphans:,} merged pages are compressed but name no dictionary, so their "
            "bodies could never be decoded again. The merge was rolled back. The other "
            "warehouse is missing rows from snapshot_dictionary that its own pages need.")


def _same_shape(conn: sqlite3.Connection) -> None:
    """Both sides must be the same kind of database at the same schema version.

    REFUSED RATHER THAN ATTEMPTED, because a v8 file and a v9 one disagree about which
    tables exist — merging into the older would drop what the newer knows, and merging
    into the newer would leave the older's rows referencing columns it has never had.
    `R-24` is the same rule one level up: upgrade, do not replace.
    """
    ours = conn.execute("PRAGMA user_version").fetchone()[0]
    theirs = conn.execute("PRAGMA other.user_version").fetchone()[0]
    if ours != theirs:
        raise NotMergeable(
            f"this warehouse is at schema v{ours} and the other is at v{theirs}. Run "
            "`scrapex init-db` on the older one first — a merge across versions would "
            "either drop what the newer knows or leave rows pointing at columns that do "
            "not exist.")
    kind = conn.execute(
        "SELECT value FROM other.scrapex_meta WHERE key = 'database_kind'").fetchone()
    if kind is not None and str(kind[0]) != "engine":
        raise NotMergeable(
            f"the other file says it is a {kind[0]!r} database, not an engine one")


def merge(conn: sqlite3.Connection, other: str, *, machine: str) -> Merged:
    """Take everything the other warehouse knows and this one does not.

    THE CLAIM IS CHECKED FIRST and the merge does not start without it, because the whole
    reason the claim exists is that the loser of a race must find out before it writes
    rather than after somebody's day is gone.

    ATTACH AND NOT TWO CONNECTIONS, so every insert below is one statement inside one
    transaction. Reading rows into Python and writing them back would put 20,000
    round trips and a partial-failure mode where there is no need for either.
    """
    if holder(conn) != machine:
        raise NotYours(
            f"this machine is {machine!r} and the warehouse is held by "
            f"{holder(conn)!r}. Claim it first.")

    conn.execute("ATTACH DATABASE ? AS other", (other,))
    try:
        _same_shape(conn)
        report = Merged()

        report.dictionaries_added = _carry_dictionaries(conn)

        # SNAPSHOTS: ADDITIVE, KEYED ON WHAT THE PAGE IS. `page_snapshot_id` is never
        # carried across — it is assigned here — so nothing downstream can reference a
        # foreign machine's id. The columns are named rather than `SELECT *` because the
        # id must be excluded and because a column added later must break this loudly
        # instead of silently shifting values one place left.
        #
        # AND `html_dict_id` IS REMAPPED, NOT COPIED. It was copied, and that is the one
        # place this module broke its own rule: a dictionary id is a foreign machine's
        # PRIMARY KEY, so carrying it verbatim is exactly what the paragraph above says
        # never happens. It failed loudly on his real transfer — FOREIGN KEY constraint
        # failed, because `snapshot_dictionary` was not merged at all — and that was the
        # LUCKY outcome. Had the ids happened to line up, 20,379 pages would have been
        # inserted pointing at the WRONG dictionary and decoded to nothing, discovered
        # whenever somebody next opened one.
        before = conn.execute(
            "SELECT COUNT(*) FROM generic_page_snapshot").fetchone()[0]
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "(source_url, content_type, html_content, content_hash, captured_at, "
            " crawl_run_ref, html_codec, html_dict_id) "
            "SELECT source_url, content_type, html_content, content_hash, captured_at, "
            "       crawl_run_ref, html_codec, "
            # Matched on the BODY, which is the only honest key: each machine seeds a
            # dictionary from its own first page of a kind, so the same `label` on two
            # machines names two different bodies. A 'plain' row has no dict_id, and NULL
            # stays NULL because a subquery over no rows IS NULL.
            "       (SELECT ours.dict_id FROM snapshot_dictionary AS ours "
            "          JOIN other.snapshot_dictionary AS od ON od.body = ours.body "
            "         WHERE od.dict_id = theirs.html_dict_id) "
            "  FROM other.generic_page_snapshot AS theirs "
            " WHERE NOT EXISTS (SELECT 1 FROM generic_page_snapshot AS ours "
            "                    WHERE ours.source_url = theirs.source_url "
            "                      AND ours.content_hash = theirs.content_hash)")
        _no_page_lost_its_dictionary(conn)
        report.snapshots_added = (
            conn.execute("SELECT COUNT(*) FROM generic_page_snapshot").fetchone()[0]
            - before)

        # SIGHTINGS: MERGED, NOT REPLACED. A sighting is the only record of what the site
        # showed and when, and the two machines saw different moments — so the earliest
        # first sighting, the latest last, and the counts ADDED. `last_absent_at` takes the
        # later, because an absence proved on either machine is an absence proved.
        before = conn.execute("SELECT COUNT(*) FROM dataset_sighting").fetchone()[0]
        conn.execute(
            "INSERT INTO dataset_sighting "
            "(dataset_key, external_id, first_seen_at, last_seen_at, seen_count, "
            " first_run_ref, last_absent_at, last_absent_run_ref) "
            "SELECT dataset_key, external_id, first_seen_at, last_seen_at, seen_count, "
            "       first_run_ref, last_absent_at, last_absent_run_ref "
            # `WHERE true` IS NOT DECORATION. SQLite cannot parse
            # `INSERT ... SELECT ... ON CONFLICT` without something closing the SELECT —
            # the parser cannot tell an upsert clause from part of the query — and it
            # answers `near "DO": syntax error`. Documented quirk, and the one-word fix.
            "  FROM other.dataset_sighting WHERE true "
            "ON CONFLICT(dataset_key, external_id) DO UPDATE SET "
            "  first_seen_at = MIN(first_seen_at, excluded.first_seen_at), "
            "  last_seen_at  = MAX(last_seen_at,  excluded.last_seen_at), "
            # `MAX` AND NOT `+`, AND THE FIRST VERSION SUMMED. Measured: three merges of
            # the same file took one id's `seen_count` from 4 to 8 to 12 to 16, while the
            # docstring above claimed the operation was idempotent. It was not, and the
            # test that missed it counted ROWS and never looked at a value.
            #
            # SUMMING IS ALSO WRONG ON THE FIRST MERGE, which is the deeper reason. Two
            # machines crawling the same listing observe the SAME site state, so their
            # counts are two observations of one fact rather than two facts. `MAX` keeps
            # "seen at least this many times" — which is what `sighting_frequencies` uses
            # to estimate coverage — and is commutative and idempotent besides.
            "  seen_count    = MAX(seen_count, excluded.seen_count), "
            "  last_absent_at = MAX(IFNULL(last_absent_at, ''), "
            "                       IFNULL(excluded.last_absent_at, ''))")
        report.sightings_added = (
            conn.execute("SELECT COUNT(*) FROM dataset_sighting").fetchone()[0] - before)
        report.sightings_updated = (
            conn.execute("SELECT COUNT(*) FROM other.dataset_sighting").fetchone()[0]
            - report.sightings_added)

        if report.snapshots_added:
            # WHOSE DERIVED ROWS ARE NOW STALE. Named rather than rebuilt here: a rebuild
            # needs a run ref and belongs to the command that owns approving, and one
            # function that both merges evidence and re-interprets it would be two
            # responsibilities with one error path.
            report.rebuild = tuple(
                str(row[0]) for row in conn.execute(
                    "SELECT DISTINCT dataset_key FROM dataset_definition "
                    " WHERE valid_to IS NULL ORDER BY dataset_key"))
        conn.commit()
        return report
    finally:
        # THE TRANSACTION MUST CLOSE BEFORE THE DETACH, or SQLite answers
        # `database other is locked` and the real failure above is replaced by a
        # confusing one — which is exactly what happened the first time this ran.
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        # DETACHED WHETHER OR NOT IT WORKED, or the next call in the same process finds
        # the name taken and fails for a reason that has nothing to do with the merge.
        conn.execute("DETACH DATABASE other")
