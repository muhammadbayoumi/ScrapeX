"""The web UI's focus-ring sweep at 640px, in a file of its own so CI's `--dist loadfile`
runs it on its own worker (#1489). The sweep is tests/test_the_focus_ring_draws_in_the_web_ui.py's."""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from tests.test_panel_dom import browser  # noqa: E402,F401  (the fixture)
from tests.test_the_focus_ring_draws_in_the_web_ui import every_page_swept, webui  # noqa: E402,F401


def test_every_control_on_every_page_draws_the_ring_at_640px(webui):
    every_page_swept(webui, 640)
