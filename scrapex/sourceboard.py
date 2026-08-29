"""Every source this installation has, in one list, whatever registry it lives in.

WHY THIS EXISTS. He asked «اى الجديد واى الى خلص» — which is new and which is
finished — and measured 2026-08-21, **no command could answer it**: eighteen
subcommands and not one lists the sources. Worse, there was nowhere for the answer to
come from, because there were TWO DATABASE REGISTRIES and a source landed in one or the
other by accident of which pipeline collected it — `source_site` for the price path,
`site_profile` for everything else.

`R-62` merged them on 2026-08-29 (migration `0014`), so the database now holds ONE:

    source_site, declared in sources.yaml    ARAMCO_FUEL_SA, HEIDELBERG_EG, MADAR, ...
    source_site, declared nowhere else       muqawil_org   <- not in sources.yaml at all

What remains is not two registries but a registry and a MANIFEST: `sources.yaml` is where
price sources are declared, and the twelve rows mirror it. A source with no manifest entry
is now an ordinary row rather than a second kind of thing.

`R-32` settles that price is one **category** among several and not the whole tool;
`REQ-25` is the single registry. **This module is not that merge.** Merging
`source_site` into `source_site` is a migration over live rows and the owner's
decision, and it is recorded as open. What this does is give him the ANSWER now, from
a read-only view over both — so the query exists before the schema changes, and the
merge can be judged on its own merits rather than being forced by a missing report.

THE STATE VOCABULARY EXISTS TWICE, WHICH IS THE SAME DEFECT IN WORDS. The products
side says `active: true/false` plus `family: TBD-probe`; the contractors side says
`lifecycle IN ('draft','active','paused')`. Neither is wrong and they do not agree, so
this maps both onto one vocabulary and says, per row, which registry it came from.

    registered   the source is on the list and has NO collector yet -- his
                 «يحفظ فقط فى قائمة مصادر حتى ياتى دوره». Only the manifest can say
                 this today: it is `family: TBD-probe`, which validation refuses to
                 let go active
    built        a collector exists; scheduled runs are off
    active       a collector exists and scheduled runs are on
    paused       deliberately stopped (warehouse side only)

IT MUST WORK WITH NO DATABASE AT ALL. A new user has an empty installation — `R-23`
says that is the normal first-run state — so the warehouse half is skipped when there
is no file, rather than failing. A report that only works once you already have data
is not a report a new user can use.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import MANIFEST_FILE, load_manifest
from .vocab import ConnectorFamily, SourceCategory

#: One vocabulary for every source, declared in the manifest or not. Ordered by how
#: far along a source is, so
#: sorting a board sorts by progress.
STATES = ("registered", "built", "active", "paused")


@dataclass(frozen=True)
class Source:
    """One source, as the board reports it."""

    key: str
    category: SourceCategory
    name: str
    base_url: str
    #: The family for a manifest source; the crawl scope for a warehouse one. Named
    #: for what it answers -- "what collects this" -- rather than for either
    #: registry's column, because the two do not share a column.
    collector: str
    state: str
    #: Which registry this row came from, so the two-registry split is VISIBLE in the
    #: output rather than smoothed over. It is the thing `REQ-25` exists to remove.
    registry: str

    def __str__(self) -> str:
        return (f"{self.state:<11} {self.category.value:<12} {self.key:<18} "
                f"{self.collector:<26} {self.registry}")


def _manifest_state(entry) -> str:
    """`family: TBD-probe` is the only way any registry can say "no collector yet".

    It is not a placeholder that happens to be useful: `SourceEntry` validation
    refuses `active: true` while the family is TBD-probe -- *"A source that has not
    been probed cannot be active"* -- so the manifest genuinely cannot mark such a
    source runnable, which is exactly the guarantee his request asks for.
    """
    if entry.family == ConnectorFamily.TBD_PROBE:
        return "registered"
    return "active" if entry.active else "built"


def from_manifest(manifest_file: Path | str = MANIFEST_FILE) -> tuple[Source, ...]:
    """The products side. Reads the contract, touches no database."""
    found = []
    for entry in load_manifest(manifest_file).sources:
        found.append(Source(
            key=entry.source_key,
            category=getattr(entry, "category", SourceCategory.PRODUCTS),
            name=entry.source_name or entry.source_key,
            base_url=entry.base_url,
            collector=entry.family.value,
            state=_manifest_state(entry),
            registry="manifest"))
    return tuple(found)


#: `source_site.lifecycle` -> the shared vocabulary. There is deliberately no
#: mapping onto "registered": the generic side has no way to say a site is listed
#: with no collector, because a `source_site` row is only written once something is
#: crawling it. That asymmetry is a finding, not a rounding error, and `REQ-25` is
#: where it gets fixed.
_LIFECYCLE = {"draft": "built", "active": "active", "paused": "paused"}


def from_warehouse(conn: sqlite3.Connection) -> tuple[Source, ...]:
    """The generic side. Every `source_site` row, with its datasets counted."""
    rows = conn.execute(
        "SELECT p.source_key AS site_key, p.source_name AS display_name, p.base_url, "
        "       p.lifecycle, p.crawl_scope, "
        "       (SELECT COUNT(*) FROM dataset_definition AS d "
        "         WHERE d.source_id = p.source_id) AS datasets "
        "  FROM source_site AS p WHERE p.valid_to IS NULL "
        " ORDER BY p.source_key").fetchall()
    found = []
    for row in rows:
        datasets = int(row["datasets"] or 0)
        found.append(Source(
            key=str(row["site_key"]),
            # EVERY source_site ROW IS A CONTRACTOR SOURCE TODAY, and saying so is
            # honest rather than convenient: the column does not exist yet, muqawil
            # is the only row, and inventing a guess per row would be worse than
            # naming the one fact that is true. `REQ-25` puts the category on the
            # row and this line goes away.
            category=SourceCategory.CONTRACTORS,
            name=str(row["display_name"] or row["site_key"]),
            base_url=str(row["base_url"] or ""),
            collector=f"{row['crawl_scope']} · {datasets} dataset(s)",
            state=_LIFECYCLE.get(str(row["lifecycle"]), str(row["lifecycle"])),
            registry="warehouse"))
    return tuple(found)


def board(conn: sqlite3.Connection | None = None,
          manifest_file: Path | str = MANIFEST_FILE,
          category: SourceCategory | None = None) -> tuple[Source, ...]:
    """Both registries as one list, sorted by category then key.

    `conn` is optional ON PURPOSE -- see the module docstring: a fresh
    installation has no warehouse, and the products half is a file.
    """
    found = list(from_manifest(manifest_file))
    if conn is not None:
        found.extend(from_warehouse(conn))
    if category is not None:
        found = [one for one in found if one.category == category]
    return tuple(sorted(found, key=lambda one: (one.category.value, one.key)))


def summary(sources: tuple[Source, ...]) -> dict[str, dict[str, int]]:
    """`{category: {state: count}}` -- his question reduced to a number per cell."""
    out: dict[str, dict[str, int]] = {}
    for one in sources:
        out.setdefault(one.category.value, {})[one.state] = (
            out.setdefault(one.category.value, {}).get(one.state, 0) + 1)
    return out
