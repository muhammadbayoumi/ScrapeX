You are a senior product designer, UX architect, browser-extension engineer, local-runtime engineer, and data-platform architect.

Your mission is to design and implement a production-quality browser Side Panel Extension for resilient website crawling, scraping, structured local storage, dataset management, historical change tracking, price monitoring, Excel export, Google Sheets synchronization, and background job scheduling.

This is not a generic scraper dashboard. It is a local-first, multi-engine data collection and synchronization product.

# 1. Mandatory communication and language rules

These rules are non-negotiable:

1. Always communicate with me, explain your decisions, report progress, and provide final summaries in Arabic.
2. The entire product interface must be written in English only.
3. English-only interface content includes:
   - Navigation
   - Buttons
   - Labels
   - Forms
   - Status messages
   - Errors
   - Warnings
   - Empty states
   - Tooltips
   - Dialogs
   - Setup instructions
   - Logs
   - Notifications
   - Generated integration instructions
4. Arabic is supported only as user-entered data, site names, or scraped content.
5. Do not place Arabic text inside the product interface itself.
6. Scraped Arabic data must render correctly with RTL support.
7. Use automatic text-direction detection for user-entered and scraped values.
8. URLs, file paths, IDs, versions, source keys, code, and technical logs must always remain LTR.
9. All source-code comments, docstrings, variable names, function names, test descriptions, commit messages, and technical documentation must be written in English.
10. Do not propose or create a color palette.
11. Focus on:
    - Layout
    - Spacing
    - Typography
    - Hierarchy
    - Responsive behavior
    - Component structure
    - Interaction design
    - Loading, empty, success, warning, and failure states
12. Reuse the existing project theme and design tokens when available.
13. Never rely only on color to communicate status.

# 2. Working approach

Before making changes:

1. Inspect the existing project.
2. Understand its architecture, framework, components, conventions, and design system.
3. Reuse the current stack where practical.
4. Do not replace the existing architecture without a clear technical reason.
5. Preserve existing user work.
6. Explain important assumptions to me in Arabic.
7. Make sensible decisions without asking unnecessary questions.

Do not stop at a conceptual description.

If a repository is available, implement a polished and functional solution.

If some backend capability is unavailable, create a well-structured adapter or realistic mock implementation and clearly distinguish mock behavior from production behavior.

If no implementation environment is available, produce:

- High-fidelity interface specifications.
- Component specifications.
- State models.
- Data models.
- User flows.
- Technical architecture.
- Implementation-ready acceptance criteria.

# 3. Product vision

The product must:

- Run as a browser Side Panel Extension.
- Support multiple crawling and scraping engines.
- Support multiple programming runtimes and strategies.
- Support local Python.
- Support JavaScript-based processing.
- Support browser automation.
- Support static HTTP extraction.
- Support structured API extraction when legitimately available.
- Support site-specific adapters.
- Support automatic engine selection.
- Support ordered fallback engines.
- Use a locally installed runtime/helper on the user’s device.
- Detect whether local components are installed, running, compatible, and ready.
- Crawl a site for the first time.
- Update previously collected datasets.
- Detect field-level changes.
- Track product prices over time.
- Identify new, changed, unavailable, returned, and removed records.
- Rebuild datasets when explicitly requested.
- Store data locally by default.
- Export data to Excel.
- Synchronize data through Apps Script.
- Connect directly to Google Drive and Google Sheets.
- Schedule automatic runs.
- Continue background jobs when the Side Panel is closed.
- Restore the current job state when the Side Panel is opened again.
- Handle different schemas for different websites.
- Allow users to customize data presentation without altering original collected fields.

Handle legitimate crawling challenges through:

- Retry policies.
- Pagination detection.
- Browser rendering.
- Session management.
- Rate limiting.
- Throttling.
- Timeouts.
- Engine fallback.
- Checkpoints.
- Structured error recovery.
- Network interruption recovery.

Never silently bypass access controls.

Detect and report:

- Authentication requirements.
- Blocked access.
- CAPTCHA challenges.
- Permission problems.
- Rate limits.
- Robots or policy restrictions.
- Unsupported website behavior.

# 4. Required system architecture

The Side Panel must never own or directly execute a long-running crawl.

Use this responsibility model:

```text
SIDE PANEL
- Remote control
- Site selection
- Run configuration
- Progress summary
- Job controls
- Runtime status
- Quick data preview

FULL WORKSPACE TAB
- Dynamic datasets
- Full tables
- Column management
- Comparisons
- Change history
- Review queue
- Jobs and schedules
- Detailed logs
- Advanced settings

EXTENSION SERVICE WORKER
- Extension event handling
- Native Messaging bridge
- Browser permissions
- Authentication coordination
- Alarm coordination
- UI notifications

LOCAL RUNTIME
- Crawling engines
- Job execution
- Job queue
- Persistent checkpoints
- SQLite database
- Full technical logs
- Scheduling
- Excel generation
- Synchronization workers
- Backups and recovery
```

The Local Runtime must continue jobs independently from the Side Panel.

If the Side Panel closes and reopens, it must request the current job state and reconnect to live updates.

Use persistent Job IDs and database-backed job state.

Do not depend on a Manifest V3 Service Worker remaining alive for a long-running crawl.


# Service Worker Lifecycle and MV3 Constraints

The architecture must explicitly handle Chrome Manifest V3 (MV3) Service Worker hibernation. 
Do not assume the Service Worker will remain active for longer than 30 seconds.

Ensure:
- The Local Runtime functions independently regardless of the Service Worker's state.
- The Side Panel communicates directly with the Local Runtime when open, using the Service Worker only as a coordination bridge when necessary.
- Use Chrome Offscreen Documents or explicit heartbeat pings to maintain the Native Messaging host connection only during critical background UI notifications.
- Re-establish lost Native Messaging connections automatically and request the latest missed job events upon waking.

# Local Runtime Distribution and Updates

The Local Runtime must be frictionless for non-technical users. 
Do not require end-users to use the command line, install Python manually, or manage dependencies via `pip`.

Require:
- A bundled, standalone executable installer (e.g., a single `.exe` or `.dmg`).
- Over-The-Air (OTA) silent background updates for the runtime and its dependencies.
- Version parity checks between the browser extension and the Local Runtime.

The extension must prompt users gracefully when an OTA update requires a runtime restart.


# 5. Local database as the source of truth

Use the local SQL database as the canonical source of truth.

Prefer SQLite unless the existing architecture already uses another appropriate local SQL database.

```text
Website
   ↓
Crawling and Extraction Engines
   ↓
Local SQLite Database — Source of Truth
   ├── Excel Output
   ├── Google Sheets via Apps Script
   └── Google Drive and Sheets APIs
```

OPFS or browser storage may be used for temporary UI state or cache, but not as the only canonical database.

The Local Runtime must own and manage the database file.

Use:

- Transactions.
- WAL mode when appropriate.
- Safe schema migrations.
- Integrity checks.
- Recoverable backups.
- Job checkpoints.
- Database versioning.
- Compaction and maintenance.
- Storage-health monitoring.

# 6. Native Messaging constraints

Use Native Messaging as a command and status bridge between the extension and Local Runtime.

Do not send entire datasets or full logs through one message.

Native Messaging responses from the Local Runtime must remain small and paginated.

Use:

- Cursor-based pagination.
- Small command responses.
- Structured job events.
- Aggregated progress.
- Log tails.
- Explicit acknowledgements.
- Reconnection support.

Example:

```text
GET_RECORDS

datasetId
cursor
limit
visibleFields
filters
sort
```

The Local Runtime must return a limited page and a new cursor.

# 7. Core domain model

Adapt the exact implementation to the project, but support concepts equivalent to:

- Site
- Site Profile
- Site Adapter
- Runtime Component
- Crawling Engine
- Engine Capability
- Dataset
- Dataset Field
- Record Entity
- Source Identity
- Identity Alias
- Crawl Job
- Crawl Snapshot
- Change Event
- Identity Conflict
- Review Decision
- Output Destination
- Sync Session
- Sync Batch
- Schedule
- Saved View
- Export Job
- Backup
- Runtime Log

# 8. Side Panel information architecture

The primary Side Panel must contain:

1. Product header.
2. Local Runtime status.
3. Sites section.
4. Add Site action.
5. Site search and checklist.
6. Selected site cards.
7. Run mode.
8. Output summary.
9. Main run action.
10. Activity summary.
11. Persistent active-job mini-player.
12. Bottom navigation.

Bottom navigation:

```text
Run
Browse Data
Settings
```

Do not add a complex full-width data table to the Side Panel.

# 9. Header and Local Runtime status

Place the product logo and extension name at the top.

Directly below the product name, add a thin interactive status row.

Possible states:

```text
Local Runtime Ready                         ›
Setup Required                              ›
Connection Failed                           ›
Checking Components...
Update Required                             ›
Runtime Stopped                             ›
```

The status represents the complete runtime, not Python alone.

When selected, expand:

```text
LOCAL RUNTIME

Core Service                         Running
Python Runtime                       Ready
JavaScript Runtime                   Ready
Browser Automation                  Ready
Network Tools                        Ready
Site Adapters                  24 installed

Run Diagnostics
Manage Components                            ›
```

Support:

- Installed.
- Not Installed.
- Running.
- Stopped.
- Ready.
- Update Required.
- Incompatible.
- Connection Failed.
- Checking.

If components are missing, provide:

```text
SET UP LOCAL RUNTIME

1. Download the local helper
2. Run the installer
3. Install required runtimes
4. Verify the connection
```

Actions:

- Download.
- Continue Setup.
- Recheck Status.
- Run Diagnostics.
- Manage Components.
- Open Runtime Logs.
- Check for Updates.

# 10. Sites section

Use:

```text
SITES                               + Add Site
```

Provide:

- Search by site name or URL.
- Select All.
- Clear.
- Selected count.
- Scrollable checklist.
- Empty state.
- Loading state.
- Error state.

Site format:

```text
example.com (Example Website)
news-site.com (موقع الأخبار)
```

The interface remains English and LTR, while Arabic names are treated as data and render correctly.

Allow one or multiple sites to be selected.

Unavailable sites remain visible but disabled with an English explanation.

# 11. Add Site flow

Selecting Add Site must open an internal Side Panel screen or drawer.

Include:

```text
ADD SITE

Site URL
Display Name
Scraping Profile
Extraction Type
Preferred Engine
Fallback Engines
Authentication Requirements
Output Defaults
Schedule
Advanced Settings

Test Site
Add Site
```

The flow must:

- Validate the URL.
- Test connectivity.
- Inspect basic capabilities.
- Detect likely browser-rendering requirements.
- Recommend an engine.
- Allow advanced engine override.
- Display a small discovered-data sample.
- Save a reusable Site Profile.

Under Advanced Settings, add:

```text
IDENTITY RULES

Primary Match
Fallback Match
Composite Fields
Canonical URL Rules
Ambiguous Match Behavior
```

Default behavior should be automatic and simple. Advanced identity controls must not overwhelm a new user.

# 12. Selected site cards

Every selected site appears below the checklist as a compact card.

Show:

- Display name.
- URL.
- Engine.
- Fallback availability.
- Extraction profile.
- Dataset state.
- Readiness status.
- Site Settings.
- Remove-from-current-selection action.

Example:

```text
Example Website                              ×
example.com

Engine              Playwright
Extraction          Products
Dataset             1,842 records
Status              Ready

Site Settings                                ›
```

Removing a selected card must not delete the saved site.

# 13. Run modes

Support three explicit modes:

```text
INITIAL CRAWL
Collect and save this site for the first time.

UPDATE EXISTING DATA
Collect current data and detect differences.

FULL REBUILD
Archive the current dataset and crawl the site again.
```

## Initial Crawl

- Create the first dataset.
- Discover the initial schema.
- Create stable Record Entity IDs.
- Save the initial snapshot.
- Record the source identity strategy.

## Update Existing Data

- Match incoming records against stable entities.
- Detect new records.
- Detect changed records.
- Detect unavailable records.
- Detect returned records.
- Preserve previous values.
- Create field-level Change Events.
- Update current state.
- Save a Crawl Snapshot.
- Preserve full history.

## Full Rebuild

- Show a clear warning.
- Create a backup or archive.
- Let the user choose Archive or Replace.
- Never destroy old data silently.
- Provide a rollback path.

# 14. Record identity and conflict resolution

Separate the internal entity from its current source identity.

```text
Record Entity ID
A permanent internal identity.

Source Identity
URL, SKU, source ID, canonical URL, or composite key.

Identity Aliases
Previous URLs, SKUs, IDs, and known identities.
```

Matching priority may include:

1. Stable source ID.
2. SKU.
3. Canonical URL.
4. Composite key.
5. Known identity aliases.
6. Similarity matching.
7. Requires Review.

Composite keys must be configurable.

If the system suspects that an incoming record matches an existing entity but cannot safely confirm it, create a `Requires Review` item.

Provide a Review Queue:

```text
POSSIBLE MATCH

Existing Record
Incoming Record
Match Confidence
Matched Fields
Conflicting Fields

Keep Separate
Merge Records
Review Later
```

Manual merges must:

- Preserve price history.
- Preserve previous identities.
- Create aliases.
- Create an audit record.
- Support Undo Merge.
- Prevent the same conflict from repeatedly returning.

# 15. Historical changes and price monitoring

Maintain separate current-state and historical-change layers.

```text
CURRENT RECORD

Record Entity ID
Current Values
Current Availability
First Seen
Last Seen
Last Updated
```

```text
CHANGE EVENT

Record Entity ID
Field Key
Previous Value
New Value
Detected At
Crawl Job ID
Change Type
```

## Price-history storage semantics

The owner-facing price history is a timeline of real price changes, not a daily
copy of an unchanged price row.

For each source-scoped offer identity, including its product, variant, region,
branch, customer segment, selling unit, currency, and VAT basis:

- Store the first detected price.
- Compute a normalized `price_hash` from the comparable price, currency, and VAT
  basis.
- When a successful refresh sees the same `price_hash`, do not append a price
  observation, price-history row, or price change event. Update only the current
  state's `last_seen_at` and the active price period's `last_confirmed_at`.
- When the `price_hash` changes, append exactly one immutable price observation
  and change event, close the previous price period, and open a new price period.
- Track availability and stock with a separate state hash so that a stock change
  does not create a false price change.
- Failed, partial, cancelled, or out-of-scope runs must not advance
  `last_confirmed_at` and must not mark products unavailable.
- If an offer disappears and later returns, open a new price period even when the
  returned price equals the old price; continuity during the absence is unknown.

The permanent price model must distinguish:

```text
CURRENT OFFER STATE
Latest price and availability for fast reads.
Updated in place after a successful refresh.

PRICE PERIOD
One row per continuous confirmed price period.
Contains first_detected_at and last_confirmed_at.

PRICE OBSERVATION / CHANGE EVENT
Append-only evidence for the first price and each real change.
Existing rows are never updated or deleted.

SCRAPE RUN
One audit row per refresh, including scope, completion status, row counts, and
errors.

ABSENCE PERIOD
Created only when a successfully completed full-scope run does not see an
expected offer. It records disappearance and return transitions, not unchanged
daily confirmations.
```

Do not persist a full per-offer seen row for every successful daily refresh.
The run may use a staging table or an in-memory seen set while finalizing. After
the run has updated current state, price periods, and absence transitions, the
staging seen set may be discarded. Raw snapshots remain the recoverable source
evidence under their configured retention policy.

Exact-date price lookup must behave as follows:

- If a successful in-scope run confirms the offer on the requested date, return
  the price period that covered that confirmation.
- If no reliable observation exists on that date, say so explicitly and return
  the last known price before that date together with its observation date.
- If the requested date is before tracking began, report the first tracking date.
- If the relevant run failed or was partial, report that the date has no reliable
  observation rather than assuming the previous price remained valid.

The product price-history view must list only the first detected price and each
subsequent real price change, ordered from the beginning of tracking through the
last confirmed price. Daily unchanged confirmations must not appear as duplicate
history rows.

Support:

- New records.
- Updated records.
- Price increases.
- Price decreases.
- Unchanged records as current-state confirmations without duplicate historical rows.
- Unavailable records.
- Returned records.
- Removed records.
- Crawl errors.
- Comparison between any two snapshots.
- First recorded price.
- Current price.
- Minimum price.
- Maximum price.
- Absolute change.
- Percentage change.
- Exact-date price lookup with an explicit last-known fallback.
- A change-only price timeline from first detection through last confirmation.

# 16. Output destinations

The Local Database must be enabled by default.

Allow multiple destinations for the same run:

```text
DATA OUTPUT

Local Database
Excel Files
Google Sheets via Apps Script
Google Drive and Sheets
```

The local database remains the source of truth.

# 17. Local storage settings

Provide:

- Current database location.
- Change Storage Location.
- Open Storage Folder.
- Database size.
- Database health.
- Backup.
- Restore.
- Repair.
- Compact Database.
- Export Database.
- Storage migration progress.

When changing storage location:

- Validate permissions.
- Detect unavailable or removable drives.
- Explain whether existing data will move.
- Never overwrite a database silently.
- Create a recoverable backup.
- Provide rollback.
- Report migration progress.

# 18. Data retention

Provide configurable retention policies:

```text
CHANGE HISTORY RETENTION

Keep detailed history for:
90 days

After that:
Keep daily summaries
Keep weekly summaries
Archive old history
Delete permanently
```

Always allow preserving:

- First recorded value.
- Latest value.
- Minimum price.
- Maximum price.
- Important user-marked events.

Provide:

- Retention preview.
- Estimated recovered space.
- Dataset-level exclusions.
- Backup before destructive cleanup.
- Storage usage warnings.
- Automatic database maintenance.

# 19. Excel output

Excel is an optional output destination.

Support:

```text
WORKBOOK STRUCTURE

One workbook for all sites
Separate workbook for each site
```

For a combined workbook, use separate sheets where schemas differ.

Support:

```text
UPDATE BEHAVIOR

Update existing rows
Create a new snapshot sheet
Create a new dated workbook
```

Provide:

- Change Save Location.
- Open Output Folder.
- Export Current View.
- Export Original Schema.
- Export Change History.
- Last Export Status.

Preserve Arabic data correctly.

# 20. Browse Data inside the Side Panel

Browse Data in the Side Panel is a compact preview, not a full analytics table.

Show:

- Dataset list.
- Record count.
- Last update.
- Change summary.
- Recent records.
- Compact Card View.
- Basic search.
- Basic filters.
- Open in Workspace.

Example:

```text
DATASETS

Example Store
1,842 records
Updated 12 minutes ago
34 changed · 15 new · 3 unavailable

Open Dataset
```

When a dataset is opened inside the Side Panel, use compact cards and limited fields.

Use virtualization for long lists.

# 21. Full-page Workspace

Provide an `Open in Workspace` action that opens a full extension page in a browser tab.

The Workspace must contain:

- Overview.
- Data.
- Changes.
- Crawl History.
- Review Queue.
- Jobs.
- Schedules.
- Sync.
- Exports.
- Logs.

The Data area must support:

- Dynamic table schemas.
- Search.
- Filters.
- Sorting.
- Pagination or virtualization.
- Column resizing.
- Column reordering.
- Manage Columns.
- Show Hidden Columns.
- Saved Views.
- Snapshot comparison.
- Export.
- Sync.
- Full-page horizontal scrolling when genuinely required.

# 22. Schema and column safety

Never treat a presentation change as a destructive schema change.

Every field must support:

```text
Source Key
Original Name
Display Name
Data Type
Visibility
Display Order
```

Rules:

- Source Key is stable and immutable.
- Original Name is preserved.
- Display Name is user-editable.
- Selecting X sets the field to Hidden.
- Selecting X never deletes the field or its data.
- Hidden fields continue receiving future updates.
- Users can show hidden fields again.
- Users can reset names.
- Users can reset layout.
- Users can restore the default view.
- Users can save multiple views.
- Export and sync can use either Original Schema or Current View.
- Destructive deletion requires explicit confirmation.

# 23. Job execution and lifecycle

Persist every job in the database.

Support states equivalent to:

- Scheduled.
- Queued.
- Preparing.
- Running.
- Pausing.
- Paused.
- Resuming.
- Cancelling.
- Cancelled.
- Completed.
- Partially Completed.
- Failed.
- Requires Review.

Persist:

- Job ID.
- Site IDs.
- Run mode.
- Current stage.
- Progress.
- Counters.
- Checkpoint.
- Started time.
- Last heartbeat.
- Retry count.
- Output status.
- Error summary.

Closing the Side Panel must not stop the job.

Reopening the Side Panel must retrieve and display the current state.

# 24. Active Job mini-player

Add a persistent mini-player above bottom navigation when a job is active.

Example:

```text
Amazon Update                         63%
Processing 8,420 of 10,000
1 running · 2 queued

View Job
Pause
```

The mini-player remains visible while the user moves between:

- Run.
- Browse Data.
- Settings.
- Add Site.

Selecting it opens the full job details.

# 25. Activity and logging

Do not add one UI row for every processed product.

The Local Runtime must store the complete technical log.

The Side Panel displays:

- Aggregated progress.
- Current step.
- Current site.
- Current counters.
- Last 200 log entries only.

Use a fixed-size Ring Buffer for UI logs.

Use virtualization for visible log rows.

Throttle UI progress updates instead of rendering every internal event.

Show:

- Overall percentage.
- Current site.
- Current stage.
- Records discovered.
- Records processed.
- Records created.
- Records updated.
- Records unchanged.
- Warnings.
- Errors.
- Elapsed time.
- Per-site progress.

Include:

- Show Technical Details.
- Pause Auto-scroll.
- Copy Visible Logs.
- Download Full Logs.
- Open Logs Folder.
- Pause.
- Resume.
- Cancel Run.
- Retry Failed Step.
- Open Dataset after completion.

# 26. Scheduling

Provide scheduling inside Site Settings.

Support:

- Manual.
- Daily.
- Weekly.
- Custom schedule when appropriate.
- Time selection.
- Time zone.
- Offline behavior.
- Missed-run behavior.
- Overlapping-run policy.
- Retry policy.
- Completion notifications.
- Failure notifications.
- Change-detected notifications.

Example:

```text
SCHEDULE

Frequency
Daily

Run At
09:00 AM

Time Zone
Asia/Riyadh

If Device Was Offline
Run when available

Overlapping Runs
Queue new run
```

Use the Local Runtime scheduler for reliable scheduling.

Use `chrome.alarms` only as browser-side coordination or fallback.

Do not claim that browser alarms can wake a sleeping or powered-off device.

If scheduling must work while Chrome is closed, implement an explicit user-approved Local Runtime background service or OS-level scheduling integration.

Clearly explain the behavior to the user in English.

# OS Resource and Hardware Management

Background jobs must not freeze the user's operating system or aggressively drain device batteries.

Implement:
- Hardware-aware concurrency limits (detect available CPU cores and RAM).
- Eco Mode: Automatically pause or throttle intensive jobs (like browser automation) when the device is running on battery power.
- System wake/sleep awareness to safely checkpoint and suspend running jobs when the OS goes to sleep.


# 27. Apps Script integration

Generate Apps Script code that users can copy into Google Sheets.

Setup interface:

```text
GOOGLE SHEETS — APPS SCRIPT

1. Create or open a Google Sheet
2. Open Extensions → Apps Script
3. Paste the generated code
4. Run the setup function
5. Deploy the script
6. Paste the deployment URL below
```

Include:

- Copy Script.
- Deployment URL.
- Test Connection.
- Save Connection.
- Regenerate Secret.
- Revoke Connection.
- Last Sync.
- Sync Now.
- Connection Logs.

The generated Apps Script must:

- Create required sheets.
- Create and update headers.
- Insert new records.
- Update existing records.
- Preserve supported user customizations.
- Read existing sheet data when required.
- Synchronize current data.
- Synchronize change history optionally.
- Resume interrupted synchronization.
- Prevent duplicate records.
- Support explicit full recreation.

All generated code and comments must be written in English.

# 28. Apps Script security

Do not rely on a permanent hard-coded bearer token.

Use a cryptographically secure connection secret.

Prefer:

- A 256-bit random secret.
- Secure local storage managed by Local Runtime.
- Apps Script `Script Properties`.
- HMAC request signing.
- Timestamp.
- Nonce.
- Replay protection.
- Revocation.
- Regeneration.
- Rate limiting.
- Constant-time signature comparison when possible.

Do not place secrets in URLs.

If standard HTTP authorization headers are not reliably available to Apps Script `doPost`, include the signature metadata inside the JSON request body.

# 29. Apps Script batching and recovery

Never send an entire large dataset in one request.

Use adaptive batching based on:

- Encoded payload size.
- Row count.
- Column count.
- Remaining execution time.
- Previous response time.
- Retry history.

Do not assume that 1,000 records are always an appropriate batch.

Persist:

```text
Sync Session ID
Dataset ID
Snapshot ID
Batch Number
Total Batches
Cursor
Checksum
Attempt Number
Status
Acknowledged At
```

The synchronization process must be:

- Resumable.
- Idempotent.
- Checkpointed.
- Retryable.
- Duplicate-safe.
- Observable.

Use:

- Batch acknowledgements.
- Checksums.
- Exponential backoff.
- Time-budget guards.
- Concurrency control.
- Partial-failure reporting.
- Resume from the last acknowledged batch.

Verify current official Google limits during implementation rather than relying on permanently hard-coded quota assumptions.

# 30. Direct Google integration

Provide a separate direct integration using:

- Continue with Google.
- Google Drive API.
- Google Sheets API.

Allow users to:

- Connect a Google account.
- View the connected account.
- Select or create a Drive folder.
- Create spreadsheets.
- Organize files.
- Synchronize existing datasets.
- Create missing headers.
- Update existing rows.
- Create snapshots.
- View the last sync result.
- Reconnect after authorization expires.
- Disconnect the account.

Organization options:

```text
FILE ORGANIZATION

One spreadsheet per site
One spreadsheet per crawl
Combined spreadsheet
```

Request only required permissions.

Store OAuth credentials securely.

Implement:

- Adaptive request batching.
- Quota awareness.
- Exponential backoff.
- Resumable synchronization.
- Clear error reporting.

# 31. Google Sheet conflict policy

The Local Database remains the source of truth by default.

Provide explicit sync policies:

```text
SYNC DIRECTION

Local Database to Google Sheets
Two-way Sync
```

For two-way sync, define:

- System-owned fields.
- User-editable fields.
- Conflict detection.
- Local wins.
- Google Sheet wins.
- Requires Review.
- Last-write metadata.
- Audit history.

Never overwrite a manual Google Sheet edit silently when two-way sync is enabled.

# 32. Multi-engine orchestration

Do not hard-code a single engine.

Support:

- Automatic engine recommendation.
- Preferred engine.
- Ordered fallback engines.
- Capability detection.
- Dependency checks.
- Per-site engine profiles.
- Per-step retries.
- Manual override.
- Structured failure reasons.

The execution log must show:

- Selected engine.
- Why it was selected.
- Engine switches.
- Fallback reasons.
- Retry attempts.
- Final failure reason.

# Proxy and Anti-Bot Management

Engine orchestration must handle anti-bot detection intelligently without causing permanent IP bans.

Support:
- Proxy configuration per site or globally.
- Residential and Datacenter proxy types.
- Automatic IP rotation per request or per session.
- Advanced browser fingerprint spoofing (e.g., modifying User-Agent, WebGL, canvas, and timezone metadata when using automated browsers).
- Rate-limit awareness and automatic cooldowns.

Do not permanently burn user IP addresses through aggressive retries on blocked access.

# Adapter Drift and Dynamic Maintenance

Website DOM structures and internal APIs change frequently, breaking hard-coded Site Adapters. 

The system must:
- Detect Adapter Breakdown: Identify when a previously successful site adapter experiences a sudden, extreme drop in success rates.
- Display an explicit `Adapter Outdated` status instead of a generic `Failed` error.
- Support dynamic fetching of updated adapter rules or configurations without requiring a full application update.
- Allow users to report broken adapters directly from the Side Panel.

# 33. Settings structure

Organize Settings into:

- General.
- Local Runtime.
- Storage.
- Crawling.
- Engines.
- Jobs and Scheduling.
- Excel.
- Apps Script.
- Google Account.
- Data and History.
- Privacy and Security.
- Logs and Diagnostics.
- About.

Use progressive disclosure.

Do not place every setting on one long screen.

# 34. Security and data safety

Treat all scraped content as untrusted.

Implement:

- Output sanitization.
- XSS prevention.
- Message validation.
- Command authorization.
- Native host origin restrictions.
- Secure secret storage.
- Path validation.
- Safe file creation.
- Database transactions.
- Backup before destructive operations.
- Audit logs.
- Runtime version compatibility checks.
- Protection against duplicate jobs.
- Concurrency limits.
- Safe cancellation.

Never execute remotely downloaded code inside the extension.

Comply with current browser-extension platform requirements.

# 35. Required UX states

Design and implement:

- First launch.
- Runtime not installed.
- Runtime checking.
- Runtime ready.
- Runtime update required.
- Runtime disconnected.
- Empty site list.
- Add Site.
- Site test running.
- Site test failed.
- No selected sites.
- Initial crawl.
- Update existing data.
- Full rebuild warning.
- Multi-site run.
- Scheduled run.
- Queued job.
- Paused job.
- Cancelled job.
- Partial success.
- Complete success.
- Failed run.
- Requires Review.
- Empty dataset.
- Dataset loading.
- Dynamic schema.
- Hidden columns.
- No detected changes.
- Sync pending.
- Sync running.
- Sync partially completed.
- Sync successful.
- Sync failed.
- Google disconnected.
- Apps Script not configured.
- Storage location unavailable.
- Database migration.
- Database backup.
- Database recovery.

# 36. Accessibility and responsive behavior

- Optimize the Side Panel for approximately 320px–400px widths.
- Avoid horizontal scrolling in the main Side Panel.
- Use Card View or compact previews for records.
- Use the Full Workspace for complex tables.
- Use keyboard navigation.
- Use accessible names and labels.
- Use visible focus states from the existing theme.
- Keep primary actions discoverable.
- Do not rely only on icons.
- Use confirmation dialogs only for destructive actions.
- Preserve scroll position where appropriate.
- Handle long URLs safely.
- Use `dir="auto"` or equivalent for scraped values.
- Force technical content to LTR.
- Test mixed Arabic and English data.

# 37. Testing requirements

Add tests for:

- Closing and reopening the Side Panel during a job.
- Runtime disconnection and reconnection.
- Job checkpoint recovery.
- Initial Crawl.
- Update Existing Data.
- Full Rebuild backup.
- Composite identity matching.
- Requires Review.
- Merge and Undo Merge.
- Price history preservation.
- Column rename without source-key mutation.
- Column hiding without data deletion.
- Apps Script batch retry.
- Duplicate batch prevention.
- Interrupted sync resume.
- Google authorization expiration.
- Storage migration failure.
- Scheduled-run recovery.
- Arabic data rendering.
- Native Messaging pagination.
- Log Ring Buffer behavior.
- Large dataset virtualization.
- XSS sanitization.

# 38. Expected implementation quality

- Use reusable components.
- Use typed domain models.
- Use explicit state machines where helpful.
- Separate UI, domain logic, execution, storage, and synchronization.
- Do not hard-code site schemas.
- Do not hard-code one engine.
- Do not hard-code one output.
- Do not store complete datasets in UI state.
- Do not stream one UI log event per product.
- Do not couple jobs to the Side Panel lifecycle.
- Clearly identify mock and production integrations.
- Add validation and structured recovery.
- Preserve existing project conventions.
- Verify realistic Side Panel dimensions.
- Verify the Full Workspace separately.
- Keep code comments in English.

# 39. Final implementation phases

Complete the work in these phases:

1. Inspect the existing project.
2. Explain your understanding to me in Arabic.
3. Present the implementation plan in Arabic.
4. Define the architecture and responsibility boundaries.
5. Define the domain and state models.
6. Implement Local Runtime communication abstractions.
7. Implement the Side Panel.
8. Implement the active-job mini-player.
9. Implement the Full Workspace.
10. Implement dataset and schema customization.
11. Implement job persistence and lifecycle recovery.
12. Implement scheduling.
13. Implement Excel output.
14. Implement Apps Script synchronization.
15. Implement direct Google integration.
16. Implement identity conflict review.
17. Implement logging, retention, backup, and recovery.
18. Test critical workflows.
19. Visually inspect realistic Side Panel and Workspace dimensions.
20. Report completed work, assumptions, limitations, test results, and next steps to me in Arabic.

The final product must feel like a focused, reliable, local-first crawling and data synchronization platform specifically designed around a browser Side Panel and a full data-management Workspace.

# 40. Incremental Evolution into a Generic Crawling and Data-Modeling Platform

## Mission

Evolve ScrapeX incrementally from its current product-and-price tracking system into a generic, metadata-driven crawling, extraction, and data-modeling platform.

The final platform should be capable of:

- Crawling broadly different website structures.
- Discovering multiple datasets within the same site or page.
- Extracting HTML tables, repeated DOM structures, structured data, embedded JSON, REST APIs, GraphQL responses, and browser-observed network data.
- Inferring dynamic schemas whose columns may appear, disappear, change names, or change types over time.
- Detecting and managing multiple datasets per site.
- Inferring and reviewing relationships between datasets.
- Building a versioned site-specific data model.
- Preserving raw source evidence, historical revisions, provenance, and schema history.
- Presenting dynamic datasets, columns, relationships, and crawl state through the Side Panel and Full Workspace.
- Exporting either the original discovered schema or a user-customized view.
- Keeping the existing price-tracking domain fully operational throughout the evolution.

This is an evolutionary program, not a rewrite.

## Prime Directive: Extend, Preserve, and Migrate Incrementally

Never destroy and rebuild the existing product merely to obtain a cleaner architecture.

Before implementing any capability:

1. Inspect the current repository and identify existing components that already solve part of the problem.
2. Reuse or extend those components wherever doing so preserves correctness.
3. Introduce a compatibility seam when the existing design is too specialized.
4. Move one vertical slice at a time through the new seam.
5. Keep the old path operational until the replacement path has proven behavioral parity.
6. Remove or retire an old path only after:
   - Its replacement is complete.
   - Migration is tested.
   - Existing data remains readable.
   - Rollback is possible.
   - The user has explicitly approved retirement.

Do not perform speculative large-scale refactoring.

Do not rename, relocate, or rewrite stable modules unless the current increment genuinely requires it.

Do not mix architectural cleanup with unrelated feature work.

Every increment must leave the application runnable, testable, and recoverable.

Repository behavior and tests are the ground truth. If this plan conflicts with proven repository behavior, report the conflict before changing the behavior.

## Existing Capabilities That Must Be Preserved

Treat the following as valuable working assets rather than temporary code:

- Existing product and price ingestion.
- Append-only price observation history. Existing observations are immutable;
  the optimized price path may reduce future write frequency by appending only
  the first price and real changes, as defined in section 15, but it must never
  rewrite or delete legacy observations.
- Current connectors and fetchers.
- Job persistence, pause, resume, cancellation, and checkpoint recovery.
- Native Messaging and localhost communication.
- Side Panel and active-job mini-player.
- Full Workspace.
- Storage, backup, restore, migration, and retention mechanisms.
- Column customization and saved views.
- Excel, Apps Script, and direct Google output paths.
- Review Queue and identity conflict decisions.
- Arabic content normalization and bidirectional rendering.
- Existing tests, fixtures, screenshots, and public contracts.

The price engine must become the first specialized domain built on, or interoperating with, the generic platform. It must not be discarded.

The price-history optimization in section 15 is the owner-approved target for
that specialized domain. It must be introduced through additive schema,
backfilled projections, compatibility tests, and a reversible cutover. Generic
phases do not have implicit permission to repurpose `generic_record`, rewrite
`price_observation`, or weaken existing price workflows while implementing this
optimization.

## Honest Definition of “Generic”

Do not claim that ScrapeX can scrape literally every website.

A generic platform means:

- It supports several reusable extraction patterns.
- It can describe site-specific behavior through versioned metadata.
- It provides an adapter mechanism for exceptional sites.
- It reports unsupported, blocked, ambiguous, or authentication-dependent cases honestly.
- It never silently returns incomplete or structurally incorrect data.
- It distinguishes crawler failure, extractor failure, schema drift, access denial, and unsupported structure.

CAPTCHAs, strong anti-bot systems, inaccessible authenticated content, legal restrictions, and highly interactive applications may still require user intervention or a specialized adapter.

## Architectural Direction

Separate the following responsibilities:

```text
Site Project
    ↓
Crawl Plan
    ↓
URL Frontier
    ↓
Fetcher
    ↓
Page Snapshot
    ↓
Dataset Discovery
    ↓
Extraction Plan
    ↓
Schema Inference
    ↓
Generic Records
    ↓
Identity Resolution
    ↓
Relationship Inference
    ↓
Versioned Site Data Model
    ↓
Workspace / Export / Sync
```

### Crawl and Scrape Are Different Operations

`Crawl` discovers and revisits pages.

`Scrape` extracts one or more datasets from a page or response.

Do not couple URL discovery to product extraction.

The crawler must be able to discover pages even when no extraction rule has been approved yet.

The extractor must be able to run against a saved page snapshot without repeating a network request.

### Domain Type and Extraction Method Are Different Concepts

Do not use one enum to represent both what the data means and how it was obtained.

Keep separate concepts such as:

```text
Domain:
- generic
- prices
- listings
- documents
- user-defined

Extraction Method:
- html_table
- repeated_dom
- json_array
- json_path
- json_ld
- embedded_json
- rest_api
- graphql
- browser_network
- custom_adapter
```

A dataset may use any extraction method without being classified as product or price data.

## Generic Metadata Model

Introduce the generic model through additive database migrations.

At minimum, support concepts equivalent to:

```text
SiteProject
CrawlPlan
CrawlRun
CrawlPage
PageSnapshot
PageType
DatasetDefinition
DatasetCandidate
DatasetSchemaVersion
FieldDefinition
ExtractionRule
GenericRecord
RecordRevision
RelationshipDefinition
RecordRelationship
AdapterDefinition
AdapterVersion
SchemaChange
```

### Dataset Definition

A dataset definition should identify:

- Stable dataset key.
- User-facing name.
- Source page type.
- Extraction method.
- Source selector, JSON path, or response path.
- Cardinality.
- Pagination strategy.
- Identity strategy.
- Current schema version.
- Adapter version.
- Dataset status.
- Provenance and timestamps.

### Field Definition

A field definition should preserve:

```text
field_key
source_name
display_name
source_path
data_type
nullable
repeated
key_role
position
confidence
first_seen_at
last_seen_at
status
```

Rules:

- `field_key` is stable and internal.
- `source_name` preserves the exact source label or property name.
- `display_name` is a presentation preference.
- Renaming a display name never changes source identity.
- Hiding a field never deletes it.
- Missing fields remain in schema history.
- New fields create a new schema version.
- Type changes are recorded, not silently overwritten.
- Automatic widening is allowed only through safe rules such as `integer → decimal → text`.
- Automatic narrowing is forbidden.
- Objects and arrays must remain representable without flattening away information.

### Generic Record Storage

Do not create an uncontrolled physical SQL table for every detected HTML table.

Prefer a hybrid model:

- Metadata tables describe datasets, fields, schemas, and relationships.
- Each record stores its canonical values as validated JSON.
- Frequently searched or indexed fields may receive explicit projections.
- Record revisions preserve historical changes.
- Raw snapshots remain available for re-extraction and audit.
- Materialized views may be created for performance, but they are derived and rebuildable.

Every record must preserve:

```text
record_id
dataset_id
record_key
schema_version_id
data
source_page_id
source_locator
content_hash
first_seen_at
last_seen_at
status
```

## Dataset Discovery

Dataset discovery must return candidates, not immediately create permanent datasets.

Initial reusable detectors should include:

1. Semantic HTML tables.
2. Repeated DOM structures such as cards, rows, listings, and definition blocks.
3. JSON arrays and nested object collections.
4. JSON-LD, Microdata, and embedded structured data.
5. REST and GraphQL response collections.
6. Browser-observed fetch/XHR responses.

Each candidate should report:

```text
candidate name
source type
source locator
estimated row count
sample records
detected fields
candidate identity fields
pagination evidence
confidence
warnings
```

The user must be able to:

- Preview the candidate.
- Accept or reject it.
- Rename it.
- Edit field names and types.
- Select or define identity fields.
- Configure pagination.
- Approve the dataset before persistent ingestion.

Discovery must never pollute the permanent dataset store.

## Dynamic Schema and Schema Drift

Every dataset must have versioned schemas.

When a later crawl differs from the approved schema, classify the difference:

```text
field_added
field_missing
field_renamed_candidate
field_type_widened
field_type_conflict
structure_changed
identity_field_missing
relationship_broken
extractor_failed
adapter_outdated
```

Safe additions may be accepted automatically according to dataset policy.

Destructive or ambiguous changes must enter a Schema Review Queue.

Never delete historical values because a field disappeared from the latest page.

Never reuse an old field key for a semantically different field.

Store enough provenance to explain why two fields are believed to represent the same source field.

## Identity Inference

Infer candidate record keys using this order:

1. Explicit source ID.
2. Stable API identifier.
3. Declared primary key.
4. Canonical detail URL.
5. Highly unique non-null field.
6. Composite key.
7. Deterministic fingerprint.

For every suggested key, calculate and display:

- Uniqueness percentage.
- Null percentage.
- Duplicate examples.
- Stability across snapshots.
- Confidence.
- Fields used.

Ambiguous identity must enter review.

Never merge records solely because names are similar.

Existing price identity behavior must remain unchanged until the generic identity system proves parity for that domain.

## Relationship Inference

Support relationships between datasets:

```text
one_to_one
one_to_many
many_to_one
many_to_many
hierarchical
```

Use evidence such as:

- Matching primary and foreign-key candidates.
- Nested JSON ownership.
- Shared stable identifiers.
- Detail-page URLs.
- Parent-child DOM structure.
- Link targets.
- Repeated uniqueness and cardinality evidence.
- User-defined mapping.

A relationship suggestion must include:

```text
from_dataset
from_fields
to_dataset
to_fields
cardinality
confidence
evidence
sample_matches
orphan_count
conflict_count
status
```

Low-confidence relationships must never be activated automatically.

Many-to-many relationships must use an explicit logical junction dataset.

Relationships must be versioned and reviewed when schema drift invalidates their fields.

## Declarative Adapter System

Implement generic extraction first, then use site adapters only for exceptions.

Adapters should preferably be declarative and versioned.

An adapter may define:

- Page-type matching.
- Crawl scope.
- URL normalization.
- Dataset selectors.
- Field selectors.
- JSON paths.
- Pagination rules.
- Identity rules.
- Relationship hints.
- Validation rules.
- Expected-volume canaries.

Never execute remotely downloaded Python or JavaScript.

Remote updates may provide validated configuration only.

Adapter updates must support:

- Signature or trust verification.
- Versioning.
- Compatibility checks.
- Rollback.
- Test-fixture validation.
- Drift detection.
- Explicit `Adapter Outdated` state.

## User Experience Evolution

Extend the existing Side Panel and Workspace; do not replace them.

The generic Add Site flow should evolve into:

```text
1. Enter site URL
2. Configure crawl boundaries
3. Discover pages
4. Detect dataset candidates
5. Preview candidate data
6. Approve datasets
7. Review dynamic schemas
8. Select identity keys
9. Review relationships
10. Save the site model
11. Start the crawl
```

Add Workspace areas for:

- Pages.
- Datasets.
- Schema.
- Relationships.
- Data Model.
- Extraction Rules.
- Schema Changes.
- Failed Pages.
- Raw Snapshots.
- Crawl Runs.

The Data Model screen should visualize approved datasets and relationships.

Large datasets must use pagination or virtualization.

The table renderer must be generated from the active schema version rather than from hard-coded price columns.

## Incremental Implementation Protocol

Work in small vertical slices.

A vertical slice must include, where applicable:

- Domain model.
- Database migration.
- Repository/service logic.
- API.
- UI.
- Tests.
- Error states.
- Migration or compatibility behavior.
- Visual verification.
- Documentation.

Do not implement a large backend subsystem without one minimal user-visible workflow proving that it works.

For every slice:

1. Inspect current behavior and tests.
2. State what will be reused.
3. State the smallest new seam required.
4. Implement the database change additively.
5. Implement the domain logic independently of the UI.
6. Add API boundaries.
7. Add one usable UI path.
8. Add happy-path, failure-path, recovery, and migration tests.
9. Run the full existing test suite.
10. Verify existing price workflows remain unchanged.
11. Visually inspect relevant Side Panel and Workspace states.
12. Report completed work, remaining limitations, and the next smallest slice.

If a slice breaks an existing test, treat it as a regression unless the user explicitly approved the behavioral change.

## Delivery Phases

### Phase G0 — Baseline and Compatibility Contract

- Record current database, API, CLI, Native Messaging, UI, and export behavior.
- Fix failing storage-safety regressions before adding generic ingestion.
- Add tests protecting existing price workflows.
- Define the compatibility boundary between price-specific and generic behavior.
- Add feature flags for unfinished generic screens.

Exit condition: current behavior is protected and the repository is green.

### Phase G1 — Generic Dataset Catalog

- Add SiteProject, DatasetDefinition, SchemaVersion, and FieldDefinition.
- Add generic record and revision storage.
- Implement additive migrations.
- Add repository APIs and tests.
- Expose a minimal read-only Dataset Catalog in the Workspace.

Exit condition: a manually defined generic dataset can store and display arbitrary records without affecting price tables.

### Phase G2 — First Generic Extraction Slice

Implement one complete extraction path:

```text
Saved HTML snapshot
→ HTML table detection
→ candidate preview
→ schema inference
→ user approval
→ generic ingestion
→ dynamic Workspace table
```

Exit condition: a non-product HTML table can be extracted and browsed end to end.

### Phase G3 — Repeated DOM and JSON Extraction

- Add repeated-card/list extraction.
- Add JSON array and JSONPath extraction.
- Add embedded JSON and JSON-LD extraction.
- Preserve source paths and raw evidence.
- Add fixture-driven conformance tests.

Exit condition: structurally different datasets use the same generic ingest and UI path.

### Phase G4 — Crawl Frontier

- Add persistent URL frontier.
- Add canonicalization and deduplication.
- Add scope, depth, page, and time limits.
- Add sitemap and link discovery.
- Add checkpoint recovery.
- Separate discovery status from extraction status.

Exit condition: a crawl can discover and resume pages without requiring product semantics.

### Phase G5 — Multi-Dataset Sites

- Detect several datasets from the same site.
- Allow independent approval and scheduling.
- Support dataset-specific extraction and pagination rules.
- Show dataset-level progress and failures.

Exit condition: one site can own several separately browsable datasets.

### Phase G6 — Relationships and Site Data Model

- Add key profiling.
- Add relationship suggestions.
- Add relationship review.
- Add one-to-many and many-to-many support.
- Add Data Model visualization.
- Add orphan and conflict reporting.

Exit condition: approved related datasets can be navigated and exported as a coherent site model.

### Phase G7 — Schema and Adapter Drift

- Detect schema changes.
- Add Schema Review Queue.
- Add adapter versioning.
- Add volume and structural canaries.
- Add rollback and re-extraction from saved snapshots.

Exit condition: site changes are explicit, explainable, and recoverable.

### Phase G8 — Dynamic Outputs and Synchronization

- Export any dataset using Original Schema or Current View.
- Preserve dataset relationships in export metadata.
- Support multi-sheet/workbook strategies.
- Apply dynamic schemas to Apps Script and Google synchronization.
- Resume interrupted multi-dataset synchronization.
- Report partial failures per dataset.

Exit condition: generic datasets no longer depend on price-specific export columns.

### Phase G9 — Hardening and Public Readiness

- Large crawl tests.
- Large dynamic-schema tests.
- Multi-dataset and relationship tests.
- Arabic and mixed-direction data tests.
- XSS and untrusted-content tests.
- Recovery after shutdown, sleep, disconnection, and migration failure.
- Performance profiling.
- Adapter-drift tests.
- Documentation and onboarding.

Exit condition: generic functionality is reliable without weakening existing price functionality.

## Definition of Done for Every Increment

An increment is not complete merely because classes or database tables exist.

It is complete only when:

- The feature is reachable through a real workflow.
- State is persistent.
- Failures are visible and actionable.
- Recovery behavior is defined.
- Existing data remains safe.
- Existing price workflows still pass.
- Tests cover success, failure, retry, and migration.
- The UI includes empty, loading, running, partial, success, and failure states where applicable.
- Side Panel and Workspace layouts are visually verified.
- Documentation distinguishes implemented behavior from planned behavior.
- No static mock is presented as a production integration.

## Decision Rules

Ask for user direction before:

- Removing or replacing a working compatibility path.
- Performing a destructive migration.
- Changing record identity behavior.
- Automatically approving inferred relationships.
- Automatically accepting an ambiguous schema rename.
- Expanding crawl scope beyond the configured site boundaries.
- Introducing remote adapter updates.
- Changing which database is the source of truth.

For ordinary additive implementation details, make the safest reasonable decision and continue.

## Required Progress Report

After every completed slice, report in Arabic:

```text
Slice
What existed before
What was reused
What was added
Database migrations
Compatibility impact
Tests added
Full test result
Visual evidence
Known limitations
Next recommended slice
```

Maintain a living implementation matrix with:

```text
Capability
Not Started
Foundation
Partial
Production Ready
Evidence
Known Limitations
Next Action
```

Never inflate progress because a model, API route, or static screen exists.

Measure progress using complete end-to-end workflows.

## Final Principle

ScrapeX must become generic by adding stable metadata-driven capabilities around its proven core, not by erasing the core.

The desired end state is:

```text
Generic crawling and extraction platform
    ├── Generic datasets
    ├── Dynamic schemas
    ├── Dataset relationships
    ├── Site-specific data models
    ├── Declarative adapters
    ├── Dynamic exports and synchronization
    └── Price tracking as the first specialized domain
```

At every stage, prefer:

```text
working old path + tested new path
```

over:

```text
unfinished replacement + removed old path
```
