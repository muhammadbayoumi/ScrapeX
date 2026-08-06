"""A backup a machine can restore, and a bare extension can read.

DECISION 8 and §5 of the platform plan: a fresh machine, signed in, with no
engine installed, must show the owner his data and export it.

The expensive reading of that is "run SQLite in the extension". Spike 2 measured
it (`spikes/opfs-sqlite/FINDINGS.md`): the schema runs under MV3 and survives a
restart, but OPFS loses WAL, an access handle is exclusive, the service worker
cannot write, and `wa-sqlite` is **70-208x slower than Python on the Data page's
own query** — with a fast VFS that cannot open an existing database at all.

None of that is needed, because viewing and exporting is READ-ONLY. So a backup
is a BUNDLE:

    warehouse.db          the restorable artefact, for a machine that installs
                          the engine. Taken with sqlite3's own backup API, so
                          it is consistent even while something is writing.
    datasets/<KEY>/*      a plain export per dataset — JSON Lines and CSV —
                          which is what a bare extension reads.
    manifest.json         what is inside, how many rows, and a checksum for
                          every file.

ONE WRITER, ONE READER, and no database in a browser.

THE EXPORT IS NOT A FOURTH READER. `reports.export_source_table` and its two
companions already produce exactly what the Google Sheet and the Excel workbook
carry; this writes the same rows to files. A bundle with its own SQL would drift
from the three surfaces that already agree, which is the failure
`fields.column_order` exists to prevent.

WHY CHECKSUMS ARE NOT DECORATION. `latest.json` may only ever point at a bundle
that `verify()` has passed. A backup nobody checked is a backup discovered to be
empty on the day it is needed, and that day is by definition the worst one.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .archive import backup_database
from .reports import (export_details_table, export_history_table,
                      export_source_table, list_sources)
from .payload import utc_now_iso
from .version import VERSION

#: The bundle's own shape, separate from the engine's version and from the
#: database schema's. A restoring reader checks this first: it can refuse a
#: layout it does not understand instead of half-reading one.
BUNDLE_FORMAT = 1

#: Read in 1 MiB blocks. The warehouse is 112 MB today and grows; hashing it in
#: one read would hold the whole file in memory for no gain.
_BLOCK = 1024 * 1024


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_BLOCK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Fault:
    """Something wrong with a bundle, in the words a reader needs.

    `path` is relative to the bundle root so the message is the same wherever
    the bundle was downloaded to.
    """
    path: str
    problem: str


@dataclass
class BundleReport:
    root: Path
    files: int = 0
    bytes: int = 0
    datasets: dict = field(default_factory=dict)
    faults: list[Fault] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.faults


def _write_table(directory: Path, name: str, header: list[str],
                 rows: list[list]) -> dict:
    """One table, twice: JSON Lines for a reader, CSV for a spreadsheet.

    Both, and not one: JSON Lines keeps a number a number and an empty cell
    distinguishable from an empty string, which is what the panel needs to show
    the data honestly; CSV is what the owner double-clicks. Writing only the
    first would make "export it" mean "write a converter first".
    """
    directory.mkdir(parents=True, exist_ok=True)
    jsonl = directory / f"{name}.jsonl"
    with open(jsonl, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(zip(header, row)), ensure_ascii=False))
            handle.write("\n")

    comma = directory / f"{name}.csv"
    # newline="" is required by csv on Windows or every row gains a blank line.
    # utf-8-sig so Excel opens Arabic without being told the encoding.
    with open(comma, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)

    return {"rows": len(rows), "columns": len(header),
            "files": [jsonl.name, comma.name]}


def build(db_path: Path | str, out_dir: Path | str, *,
          source_keys: list[str] | None = None) -> BundleReport:
    """Write a complete bundle into `out_dir`, which is created if absent.

    The `.db` is copied through sqlite3's own backup API rather than the
    filesystem: a plain copy of a database being written to is a copy of a
    half-written page, and archive.backup_database already refuses to "back up
    nothing" when the source is missing.
    """
    db_path, out_dir = Path(db_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied = backup_database(db_path, tag="bundle")
    warehouse = out_dir / "warehouse.db"
    shutil.move(str(copied), warehouse)

    conn = sqlite3.connect(f"file:{warehouse}?mode=ro", uri=True)
    try:
        available = [s.source_key for s in list_sources(conn)]
        wanted = available if source_keys is None else [
            key for key in source_keys if key in available]

        datasets: dict[str, dict] = {}
        for key in wanted:
            folder = out_dir / "datasets" / key
            tables: dict[str, dict] = {}
            header, rows = export_source_table(conn, key)
            # A source with no priced rows is not a fault: it is a source that
            # has been configured and never crawled, and the plan names that
            # state on the Library page. It is recorded with zero rows rather
            # than left out, so a reader can tell "nothing yet" from "missing".
            tables["current"] = _write_table(folder, "current", header, rows)
            for name, table in (("details", export_details_table(conn, key)),
                                ("history", export_history_table(conn, key))):
                extra_header, extra_rows = table
                if extra_rows:
                    tables[name] = _write_table(folder, name, extra_header, extra_rows)
            datasets[key] = tables
    finally:
        conn.close()

    manifest = {
        "bundle_format": BUNDLE_FORMAT,
        "engine_version": VERSION,
        "created_at": utc_now_iso(),
        "source": str(db_path),
        "datasets": datasets,
        # Every file, with its size and digest. The manifest itself is not in
        # here — it cannot contain its own hash — which is why verify() checks
        # the manifest is READABLE separately from checking the files it names.
        "files": {},
    }
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(out_dir).as_posix()
        manifest["files"][relative] = {"bytes": path.stat().st_size,
                                       "sha256": sha256_of(path)}

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return verify(out_dir)


def verify(bundle_dir: Path | str) -> BundleReport:
    """Read a bundle back and check it is what its manifest says.

    Every fault is reported, not just the first: a caller deciding whether to
    publish this as `latest` needs the whole picture, and stopping at the first
    bad file hides how bad it is.
    """
    root = Path(bundle_dir)
    report = BundleReport(root=root)

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        report.faults.append(Fault("manifest.json", "missing"))
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        report.faults.append(Fault("manifest.json", f"unreadable: {error}"))
        return report

    fmt = manifest.get("bundle_format")
    if fmt != BUNDLE_FORMAT:
        # Refused whole rather than half-read. A newer bundle may have moved
        # anything, and guessing which parts are still compatible is how a
        # restore silently loses a dataset.
        report.faults.append(Fault(
            "manifest.json",
            f"bundle_format {fmt!r}, and this engine reads {BUNDLE_FORMAT}"))
        return report

    named = manifest.get("files") or {}
    if not named:
        report.faults.append(Fault("manifest.json", "names no files"))

    for relative, expected in sorted(named.items()):
        path = root / relative
        if not path.is_file():
            report.faults.append(Fault(relative, "named in the manifest and missing"))
            continue
        size = path.stat().st_size
        if size != expected.get("bytes"):
            report.faults.append(Fault(
                relative, f"{size} bytes, manifest says {expected.get('bytes')}"))
            continue
        actual = sha256_of(path)
        if actual != expected.get("sha256"):
            report.faults.append(Fault(relative, "checksum does not match"))
            continue
        report.files += 1
        report.bytes += size

    # A file nobody named is as much a problem as a file that went missing:
    # something wrote into this bundle after it was sealed.
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in named:
            report.faults.append(Fault(relative, "present and not in the manifest"))

    # The row counts, read back from the files rather than trusted. A truncated
    # export has a valid checksum for its truncated self.
    for key, tables in (manifest.get("datasets") or {}).items():
        counts = {}
        for name, described in tables.items():
            jsonl = root / "datasets" / key / f"{name}.jsonl"
            if not jsonl.is_file():
                continue
            with open(jsonl, encoding="utf-8") as handle:
                rows = sum(1 for line in handle if line.strip())
            counts[name] = rows
            if rows != described.get("rows"):
                report.faults.append(Fault(
                    f"datasets/{key}/{name}.jsonl",
                    f"{rows} rows, manifest says {described.get('rows')}"))
        report.datasets[key] = counts

    return report


def read_dataset(bundle_dir: Path | str, source_key: str,
                 table: str = "current") -> list[dict]:
    """What a reader without an engine gets: rows, as dictionaries.

    This is the whole of Decision 8 on the reading side, and it is deliberately
    this short — no SQL, no schema, no database. The panel does the same thing
    in JavaScript over the same file.
    """
    path = Path(bundle_dir) / "datasets" / source_key / f"{table}.jsonl"
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# ---- what actually travels ---------------------------------------------------
# MEASURED on the owner's own warehouse, 2026-08-06:
#
#     warehouse.db   116 MB
#     exports         93 MB   (64 jsonl + 29 csv)
#     ----------------------
#     bundle         209 MB
#     zipped          33 MB   6.3x smaller, in one second
#
# Decision 12 makes the upload frequency a setting because "a daily full upload
# that changes nothing is not free". 209 MB would have made that setting a
# necessity; 33 MB makes it a preference, and one second of CPU is not a cost
# worth arguing about.
#
# It also gives `latest.json` ONE artefact to point at and one checksum to name,
# instead of seventy-one.


def pack(bundle_dir: Path | str, archive_path: Path | str) -> dict:
    """Compress a verified bundle into one file, and describe it.

    Refuses to pack a bundle that does not verify. The whole point of
    `latest.json` naming only a validated bundle is lost if the validation can
    be skipped by packing first and checking later.
    """
    root, archive = Path(bundle_dir), Path(archive_path)
    report = verify(root)
    if not report.ok:
        raise ValueError(
            "refusing to pack a bundle that does not verify: "
            + "; ".join(f"{f.path}: {f.problem}" for f in report.faults[:3]))

    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                out.write(path, path.relative_to(root).as_posix())
    return {"path": str(archive), "bytes": archive.stat().st_size,
            "sha256": sha256_of(archive), "files": report.files,
            "uncompressed_bytes": report.bytes}


def unpack(archive_path: Path | str, out_dir: Path | str) -> BundleReport:
    """Extract a bundle and verify it, refusing anything that escapes the folder.

    A bundle arrives from Drive, which is outside this machine. A zip entry
    named `../../autorun` or `C:/Windows/...` is the oldest trick there is, and
    Python's `extractall` has historically obliged. Every name is resolved
    against the destination and refused if it lands outside it.
    """
    archive, root = Path(archive_path), Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    destination = root.resolve()

    with zipfile.ZipFile(archive) as bundled:
        for entry in bundled.infolist():
            if entry.is_dir():
                continue
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination):
                raise ValueError(
                    f"refusing an archive entry that escapes the bundle: "
                    f"{entry.filename!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundled.open(entry) as source, open(target, "wb") as handle:
                shutil.copyfileobj(source, handle)

    return verify(root)
