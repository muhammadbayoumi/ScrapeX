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

    def lines(self) -> list[str]:
        """The outcome as the CLI has always printed it, in the same order."""
        said = [f"backed up the {kind} database to {where} before upgrading"
                for kind, where in self.backups]
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
        return f"Applied {applied}. {kept}."


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

    Returns the report after the attempt -- the caller re-reads `ok` and does not have to
    know whether anything happened -- and the outcome, which is what it renders.
    """
    from .archive import backup_database

    states = report.get("databases") or {}
    faulty = [state for state in states.values() if not state["ok"]]
    behind = [state for state in faulty if state.get("status") == BEHIND]
    if not behind:
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
    for state in behind:
        path = Path(state["path"])
        try:
            made = backup_database(path, tag="pre-upgrade")
        except Exception as exc:
            return report, Outcome(refused=(
                f"the {state['kind']} database is behind but could not be backed up, so "
                f"it was not upgraded ({exc})"), backups=tuple(backups))
        backups.append((state["kind"], str(made)))

    applied = registry.initialize()
    return registry.ensure_ready(), Outcome(
        upgraded=any(versions for versions in applied.values()),
        backups=tuple(backups), applied=applied)
