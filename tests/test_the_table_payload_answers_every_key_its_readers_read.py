"""The table payload has two producers and three readers, and nothing bound them.

WHY THIS EXISTS. `scrapex/webui/static/grid.js` reads keys off the payload
unconditionally, and `dataset_table_payload`'s own comment states the consequence:
*"an absent key would be a crash where a false is a switch the page simply does not
offer."* So the contract is load-bearing. It was also entirely implicit:

  * TWO producers fill it -- `reports.table_payload` from `price_observation`, and
    `extract.service.dataset_table_payload` from `generic_record`.
  * THREE readers consume it -- `grid.js` on the engine page, and
    `extension/datatable.js` and `extension/data.js` in the panel.
  * NO TypedDict, no dataclass, no JSON schema, no FastAPI `response_model`. A
    repo-wide search for all four finds nothing, so the only thing describing the
    shape was prose.

WHAT WAS GUARDING IT, AND WHY THAT WAS NOT ENOUGH. One test:
`test_it_answers_every_key_the_grid_reads` in
`tests/test_a_dataset_is_a_table_like_any_other.py`. Its docstring says *"`grid.js`
reads these unconditionally"* and its list is a **literal typed into the test**. Two
consequences were measured before this file was written:

  * It asserts thirteen keys. `grid.js` reads ten. Three of the thirteen --
    `source_key`, `folded`, `tree` -- it never reads, so the docstring's claim is
    false for nearly a quarter of the list. (`folded` IS read, but by the panel, a
    reader that test never looks at.)
  * It reads nothing off disk, so **adding a new `payload.x` read to `grid.js`
    tomorrow fails no test at all.** The crash it exists to prevent is exactly the
    crash it cannot see.

That is the same failure `tests/test_the_documents_cite_what_they_claim.py` was built
for -- an assertion about a file, written by hand, drifting from the file -- and this
guard copies its answer: derive the expectation from the artefact instead of retyping
it. It also copies its TWO TIERS, for the same reason that file gives:

  * **Tier 1** is the crash direction and is mechanical: every key a reader reads,
    both producers must emit. Zero inference -- a regex over the readers, an `ast`
    walk over the producers -- and no database, so it cannot flake.
  * **Tier 2** is the opposite direction and is a LIST, because "nothing reads this"
    is a judgement rather than a defect. A key emitted for no reader is either dead
    weight or deliberate headroom, and which one it is has to be said out loud.
    Adding to `UNREAD_BY_EVERY_READER` is the intended cost.

WHY A REGEX OVER THE READERS RATHER THAN A JS PARSER. The three readers touch the
payload through exactly one idiom, `payload.key` or `payload?.key`, verified by
reading all three at 35962cc. A parser would be a dependency and a second thing to
keep true for one extra form nobody writes. If a reader ever destructures instead --
`const {rows} = payload` -- this guard goes BLIND rather than loud, so
`test_the_readers_still_use_the_idiom_this_guard_can_see` fails on that change and
sends the next session here.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

#: MARKED, and the gate that demanded it was right for this file specifically. Two
#: of the three readers are `extension/` sources, so without the mark this guard
#: would not run on an extension-only change -- which is precisely the change most
#: likely to add a `payload.x` read to `datatable.js` or `data.js`. It would have
#: been blind in the one scope it was written for.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]

#: Every file that reads the table payload. `grid.js` is the engine's page; the other
#: two are the panel's, and they are in this list because the plan that moves the
#: source page into the extension adds readers rather than replacing one -- so the
#: number of ways to drift goes UP, which is what makes deriving the contract worth a
#: file of its own.
READERS = (
    "scrapex/webui/static/grid.js",
    "extension/datatable.js",
    "extension/data.js",
)

#: Both producers, and the function in each that builds the payload.
PRODUCERS = (
    ("scrapex/reports.py", "table_payload"),
    ("scrapex/extract/service.py", "dataset_table_payload"),
)

#: Keys BOTH producers emit that NO reader reads. Every entry needs a reason.
#:
#: `source_key` -- the readers all learn the source another way: `grid.js` takes it
#: from the DOM (`const SOURCE = mount.dataset.source`), and the panel already knows
#: which source it asked about. Harmless, and useful when reading a payload by hand.
#:
#: `tree` -- genuinely dead. `reports.table_payload` computes it with `_tree_shape`
#: and `dataset_table_payload` hard-codes `{}`; `grid.js` has a `features.tree` but
#: that is a name collision, not a read of this key. Recorded rather than deleted:
#: removing a key from the contract while a third producer is being written is two
#: changes at once, and the owner's standing instruction is one step at a time.
UNREAD_BY_EVERY_READER = frozenset({"source_key", "tree"})

#: `payload.key` and `payload?.key`. Deliberately does NOT match `payload["key"]` --
#: no reader uses it, and matching it would invite the belief that this regex sees
#: every access when it sees one idiom. The companion test below is what keeps that
#: honest.
_READ = re.compile(r"payload\s*\??\s*\.\s*([A-Za-z_]\w*)")

#: A destructure of the payload would hide reads from `_READ` entirely.
_DESTRUCTURE = re.compile(r"(?:const|let|var)\s*\{[^}]*\}\s*=\s*payload\b")


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _keys_read(relative: str) -> set[str]:
    return set(_READ.findall(_text(relative)))


def _keys_emitted(relative: str, function: str) -> set[str]:
    """The keys of the payload dict literal `function` returns.

    Returns that are not dict literals are skipped -- `dataset_table_payload`'s
    `return None` on a catalogue miss is one -- and returns belonging to a NESTED
    function are skipped too, because `table_payload` defines a `tax_ref` helper
    inside itself and its return is not the payload.
    """
    tree = ast.parse(_text(relative))
    target = next(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.FunctionDef) and node.name == function), None)
    assert target is not None, f"{relative} no longer defines {function}()"

    nested = {inner for child in target.body for inner in ast.walk(child)
              if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
              and inner is not target}
    nested_returns = {ret for func in nested for ret in ast.walk(func)
                      if isinstance(ret, ast.Return)}

    literals = [node for node in ast.walk(target)
                if isinstance(node, ast.Return)
                and node not in nested_returns
                and isinstance(node.value, ast.Dict)]
    assert len(literals) == 1, (
        f"{relative}:{function}() returns {len(literals)} dict literals; this guard "
        "reads the payload off exactly one and cannot tell which is meant")
    payload = literals[0].value
    keys = {key.value for key in payload.keys if isinstance(key, ast.Constant)}
    assert len(keys) == len(payload.keys), (
        f"{relative}:{function}() builds a key dynamically; this guard can only "
        "read constant keys and would report a false absence")
    return keys


# ---- tier 1: the crash direction -------------------------------------------------

@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize(("module", "function"), PRODUCERS)
def test_every_key_a_reader_reads_is_emitted(reader: str, module: str, function: str):
    """A key read and not emitted is `undefined` at best and a crash at worst.

    Both producers are held to EVERY reader, not each to its own, because one
    endpoint answers from either of them: `/api/table/{key}` resolves the catalogue
    first and falls through to the price path, so a reader cannot know which
    producer filled the payload it was handed.
    """
    emitted = _keys_emitted(module, function)
    missing = sorted(_keys_read(reader) - emitted)

    assert not missing, (
        f"{reader} reads {missing} off the payload and {module}:{function}() does "
        f"not emit {'it' if len(missing) == 1 else 'them'}. Either emit the key or "
        f"stop reading it -- an absent key reaches the page as undefined.")


def test_the_two_producers_agree_on_the_whole_shape():
    """One page renders both, so a key on one path and not the other is a defect.

    This is the check that would have caught the shape drifting while a third
    producer -- the dataset record card -- is being written against it.
    """
    (price_module, price_fn), (data_module, data_fn) = PRODUCERS
    price = _keys_emitted(price_module, price_fn)
    dataset = _keys_emitted(data_module, data_fn)

    assert price == dataset, (
        f"the two producers disagree: only {price_fn}() emits "
        f"{sorted(price - dataset)}, only {data_fn}() emits "
        f"{sorted(dataset - price)}")


# ---- tier 2: the stated-out-loud direction ---------------------------------------

def test_a_key_no_reader_reads_is_listed_and_not_merely_present():
    """Emitted-and-unread is a decision. It has to be written down as one."""
    emitted = set.intersection(*(_keys_emitted(m, f) for m, f in PRODUCERS))
    read = set.union(*(_keys_read(reader) for reader in READERS))
    unread = emitted - read

    assert unread == set(UNREAD_BY_EVERY_READER), (
        "the emitted-but-unread set moved.\n"
        f"  now unread and NOT listed : {sorted(unread - UNREAD_BY_EVERY_READER)}\n"
        f"  listed and no longer unread: {sorted(UNREAD_BY_EVERY_READER - unread)}\n"
        "If a key stopped being read, say why it is still emitted. If one started "
        "being read, take it off the list.")


# ---- the guard's own assumption --------------------------------------------------

@pytest.mark.parametrize("reader", READERS)
def test_the_readers_still_use_the_idiom_this_guard_can_see(reader: str):
    """Destructuring the payload would make tier 1 silently see nothing.

    This is the test that fails LOUD instead, because a guard that has gone blind
    and a guard that has nothing to report look identical from the outside.
    """
    assert not _DESTRUCTURE.search(_text(reader)), (
        f"{reader} destructures the payload, and this file finds reads by matching "
        "`payload.key`. Teach `_READ` the new form -- or tier 1 is now asserting "
        "nothing about this reader.")


@pytest.mark.parametrize("reader", READERS)
def test_every_reader_actually_reads_the_payload(reader: str):
    """A reader that reads nothing means a stale path in READERS, not a clean bill."""
    assert _keys_read(reader), (
        f"{reader} reads no payload key. It was renamed, or it stopped being a "
        "reader -- either way READERS is out of date and tier 1 lost a surface.")
