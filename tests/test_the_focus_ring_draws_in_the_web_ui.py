"""The focus ring the web UI draws, measured in a browser (#721): the panel's check, over
every page the engine serves.

The pages are served by the engine's own app through its TestClient, with Chromium's
requests routed to it, so what is measured is the real templates and sheets with no port
or thread. The warehouse is the small one tests/test_webui.py ingests.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402
from tests.test_panel_dom import browser  # noqa: E402,F401  (the fixture)
from tests.test_the_focus_ring_draws_in_the_panel import sweep  # noqa: E402

ORIGIN = "http://webui.test"
PAGES = ["/", "/data", "/data-model", "/schema", "/changes", "/history", "/review", "/jobs",
         "/schedules", "/logs", "/exports", "/settings", "/sync", "/manage", "/source/ELSEWEDYSHOP"]


@contextmanager
def webui_page(browser, tmp_path, **page_options):
    """A page of `browser`, opened with `page_options` (Playwright's new_page keywords), whose
    requests to ORIGIN the engine's own app answers over the warehouse it builds in `tmp_path`.
    tests/test_no_reach_takes_another_controls_tap.py opens one as a phone."""
    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1", product_name="LED Floodlight 400W"),
        one_row(external_product_id="2", external_variant_id="v2", product_name="Copper Wire",
                price="50.00", availability="out_of_stock"),
    ])])
    conn.commit()
    conn.close()
    client = TestClient(create_app(db_path))
    page = browser.new_page(**page_options)

    def serve(route):
        request = route.request
        answer = client.request(request.method, request.url[len(ORIGIN):], content=request.post_data_buffer,
                                headers={"content-type": request.headers.get("content-type", "")})
        route.fulfill(status=answer.status_code, body=answer.content,
                      headers={"content-type": answer.headers.get("content-type", "text/plain")})

    page.route("**/*", lambda route: route.abort())  # nothing leaves the machine
    page.route(f"{ORIGIN}/**", serve)
    try:
        yield page
    finally:
        page.close()


@pytest.fixture()
def webui(browser, tmp_path):  # noqa: F811
    with webui_page(browser, tmp_path, viewport={"width": 1280, "height": 900}) as page:
        yield page


def every_page_swept(webui, width: int) -> None:
    """#721 names both surfaces. Each page is opened, and every control on it checked the
    way the panel's are; the data page's column chooser is opened and checked too, because
    its search field is a wrapper that only exists once it opens. The web UI lays out
    differently at 900px and at 640px, and a ring that shows at one width can be cut at
    another, so each is swept (#1471).

    ONE FILE PER WIDTH, and that is the point of the split (#1489). CI runs the suite
    with `--dist loadfile`, which keeps a file on one worker, so three widths in one file
    ran one after another on one worker. Each width now has its own file:
    tests/test_the_focus_ring_draws_in_the_web_ui_at_900px.py and ..._at_640px.py."""
    webui.set_viewport_size({"width": width, "height": 900})
    seen = {"controls": 0, "opened": 0, "ringless": [], "clipped": [], "doubled": [], "faded": []}
    for path in PAGES:
        response = webui.goto(ORIGIN + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        webui.wait_for_load_state("networkidle")
        webui.keyboard.press("Tab")  # keyboard modality, so programmatic focus is :focus-visible
        for key, value in sweep(webui, path).items():
            seen[key] += value
    webui.evaluate("() => document.querySelector('#grid-columns-button').click()")
    webui.wait_for_selector(".column-chooser-search input")
    chooser = sweep(webui, "column chooser")
    assert chooser["controls"] >= 3, chooser
    for key, value in chooser.items():
        seen[key] += value
    assert seen["controls"] >= 300, seen
    assert not seen["ringless"], f"controls that draw no focus ring: {seen['ringless']}"
    assert not seen["clipped"], f"controls whose ring shows on fewer than two sides: {seen['clipped']}"
    assert not seen["doubled"], f"fields that draw a ring or gap under their wrapper's: {seen['doubled']}"
    assert not seen["faded"], f"controls whose ring is painted below full opacity: {seen['faded']}"


def test_every_control_on_every_page_draws_the_ring(webui):
    every_page_swept(webui, 1280)


def test_every_narrower_width_keeps_its_own_sweep():
    """The 900px and 640px sweeps live in files of their own, so deleting one would drop
    its width from CI with nothing failing: the browser-suite step discovers the files
    there are, not the ones there should be."""
    here = Path(__file__).parent
    missing = [width for width in (900, 640)
               if not (here / f"test_the_focus_ring_draws_in_the_web_ui_at_{width}px.py").is_file()]
    assert not missing, f"no sweep file for the web UI at {missing}px"
