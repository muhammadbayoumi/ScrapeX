"""The panel's markup and its script must actually refer to each other.

This exists because of a real defect: the Add Site form was replaced by a Source
picker, the picker was never wired to anything, and the working form was left in
the markup behind `hidden aria-hidden="true"` with NOTHING in app.js referencing
it. Every test passed, the screenshots looked right, and a new owner could not
register a site at all.

These are static checks over the two files. They cannot prove the panel behaves
correctly — that needs the DOM harness — but they do prove the two halves are
still connected, which is exactly what silently came apart.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parent.parent / "extension"
HTML = (EXT / "app.html").read_text(encoding="utf-8")
JS = (EXT / "app.js").read_text(encoding="utf-8")

# Ids the markup defines, PLUS ids the script itself renders into the page —
# several rows are built with innerHTML and bound immediately afterwards, which
# is legitimate and must not be reported as a dangling reference.
DEFINED = set(re.findall(r'\bid="([\w-]+)"', HTML)) | \
    set(re.findall(r'\bid="([\w-]+)"', JS))
REFERENCED = set(re.findall(r'\$\("([\w-]+)"\)', JS)) | \
    set(re.findall(r'getElementById\("([\w-]+)"\)', JS))


def test_every_element_the_script_reaches_for_exists():
    """`$("x")` on an id no template renders returns null and the handler dies,
    usually taking every later binding in the same function with it."""
    missing = sorted(REFERENCED - DEFINED)
    assert not missing, f"app.js reaches for ids that app.html does not define: {missing}"


def test_the_add_site_form_is_reachable_from_the_script():
    """The exact regression: a complete form nothing could ever reveal."""
    assert "source-detail" in DEFINED, "the confirm-and-add form is gone"
    assert "source-detail" in REFERENCED, \
        "nothing in app.js reveals the add-site form — a new owner cannot add a site"


def test_no_element_is_permanently_hidden_from_assistive_tech():
    """`aria-hidden` on a container that becomes visible lies to a screen reader.

    Hiding is done with the `hidden` class, which JavaScript removes; aria-hidden
    would stay behind and keep the revealed form invisible to assistive tech.
    """
    stuck = re.findall(r'<div id="([\w-]+)"[^>]*\baria-hidden="true"[^>]*>', HTML)
    assert not stuck, f"these containers are hidden from assistive tech forever: {stuck}"


@pytest.mark.parametrize("handler", ["cur-use", "urls-check", "check", "add-btn"])
def test_every_source_entry_point_has_a_listener(handler):
    """Each way into the add-site flow must be bound, not merely present."""
    assert re.search(rf'\$\("{handler}"\)\.addEventListener', JS), \
        f"#{handler} is rendered but nothing listens to it"


def test_the_unbuilt_file_source_is_disabled_not_silent():
    """A control that looks ready and does nothing is worse than one that says so."""
    block = HTML[HTML.index('id="source-file"'):HTML.index('id="source-detail"')]
    assert "Not built yet" in block
    for action in ("file-upload", "screenshot-capture"):
        assert re.search(rf'disabled data-integration="{action}"', block), \
            f"the {action} button is enabled but nothing implements it"


def test_the_interface_stays_english():
    """Spec 1: Arabic is data, never interface. The panel's own markup carries
    no Arabic — the stress fixtures that do live in the screenshot harness."""
    arabic = re.findall(r"[؀-ۿ]+", HTML)
    assert not arabic, f"Arabic leaked into the panel markup: {arabic[:3]}"
