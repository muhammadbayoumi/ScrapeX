"""The focus ring the web UI draws, measured in a browser (#721): the panel's check, over
every page the engine serves.

The pages are served by the engine's own app through its TestClient, with Chromium's
requests routed to it, so what is measured is the real templates and sheets with no port
or thread. The warehouse is the small one tests/test_webui.py ingests.
"""
from __future__ import annotations

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


@pytest.fixture()
def webui(browser, tmp_path):  # noqa: F811
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
    page = browser.new_page(viewport={"width": 1280, "height": 900})

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


def test_every_control_on_every_page_draws_the_ring(webui):
    """#721 names both surfaces. Each page is opened, and every control on it checked the
    way the panel's are; the data page's column chooser is opened and checked too, because
    its search field is a wrapper that only exists once it opens."""
    seen = {"controls": 0, "opened": 0, "ringless": [], "clipped": [], "doubled": []}
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
