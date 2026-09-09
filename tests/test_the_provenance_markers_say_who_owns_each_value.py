"""Every colour in design/tokens.css says whose it is, and this checks the answer.

WHAT THE MARKERS ARE. Each colour declaration in design/tokens.css carries an inline
comment naming the Supabase token it came from and one of two words:

    --accent-ink: #097c4f;      /* brand-600 light       PUBLISHED */
    --amber:      #f2af48;      /* --warning dark        derived   */

`PUBLISHED` means Supabase declares that value as a literal -- an HSL triple or a hex --
and converting a triple to hex is a change of notation, not an evaluation. `derived`
means the value is this product's own evaluation of one of their expressions.

WHY THAT IS A LICENCE STATEMENT. design/supabase.NOTICE.txt discharges Apache-2.0
section 4(b) and delegates the per-value record here: "WHICH IS WHICH IS RECORDED AT
EACH VALUE in design/tokens.css". A marker pointing the wrong way is a wrong statement
of changes, in the document a recipient reads to learn what was taken.

THREE THINGS THIS GUARD LEARNED THE HARD WAY, all in one review pass on its own first
version, and each is why an assertion below exists:

  1. IT TYPED THE UPSTREAM VALUES BY HAND -- 43 of them. Their sources declare 631 token
     names and 107 colour literals, so 64 literals were missing, including every one of
     the 52 in global.css. That did not make the check smaller, it made it WRONG in one
     direction: a `derived` marker on a value Supabase publishes outright passed, because
     the guard had no literal to contradict it. Under-crediting them is the direction
     every provenance error in this repository has run in. The table is now a generated
     fixture -- see tools/read_supabase_tokens.py.

  2. IT COULD NOT CATCH AN INVENTED NAME on the `derived` side. The name check returned
     early whenever the named token was unknown, so `--scale-900` was caught only because
     it also claimed PUBLISHED. `--destructive-fg` -- their token is
     `--destructive-foreground` -- and a claim naming `--brand`, which they do not
     declare at all, both passed. Every marker's name is now checked against the 631 they
     declare, whichever word it carries.

  3. ITS REGEX CROSSED NEWLINES. `\\s*` between the semicolon and the comment let a
     declaration bind to the NEXT comment in the file once its own was stripped, inventing
     a marker for a token that has none. Horizontal whitespace only, now.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Guards a design asset copied into the extension by tools/sync_design_assets.py;
# see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"
FIXTURE = ROOT / "tests" / "fixtures" / "supabase-design-tokens.json"

UPSTREAM = json.loads(FIXTURE.read_text(encoding="utf-8"))
THEIR_NAMES = frozenset(UPSTREAM["names"])
THEIR_LITERALS = UPSTREAM["literals"]

# Horizontal whitespace only between the declaration and its note. `\s` matches
# newlines, which let a declaration claim the next comment in the file as its own.
MARKED = re.compile(
    r"^[ \t]*(--[a-z0-9-]+)[ \t]*:[ \t]*(#[0-9a-fA-F]{3,8})[ \t]*;[ \t]*/\*([^*]*)\*/", re.M
)
LEADING_TOKEN = re.compile(r"^(--[a-z0-9-]+)")
FIRST_WORD = re.compile(r"^([a-z0-9-]+)")


def _named_token(note: str) -> str:
    """The upstream token a note names, ignoring how the value was obtained from it.

    A note may describe an operation -- "brand-default/80 flat" -- and the token is the
    name at the front. The marker word and the theme word are removed as WHOLE WORDS: an
    earlier version removed them as substrings, which turned
    `--colors-gray-light-900` into `--colors-gray--900`.
    """
    words = [w for w in note.split() if w not in ("PUBLISHED", "derived", "light", "dark")]
    claim = " ".join(words)
    leading = LEADING_TOKEN.match(claim)
    if leading:
        return leading.group(1)
    first = FIRST_WORD.match(claim)
    return "--" + first.group(1).split("/")[0] if first else ""


def _blocks() -> list[tuple[str, str]]:
    """(theme, block text) for the light and dark declaration blocks.

    The theme comes from WHICH BLOCK a declaration is in, never from the word "dark"
    appearing in its note -- a dark note that omits the word was otherwise checked
    against the light table.
    """
    source = TOKENS.read_text(encoding="utf-8")
    out = []
    for theme, pattern in (("light", r":root\s*\{"),
                           ("dark", r':root\[data-theme="dark"\]\s*\{')):
        match = re.search(pattern, source)
        assert match, f"no {theme} block in design/tokens.css"
        depth, start = 0, match.end() - 1
        for i in range(start, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append((theme, source[start:i]))
                    break
        else:
            raise AssertionError(f"the {theme} block does not close")
    return out


def _markers() -> list[tuple[str, str, str, str, str]]:
    """(theme, our token, our value, marker word, the upstream token it names)."""
    found = []
    for theme, block in _blocks():
        for match in MARKED.finditer(block):
            note = " ".join(match.group(3).split())
            marker = ("PUBLISHED" if "PUBLISHED" in note
                      else "derived" if "derived" in note else None)
            if marker is None:
                continue
            found.append((theme, match.group(1), match.group(2).lower(), marker, _named_token(note)))
    return found


def _literal(theme: str, token: str) -> str | None:
    """The hex Supabase publishes for a token in this theme, or at their root."""
    return THEIR_LITERALS[theme].get(token) or THEIR_LITERALS["root"].get(token)


ALL = _markers()
PUBLISHED = [m for m in ALL if m[3] == "PUBLISHED"]
DERIVED = [m for m in ALL if m[3] == "derived"]
IDS = {"all": [f"{m[0]}{m[1]}" for m in ALL],
       "pub": [f"{m[0]}{m[1]}" for m in PUBLISHED],
       "der": [f"{m[0]}{m[1]}" for m in DERIVED]}


def test_the_fixture_records_the_commit_the_notice_pins():
    """One commit, named in two places, and they must agree.

    The notice tells a recipient which commit the values came from; the fixture is what
    the guard compares against. If they drift, the guard checks the wrong Supabase.
    """
    pinned = re.search(r"^\s*Commit\s+([0-9a-f]{40})", NOTICE.read_text(encoding="utf-8"), re.M)
    assert pinned, "design/supabase.NOTICE.txt no longer pins a 40-character commit"
    assert UPSTREAM["commit"] == pinned.group(1), (
        f"the notice pins {pinned.group(1)[:8]} and the fixture was read at "
        f"{UPSTREAM['commit'][:8]}. Run tools/read_supabase_tokens.py to bring the "
        f"fixture to the pinned commit, and re-check every marker against it."
    )


def test_the_fixture_is_the_whole_reading_and_not_a_sample():
    """Nothing else fails if the fixture shrinks, so this does.

    Its first version held 107 of Supabase's literals because the generator read 7 of
    their 13 files and could not read the hsl() function form at all. Expanding it to
    the full reading changed NO test outcome -- restoring the 107-entry version left
    every assertion here green -- so the correction was carried by nothing and a revert
    would have gone unnoticed.

    Floors rather than exact counts, because a legitimate regeneration at a newer
    Supabase commit will move them. They are set where the known-blind version fails:
    it had 52 root literals and 27 dark, against 299 and 226 now.
    """
    assert len(THEIR_NAMES) >= 600, (
        f"the fixture holds {len(THEIR_NAMES)} token names. Supabase declares over 600 "
        f"across the files tools/read_supabase_tokens.py reads; a number this low means "
        f"the generator read fewer files than it should, or failed part way."
    )
    for scope, floor in (("root", 250), ("dark", 200), ("light", 25)):
        assert len(THEIR_LITERALS[scope]) >= floor, (
            f"the fixture holds {len(THEIR_LITERALS[scope])} {scope} literals, under the "
            f"floor of {floor}. Regenerate it with tools/read_supabase_tokens.py and "
            f"check what it could not read -- a partial fetch or an unrecognised literal "
            f"shape both produce a silently smaller fixture, which is the exact defect "
            f"this file exists to have caught once already."
        )


def test_the_file_still_carries_markers_to_check():
    """A regex that silently matches nothing is a green test that checks nothing."""
    assert len(PUBLISHED) >= 8 and len(DERIVED) >= 8, (
        f"parsed {len(PUBLISHED)} PUBLISHED and {len(DERIVED)} derived markers in "
        f"design/tokens.css. The comment format has changed and this guard is no longer "
        f"reading it; fix the parser rather than the floor."
    )


@pytest.mark.parametrize("theme,token,value,marker,named", ALL, ids=IDS["all"])
def test_every_marker_names_a_token_supabase_declares(theme, token, value, marker, named):
    """Whichever word it carries, the name has to be one of theirs.

    This is the assertion the first version lacked. `--scale-900` was caught only because
    it also claimed PUBLISHED; `--destructive-fg` and a claim naming `--brand` were not
    caught at all. A name they do not declare cannot be a provenance record.
    """
    assert named in THEIR_NAMES, (
        f"{theme} {token} records its origin as {named}, which Supabase does not declare "
        f"in any of the {len(UPSTREAM['files_read'])} files read at "
        f"{UPSTREAM['commit'][:8]}. Either the name is wrong -- theirs may be spelled out "
        f"in full, as --destructive-foreground rather than --destructive-fg -- or this "
        f"value did not come from them and has no business carrying a marker."
    )


@pytest.mark.parametrize("theme,token,value,_marker,named", PUBLISHED, ids=IDS["pub"])
def test_a_published_marker_equals_the_literal_it_names(theme, token, value, _marker, named):
    """PUBLISHED is a claim about THEIR authorship, so it is checked against them."""
    literal = _literal(theme, named)
    assert literal is not None, (
        f"{theme} {token} is marked PUBLISHED naming {named}, which Supabase declares but "
        f"does not publish as a literal -- it is computed. This value is therefore this "
        f"product's own evaluation of their expression, and the marker should read "
        f"`derived`."
    )
    assert literal == value, (
        f"{theme} {token} is marked PUBLISHED as {named}, which is {literal}, and this "
        f"ships {value}. A PUBLISHED value must be their literal and nothing else."
    )


@pytest.mark.parametrize("theme,token,value,_marker,named", DERIVED, ids=IDS["der"])
def test_a_derived_marker_does_not_claim_their_literal_as_ours(theme, token, value, _marker, named):
    """The mirror, and it is the direction every error here has run in.

    `derived` claims the arithmetic is ours. If the named token is one they publish
    outright and the value matches it, the claim takes credit for a transcription.
    """
    literal = _literal(theme, named)
    if literal is None:
        return
    assert literal != value, (
        f"{theme} {token} is marked derived naming {named}, but Supabase publishes "
        f"{named} as {literal} and this value equals it exactly. Nothing was derived; "
        f"the marker should read PUBLISHED."
    )


def test_the_notice_still_delegates_the_record_to_these_markers():
    """The markers are a licence statement only while the notice says they are."""
    assert "RECORDED AT EACH VALUE in design/tokens.css" in NOTICE.read_text(encoding="utf-8"), (
        "design/supabase.NOTICE.txt no longer delegates the per-value provenance record "
        "to design/tokens.css. If the notice states provenance itself now, this guard "
        "should be checking the notice instead."
    )
