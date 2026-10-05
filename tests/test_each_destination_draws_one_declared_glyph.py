"""Each destination's glyph is declared once, in design/glyph-map.json (#1056).

BEFORE THIS, TWO LISTS AND A WIRE. The engine's `WorkspaceDestination.icon`
(scrapex/ui_manifest.py) named 13 sprite ids and sent them over /api/ui; the
panel's offline fallback in extension/app.js named the same 13 again, and
`ENGINE_CANDIDATES` in extension/releases.js named 6 more. The panel drew
whatever id arrived, against its OWN sprite, and a <use> pointing at an id the
sprite lacks draws nothing and throws nothing. The two products install
separately, so the day one of them renamed a glyph the other drew blanks.

NOW ONE MAP, read by both surfaces from their own synced copy: the panel from the
block tools/sync_design_assets.py writes into extension/app.html, the engine's
templates from scrapex/webui/static/material-icons/glyph-map.json. The owner's
ruling of 2026-10-05 (issue 1056) adds the second half: every glyph id is its
source's own published name by one stated rule, and the map records each glyph's
source, so adding or changing a source has a known rule.

The browser half of the guard is tests/test_the_panel_draws_each_glyph_from_the_map.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scrapex import ui_manifest
from scrapex.ui_manifest import WORKSPACE_DESTINATIONS, WorkspaceDestination

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design"
MAP = DESIGN / "glyph-map.json"
SPRITE = DESIGN / "material-icons.svg"
ENGINE_SPRITE = ROOT / "scrapex" / "webui" / "static" / "material-icons" / "material-icons.svg"
ENGINE_MAP = ROOT / "scrapex" / "webui" / "static" / "material-icons" / "glyph-map.json"
PANEL = ROOT / "extension" / "app.html"
PANEL_ICON_PREFIX = "icon-"   # tools/sync_design_assets.py's PANEL_ICON_PREFIX
#: Each source's published name list, frozen at the commit the map records.
NAMES = ROOT / "tests" / "fixtures" / "glyph-source-names"


def _refuse_duplicate_keys(pairs):
    """JSON keeps the LAST of two equal keys without a word, so a destination
    listed twice would draw whichever line came second. Refused here instead."""
    keys = [key for key, _ in pairs]
    twice = sorted({key for key in keys if keys.count(key) > 1})
    assert not twice, f"design/glyph-map.json names these keys twice: {twice}"
    return dict(pairs)


def _read_map(text: str) -> dict:
    return json.loads(text, object_pairs_hook=_refuse_duplicate_keys)


def _the_map() -> dict:
    return _read_map(MAP.read_text(encoding="utf-8"))


def _rule(published: str) -> str:
    """The one naming rule the map's `rule` states: lowercased, `_` written as `-`."""
    return published.lower().replace("_", "-")


def _symbol_ids(text: str) -> list[str]:
    # Whitespace before `id`, as the sync tool matches it, so a `data-id` is not one.
    return re.findall(r'<symbol\b[^>]*?\sid="([^"]+)"', text)


def _normalised(path: Path) -> bytes:
    # `* text=auto`: Windows checks out CRLF. Never compare a repo file's raw bytes.
    return path.read_bytes().replace(b"\r\n", b"\n")


def _engine_candidates_block() -> str:
    source = (ROOT / "extension" / "releases.js").read_text(encoding="utf-8")
    found = re.search(r"export const ENGINE_CANDIDATES = \[(.*?)\n\];", source, re.S)
    assert found, "extension/releases.js no longer declares ENGINE_CANDIDATES as one array"
    return found.group(1)


def _panel_destinations() -> list[str]:
    source = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    found = re.search(r"const PANEL_DESTINATIONS = new Set\(\[([^\]]*)\]\);", source)
    assert found, "extension/app.js no longer declares PANEL_DESTINATIONS as one Set"
    return re.findall(r'"([\w-]+)"', found.group(1))


def _published_names(key: str, source: dict) -> set[str]:
    """The names `source` publishes, from its frozen list, which must be the list
    read at the address (and so the commit) the map records."""
    lines = (NAMES / f"{key}.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"# published_names: {source['published_names']}", (
        f"tests/fixtures/glyph-source-names/{key}.txt was not read where the map says "
        f"source {key!r}'s names are published; re-read it from {source['published_names']}")
    names = [line for line in lines if not line.startswith("#")]
    assert len(names) > 1000, f"{key}.txt holds {len(names)} names; it is not a source's list"
    return set(names)


def _fallback_navigation_block() -> str:
    source = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    found = re.search(r"const WORKSPACE_NAVIGATION_FALLBACK = \[(.*?)\n\];", source, re.S)
    assert found, "extension/app.js no longer declares WORKSPACE_NAVIGATION_FALLBACK as one array"
    return found.group(1)


# ---- the map itself ----------------------------------------------------------

def test_the_map_states_its_rule_and_every_table_it_is_read_for():
    glyphs = _the_map()
    assert set(glyphs) == {"about", "rule", "sources", "fallback", "destinations", "engines"}
    assert "lowercased" in glyphs["rule"] and "_ written as -" in glyphs["rule"], (
        "the map's header no longer states the naming rule its ids follow")
    for key, source in glyphs["sources"].items():
        assert {"title", "licence", "repository", "commit", "published_names", "file",
                "glyphs"} <= set(source), f"source {key!r} does not say where its names come from"
        assert re.fullmatch(r"[0-9a-f]{40}", source["commit"]), (
            f"source {key!r} names no commit, so its published names cannot be re-read")
        assert source["commit"] in source["published_names"], (
            f"source {key!r}'s name list is not read at the commit it records")


def test_every_glyph_id_is_its_sources_published_name_by_the_one_rule():
    """The owner's ruling: an id is its source's own name, so a new or changed
    source has a known rule. The map records the name as the source publishes it
    and the id is DERIVED, never typed, so the rule cannot be bent per glyph. Each
    recorded name is looked up in the list its source publishes at the recorded
    commit (tests/fixtures/glyph-source-names/), so a glyph credited to a source
    that does not publish it fails here, whatever its spelling."""
    sources = _the_map()["sources"]
    owner: dict[str, str] = {}
    for key, source in sources.items():
        published_names = _published_names(key, source)
        assert sorted(set(source["glyphs"]) - published_names) == [], (
            f"source {key!r} does not publish these names at {source['commit']}")
        for published in source["glyphs"]:
            # Material publishes snake_case and Tabler kebab-case; neither
            # publishes a capital, a space or anything the rule would mangle.
            assert re.fullmatch(r"[a-z0-9]+([_-][a-z0-9]+)*", published), (
                f"{key} glyph {published!r} is not a name the rule can carry")
            glyph_id = _rule(published)
            assert glyph_id not in owner, (
                f"{glyph_id!r} is claimed by {owner[glyph_id]} and {key}: two glyphs "
                "share an id. The map's rule proposes prefixing the later source's key.")
            owner[glyph_id] = key
    assert len(owner) == sum(len(s["glyphs"]) for s in sources.values())


def test_the_sprite_carries_exactly_the_glyphs_the_map_records():
    """Every symbol has a recorded source, and every recorded glyph is drawn."""
    sources = _the_map()["sources"]
    in_sprite = [_rule(name) for source in sources.values()
                 if source["file"] == SPRITE.name for name in source["glyphs"]]
    symbols = _symbol_ids(SPRITE.read_text(encoding="utf-8"))
    assert len(symbols) == len(set(symbols)), (
        f"{SPRITE.name} carries an id twice; <use> draws the first and hides the other")
    assert sorted(symbols) == sorted(in_sprite), (
        "the sprite and the map disagree; symbols with no recorded source: "
        f"{sorted(set(symbols) - set(in_sprite))}, recorded but not drawn: "
        f"{sorted(set(in_sprite) - set(symbols))}")
    # A source that is not in the sprite is a file of its own, named by its id.
    for key, source in sources.items():
        if source["file"] == SPRITE.name:
            continue
        assert [f"{_rule(name)}.svg" for name in source["glyphs"]] == [source["file"]], (
            f"source {key!r}'s file is not named by its glyph's id")
        assert (DESIGN / source["file"]).is_file(), f"design/{source['file']} is missing"


# ---- one declaration per destination ----------------------------------------

def test_every_destination_and_every_candidate_engine_has_an_entry():
    """One entry per key, and no entry for a key nobody draws. As SETS: neither
    reader uses the map's order (a lookup by key in scrapex/ui_manifest.py and
    extension/app.js), so the sidebar's order stays in ui_manifest.py and the
    Engine page's in releases.js, and reordering either needs no edit here. The
    map's own keys cannot repeat (_refuse_duplicate_keys); the lists' can."""
    glyphs = _the_map()
    destinations = [d.key for d in WORKSPACE_DESTINATIONS]
    assert len(destinations) == len(set(destinations)), (
        "scrapex/ui_manifest.py lists a destination twice")
    assert set(glyphs["destinations"]) == set(destinations), (
        "the map's destinations are not the engine's: "
        f"unmapped {sorted(set(destinations) - set(glyphs['destinations']))}, "
        f"mapped for nothing {sorted(set(glyphs['destinations']) - set(destinations))}")
    candidates = re.findall(r'\bid: "([\w-]+)"', _engine_candidates_block())
    assert candidates, "no candidate id was read from extension/releases.js"
    assert len(candidates) == len(set(candidates)), (
        "extension/releases.js's ENGINE_CANDIDATES lists an id twice: "
        f"{sorted({c for c in candidates if candidates.count(c) > 1})}")
    assert set(glyphs["engines"]) == set(candidates), (
        "the map's engines are not extension/releases.js's ENGINE_CANDIDATES: "
        f"unmapped {sorted(set(candidates) - set(glyphs['engines']))}, "
        f"mapped for nothing {sorted(set(glyphs['engines']) - set(candidates))}")


def test_every_mapped_glyph_is_in_the_sprite_each_surface_ships():
    """A mapped id the sprite lacks would draw nothing on that surface."""
    glyphs = _the_map()
    mapped = {glyphs["fallback"], *glyphs["destinations"].values(), *glyphs["engines"].values()}
    panel = set(_symbol_ids(PANEL.read_text(encoding="utf-8")))
    engine = set(_symbol_ids(ENGINE_SPRITE.read_text(encoding="utf-8")))
    assert sorted(g for g in mapped if PANEL_ICON_PREFIX + g not in panel) == [], (
        "extension/app.html's sprite lacks these mapped glyphs")
    assert sorted(g for g in mapped if g not in engine) == [], (
        "the engine's sprite lacks these mapped glyphs")


def test_each_surface_carries_the_map_design_declares():
    """The copies are the map, not a third and fourth declaration of it."""
    assert _normalised(ENGINE_MAP) == _normalised(MAP), (
        "scrapex/webui/static/material-icons/glyph-map.json is stale; run "
        "tools/sync_design_assets.py")
    block = re.search(r'<script type="application/json" id="glyph-map">\n(.*?)</script>',
                      PANEL.read_text(encoding="utf-8"), re.S)
    assert block, "extension/app.html carries no glyph map; run tools/sync_design_assets.py"
    assert block.group(1) == MAP.read_text(encoding="utf-8").replace("\r\n", "\n"), (
        "extension/app.html's glyph map is stale; run tools/sync_design_assets.py")


def test_no_second_list_names_a_destinations_glyph():
    """The two lists this replaced, and the reads that trusted the wire."""
    assert "icon:" not in _fallback_navigation_block(), (
        "extension/app.js's offline navigation names glyphs again; the map does")
    assert "icon:" not in _engine_candidates_block(), (
        "extension/releases.js's ENGINE_CANDIDATES names glyphs again; the map does")
    app = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    assert re.findall(r"\b(?:destination|engine)\.icon\b", app) == [], (
        "extension/app.js draws a destination's or an engine's glyph from a field "
        "instead of from the map")
    # In a Jinja expression only: `ScrapeXUI.icon(...)` in a page's own script is
    # the client-side icon helper, not a destination's field.
    for template in sorted((ROOT / "scrapex" / "webui" / "templates").glob("*.html")):
        text = template.read_text(encoding="utf-8")
        assert re.findall(r"\{[{%][^}]*?\.icon\b", text) == [], (
            f"{template.name} reads a destination's legacy icon field")


def test_the_rail_tab_of_each_panel_destination_draws_the_maps_glyph():
    """Data and Settings are the panel's own pages: its Workspace menu leaves them
    out (extension/app.js PANEL_DESTINATIONS) because the rail carries them. Their
    rail tab is the panel's entry for that destination, so it draws the map's glyph,
    written by tools/sync_design_assets.py from the data-glyph-destination it
    carries. A tab without the attribute would keep a glyph of its own."""
    glyphs = _the_map()["destinations"]
    panel = PANEL.read_text(encoding="utf-8")
    keys = _panel_destinations()
    assert keys, "no panel destination was read from extension/app.js"
    for key in keys:
        tab = re.search(rf'<button class="rail-item" id="tab-{key}"[^>]*>(.*?)</button>',
                        panel, re.S)
        assert tab, f"extension/app.html has no rail tab for the panel's own page {key!r}"
        assert re.findall(r"<use\b[^>]*>", tab.group(1)) == [
            f'<use href="#{PANEL_ICON_PREFIX}{glyphs[key]}" data-glyph-destination="{key}">'
        ], f"the rail tab for {key!r} does not draw the map's glyph from the map"
    assert sorted(re.findall(r'data-glyph-destination="([^"]*)"', panel)) == sorted(keys), (
        "data-glyph-destination is carried by something other than the rail tabs of "
        "the panel's own destinations")


# ---- what the sync tool refuses ------------------------------------------------

def _sync_tool(monkeypatch, tmp_path, *, glyph_map: str | None = None,
               panel: str | None = None):
    """tools/sync_design_assets.py, reading a map and a panel written for one test."""
    import tools.sync_design_assets as sync_tool

    root = tmp_path / "root"
    (root / "design").mkdir(parents=True)
    (root / "design" / "glyph-map.json").write_text(
        MAP.read_text(encoding="utf-8") if glyph_map is None else glyph_map,
        encoding="utf-8")
    page = tmp_path / "app.html"
    page.write_text(PANEL.read_text(encoding="utf-8") if panel is None else panel,
                    encoding="utf-8")
    monkeypatch.setattr(sync_tool, "ROOT", root)
    monkeypatch.setattr(sync_tool, "PANEL", page)
    return sync_tool


def test_the_sync_refuses_a_map_that_would_end_the_panels_block_early(monkeypatch, tmp_path):
    """The block carries the map's text verbatim, so `</` in it would close the
    <script> data element inside app.html and the panel would parse half a map."""
    # The map's own fallback, whichever glyph he picks for it, not a copy of it here.
    fallback = f'"fallback": "{_the_map()["fallback"]}'
    text = MAP.read_text(encoding="utf-8").replace(fallback, f"{fallback}</script>")
    assert "</script>" in text
    sync_tool = _sync_tool(monkeypatch, tmp_path, glyph_map=text)
    with pytest.raises(ValueError, match="contains '</'"):
        sync_tool._glyph_map_block()


def test_the_sync_refuses_a_rail_glyph_for_a_destination_the_map_does_not_name(
        monkeypatch, tmp_path):
    panel = PANEL.read_text(encoding="utf-8").replace(
        'data-glyph-destination="data"', 'data-glyph-destination="not-a-destination"')
    sync_tool = _sync_tool(monkeypatch, tmp_path, panel=panel)
    with pytest.raises(ValueError, match="'not-a-destination'.*does not name"):
        sync_tool._rail_glyphs(panel)


def test_the_sync_refuses_a_panel_that_lost_every_rail_glyph(monkeypatch, tmp_path):
    """The #408 shape: with the attribute gone, the rail would drop out of the sync
    and --check would call it current whatever the map said."""
    panel = PANEL.read_text(encoding="utf-8").replace("data-glyph-destination", "data-glyph")
    sync_tool = _sync_tool(monkeypatch, tmp_path, panel=panel)
    with pytest.raises(ValueError, match="lost every data-glyph-destination"):
        sync_tool._rail_glyphs(panel)


def test_the_sync_moves_the_rail_when_the_map_renames_a_destinations_glyph(
        monkeypatch, tmp_path):
    """The rail tab is written from the map, not held equal to it by hand."""
    glyphs = _the_map()
    glyphs["destinations"]["data"] = "view-stream"
    sync_tool = _sync_tool(monkeypatch, tmp_path, glyph_map=json.dumps(glyphs))
    written = sync_tool._rail_glyphs(PANEL.read_text(encoding="utf-8"))
    assert f'<use href="#{PANEL_ICON_PREFIX}view-stream" data-glyph-destination="data">' in written


# ---- the engine's templates --------------------------------------------------

def _environments():
    from scrapex.extract.api import TEMPLATES as extraction
    from scrapex.webui.app import TEMPLATES as workspace
    return [pytest.param(workspace, id="webui"), pytest.param(extraction, id="extract")]


def _sidebar(templates) -> dict[str, str]:
    """{label: the sprite id its sidebar link draws}, from base.html as rendered."""
    html = templates.get_template("base.html").render(source_key=None, tab="overview")
    nav = re.search(r'<nav class="wstabs".*?</nav>', html, re.S)
    assert nav, "base.html no longer renders the sidebar as nav.wstabs"
    links = re.findall(
        r'<a href="[^"]*" title="([^"]+)"[^>]*>\s*<svg[^>]*>\s*<use href="[^"#]*#([^"]*)"',
        nav.group(0))
    assert links, "base.html's sidebar draws no glyph at all"
    return dict(links)


def _engine_reads(monkeypatch, tmp_path, glyphs: dict) -> Path:
    """Point the engine at a map written for one test; returns where it is."""
    copy = tmp_path / "glyph-map.json"
    copy.write_text(json.dumps(glyphs), encoding="utf-8")
    monkeypatch.setattr(ui_manifest, "GLYPH_MAP_PATH", copy)
    return copy


@pytest.mark.parametrize("templates", _environments())
def test_the_sidebar_draws_the_maps_glyph_and_not_the_legacy_field(templates, monkeypatch,
                                                                    tmp_path):
    """Point every destination at a glyph its legacy field does not name, and the
    sidebar must follow the map. While the two agree, a sidebar reading the field
    would pass any check that compared it with the map."""
    moved = {d.key: ("check" if d.icon != "check" else "add") for d in WORKSPACE_DESTINATIONS}
    _engine_reads(monkeypatch, tmp_path, {**_the_map(), "destinations": moved})
    drawn = _sidebar(templates)
    assert drawn == {d.label: moved[d.key] for d in WORKSPACE_DESTINATIONS}


@pytest.mark.parametrize("templates", _environments())
def test_a_running_engine_draws_the_map_on_disk_now(templates, monkeypatch, tmp_path):
    """The sprite beside the map and the templates are read from disk live, and
    "Restart needed" (scrapex/provenance.py) watches only loaded modules. So a map
    the engine had cached would keep drawing ids a sync had renamed in the sprite,
    as empty <use>s, with no badge to say why. The map is read on every render."""
    glyphs = _the_map()
    copy = _engine_reads(monkeypatch, tmp_path, glyphs)
    assert _sidebar(templates)["Data"] == glyphs["destinations"]["data"]
    glyphs["destinations"]["data"] = "view-stream"
    copy.write_text(json.dumps(glyphs), encoding="utf-8")
    assert _sidebar(templates)["Data"] == "view-stream"


@pytest.mark.parametrize("missing", ["destinations", "fallback"])
def test_the_engine_refuses_a_map_with_no_table_or_no_fallback(missing, monkeypatch, tmp_path):
    """Without its destinations table every row would draw the fallback, and without
    a fallback a newer destination would draw nothing; either is refused by name."""
    glyphs = _the_map()
    del glyphs[missing]
    _engine_reads(monkeypatch, tmp_path, glyphs)
    with pytest.raises(ValueError, match="no destinations table or no fallback"):
        ui_manifest.glyph_map()
    with pytest.raises(ValueError, match="no destinations table or no fallback"):
        ui_manifest.workspace_navigation_groups()


@pytest.mark.parametrize("templates", _environments())
def test_a_destination_the_map_does_not_know_draws_the_declared_fallback(templates, monkeypatch):
    """A newer engine can add a destination before the map names it. It draws the
    map's declared fallback, never its legacy field and never an empty <use>."""
    # `constructor` too: a key every object answers to, which the map must not.
    added = tuple(WorkspaceDestination(key, f"Added later: {key}", f"/{key}",
                                       "Not in the map yet.", "System", "storage")
                  for key in ("added-later", "constructor"))
    monkeypatch.setattr(ui_manifest, "WORKSPACE_DESTINATIONS",
                        (*WORKSPACE_DESTINATIONS, *added))
    drawn = _sidebar(templates)
    fallback = _the_map()["fallback"]
    assert {d.label: drawn[d.label] for d in added} == {d.label: fallback for d in added}
    assert fallback in _symbol_ids(ENGINE_SPRITE.read_text(encoding="utf-8"))
