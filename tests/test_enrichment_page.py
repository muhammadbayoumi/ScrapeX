"""The organization workspace is owned by the extension and wired to the engine."""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "extension" / "enrichment.html").read_text(encoding="utf-8")
JS = (ROOT / "extension" / "enrichment.js").read_text(encoding="utf-8")
APP = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")


def test_the_dataset_action_opens_the_extension_workspace():
    assert 'action: "enrich"' in APP
    assert '"enrichment.html?source="' in APP
    assert '"&site=" + encodeURIComponent(siteKey)' in APP
    assert "chrome.runtime.getURL" in APP


def test_the_workspace_exposes_the_complete_owner_flow():
    for identifier in (
        "source-dataset", "detail-dataset", "entity-key", "detail-key",
        "field-mapping", "providers", "output-key", "create-definition",
        "run-enrichment", "run-enrichment-complete", "job-progress",
        "review-rows", "open-data",
    ):
        assert f'id="{identifier}"' in HTML
    assert "/api/enrichment/sources/" in JS
    assert "?site_key=" in JS
    assert "site_key: siteKey || null" in JS
    assert "encodeURIComponent(definition.site_key)" in JS
    assert "/api/enrichment/definitions" in JS
    assert "/api/jobs/" in JS
    assert 'runEnrichment("update")' in JS
    assert 'runEnrichment("complete")' in JS
    assert "restoreLatestJob" in JS
    assert "Providers disabled" in JS
    assert '"hidden", Boolean(definition) && !editMode' in JS


def test_interface_copy_is_english_and_arabic_is_only_named_as_source_data():
    assert '<html lang="en">' in HTML
    assert "Organization Enrichment" in HTML
    assert "Arabic source value" in JS
    assert not any("\u0600" <= char <= "\u06ff" for char in HTML + JS)
