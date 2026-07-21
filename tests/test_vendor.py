"""Vendored third-party assets are present, whole, and licensed.

ScrapeX is local-first: it must work on a machine with no internet. A page that
fetched a library from a CDN would fail exactly when the owner is offline — the
one condition the product promises to survive — and would let a third party
change what runs on their machine without a commit. So the bytes are in the
repository, and these tests are what stop them from silently going missing,
being truncated by a bad checkout, or losing their licence text.
"""
from __future__ import annotations

from pathlib import Path

import pytest

VENDOR = Path(__file__).resolve().parent.parent / "scrapex" / "webui" / "static" / "vendor"
TEMPLATES = Path(__file__).resolve().parent.parent / "scrapex" / "webui" / "templates"

# name -> (minimum plausible size, a string that must appear in it)
EXPECTED = {
    "tabulator.min.js": (300_000, "Tabulator"),
    "tabulator.min.css": (15_000, "tabulator"),
    "tabulator.LICENSE.txt": (500, "MIT"),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_the_vendored_file_is_present_and_whole(name):
    """A truncated file is worse than a missing one: the page loads, the grid
    silently does not, and nothing says why."""
    path = VENDOR / name
    assert path.is_file(), f"{name} is not vendored — the Datasets grid cannot load offline"
    minimum, marker = EXPECTED[name]
    data = path.read_bytes()
    assert len(data) >= minimum, f"{name} is {len(data)} bytes — truncated?"
    assert marker.encode() in data or marker.lower().encode() in data.lower()


def test_the_licence_travels_with_the_code():
    """MIT requires the notice to be distributed with the software. Shipping the
    minified file and dropping its licence is a licence violation, not an
    oversight."""
    licence = (VENDOR / "tabulator.LICENSE.txt").read_text(encoding="utf-8")
    assert "MIT" in licence
    assert "Copyright" in licence


def test_nothing_in_the_ui_loads_code_from_the_internet():
    """The whole reason the bytes are vendored. A CDN reference anywhere here
    would break the offline promise and hand a third party the ability to change
    what runs on the owner's machine."""
    offenders = []
    for template in TEMPLATES.glob("*.html"):
        text = template.read_text(encoding="utf-8")
        for host in ("cdn.", "unpkg.com", "jsdelivr", "cdnjs", "googleapis.com/ajax"):
            if host in text:
                offenders.append(f"{template.name}: {host}")
    assert offenders == [], f"remote code referenced: {offenders}"


def test_the_datasets_page_loads_the_grid_from_our_own_origin():
    page = (TEMPLATES / "datasets.html").read_text(encoding="utf-8")
    assert '/static/vendor/tabulator.min.js' in page
    assert '/static/vendor/tabulator.min.css' in page


def test_the_marketlens_data_page_does_not_use_the_grid():
    """Deliberate, and worth a test because the temptation is obvious: on the
    Data page the URL IS the question — filters, sort and paging live in the
    query string so a link still means the same thing a week later, and the page
    works with scripting off. A grid holding its state in memory trades that away
    for column resizing."""
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    assert "tabulator" not in page.lower()
    assert "Tabulator" not in page
