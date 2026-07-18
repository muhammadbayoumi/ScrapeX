"""scrapex — the harvest CLI (Phase 0 surface).

Commands land phase by phase; Phase 0 ships exactly what Phase 0 built:
  init-db            create/upgrade harvest.db (A10 lock + S6 migrations)
  validate-manifest  parse + validate sources.yaml (S5; same check runs in CI)
  export-contract    write contracts/funnel-payload.schema.json from the model (T8)
  funnel-test        send a tiny self-test payload through the staging funnel
  status             per-source last-run age (S8 watchdog; stub until ingest lands)

Later phases add: probe, crawl, ingest, census, apply-decisions, feeds, publish.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import db as dbmod
from . import localinbox
from .config import MANIFEST_FILE, load_manifest
from .connectors.factory import build_connector
from .funnel import FunnelClient
from .ingest import ingest_payloads
from .reports import recent_observations, source_summary
from .payload import (
    PAYLOAD_VERSION,
    FunnelPayload,
    export_json_schema,
    utc_now_iso,
)
from .vocab import ExtractKind, PayloadClient

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"


def _cmd_init_db(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else dbmod.DEFAULT_DB_PATH
    with dbmod.write_lock(db_path):
        conn = dbmod.connect(db_path)
        try:
            applied = dbmod.migrate(conn)
        finally:
            conn.close()
    if applied:
        print(f"harvest.db at {db_path}: applied migrations {applied}")
    else:
        print(f"harvest.db at {db_path}: already at version — nothing to apply")
    return 0


def _cmd_validate_manifest(args: argparse.Namespace) -> int:
    path = Path(args.manifest) if args.manifest else MANIFEST_FILE
    manifest = load_manifest(path)
    active = [s.source_key for s in manifest.sources if s.active]
    print(f"OK: {len(manifest.sources)} sources, active: {active or 'none yet'}")
    return 0


def _cmd_export_contract(args: argparse.Namespace) -> int:
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTRACTS_DIR / "funnel-payload.schema.json"
    out.write_text(
        json.dumps(export_json_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out} (payload_version {PAYLOAD_VERSION})")
    return 0


def _cmd_funnel_test(args: argparse.Namespace) -> int:
    endpoint = args.endpoint or os.environ.get("SCRAPEX_FUNNEL_URL", "")
    token = args.token or os.environ.get("SCRAPEX_FUNNEL_TOKEN", "")
    client = FunnelClient(endpoint=endpoint, token=token)
    payload = FunnelPayload(
        payload_version=PAYLOAD_VERSION,
        source_key="FUNNEL_SELFTEST",
        kind=ExtractKind.PRODUCT_PRICES,
        client=PayloadClient.CLI,
        scraped_at=utc_now_iso(),
        source_url="scrapex://funnel-test",
        header=["check"],
        rows=[["ok"]],
    )
    chunks = client.send(payload)
    print(f"funnel accepted the self-test payload ({chunks} chunk[s]). "
          "Check the staging sheet _INBOX tab for a FUNNEL_SELFTEST row.")
    return 0


def _cmd_crawl(args: argparse.Namespace) -> int:
    entry = load_manifest().get(args.source)
    connector, fetcher = build_connector(entry)
    try:
        tables = list(connector.fetch(entry))
    finally:
        fetcher.close()
    base = args.inbox or localinbox.DEFAULT_INBOX_DIR
    rows = 0
    for table in tables:
        localinbox.write_payload(base, table.to_payload())
        rows += len(table.rows)
    print(f"crawled {entry.source_key}: {rows} rows "
          f"({fetcher.requests_count} requests) -> local inbox {base}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    entry = load_manifest().get(args.source)
    base = args.inbox or localinbox.DEFAULT_INBOX_DIR
    payloads = localinbox.read_payloads(base, entry.source_key)
    if not payloads:
        print(f"no payloads in local inbox for {entry.source_key} — run: scrapex crawl {entry.source_key}")
        return 1
    db_path = Path(args.db) if args.db else dbmod.DEFAULT_DB_PATH
    with dbmod.write_lock(db_path):
        conn = dbmod.connect(db_path)
        try:
            dbmod.migrate(conn)
            result = ingest_payloads(conn, entry, payloads)
            conn.commit()
        finally:
            conn.close()
    print(f"ingested {result.source_key} (run {result.run_id}, status {result.status.value}): "
          f"{result.observations} new observations, {result.duplicates} duplicates, "
          f"{result.products} new products, {result.variants} new variants, "
          f"{result.skipped_ignored} skipped (ignored), "
          f"{result.rejected_out_of_scope} out-of-scope, {len(result.errors)} errors")
    for err in result.errors[:10]:
        print(f"  ! {err}")
    if not args.keep:
        localinbox.clear(base, entry.source_key)
    return 0


def _cmd_peek(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else dbmod.DEFAULT_DB_PATH
    if not Path(db_path).exists():
        print("harvest.db not initialized — run: scrapex init-db")
        return 1
    conn = dbmod.connect(db_path)
    try:
        summary = source_summary(conn, args.source)
        if summary is None:
            print(f"no data for {args.source} yet — run: scrapex crawl {args.source} && scrapex ingest {args.source}")
            return 1
        sample = recent_observations(conn, args.source, args.limit)
    finally:
        conn.close()

    print(f"{summary.source_key} ({summary.source_name})")
    print(f"  last run: {summary.last_run or 'never'} ({summary.last_status or '-'})")
    print("  SOURCE-LOCAL layer (raw, as scraped):")
    print(f"    products: {summary.products} | variants: {summary.variants} | observations: {summary.observations}")
    print(f"    curation: " + ", ".join(f"{n} {status}" for status, n in sorted(summary.curation.items())))
    print("  UNIFIED layer (fills only after you curate — census/apply-decisions, Phase 2):")
    print(f"    matched variants: {summary.matched_variants} | published (in view): {summary.published_rows}")
    if sample:
        print(f"  {len(sample)} recent observations:")
        for row in sample:
            vat = "incl" if row["vat_included"] else "excl"
            name = (row["name"] or "")[:48]
            print(f"    • {name:50} {row['price']:>10} {row['currency']}  ({row['availability']}, vat={vat})")
    return 0


def _cmd_google_connect(args: argparse.Namespace) -> int:
    try:
        from .gdrive import get_credentials
    except ImportError:
        print("Google support needs: pip install -e .[google]", file=sys.stderr)
        return 1
    from .gdrive import GoogleNotConfiguredError
    try:
        get_credentials()  # opens the browser for "Sign in with Google" on first run
    except GoogleNotConfiguredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Signed in with Google — token cached. You can now: scrapex push <source>")
    return 0


def _publish_with(args: argparse.Namespace, sink, verb: str) -> int:
    """Shared body for `push` (Google) and `export` (local): same data, same
    arrangement, different sink."""
    from .publish import publish_source

    db_path = Path(args.db) if args.db else dbmod.DEFAULT_DB_PATH
    if not Path(db_path).exists():
        print("harvest.db not initialized — crawl + ingest first", file=sys.stderr)
        return 1
    conn = dbmod.connect(db_path)
    try:
        n, location = publish_source(conn, args.source, sink, args.folder, args.workbook)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"{verb} {n} rows to tab '{args.source}' in '{args.workbook}'")
    print(f"  {location}")
    return 0


def _cmd_push(args: argparse.Namespace) -> int:
    try:
        from .gdrive import DriveManager, GoogleNotConfiguredError, build_services, get_credentials
        from .publish import GoogleSink
    except ImportError:
        print("Google support needs: pip install -e .[google]", file=sys.stderr)
        return 1
    try:
        creds = get_credentials()
    except GoogleNotConfiguredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    drive, sheets = build_services(creds)
    return _publish_with(args, GoogleSink(DriveManager(drive, sheets)), "pushed")


def _cmd_export(args: argparse.Namespace) -> int:
    try:
        from .localsheets import LocalSink
    except ImportError:
        print("local export needs: pip install -e .[local]", file=sys.stderr)
        return 1
    return _publish_with(args, LocalSink(), "exported")


def _cmd_ui(args: argparse.Namespace) -> int:
    try:
        import uvicorn
        from .webui.app import create_app
    except ImportError:
        print("the UI needs the ui extra: pip install -e .[ui]", file=sys.stderr)
        return 1
    db_path = Path(args.db) if args.db else dbmod.DEFAULT_DB_PATH
    if not Path(db_path).exists():
        print("harvest.db not initialized — run: scrapex init-db, then crawl + ingest", file=sys.stderr)
        return 1
    app = create_app(db_path)
    url = f"http://{args.host}:{args.port}"
    print(f"ScrapeX UI → {url}   (Ctrl+C to stop)")
    if not args.no_open:
        import threading
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    # S8 watchdog: fleshed out when ingest lands (Phase 1); the surface exists
    # now so the owner's habit starts on day one.
    db_path = Path(args.db) if args.db else dbmod.DEFAULT_DB_PATH
    if not Path(db_path).exists():
        print("harvest.db not initialized — run: scrapex init-db")
        return 1
    conn = dbmod.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT ss.source_key, MAX(cr.started_at) AS last_run "
            "FROM source_site ss LEFT JOIN crawl_run cr ON cr.source_id = ss.source_id "
            "GROUP BY ss.source_key ORDER BY ss.source_key"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        print("no sources registered yet (sources land at first crawl/ingest)")
        return 0
    for row in rows:
        print(f"{row['source_key']:24} last run: {row['last_run'] or 'never'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrapex", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="create/upgrade harvest.db")
    p.add_argument("--db", help="database path (default: env SCRAPEX_DB_PATH or ~/.scrapex/harvest.db)")
    p.set_defaults(func=_cmd_init_db)

    p = sub.add_parser("validate-manifest", help="validate sources.yaml")
    p.add_argument("--manifest", help="manifest path (default: scraper/sources.yaml)")
    p.set_defaults(func=_cmd_validate_manifest)

    p = sub.add_parser("export-contract", help="write the funnel payload JSON schema")
    p.set_defaults(func=_cmd_export_contract)

    p = sub.add_parser("funnel-test", help="send a self-test payload to the staging funnel")
    p.add_argument("--endpoint", help="funnel URL (default: env SCRAPEX_FUNNEL_URL)")
    p.add_argument("--token", help="funnel token (default: env SCRAPEX_FUNNEL_TOKEN)")
    p.set_defaults(func=_cmd_funnel_test)

    p = sub.add_parser("crawl", help="fetch a source into the local inbox (dev loop)")
    p.add_argument("source", help="source_key from sources.yaml")
    p.add_argument("--inbox", help="local inbox dir (default: ~/.scrapex/inbox)")
    p.set_defaults(func=_cmd_crawl)

    p = sub.add_parser("ingest", help="ingest a source's local-inbox payloads into harvest.db")
    p.add_argument("source", help="source_key from sources.yaml")
    p.add_argument("--inbox", help="local inbox dir (default: ~/.scrapex/inbox)")
    p.add_argument("--db", help="database path")
    p.add_argument("--keep", action="store_true", help="keep inbox payloads after ingest")
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("peek", help="show what landed for a source (both warehouse layers + sample)")
    p.add_argument("source", help="source_key from sources.yaml")
    p.add_argument("--db", help="database path")
    p.add_argument("--limit", type=int, default=10, help="how many recent observations to sample")
    p.set_defaults(func=_cmd_peek)

    p = sub.add_parser("google-connect", help="Sign in with Google (one-time OAuth; needs .[google])")
    p.set_defaults(func=_cmd_google_connect)

    p = sub.add_parser("push", help="push a source's current prices to a Google Sheet tab")
    p.add_argument("source", help="source_key from sources.yaml")
    p.add_argument("--folder", default="ScrapeX", help="Drive folder name (created if absent)")
    p.add_argument("--workbook", default="ScrapeX Data", help="spreadsheet name (created if absent)")
    p.add_argument("--db", help="database path")
    p.set_defaults(func=_cmd_push)

    home_scrapex = str(Path.home() / "ScrapeX")
    p = sub.add_parser("export", help="export a source's current prices to a local .xlsx (no Google)")
    p.add_argument("source", help="source_key from sources.yaml")
    p.add_argument("--folder", default=home_scrapex, help=f"local folder (default: {home_scrapex})")
    p.add_argument("--workbook", default="ScrapeX Data", help="workbook file name (without .xlsx)")
    p.add_argument("--db", help="database path")
    p.set_defaults(func=_cmd_export)

    p = sub.add_parser("ui", help="launch the local browse UI (needs: pip install -e .[ui])")
    p.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1, local only)")
    p.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    p.add_argument("--db", help="database path")
    p.add_argument("--no-open", action="store_true", help="do not auto-open the browser")
    p.set_defaults(func=_cmd_ui)

    p = sub.add_parser("status", help="per-source last-run age (S8 watchdog)")
    p.add_argument("--db", help="database path")
    p.set_defaults(func=_cmd_status)

    return parser


def _force_utf8_output() -> None:
    """Windows consoles default to cp1252, which cannot encode Arabic product
    names or box-drawing chars (Q5: no locale-dependent I/O). Make stdout/stderr
    UTF-8 so `peek`/`ui` output never crashes on a raw console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass  # already UTF-8, or a stream that can't be reconfigured


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 — single explicit CLI error boundary (Q3)
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
