"""A name stays inside its folder, at every edge of what `inside` can mean."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scrapex.paths import name_inside


def test_a_plain_name_lands_inside_the_folder(tmp_path):
    assert name_inside(tmp_path, "a.zip") == Path(os.path.realpath(tmp_path)) / "a.zip"


def test_a_name_may_hold_folders_of_its_own(tmp_path):
    """A zip's `sub/file.json` is a legitimate entry."""
    assert name_inside(tmp_path, "sub/file.json") == (
        Path(os.path.realpath(tmp_path)) / "sub" / "file.json")


def test_a_name_that_steps_out_of_a_subfolder_and_stays_inside_is_inside(tmp_path):
    name = os.path.join("a", os.pardir, "b.txt")

    assert name_inside(tmp_path, name) == Path(os.path.realpath(tmp_path)) / "b.txt"


def test_the_folder_need_not_exist_yet(tmp_path):
    """The journal asks this for every source, including ones that never ran."""
    folder = tmp_path / "not-created"

    assert name_inside(folder, "a").name == "a"
    assert not folder.exists(), "asking where a name lands created the folder"


@pytest.mark.parametrize("name", [
    os.pardir,
    os.path.join(os.pardir, "x"),
    os.path.join("a", os.pardir, os.pardir, "x"),
    "",
    os.curdir,
], ids=["the parent", "beside it", "out through a subfolder", "empty", "the folder itself"])
def test_a_name_that_does_not_land_inside_is_refused(tmp_path, name):
    folder = tmp_path / "out"
    folder.mkdir()

    with pytest.raises(ValueError, match="would land outside"):
        name_inside(folder, name)


def test_an_absolute_name_is_refused(tmp_path):
    folder = tmp_path / "out"

    with pytest.raises(ValueError, match="would land outside"):
        name_inside(folder, str(tmp_path / "elsewhere" / "x"))


def test_a_sibling_whose_name_begins_the_same_is_outside(tmp_path):
    """A prefix check without the separator reads `out-and-more` as inside `out`."""
    folder = tmp_path / "out"
    folder.mkdir()

    with pytest.raises(ValueError, match="would land outside"):
        name_inside(folder, os.path.join(os.pardir, "out-and-more", "x"))


def test_a_link_inside_the_folder_that_leads_out_of_it_is_outside(tmp_path):
    """The name is spelled inside and the file would land elsewhere, which is the case
    a check on the spelling alone cannot see. A junction needs no privilege on Windows."""
    folder = tmp_path / "out"
    folder.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = folder / "link"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(elsewhere), str(link))
    else:
        link.symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(ValueError, match="would land outside"):
        name_inside(folder, os.path.join("link", "x"))


def test_a_folder_that_is_a_link_is_followed_and_its_names_land_inside(tmp_path):
    """His folders may be links. The check compares where things really are, so a linked
    folder is not refused for its own spelling."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(real), str(link))
    else:
        link.symlink_to(real, target_is_directory=True)

    assert name_inside(link, "a") == Path(os.path.realpath(real)) / "a"


def test_a_drive_root_is_a_folder_like_any_other(tmp_path):
    """A root already ends in its separator, so adding one blindly refuses everything."""
    root = Path(tmp_path.anchor)

    assert name_inside(root, "a") == Path(os.path.realpath(root)) / "a"


@pytest.mark.parametrize("name", [r"..\x", r"a\..\..\x", "Z:elsewhere"],
                         ids=["back slash", "back slash through a subfolder", "another drive"])
def test_what_leaves_on_windows_is_refused_there_and_is_a_plain_name_elsewhere(tmp_path, name):
    """Windows-only spellings, so the answer depends on where the engine runs."""
    folder = tmp_path / "out"
    folder.mkdir()

    if os.name == "nt":
        with pytest.raises(ValueError, match="would land outside"):
            name_inside(folder, name)
    else:
        assert name_inside(folder, name).parent == Path(os.path.realpath(folder))


def test_the_refusal_says_what_was_refused(tmp_path):
    """Whoever reads this has to find the bad name, so it travels with the error."""
    with pytest.raises(ValueError) as refused:
        name_inside(tmp_path, os.pardir)

    assert repr(os.pardir) in str(refused.value)
    assert str(tmp_path) in str(refused.value)
