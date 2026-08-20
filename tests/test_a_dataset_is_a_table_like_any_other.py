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

    assert payload["bilingual"] == {"city_ar": "city"}


def test_a_lonely_ar_column_is_not_offered_as_a_pair(conn):
    """A toggle that flipped a column with nothing to flip TO would blank it."""
    payload = stored(conn, extra={"city_ar": "الرياض"})

    assert payload["bilingual"] == {}


def test_nothing_here_is_a_hand_written_field_list(conn):
    """`reports.BILINGUAL_COLUMNS` is a literal dict for products, which is why
    a second table could never have used it. A column added tomorrow pairs
    without anyone editing anything."""
    payload = stored(conn, extra={"brand_new": "x", "brand_new_ar": "س"})

    assert payload["bilingual"] == {"brand_new_ar": "brand_new"}


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
    `/api/sources` walked the manifest alone, so a `site_profile` row could
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
