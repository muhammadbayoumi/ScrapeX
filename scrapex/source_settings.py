"""His choices about one source, stored in the warehouse (#1584).

`settings.py` holds his GENERAL rules -- the pace, the agent, whether Disallow is
obeyed -- for every source at once. This module holds the layer above it: what he
decided about ONE source. Five fields, named exactly as `config.SourceEntry` names
them so a consumer can take either without translating:

    active          is this source crawled by the schedule
    robots          `robots.RobotsChoice`: default | obey | custom
    robots_custom   the custom rule, {enforce_disallow, crawl_delay_s}; only under custom
    user_agent      the agent this source is fetched as
    crawl_pace_s    seconds between requests, for this source alone

WHY THE WAREHOUSE AND NOT `sources.yaml`, his ruling on #1584 (option C): the manifest
ships inside the packaged engine and is deleted when it exits, so a panel edit to it
does not survive a restart (#1583); and a directory source (muqawil_org, the Oman
register) has no manifest entry at all, so it had nowhere to keep a choice. The table is
`source_setting`, migration 0022, keyed on `source_site.source_id` -- the one registry
every kind of source is in.

THREE LAYERS, MOST SPECIFIC FIRST, and `effective` is the only reader of all three:

    his choice for this source  >  what the source shipped with  >  no per-source opinion

"Shipped with" is the release's own word on the source: its `sources.yaml` entry for a
price source, its `directories.Directory` for a directory -- which ships `active` and no
robots, agent or pace opinion. Clearing a choice returns the field to that (his ruling,
2026-10-08). "No per-source opinion" is what a source that said nothing has today -- inactive, robots
`default`, no agent, no pace -- and it is NOT his general rules resolved here. Those are
applied downstream exactly as they are now (`connectors.base.general_fetcher`,
`resolve_user_agent`, `robots.decide`'s `tool_default_obeys`), so reading them a second
time here would be a second copy of the chain that decides a crawl's agent and pace.

NONE MEANS "NOT CHOSEN", EVERYWHERE IN THIS MODULE. A NULL column is a field he has not
decided, so the source inherits it; `save` with a field set to None clears his choice and
the source inherits again. `robots = "default"` is the opposite of None: a choice to
follow the tool-wide setting even where the source shipped `obey`.

THE CALLER OWNS THE TRANSACTION, as `settings.save` leaves it to its caller:
`EngineDatabase.write(lambda conn: source_settings.save(conn, ...))` commits, and holds
the write lock while it does.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from . import directories
from .config import (
    Manifest,
    SourceEntry,
    checked_robots,
    checked_robots_custom,
    checked_seconds,
    checked_user_agent,
)
from .directories import Directory
from .robots import RobotsChoice
from .vocab import ConnectorFamily

#: The fields `save` accepts and `read` returns. A key outside this set is refused
#: rather than ignored, for `settings.SETTINGS`' reason: a typo must not look saved.
FIELDS = ("active", "robots", "robots_custom", "user_agent", "crawl_pace_s")

#: What a source ships with: its manifest entry, its directory, or nothing.
Shipped = SourceEntry | Directory | None


class UnknownSourceError(LookupError):
    """No `source_site` row has this key, so there is nothing to attach a choice to.

    `LookupError` and not `KeyError`: `str()` of a KeyError is the repr of its argument,
    so the sentence below would reach the panel wrapped in quotes. A caller catching
    `LookupError` still catches it, as it catches `Manifest.get`'s KeyError.
    """


class SourceSettingError(ValueError):
    """A choice that cannot be stored, with the sentence saying why."""


@dataclass(frozen=True)
class SourceRules:
    """One source's answer to each of the five questions, after layering.

    Shaped as `SourceEntry` holds the same fields, so a consumer that builds a fetcher
    from an entry today takes these instead. None in `robots_custom`, `user_agent` and
    `crawl_pace_s` means no per-source opinion: the general rule decides.
    """

    active: bool
    robots: RobotsChoice
    #: Only ever set when `robots` is CUSTOM -- the same invariant the table's CHECK
    #: holds -- so a consumer never meets a rule the choice ignores.
    robots_custom: dict | None
    user_agent: str | None
    crawl_pace_s: float | None


def read(conn: sqlite3.Connection, source_key: str) -> dict:
    """His stored choices for one source: only the fields he has decided.

    An empty dict when he has decided nothing, and also when the warehouse has no row
    for this source yet -- a price source is registered in `source_site` by its first
    ingest, so a source nobody has crawled is not an error to READ, only to write to.
    The result is what `save` accepts, so `save(conn, m, key, read(conn, key))` changes
    nothing.
    """
    row = conn.execute(
        "SELECT st.active, st.robots_choice, st.robots_enforce_disallow, "
        "       st.robots_crawl_delay_s, st.user_agent, st.crawl_pace_s "
        "  FROM source_setting AS st "
        "  JOIN source_site AS ss ON ss.source_id = st.source_id "
        " WHERE ss.source_key = ?", (source_key,)).fetchone()
    if row is None:
        return {}
    active, choice, enforce, delay, agent, pace = tuple(row)
    chosen: dict = {}
    if active is not None:
        chosen["active"] = bool(active)
    if choice is not None:
        chosen["robots"] = RobotsChoice(choice)
        # The CHECK guarantees the rule is here exactly when the choice is custom, so
        # this reads it under that condition and nothing else.
        if chosen["robots"] is RobotsChoice.CUSTOM:
            chosen["robots_custom"] = {"enforce_disallow": bool(enforce),
                                       "crawl_delay_s": delay}
    if agent is not None:
        chosen["user_agent"] = agent
    if pace is not None:
        chosen["crawl_pace_s"] = pace
    return chosen


def save(conn: sqlite3.Connection, source_key: str, shipped: Shipped,
         changes: dict) -> dict:
    """Store some of his choices for one source; None clears one. Returns all stored.

    PARTIAL ON PURPOSE: a field `changes` does not name keeps what it had, so the panel
    sending the pace alone cannot wipe his robots choice.

    `shipped` is what `effective` takes -- this source's manifest entry, its directory,
    or None -- and is required for the same reason: the rule it serves (an unprobed
    source cannot be activated) must not be skippable by a caller that forgot it.

    EVERY VALUE IS CHECKED BY `config`'s checkers, the ones `SourceEntry` runs on the
    manifest, so the panel and `sources.yaml` refuse the same values with one sentence.

    REFUSED, each with the reason, and before anything is written:
      * a key outside `FIELDS`, or a source `source_site` does not have;
      * a value of the wrong kind or out of the bounds the table's CHECKs hold;
      * `custom` with no rule, or a rule under any other choice -- except that changing
        the choice away from custom clears the rule, as `/api/sources/{key}/edit` does;
      * a change that sets `active` on a source whose family is still TBD-probe, which
        `SourceEntry` refuses in the manifest for the same reason (A3: no family until
        proven).
    """
    if not isinstance(changes, dict):
        raise SourceSettingError(
            f"{source_key}: the choices must be a mapping of field to value, "
            f"not {changes!r}")
    # A list and not a sorted set: a key that is not a string cannot be sorted against
    # the strings, and the refusal must be this sentence rather than a TypeError.
    unknown = [key for key in changes if key not in FIELDS]
    if unknown:
        raise SourceSettingError(
            f"{source_key}: {unknown} are not per-source choices; the fields are "
            f"{list(FIELDS)}")
    found = conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                         (source_key,)).fetchone()
    if found is None:
        raise UnknownSourceError(
            f"{source_key!r} is not in this warehouse's source registry (source_site), "
            "so there is no source to store a choice for")
    source_id = int(found[0])

    # Column -> value, for the columns this change writes and only those. The names come
    # from this function's own literals, never from `changes`, so the f-string below
    # carries no outside text; every value is a bound parameter.
    columns: dict[str, object] = {}
    if "active" in changes:
        active = changes["active"]
        if active is not None and type(active) is not bool:
            raise SourceSettingError(
                f"{source_key}: active must be true, false or null, not {active!r}")
        columns["active"] = None if active is None else int(active)
        if active is True and isinstance(shipped, SourceEntry) \
                and shipped.family == ConnectorFamily.TBD_PROBE:
            # Only when THIS change activates it: a pace edit to a source whose stored
            # `active` predates its family reverting to TBD-probe is not an activation,
            # and `effective` already reads that source as inactive.
            raise SourceSettingError(
                f"{source_key}: family is TBD-probe, so there is no collector to run "
                "yet; it cannot be activated until the site is probed and its family "
                "is set")
    if "robots" in changes:
        choice = changes["robots"]
        if choice is not None:
            choice = _checked(source_key, checked_robots, choice)
        columns["robots_choice"] = None if choice is None else str(choice)
        if choice is not RobotsChoice.CUSTOM:
            # Away from custom, the rule goes with it -- see the migration's header.
            columns["robots_enforce_disallow"] = None
            columns["robots_crawl_delay_s"] = None
    if "robots_custom" in changes:
        rule = changes["robots_custom"]
        if rule is None:
            enforce, delay = None, None
        else:
            checked = _checked(source_key, checked_robots_custom, rule)
            enforce, delay = checked["enforce_disallow"], checked["crawl_delay_s"]
        # Written over whatever `robots` above cleared: a rule sent beside a choice
        # other than custom is then refused below as the contradiction it is, rather
        # than silently dropped.
        columns["robots_enforce_disallow"] = None if enforce is None else int(enforce)
        columns["robots_crawl_delay_s"] = delay
    if "user_agent" in changes:
        # Empty CLEARS, as it does in `settings.save`: an emptied text box is the
        # panel's way of saying "no agent of my own".
        columns["user_agent"] = _checked(source_key, checked_user_agent,
                                         changes["user_agent"])
    if "crawl_pace_s" in changes:
        pace = changes["crawl_pace_s"]
        columns["crawl_pace_s"] = (
            None if pace is None
            else _checked(source_key, checked_seconds, "crawl_pace_s", pace,
                          allow_zero=False))

    # THE ROW AS IT WILL STAND, so the rules between fields are judged on the result
    # and not on the change alone: a pace-only change to a custom source keeps a rule
    # it already has, and setting custom keeps the rule stored beside an earlier one.
    stored = conn.execute(
        "SELECT active, robots_choice, robots_enforce_disallow, robots_crawl_delay_s "
        "  FROM source_setting WHERE source_id = ?", (source_id,)).fetchone()
    after = dict(zip(("active", "robots_choice", "robots_enforce_disallow",
                      "robots_crawl_delay_s"),
                     tuple(stored) if stored is not None else (None,) * 4, strict=True))
    after.update({k: v for k, v in columns.items() if k in after})
    has_rule = after["robots_enforce_disallow"] is not None
    if after["robots_choice"] == RobotsChoice.CUSTOM and not has_rule:
        # `robots.decide` refuses this at crawl time; refusing it here means the crawl
        # never meets it.
        raise SourceSettingError(
            f"{source_key}: robots = custom needs its rule (robots_custom: "
            "{enforce_disallow, crawl_delay_s}); choose default or obey, or send the rule")
    if after["robots_choice"] != RobotsChoice.CUSTOM \
            and (has_rule or after["robots_crawl_delay_s"] is not None):
        raise SourceSettingError(
            f"{source_key}: a custom robots rule needs robots = custom, and this source's "
            f"choice is {after['robots_choice'] or 'not set'}")

    # AN UPDATE OR AN INSERT, AND NOT `INSERT ... ON CONFLICT DO UPDATE`. SQLite checks
    # a row's CHECKs on the row the INSERT proposes, before it looks for the conflict,
    # so an upsert of `robots = custom` alone failed the custom-needs-its-rule CHECK on
    # a row whose stored rule satisfied it. Only the named columns are written either
    # way, so a field this change does not name is never rewritten from a stale read.
    names = list(columns)
    if names and stored is not None:
        conn.execute(
            "UPDATE source_setting SET "
            + ", ".join(f"{name} = ?" for name in names)
            + ", updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE source_id = ?",
            (*columns.values(), source_id))
    elif names:
        conn.execute(
            f"INSERT INTO source_setting (source_id, {', '.join(names)}) "
            f"VALUES (?{', ?' * len(names)})", (source_id, *columns.values()))
    return read(conn, source_key)


#: What a source that said nothing has, and what `effective` falls to when neither he
#: nor `sources.yaml` answered a field: inactive, robots `default`, no agent, no pace.
#: Each None hands the question to his GENERAL rules, which `connectors.base.
#: general_fetcher` applies. Named for the one caller with no warehouse to ask: the
#: command line's `contractors --plan`.
NO_OPINION = SourceRules(active=False, robots=RobotsChoice.DEFAULT, robots_custom=None,
                         user_agent=None, crawl_pace_s=None)


def effective(conn: sqlite3.Connection, source_key: str, shipped: Shipped) -> SourceRules:
    """The five answers a crawl of this source acts on.

    `shipped` is this source's `sources.yaml` entry, its `directories.Directory`, or None
    for a source the release says nothing about. It is REQUIRED, not defaulted: a price
    source asked for without its entry would silently lose Zid's agent, so a caller says
    "None" on purpose. Taken as the entry rather than the manifest because the crawl
    already holds the entry it is running (`capture.capture_source`).

    Per field: his stored choice, else the `sources.yaml` entry's value, else no
    per-source opinion (`NO_OPINION`); `layered` says how.

    A source with no `source_site` row is not refused here, unlike in `save`. A price
    source's first crawl happens before its first ingest registers it, and that crawl
    still needs its shipped agent -- Zid answers 403 to any other.

    """
    return layered(read(conn, source_key), source_key, shipped)


def layered(chosen: dict, source_key: str, shipped: Shipped) -> SourceRules:
    """`effective`'s layering, given his choices already read -- `{}` for none.

    Its own function for the one caller with no warehouse to read: `scrapex crawl`, which
    writes to the local inbox and so runs a source as it shipped.

    `robots` and `robots_custom` move as ONE field, because a rule is meaningless without
    its choice: his choice of `obey` must not inherit a shipped custom rule, and his
    `custom` must not be judged against a shipped `obey`.
    """
    base = _shipped_rules(source_key, shipped)
    if "robots" in chosen:
        robots, custom = chosen["robots"], chosen.get("robots_custom")
    else:
        robots, custom = base.robots, base.robots_custom
    if isinstance(shipped, SourceEntry) and shipped.family == ConnectorFamily.TBD_PROBE:
        # Whatever was stored: a source can be activated and then see a later release
        # put its family back to TBD-probe, and there is then no collector to run.
        active = False
    else:
        active = chosen.get("active", base.active)
    return SourceRules(active=active, robots=robots, robots_custom=custom,
                       user_agent=chosen.get("user_agent", base.user_agent),
                       crawl_pace_s=chosen.get("crawl_pace_s", base.crawl_pace_s))


def _shipped_rules(source_key: str, shipped: Shipped) -> SourceRules:
    """What the release says about this source, as the five answers.

    A manifest entry has been through `SourceEntry`'s checks, which are `save`'s; its
    custom rule is checked again here anyway, because a consumer edits what it is handed
    and must not be editing the manifest: this builds a NEW dict. A directory ships
    whether it is on and nothing else -- no robots, agent or pace of its own.
    """
    if isinstance(shipped, SourceEntry):
        if shipped.source_key != source_key:
            raise ValueError(
                f"asked for {source_key!r} with {shipped.source_key!r}'s manifest entry")
        robots = _checked(source_key, checked_robots, shipped.robots)
        # Under custom the rule is checked even when it is missing: custom with no rule
        # is what `robots.decide` refuses at crawl time, so it is refused here, with the
        # checker's sentence, rather than handed on as "no rule".
        custom = (_checked(source_key, checked_robots_custom, shipped.robots_custom)
                  if robots is RobotsChoice.CUSTOM else None)
        return SourceRules(active=bool(shipped.active), robots=robots, robots_custom=custom,
                           user_agent=shipped.user_agent, crawl_pace_s=shipped.crawl_pace_s)
    if isinstance(shipped, Directory):
        if shipped.key != source_key:
            raise ValueError(
                f"asked for {source_key!r} with {shipped.key!r}'s directory")
        return SourceRules(active=shipped.active, robots=NO_OPINION.robots,
                           robots_custom=None, user_agent=None, crawl_pace_s=None)
    return NO_OPINION


def shipped_with(manifest: Manifest, source_key: str) -> Shipped:
    """What the release says about a source: its manifest entry, else its directory,
    else None. The argument `effective` and `save` take, for a caller holding the
    manifest rather than the entry (`storage.reconcile_active`, the panel's routes)."""
    for entry in manifest.sources:
        if entry.source_key == source_key:
            return entry
    if source_key in directories.BUILDERS:
        return directories.get(source_key)
    return None


def _checked(source_key: str, check: Callable, *args, **kwargs):
    """Run one of `config`'s checkers, naming the source in its refusal."""
    try:
        return check(*args, **kwargs)
    except ValueError as exc:
        raise SourceSettingError(f"{source_key}: {exc}") from None
