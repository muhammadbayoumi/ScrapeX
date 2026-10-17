"""A skipped job on the engine's /jobs page still reads "Did not run" after the live
refresh repaints it (#1620 review, round 2).

The page's script repaints every row every 4 s while any job is live, and it rewrote the
progress cell as `done/total sources` -- so within one tick a job that never ran said
"0/1 sources" again. Served by the engine's own app through its TestClient, with
Chromium's requests routed to it, as tests/test_the_focus_ring_draws_in_the_web_ui.py does.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.jobs import _finish, create_job, get_job  # noqa: E402
from scrapex.vocab import JobStatus  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_panel_dom import browser  # noqa: E402,F401  (the fixture)

ORIGIN = "http://webui.test"


def test_a_skip_still_says_did_not_run_after_the_live_tick(browser, tmp_path):  # noqa: F811
    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    running = create_job(conn, ["ELSEWEDYSHOP"])
    conn.execute("UPDATE crawl_job SET status = 'running' WHERE job_ref = ?", (running,))
    skipped = create_job(conn, ["ELSEWEDYSHOP"])
    _finish(conn, get_job(conn, skipped)["job_id"], JobStatus.SKIPPED,
            f"This site's previous run was still going ({running})")
    conn.close()
    client = TestClient(create_app(db_path))
    page = browser.new_page()
    asked: list[str] = []

    def serve(route):
        asked.append(route.request.url)
        answer = client.request(route.request.method, route.request.url[len(ORIGIN):])
        route.fulfill(status=answer.status_code, body=answer.content,
                      headers={"content-type": answer.headers.get("content-type", "text/plain")})

    page.route("**/*", lambda route: route.abort())
    page.route(f"{ORIGIN}/**", serve)
    try:
        page.goto(f"{ORIGIN}/jobs")
        cell = page.locator(f'[data-job-ref="{skipped}"] [data-cell="progress"]')
        assert cell.inner_text() == "Did not run"
        page.wait_for_timeout(4800)
        assert any("/api/jobs" in url for url in asked), "the live tick never ran"
        assert cell.inner_text() == "Did not run", (
            "the live refresh rewrote a job that never ran as a count of sources")
        running_cell = page.locator(f'[data-job-ref="{running}"] [data-cell="progress"]')
        assert running_cell.inner_text().startswith("0/1 sources")
    finally:
        page.close()
