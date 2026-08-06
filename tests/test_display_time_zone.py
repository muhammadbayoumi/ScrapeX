"""The display time zone (spec 33 / issue #33), and the promise it is built on.

The feature is one sentence — show times in the owner's zone — and the whole
risk is in the word "show". A time zone that reached the WRITE path would
silently corrupt a price history that is append-only by design and has no
second copy: an observation stamped in Riyadh time and read back as UTC is a
price that moved three hours before it did, in a table nothing recomputes.

So the tests that matter most here are the negative ones. They are first in the
file for that reason:

  * changing the zone changes exactly one row in the entire database,
  * no writer can even READ the preference,
  * and no surface may grow a second date formatter to drift from the one.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod, storage  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
STATIC = ROOT / "scrapex" / "webui" / "static"
TEMPLATES = ROOT / "scrapex" / "webui" / "templates"


@pytest.fixture(autouse=True)
def isolated_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")


@pytest.fixture()
def db_path(tmp_path) -> Path:
    """A real warehouse with real ingested rows.

    A tmp_path database and never the live one: the owner's warehouse is opened
    read-only for a reason, and a test that wrote to it while a crawl of ten
    sources was running would be the exact accident this feature promises never
    to cause.
    """
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


# ---- 1. nothing stored changes ----------------------------------------------

def _whole_database(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Every row of every table, so a diff can be taken over the lot.

    Deliberately not a checksum: when this test fails the reviewer needs to see
    WHICH table and WHICH row moved, and a single changed digest cannot say.
    """
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: sorted(conn.execute(f'SELECT * FROM "{t}"').fetchall(), key=repr)
            for t in tables}


def test_choosing_a_time_zone_changes_exactly_one_row_in_the_database(client, db_path):
    """The strongest guarantee in the feature, taken over the whole warehouse.

    Not "the timestamps look the same" — every row of every table, before and
    after, with the single expected settings row named. A future change that
    starts writing a converted value anywhere at all fails here, whichever
    table it picks.
    """
    conn = sqlite3.connect(db_path)
    try:
        before = _whole_database(conn)
    finally:
        conn.close()

    response = client.post("/api/timezone",
                           json={"zone": "Asia/Riyadh", "updatedAt": 1_769_000_000_000})
    assert response.status_code == 200, response.text
    assert response.json()["timezone"]["zone"] == "Asia/Riyadh"

    conn = sqlite3.connect(db_path)
    try:
        after = _whole_database(conn)
    finally:
        conn.close()

    assert set(before) == set(after), "a table appeared or vanished"

    moved = {table: (before[table], after[table])
             for table in before if before[table] != after[table]}
    assert set(moved) == {"scrapex_meta"}, (
        "choosing a display time zone touched more than the preference itself: "
        f"{sorted(moved)}. This feature is display-only — see spec 33 §6.2.")

    was, now = moved["scrapex_meta"]
    added = [row for row in now if row not in was]
    removed = [row for row in was if row not in now]
    assert not removed, f"a meta row was rewritten or deleted: {removed}"
    assert len(added) == 1 and added[0][0] == "setting:ui_time_zone", (
        f"expected one new row for the preference, got {added}")
    assert json.loads(added[0][1]) == {"zone": "Asia/Riyadh",
                                       "updatedAt": 1_769_000_000_000}


def _instant_columns(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Every (table, column) in the warehouse that holds an instant."""
    found = []
    for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        for row in conn.execute(f'PRAGMA table_info("{table}")'):
            if row[1].endswith("_at"):
                found.append((table, row[1]))
    return found


def test_every_stored_instant_is_utc_and_stays_utc_across_a_zone_change(client, db_path):
    """The same promise from the other side, and column by column.

    It reads the schema rather than a list written here, so a column added later
    is covered the day it appears — including the Z, which is what makes the
    stored value unambiguous in the first place (§6.3).
    """
    conn = sqlite3.connect(db_path)
    try:
        columns = _instant_columns(conn)
        before = {}
        for table, column in columns:
            values = [r[0] for r in conn.execute(
                f'SELECT "{column}" FROM "{table}" ORDER BY "{column}"')]
            before[(table, column)] = values
    finally:
        conn.close()

    assert columns, "the fixture warehouse holds no instants to check"
    populated = {key: v for key, v in before.items() if any(v)}
    assert populated, "no instant column has a value, so this proves nothing"
    for (table, column), values in populated.items():
        for value in values:
            if value:
                assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value), (
                    f"{table}.{column} is not stored as UTC: {value!r}")

    client.post("/api/timezone", json={"zone": "Pacific/Kiritimati",
                                       "updatedAt": 1_769_000_000_001})

    conn = sqlite3.connect(db_path)
    try:
        after = {}
        for table, column in columns:
            after[(table, column)] = [r[0] for r in conn.execute(
                f'SELECT "{column}" FROM "{table}" ORDER BY "{column}"')]
    finally:
        conn.close()

    assert after == before, (
        "a stored instant changed when the DISPLAY zone changed — the one thing "
        "spec 33 §6.2 forbids")


def test_no_writer_can_read_the_display_preference():
    """The preference is unreachable from anything that writes.

    A test on behaviour would only cover the paths it thought to exercise. This
    covers every module by construction: `ui_time_zone` may be named in the web
    layer that serves it, the settings registry that declares it, and the two
    browser copies — nowhere that stamps a row.
    """
    allowed = {
        Path("scrapex/settings.py"),                 # declares it
        Path("scrapex/webui/app.py"),                # serves it
    }
    offenders = []
    for path in sorted((ROOT / "scrapex").rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative in allowed:
            continue
        if "ui_time_zone" in path.read_text(encoding="utf-8"):
            offenders.append(relative.as_posix())
    assert not offenders, (
        f"these modules can read the display time zone: {offenders}. Only the "
        "presentation layer may — a writer that reads it is how a converted "
        "value reaches the database.")


def test_the_payload_contract_still_refuses_a_non_utc_timestamp():
    """§6.2/§6.3 need no new enforcement, and this says why: the refusal was
    already there and still is. Nothing in this feature is allowed to relax it."""
    from pydantic import ValidationError

    from scrapex.payload import FunnelPayload

    fixture = ROOT / "contracts" / "fixtures" / "payload_invalid_timezone.json"
    with pytest.raises(ValidationError, match="must be UTC"):
        FunnelPayload.model_validate_json(fixture.read_text(encoding="utf-8"))


# ---- 2. the identifier is validated, never guessed --------------------------

@pytest.mark.parametrize("zone", ["Asia/Riyadh", "Europe/London", "America/New_York",
                                  "Asia/Dubai", "UTC"])
def test_the_iana_identifiers_the_issue_names_are_accepted(client, zone):
    """§6.4's own examples, each one a real save."""
    response = client.post("/api/timezone", json={"zone": zone, "updatedAt": 1})
    assert response.status_code == 200, response.text
    assert client.get("/api/timezone").json()["timezone"]["zone"] == zone


@pytest.mark.parametrize("zone", [
    "Mars/Phobos",          # not a place with a tz database entry
    "Asia/Riyad",           # the typo that is one letter from a real zone
    "GMT+3",                # a fixed offset, which §6.4 rules out as a setting
    "riyadh",               # a city, not an identifier
])
def test_an_unknown_identifier_is_refused_rather_than_stored(client, zone, db_path):
    """§6.4: refuse it. A zone stored but unresolvable would show every time in
    the fallback zone while the setting claimed otherwise — the one failure the
    owner could not diagnose from the screen."""
    response = client.post("/api/timezone", json={"zone": zone, "updatedAt": 1})
    assert response.status_code == 400, response.text
    assert zone in response.json()["detail"]

    conn = sqlite3.connect(db_path)
    try:
        stored = conn.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'setting:ui_time_zone'"
        ).fetchone()
    finally:
        conn.close()
    assert stored is None, f"{zone!r} was refused and stored anyway: {stored}"


def test_the_empty_zone_is_valid_and_means_follow_the_detected_one(client):
    """§6.5: detection produces a DEFAULT, and the default has to be storable
    without naming a zone — otherwise "use whatever this browser detects" would
    have to be spelled as some particular zone, which is exactly the silent
    overwrite of the owner's choice that §6.5 forbids."""
    assert client.get("/api/timezone").json()["timezone"] is None, (
        "a fresh install has chosen nothing, and must say so rather than "
        "naming a zone the owner never picked")
    assert client.post("/api/timezone", json={"zone": "Asia/Riyadh",
                                              "updatedAt": 5}).status_code == 200
    assert client.post("/api/timezone", json={"zone": "", "updatedAt": 6}).status_code == 200

    # Going BACK to Detected is stored, not cleared, and the difference is not
    # cosmetic. The two surfaces reconcile on updatedAt (§6.9): if this row
    # vanished, the panel would read "nothing saved", keep its own older
    # Asia/Riyadh — which nothing would ever contradict — and push it back up.
    # Resetting to Detected on one surface would then never reach the other.
    saved = client.get("/api/timezone").json()["timezone"]
    assert saved == {"zone": "", "updatedAt": 6}, (
        "choosing Detected must be shareable as a decision with its own "
        f"timestamp, not as an absence: {saved}")


def test_the_endpoint_refuses_a_body_it_cannot_understand(client):
    for body in [{"zone": 3, "updatedAt": 1},
                 {"zone": "UTC", "updatedAt": -1},
                 {"zone": "UTC", "updatedAt": True},
                 {"zone": "UTC"}]:
        assert client.post("/api/timezone", json=body).status_code == 400, body


def test_a_zone_the_tz_database_later_drops_does_not_break_the_page(client, db_path):
    """A preference saved under one tzdata and read under a newer one must not
    take the interface down with it — the browser's own fallback chain handles
    it, so the endpoint reports "nothing chosen" rather than raising."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     ("setting:ui_time_zone",
                      json.dumps({"zone": "Mars/Phobos", "updatedAt": 9})))
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/timezone")
    assert response.status_code == 200
    assert response.json()["timezone"] is None


def test_the_preference_is_shared_by_both_surfaces_through_one_setting():
    """§6.9, as the owner ruled it on 2026-07-30: ONE preference, and its only
    control is in the extension. The mechanism is the one `ui_appearance`
    already uses — a settings row both surfaces read — so there is no second
    sharing scheme to keep in step."""
    from scrapex.settings import SETTINGS

    assert "ui_time_zone" in SETTINGS, "the preference is not a declared setting"
    assert SETTINGS["ui_time_zone"].default == "", (
        "the default must be empty — a detected zone is never written")
    assert not SETTINGS["ui_time_zone"].env, (
        "an environment variable would give the two surfaces different answers")


# ---- 3. one formatter, and the build says so -------------------------------

def test_the_two_copies_of_the_module_are_identical():
    """The extension and the Workspace are different origins and cannot share a
    file, exactly as with appearance.js. Byte equality is the only thing that
    keeps them one formatter rather than two."""
    panel = (EXT / "timezone.js").read_bytes()
    workspace = (STATIC / "timezone.js").read_bytes()
    assert panel == workspace, (
        "extension/timezone.js and scrapex/webui/static/timezone.js have "
        "drifted. They are one module in two places; copy one over the other.")


# Files that legitimately name a zone or a date without formatting one.
_FORMATTER_EXEMPT = {"timezone.js"}


def _ui_scripts() -> list[Path]:
    scripts = [p for p in EXT.glob("*.js")]
    scripts += [p for p in STATIC.rglob("*.js") if "vendor" not in p.parts]
    return sorted(scripts)


# The idioms this feature REPLACED. Each one is a way of rendering an instant
# that bypasses the single formatter, and each was really in the tree before
# issue #33 — so this list is a record of what was fixed, not a guess at what
# might break.
#
# Note what these key on: the MANIPULATION, not the name of the field. The first
# version of the last rule read `[a-zA-Z_]+_at ... slice(0, 1[06])` and was blind
# by construction to `summary.last_run[:16]` — the owner found that one himself,
# under the source table, after this suite had gone green. Hand-formatting an
# instant has only a few shapes; a vocabulary of field names is always one
# product decision behind.
_SECOND_FORMATTER = [
    (r"\.toLocaleDateString\(", "toLocaleDateString"),
    (r"\.toLocaleTimeString\(", "toLocaleTimeString"),
    (r"\.toLocaleString\(\s*\[\s*\]", "toLocaleString([], {date parts})"),
    (r"new Intl\.DateTimeFormat\([^)]*\)\s*\.\s*format", "Intl.DateTimeFormat().format"),
    (r"\.slice\(\s*0\s*,\s*(?:10|16|19)\s*\)",
     "slicing a value to a date or minute by hand"),
    (r"""\.replace\(\s*(["'])T\1\s*,""",
     'swapping the ISO "T" for a space by hand'),
]

# The one written value that legitimately wears the truncation shape. Named
# rather than pattern-matched, so the exemption is a decision on the record.
_SLICE_EXEMPT = {
    # The CSV/JSON export FILENAME stamp. A written value, not a rendering, and
    # a filename dated in a display zone would disagree with the UTC inside the
    # file it names.
    ("grid.js", "toISOString"),
}


@pytest.mark.parametrize("pattern,name", _SECOND_FORMATTER)
def test_no_surface_grows_a_second_date_formatter(pattern, name):
    """§6.7 says "consistently, everywhere", which only holds while there is one
    formatter. Six surfaces each had their own before this — including two that
    truncated an instant with slice(0, 10), so a period that opened at 23:30 UTC
    was filed under the wrong DAY for anyone east of London."""
    offenders = []
    for script in _ui_scripts():
        if script.name in _FORMATTER_EXEMPT:
            continue
        source = script.read_text(encoding="utf-8")
        for match in re.finditer(pattern, source):
            line = source[source.rfind("\n", 0, match.start()) + 1:
                          source.find("\n", match.end())]
            if any(script.name == f and token in line for f, token in _SLICE_EXEMPT):
                continue
            offenders.append(f"{script.relative_to(ROOT).as_posix()}: {line.strip()[:70]}")
    assert not offenders, (
        f"{name} is a second date formatter: {offenders}. Every displayed "
        "instant goes through ScrapeXTime (extension/timezone.js) — see §6.7.")


# Jinja expressions that name an *_at field and are NOT a stamp() call. Each
# needs a reason, because a page that formats a time itself is a page that will
# disagree with every other one.
_TEMPLATE_TIME_EXEMPT = {
    # The macro and the one call site that cannot hold a child element: both
    # hand the raw value to the SAME formatter through data-utc.
    "_time.html",
    "_storage.html",
    # `run_at` is a wall clock ("09:00"), not an instant: it is what the owner
    # typed for the scheduler to fire at, in the schedule's own zone. Converting
    # it would change WHEN a job runs, which is not a display change at all.
    "schedules.html",
}

# The shape of hand-formatting an instant, in Jinja. This is the guard that
# would have caught what the owner found, and the NAME guard below is the one
# that did not: `summary.last_run` does not end in _at, so no vocabulary of
# field names could have seen it. Keep both — shape catches hand-FORMATTING,
# name catches hand-NAMING — and note the residual blind spot they share: a bare
# {{ summary.last_run }} with no manipulation at all is invisible to both, and
# still needs a reader.
_TEMPLATE_TIME_SHAPES = [
    (re.compile(r"\{\{[^}]*\[\s*:\s*(?:10|16|19)\s*\][^}]*\}\}"),
     "slicing a value to its first 10, 16 or 19 characters"),
    (re.compile(r"""\{\{[^}]*replace\(\s*["']T["']"""),
     'swapping the ISO "T" for a space'),
]


@pytest.mark.parametrize("pattern,name", _TEMPLATE_TIME_SHAPES)
def test_no_template_formats_a_time_by_hand(pattern, name):
    """The guard the owner's report earned.

    Four copies of `{{ summary.last_run[:16].replace("T", " ") }}` sat under the
    source table while this suite was green, because the guard below keys on the
    field's NAME and `last_run` does not end in _at. This one keys on what the
    template DOES, which is the part that cannot be renamed out of view.
    """
    offenders = []
    for template in sorted(TEMPLATES.glob("*.html")):
        if template.name in _TEMPLATE_TIME_EXEMPT:
            continue
        for match in pattern.finditer(template.read_text(encoding="utf-8")):
            offenders.append(f"{template.name}: {match.group(0)[:70]}")
    assert not offenders, (
        f"these templates format a time by hand ({name}): {offenders}. "
        'Use {% from "_time.html" import stamp %} and stamp(value) — one '
        "formatter, so no page can disagree with another (§6.7).")


def test_every_template_that_renders_an_instant_uses_the_macro():
    """The server-side half of the same rule. A page added next month gets
    caught here rather than by a reader noticing its times are four hours out."""
    pattern = re.compile(
        r"\{\{[^}]*\b(?:[a-z_]+_at|last_run|next_run|last_success|last_crawl|"
        r"last_seen|last_updated)\b[^}]*\}\}")
    offenders = []
    for template in sorted(TEMPLATES.glob("*.html")):
        if template.name in _TEMPLATE_TIME_EXEMPT:
            continue
        for match in pattern.finditer(template.read_text(encoding="utf-8")):
            if "stamp(" in match.group(0):
                continue
            offenders.append(f"{template.name}: {match.group(0)[:70]}")
    assert not offenders, (
        f"these templates render an instant without the macro: {offenders}. "
        'Use {% from "_time.html" import stamp %} and stamp(value) so every '
        "page converts through the one formatter (§6.7).")


# A template's inline <script> is a third surface, and the one the sweep found
# two live defects in: both jobs.html and logs.html re-rendered a cell that the
# server had already stamped, writing the raw instant back over it. That is
# worse than never converting at all — the page is right until the first poll
# tick, then silently wrong, and because textContent deletes the <time data-utc>
# element, ScrapeXTime.paint() can never repair it on a zone change.
_TEMPLATE_SCRIPT_SINK = re.compile(
    r"\.textContent\s*=\s*[^;\n]*\b(?:[a-z_]+_at|last_run|next_run)\b")


def test_no_template_script_writes_a_raw_instant_into_the_page():
    """A poll must not undo what the macro did."""
    offenders = []
    for template in sorted(TEMPLATES.glob("*.html")):
        source = template.read_text(encoding="utf-8")
        for match in _TEMPLATE_SCRIPT_SINK.finditer(source):
            offenders.append(f"{template.name}: {match.group(0).strip()[:70]}")
    assert not offenders, (
        f"these inline scripts write a raw instant back into the page: "
        f"{offenders}. Use ScrapeXTime.node(value) with replaceChildren/append "
        "— textContent deletes the <time data-utc> element the macro rendered, "
        "so the value reverts to UTC and paint() cannot fix it (§6.7, §6.10).")


def test_the_web_page_shows_the_active_zone_and_offers_no_control(client):
    """The owner's ruling of 2026-07-30, made mechanical from the display side.

    tests/test_settings_live_in_the_extension.py already fails the build if this
    page grows a control. This is the other half: it must still SAY which zone
    is in force, or "display-only" has quietly become "silent".
    """
    body = client.get("/settings").text
    assert "data-time-zone-active" in body, (
        "the web page stopped showing which zone times are in")
    assert "data-time-zone-note" in body
    assert "data-time-zone-select" not in body, (
        "the web page grew a time zone selector. The owner ruled on 2026-07-30 "
        "that the selector lives in the extension and this page displays only "
        "(issue #32 §2.3); see tests/test_settings_live_in_the_extension.py.")


def test_the_panel_is_where_the_zone_is_chosen():
    """§6.1's home, asserted the way the crawl-pace controls are."""
    panel = (EXT / "app.html").read_text(encoding="utf-8")
    assert 'id="ui_time_zone"' in panel, "the zone selector is not in the side panel"
    assert "data-time-zone-select" in panel
    assert 'src="timezone.js"' in panel, "the panel does not load the formatter"


def test_the_two_polls_that_repainted_a_stamped_cell_now_use_the_formatter():
    """The defect the generic guard above is generic ABOUT, named concretely.

    Both pages server-render a time through the macro and then overwrite it on a
    4s poll. Before this, jobs.html wrote `job.finished_at` and logs.html wrote
    `e.logged_at` straight into the cell, so each page was correct until its
    first tick and silently raw UTC afterwards — and because `textContent`
    deletes the <time data-utc> element, a later zone change could not repair
    either one.
    """
    jobs = (TEMPLATES / "jobs.html").read_text(encoding="utf-8")
    assert "ScrapeXTime.node(job.finished_at)" in jobs, (
        "the jobs poll no longer routes the Finished cell through the formatter")
    assert 'replaceChildren(' in jobs, (
        "the jobs poll must replace the cell's CHILDREN — assigning textContent "
        "deletes the <time data-utc> element and paint() cannot repair it")

    logs = (TEMPLATES / "logs.html").read_text(encoding="utf-8")
    assert 'ScrapeXTime.node(value, "datetime")' in logs, (
        "the log tail no longer routes the Time column through the formatter")


def test_the_freshness_line_reads_the_same_on_both_surfaces():
    """One fact, two surfaces, and they disagreed.

    "Last crawled ..." is rendered by the Workspace from _source_list.html and
    by the panel from freshnessLine() in app.js. Both hard-coded the word UTC
    beside a hand-formatted instant, which is what the owner reported under the
    source table. Neither may go back to doing that.
    """
    partial = (TEMPLATES / "_source_list.html").read_text(encoding="utf-8")
    assert "stamp(s.last_success.started_at, zone=true)" in partial
    # The RENDERED text, not the file: a comment may say "UTC" (this one does,
    # explaining the fix), but no expression may be followed by the fixed word
    # again — that is the exact shape the owner reported.
    assert "}} UTC" not in partial, (
        "the workspace freshness line names UTC in fixed text again, beside a "
        "value that is no longer in UTC")

    panel = (EXT / "app.js").read_text(encoding="utf-8")
    assert 'ScrapeXTime.markup(last.started_at, "datetime", {zone: true})' in panel, (
        "the panel's freshness line no longer uses the one formatter")

    page = (TEMPLATES / "source.html").read_text(encoding="utf-8")
    assert page.count("stamp(summary.last_run, zone=true)") == 4, (
        "the source page's own freshness footer is rendered in four places — "
        "the empty state and the populated one, each twice — and all four must "
        "convert, or the owner sees two formats on one page")
