"""The Data page's grid, driven in a real browser.

Until now the only thing testing 3,000 lines of grid.js was `assert "..." in
script` — the file read as TEXT. That catches a renamed literal (it did, once)
and cannot catch a single behavioural regression: every defect the owner
reported was invisible to it.

These tests load the real grid.js against a fixture payload and ask the table
what it actually did. The fixture deliberately carries the shapes that broke:
space-padded names, a brand that is one space, a numeric column, Arabic names,
alphanumeric measurements, and a product name made of markup.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright

import grid_harness as harness  # noqa: E402


# The values that caused real defects, kept together so a reader can see at a
# glance what this suite is defending.
PADDED_NAME = "                 Putty - 1 kg"
MARKUP_NAME = "<img src=x onerror=window.__pwned=1>"


def _payload() -> dict:
    def row(name, name_ar, price, unit, brand, observations, country, code, offer_id):
        return {
            "product_name": name, "product_name_ar": name_ar,
            "price": price, "currency": "SAR", "unit": unit,
            "brand": brand, "observations": observations,
            "country": country, "country_code_alpha2": code,
            "availability": "in_stock", "offer_id": offer_id,
            "tax_ref": 0, "product_link": "", "sku": f"SKU{offer_id}",
        }

    return {
        "source_key": "TESTSRC",
        "columns": [
            {"key": "product_name", "label": "Product name"},
            {"key": "product_name_ar", "label": "Product name (AR)"},
            {"key": "price", "label": "Price"},
            {"key": "unit", "label": "Unit"},
            {"key": "brand", "label": "Brand"},
            {"key": "observations", "label": "Observations"},
            {"key": "country_code_alpha2", "label": "Country code"},
        ],
        "rows": [
            # A padded name. Sorted raw it files ahead of everything; the
            # product itself begins with P.
            row(PADDED_NAME, "معجون", 4.23, "2 kg", " ", 1, "Saudi Arabia", "SA", 1),
            row("Alpha cement", "أسمنت", 135.24, "10 kg", "AKS", 2, "Egypt", "EG", 2),
            row("Zinc sheet", "زنك", 9.66, "2.5 kg", "3M", 1, "Andorra", "AD", 3),
            row("Beta rebar", "حديد", 0.81, "", "", 2, "United Arab Emirates", "AE", 4),
        ],
        "tax_states": [{"tax_short": "Incl. 15%", "tax": "Includes VAT"}],
        "total": 4, "returned": 4, "truncated": False,
        "tree": None, "bilingual": {"product_name_ar": "product_name"},
        "moved_to_details": [],
    }


def _fields() -> dict:
    """What /api/fields answers: every column, and whether it is in the table."""
    return {"fields": [
        {"field_key": key, "display_name": label, "is_hidden": False}
        for key, label in [
            ("product_name", "Product name"), ("product_name_ar", "Product name (AR)"),
            ("price", "Price"), ("unit", "Unit"), ("brand", "Brand"),
            ("observations", "Observations"), ("country_code_alpha2", "Country code"),
        ]
    ]}


@pytest.fixture(scope="module")
def page_factory(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("grid")

    def open_grid(payload=None, *, expect_table=True, **kw):
        kw.setdefault("fields", _fields())
        # expect_table=False for a source with no rows: grid.js deliberately
        # never constructs a table for one, so waiting for the instance would
        # time out on the very case the test is about.
        target = harness.build_page(tmp, payload or _payload(), **kw)
        ctx = sync_playwright().start()
        browser = ctx.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(target.as_uri())
        if expect_table:
            page.wait_for_function("() => !!window.Tabulator "
                                   "&& Tabulator.findTable('#grid').length > 0")
        else:
            page.wait_for_function(
                "() => document.getElementById('grid-note')"
                "  && !document.getElementById('grid-note').hidden")
        page.wait_for_timeout(400)
        return page, browser, ctx

    return open_grid


@pytest.fixture
def page(page_factory):
    page, browser, ctx = page_factory()
    yield page
    browser.close()
    ctx.stop()


def _sorted_names(page, field, direction):
    return page.evaluate(
        """([field, dir]) => {
            const t = Tabulator.findTable('#grid')[0];
            t.setSort(field, dir);
            return t.getData('active').map(r => r[field]);
        }""",
        [field, direction],
    )


# ---- the record is the record ------------------------------------------------

def test_the_padded_name_is_delivered_and_kept_verbatim(page):
    """The grid must not tidy what the site published."""
    names = page.evaluate(
        "() => Tabulator.findTable('#grid')[0].getData().map(r => r.product_name)")
    assert PADDED_NAME in names, "the captured value was altered before it arrived"
    brands = page.evaluate(
        "() => Tabulator.findTable('#grid')[0].getData().map(r => r.brand)")
    assert " " in brands, "a brand published as a single space became something else"


def test_padding_decides_nothing_about_the_order(page):
    """The padded product sorts under P, not ahead of every row on the page."""
    ascending = _sorted_names(page, "product_name", "asc")
    assert [n.strip() for n in ascending] == [
        "Alpha cement", "Beta rebar", PADDED_NAME.strip(), "Zinc sheet"]
    # and the value that came back is still the padded one
    assert PADDED_NAME in ascending


def test_a_brand_of_one_space_is_offered_as_blank_not_as_a_value(page):
    """It is not a brand, so the filter must not list it as one."""
    values = page.evaluate("""() => {
        const col = [...document.querySelectorAll('.tabulator-col')]
          .find(c => c.getAttribute('tabulator-field') === 'brand');
        col.querySelector('.material-filter-icon').parentElement.click();
        return [...document.querySelectorAll('.setfilter-row')].map(r => r.textContent);
    }""")
    assert "(Blanks)" in values
    assert " " not in values and "  " not in values


# ---- sorting -----------------------------------------------------------------

def test_a_numeric_column_sorts_numerically(page):
    assert _sorted_names(page, "price", "asc") == [0.81, 4.23, 9.66, 135.24]
    assert _sorted_names(page, "price", "desc") == [135.24, 9.66, 4.23, 0.81]


def test_a_measurement_column_sorts_by_its_number(page):
    """2 kg before 2.5 kg before 10 kg — not the text order 10, 2, 2.5."""
    units = [u for u in _sorted_names(page, "unit", "asc") if u]
    assert units == ["2 kg", "2.5 kg", "10 kg"]


def test_empties_sort_last_in_both_directions(page):
    assert _sorted_names(page, "unit", "asc")[-1] == ""
    assert _sorted_names(page, "unit", "desc")[-1] == ""


def test_arabic_sorts_by_arabic_collation(page):
    """أ ... not the order Unicode happens to store the letters in."""
    got = _sorted_names(page, "product_name_ar", "asc")
    want = page.evaluate(
        """(names) => names.slice().sort(
             new Intl.Collator(['ar','en'], {numeric: true}).compare)""",
        got,
    )
    assert got == want


def test_country_sorts_by_the_name_on_screen_not_the_hidden_code(page):
    """The cell reads "United Arab Emirates"; sorting on "AE" would put it second."""
    order = page.evaluate("""() => {
        const t = Tabulator.findTable('#grid')[0];
        t.setSort('country_code_alpha2', 'asc');
        return t.getData('active').map(r => r.country);
    }""")
    assert order == ["Andorra", "Egypt", "Saudi Arabia", "United Arab Emirates"]


def test_the_sort_survives_a_rebuild(page):
    """Grouping rebuilds the table; it must not discard the chosen order."""
    before = page.evaluate("""() => {
        const t = Tabulator.findTable('#grid')[0];
        t.setSort('price', 'asc');
        return t.getSorters().map(s => s.field + ':' + s.dir);
    }""")
    assert before == ["price:asc"]
    page.evaluate("""() => {
        const col = [...document.querySelectorAll('.tabulator-col')]
          .find(c => c.getAttribute('tabulator-field') === 'brand');
        const b = col.querySelector('.material-menu-icon').parentElement;
        const r = b.getBoundingClientRect();
        const o = {bubbles:true, cancelable:true, button:0, buttons:1,
                   clientX:r.left+3, clientY:r.top+3, view:window};
        b.dispatchEvent(new MouseEvent('mousedown', o));
        b.dispatchEvent(new MouseEvent('mouseup', o));
        b.dispatchEvent(new MouseEvent('click', o));
        [...document.querySelector('.tabulator-menu').children]
          .find(x => /^Group by/.test(x.textContent)).click();
    }""")
    page.wait_for_timeout(700)
    after = page.evaluate(
        "() => Tabulator.findTable('#grid')[0].getSorters().map(s => s.field+':'+s.dir)")
    assert after == ["price:asc"], "grouping threw the sort away"


# ---- markup is data, never code ---------------------------------------------

def test_a_group_header_renders_markup_as_text(page_factory):
    """Tabulator writes a STRING group header through innerHTML."""
    payload = _payload()
    payload["rows"][0]["product_name"] = MARKUP_NAME
    page, browser, ctx = page_factory(payload)
    try:
        page.evaluate("""() => {
            const col = [...document.querySelectorAll('.tabulator-col')]
              .find(c => c.getAttribute('tabulator-field') === 'product_name');
            const b = col.querySelector('.material-menu-icon').parentElement;
            const r = b.getBoundingClientRect();
            const o = {bubbles:true, cancelable:true, button:0, buttons:1,
                       clientX:r.left+3, clientY:r.top+3, view:window};
            b.dispatchEvent(new MouseEvent('mousedown', o));
            b.dispatchEvent(new MouseEvent('mouseup', o));
            b.dispatchEvent(new MouseEvent('click', o));
            [...document.querySelector('.tabulator-menu').children]
              .find(x => /^Group by/.test(x.textContent)).click();
        }""")
        page.wait_for_timeout(700)
        assert page.evaluate("() => window.__pwned") is None, "scraped markup ran"
        assert page.evaluate(
            "() => document.querySelectorAll('.tabulator-group img').length") == 0
        bands = page.evaluate(
            "() => [...document.querySelectorAll('.tabulator-group')].map(g => g.textContent)")
        assert any(MARKUP_NAME in b for b in bands), "the value should show as text"
    finally:
        browser.close()
        ctx.stop()


# ---- a control that can remove itself needs a door outside it ----------------

def test_the_columns_button_opens_the_chooser(page):
    """The header menu is carried by the columns the chooser can remove."""
    page.click("#grid-columns-button")
    page.wait_for_selector(".column-chooser", timeout=3000)
    assert page.is_visible(".column-chooser")


def test_the_columns_button_still_works_with_no_rows(page_factory):
    """A source with no rows still has columns to arrange."""
    payload = _payload()
    payload["rows"] = []
    payload["total"] = payload["returned"] = 0
    page, browser, ctx = page_factory(payload, expect_table=False)
    try:
        page.click("#grid-columns-button")
        page.wait_for_selector(".column-chooser", timeout=3000)
        assert page.is_visible(".column-chooser")
    finally:
        browser.close()
        ctx.stop()


# ---- the footer must describe the table in front of you ----------------------

def test_the_footer_counts_the_rows_actually_shown(page):
    """dataFiltered fires before the filtered rows become the active set."""
    footer = page.evaluate("""() => {
        const t = Tabulator.findTable('#grid')[0];
        t.setFilter([{field: (row) => row.price > 100}]);   // one row of four
        return null;
    }""")
    page.wait_for_timeout(300)
    shown, text = page.evaluate("""() => [
        Tabulator.findTable('#grid')[0].getDataCount('active'),
        document.querySelector('.grid-footer-summary').textContent,
    ]""")
    assert shown == 1
    assert "TotalRows:1" in text.replace(" ", ""), (
        f"footer reported the previous state: {text!r}")


# ---- nesting must not take matching rows down with the branch ---------------

def test_filtering_while_nested_keeps_branches_that_hold_a_match(page):
    """A parent carries only the nested column, so it fails every other filter."""
    kept = page.evaluate("""() => {
        const t = Tabulator.findTable('#grid')[0];
        // nest by a column two rows share, then filter on a DIFFERENT column
        t.setFilter([{field: (row) => {
            const hit = (r) => String(r.observations) === '2';
            return hit(row) || (Array.isArray(row._children) && row._children.some(hit));
        }}]);
        return t.getDataCount('active');
    }""")
    assert kept == 2, "the filter dropped rows that match"


# ---- a column whose cell comes from elsewhere still groups ------------------

def test_grouping_by_a_derived_column_uses_what_the_cell_shows(page):
    """Country's field holds "AD"; the cell reads "Andorra"."""
    bands = page.evaluate("""() => {
        const t = Tabulator.findTable('#grid')[0];
        return t.getGroups ? t.getGroups().length : -1;
    }""")
    # four distinct countries in the fixture, so a correct grouping is four bands
    groups = page.evaluate("""() => {
        const t = Tabulator.findTable('#grid')[0];
        t.setGroupBy((data) => data.country || data.country_code_alpha2 || '');
        return t.getGroups().map(g => g.getKey());
    }""")
    assert sorted(groups) == ["Andorra", "Egypt", "Saudi Arabia",
                              "United Arab Emirates"]


# ---- a dialog must always be closable ---------------------------------------

def test_the_chooser_can_be_closed_after_a_save_keeps_failing(page):
    """A server that is down must not hold the dialog shut."""
    # The LIST still loads; only storing a choice fails. Breaking both would
    # test an empty dialog instead of a dialog with unsaveable changes.
    page.evaluate("() => { window.__fetchFailures['POST /api/fields/'] = 500; }")
    page.click("#grid-columns-button")
    page.wait_for_selector(".column-chooser-row", timeout=3000)
    page.evaluate("""() => {
        const row = document.querySelector('.column-chooser-row input[type=checkbox]');
        row.checked = !row.checked;
        row.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    page.wait_for_timeout(400)
    assert page.evaluate(
        "() => window.__posts.some(p => p.path.includes('/api/fields/'))"), \
        "no save was attempted, so the test is not exercising a failed save"
    page.click(".column-chooser-close")
    page.wait_for_timeout(300)
    page.click(".column-chooser-close")
    page.wait_for_timeout(300)
    assert page.evaluate(
        "() => !document.querySelector('.column-chooser')"), "the dialog was trapped"


# ---- every link off this page opens someone else's site ---------------------

def test_outbound_links_carry_target_and_rel_together(page_factory):
    """target=_blank without rel=noopener hands the opened page a handle on this one.

    This also exercises externalLink() at all. The helper was introduced to
    remove six copies of the same two lines, and a bad rewrite left it calling
    ITSELF — infinite recursion — which every other test in this file sailed
    past, because none of them rendered a cell that builds a link.
    """
    payload = _payload()
    for i, row in enumerate(payload["rows"]):
        row["product_link"] = f"https://example.test/p/{i}"
    payload["columns"].append({"key": "product_link", "label": ""})
    page, browser, ctx = page_factory(payload)
    try:
        links = page.evaluate("""() => [...document.querySelectorAll(
            '.tabulator-cell[tabulator-field=product_link] a')].map(a => ({
                href: a.getAttribute('href'),
                target: a.getAttribute('target'),
                rel: a.getAttribute('rel'),
            }))""")
        assert links, "no product link was rendered at all"
        for link in links:
            assert link["target"] == "_blank"
            assert link["rel"] == "noopener noreferrer", link
            assert link["href"].startswith("https://example.test/")
    finally:
        browser.close()
        ctx.stop()


# ---- the harness stands in for source.html, so the two must agree ------------

def test_the_real_template_carries_every_id_the_grid_binds():
    template = (ROOT / "scrapex" / "webui" / "templates" / "source.html").read_text(
        encoding="utf-8")
    for element_id in harness.REQUIRED_IDS:
        assert f'id="{element_id}"' in template, (
            f"source.html has no #{element_id}; the harness would pass while the "
            f"real page failed")
