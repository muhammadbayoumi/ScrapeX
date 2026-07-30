"""Harvest Manifest models + validation (ENGINEERING.md S5).

sources.yaml is the extraction CONTRACT for the whole system (owner principle:
"له أساس ليس جمعاً عشوائياً"). This module is its single validator — the same
validation runs in CI on every push, at CLI startup, and inside tests, so a
broken contract can neither merge nor run.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

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


class TaxonomyConfig(BaseModel):
    """Where a source publishes its CATEGORIES, when that is not where it
    publishes its products.

    heidelbergmaterials.eg is the case this exists for, and it is a THIRD host:
    prices come from onlinestoreapi.<host> (`api.base_url`), the storefront is
    onlinestore.<host> (`base_url`), and the only real taxonomy the company
    publishes anywhere is on the corporate site www.<host>. The store API's own
    `productTypes` has exactly two values, `Bagged` and `Bulk`, and all nine
    catalogued products are `Bagged` — a packaging type, constant across the
    catalogue, which distinguishes nothing.

    BOTH paths are named explicitly, per language, and neither is derived from
    the other. The site's Arabic and English aliases for one page do NOT share
    a stem — `/en/our-products` against `/ar/our_products_ar` — so any rule
    that built one from the other would be a guess. They are recorded here
    (P5: explicit over a magic URL guess) and each is verified against the
    site's own `<link rel="alternate" hreflang>` in the captured fixtures.
    """

    model_config = ConfigDict(extra="forbid")

    # The taxonomy host root, e.g. https://www.heidelbergmaterials.eg. A
    # DIFFERENT host from base_url and api.base_url, with its own robots.txt
    # and its own session.
    base_url: str | None = None
    # The category listing, once per language. The unmarked field is English,
    # matching the bilingual rule every other column follows.
    listing_path: str | None = None
    listing_path_ar: str | None = None


class ApiConfig(BaseModel):
    """Endpoint facts for connectors whose data API lives on a DIFFERENT host
    than base_url. Only populated for such sources (Hybris OCC: the storefront is
    www.<host> but products come from api.<host>/rest/v2/{base_site}); same-host
    JSON and HTML connectors leave it null. Explicit over a magic URL guess (P5)."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None   # API host root, e.g. https://api.masdaronline.com
    base_site: str | None = None  # OCC baseSite id (Hybris)
    # A STATEMENT OF FACT about one product shape, not an instruction to do
    # arithmetic: "this API's ConfigurableProduct figures are the storefront's
    # tax-EXCLUSIVE ones". The connector never converts them — it records the
    # number the API gave and marks that row tax_included = 0, so the Tax
    # column says "Excl. 15%" beside a simple product's "Incl. 15%".
    #
    # There used to be a `prices_exclude_tax_pct` here (and a shape-scoped
    # twin) that multiplied by 1 + rate. It is gone. Declared source-wide on
    # 2026-07-23 it made 3,312 madar rows 15% too high, and the owner's ruling
    # closes the question for good: «سجلها كما تاخذ البيانات من الموقع بدون
    # تعديل ولكن عمود الضريبة يكون واضح» — record what the site gives,
    # unmodified, and let the tax column say what the number is. A price we
    # computed is a price no page ever printed; a price plus an honest label is
    # two facts, both true. The RATE for that label comes from the source's
    # `tax:` evidence block, where it must carry the sentence it was read from.
    configurable_prices_exclude_tax: bool = False


class TaxEvidence(BaseModel):
    """What the SOURCE says about tax, and where it says it.

    The owner's rule is to be certain of what is written and never assume, so a
    rate may only be recorded together with the sentence it came from and a link
    to that sentence. Three states, because a live survey of a real source found
    exactly three:

      stated   a clause naming a rate            -> rate_pct required
      general  a clause confirming inclusion but -> rate_pct must stay empty
               naming no rate
      unknown  the source publishes nothing      -> shown as unverified

    `region` is '*' for a source-wide statement, or an ISO country code — one
    source can publish a general statement for the site and specific evidence
    for individual countries.
    """

    model_config = ConfigDict(extra="forbid")

    region: str = "*"
    # '*' = the whole source; a material key scopes this evidence to ONE
    # commodity. The site states its tax position per energy-type page, in
    # different words, so one source legitimately holds several.
    material: str = "*"
    vat_mode: VatMode | None = None       # defaults to the source's vat_mode
    evidence: Literal["stated", "general", "unknown"] = "unknown"
    rate_pct: float | None = Field(default=None, ge=0, le=100)
    statement_text: str | None = None
    statement_url: str | None = None
    statement_lang: str | None = None
    verified_at: str | None = None

    @model_validator(mode="after")
    def _evidence_must_be_evidenced(self) -> "TaxEvidence":
        # These mirror the CHECK constraints in migration 0018, so a bad manifest
        # is refused by validate-manifest instead of by SQLite mid-crawl.
        if self.evidence == "stated":
            if self.rate_pct is None:
                raise ValueError("tax evidence 'stated' must name a rate_pct")
            if not self.statement_url:
                raise ValueError(
                    "tax evidence 'stated' must carry statement_url — a rate "
                    "without a source is the assertion this field exists to prevent")
        if self.evidence == "general":
            if self.rate_pct is not None:
                raise ValueError(
                    "tax evidence 'general' means the source confirms inclusion "
                    "WITHOUT naming a rate; use 'stated' if it names one")
            if not self.statement_url:
                raise ValueError("tax evidence 'general' must carry statement_url")
        if self.evidence == "unknown" and (self.rate_pct is not None or self.statement_text):
            raise ValueError(
                "tax evidence 'unknown' means nothing is published; it cannot "
                "carry a rate or a statement")
        return self


class IdentityRules(BaseModel):
    """How a record is recognised again on the next crawl (spec 14).

    Defaults are deliberately automatic — a new user never has to touch this.
    They exist so the Add Site form can PERSIST what it collects instead of
    silently discarding it.
    """

    model_config = ConfigDict(extra="forbid")

    primary: str = "auto"          # auto | source_id | sku | canonical_url | composite
    fallback: str = "auto"
    composite_fields: list[str] = Field(default_factory=list)
    canonical_url_strip_query: bool = True
    on_ambiguous: str = "review"   # review | keep_separate


class SourceEntry(BaseModel):
    """One source's full contract."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    # English is the primary display language, so the unmarked name is English
    # and it is REQUIRED. Requiredness inverts here deliberately: these twelve
    # labels are owner-authored rather than scraped, all twelve already carry
    # both, and the primary column must never be blank on the one surface we
    # fully control. min_length pins that: a blank primary name is refused
    # rather than listed under an empty heading.
    source_name: str = Field(min_length=1)
    # The site's own Arabic name, when it publishes one. Stored BESIDE the
    # primary name, never instead of it — the rule 0033 set for every bilingual
    # field: the warehouse remembers both, the display layer chooses. Optional,
    # so a source that answers in one language only stays valid.
    source_name_ar: str = ""
    # A single-brand shop: every product it sells IS that brand, and the
    # pages never repeat it because on that site it is not information.
    # Stated here, per source, and applied ONLY where the connector found
    # nothing — a shop that names brands per product always wins, so this
    # can never overwrite a real answer with a guess.
    brand: str = ""
    base_url: str
    family: ConnectorFamily
    cadence: Cadence = Cadence.MANUAL
    authority: Authority = Authority.SHOP
    fetcher: Fetcher = Fetcher.HTTP
    api: ApiConfig | None = None
    # Where this source publishes its CATEGORIES, when that is a different host
    # from where it publishes its products. Null for every source whose own
    # listing pages already carry its taxonomy.
    taxonomy: TaxonomyConfig | None = None
    # Some platforms (Zid) 403 non-browser clients; such a source declares the
    # exact UA the fetcher must send. Explicit per source, never a silent global (F5).
    user_agent: str | None = None
    # Ordered families to try if `family` fails (spec 32). Recorded per source so
    # the choice is visible in the manifest rather than hidden in code.
    fallback_families: list[ConnectorFamily] = Field(default_factory=list)
    # True when the site needs a signed-in session. We never bypass access
    # controls (spec 3) — this flags the source so the run reports it honestly.
    auth_required: bool = False
    identity: IdentityRules = Field(default_factory=IdentityRules)
    active: bool = False
    # Per-source facts a product connector needs (offers carry region+currency,
    # but a single-market shop's rows all share these). Commodity sources carry
    # region per row, so their default_region stays '*'.
    currency: str | None = None
    default_region: str = "*"
    vat_mode: VatMode = VatMode.INCLUSIVE
    # Evidence FOR that vat_mode, when the source publishes any. Optional, so
    # every existing entry stays valid — but a source without it is reported as
    # unverified rather than quietly trusted, which is the whole point:
    # vat_mode on its own is a claim, not a source.
    tax: list[TaxEvidence] = Field(default_factory=list)
    extract: list[ExtractSpec] = Field(min_length=1)
    # DISPLAY, not capture. samehgabriel sells 18 products in 6 colours each, so
    # the table showed 108 rows differing only by colour. With this on, the page
    # folds a product's SAME-PRICED variations into one row and lists them
    # together; the warehouse still stores all 108, because what the site
    # published is the record. Per source because it is not universally right —
    # MADAR's variations are a different kind of thing. Owner ruling 2026-07-28.
    fold_variants: bool = False
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
    def _fallbacks_exclude_self(self) -> "SourceEntry":
        # A fallback chain that re-tries the family that just failed would loop
        # over the same failure instead of escalating.
        if self.family in self.fallback_families:
            raise ValueError(
                f"{self.source_key}: fallback_families must not repeat the primary "
                f"family {self.family.value!r}")
        return self

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
