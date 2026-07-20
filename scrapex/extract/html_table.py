"""Bounded semantic HTML-table discovery and schema inference."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from .models import (
    MAX_PREVIEW_ROWS, MAX_TABLE_COLUMNS, MAX_TABLE_ROWS, MAX_TABLES,
)

_INTEGER = re.compile(r"^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(?:\d+\.\d+|\d+\.)$")
_SPACE = re.compile(r"\s+")
_KEY_PARTS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class InferredField:
    field_key: str
    source_name: str
    data_type: str
    nullable: bool
    position: int
    confidence: float
    uniqueness: float
    null_fraction: float
    identity_candidate: bool

    def public(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "source_name": self.source_name,
            "display_name": self.source_name,
            "data_type": self.data_type,
            "nullable": self.nullable,
            "position": self.position,
            "confidence": self.confidence,
            "uniqueness": self.uniqueness,
            "null_fraction": self.null_fraction,
            "identity_candidate": self.identity_candidate,
        }


@dataclass(frozen=True)
class TableCandidate:
    table_index: int
    name: str
    locator: str
    fields: tuple[InferredField, ...]
    rows: tuple[dict[str, str | None], ...]
    confidence: float
    warnings: tuple[str, ...]
    approvable: bool
    truncated: bool

    def public(self) -> dict[str, Any]:
        suggested = [
            field.field_key for field in self.fields if field.identity_candidate
        ][:1]
        return {
            "candidate_id": f"html-table-{self.table_index}",
            "table_index": self.table_index,
            "name": self.name,
            "source_type": "html_table",
            "source_locator": self.locator,
            "estimated_row_count": len(self.rows),
            "sample_records": list(self.rows[:MAX_PREVIEW_ROWS]),
            "fields": [field.public() for field in self.fields],
            "candidate_identity_fields": suggested,
            "pagination_evidence": None,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "approvable": self.approvable,
            "truncated": self.truncated,
        }


def _clean(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def _field_key(name: str, position: int, used: set[str]) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = _KEY_PARTS.sub("_", ascii_name.lower()).strip("_") or f"field_{position + 1}"
    if not base[0].isalpha():
        base = f"field_{base}"
    base = base[:64]
    if len(base) < 2:
        base = f"field_{position + 1}"
    key = base
    suffix = 2
    while key in used:
        tail = f"_{suffix}"
        key = f"{base[:64 - len(tail)]}{tail}"
        suffix += 1
    used.add(key)
    return key


def _direct_rows(table: Tag) -> list[Tag]:
    rows: list[Tag] = []
    for row in table.find_all("tr", limit=MAX_TABLE_ROWS + 2):
        if row.find_parent("table") is table:
            rows.append(row)
    return rows


def _cells(row: Tag) -> list[Tag]:
    return [cell for cell in row.find_all(["th", "td"], recursive=False)]


def _infer_type(values: list[str | None]) -> tuple[str, float]:
    present = [value for value in values if value not in (None, "")]
    if not present:
        return "unknown", 0.0
    lowered = {value.casefold() for value in present}
    if lowered <= {"true", "false", "yes", "no"}:
        return "boolean", 1.0
    if all(_INTEGER.fullmatch(value) for value in present):
        return "integer", 1.0
    if all(_INTEGER.fullmatch(value) or _DECIMAL.fullmatch(value) for value in present):
        return "decimal", 1.0
    if all(_is_datetime(value) for value in present):
        return "datetime", 1.0
    if all(_is_date(value) for value in present):
        return "date", 1.0
    if all(_is_url(value) for value in present):
        return "url", 1.0
    return "text", 1.0


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _is_datetime(value: str) -> bool:
    if "T" not in value and " " not in value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _locator(table: Tag, table_index: int) -> str:
    identifier = table.get("id")
    if isinstance(identifier, str) and identifier:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", identifier)
        return f"table#{safe_id}"
    return f"table:nth-of-type({table_index + 1})"


def _candidate(table: Tag, table_index: int) -> TableCandidate:
    warnings: list[str] = []
    rows = _direct_rows(table)
    truncated = len(rows) > MAX_TABLE_ROWS + 1
    if truncated:
        rows = rows[:MAX_TABLE_ROWS + 1]
        warnings.append(
            f"The table exceeds {MAX_TABLE_ROWS:,} data rows. Narrow the saved HTML "
            "before approval so no rows are silently omitted."
        )

    thead = table.find("thead")
    header_row: Tag | None = None
    header_rows: set[int] = set()
    if isinstance(thead, Tag):
        owned = [
            row for row in thead.find_all("tr", limit=MAX_TABLE_ROWS + 2)
            if row.find_parent("table") is table
        ]
        if owned:
            header_row = owned[-1]
            header_rows = {id(row) for row in owned}
    if header_row is None and rows:
        first_cells = _cells(rows[0])
        if first_cells and any(cell.name == "th" for cell in first_cells):
            header_row = rows[0]
            header_rows = {id(rows[0])}

    data_rows = [row for row in rows if id(row) not in header_rows]
    raw_data = [[_clean(cell.get_text(" ", strip=True)) or None for cell in _cells(row)]
                for row in data_rows]
    raw_data = [row for row in raw_data if row]
    width = max(
        [len(_cells(header_row)) if header_row is not None else 0]
        + [len(row) for row in raw_data]
        + [0]
    )
    if width > MAX_TABLE_COLUMNS:
        warnings.append(
            f"The table has {width} columns; the approval limit is "
            f"{MAX_TABLE_COLUMNS}. Reduce the table width and retry."
        )

    usable_width = min(width, MAX_TABLE_COLUMNS)
    if header_row is not None:
        source_names = [_clean(cell.get_text(" ", strip=True)) for cell in _cells(header_row)]
    else:
        source_names = []
        if usable_width:
            warnings.append(
                "No semantic header row was found. Review the generated column names "
                "before approval."
            )
    source_names += [f"Column {index + 1}" for index in range(len(source_names), usable_width)]
    source_names = [name or f"Column {index + 1}" for index, name in enumerate(source_names)]

    has_merged_cells = bool(
        table.find(["td", "th"], attrs={"rowspan": True}) or table.find(
        ["td", "th"], attrs={"colspan": True}
        )
    )
    if has_merged_cells:
        warnings.append(
            "Merged cells are not expanded in this slice. Save a table with one cell "
            "per field before approval."
        )

    used: set[str] = set()
    keys = [_field_key(name, index, used) for index, name in enumerate(source_names)]
    normalized_rows = [
        {key: (row[index] if index < len(row) else None) for index, key in enumerate(keys)}
        for row in raw_data[:MAX_TABLE_ROWS]
    ]
    fields: list[InferredField] = []
    row_count = len(normalized_rows)
    for position, (key, source_name) in enumerate(zip(keys, source_names, strict=True)):
        values = [row[key] for row in normalized_rows]
        present = [value for value in values if value not in (None, "")]
        unique = len(set(present))
        uniqueness = unique / len(present) if present else 0.0
        null_fraction = (row_count - len(present)) / row_count if row_count else 1.0
        data_type, confidence = _infer_type(values)
        fields.append(InferredField(
            field_key=key,
            source_name=source_name,
            data_type=data_type,
            nullable=len(present) != row_count,
            position=position,
            confidence=confidence,
            uniqueness=round(uniqueness, 4),
            null_fraction=round(null_fraction, 4),
            identity_candidate=bool(present) and uniqueness == 1.0 and null_fraction == 0.0,
        ))

    caption = table.find("caption")
    aria_label = table.get("aria-label")
    name = (
        _clean(caption.get_text(" ", strip=True)) if isinstance(caption, Tag)
        else _clean(aria_label) if isinstance(aria_label, str)
        else f"Table {table_index + 1}"
    )
    semantic_header = header_row is not None
    confidence = 0.95 if semantic_header and isinstance(caption, Tag) else (
        0.88 if semantic_header else 0.7
    )
    approvable = (
        bool(normalized_rows and fields)
        and not truncated
        and width <= MAX_TABLE_COLUMNS
        and not has_merged_cells
    )
    if not normalized_rows:
        warnings.append(
            "No data rows were found. Add at least one row to the saved HTML and retry."
        )
    return TableCandidate(
        table_index=table_index,
        name=name[:500],
        locator=_locator(table, table_index),
        fields=tuple(fields),
        rows=tuple(normalized_rows),
        confidence=confidence,
        warnings=tuple(warnings),
        approvable=approvable,
        truncated=truncated,
    )


def detect_html_tables(html_content: str) -> list[TableCandidate]:
    """Return bounded candidates without writing catalogue or record state."""
    soup = BeautifulSoup(html_content, "html.parser")
    candidates: list[TableCandidate] = []
    for table in soup.find_all("table", limit=MAX_TABLES * 10):
        if not isinstance(table, Tag) or table.find_parent("table") is not None:
            continue
        candidates.append(_candidate(table, len(candidates)))
        if len(candidates) == MAX_TABLES:
            break
    return candidates


def candidate_by_index(html_content: str, table_index: int) -> TableCandidate:
    for candidate in detect_html_tables(html_content):
        if candidate.table_index == table_index:
            return candidate
    raise LookupError(table_index)
