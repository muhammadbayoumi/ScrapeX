"""The two version numbers: what each one refuses, and what neither may allow.

One number used to answer two questions, and every consumer checked it for
EQUALITY. So four new columns — columns the Apps Script funnel would have
written without being told anything, because it builds each sheet from the
payload's own header — cost the owner a hand re-paste of the whole script into
his spreadsheet. That is the friction these tests exist to keep dead.

The equality gate was not stupid, though, and half of this file is about what it
was protecting. A header-driven consumer treats a RENAMED column as a brand-new
one: it writes the new name beside the old, the old keeps filling with nothing,
and nothing anywhere errors. So a rename must move PAYLOAD_COMPAT_VERSION, and
`test_no_column_may_disappear_...` is what fails the build when one does not.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scrapex import rowspec
from scrapex.payload import (
    GENERATION_OF_VERSION,
    PAYLOAD_COMPAT_MIN_VERSION,
    PAYLOAD_COMPAT_VERSION,
    PAYLOAD_VERSION,
    VERSIONS_READABLE_WITHOUT_COMPAT,
    FunnelPayload,
    compat_generation,
    compat_problem,
    export_json_schema,
    new_payload,
)
from scrapex.rowspec import RowView
from scrapex.vocab import ExtractKind

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
APPS_SCRIPT = ROOT / "apps_script" / "StagingAppScript.txt"


def payload(**overrides) -> dict:
    body = {
        "payload_version": PAYLOAD_VERSION,
        "payload_compat_version": PAYLOAD_COMPAT_VERSION,
        "source_key": "MADAR",
        "kind": "product_prices",
        "client": "cli",
        "scraped_at": "2026-07-16T10:00:00Z",
        "source_url": "https://www.madar.com/graphql",
        "header": ["external_product_id", "price"],
        "rows": [["4672", "112.50"]],
    }
    body.update(overrides)
    return body


# ---- the friction being removed ---------------------------------------------

def test_a_newer_content_version_is_accepted_by_a_reader_speaking_the_old_generation():
    """THE POINT OF THE WHOLE CHANGE.

    A future ScrapeX adds a column, stamps content 99, and says "still
    generation 5". This build has never heard of 99 and must read it anyway.
    Under the old `v != PAYLOAD_VERSION` gate this was a hard refusal, and the
    only cure was pasting a new Apps Script into the sheet.
    """
    accepted = FunnelPayload.model_validate(
        payload(payload_version=99, payload_compat_version=PAYLOAD_COMPAT_VERSION)
    )
    assert accepted.payload_version == 99
    assert accepted.payload_compat_version == PAYLOAD_COMPAT_VERSION
    assert compat_problem(99, PAYLOAD_COMPAT_VERSION) == ""


def test_the_content_version_never_refuses_anything_on_its_own():
    """Every content version in the ledger that belongs to a readable
    generation is readable, whatever its number."""
    for version, generation in GENERATION_OF_VERSION.items():
        readable = PAYLOAD_COMPAT_MIN_VERSION <= generation <= PAYLOAD_COMPAT_VERSION
        # Declared explicitly: the content number is irrelevant to the verdict.
        assert (compat_problem(version, PAYLOAD_COMPAT_VERSION) == "") is True
        # Undeclared: the ledger decides, and it decides by GENERATION.
        assert (compat_problem(version, None) == "") is readable, version


# ---- what the equality gate was protecting, kept ------------------------------

def test_a_newer_generation_is_refused_with_both_numbers_named():
    with pytest.raises(ValidationError) as raised:
        FunnelPayload.model_validate(payload(payload_version=12, payload_compat_version=9))
    message = str(raised.value)
    assert "payload_compat_version 9 is newer" in message
    assert f"generation {PAYLOAD_COMPAT_VERSION}" in message, "the reader's number is missing"
    assert "payload_version is 12" in message, "the payload's own content number is missing"
    assert f"this build's is {PAYLOAD_VERSION}" in message, "the build's content number is missing"
    assert "renamed, removed or given a new meaning" in message


def test_an_older_generation_is_refused_and_says_something_different():
    """The two directions need different words: one means "update the reader",
    the other means "that batch cannot be read at all". A message carrying one
    bare number cannot tell the owner which he is looking at."""
    with pytest.raises(ValidationError) as raised:
        FunnelPayload.model_validate(payload(payload_version=1, payload_compat_version=1))
    message = str(raised.value)
    assert "payload_compat_version 1 is older" in message
    assert f"generation {PAYLOAD_COMPAT_MIN_VERSION}" in message
    assert f"this build's is {PAYLOAD_VERSION}" in message
    assert "before a column changed meaning" in message
    assert "update this reader" not in message, (
        "an older batch is not fixed by updating the reader; saying so would send "
        "the owner after the wrong remedy")


def test_an_unknown_version_declaring_no_generation_is_refused_not_guessed():
    with pytest.raises(ValidationError, match="payload_version 42 is unknown"):
        FunnelPayload.model_validate(payload(payload_version=42, payload_compat_version=None))
    assert compat_generation(42, None) is None


# ---- the mailbox that predates the field --------------------------------------

def test_batches_written_before_the_field_existed_are_still_readable():
    """_INBOX holds batches stamped 6 with no generation on them at all.

    6 was additive over 5, so a 6 IS a generation 5, and the ledger is the only
    thing that knows it. Get this wrong and every tab in the owner's spreadsheet
    goes stale the day he pastes the new script — the sync would refuse its own
    history for being too NEW, which is the bug this change exists to remove,
    reappearing from the other side.
    """
    legacy = FunnelPayload.model_validate(payload(payload_version=6, payload_compat_version=None))
    assert legacy.payload_compat_version is None
    assert compat_generation(6, None) == PAYLOAD_COMPAT_VERSION


def test_the_ledger_and_the_two_constants_cannot_disagree():
    assert GENERATION_OF_VERSION[PAYLOAD_VERSION] == PAYLOAD_COMPAT_VERSION
    assert PAYLOAD_COMPAT_MIN_VERSION <= PAYLOAD_COMPAT_VERSION
    assert set(VERSIONS_READABLE_WITHOUT_COMPAT) == {
        version for version, generation in GENERATION_OF_VERSION.items()
        if PAYLOAD_COMPAT_MIN_VERSION <= generation <= PAYLOAD_COMPAT_VERSION
    }
    # A generation is named after the version at which it began, so no version
    # can belong to a generation that starts after it.
    for version, generation in GENERATION_OF_VERSION.items():
        assert generation <= version, f"version {version} claims generation {generation}"


def test_no_producer_can_build_a_payload_without_the_stamp():
    """One place applies the two numbers, so no producer can half-apply them.

    A producer that stamped the content version and left the generation off
    would work today — every reader would fall back to the ledger and get the
    right answer — and would break the day this build's version is newer than
    some reader's ledger, which is the exact case the field exists to cover. A
    bug that only appears once the mechanism is needed is a bug that ships.
    """
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "scrapex").rglob("*.py")
        if path.name != "payload.py" and "FunnelPayload(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"{offenders} construct FunnelPayload directly — use payload.new_payload(), "
        "which is the one place PAYLOAD_VERSION and PAYLOAD_COMPAT_VERSION are applied")


def test_the_outbox_carries_the_generation_across_a_restart():
    """A spooled batch is re-read by whatever build runs next, so the generation
    has to survive the round-trip to disk (funnel.py writes model_dump_json and
    reads it back with model_validate_json)."""
    spooled = new_payload(source_key="MADAR", kind=ExtractKind.PRODUCT_PRICES, client="cli",
                          scraped_at="2026-07-16T10:00:00Z", source_url="scrapex://x",
                          header=["price"], rows=[["1.00"]]).model_dump_json()
    assert FunnelPayload.model_validate_json(spooled).payload_compat_version == \
        PAYLOAD_COMPAT_VERSION


def test_every_producer_stamps_both_numbers():
    made = new_payload(source_key="MADAR", kind=ExtractKind.PRODUCT_PRICES, client="cli",
                       scraped_at="2026-07-16T10:00:00Z", source_url="scrapex://x",
                       header=["price"], rows=[["1.00"]])
    assert made.payload_version == PAYLOAD_VERSION
    assert made.payload_compat_version == PAYLOAD_COMPAT_VERSION
    on_the_wire = json.loads(made.model_dump_json())
    assert on_the_wire["payload_compat_version"] == PAYLOAD_COMPAT_VERSION, (
        "the generation has to travel; a reader with an older ledger has nothing "
        "else to go on")


# ---- THE RENAME: a dropped column must fail the build ------------------------

def test_no_column_may_disappear_without_the_generation_moving():
    """The dangerous case, and the one the version gate cannot see on its own.

    A consumer that builds its sheet from the payload's header treats a renamed
    column as a new one: it writes `brand` beside the `brand_raw` that is now
    never filled, and both sit there looking like data. That is worse than an
    error, so a rename MUST move PAYLOAD_COMPAT_VERSION — and this is what fails
    the build when it does not.

    The baseline is a FLOOR, not a mirror: additions are fine and are not
    recorded here, which is exactly what makes an additive change free.
    """
    baseline = json.loads((CONTRACTS / "header-baseline.json").read_text(encoding="utf-8"))

    assert baseline["payload_compat_version"] == PAYLOAD_COMPAT_VERSION, (
        f"contracts/header-baseline.json describes generation "
        f"{baseline['payload_compat_version']} and this build speaks "
        f"{PAYLOAD_COMPAT_VERSION} (content {PAYLOAD_VERSION}) — the generation moved, so "
        "write the new baseline in the same commit: python -m scrapex.cli export-contract")

    for kind, pinned in baseline["kinds"].items():
        current = set(rowspec.spec_for(ExtractKind(kind)).columns)
        gone = [column for column in pinned if column not in current]
        assert not gone, (
            f"{kind}: {gone} disappeared from the row spec while "
            f"PAYLOAD_COMPAT_VERSION stood still at {PAYLOAD_COMPAT_VERSION} "
            f"(content version {PAYLOAD_VERSION}). Renaming or removing a column is a "
            "BREAKING change: a header-driven consumer writes the new name beside the "
            "stale old one and reports nothing. Give the new version its own generation "
            "in payload.GENERATION_OF_VERSION, then regenerate the baseline.")


def test_the_baseline_is_never_rewritten_for_the_generation_it_describes(tmp_path, monkeypatch):
    """A baseline that regenerated itself would guard nothing.

    The floor only means something if it predates the change being reviewed. Let
    `export-contract` refresh it in place and a rename would simply move the
    floor down with it — the guard would go green on the exact commit it exists
    to stop. So an existing baseline for the CURRENT generation is left alone,
    and only a generation it has never described gets a new file, which is the
    same act as declaring the break.
    """
    from scrapex import cli

    monkeypatch.setattr(cli, "CONTRACTS_DIR", tmp_path)
    path = tmp_path / "header-baseline.json"

    assert "wrote" in cli._write_header_baseline()
    first = path.read_text(encoding="utf-8")

    # Someone drops a column and re-runs the exporter hoping for a clean build.
    doctored = json.loads(first)
    doctored["kinds"]["product_prices"] = ["only_one_column_left"]
    path.write_text(json.dumps(doctored, indent=2) + "\n", encoding="utf-8")

    assert "kept" in cli._write_header_baseline()
    assert json.loads(path.read_text(encoding="utf-8")) == doctored, (
        "the exporter overwrote a baseline for its own generation; the floor "
        "would move with every rename and catch nothing")

    # A generation this file has never described DOES get written.
    doctored["payload_compat_version"] = PAYLOAD_COMPAT_VERSION - 1
    path.write_text(json.dumps(doctored, indent=2) + "\n", encoding="utf-8")
    assert "wrote" in cli._write_header_baseline()
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(first)


def test_the_baseline_covers_every_spec_there_is():
    """A spec missing from the baseline is a spec whose columns nothing guards."""
    baseline = json.loads((CONTRACTS / "header-baseline.json").read_text(encoding="utf-8"))
    assert set(baseline["kinds"]) == {spec.kind.value for spec in rowspec.ALL_SPECS}


def test_the_guard_notices_a_rename(monkeypatch):
    """The test above must be able to FAIL. Rename a column in the spec, leave
    the generation where it is, and the build has to stop.

    A guard nobody has watched fail is a guard nobody knows is wired up — the
    reason this repo makes the panel suite prove it RAN (see .github/ci.yml).
    """
    original = rowspec.spec_for
    doctored = dataclasses.replace(
        rowspec.PRODUCT_PRICES,
        columns=tuple("product_name_arabic" if column == "product_name_ar" else column
                      for column in rowspec.PRODUCT_PRICES.columns),
    )
    monkeypatch.setattr(rowspec, "spec_for", lambda kind: (
        doctored if kind == ExtractKind.PRODUCT_PRICES else original(kind)))

    with pytest.raises(AssertionError, match="product_name_ar.*disappeared from the row spec"):
        test_no_column_may_disappear_without_the_generation_moving()


# ---- A REORDER, on the other hand, must stay safe ----------------------------

def test_a_reordered_header_still_lands_under_the_right_names():
    """Safe because every reader reads by NAME — proved here rather than trusted.

    This is the other half of why an additive change can be free: if position
    mattered, appending a column would be as dangerous as renaming one.
    """
    spec = rowspec.PRODUCT_PRICES
    shuffled = list(reversed(spec.columns))
    row = [f"value-of-{column}" for column in shuffled]

    view = RowView(spec, shuffled)
    for column in spec.columns:
        assert view.get(row, column) == f"value-of-{column}"


def test_a_reordered_header_survives_the_payload_contract_too():
    spec = rowspec.PRODUCT_PRICES
    shuffled = list(reversed(spec.columns))
    built = new_payload(
        source_key="MADAR", kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-16T10:00:00Z", source_url="scrapex://export/MADAR",
        header=shuffled, rows=[[f"value-of-{column}" for column in shuffled]])
    view = RowView(spec, built.header)
    assert view.get(built.rows[0], "price") == "value-of-price"
    assert view.get(built.rows[0], "external_product_id") == "value-of-external_product_id"


# ---- the golden vectors, each failing for its OWN reason ---------------------

@pytest.mark.parametrize("fixture", [
    "payload_valid.json",
    "payload_valid_newer_content.json",
    "payload_valid_unstamped_legacy.json",
])
def test_valid_fixtures_parse(fixture: str):
    parsed = FunnelPayload.model_validate_json(
        (CONTRACTS / "fixtures" / fixture).read_text(encoding="utf-8"))
    assert parsed.source_key == "MADAR"


@pytest.mark.parametrize("fixture,reason", [
    ("payload_invalid_v1.json", "is older than this build reads"),
    ("payload_invalid_newer_generation.json", "is newer than this build reads"),
    ("payload_invalid_unknown_unstamped.json", "is unknown to this build"),
    ("payload_invalid_ragged.json", "ragged rows are a parse defect"),
    ("payload_invalid_timezone.json", "must be UTC"),
])
def test_invalid_fixtures_are_refused_for_the_reason_they_are_named_for(fixture, reason):
    """Two of these were stamped payload_version 1, so for several releases the
    only reason either was rejected was its version — the raggedness and the
    timezone they are named for went untested behind it. They now carry the
    current stamp, so each vector fails for its own reason or not at all."""
    with pytest.raises(ValidationError, match=reason):
        FunnelPayload.model_validate_json(
            (CONTRACTS / "fixtures" / fixture).read_text(encoding="utf-8"))


# ---- ONE definition of the two numbers, in three languages ------------------

def test_the_exported_schema_carries_the_gate_and_not_an_equality():
    """A consumer validating against the neutral form must reach the same verdict
    as the model: gate on the generation, never on the content version."""
    schema = export_json_schema()
    assert "const" not in schema["properties"]["payload_version"], (
        "a const on the content version is the friction this change removed")

    rule = schema["allOf"][0]
    assert rule["then"]["properties"]["payload_compat_version"] == {
        "minimum": PAYLOAD_COMPAT_MIN_VERSION, "maximum": PAYLOAD_COMPAT_VERSION}
    assert rule["else"]["properties"]["payload_version"]["enum"] == \
        list(VERSIONS_READABLE_WITHOUT_COMPAT), (
        "a payload declaring no generation is judged on its content version, and "
        "only the pre-split versions this build reads may pass")

    committed = json.loads((CONTRACTS / "funnel-payload.schema.json").read_text(encoding="utf-8"))
    assert committed == schema, (
        "contracts/funnel-payload.schema.json is stale — run: "
        "python -m scrapex.cli export-contract")


def test_the_apps_script_mirror_cannot_drift_from_python():
    """Both numbers AND the ledger live in two languages, and only one of them is
    Python. The Apps Script is pasted by hand into a spreadsheet, so nothing but
    this test can notice when its copy stops agreeing."""
    script = APPS_SCRIPT.read_text(encoding="utf-8")

    assert f"const SYNC_PAYLOAD_VERSION = {PAYLOAD_VERSION};" in script
    assert f"const SYNC_PAYLOAD_COMPAT_VERSION = {PAYLOAD_COMPAT_VERSION};" in script
    assert f"const SYNC_PAYLOAD_COMPAT_MIN_VERSION = {PAYLOAD_COMPAT_MIN_VERSION};" in script

    ledger = ", ".join(f'"{version}": {generation}'
                       for version, generation in sorted(GENERATION_OF_VERSION.items()))
    assert f"const SYNC_GENERATION_OF_VERSION = {{ {ledger} }};" in script, (
        "the Apps Script ledger disagrees with payload.GENERATION_OF_VERSION; a sheet "
        "reading an old batch as the wrong generation is how stale columns get "
        f"trusted. Python says: {{ {ledger} }}")

    # The gate itself, not just the numbers: the script must refuse on the
    # generation and must NOT have kept a content-version equality anywhere.
    assert "compatProblem_(chunks[0].version, chunks[0].compat)" in script
    assert "!== SYNC_PAYLOAD_VERSION" not in script, (
        "an equality check on the content version is back; that is the re-paste")
