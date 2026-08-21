# The platform, not a price tracker — categories, accounts, one source registry

**Opened 2026-08-21, from four things he said in one conversation.** Nothing here is
built. It exists because the corrections are architectural, and an architectural
correction that is not written down is one the next session will build against.

> «الاداة فى المقام الاول scrape او crawl · تسميتها او ادراجها تحت بند واحد الا وهو
> متابعة الاسعار دا خطا تماما · الفكرة واسعة لكن بالخطا مسجل انها نظام price ونظام عام»
>
> «ونعمل category للمصادر لدينا الان 2 منتجات ومقاولين»
>
> «اى مصدر اعطيه لك ونشتغل عليه لازم يظهر ضمن المصادر المسجلة لاى مستخدم ويستطيع عمل
> زحف عليه · اى مصدر ادتهولك ولم ناسس له زحف يحفظ فقط فى قائمة مصادر حتى ياتى دوره»
>
> «كيف تتعامل الاداة مع الحسابات المختلفة … لكل حساب قاعدة بيانات»
>
> «علشان لما اديك مصدر لمقاولين تانى فى المستقبل منخترعش الذرة نكمل على الى موجود
> بالمثل كالمنتجات اعتقد انها مستقرة الى حد ما»

Ruled as [R-32](../RULINGS.md#r-32--scrapex-is-a-collection-platform-price-is-one-category-and-filing-it-as-the-whole-thing-was-a-mistake).
Requests: `REQ-25` (one registry, with a category), `REQ-26` (a database per
account), `REQ-27` (a second source of a category reuses the first's machinery).

---

## What is already right, and must not be rebuilt

**He is correct that products are "fairly stable", and the measurement agrees.**
`sources.yaml` already says, in its own header:

> *"Sources start `active: false`. Each is activated ONLY when its connector lands
> with tests. `active` gates SCHEDULED runs only — manual runs from the panel always
> work."*

And `family: TBD-probe` already means *registered, no collector yet* — `SourceEntry`
validation **refuses** `active: true` while the family is unproven: *"A source that
has not been probed cannot be active."*

**So "a source I give you with no crawler yet waits in the list until its turn" is
built.** Measured with `scrapex sources`: **twelve** registered, seven active, five
built — and **nothing is in the `registered` state today**, so the mechanism his
request asks for exists and is currently empty. Nothing in this plan should replace
it. What follows extends it.

**The collection engine is already generic**, which is the other thing not to
rebuild. `partitioncrawl.PartitionedListing` is a `Protocol`; `pagesource.Cell`,
`sightings`, `snapshotcrawl` and `extract/service` are keyed on a dataset, not on a
site. Their references to muqawil are **docstrings citing where a number was
measured**, not code.

---

## 1 · ~~The wheel that would be reinvented is the one shipped today~~ — DONE

> **Built 2026-08-21 as `scrapex/directories.py`.** A `Directory` is four facts
> and a partition; `--source` names it and refuses a name it does not know.
> The four module constants are gone, and a test asserts they have not come
> back. What follows is the account as it was written, because the reasoning is
> the part worth keeping.

`REQ-27`. Measured on `scrapex/contractors.py`, committed this morning:

```
BASE = "https://muqawil.org"
DATASET = "contractors"
SITE_NAME = "Saudi Contractors Authority"
...
partition = MuqawilPartition()
from .extract.muqawil import bilingual_listing_candidate
```

**A second contractor directory today needs a copy of that file.** That is precisely
«منخترعش الذرة», and it is worth naming plainly: the command was built to close a
different gap — a user could not run *any* crawl — and it closed it by hardcoding the
one site we have.

**The shape to copy is the products one**, because he is right that it is settled: a
source is a **contract entry** naming a `family`, and `build_connector(entry)` returns
the collector for that family. Nothing about a second Shopify shop requires a new
module.

    products     source entry  ->  family: shopify-json      ->  build_connector
    contractors  source entry  ->  family: muqawil-listing   ->  build_partition

The engine underneath is already protocol-shaped, so what is missing is the
**registry entry and the factory**, not the crawler.

**Open, and it is a real design question rather than a detail:** `ConnectorFamily`'s
values are all shop and price shapes. Either it grows contractor families, or the
category gets its own family enum. Deciding that before writing code is the whole
point of this section.

---

## 2 · A category on the source, and ONE registry

`REQ-25`. His categories, in his words: **`products`** and **`contractors`**. Two
today, `jobs` and `tenders` named as coming.

**`products`, not `prices` — and the distinction is load-bearing.** A price is an
attribute of a product observed at a time. Calling the category "prices" would repeat
the mistake `R-32` corrects, one level down.

**The measured defect is that there are two registries, not one.**

| | holds | populated by |
|---|---|---|
| `source_site` + `sources.yaml` | `ARAMCO_FUEL_SA`, `HEIDELBERG_EG`, `MADAR`, `SIKAEGSHOP` | the price pipeline |
| `site_profile` | `muqawil_org` | the generic pipeline |

**muqawil is not in `sources.yaml` at all.** So a source lands in one registry or the
other depending on which pipeline happened to collect it, and no single place answers
*"what sources does this installation have, and what state is each in"* — which is
exactly the question he asked («اى الجديد واى الى خلص»).

**What has to be decided before building:** whether `site_profile` merges into
`source_site`, or both become views over one table. Merging is correct and is a
migration over live rows; keeping both is cheaper and keeps the split he objects to.
**Not my call.**

**What the registry must be able to say** — this part is not in question:

    category   products | contractors | (jobs) | (tenders)
    state      registered (no collector) -> collector built -> active
    site       its names in both languages, and its base URL
    evidence   what it last collected, and when

---

## 3 · A database per account

`REQ-26`. Measured: **there is no account concept anywhere.**

```python
DATABASE_ROOT = os.environ.get("SCRAPEX_DATA_ROOT", Path.home() / ".scrapex")
```

One database per **operating-system user**. `grep` for `google_account`, `user_email`,
`signed_in`, `def account` returns nothing across `scrapex/`. So today:

- two Google accounts on one Windows user share **one** database;
- two Chrome profiles with different accounts share **one** database;
- the only isolation that exists is `SCRAPEX_DATA_ROOT`, an environment variable — a
  manual workaround, not a design.

This is the item with a **question only he can answer**, recorded as `Q-14`: **what
identifies an account?** The Google address the user signed in with, the Chrome
profile, or an explicit choice in the panel? It decides where other people's data
lands, so it is not a default to be guessed.

**What is already right and helps:** `R-23` settled that a warehouse is **per
installation** and an empty one is the normal first-run state; `R-24` settled that a
database is **upgraded, never replaced**, so a user's rows survive. A per-account root
is the same rule applied one level finer — and `carry_over` already exists to move a
warehouse forward rather than starting over.

---

## 4 · The debts the price framing left behind

These are not renames. Each is a missing function, measured 2026-08-21:

| debt | measured |
|---|---|
| **retention** | `retention.py` and `compaction.py` touch **`price_observation` only**. The contractor dataset — 16,761 sighted ids — has no retention policy and no compaction, and nothing generic was ever written |
| **two registries** | §2 above |
| **`ConnectorFamily`** | every value is a shop or price shape; no contractor, tender or job shape can be named |
| ~~**the description**~~ | **DONE 2026-08-21.** All three said *"price-tracking warehouse"*; `CLAUDE.md` is read first by every session, so the framing was self-perpetuating. It now names the categories and says price was the first of them |

**Order matters here.** The description is the cheapest and has the largest effect on
what the next session builds, so it goes first. Retention is the largest and can wait,
because nothing is deleting contractor rows today.

---

## The order I recommend, and why

1. ~~**The description**~~ — **DONE.** It stops the wrong framing propagating into
   the next session's work, which is the only reason `CLAUDE.md` exists.
2. **`category` on the registry, one registry** (`REQ-25`) — because §1 and §4 both
   need somewhere to put the answer, and because it is what makes *"what is new and
   what is finished"* a query rather than a memory.
3. ~~**A contractors source as a contract entry**~~ — **DONE.** `directories.py`;
   the second directory no longer forks the file.
4. **A database per account** (`REQ-26`) — blocked on `Q-14`, and it is the one with
   real consequences for people's data, so it is not started on a guess.

**What blocks nothing and should keep running meanwhile:** the muqawil crawl (96.2% of
the listing sighted) and `R-28`'s wipe-and-re-approve once `R-31` lands.
