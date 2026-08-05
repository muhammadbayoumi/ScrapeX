> **SUPERSEDED 2026-08-05 by [`docs/PLATFORM-PLAN.md`](../PLATFORM-PLAN.md).**
>
> Archived rather than deleted, at the owner's instruction, because it is the
> document the current plan was argued against and several of its decisions
> survive unchanged. What replaced it, and why, is listed in PLATFORM-PLAN §2
> and §7 — including the measured reasons the `apps/` relocation, the four
> uncommitted backends, MSIX, and "Domain Engines: Price / Listing / Table"
> were dropped.
>
> Nothing below has been edited. Read it as history.

---

# scrapeX Ecosystem

## Architecture and Implementation Plan

**Status:** Agreed development architecture  
**Primary products:** scrapeX, MarketLens, and MBI Console  
**Repository strategy:** One GitHub monorepo during development, with independently built and versioned applications  
**Operating model:** Hybrid, local-first, multi-engine architecture with configurable storage

---

## 1. Executive Summary

scrapeX is the Chrome Extension that provides the user interface, Google sign-in, source management, and control of crawling and data-publishing workflows. Through scrapeX, the user selects the Crawler Backend, Database Profile, and Storage Profile for a workspace or job, then sends that configuration to the selected backend.

MarketLens is a standalone local Windows crawler engine for stores and products. It does not use Scrapy, Crawlee, Crawl4AI, or any other external crawler. MarketLens is the only internally defined backend in the current architecture: it has its own crawler implementation, domain engines, and connector families for e-commerce stores and product data. Its current internal domain engines include Price Engine, Listing Engine, and Table Engine; its connector families include Shopify, Magento, WooCommerce, and future store families. Any other type of website or data is handled through the available general-purpose external tools. A separate local Engine Host can launch and monitor the selected backend, but each backend remains independent.

Google Drive is one selectable user-owned backup/synchronization provider. Google Sheets is one selectable configuration and publishing provider used by the spreadsheet/Excel ecosystem. Local files, local XLSX, Drive, Sheets, and future database providers are exposed through Database Profiles and Storage Profiles selected in scrapeX rather than being hard-coded into one workflow. GitHub stores the source code, CI/CD workflows, release metadata, and distributable engine releases; it is not the user's data store.

MBI Console is an owner-only administration module integrated into the scrapeX development build. It provides a browser-based interface for managing the Google Sheets configuration that defines how datasets are represented, validated, mapped, displayed, and exported. It must be isolated as a module so it can be excluded from the future commercial build.

The initial implementation remains a monorepo for speed and coordinated development. scrapeX, the Engine Host, and MarketLens remain separate applications or components inside that repository, with separate versions, tests, build pipelines, and releases. The hybrid model does not make the browser extension a crawler engine: the extension is the control plane, the Engine Host manages independent processes, and MarketLens is a complete independently runnable crawler engine.

---

## 2. Final Architectural Decisions

| Area | Decision |
|---|---|
| Repository | Keep one monorepo during development. |
| Chrome product | `scrapeX` Chrome Extension. |
| Local product | `MarketLens` standalone Windows crawler engine. |
| Local engine host | Local scrapeX component that installs, selects, launches, and monitors independent engines. It does not become an engine itself. |
| Crawler Backends | scrapeX can select MarketLens for stores/products, or an available general-purpose backend for other website/data types. |
| MarketLens internals | MarketLens contains the Crawler Backend, Domain Engines, and Connector Families that belong to its own ecosystem. |
| Extension updates | GitHub Actions builds and submits approved packages to the Chrome Web Store; Chrome distributes updates. |
| Engine updates | GitHub Actions builds a signed MSIX and publishes an AppInstaller/release channel. |
| Database and storage selection | scrapeX owns the user-facing selection of Database Profiles and Storage Profiles and passes the selected profile to the active backend. Local SQLite is the first certified warehouse; Drive, Sheets, and XLSX are selectable providers. |
| New-device setup | Sign in with Google, restore the selected workspace profile when applicable, verify the engine/backends, then allow crawling. |
| Cloud publishing | Publish validated configuration and dataset outputs through the selected Sheets/Drive/export profile. |
| Engine communication | Chrome Native Messaging between scrapeX and the Engine Host; the host launches the selected backend. |
| Admin tooling | `MBI Console`, a separately structured owner-only module inside the development extension. |
| Commercialization | Start privately, then introduce licensing, commercial builds, privacy/legal controls, and support processes. |

---

## 3. System Overview

```text
┌─────────────────────────┐
│ scrapeX Chrome Extension│
│ - Google Login          │
│ - Sources and controls  │
│ - Status and setup UI   │
│ - MBI Console (dev only)│
└────────────┬────────────┘
             │ Chrome Native Messaging
             ▼
┌─────────────────────────────────────────┐
│ scrapeX Local Engine Host             │
│ - Engine Manager                      │
│ - Install/select/launch/monitor       │
│ - Shared process and message contract  │
└──────────┬────────────────────────────┘
           │
           ├──────────────────────┐
           ▼                      ▼
┌────────────────────────┐   ┌────────────────────────┐
│ Selected Crawler Backend │   │ Other selectable backends │
│                          │   │ Scrapy / Crawlee /         │
│ If MarketLens:           │   │ Crawl4AI / Katana / ...   │
│ - MarketLens Crawler Core│   │ General-purpose temporarily│
│ - Price Engine           │   └────────────┬───────────────┘
│ - Listing Engine         │                │
│ - Table Engine           │                │
│ - Connector Families    │                │
└───────────┬─────────────┘                │
            └──────────────┬───────────────┘
                           ▼
              Selected backend result/output
                           │
                           ▼
┌──────────────────┐   ┌──────────────────────┐
│ Selected database│   │ Selected providers   │
│ - SQLite first   │   │ - Local XLSX/CSV     │
│ - Future adapters │   │ - Google Drive       │
│ - One writer     │   │ - Google Sheets      │
└──────────────────┘   │ - Future providers  │
                       └──────────┬───────────┘
                                  ▼
                         Excel / spreadsheet tool

GitHub stores source, workflows, releases, and engine packages.
```

The extension is the control plane. The Local Engine Host manages independent engine processes but does not replace them. MarketLens is a complete standalone engine with its own internal domain engines and connector families. Other open-source tools are separate engine options and are never silently loaded as MarketLens dependencies. Database, backup, and publishing profiles are selected independently for the active engine/workspace.

---

## 4. Monorepo Structure

```text
scrapeX/
├── apps/
│   ├── extension/                 # scrapeX Chrome Extension
│   │   ├── src/
│   │   │   ├── background/
│   │   │   ├── content/
│   │   │   ├── popup/
│   │   │   ├── options/
│   │   │   ├── setup/
│   │   │   ├── mbi-console/      # Owner-only development module
│   │   │   └── integrations/
│   │   ├── manifest.json
│   │   └── package.json
│   │
│   ├── marketlens/                # Standalone local Windows crawler engine
│   │   ├── src/
│   │   │   ├── native_host/
│   │   │   ├── crawler/
│   │   │   ├── adapters/
│   │   │   ├── domain_engines/
│   │   │   │   ├── price/
│   │   │   │   ├── listing/
│   │   │   │   └── table/
│   │   │   ├── connector_families/
│   │   │   │   ├── shopify/
│   │   │   │   ├── woocommerce/
│   │   │   │   └── magento/
│   │   │   ├── database_profiles/
│   │   │   ├── storage_profiles/
│   │   │   ├── backup/
│   │   │   ├── publishing/
│   │   │   ├── runtime/
│   │   │   └── capabilities/
│   │   ├── pyproject.toml
│   │   └── packaging/
│
│   └── engine-host/               # Local lifecycle host; not a crawler engine
│       ├── src/
│       │   ├── engine_manager/
│       │   ├── process_launcher/
│       │   ├── adapter_protocol/
│       │   ├── health_checks/
│       │   └── native_messaging/
│       └── packaging/
│
├── packages/
│   ├── shared-contracts/          # Message, schema, and compatibility contracts
│   ├── config-rules/              # Validation and mapping rules
│   ├── crawler-adapter-contract/  # Versioned backend protocol
│   ├── database-contract/         # Warehouse/provider contract
│   └── google-integration/        # Drive/Sheets provider adapters
│
├── packaging/
│   ├── msix/                      # MSIX and AppInstaller configuration
│   └── native-messaging/          # Chrome host manifest and registration
│
├── docs/
├── tests/
└── .github/
    └── workflows/
        ├── extension-ci.yml
        ├── marketlens-ci.yml
        ├── publish-scrapex.yml
        └── release-marketlens.yml
```

The repository is shared, but the applications are not bundled into one runtime. Each application has its own dependency set, test suite, build artifact, version, and release process.

### Independence and Release Ownership

The components are intentionally independent products connected through stable contracts:

| Component | Owns | Update channel |
|---|---|---|
| scrapeX | Central control UI, Google authentication, backend selection, profile selection, MBI Console, and compatibility checks | Chrome Web Store through GitHub Actions |
| MarketLens | Specialized stores/products crawler, MarketLens Crawler Core, Price/Listing/Table Engines, and store Connector Families | Independent signed MSIX/AppInstaller release |
| Other Crawler Backends | Their own general-purpose runtimes and community-maintained capabilities | Their upstream/community releases, installed as versioned packs |
| Engine Host | Installation, launch, monitoring, health checks, and lifecycle management | Released with the local integration/host package |

scrapeX can be upgraded independently when its protocol and profile contracts remain compatible. MarketLens can be upgraded independently when its declared engine contract remains compatible. Other backends can evolve according to their communities and upstream release cycles; scrapeX controls only their adapter, manifest, compatibility status, and installation policy. scrapeX does not own or rewrite their internal implementations.

The only intentional coupling is contractual:

```text
scrapeX ↔ Engine Host ↔ Selected Backend
              ↕
       Versioned Contracts
              ↕
Database/Storage Profile Contract
```

Every component must publish its version, supported protocol versions, capabilities, required profiles, and compatibility status before a job can run. This preserves independent upgrades without allowing an incompatible update to corrupt a workspace or silently change its data behavior.

---

## 4.1 Crawler Backends and MarketLens Scope

scrapeX is the selection and control surface for the Crawler Backends. The current backend catalogue is:

```text
Scrapy
Crawlee
Crawl4AI
Katana
MarketLens
```

MarketLens is a complete, standalone crawler engine. It is not a wrapper around Scrapy, Crawlee, Crawl4AI, Katana, or another external product. It has its own crawler implementation and its own internal data model:

```text
MarketLens
├── MarketLens Crawler Core
│   ├── HTTP/browser transport
│   ├── discovery and extraction
│   └── crawl execution
├── Domain Engines
│   ├── Price Engine
│   ├── Listing Engine
│   └── Table Engine
├── Connector Families
│   ├── Shopify
│   ├── WooCommerce
│   ├── Magento
│   ├── Salla
│   └── Zid
├── Database/Storage adapters
│   └── Applied according to scrapeX-selected profiles
└── Backup/Publishing integration
```

### Domain Engines inside MarketLens

The Price Engine, Listing Engine, and Table Engine are modules inside MarketLens. Each module owns the meaning of its data, RowSpecs, ingest rules, read models, and schema slice. They are not separate external programs and are not dependencies that the user installs independently.

The current defined MarketLens scope includes Price Engine, Listing Engine, and Table Engine. The initial public focus may still be Price Engine, but the other modules are part of the MarketLens architecture and can be enabled as their implementation becomes ready. The architecture must not force price-specific concepts onto their schemas.

### Connector Families inside MarketLens

Connector Families are also part of MarketLens. They contain the site-shape knowledge required to work with Shopify, WooCommerce, Magento, Salla, Zid, custom JSON, static HTML, and future families. A connector family selects the appropriate MarketLens domain engine and maps the site's response into that engine's canonical records.

### Other Crawler Backends

Scrapy, Crawlee, Crawl4AI, Katana, and future backends are selectable independently through scrapeX for general-purpose website/data collection. Their exact domain responsibilities are intentionally general and not fixed. They are not loaded by MarketLens and MarketLens does not depend on them. When one is selected, the Engine Host launches it as an independent, version-pinned process or pack through the common integration contract.

This distinction is intentional:

```text
MarketLens selected
    → MarketLens Crawler Backend
    → MarketLens Connector Family
    → MarketLens Domain Engine

Any general backend selected
    → Its own runtime and configuration
    → General backend result/output contract
    → selected Database/Storage Profile
```

An external backend must never silently become part of MarketLens, use MarketLens's internal modules, or change MarketLens's normalization and history rules. The selected Database Profile and Storage Profile are passed from scrapeX as part of the job/workspace configuration.

### General Backend Result Contract

Because the non-MarketLens backends are general-purpose for now, scrapeX must not force them into the Price, Listing, or Table schemas. They return a generic result envelope that can later be mapped to a domain model when a backend's exact responsibility is defined:

```json
{
  "backendId": "scrapy",
  "jobId": "job-123",
  "status": "completed",
  "records": [],
  "artifacts": [],
  "provenance": {
    "sourceUrls": [],
    "backendVersion": "pinned-version",
    "collectedAt": "timestamp"
  },
  "warnings": []
}
```

MarketLens may return its specialized Price, Listing, or Table records in addition to the generic envelope. This keeps the external backends flexible without weakening MarketLens's domain-specific behavior.

---

## 4.2 Pluggable Crawler Backends and Engine Manager

The scrapeX Engine Host includes an Engine Manager. It discovers, installs, health-checks, updates, selects, launches, isolates, and uninstalls independent engine packs. It does not perform crawling and it does not turn MarketLens into a wrapper around another tool.

The core installation should contain the Engine Host, the standalone MarketLens engine, MarketLens's currently implemented modules and connector families, and the shared process/message contract. Other engines are installed on demand:

| Backend/pack | Natural role | Initial integration shape |
|---|---|---|
| MarketLens | Standalone local crawler engine containing its own domain engines and connector families | Independently packaged local engine |
| Scrapy | General-purpose backend; exact domain role TBD | Isolated Python worker |
| Crawlee | General-purpose backend; exact domain role TBD | Isolated worker or sidecar |
| Crawl4AI | General-purpose backend; exact domain role TBD | Isolated worker or local service |
| Katana | General-purpose backend; exact domain role TBD | Versioned binary adapter |

Firecrawl and Heritrix remain future candidates from the wider architecture study, not committed current backends. Their inclusion requires a separate need, integration spike, packaging decision, and license review.

These are candidates, not a promise to bundle every open-source project. Every backend must pass a ScrapeX conformance suite, declare its exact upstream version, expose capabilities and health, and carry its license/notice information.

The adapter protocol should support:

```text
health
plan
run
cancel
resume
diagnostics
```

During a run, adapters emit structured events such as `discovered`, `fetched`, `artifact`, `candidate_record`, `checkpoint`, `warning`, `blocked`, `failed`, and `completed`. Final artifacts include provenance, canonical URLs, timestamps, content hashes, and references to raw evidence.

The planner may operate in three modes:

```text
Auto      → recommend a certified backend and explain why
Recipe    → compose discovery, fetch, render, extract, validate, and archive steps
Expert    → expose backend-specific settings from its machine-readable schema
Compare   → run a bounded sample through multiple backends and compare results
```

Fallbacks must be bounded by request, time, cost, resource, retry, and backend-switch limits. Every backend switch and its reason belongs in the run audit trail.

### Backend and profile selection contract

Every scrapeX workspace/job configuration must carry the selections made in the scrapeX UI:

```json
{
  "crawlerBackendId": "marketlens",
  "databaseProfileId": "local-sqlite",
  "storageProfileId": "local-drive-backup-sheets",
  "domainEngineId": "price",
  "connectorFamilyId": "shopify"
}
```

`domainEngineId` and `connectorFamilyId` are required when `crawlerBackendId` is `marketlens`, because those modules belong to MarketLens. For the currently general-purpose backends, those fields remain unset or backend-defined until their responsibilities are decided.

### Backend capability matrix

Before scrapeX activates a combination, it must check the selected backend's declared support for:

```text
Backend
Domain mode
Database Profile
Storage Profile
Operating system
Required runtime/pack
Authentication/session support
Resource limits
```

The UI should disable unsupported combinations and explain why. A backend is not required to support every Database Profile or Storage Profile.

---

## 4.3 Database and Storage Profiles

The application must not hard-code one permanent storage path or one publishing destination. A workspace has a selectable profile composed of a database provider and zero or more backup/publish providers. The user makes this selection in scrapeX; the selected backend receives and applies the profile through the job/workspace contract.

### Database providers

The initial certified provider is local SQLite using the existing append-only warehouse schema. The provider interface must leave room for future certified implementations such as DuckDB or PostgreSQL when a real requirement exists.

```text
Database Profile
├── provider: sqlite | future provider
├── location or connection reference
├── schema version
├── migration policy
├── single-writer/concurrency policy
└── backup/export policy
```

The user may select the database profile and local location from scrapeX where supported. A provider is not considered supported merely because it can open a file; it must preserve migrations, append-only history, fingerprints, transactions, locking, and compatibility with the selected backend's data model.

### Storage and publishing profiles

The user can choose or switch among profiles such as:

```text
Local Only
    Local database; no cloud egress

Local + XLSX
    Local database plus explicit workbook export

Local + Google Drive Backup
    Local database plus versioned Drive backups and restore

Local + Google Sheets Publish
    Local database plus validated Sheets publishing

Local + Drive Backup + Sheets Publish
    Combined backup and publishing workflow

Custom Provider Profile
    Future certified provider selected by the user
```

For the first certified workflows, local SQLite remains the active writer even when Drive or Sheets is selected. Drive is a backup/restore and synchronization provider, not a directly shared SQLite file. Direct multi-device writes to a remote file would risk corruption and are not part of the initial contract. Additional database providers can become selectable after they pass the same conformance and migration checks.

### Safe switching

Changing a profile is an explicit migration operation:

```text
Validate the target provider
        ↓
Create a verified snapshot of the current workspace
        ↓
Export/migrate compatible data and configuration
        ↓
Write the new profile manifest
        ↓
Verify the target and run a read-back check
        ↓
Activate the new profile
```

The system must never silently switch providers, delete the previous data, or claim that a provider is active before verification succeeds. MBI Console and the main settings UI should show the active profile, available profiles, migration status, and rollback option.

Example independent versions:

```text
scrapeX:     0.6.0
MarketLens:  0.9.2
Protocol:    2
```

Use independent tags such as:

```text
scrapex-v0.6.0
marketlens-v0.9.2
```

---

## 5. scrapeX Chrome Extension

### Responsibilities

- Authenticate the user with Google OAuth.
- Identify the signed-in account and load its configuration.
- Show sources, crawl status, row counts, errors, and engine status.
- Present the Crawler Backend catalogue and let the user select any installed/certified backend.
- Let the user select the Database Profile and Storage Profile for each workspace or job.
- Start, pause, and monitor jobs for the selected backend.
- Guide the user through first-time installation and updates for the selected backend.
- Read and write authorized Google Drive and Google Sheets resources.
- Trigger validation, backup, and publishing workflows.
- Expose MBI Console only in the development build and only to the owner account.

### Store distribution

The extension may begin as a private or unlisted Chrome Web Store item. The user installs it on any supported device and signs in with Google. A GitHub Actions workflow builds the extension and submits a release to the Chrome Web Store. Chrome then handles distribution and update delivery.

The extension must not download executable JavaScript from GitHub or use GitHub as a remote code source. New extension logic must be included in the reviewed extension package. GitHub may provide release metadata, configuration, or documentation, but not runtime extension code.

### Engine setup experience

If the selected backend is not detected, scrapeX should show a setup wizard. For MarketLens, the flow is:

```text
Sign in with Google
        ↓
Check for MarketLens
        ↓
Engine missing? → Download/open installer
        ↓
User approves Windows installation
        ↓
Register Native Messaging host
        ↓
Re-check connection
        ↓
Engine Ready
```

The extension can guide or initiate the download, but Windows installation and update approval remain explicit user actions. Silent installation of a local engine is not part of the design.

---

## 6. MarketLens Standalone Engine

### Responsibilities

- Run as an independent local crawler engine, comparable in role to Scrapy.
- Accept a job through the versioned crawler adapter protocol.
- Perform its own supported discovery, fetching, rendering, extraction, and crawl execution.
- Return canonical crawl artifacts, candidate records, structured events, and backend provenance.
- Report its own engine version, capabilities, health, progress, warnings, failures, and cancellation state.
- Keep its runtime and dependencies isolated from other crawler engines.

MarketLens owns its own canonical warehouse, normalization, fingerprinting, deduplication, and domain-engine ingest. It provides database/storage adapters and applies the Database Profile and Storage Profile selected in scrapeX. It does not own MBI Console or the Engine Manager, and it does not use external crawler engines. The Engine Host only launches, monitors, and communicates with MarketLens; it does not replace MarketLens's internal data pipeline.

### Packaging

MarketLens is distributed as an independently versioned Windows MSIX package with an AppInstaller update channel. Its package should include:

- The MarketLens executable and embedded runtime.
- MarketLens crawler capabilities and configuration support.
- Its own runtime and dependencies.
- Adapter-protocol support.
- Database and storage profile support.
- Backup and publishing support selected by the user.
- Native Messaging or local-process registration required by the Engine Host.
- Installer registration and update metadata.

Other crawler engines such as Scrapy, Crawlee, Crawl4AI, Katana, Firecrawl, or Heritrix are separate packs and releases. The Engine Manager installs them as signed, version-pinned, isolated packages when selected. They remain independent from MarketLens, and the MarketLens installer must not force their runtimes onto every user.

Every distributable package must be digitally signed. Build secrets and signing certificates remain in GitHub Actions secrets or a dedicated secure release system, never in the repository.

### Capability handshake

When scrapeX connects, MarketLens should return a machine-readable status such as:

```json
{
  "status": "ready",
  "engineId": "marketlens",
  "engineVersion": "0.9.2",
  "protocolVersion": 2,
  "domainEngines": ["price", "listing", "table"],
  "connectorFamilies": ["shopify", "woocommerce", "magento"],
  "selectedDomainEngine": "price",
  "selectedConnectorFamily": "shopify",
  "databaseProfile": "local-sqlite",
  "storageProfile": "local-drive-backup-sheets",
  "capabilities": [
    "marketlens-crawler",
    "domain-engines",
    "connector-families",
    "database-profiles",
    "storage-profiles",
    "http-extractor",
    "tsv-export",
    "google-drive-backup",
    "google-sheets-publish"
  ]
}
```

The extension must check minimum engine and protocol versions before starting a job and provide a clear update action when compatibility is insufficient.

---

## 7. Google Login, Drive Backup, and Sheets Publishing

### Google authentication

Use Google OAuth through the extension's identity flow. Store tokens using the platform's secure extension storage mechanisms, never in GitHub, the local database, logs, or exported files.

Use the narrowest practical Google scopes. The preferred Drive model is to operate on files created or explicitly selected by the user rather than requesting unrestricted access to the entire Drive.

### Drive layout

MarketLens should create or use a clear application-owned folder structure:

```text
MarketLens/
├── databases/
├── backups/
├── exports/
├── manifests/
└── locks/
```

The exact folder IDs should be stored in the user's configuration and re-discovered safely when necessary. The system must never assume that a Drive path is globally unique.

### Backup after changes

After a successful crawl or material database/configuration change, MarketLens follows the active storage profile:

```text
Update local database
        ↓
Run integrity and consistency checks
        ↓
Create a compressed, versioned backup
        ↓
If Drive is selected → upload backup and update latest manifest
        ↓
If Sheets is selected → publish configured Sheets/TSV outputs
        ↓
Report completion to scrapeX
```

For a Local Only profile, the workflow stops after local validation. For a Local + XLSX profile, it creates the configured workbook without requiring Google OAuth. The user can switch profiles later through an explicit, verified migration operation.

Use immutable versioned files instead of overwriting one backup:

```text
marketlens-db-v105.zip
marketlens-db-v106.zip
marketlens-db-v107.zip
latest.json
```

`latest.json` should point only to a backup that passed validation. Retain a configurable number of previous versions so a failed or corrupted update can be rolled back.

### Sheets publishing

Google Sheets acts as a structured configuration and publishing layer. MBI Console manages the metadata; MarketLens and scrapeX apply it. Publishing should be transactional at the workflow level: validate first, write the intended ranges, verify the result, then mark the configuration/output as successful.

---

## 8. Multi-Device Restore, Locking, and Versioning

### New device flow

```text
Install scrapeX
        ↓
Sign in with Google
        ↓
Install/verify MarketLens
        ↓
Read the active database/storage profile
        ↓
If Drive backup is selected → discover the user's MarketLens folder
        ↓
If a backup exists → download and validate it
        ↓
Restore or initialize the selected database profile
        ↓
Check backend, database, storage, and protocol compatibility
        ↓
Allow a new crawl
```

The system should not begin a new crawl on a new device until restoration has either completed successfully or the user has explicitly chosen to start a new empty workspace.

### Concurrent-device protection

Before any operation that may change shared state:

1. Read the latest manifest from Drive.
2. Pull a newer backup if the local copy is behind.
3. Acquire a user/workspace lock with an owner ID, device ID, version, timestamp, and expiry.
4. Run the operation locally.
5. Create and validate a new version.
6. Upload the new backup and manifest.
7. Release the lock.

Locks must expire safely, and the UI must provide a recovery path for a stale lock. The system must never silently overwrite a newer backup created by another device.

### Compatibility rules

Maintain separate values for:

```text
Extension version
Engine version
Protocol version
Database schema version
Backup format version
```

Database migrations and backup-format compatibility must be explicit. A newer engine may read older backups when supported, but it must not claim success without completing validation.

---

## 9. MBI Console

### Purpose

MBI Console is an owner-only administration interface for configuring the spreadsheet/Excel data model. It is part of the scrapeX development build initially, but it is an isolated module that can be removed from the commercial build without rewriting the extension.

### Core functions

- Discover datasets and tabs from Google Sheets.
- Select the standalone engine for a workspace or job; when MarketLens is selected, choose its domain engine and connector family.
- View installed independent engines, health, provenance, license notices, and update channels.
- Select the database profile and local storage location where supported.
- Select a backup/publishing profile such as Local Only, Local + XLSX, Drive Backup, or Sheets Publish.
- Start a verified profile migration or rollback.
- Create and edit dataset definitions.
- Apply data validation and schema rules.
- Define source-to-dataset mappings.
- Configure ribbon groups and display order.
- Define export views and visible columns.
- Inspect scrapeX and MarketLens integration status.
- Publish validated changes back to the configured Sheets.

### Managed configuration tables

MBI Console manages these six logical tables:

```text
DATASOURCE
TABLE DEFINITION
SCHEMA RULE
DATA MAP
RIBBON CONFIG
EXPORT VIEW
```

### Dataset builder

A dataset-creation workflow should collect or infer:

```text
Dataset name
Source/TSV URL
Google Sheets tab
SQL/local table name
Primary key
Domain engine
Connector family
Database profile
Storage/backup profile
Columns and order
Data types
Validation rules
Mapping rules
Ribbon group
Export view
```

When a new scraped tab is detected, MBI Console should prefill technical information such as tab name, column names, order, row count, and suggested data types. The owner then completes business-facing metadata such as display name, SQL name, visible fields, ribbon placement, and export rules.

### Access control

The interface must not be protected by visual hiding alone. Enforce authorization at the authentication and write-operation layers:

```text
Google sign-in
        ↓
Verify owner/admin identity
        ↓
Load MBI Console module
        ↓
Authorize every privileged read/write operation
```

The owner allowlist must be environment-specific and must not be hard-coded into a public commercial build. The commercial build should omit the module and its privileged routes entirely unless a future business requirement explicitly adds an administrative product.

### Suggested module layout

```text
apps/extension/src/mbi-console/
├── pages/
│   ├── Dashboard
│   ├── Sources
│   ├── DatasetBuilder
│   ├── SchemaRules
│   ├── DataMapping
│   ├── RibbonConfig
│   └── ExportViews
├── google/
│   ├── driveClient
│   └── sheetsClient
└── integrations/
    ├── scrapeX
    └── marketlens
```

---

## 10. GitHub and Update Workflows

### What GitHub stores

- Extension source code.
- MarketLens source code.
- Shared contracts and migrations.
- Dependency manifests and lockfiles.
- MSIX/AppInstaller packaging configuration.
- Tests and documentation.
- Open-source license notices.
- Release notes and version metadata.

Do not store user databases, Google OAuth tokens, cookies, passwords, backup files, signing certificates, or generated build artifacts in the normal source tree.

### Branching and local development

```text
main        → stable, releasable code
develop     → active integration branch
feature/*   → individual changes
```

During development, load scrapeX as an unpacked extension locally. Publish to the Chrome Web Store only from a deliberate release process.

### CI/CD behavior

Use path-filtered workflows so an extension change does not unnecessarily rebuild the engine, and vice versa.

```text
Extension change
    ↓
Extension tests and package build
    ↓
Chrome Web Store submission on release
    ↓
Chrome update delivery

MarketLens change
    ↓
Engine tests and Windows package build
    ↓
Signed MSIX/AppInstaller release
    ↓
User-approved engine update
```

GitHub Releases are the distribution record for MarketLens binaries. They are not the system of record for user data.

---

## 11. Security and Reliability Requirements

- Use OAuth and least-privilege scopes.
- Keep access tokens in secure local storage.
- Never commit secrets or signing keys.
- Validate every backup before advertising it as latest.
- Use immutable backup versions and rollback support.
- Prevent concurrent-device overwrites with leases/locks.
- Authenticate and authorize MBI Console operations server-side or at the privileged integration boundary.
- Verify engine identity, version, and protocol before accepting commands.
- Validate all crawler output before publishing to Sheets.
- Keep user data out of logs unless explicitly redacted and needed for diagnosis.
- Track open-source dependencies and comply with their licenses.
- Add privacy, deletion, and consent documentation before any public commercial release.

---

## 12. Implementation Roadmap

### Phase 1 — Monorepo foundation

- Establish the directory structure and independent package manifests.
- Define shared message, schema, version, and error contracts.
- Add basic CI for scrapeX and MarketLens.
- Add branch, tag, and release conventions.

**Acceptance criteria:** both applications build and test independently from the same repository.

### Phase 2 — Local engine integration

- Implement the Native Messaging host.
- Add `PING`, capability, version, selected-backend, selected-profile, job-start, progress, cancel, and error messages.
- Define the versioned engine communication contract and make MarketLens the first complete standalone engine.
- Define the database and storage provider contracts.
- Run a first local crawl through the extension using MarketLens's Price Engine and a Shopify connector family.
- Add local database initialization and migrations.

**Acceptance criteria:** scrapeX can detect MarketLens, start a job, display progress, and receive a verified result.

### Phase 3 — Google identity and persistence

- Implement Google sign-in.
- Implement the initial database profiles and storage profiles.
- Create/discover the MarketLens Drive folder only when a Drive profile is selected.
- Add profile-aware backup creation, validation, upload, manifests, and restore.
- Add Google Sheets read/write integration as a selectable provider.
- Add explicit profile switching with snapshot, migration, read-back verification, and rollback.

**Acceptance criteria:** a user can select Local Only, Local + XLSX, or a Google-backed profile; run a crawl; switch profiles safely; and restore the data on another device without losing the last valid state.

### Phase 4 — MBI Console

- Implement the owner-only module within the development extension.
- Add the six configuration tables and validation rules.
- Add dataset discovery and the dataset builder.
- Connect configuration changes to scrapeX, MarketLens, and Sheets publishing.

**Acceptance criteria:** the owner can discover a new dataset, complete its metadata, validate it, and publish the resulting configuration without manually editing the six tables.

### Phase 5 — Packaging and release automation

- Build the signed MarketLens MSIX.
- Add AppInstaller metadata and update checks.
- Add Engine Manager pack manifests, health checks, checksums, license notices, and explicit uninstall paths.
- Package the core Native backend separately from optional certified backend packs.
- Add extension release submission workflow.
- Add version/protocol compatibility checks and release notes.

**Acceptance criteria:** a tagged release produces the correct extension package or signed engine installer through the intended release path.

### Phase 6 — Private pilot

- Use a private/unlisted extension distribution model.
- Test multiple devices and interrupted uploads.
- Test stale locks, rollback, corrupted backups, and engine mismatch.
- Test profile switching and at least one optional backend in an isolated worker.
- Test backend provenance, resource limits, cancellation, and bounded fallback.
- Confirm that the MBI Console is unavailable to non-owner accounts.

**Acceptance criteria:** the complete workflow is reliable for the owner's real datasets and can recover from expected failures.

### Phase 7 — Commercial preparation

- Create a commercial build configuration that excludes MBI Console.
- Define which backend packs are included in the core product and which are opt-in downloads.
- Complete license, attribution, SBOM, compatibility, and security review for every distributable backend.
- Add licensing and subscription verification through a future dedicated service.
- Finalize privacy policy, data handling, deletion, support, and open-source notices.
- Define paid/free/trial entitlements and release channels.

Google Drive remains the user's data-storage location, while licensing must not rely solely on a user-editable Drive file.

---

## 13. Commercial Roadmap

```text
Development build
scrapeX + MarketLens + MBI Console + experimental backend/profile options

Private pilot
Private/unlisted distribution + owner/admin controls + certified backend packs

Commercial build
scrapeX + MarketLens + selected certified packs, with MBI Console excluded

Future service layer
License/entitlement API, billing, telemetry only with consent, and support tooling
```

The local-first design keeps crawling fast and reduces infrastructure cost. The pluggable design lets the product use the best certified backend for a job without allowing external tools to bypass ScrapeX validation and history rules. User-owned Google Drive remains an optional selectable backup provider. A future licensing service can manage free, trial, paid, and expired states without becoming the user's primary data store.

---

## 14. Definition of Done for the Initial Release

The initial release is ready when:

- scrapeX authenticates with Google and can be installed from its intended Store channel.
- MarketLens installs as a signed Windows package and communicates through Native Messaging.
- A crawl runs locally through MarketLens and updates its selected database profile.
- At least one optional backend pack can be installed, health-checked, selected, run, cancelled, and removed safely.
- At least one validated storage profile works without Google, and a Google-backed profile can create a versioned backup when selected.
- A new device can restore the selected profile's latest valid backup before crawling when backup/restore is enabled.
- Concurrent devices cannot silently overwrite one another.
- Google Sheets configuration and publishing work end to end.
- Profile switching performs a verified migration and preserves rollback data.
- MBI Console is available only in the development build and only to the owner.
- Extension and engine versions/protocols are independently tracked.
- GitHub workflows build and release the correct artifacts.
- Secrets, user data, and signing material are excluded from the repository.

This architecture preserves development speed now while keeping a clean path to a private pilot and a future commercial product.
