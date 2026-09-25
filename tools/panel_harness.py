"""Load the Chrome side panel in a real browser, with chrome.* and fetch stubbed.

The panel is an extension page: `chrome.tabs/runtime/storage` are undefined over
file://, and app.js dies on load without them. This module builds a single
self-contained page from the panel's own HTML, CSS and JS, injects a shim, and
lets a caller drive it.

It exists as its own module because two very different callers need exactly the
same page: `screenshot_panel.py` photographs it, and `tests/test_panel_dom.py`
asserts against it. A second copy of the stub would drift, and the two would stop
describing the same product — which is the whole failure this harness prevents.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"

DEFAULT_BACKEND = "http://127.0.0.1:8000"

# A site whose name and URL are deliberately punishing: long Arabic, a long host,
# and mixed direction — the cases spec 28 asks to be tested.
STRESS_SOURCES = [
    {"source_key": "LONG_AR", "base_url": "https://very-long-subdomain.example-store-name.com.sa",
     "source_name": "متجر مواد البناء والتشطيبات المتكاملة للمقاولات الكبرى بالمملكة",
     "family": "salla-html", "active": True, "implemented": True,
     "observations": 128394, "products": 9321},
    {"source_key": "SHORT", "base_url": "https://a.co", "source_name": "A",
     "family": "shopify-json", "active": True, "implemented": True,
     "observations": 3, "products": 1},
    {"source_key": "NOT_READY", "base_url": "https://unsupported-platform.example.com",
     "source_name": "Unsupported Platform Store", "family": "TBD-probe",
     "active": False, "implemented": False, "observations": 0, "products": 0},
    # A GENERIC DATASET, shaped exactly as `_dataset_rows` builds one, because the
    # rule it exercises is keyed on `kind` and no other row here has that key.
    # Without it `test_dataset_action_opens_the_workspace_directly` could assert
    # that EVERY card carries an actions menu and pass for ten days while
    # `sourceMenu` gave a dataset none — which is what happened.
    #
    # `last_success` CARRIES A DATE, and that is #255's doing rather than a
    # decorative choice: `_dataset_freshness` returns the capture instant with
    # `rows_seen` and `requests_count` both 0, so a crawled dataset reads "Last
    # crawled …" instead of "no successful crawl yet" over 17,304 rows. A literal
    # `None` here was true of the engine for about ten minutes and would now be the
    # stub disagreeing with the shipped product.
    #
    # `coverage` CARRIES THE SECOND CRAWL, and this row is now ONE card where the
    # engine used to send two (`R-47`, `REQ-37`): `_dataset_listing` folds
    # `contractor_profiles` into `contractors` on their confirmed one-to-one
    # relationship and reports the child as coverage instead of as a second
    # population. The numbers are his warehouse's, measured read-only 2026-08-23.
    {"kind": "dataset", "source_key": "contractors",
     # `site_key` IS WHAT THE ENGINE SENDS AND THIS FIXTURE DID NOT.
     # `scrapex/webui/app.py`'s dataset rows set `source_key` to the DATASET key and
     # carry the site separately, so a stub without it exercises a shape the product
     # never produces -- and the crawl action needs exactly this field, because
     # `POST /api/jobs` resolves a source key and 404s for a dataset key.
     "site_key": "muqawil_org",
     "source_name": "muqawil.org contractors", "source_name_ar": "",
     "base_url": "https://muqawil.org", "family": "generic",
     "active": True, "implemented": True, "supports_history": False,
     "observations": 17304, "products": 17304,
     "coverage": [{"dataset_key": "contractor_profiles",
                   "label": "Contractor profiles",
                   "stored": 704, "population": 17304}],
     # BOTH THINGS WAITING, because the card draws a line for each and a stub carrying
     # neither would let a guard for them pass on an empty card -- the shape of failure
     # this file has paid for twice: no dataset-kind source for weeks while a test
     # asserted every card has a menu, and `backups: []` beside `backup_count: 2`.
     #
     # The numbers are his warehouse's, measured read-only 2026-09-06: a listing crawl
     # that finished with its pages uninterpreted, and 469 sighted contractors with no
     # profile page stored.
     # ALL THREE THINGS WAITING, because the card draws a line for each and a stub
     # carrying one of them would let a guard for the others pass on an empty card --
     # the shape of failure this file has paid for three times now.
     #
     # His warehouse, measured read-only 2026-09-06: a listing crawl whose pages are
     # uninterpreted, 469 sighted contractors with no profile page, and a run he
     # cancelled holding 3,138 stored readings.
     "work_waiting": {"interpret": {"crawl_finished_at": "2026-09-06T05:01:44Z",
                                    "interpreted_at": None},
                      # TWO NUMBERS SINCE THE FETCH GAP AND THE ROW GAP WERE SPLIT.
                      # `fetch` is what a request would buy; `rowless` is the coverage
                      # figure. EQUAL HERE, which is the state before any fetch has run
                      # and the one that offers the button -- his warehouse on 2026-09-07
                      # at 10:33. The state where they DIVERGE is driven by a test with
                      # its own `sources=` stub, because that branch withholds the button
                      # and a default carrying it would hide the offer everywhere else.
                      "profiles": {"rowless": 469, "fetch": 469},
                      "resumable": {"run_ref": "job-job_925080aad843",
                                    "job_ref": "job_925080aad843",
                                    "status": "cancelled",
                                    "stopped_at": "2026-09-05T05:06:20Z",
                                    "readings": 3138}},
     "last_success": {"started_at": "2026-08-21T18:40:11Z",
                      "finished_at": "2026-08-21T18:40:11Z",
                      "rows_seen": 0, "requests_count": 0},
     "kept_pages": 0, "kept_at": None},
]

ACTIVE_TAB = {"url": "https://shop.example.com/products/lamp",
              "title": "Example Store — Lamps"}

PROBE_RESULT = {
    "url": "https://shop.example.com", "reachable": True,
    "family": "shopify-json", "implemented": True,
    "evidence": ["/products.json returned a Shopify products array (24 products)"],
    "notes": "Known family with a connector — you can capture immediately.",
    "suggested": {"source_key": "SHOP_EXAMPLE", "source_name": "متجر الأمثلة للمواد",
                  "base_url": "https://shop.example.com", "family": "shopify-json",
                  "currency": "SAR", "default_region": "SA", "vat_mode": "incl",
                  "fetcher": "http", "cadence": "daily", "authority": "shop",
                  "kind": "product_prices", "scope": "census", "active": False},
}

OUTPUTS = [
    {"key": "local_db", "label": "Local database", "ready": True, "required": True,
     "detail": "Always on — the source of truth. It cannot be disabled.",
     "blocker": "", "settings_url": ""},
    {"key": "excel", "label": "Excel workbook", "ready": True, "required": False,
     "detail": "", "blocker": "", "settings_url": "/exports"},
    {"key": "apps_script", "label": "Google Sheets via Apps Script", "ready": False,
     "required": False, "settings_url": "/sync",
     "blocker": "Missing: Deployment URL and token. Deploy the script, then save both here."},
    {"key": "google_drive", "label": "Google Drive and Sheets", "ready": False,
     "required": False, "settings_url": "/sync",
     "blocker": "Not signed in yet — use Continue with Google."},
]


def stub(backend: str = DEFAULT_BACKEND, *, engine_up=True, sources=None, jobs=None,
         records=None, changes=None, slow=False, tab=None, resolve=None, probe=None,
         fail_routes=(), storage=None, logs=None, extension_version=None,
         copy_check=None, copy_check_echoes=True, bundles=None, adopt=None,
         engine_version=None, version_reporting=True, omit_capabilities=(),
         timezone=None, schedules=None, rates_status=None,
         protocol_version=None, engine_manifest=None,
         signed_in=None, signin_error=None, signin_delay_ms=0,
         signin_never_returns=False, route_delays=None, blackhole_routes=(),
         native_mode="absent", google_account_mode="ok",
         remembered_accounts=None, drive=None,
         silent_for=None, revoke_status=200,
         worker_alive=True, engine_build=None, bundle=None) -> str:
    """A chrome.* shim plus a fetch() interceptor.

    Any state can be rendered deterministically, including ones a live engine
    cannot easily produce: a route that fails, an engine that is down, a tab that
    is not a website.

    The three version knobs are what make the compatibility work testable:
    `extension_version` is what `chrome.runtime.getManifest()` reports (Chrome's
    only honest answer to "what is loaded"), `engine_version` is what the engine
    says it is, and `version_reporting=False` removes /api/version entirely — an
    engine built before it existed, which is not a broken route and must not be
    read as one.

    /api/version is answered by the REAL scrapex.version.version_report, never
    by a hand-written fixture: a stub ledger would let the panel be tested
    against a compatibility rule the engine does not have.

    `signed_in` is the account chrome.identity hands back — None for the
    machine nobody has signed in on, which is every machine before M1c and the
    default here. `signin_error` is what Chrome puts in runtime.lastError
    instead of a token, and it is a separate knob because a closed consent
    window and a mismatched OAuth client are different sentences.

    `engine_manifest` is the fifth: the body of `ScrapeX/json/version.json` on
    the public delivery endpoint. None means the file is not there, answered as
    a 404 — which is what the hub gives TODAY, no engine having been released,
    so the default is the truth rather than a convenience.

    `protocol_version` is the fourth knob and it defaults to the REAL
    scrapex.native.PROTOCOL_VERSION for the same reason. /api/health has carried
    it since the handshake moved onto the transport that carries the traffic,
    and this stub did not — so the panel was being tested against an engine that
    stays silent about the one thing that can refuse an impossible pair.
    """
    from scrapex.native import PROTOCOL_VERSION
    from scrapex.version import VERSION, MINIMUM_EXTENSION_VERSION, version_report

    manifest_version = json.loads(
        (EXT / "manifest.json").read_text(encoding="utf-8"))["version"]
    extension_version = manifest_version if extension_version is None else extension_version
    engine_version = VERSION if engine_version is None else engine_version
    # `engine_build` is the sixth knob. None means "what a live engine says today":
    # a source run, level with the disk — which is the truth on the owner's machine
    # whenever he has just restarted, and the state that must render as no badge at
    # all. `False` REMOVES the key, which is an engine built before the field
    # existed and is not a fault. A dict overrides it outright, which is how the
    # stale and moved states are rendered: they cannot be produced from a live
    # engine on demand, which is the whole reason this harness exists.
    build = {"mode": "source", "sealed_at": "2026-08-23T05:00:00+00:00",
             "commit": "d10e974f97cb65103df74e470f3821af32b78002",
             "commit_now": "d10e974f97cb65103df74e470f3821af32b78002",
             "moved": False, "stale": False,
             "detail": "running from source, and level with the code on disk."}
    if isinstance(engine_build, dict):
        build = engine_build
    health = {"ok": True, "app": "scrapex", "version": engine_version,
              "worker_alive": worker_alive,
              "latest_extension_version": VERSION,
              "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
              "protocol_version": PROTOCOL_VERSION if protocol_version is None
                                  else protocol_version,
              "sources_with_data": 2}
    if engine_build is not False:
        health["build"] = build
    routes = {
        "/api/health": health,
        "/api/sources": {"sources": STRESS_SOURCES if sources is None else sources},
        "/api/jobs": {"jobs": jobs or []},
        "/api/records": records or {"records": [], "total": 0, "next_cursor": None},
        "/api/changes": changes or {"summary": {}, "changes": []},
        "/api/schedules": schedules or {
            "schedules": [],
            "note": "Schedules run only while the ScrapeX engine is "
                    "running. Nothing can wake a sleeping or "
                    "powered-off machine."},
        "/api/outputs": {"outputs": OUTPUTS},
        # THE SCHEMA BLOCK IS PART OF THE DEFAULT, and leaving it out is the shape of a
        # failure this repository has paid for: the harness carried no dataset-kind
        # source for weeks while a test asserted every card has a menu. The Database
        # page reads these three fields, so a stub without them would let it render
        # "unreadable" in every DOM test and pass.
        #
        # BEHIND BY ONE, so the default state exercises the branch that has a button to
        # press rather than the quiet one.
        "/api/storage": storage or {
            # THE LAYOUT THE ENGINE ACTUALLY PRODUCES. `scrapex/db.py:39-40`
            # says `~/.scrapex/harvest.db` is NOT the warehouse -- the real one
            # is the engine database under `~/.scrapex/engine/` -- and `folder`
            # is the directory that HOLDS it, which is what the live engine
            # returns. The stub was wrong on both, and a status line designed
            # against it could not tell two installations apart.
            "path": "C:\\Users\\Owner\\.scrapex\\engine\\scrapex-engine.db",
            "folder": "C:\\Users\\Owner\\.scrapex\\engine",
            "backup_folder": "C:\\Users\\Owner\\.scrapex",
            "sizes": {"db_bytes": 4194304, "wal_bytes": 8192, "shm_bytes": 32768,
                      "free_bytes": 51539607552, "backup_bytes": 8388608,
                      "backup_count": 2},
            # NARROW BY DEFAULT, because that is what the route answers now: the
            # corruption scan is O(file size) and is asked for, not drawn. A stub
            # claiming `integrity_checked` would hide the whole Corruption row.
            "health": {"status": "healthy", "ok": True, "integrity_checked": False,
                       "detail": ("Readable, at the expected version, and the right "
                                  "kind of file. Corruption has not been checked.")},
            "schema": {"version": 17, "expected": 18,
                       "pending": ["0018_a_job_may_interpret_what_a_crawl_stored.sql"]},
            "last": {"at": "2026-09-03T09:28:39Z", "ok": True},
            # NOT YET CHECKED, so the default exercises the branch with a control to
            # press rather than the one that reports a stored verdict.
            "integrity": None,
            # TWO OF THEM, MATCHING `backup_count`, AND NEWEST FIRST. This was `[]`
            # beside a count of 2 -- a stub that contradicted itself, and the Backups
            # row reads THIS list rather than the count, so every DOM test would have
            # asserted against "no backup" while the card claimed two.
            "backups": [
                {"path": "C:\\Users\\Owner\\.scrapex\\harvest.pre-upgrade-"
                         "20260903T092839Z.backup.db",
                 "name": "harvest.pre-upgrade-20260903T092839Z.backup.db",
                 "bytes": 4194304, "taken_at": "2026-09-03T09:28:39Z",
                 "modified_at": "2026-09-03T09:28:45Z", "tag": "pre-upgrade"},
                {"path": "C:\\Users\\Owner\\.scrapex\\harvest.manual-"
                         "20260830T045246Z.backup.db",
                 "name": "harvest.manual-20260830T045246Z.backup.db",
                 "bytes": 4194304, "taken_at": "2026-08-30T04:52:46Z",
                 "modified_at": "2026-08-30T04:52:52Z", "tag": "manual"},
            ],
            # A ZIP IN THE FOLDER BY DEFAULT, so the state with a control to
            # press is the one every test meets unless it asks otherwise. This
            # is what somebody arriving on a second machine has: a bundle
            # downloaded out of Drive and nothing yet that `restore` will look
            # at. `bundles=[]` is the empty folder, which is its own branch --
            # the card stays and explains what to put there.
            "bundles": [
                {"name": "scrapex-bundle-20260906-021500.zip",
                 "bytes": 655360000,
                 "modified_at": "2026-09-06T02:15:00Z"},
            ] if bundles is None else bundles},
        "/api/rates/google-finance": rates_status if rates_status is not None else {
            "automatic": True,
            "refresh_hours": 6,
            "tracked_currencies": ["SAR", "AED", "EUR", "GBP", "JPY"],
            "latest_rates": [
                {"currency": "AED", "per_usd": 3.6725,
                 "as_of": "2026-08-02T10:29:00Z"},
                {"currency": "EUR", "per_usd": 0.92,
                 "as_of": "2026-08-02T10:29:00Z"},
                {"currency": "GBP", "per_usd": 0.79,
                 "as_of": "2026-08-02T10:29:00Z"},
                {"currency": "JPY", "per_usd": 147.3,
                 "as_of": "2026-08-02T10:29:00Z"},
                {"currency": "SAR", "per_usd": 3.75,
                 "as_of": "2026-08-02T10:29:00Z"},
            ],
            "last_checked": "2026-08-02T10:28:32Z",
            "latest_market_at": "2026-08-02T10:29:00Z",
            "rows": 710,
            "due": False,
            "detail": "Exchange rates updated.",
            "warnings": [],
        },
        "/api/resolve": resolve if resolve is not None else {"matched": False},
        "/api/probe": probe if probe is not None else PROBE_RESULT,
        # The crawl pace lives in the panel now (owner's rule, 2026-07-29:
        # every setting in the extension, the web page display-only).
        "/api/settings": {"settings": {
            "crawl_honour_delay": {"value": "1"},
            "crawl_min_interval_s": {"value": "1.0"},
            "crawl_parallel_sources": {"value": "1"},
            "crawl_timeout_s": {"value": "30"},
            "crawl_user_agent": {"value": ""},
            "log_retention_days": {"value": "30"}}},
        # The shared display time zone (spec 33). None is the real default state
        # — no zone chosen yet, so every surface follows what it detects.
        "/api/timezone": {"timezone": timezone},
    }
    if version_reporting:
        # Keyed by the path WITHOUT its query string: the interceptor below
        # matches by prefix, and the panel sends ?extension_version=…
        report = version_report(extension_version or None)
        if omit_capabilities:
            # An engine that reports its capabilities and does not have this
            # one. Not a fiction: it is every engine one release behind, which
            # is what the panel meets the day the ledger grows an entry.
            report = dict(report, capabilities=[
                c for c in report["capabilities"] if c["key"] not in omit_capabilities])
        routes["/api/version"] = report
    # A write answers differently from a read on the same path: POST /api/jobs
    # returns the new job's ref, and the panel stores it to start polling. The
    # read table would hand back the job LIST, so anything that checked what a
    # click actually queued was testing against a shape the engine never sends.
    write_routes = {
        "/api/jobs": {"job_ref": "job_stub", "status": "queued"},
        # WHAT THE Check integrity CONTROL ASKS FOR. `at` is the engine's stamp on the
        # verdict, which is the whole reason the route is a POST: the page says WHEN
        # corruption was last looked for, and without a recorded moment a card showing
        # no problems is indistinguishable from a card that never asked.
        "/api/storage/integrity": {
            "status": "healthy", "ok": True, "integrity_checked": True,
            "problems": [], "foreign_key_problems": 0,
            "at": "2026-09-06T12:45:10Z", "detail": "No problems found."},
        # WHERE TO PUT THE FILE. The engine opens the folder and answers a
        # state; the panel reads nothing out of it, so the assertion a test can
        # make is that the request was sent AND which folder was named --
        # `which` comes from a fixed set precisely so no path can come from the
        # page.
        "/api/storage/open-folder": {"ok": True, "opened": True,
                                     "detail": "The folder is open."},
        # WHAT UNPACKING ONE ANSWERS. `ok` is the ENGINE'S verdict on the
        # database that came out, not on whether the zip was read: a bundle
        # built by a newer engine verifies its digests perfectly and then is not
        # a warehouse this build can open. `adopt=` is how a test reaches that.
        "/api/storage/adopt-bundle": dict({
            "ok": True,
            "name": "harvest.bundle-20260906T021500Z.backup.db",
            "path": r"C:\Users\Owner\.scrapex"
                    r"\harvest.bundle-20260906T021500Z.backup.db",
            "bytes": 4194304,
            "from_bundle": "scrapex-bundle-20260906-021500.zip",
            "health": {"status": "healthy", "ok": True},
            "detail": ("scrapex-bundle-20260906-021500.zip is unpacked as "
                       "harvest.bundle-20260906T021500Z.backup.db. It is listed "
                       "as a copy now -- check it, then restore it from the "
                       "same card."),
        }, **(adopt or {})),
    }
    # The job log endpoint. A distinct shape from the jobs LIST (both live under
    # /api/jobs), and matched ahead of it by the interceptor's `/logs` check —
    # otherwise every log fetch would get the job list and the panel would draw
    # an empty log. Carries `total` so the "all shown" caption has its number.
    entries = logs if logs is not None else []
    log_payload = {"entries": entries, "total": len(entries), "truncated": False}
    # What chrome.storage.local already holds when the panel opens. `backend` is
    # what engine.js reads; `remembered_accounts` seeds the account directory so
    # a card with more than one row can be driven at all — the panel can only
    # ever write ONE account into it by signing in.
    local_seed = {"backend": backend}
    if remembered_accounts is not None:
        local_seed["scrapex-accounts-v1"] = remembered_accounts
    local_seed = json.dumps(local_seed)
    return f"""
if (typeof AbortSignal !== 'undefined' && !AbortSignal.timeout) {{
  AbortSignal.timeout = (ms) => {{
    const c = new AbortController();
    setTimeout(() => c.abort(), ms);
    return c.signal;
  }};
}}
window.chrome = {{
  // getManifest is the extension's only honest answer to "which version of ME
  // is running", so the panel reads it and the harness has to provide it.
  runtime: {{ getURL: p => p, lastError: null,
              getManifest: () => ({{version: {extension_version!r}}}),
              sendNativeMessage: (_host, message, callback) => {{
                window.__nativeCalls.push(message.command);
                if (NATIVE_MODE === "nonresponsive") return;
                if (NATIVE_MODE === "absent") {{
                  chrome.runtime.lastError = {{message: "Specified native messaging host not found."}};
                  callback(undefined);
                  chrome.runtime.lastError = null;
                  return;
                }}
                callback({{ok: true, installed: false}});
              }} }},
  tabs: {{ query: async () => [{json.dumps(tab if tab is not None else ACTIVE_TAB)}],
           create: () => {{}} }},
  // A REAL store, not a fixed answer. accounts.js writes the remembered account
  // directory through here and reads it back; a `set` that threw everything away
  // would let a broken write pass every test driven by this harness, which is
  // the shape of failure this file exists to prevent.
  storage: {{ local: (() => {{
    const held = {local_seed};
    return {{
      get: async (keys) => {{
        if (typeof keys === "string") return keys in held ? {{[keys]: held[keys]}} : {{}};
        return {{...held}};
      }},
      set: async (patch) => {{ Object.assign(held, patch); }},
      // A store you cannot delete from is not the one the panel talks to.
      // "Create a spreadsheet" clears the chosen export target through here, so
      // a stub without `remove` turns a working button into a TypeError that
      // only appears in the browser.
      remove: async (keys) => {{
        for (const key of (typeof keys === "string" ? [keys] : keys)) delete held[key];
      }},
    }};
  }})(),
  // The chooser's handoff lives here. Nothing survives the page, which is
  // exactly what chrome.storage.session is.
  session: (() => {{
    const kept = {{}};
    return {{
      get: async (keys) => {{
        if (typeof keys === "string") return keys in kept ? {{[keys]: kept[keys]}} : {{}};
        return {{...kept}};
      }},
      set: async (patch) => {{ Object.assign(kept, patch); }},
      remove: async (keys) => {{
        for (const key of (typeof keys === "string" ? [keys] : keys)) delete kept[key];
      }},
    }};
  }})() }},
  // chrome.identity reports failure by leaving the token undefined and setting
  // runtime.lastError, so the shim must be able to do BOTH — a stub that only
  // ever returned a token could not test a single refusal branch.
  identity: {{
    getAuthToken: (opts, cb) => {{
      if (SIGNIN_NEVER_RETURNS) return;
      if (SIGNIN_ERROR) {{ chrome.runtime.lastError = {{message: SIGNIN_ERROR}};
                           cb(undefined);
                           chrome.runtime.lastError = null; return; }}
      // The delay is about WHEN Chrome answers, not WHAT it answers, so it
      // wraps both outcomes. It used to sit below the signed-out branch, which
      // returned first -- so `signin_delay_ms` did nothing for a signed-out
      // panel and the waiting state was unobservable in the one case a test
      // wanted to see it.
      const answer = () => {{
        if (!SIGNED_IN) {{ chrome.runtime.lastError =
                             {{message: "The user did not approve access."}};
                           cb(undefined);
                           chrome.runtime.lastError = null; return; }}
        cb("stub-token");
      }};
      if (SIGNIN_DELAY_MS) {{ setTimeout(answer, SIGNIN_DELAY_MS); return; }}
      answer();
    }},
    // The removed tokens are RECORDED, not just acted on. A 401 that forgets to
    // clear Chrome's cache leaves a dead token that every later sign-in hands
    // back, and the panel then asks the owner to sign in to an account he is
    // already signed in to -- indistinguishable, from the outside, from a 401
    // that cleared it properly.
    removeCachedAuthToken: (opts, cb) => {{
      window.__sx_removed_tokens = (window.__sx_removed_tokens || [])
        .concat([opts && opts.token]);
      SIGNED_IN = null; cb && cb();
    }},
    // ---- the multi-account half, absent until 2026-08-16 -------------------
    //
    // `getAuthToken` above speaks only for the Chrome profile's PRIMARY
    // account, so everything the account switcher does -- switching, adding,
    // and now signing out of a row that is not the current one -- goes through
    // `launchWebAuthFlow` instead. Neither of these two existed here, so
    // `identity.js:authorize()` hit the `getRedirectURL()` try/catch and
    // returned state "failed" under every panel test ever written. The whole
    // multi-account surface was unreachable, and silently: a test could drive
    // the button and read a plausible error message.
    getRedirectURL: () => "https://harness.chromiumapp.org/",
    launchWebAuthFlow: (opts, cb) => {{
      const url = new URL(opts.url);
      const hint = url.searchParams.get("login_hint") || "";
      window.__sx_auth_flows = (window.__sx_auth_flows || []).concat([
        {{hint, interactive: Boolean(opts.interactive),
          prompt: url.searchParams.get("prompt")}}]);
      // WHO GOOGLE WILL ANSWER FOR, SILENTLY. `prompt=none` succeeds only
      // where there is a live session, so the test names the set -- and an
      // account outside it produces the real refusal shape
      // (`error=login_required`), not a rejected promise.
      const live = SILENT_FOR === null || SILENT_FOR.includes(hint);
      if (!opts.interactive && !live) {{
        cb("https://harness.chromiumapp.org/#error=login_required");
        return;
      }}
      cb("https://harness.chromiumapp.org/#access_token=minted-for-"
         + encodeURIComponent(hint || "default")
         + "&token_type=Bearer&expires_in=3599&scope="
         + encodeURIComponent(url.searchParams.get("scope") || ""));
    }},
  }},
}};

// SIGNING IN A SECOND TIME, which this harness could not model at all.
//
// `removeCachedAuthToken` sets SIGNED_IN to null, correctly: Chrome really has
// forgotten the token. But a person who signs out and presses Sign in again
// gets a working sign-in, and until this existed no test could reach that
// state — which is exactly where the owner found the panel listing him as
// signed out while the header said he was signed in (2026-08-12).
//
// A test-only door, and a narrow one: it restores what Chrome would answer and
// nothing else. The panel is driven through its own button either way.
window.__sx_grant_again = (account) => {{ SIGNED_IN = account; }};
let SIGNED_IN = {json.dumps(signed_in)};
const SIGNIN_ERROR = {json.dumps(signin_error)};
const SIGNIN_DELAY_MS = {json.dumps(signin_delay_ms)};
const SIGNIN_NEVER_RETURNS = {str(signin_never_returns).lower()};
// `null` means Google answers a silent mint for ANY account, which is the
// ordinary case. A list names the ones with a live session, so a test can say
// "this account's session has ended" without inventing an error shape.
const SILENT_FOR = {json.dumps(silent_for)};
const REVOKE_STATUS = {json.dumps(revoke_status)};
const NATIVE_MODE = {json.dumps(native_mode)};
const GOOGLE_ACCOUNT_MODE = {json.dumps(google_account_mode)};
const DRIVE = {json.dumps(drive)};
// THE BUNDLE ROUTES, so a whole backup can be driven end to end.
// Without this the harness could show the Manage-account screen and never
// press its button: `/api/bundle` 404s, so every test of the control that
// takes a backup could only ever see it fail. The two production defects
// this feature has had -- a 541,531,989-byte read that returned 0, and two
// builds spliced into one Drive object -- were both on the happy path.
const BUNDLE = {json.dumps(bundle)};
// One validator for the whole session, which is what a real engine serves
// while the file on disk does not change. `range()` sends it back as
// `If-Range`; a fake that varied it would fail every chunk after the first.
const BUNDLE_ETAG = '"harness-archive"';
const ROUTES = {json.dumps(routes)};
const WRITE_ROUTES = {json.dumps(write_routes)};
const LOG_PAYLOAD = {json.dumps(log_payload)};
const ENGINE_UP = {str(engine_up).lower()};
const SLOW = {str(slow).lower()};
const FAIL = {json.dumps(list(fail_routes))};
// THE COPY CHECK. `POST /api/storage/integrity` grew an optional
// `backup_path`, and the verdict ECHOES the file it read -- an engine that
// predates the field ignores it and answers about the live warehouse, which
// would read as reassurance about the wrong file. `copy_check_echoes=False`
// is that older engine, and it is the only way to test the panel's guard
// against it.
const COPY_CHECK = {json.dumps(copy_check)};
const COPY_CHECK_ECHOES = {str(copy_check_echoes).lower()};
// The release feed is not the engine, and must be answered BEFORE the
// engine-down branch below. Letting a stopped engine make the endpoint
// unreachable would have tested the Engines page — the one page whose whole
// purpose is to work with no engine installed — against a state that cannot
// happen.
const ENGINE_MANIFEST = {json.dumps(engine_manifest)};
window.__calls = [];
window.__nativeCalls = [];
// The BODY of every write, which __calls (a path list) cannot carry — and the
// body is where "resume" lives, so a test that only saw the path could not
// tell a resume from a run that discards the journal.
window.__writes = [];
const ROUTE_DELAYS = {json.dumps(route_delays or {})};
const BLACKHOLE_ROUTES = {json.dumps(list(blackhole_routes))};
const waitWithSignal = (ms, signal) => new Promise((resolveWait, rejectWait) => {{
  let timer = null;
  const aborted = () => {{
    if (timer !== null) clearTimeout(timer);
    rejectWait(signal.reason || Object.assign(new Error("aborted"), {{name: "AbortError"}}));
  }};
  if (signal && signal.aborted) {{ aborted(); return; }}
  if (signal) signal.addEventListener("abort", aborted, {{once: true}});
  timer = setTimeout(() => {{
    if (signal) signal.removeEventListener("abort", aborted);
    resolveWait();
  }}, ms);
}});
window.fetch = async (url, options = {{}}) => {{
  const path = String(url).replace({backend!r}, "");
  const method = (options && options.method) || "GET";
  window.__calls.push(path);
  if (method !== "GET") {{
    let body = null;
    try {{ body = JSON.parse((options && options.body) || "null"); }} catch (_) {{}}
    window.__writes.push({{path, method, body}});
  }}
  // GOOGLE'S REVOKE ENDPOINT, which had no route here at all — so it fell
  // through to the generic 404, `identity.js` counted that as NOT revoked
  // (only `ok || 400` is), and EVERY sign-out driven through this harness
  // silently took the `local-only` path and painted "Google answered 404 to
  // the revoke request." No test read that element, which is the only reason
  // it went unnoticed. The tokens are recorded because which token was ended
  // is the whole question when several accounts are signed out at once.
  if (String(url).includes("oauth2.googleapis.com/revoke")) {{
    let ended = "";
    try {{ ended = new URLSearchParams(options.body || "").get("token") || ""; }}
    catch (_) {{}}
    window.__sx_revoked = (window.__sx_revoked || []).concat([ended]);
    return new Response("", {{status: REVOKE_STATUS}});
  }}

  // DRIVE'S RESUMABLE UPLOAD, before the read branch below. `UPLOAD` is
  // `.../upload/drive/v3/files`, which CONTAINS `drive/v3/files`, so without
  // this the handshake fell into the folder search, came back with no
  // `Location`, and `upload` refused with "no-session" -- a real refusal for a
  // fake reason, which is the worst kind of green.
  if (DRIVE && String(url).includes("uploadType=resumable")) {{
    window.__sx_uploads = (window.__sx_uploads || []).concat(
      [JSON.parse((options.body) || "{{}}").name || ""]);
    return {{ ok: true, status: 200,
              headers: {{get: (k) => (String(k).toLowerCase() === "location"
                ? "https://upload.harness.invalid/session/1" : null)}},
              json: async () => ({{}}), text: async () => "" }};
  }}
  if (String(url).startsWith("https://upload.harness.invalid/session/")) {{
    // One chunk is enough here: the archive this harness serves is small. The
    // 308-until-complete path is covered by extension/tests, against `upload`
    // itself rather than through the panel.
    window.__sx_chunks = (window.__sx_chunks || []).concat(
      [(options.headers || {{}})["Content-Range"] || ""]);
    // THE FILE JOINS THE FOLDER. Drive's own listing shows what was just put
    // there, and a fake whose folder never changes cannot tell a screen that
    // refreshes from one that does not -- which is the whole reason the backup
    // button was moved next to the list.
    const named = (window.__sx_uploads || []).slice(-1)[0] || "from-harness";
    const id = "uploaded-" + ((window.__sx_chunks || []).length);
    if (DRIVE) {{
      DRIVE.files = (DRIVE.files || []).filter(f => f.name !== named)
        .concat([{{id, name: named, createdTime: "2026-09-06T00:00:00Z",
                   size: String((BUNDLE && BUNDLE.bytes) || 0)}}]);
    }}
    return {{ ok: true, status: 200, headers: {{get: () => null}},
              json: async () => ({{id, name: named}}), text: async () => "" }};
  }}
  if (DRIVE && method === "DELETE"
      && String(url).includes("googleapis.com/drive/v3/files/")) {{
    window.__sx_pruned = (window.__sx_pruned || []).concat([String(url)]);
    return {{ ok: true, status: 204, headers: {{get: () => null}},
              json: async () => ({{}}), text: async () => "" }};
  }}

  // GOOGLE DRIVE. Without this every Drive read 404s and the Manage-account
  // screen can only ever be seen in its failure state — which is how it was
  // first shipped to review. `drive: None` keeps that behaviour deliberately,
  // so the error path stays testable too.
  //
  // Three requests, told apart the way drive.js builds them: `alt=media` is a
  // download, `orderBy` is only on the folder listing, and anything else is the
  // search for the folder itself.
  if (String(url).includes("googleapis.com/drive/v3/files")) {{
    if (!DRIVE) {{
      return {{ ok: false, status: 404, statusText: "Not Found",
                headers: {{get: () => null}},
                json: async () => ({{}}), text: async () => "" }};
    }}
    const target = String(url);
    if (target.includes("alt=media")) {{
      const id = decodeURIComponent(target.split("/files/")[1].split("?")[0]);
      const pointer = (DRIVE.files || []).find(f => f.name === "latest.json");
      const body = pointer && pointer.id === id
        ? JSON.stringify(DRIVE.pointer || {{}}) : "";
      return {{ ok: true, status: 200, headers: {{get: () => null}}, body: null,
                blob: async () => new Blob([body]),
                text: async () => body, json: async () => JSON.parse(body || "null") }};
    }}
    if (target.includes("orderBy")) {{
      return {{ ok: true, status: 200, headers: {{get: () => null}},
                json: async () => ({{files: DRIVE.files || []}}) }};
    }}
    return {{ ok: true, status: 200, headers: {{get: () => null}},
              json: async () => ({{files: DRIVE.folder
                ? [{{id: DRIVE.folder, name: "ScrapeX backups"}}] : []}}) }};
  }}
  if (String(url).includes("oauth2/v3/userinfo")) {{
    if (GOOGLE_ACCOUNT_MODE === "offline") throw new Error("network offline");
    if (GOOGLE_ACCOUNT_MODE === "nonresponsive") {{
      await waitWithSignal(60000, options.signal);
    }}
    if (!SIGNED_IN) return {{ ok: false, status: 401, json: async () => ({{}}) }};
    return {{ ok: true, status: 200, json: async () => SIGNED_IN }};
  }}
  if (String(url).includes("raw.githubusercontent.com")) {{
    // A STATIC FILE, so its absence is a 404 and that is not an error: the
    // manifest is not written until the first release writes it. Answering an
    // empty 200 here instead would test the panel against a state the endpoint
    // cannot produce.
    if (!ENGINE_MANIFEST) {{
      return {{ ok: false, status: 404, json: async () => null }};
    }}
    return {{ ok: true, status: 200, json: async () => ENGINE_MANIFEST }};
  }}
  if (!ENGINE_UP) throw new Error("engine down");
  if (SLOW || BLACKHOLE_ROUTES.some(route => path.startsWith(route))) {{
    await waitWithSignal(60000, options.signal);
  }}
  const delayed = Object.entries(ROUTE_DELAYS).find(([route]) => path.startsWith(route));
  if (delayed) await waitWithSignal(Number(delayed[1]), options.signal);
  if (FAIL.some(f => path.startsWith(f))) {{
    return {{ ok: false, status: 500, statusText: "engine error",
              json: async () => ({{detail: "the engine could not do that"}}) }};
  }}
  // THE BUNDLE, BEFORE THE FLAT TABLE. These three cannot be rows in `ROUTES`:
  // that table answers `{{ok, status, json}}` and nothing else, and an archive
  // needs a byte range, a `Content-Range`, an `ETag` and a blob. The panel reads
  // the archive's LENGTH off `Content-Range` rather than off the manifest on
  // purpose -- they are two facts and comparing them is what catches a truncated
  // upload -- so a fake that skipped the header would test the wrong thing.
  if (BUNDLE && path.startsWith("/api/bundle")) {{
    const bytes = Number(BUNDLE.bytes || 0);
    const filler = (n) => new Blob([new Uint8Array(Math.max(0, n))]);
    if (path === "/api/bundle" && method === "POST") {{
      return {{ ok: true, status: 200, headers: {{get: () => null}},
                json: async () => BUNDLE }};
    }}
    if (path.startsWith("/api/bundle/panel-pack")) {{
      const size = Number((BUNDLE.panel_pack || {{}}).bytes || 0);
      return {{ ok: true, status: 200, headers: {{get: () => null}},
                blob: async () => filler(size), json: async () => ({{}}) }};
    }}
    if (path.startsWith("/api/bundle/archive")) {{
      // RECORDED, because "was the archive read as a range" is the question the
      // 2026-09-03 failure turned on and a test cannot see it any other way:
      // a whole-body read and a ranged one both end with bytes in Drive.
      window.__sx_archive_reads = (window.__sx_archive_reads || []).concat(
        [(options.headers && (options.headers.Range || options.headers.range)) || ""]);
      const asked = /bytes=(\\d+)-(\\d+)/.exec(
        (options.headers && (options.headers.Range || options.headers.range)) || "");
      if (!asked) {{
        return {{ ok: true, status: 200,
                  headers: {{get: (k) => (String(k).toLowerCase() === "etag"
                    ? BUNDLE_ETAG : null)}},
                  blob: async () => filler(bytes), json: async () => ({{}}) }};
      }}
      const start = Number(asked[1]);
      const end = Math.min(Number(asked[2]) + 1, bytes);
      return {{ ok: true, status: 206,
                headers: {{get: (k) => {{
                  const name = String(k).toLowerCase();
                  if (name === "content-range") {{
                    return `bytes ${{start}}-${{end - 1}}/${{bytes}}`;
                  }}
                  if (name === "etag") return BUNDLE_ETAG;
                  return null;
                }}}},
                blob: async () => filler(end - start), json: async () => ({{}}) }};
    }}
  }}

  // THE COPY CHECK, BEFORE THE FLAT TABLE. It cannot be a row in `ROUTES`:
  // that table answers a fixed payload, and this verdict has to depend on the
  // REQUEST -- it echoes the path it was given. A fixed answer would make the
  // panel's echo check pass by accident on every path it ever sent.
  if (path === "/api/storage/integrity" && method === "POST") {{
    let asked = null;
    try {{ asked = JSON.parse((options && options.body) || "null"); }}
    catch (_) {{}}
    const wanted = asked && asked.backup_path;
    if (wanted) {{
      const verdict = Object.assign(
        {{status: "healthy", ok: true, integrity_checked: true,
         problems: [], foreign_key_problems: 0,
         at: "2026-09-09T10:00:00Z", detail: "No problems found.",
         // THE TWO SIDES DIFFER, and that is the whole point of the stub.
         // Both were 12, so the one assertion on the rendered verdict could
         // not tell `rows` from `live_rows`: swapping them in `rowVerdict`
         // was a surviving mutation, and the comparison the counts exist for
         // was never actually read.
         rows: {{generic_page_snapshot: 12}},
         live_rows: {{generic_page_snapshot: 340}}}},
        COPY_CHECK || {{}});
      // The echo, or the older engine that never learnt the field.
      verdict.checked = COPY_CHECK_ECHOES
        ? wanted : "C:\\Users\\Owner\\.scrapex\\harvest.db";
      return {{ok: true, status: 200, json: async () => verdict}};
    }}
  }}

  // The log endpoint lives under /api/jobs too, so it must be answered BEFORE
  // the generic /api/jobs list route swallows it.
  if (/^\\/api\\/jobs\\/[^/]+\\/logs/.test(path)) {{
    return {{ ok: true, status: 200, json: async () => LOG_PAYLOAD }};
  }}
  const table = method === "GET" ? ROUTES
                                 : {{...ROUTES, ...WRITE_ROUTES}};
  // THE MOST SPECIFIC ROUTE WINS, AND INSERTION ORDER IS NOT SPECIFICITY. `find` took
  // the first key that was a prefix, so `POST /api/storage/integrity` was answered with
  // `/api/storage`'s payload -- the storage blob, complete with a `status` field, so the
  // caller read a plausible verdict for a route the stub never declared. Any nested pair
  // of paths has the same hole.
  const key = Object.keys(table)
    .sort((a, b) => b.length - a.length)
    .find(k => path.startsWith(k));
  if (!key) return {{ ok: false, status: 404, statusText: "not found",
                      json: async () => ({{detail: "not found"}}) }};
  return {{ ok: true, status: 200, json: async () => table[key] }};
}};
"""


_ICON_URL = re.compile(r'url\(["\']?(?:[^"\')]*/)?icons/([^"\')]+)["\']?\)')


def _embed_icons(css: str) -> str:
    """Replace icon references with data: URIs.

    Chromium will not load a CSS mask image over file://, so every masked icon
    rendered as an empty box and the screenshots understated the UI. Embedding
    the bytes removes the origin question entirely.
    """
    def sub(match: re.Match) -> str:
        icon = EXT / "icons" / match.group(1)
        if not icon.exists():
            return match.group(0)
        mime = mimetypes.guess_type(str(icon))[0] or "image/png"
        data = base64.b64encode(icon.read_bytes()).decode("ascii")
        return f'url("data:{mime};base64,{data}")'

    return _ICON_URL.sub(sub, css)


def build_page(tmp: Path, stub_js: str, name: str = "panel.html") -> Path:
    """Inline the panel's own HTML/CSS/JS into one file so file:// can load it."""
    html = (EXT / "app.html").read_text(encoding="utf-8")
    body = html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    # Drop the module <script src>: file:// blocks module loads by CORS, and the
    # real app.js is inlined below anyway.
    body = re.sub(r'<script type="module".*?</script>', "", body, flags=re.S)
    style = _embed_icons((EXT / "app.css").read_text(encoding="utf-8"))
    tokens_css = (EXT / "tokens.css").read_text(encoding="utf-8")
    components_css = _embed_icons((EXT / "components.css").read_text(encoding="utf-8"))
    # NO ICON WORK HERE, ON PURPOSE. app.html carries its sprite inline and every
    # icon in the panel, markup and app.js alike, points at those symbols
    # (tools/sync_design_assets.py). This harness used to inline its own copy
    # and rewrite every <use> onto it, which is why every harness test stayed
    # green while the real panel stuck blank on the external sprite (issue
    # 1110): the page under test could not have the defect. The page now
    # arrives with its icons as the extension ships them.
    #
    # An <img src> is a real subresource, and this page lives in a temporary
    # directory with no icons/ beside it — so Google's mark rendered as a BROKEN
    # IMAGE in every screenshot while every assertion about it passed, because
    # they read the markup and the file rather than the page. Inlined for that
    # reason.
    for asset in ("google-g.png",
                  "google-signin/light-rectangular@4x.png",
                  "google-signin/dark-rectangular@4x.png"):
        path = EXT / "icons" / asset
        # RAISES, and does not `continue`. Skipping a missing asset let every
        # assertion about the Google button pass while the panel drew a BROKEN
        # IMAGE -- which is the exact failure this inlining was written to
        # prevent, and it is how the broken mark shipped once already. A test
        # run that cannot find the asset has not tested the button.
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing, so the panel would render a broken image and "
                "every assertion about it would still pass. Restore the asset or "
                "remove it from this list -- do not let the harness skip it.")
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        body = body.replace(f'src="icons/{asset}"',
                            f'src="data:image/png;base64,{data}"')
    app_js = (EXT / "app.js").read_text(encoding="utf-8")
    startup_trace_js = (EXT / "startup-trace.js").read_text(encoding="utf-8")
    startup_bootstrap_js = (EXT / "startup-bootstrap.js").read_text(encoding="utf-8")
    startup_js = (EXT / "startup.js").read_text(encoding="utf-8")
    appearance_js = (EXT / "appearance.js").read_text(encoding="utf-8")
    # The shared split-button behaviour is loaded in the production head before
    # app.js so its global exists when the Activity panel wires the log control.
    split_button_js = (EXT / "split-button.js").read_text(encoding="utf-8")
    timezone_js = (EXT / "timezone.js").read_text(encoding="utf-8")
    engine_js = (EXT / "engine.js").read_text(encoding="utf-8")
    transport_js = (EXT / "transport.js").read_text(encoding="utf-8")
    version_js = (EXT / "version.js").read_text(encoding="utf-8")
    releases_js = (EXT / "releases.js").read_text(encoding="utf-8")
    identity_js = (EXT / "identity.js").read_text(encoding="utf-8")
    # THE LIST BELOW IS HAND-MAINTAINED, and a module missing from it does not
    # fail loudly: app.js's imports are stripped, so a call into an un-inlined
    # module is a ReferenceError at the call site. accounts.js is wrapped in
    # try/catch by design — the panel must survive a storage fault — so leaving
    # it out made the directory silently never written while every visible part
    # of the panel kept working.
    accounts_js = (EXT / "accounts.js").read_text(encoding="utf-8")
    # backend.js is where the engine's address and the request policy went when
    # the Data page needed them too (plan B2). Inlined AFTER engine.js, whose
    # getBackend it calls, and before app.js, which calls all of it.
    backend_js = (EXT / "backend.js").read_text(encoding="utf-8")

    # Flatten the ES-module graph. engine.js imports the protocol version from
    # transport.js, while app.js imports both modules; leaving even that
    # transitive import in this classic inline script stops the whole panel
    # before DOMContentLoaded. Keep the harness on the extension's real module
    # graph instead of re-declaring any of its functions in a test-only stub.
    app_js = re.sub(r"^import[\s\S]*?;\s*$", "", app_js, flags=re.M)
    # ONE FLATTENING RULE, APPLIED TO EVERY MODULE, rather than three lines per
    # module repeated down the file. The comment above says this list is
    # hand-maintained; it still is, but adding a module is now one name instead
    # of three near-identical substitutions to copy correctly.
    #
    # drive.js, bundleview.js and sheets.js arrived on 2026-08-12 when the Drive
    # work landed on main, and the test below caught their absence during the
    # rebase — which is what it was written for.
    def flatten(source: str) -> str:
        source = re.sub(r"^import[\s\S]*?;\s*$", "", source, flags=re.M)
        return re.sub(r"\bexport\s+", "", source)

    startup_js = flatten(startup_js)
    engine_js = flatten(engine_js)
    transport_js = flatten(transport_js)
    version_js = flatten(version_js)
    releases_js = flatten(releases_js)
    identity_js = flatten(identity_js)
    accounts_js = flatten(accounts_js)
    backend_js = flatten(backend_js)
    drive_js = flatten((EXT / "drive.js").read_text(encoding="utf-8"))
    sheets_js = flatten((EXT / "sheets.js").read_text(encoding="utf-8"))
    bundleview_js = flatten((EXT / "bundleview.js").read_text(encoding="utf-8"))
    # jobsview.js arrived on 2026-09-09 with the Jobs page, and its absence cost a
    # debugging round exactly as the comment above predicts: `rowsFrom is not defined`,
    # thrown inside `showView`, so the page kept its empty placeholder and every guard
    # for it failed with "0 of 4 jobs drawn" instead of with the real reason.
    jobsview_js = flatten((EXT / "jobsview.js").read_text(encoding="utf-8"))

    tmp.mkdir(parents=True, exist_ok=True)
    page = tmp / name
    page.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>ScrapeX panel</title>"
        # The trace comes first, exactly as app.html loads it: the bootstrap
        # records nothing without it.
        f"<script>{startup_trace_js}</script>\n"
        f"<script>{startup_bootstrap_js}</script>\n"
        f"<script>{appearance_js}</script>\n"
        # Match app.html's startup-critical ordering: local appearance runs in
        # <head> before styles and before any body content can be painted.
        f"<style>{tokens_css}</style><style>{components_css}</style>"
        f"<style>{style}</style>\n"
        # Every page this harness builds is a file:// document, and Chromium
        # gives them all ONE localStorage. A zone chosen by one test would
        # therefore be the starting state of the next, which made a real test
        # pass for the wrong reason (it read the previous test's Riyadh as its
        # own "before"). Cleared BEFORE timezone.js reads it, so each page opens
        # in the state a fresh install is in.
        "<script>try{window.localStorage.removeItem('scrapex-timezone-v1')}"
        "catch(e){}</script>\n"
        # Same order as app.html's <head>, and it matters: timezone.js registers
        # its DOMContentLoaded binder before app.js registers init(), so the
        # select is populated and the module's own change listener is attached
        # before the panel adds its own.
        f"<script>{timezone_js}</script>\n"
        f"<script>{split_button_js}</script>\n"
        f"</head><body>{body}\n"
        f"<script>{stub_js}</script>\n"
        # No manual DOMContentLoaded dispatch: this inline script is parsed
        # BEFORE the browser fires the real event, so dispatching one as well
        # would run init() twice and double-bind every listener — a click would
        # then toggle twice and appear to do nothing at all.
        f"<script>{startup_js}\n{transport_js}\n{version_js}\n{releases_js}\n{identity_js}\n"
        f"{accounts_js}\n{drive_js}\n{sheets_js}\n{bundleview_js}\n"
        f"{engine_js}\n{backend_js}\n{jobsview_js}\n{app_js}</script></body></html>",
        encoding="utf-8")
    return page


def wait_until_settled(page, timeout: int = 5_000) -> None:
    """Block until the panel has finished booting, instead of sleeping past it.

    WHAT IT REPLACED, AND BY HOW MUCH. Every fixture that opened this page used
    to follow `page.goto()` with `wait_for_timeout(500)`. Measured 2026-09-11 on
    `e868486`, twelve samples of the real stub page: after `goto()` RETURNS the
    panel settles in a median of **16.6ms** (min 15.6, max 112.3). `goto()`
    already waits for `load`, and the marks put `load` at 53ms and
    `fully-settled` at 60ms from navigation start, so the sleep began after the
    work was essentially done and overshot by ~483ms every time. Across the three
    fixtures that opened the panel that was 130.5s of a 224.8s sleep bill (#648).

    EITHER MARK ENDS THE WAIT, and waiting for `fully-settled` alone would hang
    on a real path. `extension/app.js` fires it from `Promise.allSettled`, so a
    down engine or a refused account still settles — but `init()` throwing fires
    `startup-failed` instead, and a cancelled paint opportunity returns early
    firing NEITHER. The first two are states a test may legitimately stub; the
    third is why this keeps a bounded timeout and raises rather than waiting on.

    A TIMEOUT HERE IS A REAL FAILURE, not a slow machine. The margin is 5s
    against a measured 112ms worst case — a factor of 44 — so a test that trips
    it has a panel that never finished booting, which is the thing worth knowing.

    `tests/test_panel_startup.py` keeps its own `_wait_for_mark`: it asserts on
    individual marks by name and on their number, which is a different question
    from "is the panel ready", and merging them would make one helper serve two.
    """
    _wait_for_either(page, "fully-settled", timeout)


def wait_until_interactive(page, timeout: int = 5_000) -> None:
    """Block until the shell is usable, WITHOUT waiting for the slow work behind it.

    A test that stubs a delayed answer -- `signin_delay_ms=1200` -- is asking to
    see the panel while that answer is still in flight, and `wait_until_settled`
    is the wrong wait for it: `fully-settled` fires from
    `Promise.allSettled([accountPromise, enginePromise])`, so it lands AFTER the
    delay it was stubbed to outlast, and the transient state is gone by the time
    the fixture returns. Measured: two tests went red that way, both of them
    tests OF the transient -- `test_the_profile_card_shows_checking_while_chrome_answers`
    and `test_the_initial_state_is_checking_then_resolves_to_signed_out`.

    `account-check-start` IS THE MARK, AND `shell-interactive` WAS THE MISTAKE.
    The first version of this helper waited on `shell-interactive`, which
    `wireStartupShell()` fires BEFORE `init()` awaits its paint opportunity --
    while `loadAccount()` marks `account-check-start` and only then calls
    `setChecking(true)`. Measured: `shell-interactive` at 77-83ms against
    `account-check-start` at 79-197ms, so the barrier could return before the
    panel had entered the state under test. Both assertions in those two tests are
    the SHIPPED MARKUP DEFAULTS, so they stayed green while testing nothing.

    Named by mutation -- invert `setChecking(true)` to `setChecking(false)`, the
    exact state those tests are named for:

        the 500ms sleep this replaced   mutant passed  0/10
        the shell-interactive barrier   mutant passed  3/10
        this one                        mutant passed  0/10

    So the barrier is stronger than the sleep it replaces, not merely faster.

    `startup-failed` ends this wait too -- see `_wait_for_either`, which is where
    both helpers decide what a failed start means.
    """
    _wait_for_either(page, "account-check-start", timeout)


def wait_until_idle_work_done(page, timeout: int = 5_000) -> None:
    """Block until the deferred phase has finished, not merely until startup has.

    `fully-settled` FIRES BEFORE THE PANEL HAS FINISHED. It comes from
    `Promise.allSettled([accountPromise, enginePromise])`, and
    `scheduleNonCriticalStartup` then runs `ScrapeXAppearance.connect`,
    `ScrapeXTime.connect` and `reattachToRunningJob` in an `afterIdle` callback
    afterwards. A test that reads any of those needs this wait, not the settled one.

    MEASURED, AND THE REASON THIS EXISTS: replacing the fixture's flat
    `wait_for_timeout(500)` with `wait_until_settled` turned
    `test_a_zone_saved_on_the_other_surface_arrives_here` and
    `test_an_invalid_zone_falls_back_down_the_chain_and_says_which_step` red in CI,
    both reading `window.ScrapeXTime.get().zone` as an empty string. The sleep had
    been covering the gap by accident and not always -- `startup.js`'s `afterIdle`
    falls back at 750ms, which is longer than the 500 it was racing.
    """
    _wait_for_either(page, "idle-work-done", timeout)


def _wait_for_either(page, mark: str, timeout: int) -> None:
    """Wait for `mark` or for startup to fail — and RAISE if it failed.

    RETURNING ON `startup-failed` WAS A SILENT PASS ACROSS EVERY CALL SITE, and a
    merge gate demonstrated it: rename `id="signin"` in the generated page and
    `wireStartupShell()` dies on its first statement, `init()` rejects,
    `startPanel()` catches it (extension/app.js), and the mark is the only trace.
    Measured on that page — the wait RETURNED after 31.0ms, `page.js_errors` was
    empty because the rejection was caught, `window.__calls` was empty because the
    panel never made a request, and the test then failed on whatever selector it
    touched next with no mention of the panel having never started.

    The mark carries the reason, so the reason is what gets raised: `markStartup`
    records `{message: ...}` as the mark's `detail`, readable from Playwright.

    `AssertionError`, not `pytest.fail`: `Failed` derives from BaseException, so a
    caller writing `pytest.raises(Exception)` -- including this module's own tests
    -- would not catch it, and neither would any `except Exception` a future
    fixture wraps this in. Measured: all three new tests failed that way first.
    """
    page.wait_for_function(
        "name => performance.getEntriesByName('scrapex:' + name).length"
        " + performance.getEntriesByName('scrapex:startup-failed').length > 0",
        arg=mark,
        polling=10,
        timeout=timeout,
    )
    # THE MARK'S PRESENCE DECIDES, NOT ITS MESSAGE. A first draft keyed on
    # `detail.message` and passed silently on a mark carrying no detail -- caught
    # because this file's own tests fire a bare `performance.mark(...)` and went
    # green against a helper that was supposed to refuse them.
    failed = page.evaluate(
        "() => { const m = performance.getEntriesByName('scrapex:startup-failed');"
        "        return m.length ? [m[0].detail?.message ?? 'unknown'] : null; }")
    if failed is not None:
        raise AssertionError(
            "the panel failed to start, so this page can prove nothing about "
            f"the product: {failed[0]}")
