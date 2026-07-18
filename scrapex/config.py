"""Harvest Manifest models + validation (ENGINEERING.md S5).

sources.yaml is the extraction CONTRACT for the whole system (owner principle:
"له أساس ليس جمعاً عشوائياً"). This module is its single validator — the same
validation runs in CI on every push, at CLI startup, and inside tests, so a
broken contract can neither merge nor run.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .vocab import Authority, Cadence, ConnectorFamily, ExtractKind, ExtractScope, Fetcher, VatMode

MANIFEST_FILE = Path(__file__).resolve().parent.parent / "sources.yaml"

_SOURCE_KEY = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_REGION = re.compile(r"^([A-Z]{2}|\*)$")  # ISO 3166-1 alpha-2 or wildcard
_MATERIAL_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class ExtractSpec(BaseModel):
    """One extract block: exactly WHAT this source may produce (the contract)."""

    model_config = ConfigDict(extra="forbid")

    kind: ExtractKind
    scope: ExtractScope = ExtractScope.TARGETED
    materials: list[str] = Field(default_factory=list)  # material keys; empty = kind-wide
    regions: list[str] = Field(default_factory=lambda: ["*"])
    categories: list[str] = Field(default_factory=list)  # source category codes, when targeting

    @field_validator("regions")
    @classmethod
    def _regions_vocab(cls, v: list[str]) -> list[str]:
        for region in v:
            if not _REGION.match(region):
                raise ValueError(
                    f"region {region!r} is not ISO 3166-1 alpha-2 or '*'"
                )
        return v

    @field_validator("materials")
    @classmethod
    def _material_vocab(cls, v: list[str]) -> list[str]:
        for key in v:
            if not _MATERIAL_KEY.match(key):
                raise ValueError(f"material key {key!r} must be UPPER_SNAKE_CASE")
        return v


class SourceEntry(BaseModel):
    """One source's full contract."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    source_name: str
    base_url: str
    family: ConnectorFamily
    cadence: Cadence = Cadence.MANUAL
    authority: Authority = Authority.SHOP
    fetcher: Fetcher = Fetcher.HTTP
    active: bool = False
    # Per-source facts a product connector needs (offers carry region+currency,
    # but a single-market shop's rows all share these). Commodity sources carry
    # region per row, so their default_region stays '*'.
    currency: str | None = None
    default_region: str = "*"
    vat_mode: VatMode = VatMode.INCLUSIVE
    extract: list[ExtractSpec] = Field(min_length=1)
    # F6 volume-sanity canary (generalized samehgabriel canary):
    min_expected_rows: int | None = Field(default=None, ge=0)
    max_drop_pct: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = None

    @field_validator("source_key")
    @classmethod
    def _key_shape(cls, v: str) -> str:
        if not _SOURCE_KEY.match(v):
            raise ValueError(f"source_key {v!r} must be UPPER_SNAKE_CASE, 3-64 chars")
        return v

    @field_validator("default_region")
    @classmethod
    def _default_region_vocab(cls, v: str) -> str:
        if not _REGION.match(v):
            raise ValueError(f"default_region {v!r} is not ISO 3166-1 alpha-2 or '*'")
        return v

    @model_validator(mode="after")
    def _probe_placeholder_is_inactive(self) -> "SourceEntry":
        # A source that has not been probed cannot be active (A3: no family until proven).
        if self.family == ConnectorFamily.TBD_PROBE and self.active:
            raise ValueError(
                f"{self.source_key}: family is TBD-probe; run `scrapex probe` and set the "
                "real family before activating"
            )
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_source_keys(self) -> "Manifest":
        seen: set[str] = set()
        for entry in self.sources:
            if entry.source_key in seen:
                raise ValueError(f"duplicate source_key {entry.source_key!r}")
            seen.add(entry.source_key)
        return self

    def get(self, source_key: str) -> SourceEntry:
        for entry in self.sources:
            if entry.source_key == source_key:
                return entry
        raise KeyError(f"unknown source_key {source_key!r}")

    def resolve_by_url(self, url: str) -> SourceEntry | None:
        """Match a browsed page URL to a source by registered base_url host
        (used by the extension: 'which source is this tab?'). Host compared
        case-insensitively with a leading 'www.' stripped from both sides."""
        host = _host_of(url)
        if not host:
            return None
        for entry in self.sources:
            if _host_of(entry.base_url) == host:
                return entry
        return None


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url if "//" in url else f"//{url}")
    return (parsed.hostname or "").lower().removeprefix("www.")


def load_manifest(path: Path | str = MANIFEST_FILE) -> Manifest:
    """Parse + validate sources.yaml. Raises with a precise message on any defect."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if raw is None:
        raise ValueError(f"{path}: manifest is empty")
    return Manifest.model_validate(raw)
