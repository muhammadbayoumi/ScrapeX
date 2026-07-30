"""Drive the MV3 extension through the experiments and write `results/`.

    python prepare.py          # snapshot the live warehouse (read-only)
    python baseline.py         # the Python/SQLite reference numbers + SQL trace
    npm install && npm run vendor
    python run.py              # this file

Nothing here talks to the shipping engine, the manifest, or the live database.
It serves `.work/` on 127.0.0.1, launches Chromium with `extension/` loaded,
and asks that extension questions.

`--headed` if the headless launch cannot start the MV3 service worker;
`--phases a,b,c` to re-run one experiment without repeating an hour of others.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import platform
import shutil
import socketserver
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / ".work"
RESULTS = HERE / "results"
STAGED = WORK / "ext"
PROFILE = WORK / "profile"
PORT = 8917
# Two copies of the same warehouse: as it lives on disk (WAL), and with WAL
# turned off. Which one a browser can actually open is question 1's real answer.
DB_URL_WAL = f"http://127.0.0.1:{PORT}/snapshot.db"
DB_URL = f"http://127.0.0.1:{PORT}/snapshot-nowal.db"
OPFS_WAL = "marketlens-wal.db"
OPFS_DB = "marketlens.db"

ALL_PHASES = [
    "env", "import", "describe", "migrate", "queries", "ingest",
    "restart", "contend", "journal", "quota", "sw",
]


# ---- the local file server -------------------------------------------------

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence the request log
        pass


def serve(directory: Path) -> socketserver.TCPServer:
    handler = functools.partial(_Quiet, directory=str(directory))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ---- staging ---------------------------------------------------------------

def stage(unlimited_storage: bool) -> Path:
    """Copy `extension/` into `.work/ext` so variants never edit the repo copy."""
    if not (HERE / "extension" / "vendor").is_dir():
        raise SystemExit("extension/vendor is missing — run: npm install && npm run vendor")
    if STAGED.exists():
        shutil.rmtree(STAGED)
    shutil.copytree(HERE / "extension", STAGED)
    manifest_path = STAGED / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not unlimited_storage:
        manifest["permissions"] = [p for p in manifest["permissions"] if p != "unlimitedStorage"]
        manifest["name"] += " (no unlimitedStorage)"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return STAGED


# ---- browser ---------------------------------------------------------------

class Browser:
    def __init__(self, playwright, ext_dir: Path, headed: bool, fresh_profile: bool):
        if fresh_profile and PROFILE.exists():
            shutil.rmtree(PROFILE, ignore_errors=True)
        PROFILE.mkdir(parents=True, exist_ok=True)
        self.context = playwright.chromium.launch_persistent_context(
            str(PROFILE),
            headless=not headed,
            channel="chromium",
            args=[
                f"--disable-extensions-except={ext_dir}",
                f"--load-extension={ext_dir}",
                "--no-first-run",
            ],
        )
        self.extension_id = self._wait_for_extension_id()
        self.page = self.context.new_page()
        self.page.goto(f"chrome-extension://{self.extension_id}/harness.html")
        self.page.wait_for_function("window.spikeReady === true", timeout=30_000)
        # Replaying an 18,297-statement ingest through Asyncify takes far longer
        # than Playwright's 30 s default, and a timeout here would look like a
        # failure of the engine rather than of the harness.
        self.page.set_default_timeout(45 * 60 * 1000)

    def _wait_for_extension_id(self, timeout_s: float = 30.0) -> str:
        """The id is read off the service worker's URL, so this also proves it started."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            for worker in self.context.service_workers:
                return worker.url.split("/")[2]
            try:
                self.context.wait_for_event("serviceworker", timeout=2000)
            except Exception:
                pass   # not up yet; the deadline is what decides
        raise SystemExit("the MV3 service worker never started — retry with --headed")

    def worker(self, command: str, args: dict | None = None, which: str = "spike"):
        return self.page.evaluate(
            f"([c, a]) => window.{which}(c, a)", [command, args or {}])

    def sw(self, command: str, args: dict | None = None, timeout: int | None = None):
        page = self.page
        if timeout:
            page.set_default_timeout(timeout)
        try:
            reply = page.evaluate(
                "([c, a]) => chrome.runtime.sendMessage({command: c, args: a})",
                [command, args or {}])
        finally:
            if timeout:
                page.set_default_timeout(45 * 60 * 1000)
        if reply is None:
            raise RuntimeError("service worker returned nothing (it may have been terminated)")
        if not reply.get("ok"):
            raise RuntimeError(f"service worker error: {reply.get('error')}")
        return reply["result"]

    def close(self):
        self.context.close()


# ---- experiments -----------------------------------------------------------

def load_traces() -> tuple[dict, list[dict]]:
    queries = json.loads((WORK / "trace-queries.json").read_text(encoding="utf-8"))["traces"]
    ingest = json.loads((WORK / "trace-ingest.json").read_text(encoding="utf-8"))["statements"]
    return queries, ingest


def phase_env(b: Browser) -> dict:
    out: dict = {"hardware": {"platform": platform.platform(), "processor": platform.processor()}}
    # Each probe is contained: one missing API must not cost the other answers.
    for key, fn in (
        ("dedicated_worker", lambda: b.worker("ping")),
        ("service_worker", lambda: b.sw("ping")),
        ("storage_estimate_before", lambda: b.worker("estimate")),
        ("persist_from_worker", lambda: b.worker("persist")),
        # `StorageManager.persist()` is Window-only, so the request has to be
        # made from the extension PAGE even though the storage it protects is
        # used by the worker. Whether it is granted decides if the warehouse is
        # evictable.
        ("persist_from_page", lambda: b.page.evaluate(
            "async () => ({ before: await navigator.storage.persisted(),"
            " granted: await navigator.storage.persist(),"
            " after: await navigator.storage.persisted() })")),
    ):
        try:
            out[key] = fn()
        except Exception as exc:
            out[key] = {"failed": f"{type(exc).__name__}: {str(exc)[:300]}"}
    return out


def phase_import(b: Browser) -> dict:
    """Can the warehouse land in OPFS at all, and how long does it take?"""
    out = {}
    # wa-sqlite reads real OPFS paths, so both warehouses are streamed in as files.
    out["download_wal"] = b.worker("download", {"url": DB_URL_WAL, "path": OPFS_WAL})
    out["download_nowal"] = b.worker("download", {"url": DB_URL, "path": OPFS_DB})
    out["tree_after"] = b.worker("tree")
    out["estimate_after"] = b.worker("estimate")
    return out


def phase_describe(b: Browser) -> dict:
    """Does `db/schema.sql`'s model survive the trip — and in which journal mode?"""
    out = {}
    for label, args in (
        # The warehouse exactly as it lives on disk today.
        ("wa-sqlite-wal", {"engine": "wa-sqlite", "dbPath": OPFS_WAL}),
        ("wa-sqlite-nowal", {"engine": "wa-sqlite", "dbPath": OPFS_DB}),
        # The SAH pool keeps its own opaque files, so it is handed the bytes.
        # Handed the WAL file on purpose: what it does with it is the finding.
        ("sahpool-from-wal", {"engine": "sahpool", "dbPath": "/marketlens.db", "importUrl": DB_URL_WAL}),
    ):
        try:
            out[label] = b.worker("open", args)
        except Exception as exc:  # a failure IS a result
            out[label] = {"failed": f"{type(exc).__name__}: {exc}",
                          "worker_console": b.worker("logs")}
        finally:
            try:
                b.worker("close")
            except Exception:
                pass
    return out


def phase_migrate(b: Browser) -> dict:
    """wa-sqlite's FAST OPFS VFS cannot be handed a file, so it rebuilds one.

    This is the migration Topology A would run on every existing user's machine
    the first time the extension started, so its cost is a first-class number.
    """
    try:
        return b.worker("open", {
            "engine": "ahp", "dbPath": "marketlens.db", "copyFrom": OPFS_DB})
    except Exception as exc:
        return {"failed": f"{type(exc).__name__}: {str(exc)[:1200]}",
                "worker_console": b.worker("logs")}
    finally:
        try:
            b.worker("close")
        except Exception:
            pass


def _query_statements(traces: dict, source_key: str) -> list[dict]:
    """The two statements that carry the Data page, as Python issued them."""
    return [s for s in traces[source_key] if "price_observation" in s["sql"]]


# Every engine the browser phases can measure, and how to open each one.
ENGINES = {
    # wa-sqlite's plain OPFS VFS: the only one that can be handed an existing
    # database file, and the slow one (Asyncify).
    "wa-sqlite": {"engine": "wa-sqlite", "dbPath": OPFS_DB},
    # The SQLite project's own build, sync access handles.
    "sahpool": {"engine": "sahpool", "dbPath": "/marketlens.db", "importUrl": DB_URL_WAL},
    # wa-sqlite's fast VFS, reachable only after the `migrate` phase rebuilds
    # the warehouse into its pool.
    "wa-sqlite-ahp": {"engine": "ahp", "dbPath": "marketlens.db"},
}


def phase_queries(b: Browser, repeats: int, engines: list[str]) -> dict:
    traces, _ = load_traces()
    out: dict = {}
    for engine, open_args in ((k, ENGINES[k]) for k in engines):
        engine_out: dict = {}
        try:
            engine_out["opened"] = b.worker("open", open_args)
            for source_key in traces:
                stmts = _query_statements(traces, source_key)
                per = []
                for stmt in stmts:
                    label = "count" if stmt["sql"].lstrip().upper().startswith("SELECT COUNT") else "rows"
                    try:
                        timing = b.worker("statement", {
                            "sql": stmt["sql"], "params": stmt["params"], "repeats": repeats})
                    except Exception as exc:
                        timing = {"failed": f"{type(exc).__name__}: {str(exc)[:300]}"}
                    per.append({"label": label, **timing})
                # End to end: the whole Data page's statement list, in order.
                try:
                    whole = b.worker("trace", {"statements": traces[source_key], "repeats": repeats})
                except Exception as exc:
                    whole = {"failed": f"{type(exc).__name__}: {str(exc)[:300]}"}
                engine_out[source_key] = {"statements": per, "table_payload": whole}
        except Exception as exc:
            engine_out["failed"] = f"{type(exc).__name__}: {str(exc)[:1200]}"
            try:
                engine_out["worker_console"] = b.worker("logs")
            except Exception:
                pass
        finally:
            try:
                b.worker("close")
            except Exception:
                pass
        out[engine] = engine_out
    return out


def phase_ingest(b: Browser, engines: list[str]) -> dict:
    _, statements = load_traces()
    out: dict = {"statements": len(statements)}
    for engine, open_args in ((k, ENGINES[k]) for k in engines):
        try:
            b.worker("open", open_args)
            t0 = time.perf_counter()
            result = b.worker("trace", {"statements": statements, "transaction": True})
            out[engine] = {
                **result,
                "driver_wall_s": round(time.perf_counter() - t0, 1),
            }
        except Exception as exc:
            out[engine] = {"failed": f"{type(exc).__name__}: {str(exc)[:400]}"}
        finally:
            try:
                b.worker("close")
            except Exception:
                pass
    return out


def phase_contend(b: Browser) -> dict:
    """Two lanes, one warehouse: what a second context gets while the first holds it."""
    held = b.worker("hold", {"path": OPFS_DB})
    same_context = b.worker("contend", {"path": OPFS_DB})
    other_worker = b.worker("contend", {"path": OPFS_DB}, which="rival")
    try:
        sw_side = b.sw("open", {"engine": "wa-sqlite", "dbPath": OPFS_DB})
        sw_side = {"opened_while_held": sw_side}
    except Exception as exc:
        sw_side = {"opened_while_held": f"{type(exc).__name__}: {str(exc)[:300]}"}
    released = b.worker("release")
    after = b.worker("contend", {"path": OPFS_DB})
    return {
        "held": held, "second_handle_same_worker": same_context,
        "second_handle_other_worker": other_worker,
        "service_worker": sw_side, "released": released, "after_release": after,
    }


def phase_journal(b: Browser, pages: int) -> dict:
    return b.worker("journal", {"pages": pages, "bytesPerPage": 1069})


def phase_quota(b: Browser) -> dict:
    return b.worker("quotaProbe", {"chunkMiB": 64, "maxMiB": 6144})


def phase_sw(b: Browser, heartbeat_s: int) -> dict:
    out: dict = {"scope": b.sw("ping")}
    try:
        out["opfs_write_capabilities_sw"] = b.sw("opfsWriteCapabilities")
    except Exception as exc:
        out["opfs_write_capabilities_sw"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    # The same probe from the window and the dedicated worker, so the
    # difference between the three scopes is measured rather than asserted from
    # a sentence in the spec.
    out["opfs_write_capabilities_worker"] = b.page.evaluate(
        "async () => { const root = await navigator.storage.getDirectory();"
        " const h = await root.getFileHandle('capability-probe-page.bin', {create: true});"
        " const r = { createSyncAccessHandle: typeof h.createSyncAccessHandle,"
        "   createWritable: typeof h.createWritable, scope: 'Window' };"
        " await root.removeEntry('capability-probe-page.bin').catch(() => {});"
        " return r; }")
    out["opfs_write_capabilities_dedicated_worker"] = b.worker("capabilities")

    try:
        out["opened_in_service_worker"] = b.sw("open", {"engine": "wa-sqlite", "dbPath": OPFS_DB})
    except Exception as exc:
        out["opened_in_service_worker"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    try:
        out["write_from_service_worker"] = b.sw("tryWrite")
    except Exception as exc:
        out["write_from_service_worker"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    # How long does a service worker doing pure OPFS work stay alive?
    t0 = time.perf_counter()
    try:
        out["heartbeat"] = b.sw("heartbeat", {"seconds": heartbeat_s},
                                timeout=(heartbeat_s + 120) * 1000)
        out["heartbeat"]["driver_wall_s"] = round(time.perf_counter() - t0, 1)
    except Exception as exc:
        out["heartbeat"] = {
            "died": True,
            "after_s": round(time.perf_counter() - t0, 1),
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
    try:
        out["after_heartbeat"] = b.sw("lastHeartbeat")
    except Exception as exc:
        out["after_heartbeat"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--phases", default=",".join(ALL_PHASES))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--journal-pages", type=int, default=3570)
    ap.add_argument("--heartbeat-seconds", type=int, default=360)
    ap.add_argument("--no-unlimited-storage", action="store_true")
    # Phases share OPFS state (import lands the warehouse; queries read it), so
    # re-running one phase alone needs the profile the previous run left behind.
    ap.add_argument("--keep-profile", action="store_true")
    # wa-sqlite's Asyncify VFS takes ~50 s per repeat of the Data page, so the
    # fast engines are usually measured with more repeats in a separate run.
    ap.add_argument("--engines", default=",".join(ENGINES))
    ap.add_argument("--out", default="results.json")
    args = ap.parse_args()
    phases = [p.strip() for p in args.phases.split(",") if p.strip()]
    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    unknown = [e for e in engines if e not in ENGINES]
    if unknown:
        raise SystemExit(f"unknown engine(s): {unknown}; choose from {list(ENGINES)}")

    if not (WORK / "snapshot.db").exists():
        raise SystemExit("run prepare.py first")
    if not (WORK / "trace-queries.json").exists():
        raise SystemExit("run baseline.py first")

    from playwright.sync_api import sync_playwright  # imported late: optional dep

    RESULTS.mkdir(exist_ok=True)
    ext = stage(unlimited_storage=not args.no_unlimited_storage)
    httpd = serve(WORK)
    out: dict = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "snapshot_bytes": (WORK / "snapshot.db").stat().st_size,
        "unlimited_storage": not args.no_unlimited_storage,
        "phases": {},
    }

    try:
        with sync_playwright() as pw:
            out["chromium"] = pw.chromium.executable_path
            # A FRESH profile: "did it survive a restart?" only means something
            # if the first launch started from nothing.
            b = Browser(pw, ext, args.headed, fresh_profile=not args.keep_profile)
            out["extension_id"] = b.extension_id
            try:
                for name, fn in (
                    ("env", lambda: phase_env(b)),
                    ("import", lambda: phase_import(b)),
                    ("describe", lambda: phase_describe(b)),
                    ("migrate", lambda: phase_migrate(b)),
                    ("queries", lambda: phase_queries(b, args.repeats, engines)),
                    ("ingest", lambda: phase_ingest(b, engines)),
                    ("contend", lambda: phase_contend(b)),
                    ("journal", lambda: phase_journal(b, args.journal_pages)),
                    ("quota", lambda: phase_quota(b)),
                    ("sw", lambda: phase_sw(b, args.heartbeat_seconds)),
                ):
                    if name not in phases:
                        continue
                    print(f"[phase] {name} ...", flush=True)
                    t0 = time.perf_counter()
                    try:
                        out["phases"][name] = fn()
                    except Exception as exc:
                        out["phases"][name] = {"failed": f"{type(exc).__name__}: {str(exc)[:600]}"}
                    print(f"[phase] {name} done in {time.perf_counter()-t0:.1f}s", flush=True)
            finally:
                b.close()

            if "restart" in phases:
                print("[phase] restart ...", flush=True)
                # Same profile directory, brand-new browser process.
                b2 = Browser(pw, ext, args.headed, fresh_profile=False)
                try:
                    survived = {"tree": b2.worker("tree"), "estimate": b2.worker("estimate")}
                    try:
                        b2.worker("open", {"engine": "wa-sqlite", "dbPath": OPFS_DB})
                        survived["wa_sqlite_after_restart"] = b2.worker("statement", {
                            "sql": "SELECT count(*) FROM price_observation", "repeats": 1})
                    except Exception as exc:
                        survived["wa_sqlite_after_restart"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                    out["phases"]["restart"] = survived
                finally:
                    b2.close()
    finally:
        httpd.shutdown()

    (RESULTS / args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
