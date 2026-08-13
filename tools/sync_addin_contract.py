"""Generate the Console's vocabulary module from the add-in's contract.

`contract/addin-contract.json` says what mbiXaddin's C# accepts. This turns it
into `extension/addin-vocabulary.js`, which the Console imports.

WHY GENERATE RATHER THAN TYPE. The first version of that module was typed by
hand from a reading of ~350 .cs files. It was correct on the day it was written
and silently wrong the moment anyone added an enum value, because nothing
anywhere compared the two. A generated file with a `--check` gate cannot drift:
editing it by hand fails the build, and so does letting the JSON move without
regenerating.

WHAT THIS DELIBERATELY DOES NOT GENERATE. `extension/addin-contract.js` stays
hand-written, because it holds what no generator can know — that a blank
IS_ACTIVE means the row is LIVE, that an unrecognised value means the same
thing and says nothing, that the same column name means the opposite one sheet
away. Those came from reading behaviour, not from reflecting over types. Mixing
the two in one file would mean either the generator erases the reasoning or the
reasoning blocks the generator.

Usage:
    python tools/sync_addin_contract.py
    python tools/sync_addin_contract.py --check
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contract" / "addin-contract.json"
GENERATED = ROOT / "extension" / "addin-vocabulary.js"

#: Emitted in the order given rather than the order the JSON happens to carry,
#: so a reordered source file does not produce a spurious diff.
ORDER = [
    ("4.DataMap", ["SOURCE_TYPES", "MATCH_MODES", "CONTEXT_EXPRESSIONS",
                   "TRANSFORMS", "PROCESS_CONFIG_KEYS", "MAP_STRATEGIES",
                   "ROW_FILTER_OPERATORS"]),
    ("2.SchemaRule", ["SEMANTIC_ROLES", "REPEATABLE_ROLES", "DATA_TYPES",
                      "UX_CONFIG_KEYS", "LOGIC_CONFIG_KEYS"]),
    ("1.TableDefinition and 3.DataSource",
     ["ENTITY_TYPES", "STORAGE_STRATEGIES", "STORAGE_STRATEGY_ALIASES",
      "LICENSE_TIERS", "VIEW_MODES", "BUSINESS_DOMAINS", "CONTEXT_PROPS_KEYS",
      "CONTEXT_SOURCE_TYPES", "SYNC_FREQUENCIES"]),
    ("6.RibbonControls", ["MENU_LAYOUTS", "CLICKABLE_ACTIONS", "MENU_ACTIONS"]),
    ("booleans, severities and the add-in's own error codes",
     ["TRUE_SPELLINGS", "FALSE_SPELLINGS", "SEVERITIES", "ERROR_CODES"]),
]


def _js(value: object) -> str:
    """A JS literal. json.dumps is exact for these shapes and keeps Arabic as
    Arabic — `ensure_ascii` would emit escapes nobody can read in a review."""
    return json.dumps(value, ensure_ascii=False)


def render(contract: dict) -> str:
    vocabularies = contract["vocabularies"]
    unknown = sorted(set(vocabularies) - {n for _, names in ORDER for n in names})

    lines = [
        "// GENERATED — do not edit. Run `python tools/sync_addin_contract.py`.",
        "//",
        "// The source is contract/addin-contract.json, which describes what",
        "// mbiXaddin's C# accepts. A test fails if this file and that one",
        "// disagree, so a hand edit here is caught rather than shipped.",
        "//",
        f"// contract version {contract['contractVersion']}"
        f" · behaviour version {contract['behaviourVersion']}"
        f" · read {contract['readOn']} from {contract['readFrom']}",
        "",
        f"export const CONTRACT_VERSION = {contract['contractVersion']};",
        f"export const BEHAVIOUR_VERSION = {contract['behaviourVersion']};",
        f"export const CONTRACT_READ_ON = {_js(contract['readOn'])};",
        "",
    ]

    for heading, names in ORDER:
        lines.append(f"// ---- {heading} " + "-" * max(3, 68 - len(heading)))
        for name in names:
            if name not in vocabularies:
                continue
            lines.append(f"export const {name} = {_js(vocabularies[name])};")
        lines.append("")

    if unknown:
        # A new vocabulary must still reach the module. Emitting it unsorted
        # under a named heading is better than dropping it silently, and the
        # heading tells whoever added it where it should really go.
        lines.append("// ---- not yet placed in a section " + "-" * 43)
        for name in unknown:
            lines.append(f"export const {name} = {_js(vocabularies[name])};")
        lines.append("")

    lines.append("// ---- the sheets, and the gids compiled into the add-in " + "-" * 22)
    lines.append("export const SHEETS = {")
    for tab, spec in contract["sheets"].items():
        lines.append(f"  {_js(tab)}: {{")
        lines.append(f"    gid: {_js(spec['gid'])},")
        lines.append(f"    key: {_js(spec['key'])},")
        lines.append(f"    registryCritical: {_js(spec['registryCritical'])},")
        lines.append(f"    columns: {_js(spec['columns'])},")
        lines.append("  },")
    lines.append("};")
    lines.append("")

    lines.append("// ---- constants " + "-" * 61)
    for name, value in contract["constants"].items():
        lines.append(f"export const {name} = {_js(value)};")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="exit non-zero if the generated file is not what it would be now")
    arguments = parser.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    wanted = render(contract)

    if arguments.check:
        have = GENERATED.read_text(encoding="utf-8") if GENERATED.exists() else ""
        if have != wanted:
            print(f"{GENERATED.relative_to(ROOT)} is not what "
                  f"{CONTRACT.relative_to(ROOT)} would produce.")
            print("Run: python tools/sync_addin_contract.py")
            return 1
        print(f"{GENERATED.relative_to(ROOT)} matches the contract.")
        return 0

    GENERATED.write_text(wanted, encoding="utf-8")
    print(f"wrote {GENERATED.relative_to(ROOT)} "
          f"(contract {contract['contractVersion']}, "
          f"behaviour {contract['behaviourVersion']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
