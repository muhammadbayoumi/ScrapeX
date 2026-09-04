"""The one guarded way to advance an existing warehouse, for BOTH front doors.

WHY THIS MODULE EXISTS, AND IT IS NOT TIDINESS. `registry.ensure_ready`'s docstring states
the rule and names its single exception:

    "the protections spec 40 existed for are kept in the caller -- a backup first without
    exception, forward only, never over damage, and said out loud. Nothing else in the
    codebase may migrate an existing file."

`cli._upgrade_what_is_only_behind` kept all four. `native.upgrade_database` -- the panel's
«Upgrade database» button, and under `R-81` the only door the owner uses -- called
`registry.initialize()` bare: no backup, no BEHIND check, no refusal over damage, and
nothing said. On a 1.4 GB warehouse. That is `OP-128`'s sibling and it is `OP-127`.

WHY THE TWO PATHS DIVERGED, BECAUSE IT IS WHAT SHAPES THIS MODULE. The guarded version
PRINTS, and the native host writes framed messages to `sys.stdout.buffer` (`native.serve`).
A `print` reached from a native command injects unframed bytes into the protocol stream and
Chrome reads the next length prefix wrong. So the protections could not simply be CALLED
from there, and whoever wrote the escape hatch wrote a second, bare path instead.

SO THE RULE RETURNS WHAT IT DID INSTEAD OF SAYING IT. Each caller renders the outcome: the
CLI to stdout in the words it has always used, the native host into its JSON reply. That is
strictly better than moving code, because it finally gives the panel the FOURTH protection
it has never had -- *said out loud*, naming the backup by path -- on the surface he
actually presses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: What `registry.health()` reports for a database whose only fault is its version.
#: Spelled once here and imported by both callers, because a second spelling is a check
#: that silently stops matching -- `LESSONS` section 9, a search for one spelling of a
#: feature is not a measurement of the feature.
BEHIND = "Needs upgrade"

#: What it reports for a database BELOW this build's squashed baseline (`R-84`).
#: A different fault with a different remedy: there is no upgrade path to offer, so
#: the panel must not offer one. It is spelled here beside `BEHIND` for exactly the
#: same reason -- `native.startup_check` decides whether to show the "Upgrade
#: database" button by comparing against these strings.
#:
#: IT MIRRORS `_storage.html`'s WORDS for `storage.py`'s `too_old` -- "Older than
#: this engine's schema" -- because two surfaces already describe this state and the
#: owner should not have to work out that they are the same one. It drops the
#: possessive, and both reasons are mechanical rather than aesthetic:
#:
#:   - `/api/health` composes it as `f"{kind} {status.lower()}"` (`webui/app.py`),
#:     where "this engine's" would reach the panel as "engine older than this
#:     engine's schema".
#:   - `base.html` renders it through Jinja with autoescaping on, so an apostrophe
#:     arrives in the page as `&#39;` -- and a test that looked for the plain form
#:     would pass or fail for a reason that has nothing to do with the status.
TOO_OLD = "Older than the schema baseline"

def no_upgrade_path(version: int, baseline: int,
                    subject: str = "This warehouse") -> str:
    """The one sentence for a database below this build's baseline (`R-84`).

    IT HAD THREE SPELLINGS AND ONE OF THEM WAS A LIE. `EngineDatabase._migrate`
    raises it, `storage.py` `health()` reports it as `too_old` -- and
    `EngineDatabase.health()`, the one the side panel actually reads, said "Needs
    upgrade. Run 'python -m scrapex.cli init-db'" about a database that no command
    can upgrade. A sentence that must never name a command (`R-81`), must name
    `R-84`, and must say that nothing was touched is exactly the sentence to write
    once and read from everywhere.

    `subject` because the same fact is told about different things: a file being
    restored, and the engine's own warehouse refusing to open.
    """
    return (
        f"{subject} is at schema v{version} and this build's baseline starts at "
        f"v{baseline}, so there is no upgrade path between them: the migrations "
        f"that led to v{baseline} were collapsed into the baseline before release "
        f"(R-84). Nothing has been changed. Bring it to v{baseline} with the last "
        "release that still carried those migrations, or start a new one and carry "
        "this one's rows into it.")


@dataclass(frozen=True)
class Outcome:
    """What the guarded upgrade did, in a shape either front door can render.

    `refused` IS A SENTENCE, NOT A FLAG. Every refusal here has a different reason and the
    owner has to be able to act on it: a database written by a newer build is not the same
    problem as one that failed its integrity check, and "could not upgrade" is not
    something a person can do anything with.
    """

    #: `True` only when migrations were actually applied.
    upgraded: bool = False
    #: Empty when nothing stood in the way; otherwise why, in words.
    refused: str = ""
    #: `(kind, backup path)` for every database copied before it was touched.
    backups: tuple[tuple[str, str], ...] = ()
    #: `kind -> [version numbers applied]`, straight from `registry.initialize()`.
    applied: dict[str, list[int]] = field(default_factory=dict)
    #: Superseded backups removed AFTER the new copy was safely made, by name.
    pruned: tuple[str, ...] = ()

    def lines(self) -> list[str]:
        """The outcome as the CLI has always printed it, in the same order."""
        said = [f"backed up the {kind} database to {where} before upgrading"
                for kind, where in self.backups]
        if self.pruned:
            # A DELETION HAS TO SAY SO LOUDER THAN A COPY DOES. "It says out loud
            # what it did" is the fourth protection, and removing one of the
            # owner's backups is the half of it he cannot discover any other way.
            said.append(
                f"removed {len(self.pruned)} superseded backup(s): "
                + ", ".join(self.pruned))
        if self.refused:
            said.append(f"error: {self.refused}")
        said += [f"upgraded the {kind} database: applied {versions}"
                 for kind, versions in self.applied.items() if versions]
        return said

    def message(self) -> str:
        """One sentence for the panel, and it NAMES THE BACKUP.

        The button's old reply said only how many migrations were applied, because there
        was no backup to name. This is the fourth protection arriving on the surface that
        never had it.
        """
        if self.refused:
            return self.refused
        moved = {kind: versions for kind, versions in self.applied.items() if versions}
        if not moved:
            return "The database is already up to date."
        applied = ", ".join(
            f"{len(versions)} migration{'s' if len(versions) != 1 else ''} to {kind}"
            for kind, versions in moved.items())
        if not self.backups:
            return f"Applied {applied}."
        kept = "; ".join(f"{kind} backed up to {where}"
                         for kind, where in self.backups)
        swept = (f" {len(self.pruned)} superseded backup(s) removed."
                 if self.pruned else "")
        return f"Applied {applied}. {kept}.{swept}"


def _bounded(path: Path) -> list[str]:
    """Apply the owner's backup retention policy to the copy just made.

    THE POLICY IS NOT WRITTEN HERE AND MUST NOT BE. `storage`'s keep-N-per-LINEAGE
    rule already recognises these files (`storage.backup_tag` classifies a
    `pre-upgrade-<stamp>` copy) and already protects the ones that matter: it keeps
    the newest of every lineage, so a run of pre-upgrade copies can never evict the
    only `pre-wipe` copy of a source erased months ago, and it never touches a file a
    person named by hand. What it lacked was a caller on this path -- its only one is
    `storage.backup_now`, reached from the Storage page's button.

    HIS NUMBER WHEN IT CAN BE READ, the shipped default when it cannot.
    `storage.backups_kept` reads `backups_kept_per_tag` from the database, and this
    runs while that database is at a schema this build does not read -- so it is
    asked on a bare connection and every failure falls back. Housekeeping must not
    be able to fail an upgrade, and a setting read is not worth one.

    The folder is the database's own, deliberately: `archive.backup_database` writes
    beside the file it copies, wherever `backup_folder` may point.

    AND IT JUDGES ONE LINEAGE, ITS OWN. `pre-upgrade` is the lineage this function
    creates; `reset-backup` is the only copy of everything a "Start fresh" wiped, and
    its ordering cannot be trusted because `start_fresh` RENAMES the warehouse aside
    and a rename carries the warehouse's own last-write time (`OP-141`). An upgrade
    that quietly deleted today's reset copy would be the worst thing in this file.
    """
    import sqlite3

    from . import storage

    keep = storage.BACKUPS_KEPT_PER_TAG
    try:
        conn = sqlite3.connect(str(path))
        try:
            keep = storage.backups_kept(conn)
        finally:
            conn.close()
    except Exception:                       # every failure falls back, see above
        pass
    return storage.prune_backups_at(path, keep=keep, only="pre-upgrade")[1]


def upgrade_what_is_only_behind(registry, report: dict) -> tuple[dict, Outcome]:
    """Back up and migrate a warehouse whose ONLY fault is that it is behind.

    THE FOUR PROTECTIONS, and every one of them is why this function exists rather than a
    call to `registry.initialize()`:

      - A BACKUP FIRST, ALWAYS. If the copy cannot be made, nothing is migrated and the
        outcome says so. There is no path through here that advances a schema without a
        restorable copy beside it.
      - ONLY FORWARD, and only from BEHIND. A database written by a NEWER build reports a
        different status and is never touched -- downgrading is how a warehouse dies.
      - ONLY WHEN NOTHING ELSE IS WRONG. A damaged file reports "Integrity check failed",
        and migrating damage is how a small corruption becomes an unrecoverable one.
      - IT SAYS SO. The outcome names every backup by path, and both callers render it.
      - AND THE COPIES ARE BOUNDED, by the owner's own retention policy rather than
        by a number invented here (`_bounded` below). Unbounded was not untidiness:
        a refusal that copies 302 MB and then changes nothing repeats on every
        launch, and the policy that would have removed them had no caller on this
        path -- measured at 963,768,368 bytes across five copies.

    Returns the report after the attempt -- the caller re-reads `ok` and does not have to
    know whether anything happened -- and the outcome, which is what it renders.
    """
    from .archive import backup_database

    states = report.get("databases") or {}
    faulty = [state for state in states.values() if not state["ok"]]
    behind = [state for state in faulty if state.get("status") == BEHIND]
    if not behind:
        # AN EMPTY `behind` MEANS TWO COMPLETELY DIFFERENT THINGS, and answering both
        # with a bare `Outcome()` made the second one lie. "Nothing is wrong" is one;
        # the other is a fault an upgrade cannot fix -- a database below the squashed
        # baseline (`R-84`), one written by a newer build, a damaged file. `Outcome()`
        # carries no refusal, so `native.upgrade_database` answered `ok: True` with
        # "The database is already up to date." about a database the engine refuses to
        # open. That is `OP-131`'s defect on a third surface, and its worst property:
        # a reader told nothing is wrong is sent nowhere at all.
        if faulty:
            return report, Outcome(refused=(
                "the database was not upgraded because its fault is not a pending "
                "migration: " + "; ".join(
                    f"{state['kind']}: {state['status']}. {state['action']}".strip()
                    for state in faulty)))
        return report, Outcome()
    if len(behind) != len(faulty):
        # SOMETHING ELSE IS WRONG AND IT IS NAMED. Refusing silently would leave the owner
        # pressing a button that does nothing, which is the failure `R-81` is about.
        other = [f"{state['kind']}: {state['status']}"
                 for state in faulty if state.get("status") != BEHIND]
        return report, Outcome(refused=(
            "the database was not upgraded because something other than its version is "
            "wrong, and migrating a damaged file is how a small corruption becomes an "
            "unrecoverable one: " + "; ".join(other)))

    backups: list[tuple[str, str]] = []
    pruned: list[str] = []
    for state in behind:
        path = Path(state["path"])
        try:
            made = backup_database(path, tag="pre-upgrade")
        except Exception as exc:
            return report, Outcome(refused=(
                f"the {state['kind']} database is behind but could not be backed up, so "
                f"it was not upgraded ({exc})"), backups=tuple(backups))
        backups.append((state["kind"], str(made)))
        # PRUNED HERE, NOT AFTER THE MIGRATION, and the order is the whole point. The
        # copy just made is a verified point-in-time copy of the file as it stands, so
        # the newest copy is never the one at risk -- and the path that REPEATS is the
        # failing one, where `initialize()` raises below the baseline and a line placed
        # after it would never run at all.
        pruned += _bounded(path)

    applied = registry.initialize()
    return registry.ensure_ready(), Outcome(
        upgraded=any(versions for versions in applied.values()),
        backups=tuple(backups), applied=applied, pruned=tuple(pruned))
