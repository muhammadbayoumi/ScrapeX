"""pt-api.tvtc.gov.sa — what TVTC's register of licensed training establishments knows about itself.

Studied in `#1716` before a line of this was written. Every constant here is a measurement
from that study, and the issue carries the request that measured it.

A JSON API, NOT A PAGE. `pt-web.tvtc.gov.sa/institutes` is a React shell with an empty
`#root`; the rows come from a Laravel REST surface the shell calls, answering
`{"data": [...], "links": {...}, "meta": {"total", "last_page", "per_page", ...}}`. So this
reader parses JSON, and the crawl stores the JSON body exactly as it stores any page body:
nothing between the fetch and `generic_page_snapshot` reads it (`#1716`, the wiring map).

THE LANGUAGE TRAVELS IN `locale=`, AND ONLY THERE. Measured: `locale=ar` and `locale=en`
switch `establishment_type.name` and `city.name`; `lang=ar` is ignored and the answer
follows `Accept-Language`, which `HttpFetcher` sends as English
(`scrapex/connectors/base.py:112`). A URL without `locale=` is therefore an English page
whatever it looks like, and `listing_url` always writes the parameter.

THE ORDER IS STABLE. Page 1 returned the same ids in the same order across four requests
minutes apart and three page sizes (9, 100, 1000), which is what `partitioncrawl`'s
witness needs; one `WHOLE` cell, as Oman's register.

`meta.total` IS THE HONEST TOTAL, and a page past the end is EMPTY with status 200 --
`page=99999` answered `data: []` -- so `read_page` checks `last_page` against `total` and
`per_page` rather than trusting either alone, and a crawl ends on `last_page`.
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..pagesource import WHOLE, Cell, RowIdentity, SliceNotSupported

#: Matches `source_site.source_key`, as `directories.Directory.key` requires.
SITE_KEY = "tvtc_establishments"

#: THE API HOST, NOT THE SHELL'S. Approval registers a site under the scheme and host of
#: the stored page's own URL (`extract/service.py:90`), and the crawl registers this one;
#: the two must be the same host or every page is refused as a catalog conflict.
BASE_URL = "https://pt-api.tvtc.gov.sa"
LIST_PATH = "/api/v1/public-inquiries/licensed-establishments"

#: THE SECOND LISTING ON THE SAME API: every training plan an establishment is licensed
#: to run, one row per (establishment, plan) -- 41,694 rows on 2026-10-18. Its own
#: directory and source key, because a `Directory` reads one listing into one dataset
#: (`scrapex/directories.py`). The paginator, the locale parameter and the page shape
#: are the establishments listing's, measured on both (`#1716`), so everything below is
#: shared and only the path and the key differ.
PLANS_SITE_KEY = "tvtc_training_plans"
PLANS_PATH = "/api/v1/public-inquiries/licensed-establishments/plans"

LOCALES = ("en", "ar")
PRIMARY_LOCALE = "en"

#: Measured: `limit=1000` is honoured, and 3,140 establishments are four pages. A page is
#: about 3.65 MB of JSON, which is why `MAX_STORED_BODY_BYTES` exists (`extract/models.py`).
PAGE_SIZE = 1000


class RegisterShapeError(RuntimeError):
    """The API answered something this reader does not recognise. A crawl stops here
    rather than storing rows read from a shape nobody checked."""


@dataclass(frozen=True)
class Page:
    """One answer of the list endpoint, its shape already checked."""

    rows: tuple[dict[str, Any], ...]
    total: int
    last_page: int
    per_page: int
    current_page: int


def _int(meta: dict[str, Any], key: str) -> int:
    value = meta.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RegisterShapeError(f"meta.{key} is {value!r}, not an integer")
    return value


def read_page(body: str) -> Page:
    """Parse one list response and assert every fact the crawl will lean on.

    THE COUNT IS CHECKED THREE WAYS, because `last_page` is the only end the crawl has:
    `last_page` must equal `ceil(total / per_page)`, and a page inside the range must
    carry exactly the rows that arithmetic says it holds. A paginator that changed shape
    fails here, loudly, rather than as a crawl that stopped one page early.
    """
    try:
        doc = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RegisterShapeError(f"the body is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise RegisterShapeError(f"the body is a {type(doc).__name__}, not an object")
    data, meta = doc.get("data"), doc.get("meta")
    if not isinstance(data, list):
        raise RegisterShapeError("the body carries no `data` list")
    if not isinstance(meta, dict):
        raise RegisterShapeError("the body carries no `meta` object")
    total, last_page = _int(meta, "total"), _int(meta, "last_page")
    per_page, current = _int(meta, "per_page"), _int(meta, "current_page")
    if per_page < 1:
        raise RegisterShapeError(f"meta.per_page is {per_page}")
    if last_page != max(1, math.ceil(total / per_page)):
        raise RegisterShapeError(
            f"meta.last_page is {last_page}, but {total} rows at {per_page} a page "
            f"is {max(1, math.ceil(total / per_page))}")
    if current <= last_page:
        expected = per_page if current < last_page else total - (last_page - 1) * per_page
        if len(data) != expected:
            raise RegisterShapeError(
                f"page {current} of {last_page} carries {len(data)} rows, not {expected}")
    elif data:
        raise RegisterShapeError(f"page {current} is past the last ({last_page}) "
                                 f"yet carries {len(data)} rows")
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise RegisterShapeError(f"row {index} is a {type(row).__name__}")
        key = row.get("id")
        if isinstance(key, bool) or not isinstance(key, (int, str)) or str(key) == "":
            raise RegisterShapeError(f"row {index} has no usable `id`: {key!r}")
    return Page(rows=tuple(data), total=total, last_page=last_page,
                per_page=per_page, current_page=current)


def listing_url(base_url: str = BASE_URL, *, locale: str = PRIMARY_LOCALE, page: int = 1,
                cell: Cell = WHOLE, path: str = LIST_PATH) -> str:
    """One page of a listing (`LIST_PATH` or `PLANS_PATH`), in one language.

    THE PARAMETERS ARE ALWAYS WRITTEN IN ONE ORDER, because the URL is what a resume
    matches on (`snapshotcrawl.already_stored` compares `source_url`).
    """
    if page < 1:
        raise ValueError(f"page must be at least 1, got {page}")
    if locale not in LOCALES:
        raise ValueError(f"locale must be one of {LOCALES}, got {locale!r}")
    if path not in (LIST_PATH, PLANS_PATH):
        raise ValueError(f"path must be one of the register's two listings, got {path!r}")
    url = f"{base_url}{path}?locale={locale}&limit={PAGE_SIZE}&page={page}"
    for name, value in cell.params:
        url += f"&{name}={value}"
    return url


def locale_in_query(url: str) -> tuple[str, str] | None:
    """`...?locale=en&limit=1000&page=2` -> (the url with `locale` removed, `en`).

    The counterpart of Oman's `CTRL_STRDIRECTION` removal: the two language copies of one
    page share every parameter but this one. A URL with no `locale=en|ar` is not one of
    this register's pages.
    """
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    locales = [value for name, value in query if name == "locale"]
    if len(locales) != 1 or locales[0] not in LOCALES:
        return None
    rest = urlencode([(name, value) for name, value in query if name != "locale"])
    return urlunsplit(parts._replace(query=rest)), locales[0]


def read_last_page(body: str) -> int:
    return read_page(body).last_page


def read_ids(body: str) -> tuple[str, ...]:
    """Every establishment's id on this page, in published order, keeping duplicates."""
    return tuple(str(row["id"]) for row in read_page(body).rows)


def identity_evidence(body: str) -> tuple[RowIdentity, ...]:
    """The key alone, and that is a measurement rather than a gap.

    NO `registration`. The obvious candidate, the unified CR number, is shared: 303 CR
    numbers carry more than one establishment, up to 60 branches each, across the census
    of 3,140. `RowIdentity.registration` says "the same firm under any key", and a branch
    is not the same establishment, so offering the CR would let a departure be matched to
    a sibling branch.
    """
    return tuple(RowIdentity(key=str(row["id"])) for row in read_page(body).rows)


class TvtcPageSource:
    """The pages one cell of this register covers. `PageSource` for a listing that is the
    whole record."""

    site_key = SITE_KEY

    def __init__(self, *, last_page: int, locales: Iterable[str] = LOCALES,
                 cell: Cell = WHOLE, site_key: str = SITE_KEY,
                 path: str = LIST_PATH) -> None:
        if last_page < 1:
            raise ValueError(f"last_page must be at least 1, got {last_page}")
        self._last_page = last_page
        self._locales = tuple(locales)
        if not self._locales:
            raise ValueError("a page source with no locale fetches nothing")
        self._cell = cell
        self.site_key = site_key
        self._path = path

    def listing_urls(self, base_url: str) -> Iterable[str]:
        """Page by page, both languages of a page together, so a run stopped half way holds
        both halves of every page it reached -- Oman's order, for Oman's reason."""
        for page in range(1, self._last_page + 1):
            for locale in self._locales:
                yield listing_url(base_url, locale=locale, page=page, cell=self._cell,
                                  path=self._path)

    def detail_urls(self, page: Any) -> Iterable[str]:
        """None. The detail endpoint adds only `active_training_plans`, and the plans
        endpoint carries those whole (`#1716` §4b), so there is no per-row fetch."""
        return ()

    def belongs_to_slice(self, page: Any, row_index: int, slice_of: str) -> bool:
        raise SliceNotSupported(
            f"{self.site_key} offers no slice scope; the register is crawled whole in "
            f"{PAGE_SIZE}-row pages (asked for {slice_of!r})")


class TvtcPartition:
    """`PartitionedListing` for a register that needs no partition: one `WHOLE` cell,
    because its order is stable (see the module docstring)."""

    site_key = SITE_KEY
    path = LIST_PATH
    locales = LOCALES
    primary_locale = PRIMARY_LOCALE

    def cells(self) -> tuple[Cell, ...]:
        return (WHOLE,)

    def listing_url(self, base_url: str, *, locale: str, page: int,
                    cell: Cell = WHOLE) -> str:
        return listing_url(base_url, locale=locale, page=page, cell=cell, path=self.path)

    def read_last_page(self, html: str) -> int:
        return read_last_page(html)

    def read_ids(self, html: str) -> tuple[str, ...]:
        return read_ids(html)

    def identity_evidence(self, html: str) -> tuple[RowIdentity, ...]:
        return identity_evidence(html)

    def in_cell(self, cell: Cell, *, last_page: int) -> TvtcPageSource:
        return TvtcPageSource(last_page=last_page, locales=self.locales, cell=cell,
                              site_key=self.site_key, path=self.path)


class TvtcPlansPartition(TvtcPartition):
    """The training-plans listing: the same register, paginator and order, another path.

    ONE `WHOLE` CELL FOR THE ESTABLISHMENTS' REASON, measured again here on 2026-10-18:
    the first 20 ids of `plans?limit=20` equalled the first 20 of the `limit=1000` page
    captured the day before, in both languages, and the 1,000 row ids were distinct.
    """

    site_key = PLANS_SITE_KEY
    path = PLANS_PATH
