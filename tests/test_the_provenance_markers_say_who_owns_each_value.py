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
import sys
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


# THE THREE DECLARATION BLOCKS, and the theme each one's values belong to. There are TWO
# dark blocks -- `:root[data-theme="dark"]` is the explicit choice and
# `:root:not([data-theme="light"])` inside `@media (prefers-color-scheme: dark)` is the
# device following the operating system -- and this guard read only the first. The second
# holds 28 colour declarations, so a marker written there was checked by nothing.
#
# It is not required to CARRY markers: the two blocks hold identical values, pinned to each
# other by test_a_palette_may_change_nothing_but_colour.py::test_both_dark_blocks_agree, so
# the provenance record for a dark value is made once in the explicit block. What this
# closes is the other direction -- a marker that IS written here is now checked.
BLOCKS = (
    ("light", r":root\s*\{"),
    ("dark", r':root\[data-theme="dark"\]\s*\{'),
    ("dark", r':root:not\(\[data-theme="light"\]\)\s*\{'),
)


def _without_comment_bodies(source: str) -> str:
    """`source` with each comment's body replaced by spaces, and its length preserved.

    THE BRACE SCAN BELOW COUNTS CHARACTERS, so a `}` inside a comment closes a block that
    has not ended -- every marker after it vanishes from the parse, and the result is a
    green test checking less than it says. design/tokens.css carries 75 comments and none
    holds a brace today, so this is a latch rather than a repair; the file is prose-heavy
    and the failure would be silent.

    LENGTHS ARE PRESERVED because the slices index the ORIGINAL text, and the markers this
    guard reads live inside exactly those comments. Stripping them would delete the thing
    being checked.
    """
    return re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), source, flags=re.S)


def _blocks() -> list[tuple[str, str]]:
    """(theme, block text) for the light and the two dark declaration blocks.

    The theme comes from WHICH BLOCK a declaration is in, never from the word "dark"
    appearing in its note -- a dark note that omits the word was otherwise checked
    against the light table.
    """
    source = TOKENS.read_text(encoding="utf-8")
    scanned = _without_comment_bodies(source)
    out = []
    for theme, pattern in BLOCKS:
        match = re.search(pattern, scanned)
        assert match, f"no {theme} block matching {pattern} in design/tokens.css"
        depth, start = 0, match.end() - 1
        for i in range(start, len(scanned)):
            if scanned[i] == "{":
                depth += 1
            elif scanned[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append((theme, source[start:i]))
                    break
        else:
            raise AssertionError(f"the {theme} block matching {pattern} does not close")
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


# EVERY VALUE THAT CARRIES A LICENCE STATEMENT TODAY, pinned as a SET and not a count.
# The marker word is what opts a value into being checked at all, so deleting the word
# deletes the check: the parametrized tests below simply get one case fewer, the floor
# test still passes because the total is nowhere near its floor, and nothing anywhere
# says a value lost its statement.
#
# 22 of the 40 colour declarations carrying an inline note are marked. The other 18 name
# a Supabase token their sources COMPUTE -- so each is a `derived` nobody wrote down --
# and that gap is recorded in its own issue rather than closed here.
MARKED_VALUES = frozenset({
    ("dark", "--accent"),
    ("dark", "--accent-contrast"),
    ("dark", "--accent-hover"),
    ("dark", "--accent-ink"),
    ("dark", "--accent-weak"),
    ("dark", "--amber"),
    ("dark", "--amber-ink"),
    ("dark", "--amber-weak"),
    ("dark", "--danger-contrast"),
    ("dark", "--focus"),
    ("dark", "--red"),
    ("dark", "--red-weak"),
    ("light", "--accent"),
    ("light", "--accent-active"),
    ("light", "--accent-hover"),
    ("light", "--accent-ink"),
    ("light", "--accent-weak"),
    ("light", "--amber-weak"),
    ("light", "--danger-contrast"),
    ("light", "--focus"),
    ("light", "--red"),
    ("light", "--red-weak"),
})

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


def test_every_stored_literal_is_what_the_converter_produces():
    """The fixture is generated, and nothing asserted the generator still reproduces it.

    THIS IS THE STALENESS CHECK, and it runs offline. The fixture records each raw
    declaration beside the hex it converted to, so every entry can be re-derived here
    from tools/read_supabase_tokens.py's own `as_hex` without the network or `gh`.
    `--check` re-reads their files and is the human's tool; this is CI's.

    It exists because two arithmetic defects shipped in a fixture that no test could
    contradict, and correcting them changed NO test outcome -- exactly the condition the
    reading-is-whole test above warns about, where a revert goes unnoticed:

      * `_hsl` rounded ties to EVEN. Three conversions land on an exact tie and a CSS
        engine rounds ties AWAY FROM ZERO, so `hsl(206, 100%, 50%)` was stored as
        #0090ff where Chromium renders #0091ff.
      * 48 alpha-bearing declarations were stored as fully opaque. `hsla(0, 0%, 0%, 0)`
        became #000000 -- an assertion that Supabase publishes opaque black where they
        publish full transparency.

    Either regression now fails here rather than silently weakening the table.
    """
    from tools.read_supabase_tokens import as_hex

    conversions = UPSTREAM.get("conversions")
    assert conversions, (
        "the fixture records no `conversions` map, so nothing can re-derive it. Regenerate "
        "it with tools/read_supabase_tokens.py, which writes one."
    )
    wrong = {raw: (stored, as_hex(raw)) for raw, stored in conversions.items()
             if as_hex(raw) != stored}
    assert not wrong, (
        f"{len(wrong)} of {len(conversions)} stored literals are not what "
        f"tools/read_supabase_tokens.py now produces, so the fixture is stale against its "
        f"own generator. First few (raw: stored -> produced): "
        f"{dict(list(wrong.items())[:5])}. Run `python tools/read_supabase_tokens.py` and "
        f"re-check every marker against the result."
    )


def test_every_published_literal_came_through_that_converter():
    """The conversions map has to COVER the table, or the check above proves nothing.

    A generator that stopped recording conversions -- or recorded a handful -- would leave
    the test above green over an empty or partial map while the literals it is supposed to
    guard went unchecked.
    """
    produced = set(UPSTREAM["conversions"].values())
    stored = {value for scope in THEIR_LITERALS.values() for value in scope.values()}
    missing = stored - produced
    assert not missing, (
        f"{len(missing)} literal(s) in the table were produced by no recorded conversion, "
        f"so test_every_stored_literal_is_what_the_converter_produces cannot see them: "
        f"{sorted(missing)[:5]}. The generator and the fixture disagree about their own "
        f"provenance; regenerate it."
    )


def test_the_fixture_names_the_files_that_declare_nothing():
    """Two of the thirteen sources declare no custom property, and that is recorded.

    An empty file otherwise reads the same as a file this tool failed to fetch or could
    not parse, and the difference decides whether a missing name is Supabase's choice or
    this tool's bug. Listing them keeps a future commit that STARTS declaring in them --
    or a fetch that silently returns nothing -- from passing as the status quo.
    """
    from tools.read_supabase_tokens import DECLARE_NOTHING

    assert UPSTREAM.get("files_declaring_nothing") == sorted(DECLARE_NOTHING), (
        f"the fixture says {UPSTREAM.get('files_declaring_nothing')} declare nothing and "
        f"tools/read_supabase_tokens.py expects {sorted(DECLARE_NOTHING)}. Either Supabase "
        f"changed those files at the pinned commit, or the reader stopped reading one. "
        f"Regenerate and check which."
    )


@pytest.mark.parametrize("theme,token", sorted(MARKED_VALUES), ids=lambda p: str(p))
def test_a_marked_value_cannot_quietly_stop_being_checked(theme, token):
    """Every check in this file is opt-in, and the marker word is what opts in.

    Delete the word `PUBLISHED` from a declaration and its value stops being compared
    against Supabase's -- the parametrized tests simply get one case fewer, the floor test
    still passes because the total is nowhere near its floor, and nothing anywhere says a
    value lost its licence statement. That is the whole check removed by a one-word edit.

    So the SET is pinned, not just the count. Adding a marker fails here too, deliberately:
    a new marker is a new statement in the Apache 4(b) record and belongs in this list by a
    decision rather than by arriving.
    """
    assert (theme, token) in {(m[0], m[1]) for m in ALL}, (
        f"{theme} {token} carried a PUBLISHED/derived marker and no longer does, so its "
        f"value is no longer checked against Supabase's. If the value genuinely stopped "
        f"coming from them, remove it from MARKED_VALUES in this file and say so in the "
        f"PR; if the marker was deleted by accident, put it back."
    )



def test_a_brace_inside_a_comment_cannot_close_a_block():
    """The blanking is driven with input that HAS the defect, not with today's file.

    design/tokens.css carries no brace in any comment right now, so removing the blanking
    changes nothing there and a guard resting on that file passes either way -- measured,
    the mutation survived the whole suite. This drives the helper directly instead.
    """
    source = ":root {\n  --a: #111111; /* a note with } in it   PUBLISHED */\n  --b: #222222;\n}\n"
    scanned = _without_comment_bodies(source)

    assert len(scanned) == len(source), (
        "the blanking changed the length, so every slice taken from it indexes the wrong "
        "part of the original text"
    )
    assert scanned.count("{") == 1 and scanned.count("}") == 1, (
        f"the scan sees {scanned.count('{')} open and {scanned.count('}')} close braces; "
        f"the block's own pair should be the only one left"
    )
    assert "--a: #111111;" in scanned and "--b: #222222;" in scanned, (
        "the blanking ate a declaration that was outside a comment"
    )


def test_the_block_scan_survives_a_brace_in_a_comment(tmp_path, monkeypatch):
    """The whole scan, over a file whose first comment holds an unbalanced brace.

    Without the blanking the light block comes back truncated at that comment and every
    marker after it disappears -- a green test checking less than it says.
    """
    written = (
        ":root {\n"
        "  /* the light block. A stray } lives in this sentence. */\n"
        "  --accent: #3fcf8e; /* --brand-default light   PUBLISHED */\n"
        "}\n"
        ':root[data-theme="dark"] {\n'
        "  --accent: #3ecf8e; /* --brand-default dark   PUBLISHED */\n"
        "}\n"
        ':root:not([data-theme="light"]) {\n'
        "  --accent: #3ecf8e; /* --brand-default dark   PUBLISHED */\n"
        "}\n"
    )
    path = tmp_path / "tokens.css"
    path.write_text(written, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "TOKENS", path)

    blocks = _blocks()
    assert [theme for theme, _ in blocks] == ["light", "dark", "dark"], (
        f"expected the light block and BOTH dark blocks, got {[t for t, _ in blocks]}"
    )
    assert "--accent: #3fcf8e;" in blocks[0][1], (
        "the light block was truncated at the comment holding the stray brace, so the "
        "marker after it was never parsed"
    )


def test_both_dark_selectors_are_among_the_blocks_read():
    """Dropping the second changes nothing about today's file, so assert the rule.

    The media-query dark block carries 28 colour declarations and no markers, so removing
    it from BLOCKS leaves every other assertion green -- measured, that mutation survived
    the whole suite. What has to hold is that both dark selectors are read at all.
    """
    selectors = [pattern for _, pattern in BLOCKS]

    assert any("data-theme" in p and "not" not in p for p in selectors), (
        "the explicit dark block is no longer read"
    )
    assert any("not" in p and "light" in p for p in selectors), (
        "the media-query dark block is no longer read, so a marker written there would be "
        "checked by nothing -- which is the gap this entry closes"
    )
    scanned = _without_comment_bodies(TOKENS.read_text(encoding="utf-8"))
    for pattern in selectors:
        assert re.search(pattern, scanned), (
            f"BLOCKS names {pattern}, which design/tokens.css no longer contains"
        )


def test_as_hex_keeps_an_alpha_written_as_eight_hex_digits():
    """Their sources write alpha as hsla() today, so no real value exercises this path.

    A guard resting on the fixture therefore cannot see the truncation come back --
    measured, restoring `digits[:6]` survived the whole suite. This drives as_hex directly.
    """
    from tools.read_supabase_tokens import as_hex

    assert as_hex("#11223344") == "#11223344", (
        "an eight-digit hex lost its alpha byte, which records a value Supabase publishes "
        "with transparency as the opaque one"
    )
    assert as_hex("#1122") == "#11112222", (
        f"a four-digit shorthand expanded wrongly: {as_hex('#1122')}"
    )
    assert as_hex("#112233ff") == "#112233", (
        "an explicitly opaque alpha should collapse, so the two spellings of one opaque "
        "colour compare equal"
    )
    assert as_hex("#123") == "#112233" and as_hex("#112233") == "#112233", (
        "the plain hex paths changed"
    )

def test_the_notice_still_delegates_the_record_to_these_markers():
    """The markers are a licence statement only while the notice says they are."""
    assert "RECORDED AT EACH VALUE in design/tokens.css" in NOTICE.read_text(encoding="utf-8"), (
        "design/supabase.NOTICE.txt no longer delegates the per-value provenance record "
        "to design/tokens.css. If the notice states provenance itself now, this guard "
        "should be checking the notice instead."
    )
