"""MarketLens is gone, and the places that still say so are the places that must.

He asked for it deleted -- «اى حاجة لها علاقة ب MarketLens احذفها تم التخلى عنها
مسبقا» -- and most of it went. What is left is not leftovers: each remaining
mention names a thing that still EXISTS outside this repository, and removing the
name would either break it or remove the only warning about it.

MEASURED ON HIS OWN DISK, 2026-08-30, which is why this file exists rather than a
commit that deleted the rest:

    ~/.scrapex/marketlens/marketlens.db      115.8 MB, still there
      application_id                          0x53584d4c
      scrapex_meta[database_kind]             'marketlens'
      scrapex_meta[migration_stream]          'marketlens'

WITHOUT THIS GUARD THE PURGE UNDOES ITSELF TWICE OVER. A new session copies an old
comment and the name is back; or a session doing exactly what he asked deletes one
of the entries below and takes a live contract with it. Both are silent.
"""
from __future__ import annotations

import pathlib
import re

import pytest

# BOTH MARKS. It is a documentation-tier guard by subject, and it reads
# `extension/` in SEARCHED -- and `test_the_extension_gate_is_complete`
# refuses an unmarked file that does, so an extension-only change would
# otherwise stop running the guard on exactly the pull requests that can
# reintroduce the name.
pytestmark = [pytest.mark.docs, pytest.mark.extension]

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAME = re.compile("marketlens", re.IGNORECASE)

#: Where the product's name may still appear in shipped code, and WHY. Anything
#: not listed here is a leftover and must go.
#:
#: Deleting a row means deleting the thing it protects. Read the reason first.
ALLOWED: dict[str, str] = {
    # `db/engine/schema.sql` AND `0002_...` STOOD HERE AND BOTH ARE GONE, which is
    # what this table is for and the first time it has happened by deletion rather
    # than by rename.
    #
    # Both rows said FROZEN: the baseline created `site_profile.marketlens_source_key`
    # and `0002` renamed it, and neither file could be edited because its digest is in
    # every existing ledger. `R-84`'s squash did not edit them -- it REGENERATED the
    # baseline from a database the chain built, so the column is created under its
    # current name and the migration that renamed it no longer ships. Measured after
    # the squash: `grep -ci marketlens db/engine/schema.sql` answers 0.
    #
    # This test's third clause is what found it: an allowed row whose file no longer
    # names the retired product goes red, so the exceptions could not outlive the
    # thing they protected.
    "scrapex/databases/carry_over.py":
        "CONTRACT. `marketlens_path` is a key inside ~/.scrapex/databases.json, "
        "written there by a shipped version. Rename it and carry-over silently "
        "drops the priced warehouse, reports success, and rewrites the pointer "
        "to `single` -- an installation that comes up healthy with its whole "
        "price history orphaned.",
    "scrapex/compaction.py":
        "LIVE VALUE. A real database on his disk still says "
        "`database_kind = 'marketlens'` about itself. These paragraphs are why "
        "the check reads the file header instead of that row -- a copied row "
        "lets a wrong successor vouch for itself.",
    "scrapex/databases/domain.py":
        "A RECORD OF A DELETION (OP-115). It names the constant that was "
        "removed and why, so `git log -S` still finds it.",
    "scrapex/db.py":
        "A RECORD OF A DELETION (OP-115). The comment beside `pending_migrations` "
        "names the filter that hid two real migrations, so the reason it went "
        "is readable where the code used to be.",
    "db/engine/derived-from.json":
        "FROZEN, and it says so in its own first line -- \"frozen at the M5 "
        "collapse\". It records which column of which retired stream each part "
        "of the engine schema came from, and `test_one_schema_carries_both_streams` "
        "reads it as the record. Editing it falsifies the derivation.",
    "scrapex/webui/app.py":
        "A RECORD OF A FIX (OP-117). The data-model page labelled one engine "
        "database `MarketLens` and reported its tables twice.",
    "scrapex/webui/templates/settings.html":
        "A retired ROUTE, corrected on the branch for OP-116. This row goes "
        "when that lands.",
}

#: What the tree looks for. Tests and documents are excluded on purpose: the
#: documents are a HISTORY of a product that existed and must keep saying so,
#: and `docs/plans/` is frozen by `docs/plans/README.md`.
SEARCHED = ("scrapex", "db", "extension", "packaging", "tools")
SUFFIXES = {".py", ".js", ".html", ".sql", ".json", ".yaml", ".yml", ".toml", ".css"}


def _mentions() -> dict[str, int]:
    found: dict[str, int] = {}
    for area in SEARCHED:
        for path in (ROOT / area).rglob("*"):
            if path.suffix not in SUFFIXES or "__pycache__" in path.parts:
                continue
            hits = len(NAME.findall(path.read_text(encoding="utf-8", errors="replace")))
            if hits:
                found[path.relative_to(ROOT).as_posix()] = hits
    return found


def test_no_new_file_names_the_retired_product():
    """THE PURGE STAYS DONE. A name copied out of an old comment comes back
    silently; nothing else in the repository would notice."""
    unexpected = sorted(set(_mentions()) - set(ALLOWED))
    assert not unexpected, (
        "these name a product that was abandoned and are not in the allowed "
        f"list: {unexpected}. If the mention is history, put it in a document; "
        "if it names something that still exists, add a row to ALLOWED saying "
        "what it protects.")


@pytest.mark.parametrize("path", sorted(ALLOWED), ids=lambda p: p.split("/")[-1])
def test_an_allowed_mention_still_exists(path: str):
    """AND THE OPPOSITE FAILURE, which is the dangerous one. A row whose file no
    longer mentions the name is a row protecting nothing -- and the next reader
    takes it as proof the danger was handled. Delete the row, not the reason."""
    if path == "scrapex/webui/templates/settings.html":
        pytest.skip("goes when OP-116 lands; see its row")
    assert NAME.search((ROOT / path).read_text(encoding="utf-8", errors="replace")), (
        f"{path} no longer names it, so its ALLOWED row protects nothing. "
        "Either the thing it guarded was removed -- in which case say so where "
        "it was removed -- or the name was deleted and a contract went with it.")


def test_every_allowed_row_says_what_it_protects():
    """A row without a reason is a hole with a name on it."""
    thin = sorted(path for path, why in ALLOWED.items() if len(why) < 60)
    assert not thin, f"these rows do not say what they protect: {thin}"
