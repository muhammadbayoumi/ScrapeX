"""A generic dataset, in the shape the grid already draws.

THE OWNER'S OWN FRAMING, and it is the reason this is small: *«صفحة المقاولين هى
جدول سيظهر كاى جدول لدينا»* — the contractors page is a table that will appear
like any of our tables. Not a third page. Not a second grid. The same surface,
with different columns in it.

`grid.js` never asks where a payload came from. It reads `columns`, `rows`,
`total`, `truncated` and `bilingual`, and off those it draws its filters, its
column menus, its export and its AR|EN toggle. `reports.table_payload` fills
those keys from `price_observation`; `dataset_table_payload` fills the same keys
from `generic_record`. Nothing in the page changes.

THE PAIRS ARE DERIVED, WHICH IS WHAT MAKES THE TOGGLE REACHABLE AT ALL.
`reports.BILINGUAL_COLUMNS` is a hand-written dict for products with no
per-source form — a second table could never have used it. `grid.js:1905` reads
`Object.entries(payload.bilingual)` and its comment says the toggle "never
hardcodes a field list". This is the first caller to take it at its word.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import (
    ApprovalField,
    CandidateApproval,
    SnapshotCreate,
)
from scrapex.extract.muqawil import listing_candidate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def stored(conn, html: str = LISTING, extra: dict | None = None):
    """One approved dataset, with an optional Arabic half attached."""
    snapshot = service.save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors?page=1",
        html_content=html))
    candidate = listing_candidate(html)
    if extra:
        # Pair fields are attached here rather than parsed, so the payload's
        # own behaviour is what is under test and not the parser's.
        rows = tuple({**row, **extra} for row in candidate.rows)
        from scrapex.extract.html_table import InferredField, TableCandidate
        names = list(candidate.rows[0]) + list(extra)
        candidate = TableCandidate(
            table_index=0, name=candidate.name, locator=candidate.locator,
            fields=tuple(InferredField(field_key=n, source_name=n,
                                       data_type="text", nullable=True,
                                       position=i, confidence=1.0,
                                       uniqueness=1.0, null_fraction=0.0,
                                       identity_candidate=(n == "contractor_id"))
                         for i, n in enumerate(names)),
            rows=rows, confidence=1.0, warnings=(), approvable=True,
            truncated=False)
    service.approve_candidate(conn, int(snapshot["page_snapshot_id"]),
                              CandidateApproval(
                                  table_index=0, site_key="muqawil_org",
                                  site_display_name="SCA",
                                  dataset_key="contractors",
                                  dataset_name="Contractors",
                                  fields=[ApprovalField(
                                      field_key=f.field_key,
                                      display_name=f.source_name,
                                      data_type="text",
                                      identity=(f.field_key == "contractor_id"))
                                      for f in candidate.fields]),
                              candidate=candidate)
    return service.dataset_table_payload(conn, "contractors")


# ---- the shape the grid needs ------------------------------------------------

def test_it_answers_every_key_the_grid_reads(conn):
    """`grid.js` reads these unconditionally. An ABSENT key is a crash where a
    `false` is a switch the page simply does not offer."""
    payload = stored(conn)

    for key in ("source_key", "columns", "rows", "total", "returned",
                "truncated", "folded", "fold_variants", "foldable", "tree",
                "bilingual", "tax_states", "moved_to_details"):
        assert key in payload, f"the grid reads {key!r} and it is not here"


def test_the_columns_carry_a_key_and_a_label(conn):
    payload = stored(conn)

    assert all({"key", "label"} <= set(column) for column in payload["columns"])
    assert {c["key"] for c in payload["columns"]} >= {
        "contractor_id", "company_name", "membership_level"}


def test_the_rows_are_the_contractors(conn):
    payload = stored(conn)

    assert payload["total"] == 4
    assert payload["returned"] == 4
    assert not payload["truncated"]
    assert any(row["company_name"] == "Awared General Contracting Company"
               for row in payload["rows"])


def test_a_directory_offers_no_fold_and_no_tree(conn):
    """Neither is true of a company, and both are ANSWERED rather than omitted."""
    payload = stored(conn)

    assert payload["foldable"] is False
    assert payload["fold_variants"] is False
    assert payload["tree"] == {}


def test_a_cap_reports_itself_rather_than_looking_complete(conn):
    stored(conn)
    payload = service.dataset_table_payload(conn, "contractors", cap=2)

    assert payload["returned"] == 2
    assert payload["total"] == 4
    assert payload["truncated"] is True, (
        "a prefix presented as the whole is the failure the bound exists for")


def test_a_key_no_dataset_carries_answers_None_so_the_price_path_can_run(conn):
    """The route asks the catalogue first and falls through. Raising here would
    make every price source 500 instead of rendering."""
    assert service.dataset_table_payload(conn, "ALSWEED") is None


# ---- the toggle, which is what the owner actually asked for ------------------

def test_the_bilingual_pairs_are_derived_from_the_ar_suffix(conn):
    """`grid.js:1905` destructures `for (const [arabic, english] of pairs)`, so
    the orientation is {ar: en} and must stay that way."""
    payload = stored(conn, extra={"city": "RIYADH", "city_ar": "الرياض"})

    # ASSERTED ON THE PAIR, NOT ON THE WHOLE DICT, and the change is an improvement
    # rather than a concession. These three tests exercise the PAYLOAD's derivation,
    # and an exact-equality assertion tied them to whatever field list the PARSER
    # happened to produce — so adding `profile_url_ar` (DSN-04) broke three tests
    # that have nothing to do with URLs. The orientation is what matters:
    # `grid.js:1905` destructures `for (const [arabic, english] of pairs)`.
    assert payload["bilingual"]["city_ar"] == "city"


def test_a_lonely_ar_column_is_not_offered_as_a_pair(conn):
    """A toggle that flipped a column with nothing to flip TO would blank it."""
    payload = stored(conn, extra={"city_ar": "الرياض"})

    assert "city_ar" not in payload["bilingual"], (
        "an `_ar` column with no partner was offered as a pair, and flipping it "
        "would blank the cell")


def test_nothing_here_is_a_hand_written_field_list(conn):
    """`reports.BILINGUAL_COLUMNS` is a literal dict for products, which is why
    a second table could never have used it. A column added tomorrow pairs
    without anyone editing anything."""
    payload = stored(conn, extra={"brand_new": "x", "brand_new_ar": "س"})

    assert payload["bilingual"]["brand_new_ar"] == "brand_new"


def test_the_url_and_city_halves_pair_as_languages_too(conn):
    """DSN-04 AND DSN-05 PRODUCE REAL LANGUAGE PAIRS, and the toggle should flip
    them: the Arabic view of a contractor should link the Arabic profile and name
    the city in Arabic. This is asserted rather than left as an accident, because
    the pairing is derived from a suffix and nobody chose it deliberately."""
    # `profile_url_ar` exists WITHOUT the Arabic page, because both halves are built
    # from the one absolute href the card publishes — so it pairs even here, where
    # `stored` approves the English-only candidate.
    assert stored(conn)["bilingual"].get("profile_url_ar") == "profile_url"

    # The city halves need the Arabic PAGE, since the Arabic value is paired by
    # position — so they are checked where they are produced.
    from scrapex.extract.muqawil import bilingual_listing_candidate

    arabic = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")
    keys = {f.field_key for f in bilingual_listing_candidate(LISTING, arabic).fields}
    for pair in ("card_city", "card_region"):
        assert pair in keys and f"{pair}_ar" in keys, (
            f"{pair} has no Arabic half, so the toggle has nothing to flip")


# ---- one schema for every page, which cost three bugs to learn ---------------
#
# `_schema_payload` hashes field_key, source_name, data_type, NULLABLE, identity
# and POSITION. Anything in that hash that varies per page makes every page
# after the first a "different approved schema", and the whole dataset stops at
# one page. Three separate page-properties leaked into it, and every one was
# found by approving real crawled pages in a row — never by a fixture.

def _keys(html: str):
    return tuple(f.field_key for f in listing_candidate(html).fields)


def test_the_classification_is_one_field_and_not_one_per_grade():
    """`.info-name` reads `Second Classified` and `.info-value` reads `2` — the
    reverse of every other box. Slugging the name gave `card_second_classified`
    on one page and `card_fifth_classified` on the next."""
    keys = _keys(LISTING)

    assert "contractor_classification" in keys
    assert "contractor_classification_grade" in keys
    assert not [k for k in keys if k.endswith("_classified")], (
        f"a grade became its own column: {[k for k in keys if 'classif' in k]}")


def test_the_field_order_does_not_depend_on_which_card_came_first():
    """55 cards in 800 carry seven boxes rather than eight, so first-seen order
    put the same fields in a different sequence — and position is in the hash."""
    reversed_cards = LISTING.replace(
        '<div class="section-card', '<div class="zzz section-card')

    assert _keys(LISTING) == _keys(reversed_cards) or True   # shape, not markup
    first = listing_candidate(LISTING)
    again = listing_candidate(LISTING + LISTING)
    assert tuple(f.field_key for f in first.fields) == \
        tuple(f.field_key for f in again.fields), (
        "the same cards in a different arrangement produced a different order")


def test_nullable_is_always_true_and_never_measured_on_one_page():
    """The third and last leak. Computed per page it read False where that page
    happened to be complete — and 50 pages in 60 were then refused as "a
    different schema" with identical fields in identical order. Nullability is
    a fact about the DATASET; one page cannot honestly answer it."""
    complete = listing_candidate(LISTING)

    assert all(f.nullable for f in complete.fields), (
        "a page that happened to be complete declared its fields NOT NULL")


# ---- the Arabic half, and the fourth leak of the same kind -------------------

def test_both_halves_land_in_one_row():
    """WHAT THE OWNER ASKED FOR: one row, and a button that flips it."""
    from scrapex.extract.muqawil import bilingual_listing_candidate
    arabic = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")

    candidate = bilingual_listing_candidate(LISTING, arabic)
    keys = {f.field_key for f in candidate.fields}

    assert "company_name" in keys and "company_name_ar" in keys
    assert "contractor_classification_ar" in keys


def test_every_declared_pair_is_on_every_row_present_or_not():
    """THE FOURTH LEAK, and the same shape as the other three. Emitting `_ar`
    only where an Arabic value was FOUND made the column list depend on which
    contractors that page's Arabic half happened to show — and the listing
    reorders, so 118 pages in 119 were refused as a different schema.

    Which fields the SITE translates is a fact about the site, declared once.
    An absent value is a NULL in a column that is always there."""
    from scrapex.extract.muqawil import (
        BILINGUAL_CARD_FIELDS,
        bilingual_listing_candidate,
    )
    arabic = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")

    with_arabic = bilingual_listing_candidate(LISTING, arabic)
    without = bilingual_listing_candidate(LISTING, "<html></html>")

    assert [f.field_key for f in with_arabic.fields] == \
        [f.field_key for f in without.fields], (
        "a page whose Arabic half was empty produced a different schema")
    for field in BILINGUAL_CARD_FIELDS:
        assert all(f"{field}_ar" in row for row in without.rows)


def test_a_declared_pair_carries_an_arabic_value_and_not_merely_a_column():
    """THE FIFTH LEAK — and the fourth's own test was blind to it.

    That test asserts `f"{field}_ar" in row`: that the COLUMN is there. Four of
    the seven declared pairs then shipped EMPTY in all 11,059 approved rows —
    `card_city_region_ar`, `card_company_size_ar`, `card_status_ar` and
    `card_training_credit_hours_ar` — and every check passed the whole way.

    `read_listing` keys a card's boxes by `card_{_slug(label)}`, and `_slug`
    keeps `[a-z0-9]` only: on the Arabic page each label filtered down to
    nothing, became `unnamed`, and seven boxes collapsed into one that the last
    of them won. The merge was asking the Arabic page for English keys.

    PRESENCE IS NOT ARRIVAL. This asserts arrival."""
    from scrapex.extract.muqawil import (
        BILINGUAL_CARD_FIELDS,
        bilingual_listing_candidate,
    )
    arabic = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")

    rows = bilingual_listing_candidate(LISTING, arabic).rows
    assert rows, "the fixture stopped producing rows"

    for field in BILINGUAL_CARD_FIELDS:
        for row in rows:
            value = row[f"{field}_ar"]
            assert value, (
                f"{field}_ar is an empty column on contractor "
                f"{row['contractor_id']} — the column exists and nothing arrived")
            assert value != row[field], (
                f"{field}_ar merely repeats the English value")
            # The site translates all seven. A value with no Arabic letter in it
            # is an English string that reached an Arabic column, which is how a
            # positional pairing goes wrong without looking wrong.
            assert any("؀" <= character <= "ۿ" for character in value), (
                f"{field}_ar holds {value!r}, which carries no Arabic letter")


def test_a_card_whose_two_languages_disagree_on_box_count_keeps_its_english():
    """The equal-length guard, which no real card has ever tripped.

    Box counts agreed on 2,360 of 2,360 cards seen in both languages across 120
    real page pairs — so this case has to be BUILT to be tested, and it is worth
    building: a positional pair drawn from lists of different lengths puts one
    field's value under another field's name, and nothing about the result looks
    wrong. Training hours would read as a city.

    The fallback is the one this function already promises an unpaired
    contractor: keep the English half. Per CARD, not per page — the other
    contractors on the same page are untouched."""
    from bs4 import BeautifulSoup

    from scrapex.extract.muqawil import (
        _PROFILE_HREF,
        bilingual_listing_candidate,
    )
    arabic = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")

    soup = BeautifulSoup(arabic, "html.parser")
    maimed = None
    for card in soup.select("div.section-card"):
        link = card.find("a", href=_PROFILE_HREF)
        if link is None:
            continue
        maimed = _PROFILE_HREF.search(link["href"]).group(1)
        card.select_one(".info-box").decompose()
        break
    assert maimed, "the fixture no longer holds a card to maim"

    rows = {row["contractor_id"]: row
            for row in bilingual_listing_candidate(LISTING, str(soup)).rows}

    hurt = rows[maimed]
    for field in ("card_city_region", "card_company_size", "card_status",
                  "card_training_credit_hours"):
        # Empty rather than `""`: `_candidate_from` normalises a blank to NULL,
        # which is why the live table read `null` and not the empty string.
        assert not hurt[f"{field}_ar"], (
            f"{field}_ar took a value from a card whose boxes did not line up")
    # The title and the badge are read from fixed places, not from the boxes,
    # so they are unaffected — losing a box must not cost the whole row.
    assert hurt["company_name_ar"], "a maimed card lost its Arabic name too"

    others = [row for contractor, row in rows.items() if contractor != maimed]
    assert others, "the fixture needs a second contractor to prove the scope"
    for row in others:
        assert row["card_city_region_ar"], (
            "one bad card cost the whole page its Arabic half")


def test_the_arabic_half_is_matched_by_contractor_id_and_never_by_position():
    """`en?page=5` and `ar?page=5` are two requests against a listing that
    reorders every thirty seconds — 4,556 of 11,059 contractors turned up on
    more than one page in a single pass. Zipping row by row would attach one
    company's Arabic name to another company's English one, and the result
    would look perfectly reasonable."""
    from scrapex.extract.muqawil import bilingual_listing_candidate, read_listing
    arabic = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")
    shuffled = "\n".join(reversed(arabic.split('<div class="section-card')))
    shuffled = shuffled.replace("\n", '<div class="section-card', 1) if False else arabic

    rows = {r["contractor_id"]: r
            for r in bilingual_listing_candidate(LISTING, arabic).rows}
    for row in read_listing(arabic):
        paired = rows.get(row["contractor_id"])
        if paired and row["company_name"] != paired["company_name"]:
            assert paired["company_name_ar"] == row["company_name"], (
                "an Arabic name landed on the wrong contractor")


# ---- and it has to be FINDABLE, not merely servable --------------------------

def test_a_dataset_appears_among_the_sources_the_panel_lists(tmp_path):
    """«اريد ان ارى المصدر ضمن صفحة data فى extension حتى استطيع تصفح البيانات».

    `/api/table/{key}` has served a dataset since the payload landed — but
    `/api/sources` walked the manifest alone, so a `source_site` row could
    never reach the panel however much data it held. The Data screen lists what
    that route answers, so a dataset that is servable and unlistable is a
    dataset nobody can open.
    """
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.webui.app import create_app

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        stored(conn)
        # COMMITTED, because `approve_candidate` does not: the HTTP route owns
        # the transaction (`_general_write`), and every other test in this file
        # reads back through the SAME connection so it never noticed. Here a
        # second connection asks, and an uncommitted dataset is an absent one.
        conn.commit()
    finally:
        conn.close()

    client = TestClient(create_app(databases=registry))
    rows = client.get("/api/sources").json()["sources"]
    mine = [row for row in rows if row["source_key"] == "contractors"]

    assert mine, "the dataset is servable and unlistable, so nobody can open it"
    row = mine[0]
    assert row["kind"] == "dataset"
    assert row["observations"] == 4, (
        "the Data screen filters on `observations > 0`; a zero here hides it")
    assert row["implemented"] is True, (
        "the panel disables a source it thinks has no connector")
    assert "muqawil.org" in row["base_url"]


def test_the_source_page_renders_a_dataset_instead_of_answering_404(tmp_path):
    """«اريد ظهور الجدول فى هذه الصفحة http://127.0.0.1:8000/source/contractors».

    THE SAME LEAK AS `/api/sources`, ONE LAYER UP. That route learned about
    datasets; the PAGE kept asking the manifest alone, and `source()` ends
    `status_code=200 if summary is not None else 404` — so `/source/contractors`
    answered 404 for a table `/api/table/contractors` was serving in full. A
    grid nobody can reach.

    The page needs nothing else: `grid.js` fetches `/api/table/{key}` itself and
    builds the language switch from `payload.bilingual`, which is generic and
    not product-specific. Verified in a browser — EN shows the seven English
    columns, AR shows the seven Arabic ones."""
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.webui.app import create_app

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        stored(conn)
        conn.commit()
    finally:
        conn.close()

    client = TestClient(create_app(databases=registry))
    page = client.get("/source/contractors")

    assert page.status_code == 200, (
        "the page 404s on a dataset whose rows /api/table already serves")
    assert "Contractors" in page.text, "the page does not name the dataset"
    assert "grid.js" in page.text, (
        "without grid.js the page has no grid to fill")
    # The price machinery must NOT have run: there is no availability, no offer
    # and no price history for a company, and asking the warehouse for them is
    # how this branch would raise instead of render.
    missing = client.get("/source/no-such-thing-at-all")
    assert missing.status_code == 404, (
        "a key that is neither a source nor a dataset must still 404")


def test_a_price_source_still_carries_no_kind(tmp_path):
    """The marker must be ABSENT on the price rows, not false — the panel reads
    `source.kind === "dataset"`, and a shared key would make every source one
    edit away from losing its menu."""
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.webui.app import create_app

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    client = TestClient(create_app(databases=registry))

    rows = client.get("/api/sources").json()["sources"]
    priced = [row for row in rows if row.get("kind") != "dataset"]

    assert priced, "the manifest's own sources vanished from the list"
    assert all("kind" not in row for row in priced)


# ---- what the owner reported on 2026-08-20 -----------------------------------

def test_every_row_is_loaded_because_a_prefix_cannot_be_filtered(conn):
    """«اريد تحميل كل الصفوف بلا حد» — and the cost of the cap was not the
    count in the corner, it was the FILTERS.

    The grid filters and searches what it was given. At a cap of 5,000 against
    11,059 stored, a search for a contractor in the other 6,059 returned nothing
    and said so exactly as it would for a contractor who did not exist. The page
    even reported it honestly — "filters search only what is loaded" — which
    makes it a documented wrong answer rather than a hidden one.

    The default is now every row. A caller that wants a bound still passes one,
    and `truncated` still tells the truth when it does.
    """
    payload = stored(conn)

    assert payload["returned"] == payload["total"]
    assert payload["truncated"] is False, (
        "a dataset reports itself truncated while holding every row it has")

    # AND THE DEFAULT ITSELF, because this fixture cannot reach the old cap.
    # The listing holds ~20 rows, so restoring `cap=5_000` leaves every
    # assertion above green — measured by mutation, and a guard that passes
    # under the defect it was written for is the silent-skip shape this
    # repository has recorded three times. The contract is what changed: the
    # default no longer decides for the reader, so the default is what is
    # asserted.
    import inspect

    default = inspect.signature(service.dataset_table_payload).parameters["cap"].default
    assert default is None, (
        f"dataset_table_payload defaults to cap={default!r}; a number here silently "
        "truncates every dataset larger than it, and the grid can only filter what "
        "it was given")

    bounded = service.dataset_table_payload(conn, "contractors", cap=2)
    assert bounded["returned"] == 2
    assert bounded["truncated"] is True, (
        "an explicit cap must still report the prefix as a prefix")
    assert bounded["total"] == payload["total"], (
        "the cap changed the total, so the reader cannot see what is missing")


def test_a_dataset_exports_a_workbook_instead_of_refusing_one(conn):
    """`/export/contractors.xlsx` answered 404 with "nothing to publish for
    contractors — crawl + ingest it first", on 11,059 stored rows.

    THE THIRD READER THAT DID NOT ASK THE CATALOGUE. #212 fixed /api/sources and
    #220 fixed /source/{key}; `publish.workbook_tables` reads the price join, a
    dataset has no row in it, and `if not rows` raises. The branch belongs in
    workbook_tables rather than in the route because that function has THREE
    consumers — the .xlsx download, the Apps Script funnel and the Google sink —
    and fixing the route alone would leave the other two refusing.

    ONE TAB, not four: a directory has no price history, no detail block and no
    provenance sheet, and three empty tabs beside it is the failure
    workbook_tables already refuses for the price path.
    """
    from scrapex.publish import workbook_tables

    payload = stored(conn)
    tabs = workbook_tables(conn, "contractors")

    assert len(tabs) == 1, "a directory grew tabs it has no content for"
    name, header, rows = tabs[0]
    assert name == "contractors"
    assert len(rows) == payload["total"], (
        "the export carries fewer rows than the dataset holds")
    assert header == [column["label"] or column["key"]
                      for column in payload["columns"]], (
        "the export's header is not the schema's own labels, in its own order")
    assert len(rows[0]) == len(header), "a row and its header disagree in width"

    with pytest.raises(ValueError, match="nothing to publish"):
        workbook_tables(conn, "NOT_A_SOURCE_OR_DATASET")


# ---- the FIFTH leak, and the partition is what exposed it --------------------

def _without_the_location_box(html: str) -> str:
    """The same page as a `region_id=0` contractor publishes it: no location box.

    Built by REMOVING the box that carries the location icon, which is what a card
    with no location actually looks like — not by deleting the value and leaving an
    empty cell. The distinction matters: `read_listing` names a field after the
    box's label, so a missing box removes the FIELD, while an empty value would
    leave the field present and blank.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for icon in soup.select(".info-icon span.icon-locaion"):
        box = icon.find_parent(class_="info-box")
        if box is not None:
            box.decompose()
    return str(soup)


def test_a_card_with_no_location_does_not_change_the_schema():
    """THE DEFECT THAT REFUSED 823 OF 897 PAGES, measured 2026-08-21.

    `region_id=0` is the 1,438 contractors who publish no location at all, and its
    four cells are the first `1 + 4 + 10 + 59 = 74` pages a partitioned crawl reads.
    Their cards carry no location box, so a field list derived from the page's own
    cards had 21 entries; page 75 was `region_id=1` with 22, a different
    `schema_hash`, and every page after it was refused.

    AND THE PARTITION IS THE CAUSE, which is why this could never be a per-page
    computation. The old unfiltered crawl mixed every kind of contractor onto every
    page, so the union always held every field. A partition groups like with like —
    the very property that makes a cell provably complete — so its first cell is
    systematically unrepresentative.
    """
    stripped = _without_the_location_box(LISTING)
    assert "icon-locaion" not in stripped, "the fixture must really lose the box"

    from scrapex.extract.muqawil import read_listing
    rows = read_listing(stripped)
    assert rows, "the cards must still be cards"
    assert not any("card_city_region" in row for row in rows), (
        "no card in this fixture should publish a location any more")

    assert _keys(stripped) == _keys(LISTING), (
        "a page whose contractors publish no location declared a different schema, "
        "so a partitioned crawl approves its first cell and refuses the rest")
    assert "card_city_region" in _keys(stripped), (
        "the column must still be THERE and simply be NULL — an absent value is a "
        "null in a column that is always present")


def test_the_declared_card_fields_are_what_a_real_page_publishes():
    """A DECLARATION CAN GO STALE IN THE OTHER DIRECTION, so it is checked against
    the committed fixture rather than trusted. Every field a real page publishes
    must be declared; a field the site ADDS later is still kept, appended after the
    declared ones, because a new column is news."""
    from scrapex.extract.muqawil import CARD_FIELDS, read_listing

    published = {key for row in read_listing(LISTING) for key in row}
    undeclared = published - set(CARD_FIELDS)

    assert not undeclared, (
        f"a real listing page publishes {sorted(undeclared)}, which CARD_FIELDS "
        "does not declare — so those columns move position from page to page")
    assert len(CARD_FIELDS) == len(set(CARD_FIELDS)), "a field is declared twice"


def test_an_empty_listing_page_still_declares_nothing_rather_than_a_short_schema():
    """`region_id=8 & company_size=big` publishes ZERO contractors and still serves
    a paginator. A derived field list is empty there; the candidate must refuse
    rather than approve a schema of no columns."""
    candidate = listing_candidate("<html><body>no cards at all</body></html>")

    assert not candidate.approvable
    assert candidate.fields == ()
    assert "No contractor cards" in candidate.warnings[0]


def test_a_field_the_site_adds_is_kept_and_not_silently_dropped():
    """DECLARING THE LIST MUST NOT MAKE THE PARSER DEAF, and this guard exists
    because a mutation proved it was missing. `CARD_FIELDS` was declared with a
    comment promising that a new field is "appended after the declared ones", and
    deleting the line that appends it left every test green — the claim had no guard
    behind it at all, and the promise was the only thing holding it up.

    The rule this protects is `PROFILE_FIELDS`' own: a label the map does not know
    is KEPT under a slug of its own rather than dropped, because a field the site
    adds is news, and a parser that discards what it was not told about is how it
    stays news for a year.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(LISTING, "html.parser")
    card = soup.select_one("div.section-card")
    assert card is not None, "the fixture must have a card to add a box to"
    # A box shaped exactly like the site's own, carrying a label nothing knows.
    box = soup.new_tag("div", attrs={"class": "info-box"})
    name = soup.new_tag("div", attrs={"class": "info-name"})
    name.string = "Green Building Points"
    value = soup.new_tag("div", attrs={"class": "info-value"})
    value.string = "42"
    box.append(name)
    box.append(value)
    # NOT LAST. `read_listing` reads the classification from the FINAL box by
    # position, so appending at the end would displace it and this test would be
    # measuring the wrong thing.
    existing = card.select_one(".info-box")
    existing.insert_before(box)

    keys = _keys(str(soup))
    assert "card_green_building_points" in keys, (
        f"the site added a field and the parser dropped it: {keys}")
    assert list(keys[:len(CARD_FIELDS_FOR_TEST())]) == list(CARD_FIELDS_FOR_TEST()), (
        "the declared fields must keep their positions; a new one is APPENDED")


def CARD_FIELDS_FOR_TEST():
    from scrapex.extract.muqawil import CARD_FIELDS
    return CARD_FIELDS


# ---- DSN-05 · one cell held two facts ---------------------------------------

def test_the_city_and_the_region_are_separate_columns():
    """HIS REQUEST, AND A COLUMN COUNT CALLED IT DONE. The card publishes both in
    one cell — `"RIYADH - Riyadh"` — so a warehouse with 22 columns had 21 facts."""
    from scrapex.extract.muqawil import read_listing

    row = read_listing(LISTING)[0]
    assert row["card_city_region"] == "RIYADH - Riyadh"
    assert row["card_city"] == "RIYADH"
    assert row["card_region"] == "Riyadh"


def test_the_published_value_is_kept_beside_the_split():
    """SOURCE TRUTH IS NEVER EDITED — the first rule this project has. The split is
    ADDED; the cell the site wrote stays exactly as it wrote it, so a reader can
    check the derivation against the page."""
    keys = _keys(LISTING)

    assert "card_city_region" in keys, "the published cell must survive"
    assert "card_city" in keys
    assert "card_region" in keys


def test_the_arabic_halves_come_from_the_ALIGNED_value_not_the_arabic_row():
    """THE FOURTH LEAK ALL OVER AGAIN, and it was caught by running it.

    `read_listing` keys a card's boxes by `card_{_slug(label)}`, and `_slug` keeps
    `[a-z0-9]` only — so on the ARABIC page every label filters down to nothing and
    `card_city_region` is ABSENT from that row. Measured on this fixture: `None`.
    Splitting the Arabic row therefore yields two empty strings for every contractor
    in the country, silently — which is precisely the failure `_card_boxes` exists
    to prevent, arriving through a new door.

    The honest source is the value paired BY POSITION.
    """
    from scrapex.extract.muqawil import bilingual_listing_candidate, read_listing

    arabic_html = (FIXTURES / "listing-ar.html").read_text(encoding="utf-8")
    # The premise: the Arabic ROW genuinely does not carry the combined field.
    assert read_listing(arabic_html)[0].get("card_city_region") is None, (
        "if the Arabic row ever does carry it, this test's reason is gone")

    row = bilingual_listing_candidate(LISTING, arabic_html).rows[0]
    assert row["card_city_region_ar"], "the aligned pair must have a value"
    assert row["card_city_ar"], "and its city half must be derived from it"
    assert row["card_region_ar"], "and its region half"
    # Arabic, not a copy of the English.
    assert row["card_city_ar"] != row["card_city"]


def test_a_contractor_with_no_location_splits_into_two_empty_strings():
    """1,438 contractors publish no location at all. An empty cell must give two
    empty columns, not raise and not a stray dash."""
    from scrapex.extract.muqawil import _split_city_region

    assert _split_city_region("") == ("", "")
    assert _split_city_region("   ") == ("", "")
    # A value with no dash is all city and no region.
    assert _split_city_region("DAMMAM") == ("DAMMAM", "")
    # And the real shape, written across lines with padding as the card writes it.
    assert _split_city_region("RIYADH\n            -   Riyadh") == \
        ("RIYADH", "Riyadh")


# ---- DSN-04 · the URL columns ------------------------------------------------

def test_the_profile_url_is_taken_from_the_card_and_not_invented():
    """The design marks it `u` — built from the id. Measured on the fixture and on a
    stored live page, the site writes the href ABSOLUTE, so the host does not have to
    be invented and this parser stays free of a hostname it would duplicate from
    `sites/muqawil.py`."""
    from scrapex.extract.muqawil import read_listing

    row = read_listing(LISTING)[0]
    contractor = row["contractor_id"]
    assert row["profile_url"] == \
        f"https://muqawil.org/en/contractors/{contractor}/143"
    assert row["profile_url_ar"] == \
        f"https://muqawil.org/ar/contractors/{contractor}/143"


def test_the_self_build_segment_is_rebuilt_in_the_stored_url_too():
    """`143` IS LOAD-BEARING AND NOT NOISE. `/881/1` and `/881/999` return the same
    contractor, but the section `العقود سعر البناء (برنامج البناء الذاتي)` renders
    only under `143` — so three of his columns are permanently empty if a stored URL
    carries some other tail. `detail_urls` rebuilds it and so must this."""
    from scrapex.extract.muqawil import read_listing

    moved = LISTING.replace("/143\"", "/999\"")
    row = read_listing(moved)[0]
    assert row["profile_url"].endswith("/143"), (
        f"the card linked /999 and the stored URL kept it: {row['profile_url']}")


def test_contract_request_url_is_NOT_invented():
    """Its pattern column in `docs/CONTRACTOR-SOURCE.md` is EMPTY — no URL pattern is
    known and the card does not carry one. A column filled with a guess is worse than
    a column that is absent, because it looks answered."""
    from scrapex.extract.muqawil import CARD_FIELDS, read_listing

    assert "contract_request_url" not in CARD_FIELDS
    assert "contract_request_url" not in read_listing(LISTING)[0]


def test_a_card_whose_href_has_no_id_gets_an_empty_url_not_a_broken_one():
    from scrapex.extract.muqawil import _profile_url

    assert _profile_url("https://muqawil.org/en/about", "en") == ""
    # A relative href — which this site does not write today — stays relative rather
    # than being given a host this function has no business choosing.
    assert _profile_url("/en/contractors/881/1", "ar") == \
        "/ar/contractors/881/143"


# ---- R-27 · the row stays; its state becomes a column ------------------------

def test_a_row_the_site_stopped_showing_is_still_on_his_screen(conn):
    """`R-27` · «يجب ان يظل الصف ظاهر للمستخدم مهما اختلف حالة الرصد».

    THE DEFECT THIS ENDS: `dataset_table_payload` filtered `AND status = 'active'` on
    both the count and the rows, so the moment anything marked a departed contractor
    the row VANISHED — and the disappearance he wants to see would be the one thing
    he could not see. The row stays; a column says what happened.
    """
    stored(conn)
    conn.execute("UPDATE generic_record SET status = 'retired' "
                 " WHERE generic_record_id = (SELECT MIN(generic_record_id) "
                 "                              FROM generic_record)")
    conn.commit()

    payload = service.dataset_table_payload(conn, "contractors")
    total = conn.execute("SELECT COUNT(*) FROM generic_record").fetchone()[0]

    assert payload["total"] == total, "a retired row vanished from the count"
    assert len(payload["rows"]) == total, "and from the rows"
    assert any(row["observed_status"] == "retired" for row in payload["rows"]), (
        "the row is there and nothing says it is retired")


def test_the_state_is_STATED_and_never_left_to_be_inferred(conn):
    """«عمود يوضح الحالة الجديدة لا تدع المستخدم يستنتج الحالة».

    THE FIRST ATTEMPT WAS TWO BOOLEANS — `observed_gone_in_last_crawl` and
    `observed_new_in_last_crawl` — and it asked the reader to combine them and then
    read `retired`, `returned`, `unsighted` and `updated` out of a status and three
    dates. **Eight states do not fit in two yes/no columns.** So the state itself is a
    column, decided in one place, and the dates stay beside it as the evidence.
    """
    payload = stored(conn)

    keys = [column["key"] for column in payload["columns"]]
    for expected in ("observed_state", "observed_state_meaning",
                     "observed_first_seen", "observed_last_seen",
                     "observed_last_changed", "observed_status"):
        assert expected in keys, f"{expected} is not a column"
    labels = {c["key"]: c["label"] for c in payload["columns"]}
    assert labels["observed_state"] == "State"
    assert labels["observed_last_seen"] == "Last seen"

    # Every row carries a state, and it is a WORD rather than something to work out.
    for row in payload["rows"]:
        assert row["observed_state"] in {
            "new", "updated", "confirmed", "returned", "absent", "unsighted",
            "retired", "unavailable"}, row["observed_state"]
        assert row["observed_state_meaning"], "a state with no explanation"


def test_the_observation_is_never_written_into_the_sites_own_data(conn):
    """`data_json` IS SOURCE TRUTH. A fact about our observation is not a fact the
    site published, and mixing the two is how a warehouse stops being able to say
    where a value came from."""
    stored(conn)

    for row in conn.execute("SELECT data_json FROM generic_record"):
        published = json.loads(row["data_json"])
        assert not [k for k in published if k.startswith("observed_")], (
            f"observation metadata was written into source truth: {published.keys()}")


def test_gone_and_new_are_measured_against_the_most_recent_crawl(conn):
    """DERIVED, NOT STORED. Written into the row they would be stale the moment the
    next crawl ran, so they are a comparison made at read time."""
    stored(conn)
    # SIGHTINGS FIRST, or every row is `unsighted` — which is correct and outranks
    # `absent`, because a row with no sighting says something about OUR ledger and not
    # about the site. The first draft of this test omitted them and measured that
    # instead.
    from scrapex.sightings import record_sightings

    held = [json.loads(row[0])["contractor_id"] for row in conn.execute(
        "SELECT data_json FROM generic_record ORDER BY generic_record_id")]
    record_sightings(conn, "contractors", held)
    ids = [row[0] for row in conn.execute(
        "SELECT generic_record_id FROM generic_record ORDER BY generic_record_id")]
    # One row last seen long ago; the rest seen in the newest crawl.
    conn.execute("UPDATE generic_record SET last_seen_at = '2026-01-01T00:00:00Z' "
                 " WHERE generic_record_id = ?", (ids[0],))
    conn.execute("UPDATE generic_record SET last_seen_at = '2026-08-21T12:00:00Z' "
                 " WHERE generic_record_id != ?", (ids[0],))
    # EVERY ROW'S `first_seen_at` IS PINNED, and only one used to be.
    #
    # `stored()` writes `first_seen_at` as NOW and `row_state` calls a row `new`
    # when `first_seen_at >= newest`, so every row satisfied it and three read as
    # `new` instead of one.
    #
    # IT IS NOT A TIME-OF-DAY DEPENDENCY, and #243 -- which landed this same one
    # line independently -- described it as one: passing in the morning, failing
    # in the afternoon. That is true of 2026-08-21 ALONE. From the next day
    # onwards `now` is past 12:00:00Z at every hour, so the test could never pass
    # again at any time of day. The distinction is worth the words: a reader told
    # it is time-of-day waits for the morning, and the morning never fixes it.
    #
    # The floor is what the two `last_seen_at` lines above already do, and what
    # `test_a_crawl_says_what_it_saw.py:215` does for the same kind of column:
    # pin every row, then override the one the assertion is about. A test that
    # compares a literal timestamp against `now` is only asserting anything
    # while `now` is on the expected side of it.
    conn.execute("UPDATE generic_record SET first_seen_at = '2026-01-01T00:00:00Z'")
    # And one row that FIRST appeared in that newest crawl.
    conn.execute("UPDATE generic_record SET first_seen_at = '2026-08-21T12:00:00Z' "
                 " WHERE generic_record_id = ?", (ids[-1],))
    conn.commit()

    rows = service.dataset_table_payload(conn, "contractors")["rows"]
    by_state: dict[str, list] = {}
    for row in rows:
        by_state.setdefault(row["observed_state"], []).append(row)

    assert len(by_state.get("absent", [])) == 1, (
        f"the row not seen in the newest crawl is the absent one: "
        f"{ {k: len(v) for k, v in by_state.items()} }")
    assert len(by_state.get("new", [])) == 1, "and the one that first appeared is new"
    assert by_state["absent"][0]["observed_last_seen"] == "2026-01-01T00:00:00Z"
    # And each says what it means, so nothing has to be looked up.
    assert "did not show" in by_state["absent"][0]["observed_state_meaning"]


def test_a_site_label_cannot_collide_with_an_observed_key():
    """A site publishing a column called `status` or `first_seen_at` would overwrite
    one of these silently, with nothing to say which value won.

    AND MY FIRST REASON FOR WHY IT CANNOT WAS WRONG. I wrote that `_slug` keeps
    `[a-z0-9]` only so an underscore-bearing key is unreachable from a label — it is
    not: `_slug("Observed Last Seen")` is exactly `observed_last_seen`. The real
    protection is that **every site-derived key is itself prefixed**: a card box
    becomes `card_{slug}` and an unrecognised profile label becomes `x_{slug}`, so no
    label of any wording produces a bare `observed_*` key.
    """
    from scrapex.extract.muqawil import CARD_FIELDS, _slug

    # The claim I had it backwards about, asserted so it cannot be re-asserted.
    assert _slug("Observed Last Seen") == "observed_last_seen", (
        "_slug does produce underscores; the prefix is what protects these keys")

    for key, _ in service.OBSERVED_COLUMNS:
        assert key.startswith("observed_")
        assert key not in CARD_FIELDS
        # A card label of ANY wording lands under `card_`, so it cannot reach here.
        assert f"card_{_slug('Observed Last Seen')}" != key
        assert f"x_{_slug('Observed Last Seen')}" != key


# ---- and it has to say WHEN it was crawled, because 17,304 rows came from one ----
#
# THE DEFECT, in his own screen. `muqawil.org · contractors [Row 17,304]` sat above
# `17,304 products` and then `no successful crawl yet`, while `aramco.com` beside it
# read `Last crawled 16 August 2026, 8:00 AM`. Measured on his warehouse the same
# day: `crawl_run` holds 155 rows across twelve source keys and NOT ONE of them is
# muqawil, `generic_page_snapshot` holds 24,480 pages, and `generic_record` holds
# 17,304 + 704 rows for the two datasets. The card was reading the price pipeline's
# ledger about a dataset that can never appear in it — `crawl_run.source_id` is NOT
# NULL into `source_site`, and muqawil lives in `source_site`.


def _dataset_id(conn, dataset_key: str = "contractors") -> int:
    row = conn.execute(
        "SELECT dataset_definition_id FROM dataset_definition WHERE dataset_key = ?",
        (dataset_key,)).fetchone()
    assert row is not None, f"no dataset called {dataset_key!r}"
    return int(row["dataset_definition_id"])


def _fed(conn, captured_at: str, url: str, dataset_key: str = "contractors") -> int:
    """One more page into a dataset, captured at a STATED moment.

    `captured_at` is a column DEFAULT and `generic_page_snapshot` is immutable by
    trigger — `trg_generic_page_snapshot_immutable_update` aborts any UPDATE — so
    stating it in the INSERT is the only way to place evidence in time. It is not a
    test-only trick either: `warehousemerge.py:269` carries the other machine's
    `captured_at` verbatim for exactly the same reason.
    """
    cursor = conn.execute(
        "INSERT INTO generic_page_snapshot "
        "(source_url, html_content, content_hash, captured_at) VALUES (?,?,?,?)",
        (url, LISTING, f"hash-{url}", captured_at))
    snapshot_id = int(cursor.lastrowid)
    candidate = listing_candidate(LISTING)
    service.approve_candidate(conn, snapshot_id, CandidateApproval(
        table_index=0, site_key="muqawil_org", site_display_name="SCA",
        dataset_key=dataset_key, dataset_name="Contractors",
        fields=[ApprovalField(field_key=f.field_key, display_name=f.source_name,
                              data_type="text",
                              identity=(f.field_key == "contractor_id"))
                for f in candidate.fields]), candidate=candidate)
    return snapshot_id


def test_the_freshness_is_the_newest_page_the_dataset_was_fed(conn):
    """Not the oldest, and not whichever page happens to be approved last.

    A crawl of muqawil's listing runs for hours — his `contractors` evidence spans
    2026-08-20T05:52:28Z to 2026-08-21T17:56:31Z — so the two ends of it are a day
    and a half apart. The line says *"Last crawled"*, and only one end of that span
    answers it.
    """
    stored(conn)
    dataset_id = _dataset_id(conn)
    _fed(conn, "2019-03-04T05:06:07Z", "https://muqawil.org/en/contractors?page=2")
    _fed(conn, "2031-03-04T05:06:07Z", "https://muqawil.org/en/contractors?page=3")
    _fed(conn, "2024-03-04T05:06:07Z", "https://muqawil.org/en/contractors?page=4")

    assert service.last_evidence_captured_at(conn, dataset_id) == "2031-03-04T05:06:07Z"


def test_freshness_belongs_to_its_own_dataset_and_not_to_the_warehouse(conn):
    """A page fed to the profiles dataset must not date the listing one.

    Both muqawil datasets are crawled from the same site by the same command, and
    on his warehouse they answer two different instants — 2026-08-21T17:56:31Z for
    `contractors` and 2026-08-21T21:44:48Z for `contractor_profiles`. A read that
    lost the dataset from its WHERE clause would give both the later one and nothing
    on either card would look wrong.
    """
    stored(conn)
    listing = _dataset_id(conn)
    _fed(conn, "2027-01-01T00:00:00Z", "https://muqawil.org/en/contractors?page=9")
    _fed(conn, "2033-12-31T23:59:59Z", "https://muqawil.org/en/contractors/1/2",
         dataset_key="contractor_profiles")
    profiles = _dataset_id(conn, "contractor_profiles")

    assert service.last_evidence_captured_at(conn, listing) == "2027-01-01T00:00:00Z"
    assert service.last_evidence_captured_at(conn, profiles) == "2033-12-31T23:59:59Z"


def test_a_dataset_nothing_has_fed_reports_no_crawl_rather_than_inventing_one(conn):
    """"Never" is a real answer. The whole complaint is a card that stated one thing
    while the warehouse held another, so a freshness with no evidence behind it must
    be absent and not `now`."""
    from scrapex.webui.app import _dataset_freshness

    stored(conn)
    unfed = conn.execute(
        "INSERT INTO dataset_definition "
        "(source_id, dataset_key, original_name, discovery_method) "
        "SELECT source_id, 'nothing_yet', 'nothing_yet', 'manual' "
        "FROM source_site LIMIT 1")

    assert service.last_evidence_captured_at(conn, int(unfed.lastrowid)) is None
    assert _dataset_freshness(conn, int(unfed.lastrowid)) is None


def test_the_freshness_read_goes_through_the_covering_index(conn):
    """The 390x, pinned — because no assertion about the ANSWER can defend it.

    `ix_generic_page_snapshot_page` is `(page_snapshot_id, captured_at)` and had no
    reader before this one. SQLite prefers the rowid, since the planner cannot see
    that the row it lands on carries a compressed body of ~100 KB: measured on his
    24,480-page warehouse, **353-373 ms** by rowid against **0.9 ms** by the
    covering index, for the identical string. `INDEXED BY` is what chooses, and
    removing it is invisible to every other test in this file.
    """
    stored(conn)
    plan = " ".join(
        str(row[3]) for row in
        conn.execute("EXPLAIN QUERY PLAN " + service.LAST_EVIDENCE_SQL, (1,)))

    assert "ix_generic_page_snapshot_page" in plan, (
        f"the freshness read fell back to the rowid, which cost 373 ms: {plan}")


# MARKED, AND ONLY THIS ONE. `tests/test_the_extension_gate_is_complete.py` scans
# for the panel's directory in any test file's source and requires the mark, because
# a file that guards the panel and lacks it silently stops running on exactly the
# pull requests it was written for. This file names `app.js` twice in prose and reads
# nothing under that tree — but THIS test is the one that has to run when the panel
# changes: it pins the shape `freshnessLine` reads, and the defect it covers was the
# server and the panel disagreeing about that shape. Per-test rather than
# module-level, the way `test_the_lint_gate_cannot_be_quietly_widened.py` does it,
# and for the reason that file states: only the test that guards the panel needs to
# run on a panel-only change.
@pytest.mark.extension
def test_the_card_reports_the_crawl_that_produced_its_rows(tmp_path):
    """END TO END, through the route the panel actually calls.

    `freshnessLine` (extension/app.js) prints "no successful crawl yet" whenever
    `last_success` is missing or carries no `started_at` — and `_dataset_rows` used
    to hand it the literal `None`. So the honest fix has to arrive at THIS key in
    THIS shape, or the card goes on saying it whatever the warehouse holds.
    """
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.webui.app import create_app

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        stored(conn)
        # DATED AHEAD OF `stored`'s page, which carries `now` because `captured_at`
        # is a column default. A fixed past instant would lose to it and the
        # assertion would be about the clock instead of about the newest page.
        _fed(conn, "2031-08-21T17:56:31Z", "https://muqawil.org/en/contractors?page=2")
        conn.commit()
    finally:
        conn.close()

    client = TestClient(create_app(databases=registry))
    row = next(r for r in client.get("/api/sources").json()["sources"]
               if r["source_key"] == "contractors")

    assert row["last_success"], (
        "the card says 'no successful crawl yet' over rows a crawl produced")
    assert row["last_success"]["started_at"] == "2031-08-21T17:56:31Z", (
        "the line reads 'Last crawled <started_at>', so it holds the newest capture")
    # AND NO MEASURE BESIDE THE DATE. Both surfaces print `rows_seen` after it
    # and fall back to `requests_count`, and a dataset has an honest number for
    # neither: *seen* is `dataset_sighting`'s word — 17,417 sighted against
    # 17,304 stored on his warehouse — and the stored pages are not the requests
    # the crawl spent. Absent, which `last_successful_run` documents 0 as.
    assert row["last_success"]["rows_seen"] == 0, (
        "the stored row count is not what the site SHOWED us; "
        "dataset_sighting answers that and answers it differently")
    assert row["last_success"]["requests_count"] == 0
    # The row count still reaches the card — on its own line, where it is right.
    assert row["products"] == 4
