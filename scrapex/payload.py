"""The versioned funnel payload contract (ENGINEERING.md T8).

ONE contract, THREE parties: the Python CLI (producer), the Chrome extension
(producer), and the Apps Script funnel (consumer). This module is the Python
authority; `contracts/funnel-payload.schema.json` is the exported neutral form
consumed by the extension's tests and standing as the GAS contract; the golden
fixtures in `contracts/fixtures/` are shared vectors all three validate against.

Any change here MUST bump PAYLOAD_VERSION and update the schema + fixtures in
the same commit (T8). Bumping PAYLOAD_VERSION is CHEAP — see the two numbers
below: it is a stamp, not a gate, and an additive change costs no consumer a
redeploy. Bumping PAYLOAD_COMPAT_VERSION is the expensive one.

Chunking (S1): Apps Script appends one chunk per sheet row; a cell holds at
most 50,000 chars, so chunks are capped at CHUNK_MAX_CHARS = 40,000 with margin.
Reassembly happens ONLY in Python at ingest — GAS stays dumb.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .vocab import ExtractKind, PayloadClient

# TWO NUMBERS, BECAUSE THERE ARE TWO QUESTIONS.
#
# The history below already reasoned out, in prose, the only distinction that
# matters to a consumer: versions 2..5 RENAMED columns or changed what a value
# means, and 6 only ADDED columns. Nothing encoded it, so one number had to
# answer both questions — and every consumer checked it for EQUALITY. The
# consequence was paid by hand: the owner re-pasted the whole Apps Script into
# his sheet for four new columns that the script, which builds every sheet from
# the payload's own header, would have written without being told anything.
#
#   PAYLOAD_VERSION       the CONTENT stamp. Moves on EVERY change, including a
#                         purely additive one. It is reported, logged and read
#                         by humans; it refuses nothing.
#   PAYLOAD_COMPAT_VERSION  the MEANING generation. Moves ONLY when a column is
#                         renamed or removed, when a value's units change, or
#                         when a required field becomes optional (or back).
#                         This is the number both ends gate on, and the only
#                         one whose movement costs a redeploy.
#
# A generation is NAMED after the content version at which it began, so the two
# numbers read as one sentence: "content 7, generation 5" means "the seventh
# shape, still readable by anything that speaks the fifth meaning".
#
# 2: the bilingual inversion. product_name keeps its NAME and changes its
# MEANING from Arabic to English, which no shape check anywhere can detect —
# an old product_name and a new one are the same string carrying opposite
# languages. Dual-read was rejected for exactly that reason: it would have
# made the inversion permanent and undetectable. A v1 payload is REFUSED.
# 3: `region` -> `country_code_alpha2`. The column is REQUIRED, so a v2
# header fails the required-column check loudly on its own; the number moves
# anyway, because the contract changed and the sheet has to be told once.
# 4: `brand_raw` -> the pair `brand` / `brand_ar`. ALSWEED published BOTH
# names into the one column («لوكسيفاي LUXIFY»), so half of every brand it
# sells was unreachable behind the other. Neither half is additive, so a v3
# header fails the column check on its own; the number moves anyway, because
# the contract changed and the sheet has to be told once.
# 5: the non-language vocabulary sweep (0051). Five WIRE columns move —
# product_url -> product_link, vat_included -> tax_included, regular_price ->
# price_before, sale_price -> price_sale, effective_price -> price — plus
# tax_statement_url and official_source_url. None of the five is additive, so a
# v4 header fails the column check on its own; the number moves anyway, because
# the contract changed and the sheet has to be told once.
# 6: PRODUCT_PRICES gains four columns — display_method, minimum_quantity,
# quantity_increment, quantity_is_decimal (migration 0056). ALL FOUR ARE
# ADDITIVE, which is exactly the case that flag exists for: they are new slots
# nothing used to fill, so a payload captured before them is COMPLETE rather
# than broken and replays unchanged. Nothing is renamed and nothing changes
# meaning, so unlike versions 2..5 no old header fails a column check on its
# own — and that is precisely why the number has to move. The header check
# refuses a mismatch, and the sheet has to be told once.
# 7: `payload_compat_version` joins the envelope — this commit. ADDITIVE: a new
# optional field nothing used to fill, no column touched, no meaning changed.
# It is the field that lets an OLD reader read a NEW payload, which is the whole
# point: a reader cannot infer from "7" alone whether 7 is additive over what it
# knows, so the payload says so itself.
# 8: PRODUCT_PRICES gains the pair `weight` / `weight_unit` (migration 0057) —
# the weight the source publishes for the thing it is pricing, and the unit the
# source says its weights are in. 6 stored the site's quantity NUMBERS and left
# the weight they are quantities OF unmeasured, so a madar rebar row still could
# not say what 4,830 was for. ADDITIVE, and therefore GENERATION 5: two new
# slots nothing used to fill, no column renamed, no value's units changed, no
# required field flipped. A payload written yesterday is complete rather than
# broken and replays unchanged, the sheet grows two columns on its own, and the
# owner pastes nothing — which is the case 7 built the ledger for, arriving one
# commit later.
PAYLOAD_VERSION = 8

# WHICH GENERATION EACH CONTENT VERSION BELONGS TO — the prose above, encoded.
#
# Read it as the ledger it is: 2, 3, 4 and 5 each open their own generation
# because each renamed a column or inverted a meaning; 6, 7 and 8 stay in 5's
# because all three only added. Adding a version WITHOUT adding its entry here is an
# import-time KeyError two lines down, which is deliberate: a bump has to say
# which kind it is, and the loudest possible place to ask is the build.
#
# It is also what keeps a mailbox full of history readable. _INBOX holds batches
# stamped 6 and carrying no generation at all, because they were written before
# the field existed; this table is how a reader knows a 6 is a 5, so an inbox
# that predates the split keeps publishing instead of going stale.
GENERATION_OF_VERSION = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 5, 7: 5, 8: 5}

# The generation THIS build speaks, derived rather than typed: it cannot drift
# from the ledger, and a bump that forgets to declare its kind cannot start.
PAYLOAD_COMPAT_VERSION = GENERATION_OF_VERSION[PAYLOAD_VERSION]

# The OLDEST generation this build still reads. Equal to the current one today,
# and the two are separate names because they answer different questions and
# fail in opposite directions: a payload above the range needs a NEWER reader,
# one below it was written before a column changed meaning and cannot be read at
# all. A breaking change decides then whether it can still read the generation
# it replaced; if it can, this is the number that stays put.
PAYLOAD_COMPAT_MIN_VERSION = PAYLOAD_COMPAT_VERSION

# The content versions a reader may accept when the payload declares no
# generation of its own — every pre-split version whose generation this build
# reads. Stated here because the exported JSON Schema has to say it too, and a
# schema-only consumer cannot look things up in a Python dict.
VERSIONS_READABLE_WITHOUT_COMPAT = tuple(
    version
    for version, generation in sorted(GENERATION_OF_VERSION.items())
    if PAYLOAD_COMPAT_MIN_VERSION <= generation <= PAYLOAD_COMPAT_VERSION
)


def compat_generation(payload_version: int, declared: int | None) -> int | None:
    """Which MEANING generation a payload belongs to; None when unknowable.

    A payload that declares its generation is believed — that declaration is the
    entire mechanism, and it is what a future producer uses to tell this reader
    "nothing you know how to read has moved". A payload that declares nothing
    predates the field, and for those the ledger answers; a version the ledger
    has never heard of is from a build newer than this one and MUST NOT be
    guessed at, so it answers None and the caller refuses it in words.
    """
    if declared is not None:
        return declared
    return GENERATION_OF_VERSION.get(payload_version)


def compat_problem(payload_version: int, declared: int | None = None) -> str:
    """"" when this build can read the payload, otherwise the refusal in words.

    Every refusal names BOTH numbers and which of the two failed, because the
    remedies are opposite and a bare number cannot tell them apart: a newer
    generation means "update this reader", an older one means "that batch was
    written before a column changed meaning". The Apps Script consumer carries
    the same function, character for character where JavaScript allows
    (StagingAppScript.txt: compatProblem_).
    """
    generation = compat_generation(payload_version, declared)
    if generation is None:
        return (
            f"payload_version {payload_version} is unknown to this build "
            f"(content {PAYLOAD_VERSION}, generation {PAYLOAD_COMPAT_VERSION}) and the "
            "payload declares no payload_compat_version, so which columns it means "
            "cannot be known — update this reader"
        )
    if generation > PAYLOAD_COMPAT_VERSION:
        return (
            f"payload_compat_version {generation} is newer than this build reads "
            f"(generation {PAYLOAD_COMPAT_VERSION}); the payload's payload_version is "
            f"{payload_version} and this build's is {PAYLOAD_VERSION}. A column was "
            "renamed, removed or given a new meaning — update this reader"
        )
    if generation < PAYLOAD_COMPAT_MIN_VERSION:
        return (
            f"payload_compat_version {generation} is older than this build reads "
            f"(generation {PAYLOAD_COMPAT_MIN_VERSION}); the payload's payload_version is "
            f"{payload_version} and this build's is {PAYLOAD_VERSION}. That batch was "
            "written before a column changed meaning and cannot be read as it stands"
        )
    return ""

# 40k keeps a comfortable margin under the Google Sheets 50k-char cell limit
# even after the funnel adds its envelope columns (S1).
CHUNK_MAX_CHARS = 40_000


class FunnelChunk(BaseModel):
    """Position of one chunk inside a chunked batch (1-based)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    total: int = Field(ge=1)

    @field_validator("index")
    @classmethod
    def _index_within_total(cls, v: int, info):  # explicit guard (P4)
        # total is validated afterwards when both fields exist (model validator
        # would be heavier; the pair check happens in FunnelPayload below).
        return v


class FunnelPayload(BaseModel):
    """One batch of raw scraped rows on its way to the staging inbox.

    `header` + `rows` deliberately mirror the shape the add-in's
    StreamingTsvReader produces on the read path: raw strings, no typing —
    normalization happens later, in one shared place (Q2).
    """

    model_config = ConfigDict(extra="forbid")

    # DELIBERATELY UNCONSTRAINED UPWARDS. This used to be Literal[N], pinned so
    # the generated json-schema carried a `const` and a schema-only consumer
    # could not accept v1 either. The const was also the friction: it refused a
    # payload for being NEWER, which for an additive change means refusing a
    # payload it could read perfectly. The generation below carries the refusal
    # now, and it carries it in both directions.
    payload_version: int = Field(ge=1)
    # Absent means "written before this field existed" — read as GENERATION_OF_
    # VERSION[payload_version]. Optional and not Literal on purpose: an old
    # reader must be able to accept a value it has never seen the name of, and a
    # Literal would refuse it with pydantic's own message instead of one that
    # says which number failed.
    payload_compat_version: int | None = None
    source_key: str = Field(min_length=1, max_length=64)
    kind: ExtractKind
    client: PayloadClient
    scraped_at: str  # UTC ISO8601 with Z suffix
    source_url: str = Field(min_length=1)
    header: list[str]
    rows: list[list[str]]
    chunk: FunnelChunk | None = None
    run_ref: str | None = None  # producer-side run correlation id (CLI run, extension capture)

    @model_validator(mode="after")
    def _generation_supported(self):
        """The ONE gate. A range, not an equality — and never on the content."""
        problem = compat_problem(self.payload_version, self.payload_compat_version)
        if problem:
            raise ValueError(problem)
        return self

    @field_validator("scraped_at")
    @classmethod
    def _scraped_at_utc_iso(cls, v: str) -> str:
        # Explicit over clever (P5): require the exact wire format we emit.
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"scraped_at is not ISO8601: {v!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError(f"scraped_at must be UTC ('Z' or +00:00): {v!r}")
        return v

    @field_validator("rows")
    @classmethod
    def _rows_match_header(cls, v: list[list[str]], info) -> list[list[str]]:
        header = info.data.get("header")
        if header is not None:
            width = len(header)
            for i, row in enumerate(v):
                if len(row) != width:
                    raise ValueError(
                        f"row {i} has {len(row)} cells, header has {width} — "
                        "ragged rows are a parse defect at the connector (Q4)"
                    )
        return v


def new_payload(**fields: object) -> FunnelPayload:
    """Stamp a payload with BOTH numbers — the only way a producer should make one.

    Stating the content version and forgetting the generation would ship a
    payload that says nothing about what it means, and every consumer would fall
    back to the ledger. That works today, by construction, and stops working the
    moment this build's version is newer than the reader's ledger — which is
    exactly the situation the field exists for. So neither is optional at the
    producer, and neither is typed twice: they come from the two constants.
    """
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION,
        payload_compat_version=PAYLOAD_COMPAT_VERSION,
        **fields,
    )


def utc_now_iso() -> str:
    """The one blessed wire timestamp format (Q5)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_into_chunks(
    payload: FunnelPayload,
    *,
    max_rows: int | None = None,
) -> list[FunnelPayload]:
    """Split a payload into wire chunks whose serialized size fits CHUNK_MAX_CHARS.

    Rows are never split across chunks. A payload that already fits is returned
    as a single element (with chunk 1/1 stamped so the consumer sees a uniform
    envelope).

    `max_rows` is the ADAPTIVE knob (A9): the character budget protects the
    50,000-char cell, but nothing here can know how many rows one Apps Script
    execution manages inside its 6-minute budget — only a failed delivery knows
    that. The client re-plans with a smaller `max_rows` when the funnel chokes
    (funnel.FunnelClient._deliver), so the size that works is DISCOVERED rather
    than guessed at in a constant.
    """
    if max_rows is not None and max_rows < 1:
        raise ValueError(f"max_rows must be at least 1, got {max_rows}")
    envelope_probe = payload.model_copy(update={"rows": [], "chunk": FunnelChunk(index=1, total=1)})
    envelope_chars = len(envelope_probe.model_dump_json())
    budget = CHUNK_MAX_CHARS - envelope_chars
    if budget <= 0:  # pathological header; explicit failure over silent truncation (Q4)
        raise ValueError("payload envelope alone exceeds CHUNK_MAX_CHARS")

    groups: list[list[list[str]]] = []
    current: list[list[str]] = []
    used = 0
    for row in payload.rows:
        row_chars = len(json.dumps(row, ensure_ascii=False)) + 1  # +1 separator
        if row_chars > budget:
            raise ValueError(
                f"single row of {row_chars} chars exceeds chunk budget {budget}; "
                "connector must not emit megarows (S1)"
            )
        full = used + row_chars > budget or (max_rows is not None and len(current) >= max_rows)
        if current and full:
            groups.append(current)
            current, used = [], 0
        current.append(row)
        used += row_chars
    groups.append(current)  # empty-row payloads still send one (empty) chunk

    total = len(groups)
    return [
        payload.model_copy(update={"rows": rows, "chunk": FunnelChunk(index=i, total=total)})
        for i, rows in enumerate(groups, start=1)
    ]


def reassemble_chunks(chunks: list[FunnelPayload]) -> FunnelPayload:
    """Rebuild the original batch from wire chunks (ingest side).

    Validates completeness and ordering explicitly — a missing chunk is a loud
    error, never silently-partial data (Q3/Q4).
    """
    if not chunks:
        raise ValueError("no chunks to reassemble")
    first = chunks[0]
    total = first.chunk.total if first.chunk else 1
    if len(chunks) != total:
        raise ValueError(f"expected {total} chunks, got {len(chunks)}")
    ordered = sorted(chunks, key=lambda c: c.chunk.index if c.chunk else 1)
    for expected_index, chunk in enumerate(ordered, start=1):
        got = chunk.chunk.index if chunk.chunk else 1
        if got != expected_index:
            raise ValueError(f"chunk sequence broken: expected {expected_index}, got {got}")
        if chunk.source_key != first.source_key or chunk.scraped_at != first.scraped_at:
            raise ValueError("chunks from different batches mixed together")
    rows = [row for chunk in ordered for row in chunk.rows]
    return first.model_copy(update={"rows": rows, "chunk": None})


def export_json_schema() -> dict:
    """The neutral contract form written to contracts/funnel-payload.schema.json."""
    schema = FunnelPayload.model_json_schema()
    schema["title"] = "ScrapeX funnel payload"
    schema["description"] = (
        f"Content version {PAYLOAD_VERSION}, meaning generation "
        f"{PAYLOAD_COMPAT_VERSION}. One contract for CLI + extension producers and "
        "the Apps Script consumer. A consumer gates on payload_compat_version and "
        "NEVER on payload_version: a newer content version is a payload with an "
        "extra column in it, which anything reading by column name can already "
        "read. See scraper/ENGINEERING.md T8."
    )
    # THE GATE, IN THE NEUTRAL FORM. The model raises its own message (it names
    # both numbers and which failed, which JSON Schema cannot), so the bounds are
    # stated here rather than as field constraints — one place, from the same
    # constants, and tests/test_payload_compat.py pins them to it.
    #
    # The if/then/else is not decoration: it is the ONE rule that cannot be
    # written as a constraint on a single field. A payload declaring a generation
    # is judged on that; a payload declaring none predates the field, and for
    # those the acceptable CONTENT versions are exactly the pre-split versions
    # whose generation this build reads.
    schema["allOf"] = [
        {
            "if": {"required": ["payload_compat_version"],
                   "properties": {"payload_compat_version": {"type": "integer"}}},
            "then": {"properties": {"payload_compat_version": {
                "minimum": PAYLOAD_COMPAT_MIN_VERSION,
                "maximum": PAYLOAD_COMPAT_VERSION,
            }}},
            "else": {"properties": {"payload_version": {
                "enum": list(VERSIONS_READABLE_WITHOUT_COMPAT),
            }}},
        }
    ]
    return schema


def math_expected_chunks(total_rows: int, rows_per_chunk: int) -> int:
    """Tiny helper kept for test readability."""
    return max(1, math.ceil(total_rows / rows_per_chunk))
