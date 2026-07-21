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


def test_the_data_page_uses_the_grid_from_our_own_origin():
    """The owner overruled the earlier "no grid on the Data page" rule after
    seeing what a header menu, drag-resize and drag-reorder actually buy. What
    does NOT change is where the bytes come from: our origin, never a CDN.

    The URL-as-question property that argued against a grid is kept where it
    still pays — the watch tiles, saved views and the offer history are all
    still plain links — while the table itself is now a grid.
    """
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    assert "/static/vendor/tabulator.min.js" in page
    assert "/static/grid.js" in page


def test_the_grid_script_is_served_from_our_origin_too():
    script = (VENDOR.parent / "grid.js")
    assert script.is_file(), "the Data page loads /static/grid.js"
    body = script.read_text(encoding="utf-8")
    assert "http://" not in body and "https://" not in body, (
        "the grid must not reach the internet at runtime")


def test_the_grid_features_panel_is_keyboard_operable_by_construction():
    """A real <details> with real checkboxes, not a custom popup: it opens and
    closes with the keyboard for free, and every toggle is a control that tabs.
    Building that from divs is where keyboard support usually gets lost."""
    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")

    assert "<details id=\"grid-features\"" in page
    assert page.count('type="checkbox" data-feature=') >= 6


def test_feature_choices_are_per_source_not_global():
    """A commodity table and a shop table do not want the same shape, so one
    global preference would be wrong for one of them."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert 'FEATURE_KEY = "scrapex-features-" + (mount.dataset.source' in script


def test_a_total_is_only_offered_where_a_total_means_something():
    """Summing prices across different currencies and units would be a number
    with no referent. The count is what is shown for anything not plainly
    additive."""
    script = (VENDOR.parent / "grid.js").read_text(encoding="utf-8")
    assert 'topCalc = "avg"' in script and 'topCalc = "count"' in script
