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

"Shipped with" is the `sources.yaml` entry, which a directory source does not have.
"No per-source opinion" is what a source that said nothing has today -- inactive, robots
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

import math
import sqlite3
from dataclasses import dataclass, fields

from .config import Manifest, SourceEntry
from .robots import RobotsChoice, RobotsCustom
from .vocab import ConnectorFamily

#: The fields `save` accepts and `read` returns. A key outside this set is refused
#: rather than ignored, for `settings.SETTINGS`' reason: a typo must not look saved.
FIELDS = ("active", "robots", "robots_custom", "user_agent", "crawl_pace_s")

#: The custom rule's knobs, READ OFF `robots.RobotsCustom` rather than written again
#: here: a knob added to the rule the crawl obeys is a knob this module accepts.
_CUSTOM_KEYS = frozenset(field.name for field in fields(RobotsCustom))


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


def save(conn: sqlite3.Connection, manifest: Manifest, source_key: str,
         changes: dict) -> dict:
    """Store some of his choices for one source; None clears one. Returns all stored.

    PARTIAL ON PURPOSE: a field `changes` does not name keeps what it had, so the panel
    sending the pace alone cannot wipe his robots choice.

    The manifest is taken rather than looked up, so a test and the engine pass the one
    they already hold -- and it is required rather than optional, because the rule it
    serves (an unprobed source cannot be activated) must not be skippable by a caller
    that forgot to pass it.

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
        shipped = _shipped(manifest, source_key)
        if active is True and shipped is not None \
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
            try:
                choice = RobotsChoice(choice)
            except ValueError:
                raise SourceSettingError(
                    f"{source_key}: robots must be one of "
                    f"{[str(c) for c in RobotsChoice]} or null, not {choice!r}") from None
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
            checked = _custom_rule(source_key, rule)
            enforce, delay = checked["enforce_disallow"], checked["crawl_delay_s"]
        # Written over whatever `robots` above cleared: a rule sent beside a choice
        # other than custom is then refused below as the contradiction it is, rather
        # than silently dropped.
        columns["robots_enforce_disallow"] = None if enforce is None else int(enforce)
        columns["robots_crawl_delay_s"] = delay
    if "user_agent" in changes:
        agent = changes["user_agent"]
        if agent is not None and not isinstance(agent, str):
            raise SourceSettingError(
                f"{source_key}: user_agent must be text or null, not {agent!r}")
        # Empty CLEARS, as it does in `settings.save`: an emptied text box is the
        # panel's way of saying "no agent of my own".
        agent = (agent or "").strip() or None
        if agent is not None and not all(" " <= ch <= "~" for ch in agent):
            # PRINTABLE ASCII, 0x20-0x7E, because a header value is: httpx refuses to
            # send anything else -- Arabic letters, an accented one, a line break that
            # would inject a header -- so it is refused here and not at the source's
            # next crawl. The table's CHECK is the same range (`NOT GLOB '*[^ -~]*'`).
            raise SourceSettingError(
                f"{source_key}: user_agent must be one line of printable ASCII text "
                "(English letters, digits, spaces and punctuation)")
        columns["user_agent"] = agent
    if "crawl_pace_s" in changes:
        pace = changes["crawl_pace_s"]
        columns["crawl_pace_s"] = (
            None if pace is None
            else _seconds(source_key, "crawl_pace_s", pace, allow_zero=False))

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


def effective(conn: sqlite3.Connection, source_key: str,
              shipped: SourceEntry | None) -> SourceRules:
    """The five answers a crawl of this source acts on.

    `shipped` is this source's `sources.yaml` entry, or None for a source the manifest
    does not declare -- every directory source. It is REQUIRED, not defaulted: a price
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


def layered(chosen: dict, source_key: str, shipped: SourceEntry | None) -> SourceRules:
    """`effective`'s layering, given his choices already read -- `{}` for none.

    Its own function for the one caller with no warehouse to read: `scrapex crawl`, which
    writes to the local inbox and so runs a source as it shipped.

    `robots` and `robots_custom` move as ONE field, because a rule is meaningless without
    its choice: his choice of `obey` must not inherit a shipped custom rule, and his
    `custom` must not be judged against a shipped `obey`.

    A shipped custom rule is checked by the rules `save` applies, and a misspelt shipped
    choice fails, both as `SourceSettingError`: the manifest is hand-edited, and a wrong
    value there must stop the crawl that would act on it rather than be guessed at.
    """
    if shipped is not None and shipped.source_key != source_key:
        raise ValueError(
            f"asked for {source_key!r} with {shipped.source_key!r}'s manifest entry")

    if shipped is not None and shipped.family == ConnectorFamily.TBD_PROBE:
        # Whatever was stored: a source can be activated and then see a later release
        # put its family back to TBD-probe, and there is then no collector to run.
        active = False
    elif "active" in chosen:
        active = chosen["active"]
    else:
        active = bool(shipped.active) if shipped is not None else NO_OPINION.active

    if "robots" in chosen:
        robots, custom = chosen["robots"], chosen.get("robots_custom")
    elif shipped is not None:
        # `RobotsChoice(...)` and not the string: a manifest typo fails here, loudly,
        # instead of comparing unequal to every choice and acting as the default.
        try:
            robots = RobotsChoice(shipped.robots or RobotsChoice.DEFAULT)
        except ValueError:
            raise SourceSettingError(
                f"{source_key}: sources.yaml says robots: {shipped.robots!r}, which is "
                f"none of {[str(c) for c in RobotsChoice]}") from None
        # A NEW dict, never the manifest's own: a consumer that edits the rule it was
        # handed must not be editing the manifest every later crawl reads.
        custom = (_custom_rule(source_key, shipped.robots_custom)
                  if robots is RobotsChoice.CUSTOM and shipped.robots_custom is not None
                  else None)
    else:
        robots, custom = NO_OPINION.robots, NO_OPINION.robots_custom

    if "user_agent" in chosen:
        agent = chosen["user_agent"]
    else:
        agent = shipped.user_agent if shipped is not None else NO_OPINION.user_agent

    if "crawl_pace_s" in chosen:
        pace = chosen["crawl_pace_s"]
    else:
        pace = shipped.crawl_pace_s if shipped is not None else NO_OPINION.crawl_pace_s

    return SourceRules(active=active, robots=robots, robots_custom=custom,
                       user_agent=agent, crawl_pace_s=pace)


def _shipped(manifest: Manifest, source_key: str) -> SourceEntry | None:
    """This source's `sources.yaml` entry, or None for a source the manifest does not
    declare -- every directory source. `Manifest.get` raises for that case, and here it
    is not an error: it is the layer a directory source does not have."""
    return next((entry for entry in manifest.sources
                 if entry.source_key == source_key), None)


def _custom_rule(source_key: str, rule: object) -> dict:
    """A custom robots rule, checked, as a NEW `{enforce_disallow, crawl_delay_s}`.

    `enforce_disallow` is required although `RobotsCustom` defaults it: a rule that does
    not say whether it obeys Disallow is a rule nobody decided, and reading it as False
    would be deciding for him.
    """
    if not isinstance(rule, dict) or not set(rule) <= _CUSTOM_KEYS \
            or "enforce_disallow" not in rule:
        raise SourceSettingError(
            f"{source_key}: a custom robots rule is {{enforce_disallow: "
            f"true|false, crawl_delay_s: seconds|null}}, not {rule!r}")
    enforce, delay = rule["enforce_disallow"], rule.get("crawl_delay_s")
    if type(enforce) is not bool:
        raise SourceSettingError(
            f"{source_key}: enforce_disallow must be true or false, not {enforce!r}")
    if delay is not None:
        delay = _seconds(source_key, "crawl_delay_s", delay, allow_zero=True)
    return {"enforce_disallow": enforce, "crawl_delay_s": delay}


def _seconds(source_key: str, name: str, value: object, *, allow_zero: bool) -> float:
    """A duration in seconds, refused unless it is a finite number in bounds.

    Finite because SQLite stores NaN as NULL -- a pace he set would read back as "not
    chosen" -- and an infinite pace is a crawl that never makes its next request. The
    table's `< 9e999` and `SourceEntry`'s `allow_inf_nan=False` hold the same bound. An
    integer too large for a float (`10**400`) is refused here, not raised as
    OverflowError. Not a bool, because `True` is an int in Python and would be stored as
    one second.
    """
    if type(value) not in (int, float):
        raise SourceSettingError(
            f"{source_key}: {name} must be a number of seconds or null, not {value!r}")
    try:
        seconds = float(value)
    except OverflowError:
        seconds = math.inf
    if not math.isfinite(seconds):
        raise SourceSettingError(
            f"{source_key}: {name} must be a finite number of seconds, not {value!r}")
    if seconds < 0 or (seconds == 0 and not allow_zero):
        bound = "0 or more" if allow_zero else "more than 0"
        raise SourceSettingError(f"{source_key}: {name} must be {bound}, not {value!r}")
    return seconds
