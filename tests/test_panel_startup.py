"""Side-panel startup stays usable while independent work resolves behind it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")
import panel_harness as harness  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.extension

PROFILE_TAB = 'nav.side-rail button[data-view="profile"]'
RUN_TAB = 'nav.side-rail button[data-view="run"]'
SETTINGS_TAB = 'nav.side-rail button[data-view="settings"]'
DESTINATION_ROUTES = (
    "/api/sources", "/api/outputs", "/api/jobs", "/api/resolve",
    "/api/records", "/api/changes", "/api/schedules", "/api/storage",
    "/api/settings", "/api/fields", "/api/rates",
)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_starting_panel(browser, tmp_path):
    pages = []

    def opener(*, width=360, init_script=None, **stub_kwargs):
        page_file = harness.build_page(
            tmp_path,
            harness.stub(**stub_kwargs),
            name=f"startup-{len(pages)}.html",
        )
        page = browser.new_page(viewport={"width": width, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if init_script:
            page.add_init_script(init_script)
        page.goto(page_file.as_uri(), wait_until="domcontentloaded")
        page.js_errors = errors
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            if not page.is_closed():
                page.close()


def _wait_for_mark(page, name: str, timeout=5_000):
    page.wait_for_function(
        "name => performance.getEntriesByName('scrapex:' + name).length === 1",
        arg=name,
        polling=25,
        timeout=timeout,
    )


def _marks(page):
    return page.evaluate("""() => Object.fromEntries(
      performance.getEntriesByType("mark")
        .filter(mark => mark.name.startsWith("scrapex:"))
        .map(mark => [mark.name.slice(8), mark.startTime]))""")


def _calls(page):
    return page.evaluate("() => window.__calls.slice()")


def _mark_detail(page, name: str):
    return page.evaluate(
        "name => performance.getEntriesByName('scrapex:' + name)[0]?.detail",
        name,
    )


def test_profile_shell_is_visible_without_javascript_revealing_it():
    html = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")
    profile_tag = html.rsplit('<section id="view-profile"', 1)[1].split(">", 1)[0]

    assert "hidden" not in profile_tag
    assert '<nav class="side-rail"' in html


def test_only_fcp_claims_that_the_shell_was_visually_painted():
    app = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    bootstrap = (ROOT / "extension" / "startup-bootstrap.js").read_text(
        encoding="utf-8")

    assert "shell-visible" not in app
    assert 'markStartup("shell-post-opportunity"' in app
    assert 'entry.name === "first-contentful-paint"' in bootstrap
    # The paint is recorded into the persistent trace rather than posted to a
    # service worker that may not be awake. Its ABSENCE from a stored trace is
    # the finding: the document ran and nothing was ever painted.
    assert 'trace.mark("first-contentful-paint"' in bootstrap
    assert "chrome.runtime.sendMessage" not in bootstrap


def test_the_shell_is_interactive_before_account_or_engine_settles(open_starting_panel):
    page = open_starting_panel(
        signin_never_returns=True,
        blackhole_routes=("/api/health",),
    )

    assert page.locator("html").get_attribute("data-shell-interactive") == "true"
    assert page.locator("#view-profile").is_visible()
    assert page.locator("nav.side-rail").is_visible()
    assert page.locator("#welcome-checking").is_visible()

    # This click occurs while both checks remain intentionally nonresponsive.
    page.click("#tab-appearance")
    assert page.locator("#view-appearance").is_visible()
    page.click(PROFILE_TAB)
    assert page.locator("#welcome-checking").is_visible()

    _wait_for_mark(page, "account-check-start")
    _wait_for_mark(page, "engine-check-start")
    marks = _marks(page)
    assert marks["shell-interactive"] - marks["document-first-script"] <= 250
    assert marks["shell-interactive"] <= marks["account-check-start"]
    assert marks["shell-interactive"] <= marks["engine-check-start"]
    assert "account-check-finish" not in marks
    assert "engine-check-finish" not in marks
    assert not page.js_errors


def test_account_and_engine_checks_start_independently(open_starting_panel):
    page = open_starting_panel(
        signed_in={"name": "Owner", "email": "owner@example.com"},
        signin_delay_ms=1_200,
        route_delays={"/api/health": 900},
    )
    _wait_for_mark(page, "fully-settled")
    marks = _marks(page)

    assert marks["engine-check-start"] < marks["account-check-finish"]
    assert marks["account-check-start"] < marks["engine-check-finish"]
    assert abs(marks["account-check-start"] - marks["engine-check-start"]) < 100
    assert page.locator("#welcome-signed-in").is_visible()
    assert page.locator("#estat-text").inner_text().startswith("Ready")
    assert not page.js_errors


def test_initially_unfocused_panel_finishes_without_a_frame_or_interaction(
        open_starting_panel):
    withhold_frames = """
      (() => {
        Object.defineProperty(document, "visibilityState", {
          configurable: true, get: () => "hidden",
        });
        Object.defineProperty(document, "hasFocus", {
          configurable: true, value: () => false,
        });
        window.__blockedAnimationFrames = [];
        window.__cancelledAnimationFrames = [];
        let frameId = 0;
        window.requestAnimationFrame = (callback) => {
          const id = ++frameId;
          window.__blockedAnimationFrames.push({id, callback});
          return id;
        };
        // Keep the callback so the test can deliver the cancelled frame late
        // and prove that the settled startup path does not run twice.
        window.cancelAnimationFrame = (id) => {
          window.__cancelledAnimationFrames.push(id);
        };
      })();
    """
    page = open_starting_panel(
        init_script=withhold_frames,
        signin_never_returns=True,
        blackhole_routes=("/api/health",),
    )

    # No click, hover, focus, blur, or synthetic visibility transition occurs.
    assert page.locator("#view-profile").is_visible()
    assert page.locator("nav.side-rail").is_visible()
    assert page.locator("#welcome-checking").is_visible()
    assert page.locator(PROFILE_TAB).is_enabled()
    _wait_for_mark(page, "shell-post-opportunity", timeout=1_000)
    _wait_for_mark(page, "account-check-start", timeout=1_000)
    _wait_for_mark(page, "engine-check-start", timeout=1_000)

    marks = _marks(page)
    assert marks["shell-interactive"] <= marks["paint-opportunity-resolved"]
    assert marks["paint-opportunity-resolved"] <= marks["shell-post-opportunity"]
    assert marks["shell-post-opportunity"] <= marks["account-check-start"]
    assert marks["shell-post-opportunity"] <= marks["engine-check-start"]
    assert marks["shell-post-opportunity"] - marks["document-first-script"] < 1_000
    started = _mark_detail(page, "document-first-script")
    assert started["visibilityState"] == "hidden"
    assert started["hasFocus"] is False
    assert started["readyState"] == "loading"
    # "hidden", NOT "timer". This asserted "timer" when it was written, and that
    # was the defect rather than the contract: a hidden document was requesting
    # an animation frame it can never be given and then falling through to a
    # fallback timer that is ITSELF throttled while hidden — measured at 785 ms
    # in the owner's trace, where the whole shell had been ready since 168 ms.
    #
    # `afterNextPaint` now recognises the state and resolves at once, which moved
    # the mark to 177.6 ms. "hidden" is the source that says startup understood
    # where it was; "timer" would mean it had gone back to waiting for nothing.
    assert _mark_detail(page, "paint-opportunity-resolved") == {
        "source": "hidden", "visibilityState": "hidden",
    }
    assert _mark_detail(page, "shell-post-opportunity") == {
        "source": "hidden", "visibilityState": "hidden",
    }

    _wait_for_mark(page, "fully-settled", timeout=4_000)
    assert page.locator("#welcome-signed-out").is_visible()
    assert page.locator("#estat-text").inner_text() == "Check timed out"
    assert _calls(page).count("/api/health") == 1

    page.evaluate("""() => {
      const frames = window.__blockedAnimationFrames.splice(0);
      frames.forEach(({callback}) => callback(performance.now()));
    }""")
    page.wait_for_timeout(50)
    counts = page.evaluate("""() => Object.fromEntries([
      "paint-opportunity-resolved", "shell-post-opportunity", "account-check-start",
      "account-check-finish", "engine-check-start", "engine-check-finish",
      "fully-settled",
    ].map(name => [name,
      performance.getEntriesByName("scrapex:" + name).length]))""")
    assert set(counts.values()) == {1}
    assert _calls(page).count("/api/health") == 1
    assert not page.js_errors


@pytest.mark.parametrize(
    ("worker_alive", "expected"),
    [(True, "Ready"), (False, "Stopped")],
)
def test_profile_startup_handles_healthy_and_stopped_engines_without_run_data(
        open_starting_panel, worker_alive, expected):
    page = open_starting_panel(worker_alive=worker_alive)
    _wait_for_mark(page, "fully-settled")

    assert page.locator("#estat-text").inner_text().startswith(expected)

    # THE RULE, NARROWED BY A DECISION RATHER THAN BY CONVENIENCE (2026-08-12).
    #
    # This forbade EVERY destination route on startup. The owner ruled that a
    # crawl already running must be visible the moment the panel opens, on
    # whatever screen it opens — issue 161, where a reopened panel showed an
    # idle screen over a live run and the natural response was to start it
    # again, putting two crawls on one source.
    #
    # Reattaching costs exactly one loopback request, and it happens AFTER the
    # shell has settled. What the rule was protecting — a shell that paints
    # before remote work — is untouched, and is still asserted: /api/health is
    # called once, and the heavy reads are still forbidden.
    heavy = tuple(route for route in DESTINATION_ROUTES if route != "/api/jobs")
    assert not any(call.startswith(heavy) for call in _calls(page)), (
        "startup read destination data it does not need to paint the shell")
    assert _calls(page).count("/api/health") == 1
    assert not page.js_errors


def test_a_nonresponsive_health_check_times_out_without_blocking_profile(
        open_starting_panel):
    page = open_starting_panel(blackhole_routes=("/api/health",))

    assert page.locator("#view-profile").is_visible()
    page.click("#tab-engines")
    assert page.locator("#view-engines").is_visible()
    # The Engine page's own wording, and its own live region. Both come from the
    # Engine destination this branch was rebased onto; the card is rendered from
    # `state` by one status map rather than written to by hand here.
    assert page.locator("#engine-status").inner_text() == "Checking engine…"
    assert page.locator("#engine-status-region").get_attribute("aria-busy") == "true"
    page.wait_for_function(
        "() => document.querySelector('#estat-text').textContent === 'Check timed out'",
        timeout=4_000,
    )
    _wait_for_mark(page, "fully-settled")
    assert "deadline" in page.locator("#engine-note").inner_text().lower()
    # A deadline that expired is its OWN answer, and not "Not detected" — which
    # is the sentence for a machine with no engine on it, and the wrong thing to
    # tell someone whose engine is merely slow.
    assert page.locator("#engine-status").inner_text() == "Check timed out"
    assert "deadline" in page.locator("#engine-status-detail").inner_text().lower()
    # The retry the old wording promised in the status text itself. It is a
    # labelled action beside the row now, so the assertion moved to the control.
    assert page.locator("#engine-recheck").is_enabled()
    assert page.locator("#engine-status-region").get_attribute("aria-busy") == "false"
    assert not page.js_errors


def test_a_delayed_version_request_gets_its_own_recoverable_state(open_starting_panel):
    page = open_starting_panel(route_delays={"/api/version": 4_000})
    _wait_for_mark(page, "fully-settled", timeout=4_000)

    notice = page.locator("#version-notice")
    assert notice.is_visible()
    assert "timed out" in notice.inner_text().lower()
    assert page.locator("#estat-text").inner_text().startswith("Ready")
    assert not page.js_errors


def test_an_absent_token_callback_cannot_hold_engine_or_profile(open_starting_panel):
    page = open_starting_panel(signin_never_returns=True)

    page.wait_for_function(
        "() => document.querySelector('#estat-text').textContent.startsWith('Ready')",
        timeout=1_500,
    )
    assert page.locator("#welcome-checking").is_visible()
    page.wait_for_function(
        "() => !document.querySelector('#signin-problem').classList.contains('hidden')",
        timeout=3_500,
    )
    assert "did not finish" in page.locator("#signin-problem").inner_text()
    assert page.locator("#view-profile").is_visible()
    assert not page.js_errors


def test_a_late_token_callback_cannot_overwrite_the_timeout(open_starting_panel):
    page = open_starting_panel(
        signed_in={"name": "Too late", "email": "late@example.com"},
        signin_delay_ms=3_000,
    )
    page.wait_for_function(
        "() => !document.querySelector('#signin-problem').classList.contains('hidden')",
        timeout=3_500,
    )
    assert "did not finish" in page.locator("#signin-problem").inner_text()

    # Chrome's callback arrives after the 2.5s silent deadline. It must be
    # ignored instead of replacing the newer timeout state with a stale token.
    page.wait_for_timeout(750)
    assert page.locator("#welcome-signed-out").is_visible()
    assert not page.locator("#welcome-signed-in").is_visible()
    assert "did not finish" in page.locator("#signin-problem").inner_text()
    assert not page.js_errors


def test_google_offline_keeps_the_signed_in_state_and_offers_retry(open_starting_panel):
    page = open_starting_panel(
        signed_in={"name": "Owner", "email": "owner@example.com"},
        google_account_mode="offline",
    )
    _wait_for_mark(page, "fully-settled")

    assert page.locator("#welcome-signed-in").is_visible()
    assert "Could not reach Google" in page.locator("#account-detail-status").inner_text()
    assert page.locator("#retry-account").is_visible()
    assert page.locator("#estat-text").inner_text().startswith("Ready")
    assert not page.js_errors


@pytest.mark.parametrize("native_mode", ["absent", "nonresponsive"])
def test_native_status_is_deferred_until_its_settings_section_is_visible(
        open_starting_panel, native_mode):
    page = open_starting_panel(native_mode=native_mode)
    _wait_for_mark(page, "fully-settled")
    assert page.evaluate("() => window.__nativeCalls.length") == 0

    page.click(SETTINGS_TAB)
    assert page.locator("#ui_time_zone").get_attribute("data-time-zone-select") == ""
    page.click('[data-sect="s-engine"]')
    page.wait_for_function("() => window.__nativeCalls.length === 1")
    assert page.evaluate("() => window.__nativeCalls") == ["AUTOSTART_STATUS"]
    assert not page.js_errors


def test_generic_backend_blackhole_ends_at_the_destination_deadline(open_starting_panel):
    page = open_starting_panel(blackhole_routes=("/api/sources",))
    _wait_for_mark(page, "fully-settled")
    page.click(RUN_TAB)
    _wait_for_mark(page, "first-destination-data-request")
    page.wait_for_function(
        "() => document.querySelector('#sites').textContent.includes(\"Couldn't reach\")",
        timeout=6_500,
    )

    assert page.locator("nav.side-rail").is_visible()
    assert _calls(page).count("/api/sources") == 1
    assert not page.js_errors


def test_hidden_panel_pauses_refreshes_and_visible_panel_resumes_one_of_each(
        open_starting_panel):
    track_intervals = """
      (() => {
        window.__startupIntervals = [];
        const realSetInterval = window.setInterval.bind(window);
        window.setInterval = (callback, delay, ...args) => {
          window.__startupIntervals.push(delay);
          return realSetInterval(callback, delay, ...args);
        };
      })();
    """
    job = {
        "job_ref": "job_live", "source_keys": ["SHORT"], "status": "running",
        "stage": "fetching", "current_source_key": "SHORT",
        "progress": {"done": 0, "total": 1},
        "fetch": {"requests": 0, "expected": None, "basis": None,
                  "as_of": None, "unknown_sources": [], "sources": {}},
        "counters": {"observations": 0, "duplicates": 0, "products": 0,
                     "requests": 0, "errors": 0},
        "queued_behind": None,
    }
    page = open_starting_panel(init_script=track_intervals, jobs=[job])
    _wait_for_mark(page, "fully-settled")
    page.click(RUN_TAB)
    page.wait_for_function(
        "() => window.__calls.some(path => path.startsWith('/api/jobs?active_only'))",
    )
    page.wait_for_function(
        "() => window.__calls.includes('/api/appearance') "
        "&& window.__calls.includes('/api/timezone')",
    )

    page.evaluate("""() => {
      window.__testVisibility = "hidden";
      Object.defineProperty(document, "visibilityState", {
        configurable: true, get: () => window.__testVisibility,
      });
      window.__calls.length = 0;
      document.dispatchEvent(new Event("visibilitychange"));
    }""")
    page.wait_for_timeout(2_200)
    assert not [call for call in _calls(page) if call.startswith(
        ("/api/appearance", "/api/timezone", "/api/jobs"))]

    page.evaluate("""() => {
      window.__testVisibility = "visible";
      document.dispatchEvent(new Event("visibilitychange"));
    }""")
    page.wait_for_timeout(200)
    calls = _calls(page)
    assert calls.count("/api/appearance") == 1
    assert calls.count("/api/timezone") == 1
    assert len([call for call in calls if call.startswith("/api/jobs?active_only")]) == 1
    assert page.evaluate("() => window.__startupIntervals.filter(n => n === 2000).length") == 1
    assert page.evaluate("() => window.__startupIntervals.filter(n => n === 5000).length") == 1
    assert not page.js_errors


@pytest.mark.parametrize("width", [320, 400])
def test_startup_shell_fits_supported_panel_widths(open_starting_panel, width):
    page = open_starting_panel(
        width=width,
        signin_never_returns=True,
        blackhole_routes=("/api/health",),
    )

    assert page.locator("#view-profile").is_visible()
    assert page.locator("nav.side-rail").is_visible()
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth",
    )
    assert overflow <= 1
    assert not page.js_errors


@pytest.mark.parametrize(
    ("palette", "painted"),
    [
        # STORED NAME -> THE NAME THAT REACHES THE FIRST FRAME. The two are not
        # the same thing any more and the difference is the point of this table.
        #
        # R-59 decision 3 made `whatsapp` and `github` compatibility aliases for
        # `brand` and `blue`, and R-73 built the registry that honours them. So a
        # preference SAVED before 2026-08-28 carries the old name, and what has
        # to survive is not the string -- it is the user's actual choice. This
        # table is the only place that is proven end to end, from a localStorage
        # value written by a previous build through to the attribute on the
        # painted frame.
        #
        # AND R-85 MADE ALL FOUR OLD NAMES POINT AT ONE. «احذف الثلاثة وابق
        # supabase وحده», 2026-08-31: `brand` and `blue` were deleted, so a stored
        # `whatsapp`, `github`, `brand` or `blue` now paints `supabase`. THIS IS THE
        # WHOLE MIGRATION AND THERE IS NO OTHER — no upgrade step, no rewrite of
        # stored records, nothing in the engine. It is the alias map plus
        # `resolvePalette`'s fallback, and these five rows are what proves it
        # rather than asserts it.
        #
        # A row that painted its own name would mean a deleted palette had come
        # back; a row that painted nothing would mean a stored record had become
        # unloadable. Both are what this table exists to refuse.
        pytest.param("whatsapp", "supabase", id="retired-whatsapp"),
        pytest.param("github", "supabase", id="retired-github"),
        pytest.param("brand", "supabase", id="retired-brand"),
        pytest.param("blue", "supabase", id="retired-blue"),
        pytest.param("supabase", "supabase", id="canonical-supabase"),
    ],
)
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_cached_theme_is_applied_before_the_first_frame(
        open_starting_panel, palette, painted, scheme):
    saved = json.dumps({
        "mode": "manual", "scheme": scheme, "palette": palette,
        "deviceColors": False, "updatedAt": 100,
    })
    init_script = f"""
      window.__appearanceProof = {{mutations: [], paints: []}};
      localStorage.setItem("scrapex-appearance-v2", JSON.stringify({{
        ...{saved}
      }}));
      new MutationObserver(records => {{
        const at = performance.now();
        records.forEach(record => window.__appearanceProof.mutations.push({{
          attribute: record.attributeName,
          oldValue: record.oldValue,
          value: record.target.getAttribute(record.attributeName),
          at,
        }}));
      }}).observe(document, {{
        subtree: true,
        attributes: true,
        attributeOldValue: true,
        attributeFilter: ["data-theme", "data-palette"],
      }});
      new PerformanceObserver(list => {{
        list.getEntries().forEach(entry => {{
          if (entry.name !== "first-contentful-paint") return;
          window.__appearanceProof.paints.push({{
            name: entry.name,
            startTime: entry.startTime,
            theme: document.documentElement.dataset.theme,
            palette: document.documentElement.dataset.palette,
          }});
        }});
      }}).observe({{type: "paint", buffered: true}});
    """
    for _ in range(10):
        page = open_starting_panel(init_script=init_script)
        page.wait_for_function(
            "() => window.__appearanceProof.paints.length === 1",
        )
        proof = page.evaluate("""() => ({
          current: {
            theme: document.documentElement.dataset.theme,
            palette: document.documentElement.dataset.palette,
          },
          ...window.__appearanceProof,
        })""")
        expected = {"theme": scheme, "palette": painted}
        fcp = proof["paints"][0]
        first_values = {
            name: next(change for change in proof["mutations"]
                       if change["attribute"] == name)
            for name in ("data-theme", "data-palette")
        }

        assert proof["current"] == expected
        assert {"theme": fcp["theme"], "palette": fcp["palette"]} == expected
        assert first_values["data-theme"]["value"] == scheme
        assert first_values["data-palette"]["value"] == painted
        assert first_values["data-theme"]["at"] <= fcp["startTime"]
        assert first_values["data-palette"]["at"] <= fcp["startTime"]
        assert not page.js_errors
        page.close()


def test_startup_instrumentation_spans_shell_checks_and_first_destination(
        open_starting_panel):
    page = open_starting_panel()
    _wait_for_mark(page, "fully-settled")
    before = _marks(page)
    required = {
        "document-first-script", "dom-content-loaded", "pageshow",
        "animation-frame-requested", "animation-frame-resolved",
        "paint-opportunity-resolved", "shell-post-opportunity", "shell-interactive",
        "account-check-start", "account-check-finish", "engine-check-start",
        "engine-check-finish", "fully-settled",
    }
    assert required <= before.keys()
    assert before["shell-interactive"] <= before["paint-opportunity-resolved"]
    assert before["paint-opportunity-resolved"] <= before["shell-post-opportunity"]
    assert before["shell-post-opportunity"] <= before["account-check-start"]
    assert before["shell-post-opportunity"] <= before["engine-check-start"]
    # THE PROPERTY, STATED DIRECTLY. This used to assert that no destination
    # request had happened by `fully-settled`, which was a proxy for "the shell
    # is interactive first" and stopped being true on 2026-08-12: the owner
    # ruled that a running crawl must be found the moment the panel opens
    # (issue 161), so one loopback read now lands shortly after settle.
    #
    # The ordering is what the rule was ever about, and asserting it is stronger
    # than asserting an absence at one instant — an absence that a slower
    # machine could satisfy for the wrong reason.
    _wait_for_mark(page, "first-destination-data-request")
    after = _marks(page)
    assert after["first-destination-data-request"] >= after["shell-interactive"], (
        "destination data was requested before the shell was interactive")
    assert after["first-destination-data-request"] >= after["paint-opportunity-resolved"], (
        "a remote read beat the renderer's paint opportunity")

    page.click(RUN_TAB)
    page.wait_for_timeout(300)
    assert not page.js_errors


# ---- what the fixtures wait on ---------------------------------------------

def _marked(browser, tmp_path, body: str, name: str):
    """A page carrying exactly the marks named, and nothing else of the panel.

    Deliberately NOT the real panel: the three states below are what
    `wait_until_settled` must do about the marks, and driving them through a
    real boot would test app.js's timing instead of this helper's rule.
    """
    page_file = tmp_path / name
    page_file.write_text(f"<!doctype html><html><body>{body}</body></html>",
                         encoding="utf-8")
    page = browser.new_page()
    page.goto(page_file.as_uri())
    return page


def test_a_settled_panel_ends_the_wait(browser, tmp_path):
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:fully-settled')</script>",
                   "settled.html")
    try:
        harness.wait_until_settled(page, timeout=2_000)
    finally:
        page.close()


def test_a_panel_that_failed_to_start_is_refused_not_handed_over(browser, tmp_path):
    """`init()` throwing fires `startup-failed` and never `fully-settled`.

    THE WAIT MUST END -- a fixture that hung here would report itself instead of
    the panel -- BUT IT MUST NOT HAND THE PAGE OVER. A merge gate demonstrated
    what returning costs: rename `id="signin"` in the generated page and
    `wireStartupShell()` dies on its first statement, the wait returned after
    31ms, `page.js_errors` was EMPTY because `startPanel()` caught the rejection,
    `window.__calls` was empty because the panel never made a request, and the
    test then failed on whatever selector it touched next with no mention of the
    panel having never started. Across the converted fixtures that is a silent
    pass at every call site.

    So it ends the wait by FAILING, with the reason the mark carries.
    """
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:startup-failed',"
                   " {detail: {message: 'the shell never wired'}})</script>",
                   "failed.html")
    try:
        with pytest.raises(Exception, match="the shell never wired"):
            harness.wait_until_settled(page, timeout=2_000)
    finally:
        page.close()


def test_a_failed_start_is_refused_by_the_interactive_wait_too(browser, tmp_path):
    """The same contract in the other helper, which had no test of its own until
    a single-dimension review removed its `startup-failed` arm and watched 289
    tests stay green."""
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:startup-failed',"
                   " {detail: {message: 'the shell never wired'}})</script>",
                   "failed-interactive.html")
    try:
        with pytest.raises(Exception, match="the shell never wired"):
            harness.wait_until_interactive(page, timeout=2_000)
    finally:
        page.close()


def test_the_interactive_wait_ends_on_the_mark_it_names(browser, tmp_path):
    """The literal at `panel_harness.py:968` is the whole subject of that helper's
    docstring, and until this it was bound by nothing.

    Its only other test drives a page carrying `startup-failed` alone, which ends
    the wait through the refusal arm both helpers share -- so it passes for EVERY
    possible value of the mark name. A merge gate demonstrated it: set the literal
    to `shell-interactive`, the spelling the docstring above it calls THE MISTAKE,
    and all three tests that touch the helper stayed green, 30 of 30.
    """
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:account-check-start')</script>",
                   "interactive.html")
    try:
        harness.wait_until_interactive(page, timeout=2_000)
    finally:
        page.close()


def test_the_interactive_wait_does_not_end_on_the_mark_it_used_to_wait_on(browser, tmp_path):
    """The other half of the same binding, aimed at the regression by name.

    `shell-interactive` fires from `wireStartupShell()` BEFORE `init()` awaits its
    paint opportunity, so a barrier keyed on it can return before `loadAccount()`
    has called `setChecking(true)` -- and the two tests of that transient then
    assert the shipped markup defaults and pass while testing nothing. This page
    carries that mark and nothing else: the wait must refuse it.
    """
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:shell-interactive')</script>",
                   "shell-only.html")
    try:
        with pytest.raises(Exception, match="imeout"):
            harness.wait_until_interactive(page, timeout=800)
    finally:
        page.close()


def test_the_real_panel_emits_the_mark_the_harness_refuses_on(browser, tmp_path):
    """Every test above drives a SYNTHETIC page, so none of them binds the name
    `tools/panel_harness.py` watches for to the name `extension/app.js` emits.

    Counted rather than numbered on purpose: this sentence said "the three tests
    above" and a later commit inserted two more directly above it without noticing.

    A merge gate named the surviving mutation: rename `markStartup("startup-failed"
    ...)` in the panel and every one of those tests stays green while both helpers
    silently lose the arm that refuses a dead panel. `fully-settled` and
    `account-check-start` are already bound to the real panel by the mark-ordering
    test above; `startup-failed` is not, because it fires only on failure.

    So this breaks the real panel and watches the real refusal. `wireStartupShell()`
    opens by wiring `#signin`, so a page whose signin button has been renamed makes
    `init()` reject, `startPanel()` catch it, and the mark carry the reason -- the
    exact sequence the gate demonstrated.
    """
    page_file = harness.build_page(tmp_path, harness.stub(), name="broken.html")
    markup = page_file.read_text(encoding="utf-8")
    assert markup.count('id="signin"') == 1, (
        "the page no longer carries exactly one #signin, so this test is breaking "
        "something other than the shell's first statement")
    page_file.write_text(markup.replace('id="signin"', 'id="signin-renamed"'),
                         encoding="utf-8")

    page = browser.new_page(viewport={"width": 360, "height": 800})
    try:
        page.goto(page_file.as_uri())
        with pytest.raises(AssertionError, match="failed to start"):
            harness.wait_until_settled(page, timeout=5_000)
        # AND THE REASON CAME FROM THE PANEL, not from the harness's own wording:
        # `startPanel()` catches the rejection, so `pageerror` never fires and the
        # message exists nowhere else a test can reach.
        detail = page.evaluate(
            "() => performance.getEntriesByName('scrapex:startup-failed')[0]"
            "?.detail?.message ?? null")
        assert detail and "addEventListener" in detail, (
            f"the panel marked a failure without saying what it was: {detail!r}")
    finally:
        page.close()


def test_a_failure_with_no_reason_is_still_refused(browser, tmp_path):
    """A mark carrying no `detail` must not read as success.

    A first draft keyed the refusal on `detail.message` and passed silently on a
    bare `performance.mark(...)` — green against a helper written to refuse it.
    The mark's PRESENCE decides; the message is only what the reader is told.
    """
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:startup-failed')</script>",
                   "failed-bare.html")
    try:
        with pytest.raises(Exception, match="unknown"):
            harness.wait_until_settled(page, timeout=2_000)
    finally:
        page.close()


def test_a_panel_that_never_settles_raises_rather_than_passing(browser, tmp_path):
    """The third state: `init()` returns early on a cancelled paint opportunity
    and fires NEITHER mark. There is nothing to wait for, and the wait must say
    so instead of returning — a helper that gave up quietly would put every
    fixture back to guessing."""
    page = _marked(browser, tmp_path, "<p>no marks at all</p>", "silent.html")
    try:
        with pytest.raises(Exception, match="imeout"):
            harness.wait_until_settled(page, timeout=1_000)
    finally:
        page.close()


def test_a_mark_that_merely_starts_the_same_way_does_not_end_it(browser, tmp_path):
    """`getEntriesByName` is exact, and this pins that it stays exact: a prefix
    match would let any future `scrapex:fully-settled-*` mark end the wait early,
    which is the quiet kind of wrong this whole change is removing."""
    page = _marked(browser, tmp_path,
                   "<script>performance.mark('scrapex:fully-settled-ish')</script>",
                   "near.html")
    try:
        with pytest.raises(Exception, match="imeout"):
            harness.wait_until_settled(page, timeout=800)
    finally:
        page.close()
