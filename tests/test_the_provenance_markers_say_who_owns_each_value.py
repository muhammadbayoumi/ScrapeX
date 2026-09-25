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

  1. IT TYPED THE UPSTREAM VALUES BY HAND -- 43 of them, against the 607 colour
     literals their sources actually declare, so all but a handful were missing --
     including every one of those in global.css. That did not make the check smaller,
     it made it WRONG in one
     direction: a `derived` marker on a value Supabase publishes outright passed, because
     the guard had no literal to contradict it. Under-crediting them is the direction
     every provenance error in this repository has run in. The table is now a generated
     fixture -- see tools/read_supabase_tokens.py.

  2. IT COULD NOT CATCH AN INVENTED NAME on the `derived` side. The name check returned
     early whenever the named token was unknown, so `--scale-900` was caught only because
     it also claimed PUBLISHED. `--destructive-fg` -- their token is
     `--destructive-foreground` -- and a claim naming `--brand`, which they do not
     declare at all, both passed. Every marker's name is now checked against the 648
     they declare, whichever word it carries.

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
    entry = THEIR_LITERALS[theme].get(token) or THEIR_LITERALS["root"].get(token)
    return entry["hex"] if entry else None


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
    Supabase commit will move them -- but CLOSE to the real numbers, not merely above the
    known-blind version. Set at the old distance they did not fire on a real shrink:
    78 literals and 48 names could be deleted and every floor was still met exactly.
    A regeneration that moves them is expected to move these lines with it, deliberately.
    """
    assert len(THEIR_NAMES) >= 660, (
        f"the fixture holds {len(THEIR_NAMES)} token names. Supabase declares 669 "
        f"across the files tools/read_supabase_tokens.py reads; a number this low means "
        f"the generator read fewer files than it should, or failed part way."
    )
    for scope, floor in (("root", 290), ("dark", 220), ("light", 27)):
        assert len(THEIR_LITERALS[scope]) >= floor, (
            f"the fixture holds {len(THEIR_LITERALS[scope])} {scope} literals, under the "
            f"floor of {floor}. Regenerate it with tools/read_supabase_tokens.py and "
            f"check what it could not read -- a partial fetch or an unrecognised literal "
            f"shape both produce a silently smaller fixture, which is the exact defect "
            f"this file exists to have caught once already."
        )


def test_a_name_the_design_site_declares_is_one_of_theirs():
    """The font stacks and the type ramp were taken from the design site's own sheet (#1017).

    `apps/design-system/styles/globals.css` declares `--font-heading` at :15, and the
    notice lists that file among the sources. Until the reader read it, a marker naming
    one of its 23 names failed as "Supabase does not declare it".
    """
    assert "--font-heading" in THEIR_NAMES, (
        "apps/design-system/styles/globals.css is not in the reading; add it to SOURCES in "
        "tools/read_supabase_tokens.py and regenerate the fixture")


def test_the_notice_lists_exactly_the_files_the_reader_reads():
    """The notice's "Files read" is a claim in a licence statement, so it is held to the tool.

    It listed 6 files while the reader read 13, one of them (globals.css) not read at all,
    so it was neither the reading nor a subset of it (#781). Compared with SOURCES and
    with what the fixture records it actually read.
    """
    from tools.read_supabase_tokens import SOURCES

    text = NOTICE.read_text(encoding="utf-8")
    block = text.split("  Files read:\n", 1)[1].split("\n\n", 1)[0]
    listed = [line.strip() for line in block.splitlines() if line.strip()]
    assert listed, "found no 'Files read:' list in design/supabase.NOTICE.txt"
    assert sorted(listed) == sorted(SOURCES), (
        f"design/supabase.NOTICE.txt lists {len(listed)} files and the reader reads "
        f"{len(SOURCES)}.\n  listed, not read: {sorted(set(listed) - set(SOURCES))}\n"
        f"  read, not listed: {sorted(set(SOURCES) - set(listed))}")
    assert sorted(UPSTREAM["files_read"]) == sorted(SOURCES), (
        "the fixture was read from a different file list than SOURCES; regenerate it")


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

    THIS IS THE STALENESS CHECK, and it runs offline. Every entry in the table stores
    the raw declaration beside the hex it converted to, so each is re-derived here through
    tools/read_supabase_tokens.py's own `as_hex` without the network or `gh`. `--check`
    re-reads their files and is the human's tool; this is CI's.

    IT IS DRIVEN PER TOKEN AND NOT PER DISTINCT VALUE, and that distinction is the whole
    check. An earlier version walked the value-keyed `conversions` map alone, which knows
    no token and no theme -- so it proved that `as_hex` still works and nothing more.
    Measured against that version: overwriting all 299 root literals with other
    converter-produced hexes failed NOTHING. Re-deriving each entry from its own raw
    catches that, and it catches nothing more -- an entry whose raw and hex move
    TOGETHER is consistent with itself, which is what a last-wins generator writes.
    What this check proves is that `as_hex` still produces what was stored; that the
    entry belongs to its token and theme is a different statement, held in part by
    test_the_two_themes_still_disagree_where_they_are_supposed_to.

    AND ONLY IN PART. Permuting the WHOLE table -- every entry moved onto another
    token, raw and hex together -- satisfies every offline assertion here, because
    the fixture is the only record of what Supabase declared and a permutation of it
    is self-consistent. Nothing offline can refuse that; `--check` re-reads their
    files and can. The limit is stated rather than papered over: this file proves
    the table is internally coherent and structurally intact, not that it was read
    from Supabase.

    It exists because two arithmetic defects shipped in a fixture that no test could
    contradict, and correcting them changed NO test outcome -- exactly the condition the
    reading-is-whole test above warns about, where a revert goes unnoticed:

      * `_hsl` rounded ties to EVEN. TWO conversions land on an exact tie -- backing
        three stored entries, since one of them is declared in two scopes -- and a CSS
        engine rounds ties AWAY FROM ZERO, so `hsl(206, 100%, 50%)` was stored as
        #0090ff where Chromium renders #0091ff.
      * 48 alpha-bearing declarations were stored as fully opaque. `hsla(0, 0%, 0%, 0)`
        became #000000 -- an assertion that Supabase publishes opaque black where they
        publish full transparency.

    Either regression now fails here rather than silently weakening the table.
    """
    from tools.read_supabase_tokens import as_hex

    checked, wrong = 0, []
    for scope, table in THEIR_LITERALS.items():
        for token, entry in table.items():
            assert isinstance(entry, dict) and "raw" in entry and "hex" in entry, (
                f"{scope} {token} stores {entry!r}, not a raw/hex pair, so it cannot be "
                f"re-derived. Regenerate with tools/read_supabase_tokens.py."
            )
            checked += 1
            produced = as_hex(entry["raw"])
            if produced != entry["hex"]:
                wrong.append((scope, token, entry["raw"], entry["hex"], produced))

    assert checked, "the table is empty, so this check passed over nothing"
    assert not wrong, (
        f"{len(wrong)} of {checked} stored literals are not what "
        f"tools/read_supabase_tokens.py now produces from the raw declaration recorded "
        f"beside them, so the fixture is stale against its own generator. First few "
        f"(scope, token, raw, stored, produced): {wrong[:3]}. Run "
        f"`python tools/read_supabase_tokens.py` and re-check every marker against it."
    )

    conversions = UPSTREAM.get("conversions")
    assert conversions, (
        "the fixture records no `conversions` map, so the declarations in names-only "
        "files -- which reach no table -- are re-derived by nothing. Regenerate it."
    )
    drifted = {raw: (stored, as_hex(raw)) for raw, stored in conversions.items()
               if as_hex(raw) != stored}
    assert not drifted, (
        f"{len(drifted)} of {len(conversions)} recorded conversions no longer reproduce. "
        f"First few (raw: stored -> produced): {dict(list(drifted.items())[:5])}."
    )


def test_every_published_literal_came_through_that_converter():
    """The conversions map has to COVER the table, or the check above proves nothing.

    A generator that stopped recording conversions -- or recorded a handful -- would leave
    the test above green over an empty or partial map while the literals it is supposed to
    guard went unchecked.
    """
    produced = set(UPSTREAM["conversions"].values())
    stored = {entry["hex"] for scope in THEIR_LITERALS.values()
              for entry in scope.values()}
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


def test_no_value_quietly_starts_being_checked_either():
    """The other direction, which the parametrized test above cannot express.

    Parametrizing over MARKED_VALUES asserts only that each pinned pair is still marked --
    a SUBSET check. Adding a marker to a declaration that had none simply adds a case and
    passes, which is what the test above claimed to prevent and did not: writing
    `/* --accent light derived */` onto `--chip` took the suite from 77 green to 78 green.

    That direction is the live one. #1040 answered #1016: no marker is added now, so the 18
    declarations that name a Supabase token and carry no word stay unmarked, and are
    listed in UNMARKED_COLOURS below. This equality is what forces a marker added later
    through a review rather than letting it arrive.
    """
    marked = {(m[0], m[1]) for m in ALL}
    assert marked == MARKED_VALUES, (
        f"design/tokens.css and MARKED_VALUES disagree about which values carry a licence "
        f"statement.\n"
        f"  newly marked, not pinned here: {sorted(marked - MARKED_VALUES)}\n"
        f"  pinned here, no longer marked: {sorted(MARKED_VALUES - marked)}\n"
        f"A new marker is a new statement in the Apache 4(b) record; add it to "
        f"MARKED_VALUES in the same change that writes it, and say so in the PR."
    )


# EVERY COLOUR LITERAL IN THE LIGHT AND DARK BLOCKS EITHER SAYS WHOSE IT IS OR IS NAMED
# HERE (#698). #1040 kept the Apache 4(b) record as it stands, so none of these gains a
# marker now, and ruled that the next colour cannot arrive without one. So the list only
# shrinks: #702 retires --red-hover and the dark --accent-active, and #1053 the dark
# --control-hover.
#
# A colour literal is a hex or a colour function (`rgb()`, `oklch()` and the rest), not a
# `color-mix()` or `var()` of other tokens, which carry their own statement. A CSS colour
# name (`white`) is not read; the file declares none today. "Says whose it
# is" means a marker the tests above verify, and they read markers on hex values only, so
# an `rgb()` with a marker word in its note is still listed here rather than trusted.
UNMARKED_COLOURS = frozenset({
    ("light", "--bg"), ("light", "--surface"), ("light", "--surface-subtle"),
    ("light", "--surface-raised"), ("light", "--line"), ("light", "--line-strong"),
    ("light", "--text"), ("light", "--muted"), ("light", "--text-subtle"), ("light", "--chip"),
    ("light", "--accent-contrast"), ("light", "--amber"), ("light", "--amber-ink"),
    ("light", "--red-hover"), ("light", "--shadow-color"), ("light", "--overlay"),
    ("dark", "--bg"), ("dark", "--surface"), ("dark", "--surface-subtle"),
    ("dark", "--surface-raised"), ("dark", "--line"), ("dark", "--line-strong"),
    ("dark", "--text"), ("dark", "--muted"), ("dark", "--text-subtle"), ("dark", "--chip"),
    ("dark", "--accent-active"), ("dark", "--red-hover"), ("dark", "--control-hover"),
    ("dark", "--shadow-color"),
})

# Google publishes these, test_the_google_button_follows_googles_rules.py pins all six
# values, and Google's guidelines govern the button (docs/DESIGN-SYSTEM-SOURCES.md, the gap
# table). They are Google's statement, not a gap in Supabase's.
GOOGLES_COLOURS = frozenset({"--google-btn-bg", "--google-btn-stroke", "--google-btn-text"})

COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(", re.I)
DECLARATION = re.compile(r"^[ \t]*(--[a-z0-9-]+)[ \t]*:[ \t]*([^;]+);", re.M)


def _colours_saying_nothing() -> set[tuple[str, str]]:
    """(theme, token) for each colour literal in the light and dark blocks that no verified
    marker covers.

    The device-dark block is left out: test_both_dark_blocks_agree pins it to the explicit
    dark block, so a colour arriving there arrives in both. Declarations are read with the
    comment bodies blanked, so a declaration quoted inside a comment is never counted.
    """
    marked = {(m[0], m[1]) for m in ALL}
    found = set()
    for (theme, pattern), (_, block) in zip(BLOCKS, _blocks()):
        if pattern.startswith(":root:not"):
            continue
        for match in DECLARATION.finditer(_without_comment_bodies(block)):
            token, value = match.group(1), match.group(2)
            if token in GOOGLES_COLOURS or not COLOUR_LITERAL.search(value):
                continue
            if (theme, token) not in marked:
                found.add((theme, token))
    return found


def test_no_colour_arrives_without_saying_whose_it_is():
    found = _colours_saying_nothing()
    assert found == UNMARKED_COLOURS, (
        f"design/tokens.css and UNMARKED_COLOURS disagree about which colours carry no "
        f"licence statement.\n"
        f"  unmarked and not listed: {sorted(found - UNMARKED_COLOURS)}\n"
        f"  listed and no longer an unmarked colour: {sorted(UNMARKED_COLOURS - found)}\n"
        f"A new colour says whose it is: `PUBLISHED` or `derived` naming the Supabase token "
        f"(#1040). One that is retired or gains a marker leaves this list in the same change."
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


def test_the_fixture_was_read_under_the_scope_map_the_tool_declares():
    """WHICH theme a file's literals are admitted into is a licence decision.

    `SOURCES` maps nine of its thirteen files to `None` -- names only -- and the reason is
    stated in the tool: admitting the classic-dark themes' values into the dark table would
    let a marker cite a value from a dark this product does not ship and pass. That was
    prose and nothing enforced it, so narrowing `SOURCES`, or flipping a file's scope, left
    every assertion here green. `files_declaring_nothing` already had this treatment; the
    map itself did not.
    """
    from tools.read_supabase_tokens import SOURCES

    recorded = UPSTREAM.get("scopes")
    assert recorded, (
        "the fixture records no `scopes` map, so nothing says which theme each file's "
        "literals were admitted into. Regenerate with tools/read_supabase_tokens.py."
    )
    declared = dict(sorted(SOURCES.items()))
    disagreed = sorted(set(recorded) | set(declared))
    differing = [(path, recorded.get(path, "<absent>"), declared.get(path, "<absent>"))
                 for path in disagreed if recorded.get(path) != declared.get(path)]
    assert not differing, (
        f"the fixture was read under a different source map than the tool now declares. "
        f"(file, in fixture, in SOURCES): {differing}. Which theme a file's literals are "
        f"admitted into decides whether a marker may cite a value from a theme this "
        f"product does not ship; regenerate and re-check every marker against the result."
    )
    assert UPSTREAM["files_read"] == sorted(SOURCES), (
        f"the fixture lists {len(UPSTREAM['files_read'])} files read and the tool declares "
        f"{len(SOURCES)}. A narrowed source map is how the first version of this fixture "
        f"came to hold a fraction of their literals."
    )


def test_a_names_only_source_never_reaches_a_theme_table():
    """The `None` scope has to survive the selector, and once it did not.

    `block_scope` promoted a names-only file to "dark" whenever its SELECTOR contained the
    substring, which both classic themes' do -- `[data-theme='classic-dark'], .classic-dark`.
    Their values were written into the dark table on top of the dark this product ships.
    It passed only because the later of the two happens to be byte-identical to it.

    Driven with synthetic input, because the real sources cannot show it: today the two
    files agree with `themes/dark.css`, so the promotion is invisible in the fixture.
    """
    from tools.read_supabase_tokens import read_declarations

    body = (
        "[data-theme='classic-dark'], .classic-dark {\n"
        "  --brand-default: #111111;\n"
        "}\n"
    )
    names, literals, conversions, _declared = read_declarations(body, scope=None)

    assert "--brand-default" in names, (
        "a names-only source must still contribute its NAMES -- that is what it is for"
    )
    assert conversions.get("#111111") == "#111111", (
        "a names-only source's conversions are still recorded, so the converter is "
        "checked over them"
    )
    assert literals == {"light": {}, "dark": {}, "root": {}}, (
        f"a names-only source put values into a theme table: {literals}. A selector that "
        f"merely CONTAINS 'dark' promoted `None`, which is how the classic themes came to "
        f"overwrite the dark this product ships."
    )



def test_one_file_with_two_themes_lands_in_two_tables():
    """A FILE CAN CARRY MORE THAN ONE THEME, and reading it linearly loses one.

    colors.css declares all 204 of its names twice -- once under `:root` and once under
    `[data-theme*='dark']` -- with 185 of the pairs differing. A last-wins scan stored the
    DARK value for every one of them and dropped all 185 light values, which is how a
    correct light marker came to be failed with Supabase's dark number quoted back at it.

    DRIVEN WITH SYNTHETIC INPUT, because the fixture cannot show it: `block_scope = scope`
    -- dropping the per-block rule entirely -- left the whole suite green, and so did
    returning a single block from `_selector_blocks`. Neither is visible in a reading where
    the two blocks happen to be consistent.
    """
    from tools.read_supabase_tokens import read_declarations

    body = (
        ":root {\n"
        "  --brand-default: #222222;\n"
        "}\n"
        "[data-theme*='dark'] {\n"
        "  --brand-default: #333333;\n"
        "}\n"
    )
    _names, literals, _conversions, declared = read_declarations(body, scope="root")

    assert declared == 2, f"both declarations should be seen, saw {declared}"
    assert literals["root"].get("--brand-default", {}).get("hex") == "#222222", (
        f"the light/root value was lost or overwritten by the dark block: "
        f"{literals['root']}"
    )
    assert literals["dark"].get("--brand-default", {}).get("hex") == "#333333", (
        f"the dark block's value did not reach the dark table: {literals['dark']}"
    )


def test_as_hex_reads_a_triple_with_and_without_deg():
    """`HSL_TRIPLE` converts 106 of the 514 entries -- it is not a latent path.

    An earlier comment called the whole branch latent, and nothing drove either spelling:
    undoing the optional `deg` on the triple, or on the function form, left the suite green.
    Only the deg-less spelling is latent, and it is driven here so it cannot rot.
    """
    from tools.read_supabase_tokens import as_hex

    assert as_hex("14deg 80.4% 58%") == as_hex("14 80.4% 58%"), (
        "the two spellings of one triple convert differently, so requiring `deg` silently "
        "dropped the bare CSS Color 4 form"
    )
    assert as_hex("14deg 80.4% 58%") == "#ea663e", as_hex("14deg 80.4% 58%")
    assert as_hex("hsl(206, 100%, 50%)") == as_hex("hsl(206deg 100% 50%)"), (
        "the function form's optional `deg` changed the value"
    )


def test_alpha_is_read_in_both_spellings_and_clamped():
    """`_alpha_byte` parses a percent and clamps, and no real value exercises either.

    All 60 alphas at the pinned commit are decimals in range, so dropping the `/ 100` or
    the clamp left the suite green. `hsl(0 0% 0% / 50%)` is legal CSS their sources could
    adopt at the next pin.
    """
    from tools.read_supabase_tokens import _alpha_byte, as_hex

    assert _alpha_byte("0.5") == _alpha_byte("50%") == 128, (
        f"the percent spelling is read as a fraction: "
        f"{_alpha_byte('0.5')} vs {_alpha_byte('50%')}"
    )
    assert _alpha_byte("0") == 0 and _alpha_byte("0%") == 0
    assert _alpha_byte("1") == _alpha_byte("100%") == 255
    assert _alpha_byte("1.5") == 255 and _alpha_byte("-0.5") == 0, (
        "an alpha outside 0-1 was not clamped, and a byte outside 0-255 renders as a "
        "plausible-looking hex rather than failing"
    )
    assert as_hex("hsla(0, 0%, 0%, 0)") == "#00000000", (
        "full transparency was recorded as opaque black"
    )
    assert as_hex("hsl(0 0% 0% / 50%)") == "#00000080", (
        f"the slash-and-percent alpha form was misread: {as_hex('hsl(0 0% 0% / 50%)')}"
    )


def test_a_channel_outside_a_byte_fails_the_parse():
    """`%02x` pads and never truncates, so an out-of-range channel renders as a colour.

    `hsl(0, 100%, 110%)` would reach `_channel` at 306 and `"%02x" % 306` is `"132"`,
    producing `#ff132132` -- a well-formed eight-digit hex the marker regex accepts and
    the table would store as a colour they publish. A browser renders that input #ffffff.
    No declaration at the pinned commit exceeds 100%, so nothing but this drives it.
    """
    from tools.read_supabase_tokens import _channel

    # A ValueError and NOT an AssertionError: PYTHONOPTIMIZE strips asserts, and
    # issue 833 is open against a guard that goes green under -O for exactly that.
    with pytest.raises(ValueError):
        _channel(306.0)
    with pytest.raises(ValueError):
        _channel(-1.0)
    assert _channel(0.0) == 0 and _channel(255.0) == 255, (
        "the guard rejected a channel that is in range"
    )



def test_the_two_themes_still_disagree_where_they_are_supposed_to():
    """Re-deriving each entry proves `as_hex`, NOT that the entry is Supabase's.

    `as_hex(entry["raw"]) == entry["hex"]` is a function of `raw` alone, so an entry whose
    raw and hex move TOGETHER is invisible to it -- which is exactly what a last-wins
    generator writes. Measured against the version that had only that check: replacing all
    299 root entries with their dark counterparts, pair and all, left the suite green, and
    so did shifting every root entry onto the next token. The claim that both failed was
    written from a mutation that moved the hex alone, leaving a pair no generator can
    produce.

    THIS IS THE STRUCTURAL FACT THAT CANNOT SURVIVE EITHER. colors.css declares 199 of its
    tokens in both a `:root` and a dark block and the two disagree on 185 of them. A
    last-wins scan collapses that to zero; a shuffled table collapses it too, because the
    dark value would have to land on the same token by chance.
    """
    shared = set(THEIR_LITERALS["root"]) & set(THEIR_LITERALS["dark"])
    differing = [token for token in shared
                 if THEIR_LITERALS["root"][token]["hex"]
                 != THEIR_LITERALS["dark"][token]["hex"]]

    assert len(shared) >= 190, (
        f"only {len(shared)} tokens are declared in both the root and dark tables; "
        f"colors.css declares 199 of them twice, so a number this low means one of its "
        f"two blocks was not read."
    )
    assert len(differing) >= 180, (
        f"{len(differing)} of {len(shared)} tokens shared between the root and dark "
        f"tables still differ, against 185 at the pinned commit. A collapse here means "
        f"one theme's values were written over the other's -- the defect the second "
        f"commit on this branch fixed -- and re-deriving each entry from its own raw "
        f"cannot see it, because the raw moves with the hex."
    )


def test_a_marker_on_a_value_the_parser_cannot_read_is_not_silently_skipped():
    """`MARKED` matches a hex value only, and a marker word is what opts a value in.

    So a licence statement written on a value in any OTHER notation is not checked and not
    counted. Measured: adding `--smoke: hsl(153.1 60.2% 52.7%);` with a `PUBLISHED` note
    left the whole suite green, and the equality control could not see it either, because
    the parser never produced a pair for it to compare.

    That is the natural shape for such a claim -- Supabase publishes hsl triples, and
    `as_hex` exists precisely to say a triple is the same value in another notation. 96 of
    the 179 declarations inside the three guarded blocks carry a value `MARKED` cannot
    match, 39 of them colours.
    """
    declaration = re.compile(r"^[ \t]*--[a-z0-9-]+[ \t]*:")
    unreadable = []
    for theme, block in _blocks():
        for line in block.splitlines():
            if "/*" not in line or not declaration.match(line):
                continue
            note = line.split("/*", 1)[1]
            if "PUBLISHED" not in note and "derived" not in note:
                continue
            if not MARKED.match(line):
                unreadable.append(f"{theme}: {line.strip()}")

    assert not unreadable, (
        "{} declaration(s) carry a licence statement on a value this guard cannot parse, "
        "so the statement is recorded and checked by nothing: {}. Either write the value "
        "as hex, or widen MARKED and compare through as_hex.".format(
            len(unreadable), unreadable[:5])
    )


def test_a_note_cannot_claim_the_comment_on_the_next_line():
    """Horizontal whitespace only between a declaration and its note, and nothing drove it.

    A `\\s` there matches newlines, which let a declaration bind to the NEXT comment in the
    file once its own was stripped -- inventing a marker for a token that carries none. The
    file docstring calls this one of three things learned the hard way, and swapping all
    five character classes back left the whole suite green, because today's file happens
    not to have the shape.
    """
    across_a_newline = "\n".join([
        "  --red-hover: #8e332f;",
        "  /* brand-default light   PUBLISHED */",
        "",
    ])
    assert not MARKED.search(across_a_newline), (
        "a declaration claimed the comment on the FOLLOWING line as its marker, which "
        "invents a licence statement for a token that carries none"
    )

    on_its_own_line = "  --red-hover: #8e332f; /* brand-default light   PUBLISHED */\n"
    found = MARKED.search(on_its_own_line)
    assert found and found.group(1) == "--red-hover", (
        "the parser stopped reading a marker written on its own declaration's line: "
        "{}".format(found)
    )


def test_the_marker_and_theme_words_are_removed_whole():
    """107 of their 648 names carry "light" or "dark" INSIDE them.

    An earlier version removed those words as substrings, which turned
    `--colors-gray-light-900` into `--colors-gray--900` -- a name they do not declare, so
    a truthful marker failed. The docstring records the regression; nothing drove it, and
    substring removal left the suite green.
    """
    assert _named_token("--colors-gray-dark-100 dark PUBLISHED") == "--colors-gray-dark-100", (
        "the theme word was removed from inside the token's own name"
    )
    assert _named_token("--color-foreground-light light derived") == "--color-foreground-light", (
        "the theme word was removed from inside the token's own name"
    )
    assert _named_token("--brand-default/80 flat derived") == "--brand-default", (
        "an operation described after the token changed which token was named"
    )
    for name in ("--colors-gray-dark-100", "--color-foreground-light"):
        assert name in THEIR_NAMES, (
            f"this guard assumes {name} is one of theirs; if they stopped declaring it, "
            f"pick another name carrying a theme word from the fixture"
        )


def test_a_block_is_scoped_by_its_own_selector_whichever_order_they_come_in():
    """`_selector_blocks` takes each block's selector from the text before its brace.

    Nothing drove that: the two-theme test puts the dark block SECOND, where a correct
    implementation and one that loses the selector agree. With the dark block FIRST they
    diverge -- a literal moves out of the light table and into dark, and a marker reading
    it then fails with the wrong theme's value quoted back.
    """
    from tools.read_supabase_tokens import _selector_blocks, read_declarations

    dark_first = (
        "[data-theme*='dark'] {\
  --b: #111111;\
}\
"
        ":root {\
  --b: #222222;\
}\
"
    )
    selectors = [selector for selector, _ in _selector_blocks(dark_first)]
    assert selectors == ["[data-theme*='dark']", ":root"], (
        f"a block's selector is not the text before its own brace: {selectors}"
    )

    _names, literals, _conversions, _declared = read_declarations(dark_first, scope="light")
    assert literals["light"].get("--b", {}).get("hex") == "#222222", (
        f"the :root block's value did not reach the file's own scope: {literals['light']}"
    )
    assert literals["dark"].get("--b", {}).get("hex") == "#111111", (
        f"the dark block's value did not reach the dark table: {literals['dark']}"
    )


def test_a_block_that_names_a_theme_we_do_not_ship_gives_names_only():
    """Their classic themes are a second and third dark, and this product renders neither.

    Guarding only the names-only scope left the door open at every SCOPED file: measured,
    a `classic-dark` block inside a file mapped to `root` or `light` still landed its
    values in the dark table. Falling back to the file's own scope is not safe either --
    that would overwrite the true root values with a theme nobody renders.
    """
    from tools.read_supabase_tokens import read_declarations

    classic = "[data-theme='classic-dark'], .classic-dark {\
  --brand-default: #111111;\
}\
"
    for scope in ("root", "light", "dark", None):
        names, literals, conversions, _declared = read_declarations(classic, scope=scope)
        assert names == {"--brand-default"}, (
            f"a names-only block stopped contributing its names at scope={scope}"
        )
        assert conversions.get("#111111") == "#111111", (
            f"a names-only block stopped contributing its conversions at scope={scope}"
        )
        assert all(not table for table in literals.values()), (
            f"at scope={scope} a theme this product does not ship put values into "
            f"{ {k: v for k, v in literals.items() if v} }. A marker could then cite a "
            f"value from a dark that is never rendered and pass."
        )

def test_a_body_with_no_block_is_read_as_one():
    """`_selector_blocks` falls back to a single unnamed block, and nothing drove it.

    Removing `or [("", body)]` left the whole suite green: every file at the pinned commit
    opens a brace, so the fallback is never taken. A source that stops wrapping its
    declarations -- or a fetch that returns a fragment -- would silently contribute
    nothing at all, which reads exactly like a file that declares nothing.
    """
    from tools.read_supabase_tokens import _selector_blocks, read_declarations

    bare = "  --brand-default: #111111;\n  --brand-200: #222222;\n"
    blocks = _selector_blocks(bare)
    assert len(blocks) == 1 and blocks[0][0] == "", (
        "a body with no top-level block was not read as one unnamed block: {}".format(
            [selector for selector, _ in blocks])
    )

    names, literals, _conversions, declared = read_declarations(bare, scope="root")
    assert declared == 2 and names == {"--brand-default", "--brand-200"}, (
        "a brace-less body contributed {} declaration(s) and {}".format(declared, names)
    )
    assert literals["root"].get("--brand-default", {}).get("hex") == "#111111", (
        "a brace-less body reached no table, which is indistinguishable from a file that "
        "declares nothing: {}".format(literals)
    )


def test_the_underscore_names_are_in_the_table():
    """`_` is a legal custom-property character and they use it in 11 names.

    Excluding it from `DECLARATION` hid all eleven, and the name check can only reject
    what it cannot find -- so a `derived` marker could have invented any of them without
    being caught. Undoing the character class left the suite green: the fixture is not
    regenerated by a test run, so nothing offline noticed. Naming them here does.
    """
    underscored = sorted(name for name in THEIR_NAMES if "_" in name)
    assert len(underscored) >= 11, (
        "the fixture holds {} names carrying an underscore, against 11 at the pinned "
        "commit: {}. Either they stopped declaring them, or DECLARATION stopped reading "
        "the character -- and the second hides 11 names a marker could invent.".format(
            len(underscored), underscored)
    )
    for name in ("--_base", "--color-code_block-1"):
        assert name in THEIR_NAMES, (
            "{} is one of theirs and is no longer in the table; DECLARATION's character "
            "class is the first thing to check".format(name)
        )

    # AND THE PARSER ITSELF, because the fixture is not regenerated by a test run: undoing
    # the character class leaves the stored names in place and nothing else notices.
    from tools.read_supabase_tokens import read_declarations

    body = "\n".join([
        ":root {",
        "  --_base: #111111;",
        "  --color-code_block-1: #222222;",
        "}",
        "",
    ])
    found, _literals, _conversions, declared = read_declarations(body, scope="root")
    assert declared == 2 and found == {"--_base", "--color-code_block-1"}, (
        "the declaration parser stopped reading underscored names: it saw {} "
        "declaration(s) and {}".format(declared, found)
    )


def test_the_notice_still_delegates_the_record_to_these_markers():
    """The markers are a licence statement only while the notice says they are."""
    assert "RECORDED AT EACH VALUE in design/tokens.css" in NOTICE.read_text(encoding="utf-8"), (
        "design/supabase.NOTICE.txt no longer delegates the per-value provenance record "
        "to design/tokens.css. If the notice states provenance itself now, this guard "
        "should be checking the notice instead."
    )
