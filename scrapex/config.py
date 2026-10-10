"""Harvest Manifest models + validation (ENGINEERING.md S5).

sources.yaml is the extraction CONTRACT for the whole system (owner principle:
"له أساس ليس جمعاً عشوائياً"). This module is its single validator — the same
validation runs in CI on every push, at CLI startup, and inside tests, so a
broken contract can neither merge nor run.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# WHY THE C LOADER (2026-07-31)
#
# The parser was 97% of load_manifest and pydantic was 0.5% of it — all the
# validators in this file together cost 0.85 ms, while reading 34 KB of YAML cost
# 180 ms. PyYAML ships a libyaml-backed loader that parses the SAME grammar:
#
#   yaml.safe_load(text)                     180.11 ms
#   yaml.load(text, CSafeLoader)              11.89 ms      15x
#   load_manifest() end to end          185 ms -> 16 ms     11.6x
#
# That is 308 parses per test-suite run, and it is a live cost too: five routes
# re-parse the manifest on every source edit (webui/app.py add/update/remove/
# set-active/rename), so every "Add Site" click paid 185 ms of pure-Python parsing.
#
# SafeLoader stays the fallback because libyaml is an optional C extension and a
# pure-Python wheel must still work. That path is byte-identical to the old code:
# yaml.safe_load(s) IS yaml.load(s, SafeLoader). Both loaders were checked against
# each other on 28 inputs (duplicate keys, timestamps, Arabic literals, anchors,
# merge keys, !!python/object, tabs, BOM, multi-document, 200-deep nesting) and on
# all 7 defect classes this function must reject — same values, same exception
# types, same yaml.error hierarchy. No behaviour rides on which one loads.
try:
    from yaml import CSafeLoader as _ManifestLoader
except ImportError:                          # PyYAML built without libyaml
    from yaml import SafeLoader as _ManifestLoader

from .robots import RobotsChoice, RobotsCustom
from .vocab import (
    Authority,
    Cadence,
    ConnectorFamily,
    ExtractKind,
    ExtractScope,
    Fetcher,
    SourceCategory,
    VatMode,
)

MANIFEST_FILE = Path(__file__).resolve().parent.parent / "sources.yaml"

_SOURCE_KEY = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_REGION = re.compile(r"^([A-Z]{2}|\*)$")  # ISO 3166-1 alpha-2 or wildcard
_MATERIAL_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


# ---- the per-source crawl rules, checked in ONE place ------------------------------
#
# A source's robots choice, custom rule, agent and pace reach the warehouse two ways:
# shipped in `sources.yaml` (checked here, by `SourceEntry`) and chosen in the panel
# (`source_settings.save`). They were checked by two different rules, and the manifest's
# was looser: `robots: Obey` or a custom delay of -1 loaded, was written by the panel's
# `/edit` with a 200, and then raised inside the scheduler on every tick, which stopped
# the worker dispatching ANY job (#1589 review). So both doors call these, and a value
# one refuses the other refuses with the same sentence. Each raises ValueError, which a
# pydantic validator reports as the field's error and `source_settings` re-raises as a
# `SourceSettingError` naming the source.

#: The custom rule's knobs, READ OFF `robots.RobotsCustom` rather than written again:
#: a knob added to the rule the crawl obeys is a knob both doors accept.
CUSTOM_RULE_KEYS = frozenset(field.name for field in fields(RobotsCustom))


def checked_robots(value: object) -> RobotsChoice:
    """A robots choice, as the enum the fetcher compares against.

    A misspelt one ('Obey') would otherwise compare unequal to every choice and act as
    the default -- the one outcome nobody would notice."""
    try:
        return RobotsChoice(value)
    except ValueError:
        raise ValueError(f"robots must be one of {[str(c) for c in RobotsChoice]}, "
                         f"not {value!r}") from None


def checked_seconds(name: str, value: object, *, allow_zero: bool) -> float:
    """A duration in seconds, refused unless it is a finite number in bounds.

    Finite because SQLite stores NaN as NULL -- a pace he set would read back as "not
    chosen" -- and an infinite pace is a crawl that never makes its next request; the
    table's `< 9e999` holds the same bound. An integer too large for a float
    (`10**400`) is refused, not raised as OverflowError. Not a bool, because `True` is
    an int in Python and would be one second.
    """
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a number of seconds or null, not {value!r}")
    try:
        seconds = float(value)
    except OverflowError:
        seconds = math.inf
    if not math.isfinite(seconds):
        raise ValueError(f"{name} must be a finite number of seconds, not {value!r}")
    if seconds < 0 or (seconds == 0 and not allow_zero):
        bound = "0 or more" if allow_zero else "more than 0"
        raise ValueError(f"{name} must be {bound}, not {value!r}")
    return seconds


def checked_robots_custom(rule: object) -> dict:
    """A custom robots rule, checked, as a NEW `{enforce_disallow, crawl_delay_s}`.

    `enforce_disallow` is required although `RobotsCustom` defaults it: a rule that does
    not say whether it obeys Disallow is a rule nobody decided, and reading it as False
    would be deciding for him. A delay of 0 is allowed -- "do not wait for this site" --
    because `robots.decide` applies a custom delay as set (#1413).
    """
    if not isinstance(rule, dict) or not set(rule) <= CUSTOM_RULE_KEYS \
            or "enforce_disallow" not in rule:
        raise ValueError("a custom robots rule is {enforce_disallow: true|false, "
                         f"crawl_delay_s: seconds|null}}, not {rule!r}")
    enforce, delay = rule["enforce_disallow"], rule.get("crawl_delay_s")
    if type(enforce) is not bool:
        raise ValueError(f"enforce_disallow must be true or false, not {enforce!r}")
    if delay is not None:
        delay = checked_seconds("crawl_delay_s", delay, allow_zero=True)
    return {"enforce_disallow": enforce, "crawl_delay_s": delay}


def checked_custom_pairing(choice: object, has_rule: bool) -> None:
    """The custom rule exists exactly when the choice is custom -- the table's CHECK.

    Custom with no rule is what `robots.decide` refuses at crawl time, so it is refused
    where it is typed. A rule under another choice is one the crawl ignores, and left
    behind it would govern the site again the day somebody switches back to custom
    (`/api/sources/{key}/edit` clears it for that reason). `choice` None is "not set".
    """
    custom = choice == RobotsChoice.CUSTOM
    if custom and not has_rule:
        raise ValueError("robots = custom needs its rule (robots_custom: "
                         "{enforce_disallow, crawl_delay_s}); choose default or obey, "
                         "or send the rule")
    if not custom and has_rule:
        raise ValueError("a custom robots rule needs robots = custom, and this source's "
                         f"choice is {choice or 'not set'}")


def checked_activation(family: object, active: bool) -> None:
    """A source that has not been probed cannot be active (A3: no family until proven):
    there is no collector to run."""
    if active and family == ConnectorFamily.TBD_PROBE:
        raise ValueError("family is TBD-probe, so there is no collector to run yet; run "
                         "`scrapex probe` and set the real family before activating")


def checked_user_agent(value: object) -> str | None:
    """An agent to send, or None for "none of its own" -- which is what empty means.

    PRINTABLE ASCII, 0x20-0x7E, because a header value is: httpx refuses to send
    anything else -- Arabic letters, an accented one, a line break that would inject a
    header -- so it is refused where it is typed, not at the source's next crawl.
    """
    if value is not None and not isinstance(value, str):
        raise ValueError(f"user_agent must be text or null, not {value!r}")
    agent = (value or "").strip() or None
    if agent is not None and not all(" " <= ch <= "~" for ch in agent):
        raise ValueError("user_agent must be one line of printable ASCII text "
                         "(English letters, digits, spaces and punctuation)")
    return agent


# ---- hosts ScrapeX never contacts --------------------------------------------------
#
# A host lands here when it has been found to be harmful, on the owner's word, and each
# entry names the issue that records why. Every door that takes a URL asks
# `refused_host`: the manifest and the panel's add, edit and probe refuse to declare
# it, and the fetchers refuse to send a request to it -- on every redirect hop and for
# robots.txt too, so a harmless source cannot lead the crawl into it either.
#
# BY NAME, NOT BY ADDRESS. A refused name and every name under it (www., shop.) match;
# an IP literal, or another domain pointing at the same server, does not -- this is a
# list of names somebody decided about, not a firewall.

@dataclass(frozen=True)
class RefusedHost:
    host: str     # the registrable name, lowercase ASCII, e.g. "ahrambc.com"
    reason: str   # what the host did, as a predicate: "served a malware page"
    record: str   # the issue that records it, e.g. "#1644"


REFUSED_HOSTS: dict[str, RefusedHost] = {entry.host: entry for entry in [
    RefusedHost("ahrambc.com", "served a malware page", "#1644"),
]}

_IDEOGRAPHIC_DOTS = re.compile("[。．｡]")


def canonical_host(url: str) -> str:
    """The host a URL names, as the resolver will look it up: lowercase ASCII, no port,
    no user, no trailing dot.

    THE SPELLINGS THAT REACH THE SAME SERVER all come out the same: `AhramBC.com.`,
    `ahrambc。com`, full-width `ａｈｒａｍｂｃ．ｃｏｍ` -- the stdlib IDNA codec maps
    them as a resolver does. A bare `host/path` with no scheme is read as a host, not
    as a path, because a person typing a site into the panel types it that way.
    """
    text = (url or "").strip()
    try:
        host = urlsplit(text if "://" in text else "http://" + text).hostname or ""
    except ValueError:
        # Not a URL at all (an unclosed `[` of an IPv6 literal): it names no host, so
        # none is refused -- whatever reads it next refuses it as malformed.
        return ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        # Not a name IDNA can encode (an over-long label, a forbidden character): no
        # resolver will find it either. Compare what was typed, its dots unified.
        host = _IDEOGRAPHIC_DOTS.sub(".", host)
    return host.lower().rstrip(".")


def refused_host(url: str) -> RefusedHost | None:
    """The registry entry that refuses this URL's host, or None."""
    host = canonical_host(url)
    labels = host.split(".")
    for start in range(len(labels)):
        entry = REFUSED_HOSTS.get(".".join(labels[start:]))
        if entry is not None:
            return entry
    return None


def refusal(entry: RefusedHost) -> str:
    """The one sentence every door says when it refuses a host.

    THE HOST AND ITS CAUSE FIRST: the Jobs row clamps its error to two lines, and at
    320 px after his longest key (`ARAMCO_FUEL_SA: `) that leaves about forty
    characters -- measured, review of #1644 -- so they come before the rest, and the
    record last, where a clamp costs nothing. SCRAPEX IS NAMED as the one refusing:
    the same slot already says "Connection refused" for a site that refused us, and
    a bare "Refused ahrambc.com" reads either way (copywriting.mdx@86c813ec:64-87).
    """
    return f"{entry.host} {entry.reason}, so ScrapeX sends it nothing ({entry.record})."


class RefusedHostError(ValueError):
    """A door was handed a URL on a refused host. Its text is `refusal`, whole, so a
    route can show it as it is rather than under "invalid source:"."""


def checked_host(url: object) -> str:
    """A URL whose host ScrapeX may contact, or RefusedHostError with the refusal."""
    if url is None:
        return url
    entry = refused_host(str(url))
    if entry is not None:
        raise RefusedHostError(refusal(entry))
    return url


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

    @field_validator("base_url")
    @classmethod
    def _taxonomy_host_is_not_refused(cls, v: str | None) -> str | None:
        return checked_host(v)


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

    @field_validator("base_url")
    @classmethod
    def _api_host_is_not_refused(cls, v: str | None) -> str | None:
        return checked_host(v)


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

    @field_validator("statement_url")
    @classmethod
    def _statement_host_is_not_refused(cls, v: str | None) -> str | None:
        return checked_host(v)

    @model_validator(mode="after")
    def _evidence_must_be_evidenced(self) -> TaxEvidence:
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


class UnitWitness(BaseModel):
    """One field that may state a unit, and what kind of statement it is."""

    model_config = ConfigDict(extra="forbid")

    field: str
    # Which language the field is written in. It travels with the reading, so
    # the owner can see that «20 كيلو» in the Arabic name is what answered —
    # not a translation of the English one.
    lang: str = "und"
    # A closed vocabulary, so "where did this come from" has a small number of
    # answers rather than free text. declared_by_source is a machine-readable
    # field the site publishes; stated_in_name and stated_field are the site's
    # own words for a person to read; stated_in_prose is a sentence it has to
    # be dug out of; declared_by_owner is OUR constant, and says so.
    provenance: Literal["declared_by_source", "stated_in_name", "stated_field",
                        "stated_in_prose", "declared_by_owner"] = "stated_field"
    # HOW the field speaks. "quantity" is one field holding "20 kg" and is all
    # sikaegshop needs. "pair" is a number here and its unit word in
    # `unit_field` — madar's platform publishes weight and weight_unit that way.
    # "container" is «N unit / container», where what you buy is the container
    # and N of the unit is what is in it.
    shape: Literal["quantity", "pair", "container"] = "quantity"
    # Only for shape "pair": where the unit WORD lives.
    unit_field: str = ""


class UnitCorroborator(BaseModel):
    """A field that may CONFIRM a unit and may never originate one."""

    model_config = ConfigDict(extra="forbid")

    field: str


class UnitScales(BaseModel):
    """Which measurement units can be a selling unit on this site."""

    model_config = ConfigDict(extra="forbid")

    # An allow-list. Anything absent is not a candidate, which is what stops
    # «سيكا باكينج رود 1 سم» becoming a one-centimetre selling unit.
    pack: list[str] = Field(min_length=1)
    # Units to strike from a text before reading it, for a site that writes a
    # dimension using a pack-scale word. Optional, and deliberately absent
    # where it earns nothing: measured over sikaegshop's 87 products it
    # changed zero answers, so it is not declared there.
    dimension: list[str] = []


class UnitCharter(BaseModel):
    """How ONE site states what one of its priced things is.

    Data, not code. The owner has hundreds of sites waiting and a Python
    branch per site is not a method — «كل موقع ندخله المفروض نشوف طريقة معينة
    لقياس وتحديد وحداته ونطور الأمر مع الوقت». Validated here so a charter
    that names an impossible provenance or declares no pack scale fails the
    build rather than quietly resolving nothing.

    The version travels into every witness string, so a reading can always be
    traced to the rules that authorised it, and a revision is a diff the owner
    can read.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    witnesses: list[UnitWitness] = Field(min_length=1)
    corroborators: list[UnitCorroborator] = []
    scales: UnitScales
    # canonical container -> the words this site writes for it. Its job is to
    # make one code out of the two languages the same shop uses: measured on
    # madar, without it «صندوق» (16) and "box" (24) are two different selling
    # units for one box and two prices for the same product stop comparing.
    # It is NOT what rejects a size like 1-1/2" — the reader requires letters
    # on both sides of the slash, so a fraction never reaches this list.
    containers: dict[str, list[str]] = {}


class SourceEntry(BaseModel):
    """One source's full contract."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    # Absent for a source nobody has studied yet, and that is a state
    # rather than an omission: a source with no charter resolves no
    # units at all, which is honest. Ten of eleven are in it today.
    unit_charter: UnitCharter | None = None
    # WHICH LANGUAGE THE SITE SERVES AT ITS ROOT. Not a preference and not a
    # guess: shopify's connector files the default locale's title and then
    # fetches the OTHER locale for the second column, and it had "ar" written
    # into it as an assumption. SPARK_ESHOP serves English at its root and has
    # no /en locale at all — that URL 404s — so 1,789 English titles were filed
    # as Arabic and the English column, which config calls required, stayed
    # empty on every one.
    #
    # Declared per source because the alternative is detecting it, and
    # detecting it is guessing: "ABB 1SDA100487R1 | XT5H 630 TMA 630-6300"
    # carries no letters to detect. The shop states it — <html lang> — and a
    # person checks it once.
    default_language: Literal["ar", "en"] = "ar"
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
    # WHAT KIND of thing this source publishes (`R-32`). Defaults to `products`
    # because every one of the thirteen sources in the manifest today IS a products
    # source -- so the default is a statement of fact, not a convenience, and no
    # existing entry has to be edited. A future contractors entry states it.
    category: SourceCategory = SourceCategory.PRODUCTS
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
    # ROBOTS IS A PER-SITE DECISION, and this is where the owner records it.
    # "default" defers to the tool-wide setting, so a source that never asked
    # for anything different moves when he changes his mind once. "obey" follows
    # this site's robots.txt. "custom" uses `robots_custom` below and refuses to
    # run without it -- see scrapex/robots.py for why falling back would be
    # worse than failing. Stored as a plain string because the manifest is a
    # hand-editable file and an enum in YAML is a trap; it is checked when the
    # manifest LOADS, by `checked_robots` -- the check his panel choices take too.
    robots: str = "default"
    #: Only read when `robots` is "custom": {enforce_disallow: bool,
    #: crawl_delay_s: float | null}. A null delay means the site's own.
    robots_custom: dict | None = None
    # THE PACE THIS SITE NEEDS, when it needs one it never asked for.
    #
    # A site that publishes a Crawl-delay is already honoured. This is for the
    # other kind: alsweed.sa publishes NO delay and then answers 429 anyway, and
    # the only lever before this was the tool-wide `crawl_min_interval_s` —
    # which would have slowed elburoj's 6,720 products to spare one site.
    #
    # Seconds between requests, for this source alone. Null means it has no
    # opinion and the tool-wide pace stands. It can only ever SLOW a crawl:
    # `resolve_fetcher` takes the slowest of every opinion, so naming 0.1 here
    # cannot make a source faster than the owner's own setting.
    # CHECKED BY `checked_seconds`, the one definition of a pace: finite, more than 0,
    # a number and not a bool or a numeric string -- the bound `source_setting`'s CHECK
    # (migration 0022) and the panel's `source_settings.save` hold. Pydantic's own
    # `gt=0` took `true` as 1.0 and "5" as 5.0, and said it in other words.
    crawl_pace_s: float | None = None
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
    def _fallbacks_exclude_self(self) -> SourceEntry:
        # A fallback chain that re-tries the family that just failed would loop
        # over the same failure instead of escalating.
        if self.family in self.fallback_families:
            raise ValueError(
                f"{self.source_key}: fallback_families must not repeat the primary "
                f"family {self.family.value!r}")
        return self

    @field_validator("robots")
    @classmethod
    def _robots_is_a_choice(cls, v: str) -> str:
        return str(checked_robots(v))

    @field_validator("robots_custom")
    @classmethod
    def _robots_custom_is_a_rule(cls, v: dict | None) -> dict | None:
        return None if v is None else checked_robots_custom(v)

    @field_validator("user_agent")
    @classmethod
    def _user_agent_can_be_sent(cls, v: str | None) -> str | None:
        return checked_user_agent(v)

    @field_validator("base_url")
    @classmethod
    def _site_host_is_not_refused(cls, v: str | None) -> str | None:
        return checked_host(v)

    @field_validator("crawl_pace_s", mode="before")
    @classmethod
    def _pace_is_a_pace(cls, v: object) -> float | None:
        return None if v is None else checked_seconds("crawl_pace_s", v, allow_zero=False)

    @model_validator(mode="after")
    def _custom_rule_exactly_under_custom(self) -> SourceEntry:
        try:
            checked_custom_pairing(self.robots, self.robots_custom is not None)
        except ValueError as exc:
            raise ValueError(f"{self.source_key}: {exc}") from None
        return self

    @model_validator(mode="after")
    def _probe_placeholder_is_inactive(self) -> SourceEntry:
        try:
            checked_activation(self.family, self.active)
        except ValueError as exc:
            raise ValueError(f"{self.source_key}: {exc}") from None
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_source_keys(self) -> Manifest:
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


def resolve_manifest_path(path: Path | str | None = None) -> Path:
    """WHICH manifest, in one place: an explicit path, then `SCRAPEX_SOURCES`,
    then the repository's own file.

    It is a function rather than a default argument because a default is bound at
    import time and cannot see an environment variable set afterwards — which is
    exactly how `create_app` came to read the owner's twelve real shops whatever
    the environment said.
    """
    if path is not None:
        return Path(path)
    return Path(os.environ.get("SCRAPEX_SOURCES") or MANIFEST_FILE)


def load_manifest(path: Path | str | None = None) -> Manifest:
    """Parse + validate sources.yaml. Raises with a precise message on any defect.

    `SCRAPEX_SOURCES` names a different manifest, and is what makes the CLI
    testable end to end: `crawl`, `ingest`, `export` and `peek` all reach for the
    repository's own `sources.yaml` with no argument, so before this there was no
    way to drive the whole chain against a source that is not one of the owner's
    twelve real shops. An explicit `path` still wins over the variable, and the
    variable over the repository's file — the same order `SCRAPEX_FUNNEL_URL`
    already follows in the CLI.
    """
    path = resolve_manifest_path(path)
    raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_ManifestLoader)
    if raw is None:
        raise ValueError(f"{path}: manifest is empty")
    return Manifest.model_validate(raw)
