"""Local .xlsx sink — the offline twin of the Google sink (ENGINEERING.md P1).

Produces a workbook with one tab per source, mirroring the Drive layout exactly,
using the SAME export_source_table data (via publish.publish_source). No Google,
no network. openpyxl is imported lazily so the rest of ScrapeX needs no xlsx dep.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_EXPORT_DIR = Path(os.environ.get("SCRAPEX_EXPORT_DIR", str(Path.home() / "ScrapeX")))

# Excel worksheet titles: max 31 chars, and these characters are forbidden.
_BAD_TITLE_CHARS = set(r"[]:*?/\\")


def _safe_title(tab: str) -> str:
    cleaned = "".join("_" if ch in _BAD_TITLE_CHARS else ch for ch in tab)
    return cleaned[:31] or "Sheet"


def workbook_bytes(tabs: list[tuple[str, list[str], list[list]]]) -> bytes:
    """The same workbook LocalSink writes to disk, in memory, for a download.

    The Data page's Excel button used to call Tabulator's client-side xlsx
    writer, which needs SheetJS on `window` — never vendored here, so the
    button logged a console error and produced no file at all. Worse, even
    working it could only ever have exported the grid: the details, the history
    and the provenance are not in the browser. Building the same tabs the CLI
    and the Google push build, on the server, makes one download the whole
    record (P1 DRY: publish.workbook_tables decides WHAT, this decides only how
    to write it).

    Titles are truncated to Excel's 31 characters, so two long tabs can collide
    once shortened; the suffix keeps them distinct rather than letting one
    silently replace the other.
    """
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("the Excel export needs: pip install -e .[local]") from exc
    from io import BytesIO

    book = Workbook()
    book.remove(book.active)             # openpyxl's default empty sheet
    used: set[str] = set()
    for tab, header, rows in tabs:
        title = _safe_title(tab)
        if title in used:
            title = f"{title[:28]}_{len(used)}"
        used.add(title)
        sheet = book.create_sheet(title)
        sheet.append(list(header))
        for row in rows:
            sheet.append(list(row))
        sheet.freeze_panes = "A2"        # the header stays put while scrolling
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


class LocalSink:
    """SheetSink that writes to a local .xlsx workbook (folder/workbook.xlsx)."""

    def ensure_workbook(self, folder: str, workbook: str) -> Path:
        path = Path(folder).expanduser() / f"{workbook}.xlsx"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_tab(self, path: Path, tab: str, header: list[str], rows: list[list]) -> None:
        try:
            from openpyxl import Workbook, load_workbook
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError("local export needs: pip install -e .[local]") from exc

        title = _safe_title(tab)
        if Path(path).exists():
            wb = load_workbook(path)
            new = False
        else:
            wb = Workbook()
            new = True

        if title in wb.sheetnames:
            del wb[title]            # replace the tab (idempotent, like the Google sink)
        ws = wb.create_sheet(title)
        ws.append(list(header))
        for row in rows:
            ws.append(list(row))

        if new and "Sheet" in wb.sheetnames and "Sheet" != title:
            del wb["Sheet"]          # drop openpyxl's default empty sheet
        wb.save(path)

    def location(self, path: Path) -> str:
        return str(path)
