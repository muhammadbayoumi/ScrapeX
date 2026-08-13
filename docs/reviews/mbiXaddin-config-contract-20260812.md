# The mbiXaddin configuration contract, read from its C#

Measured 2026-08-12 by seven agents over ~350 .cs files. Every answer
carries file:line. This is the source the ScrapeX Console validates
against — it must never invent a rule the add-in does not have.


## the-loader

### Which type and method reads the configuration workbook?

`MetadataOrchestrator` — a partial class split across two files (Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs = fetch/graph/registry; MetadataOrchestrator.Tier1Schema.cs = SQLite persistence). Two entry points: `SyncMetadataAsync(bool forceRefresh, IStatusScope)` (line 129) decides cache-vs-live and calls `RunOnlinePipeline` (line 249) for the network read; `LoadFromSqlite()` (line 209) is the offline read. TSV→entity parsing is `TsvParser.Parse<T>(string tsv)` (TsvParser.cs:28), reflection-based over `[JsonProperty]` names. The callers are SyncManager.SyncMetadataAsync (SyncManager.cs:471) and Bootstrapper Stage 0 (Bootstrapper.cs:268).

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:249 — `private async Task RunOnlinePipeline(bool forceRefresh, IStatusScope parentScope)`; :209 — `public bool LoadFromSqlite()`

### Which of the six sheets does it read, and in what order?

ONLINE: all six, fetched CONCURRENTLY — there is no sequential order. The six tasks are created in this order and then joined with `Task.WhenAll`: TableDefinition, SchemaRule, DataSource, DataMap, ExportViews, RibbonControls (MetadataOrchestrator.cs:265-272). OFFLINE (`LoadFromSqlite`): only FIVE tables, read sequentially — _SYS_DEFINITIONS, _SYS_SCHEMA_RULES, _SYS_DATA_SOURCES, _SYS_DATA_MAP, _SYS_EXPORT_VIEWS (:218-232). RibbonControls is NEVER read by the orchestrator on the offline path and is never part of the registry graph: it is fetched, persisted to _SYS_RIBBON_CONTROLS, and then read straight from SQLite by the ribbon layer (ThisAddIn.cs:191 `SELECT CONTROL_KEY, MAX(MENU_LAYOUT) FROM _SYS_RIBBON_CONTROLS`). Only 5 of the 6 sheets feed `BuildAndRegister` (MetadataOrchestrator.cs:361).

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:265 — `var tDef = FetchTsvAsync<TableDefinitionEntity>(Endpoints.SysDefinitionsUri.AbsoluteUri);` … :270 `var tRibbonControls = FetchTsvAsync<RibbonControlEntity>(Endpoints.SysRibbonControlsUri.AbsoluteUri);` :272 `await Task.WhenAll(tDef, tSchema, tSources, tMaps, tViews, tRibbonControls)`

### Google Sheet, embedded resource, local file, or all three?

ALL THREE, in three distinct roles. (1) The ROWS come over the network from a published Google Sheet as TSV (`_http.DownloadStringAsync(url)`, MetadataOrchestrator.cs:775). (2) The six URLs come from an EMBEDDED RESOURCE `mbiXaddin.Core.endpoints.json`, per-key validated with per-key fallback to compiled literals — a broken endpoints.json can never leave the add-in offline (EndpointCatalog.cs:77, :113-128). (3) The parsed rows are cached in a LOCAL SQLite file as the six _SYS_* TIER-1 tables and re-read on the offline path. There is no loose config file on disk — endpoints.json is compiled in deliberately so the sheet URLs stay off disk.

*certain* — mbiXaddin/Core/EndpointCatalog.cs:77 — `internal const string ResourceName = "mbiXaddin.Core.endpoints.json";`; mbiXaddin/mbiXaddin.csproj:585 — `<EmbeddedResource Include="Core\endpoints.json" />`

### What is the URL shape of the config fetch?

`{googleSheetPub}?gid={gid}&single=true&output=tsv` — one URL per sheet, composed by `EndpointCatalog.Sheet(pubBase, gid)`. The base today is `https://docs.google.com/spreadsheets/d/e/2PACX-1vTg9_7sw453ZaaHA-56WxQKIXwmpOkryauPiz9dUK688dXhXIXskHzsadUoCy86kkikrFPdwybHYNf0/pub`. HTTP GET additionally appends a cache-buster query parameter (`bypassCache: true` is the default). Note this is the CONFIG workbook URL — it is compiled in, not editable from the workbook. DATA source URLs (SOURCE_URI in the DataSource sheet) are a separate, human-authored shape.

*certain* — mbiXaddin/Core/EndpointCatalog.cs:244 — `private static Uri Sheet(string pubBase, string gid) => new Uri(pubBase + "?gid=" + gid + "&single=true&output=tsv");`

### Which gid identifies each of the six sheets?

sysDefinitions=1974308164 (TableDefinition), sysSchemaRules=1666369555 (SchemaRule), sysDataSources=434807667 (DataSource), sysDataMap=2085184385 (DataMap), sysExportViews=756534895 (ExportViews), sysRibbonControls=1089316777 (RibbonControls). These are the compiled defaults AND the values currently authored in the embedded endpoints.json; the loader accepts only an all-digits string for a gid, otherwise it falls back to the compiled default and records a diagnostic (EndpointCatalog.cs:257-264).

*certain* — mbiXaddin/Core/EndpointCatalog.cs:56 — `{ "sysDefinitions",    "1974308164" },` … :62 `{ "sysRibbonControls", "1089316777" },`

### Is the config cached, and with what policy?

Yes — a 24-hour TTL over the local SQLite copy. `MetaTtl = TimeSpan.FromHours(24)`; freshness is a marker row keyed `_METADATA_SYNC` in _SYS_SYNC_STATE, checked by `IsMetadataFresh()`. Three important qualifiers: (a) boot ALWAYS forces a live refresh (`RunAsync(forceMetaRefresh: true …)`, Bootstrapper.cs:390-391) and so does the per-table "Update Table" button (SyncManager.cs:419), so the TTL only governs non-forced calls; (b) the marker is advanced ONLY when the SQLite persist actually COMMITTED (MetadataOrchestrator.cs:366-376) — a rolled-back persist leaves the cache as the previous generation; (c) even a fresh cache is re-checked: if it loaded but every entity has zero sources, the orchestrator forces a network refresh anyway (`HasNoUsableSources`, :175-189). HTTP-level caching is bypassed (cache-buster appended, `bypassCache = true` default; HttpClient.Timeout = 60s, MaxRetries = 3).

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:68 — `private static readonly TimeSpan MetaTtl = TimeSpan.FromHours(24);`; MetadataOrchestrator.Tier1Schema.cs:470 — `return (DateTime.UtcNow - state.SyncedAt.Value) < MetaTtl;`

### What happens when the configuration workbook is unreachable?

Nothing throws out of the fetch itself: `FetchTsvAsync` wraps everything in try/catch and returns `FetchResult<T>.Empty($"Network error: {ex.Message}")` (MetadataOrchestrator.cs:801-805). The abort decision is then made per sheet: the FOUR registry-critical sheets (SYS_DEFINITIONS, SYS_SCHEMA_RULES, SYS_DATA_SOURCES, SYS_DATA_MAP) are collected by `CollectCriticalFailure`, and any failure throws `MetadataFetchException` BEFORE anything is persisted. SyncManager catches it as an expected degraded mode (a warning, not an error) and calls `LoadMetadataFallbackAsync` → `LoadFromSqlite()`, returning `MetadataOutcome.Stale` (not Fresh — which closes the destructive orphan-cleanup gate downstream) or `Failed` if even SQLite fails. The two OPTIONAL sheets (ExportViews, RibbonControls) degrade independently: their cached rows are kept and the run continues. The SQLite cache is never truncated on a failed fetch and the TTL marker is not advanced.

*certain* — mbiXaddin/Infrastructure/Services/Sync/SyncManager.cs:480 — `catch (MetadataFetchException fetchEx)` … :485 `return await LoadMetadataFallbackAsync().ConfigureAwait(false);`

### What happens if the config URL returns HTTP 200 with an HTML page (captive portal / sign-in / expired share link)?

Two independent layers reject it, both producing `FetchResult.Empty(reason)` → `FetchFailed = true` → a critical failure for the four critical sheets. Layer 1: `SourceIntegrityGate.LooksLikeMarkup(tsv)` in FetchTsvAsync, message "The server returned a web page, not TSV — the link may require sign-in." Layer 2: TsvParser's structural guard — if NOT ONE header column maps to a property of T, it refuses ("The response does not look like {T} data — none of its {n} column(s) is recognised"). The guard is keyed on "nothing matched", never "something didn't match", so a sheet that GAINS an unknown column keeps working.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:56 — `if (propMap.Count == 0) return FetchResult<T>.Empty(...)`; MetadataOrchestrator.cs:788 — `if (SourceIntegrityGate.LooksLikeMarkup(tsv))`

### FAILURE MODE — what can abort the WHOLE workbook load (no table loads at all)?

Exactly two conditions, both raising `MetadataFetchException` (the only config-load exception type; MetadataFetch.cs:27). (1) Any of the four REGISTRY-CRITICAL sheets — SYS_DEFINITIONS, SYS_SCHEMA_RULES, SYS_DATA_SOURCES, SYS_DATA_MAP — either failed transport (FailReason set) OR returned zero valid rows while its cached table is non-empty (refusing to overwrite a good cache with nothing). (2) SYS_DEFINITIONS came back with `Valid.Count == 0` and an empty cache — message distinguishes "all N row(s) were rejected by parsing/validation" from "the published sheet contains 0 rows (server-side configuration)". IMPORTANT for the Console: no single bad ROW can abort the workbook. The only row-shaped abort is "every definition row was rejected". Neither exception reaches the user as a dialog — SyncManager swallows it into the cache fallback.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:302 — `if (criticalFailures.Count > 0) throw new MetadataFetchException(criticalFailures);`; :307 — `if (rawDefs.Valid.Count == 0) throw new MetadataFetchException(...)`

### FAILURE MODE — what makes a table never appear in the registry at all?

Three row conditions in `BuildContextGraph`, all silent-to-the-user (log warning only): (1) ENTITY_KEY is blank/whitespace → the row is filtered out; (2) IS_ACTIVE is false → filtered out, with a `[MetaOrch] N definition(s) skipped — IS_ACTIVE=false` warning; (3) a DUPLICATE ENTITY_KEY → only the FIRST occurrence is kept, the rest logged as `[DUPLICATE] ENTITY_KEY '<k>' appears more than once in SYS_DEFINITIONS`. The user then meets it as an export failure: ExportEngine throws `Table '{entityKey}' is not available. Wait for sync to complete or check the entity key.` which ActionRouter shows in a `DialogHelper.ShowError(..., "Export Failed")` box; the Update-Table path shows `'{entityKey}' was not updated.\n\nNot in registry.` in a "Update Skipped" box.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:528 — `var activeDefsRaw = definitions.Where(d => d != null && d.IS_ACTIVE && !string.IsNullOrWhiteSpace(d.ENTITY_KEY)).ToList();`; ExportEngine.cs:241 — `if (!_registry.Contains(entityKey)) throw new InvalidOperationException($"Table '{entityKey}' is not available. …");`

### FAILURE MODE — what makes a REGISTERED table refuse to sync (so it stays empty or stale)?

`SyncManager.IngestEntitySafeAsync` calls `_validator.ValidateContext(context)` and, if `!report.IsValid`, SKIPS the whole entity with `FailReason = $"Validation: {report.ErrorCount} error(s)"`. `IsValid` means "no result with Severity >= Error" (Validation.cs:166-167), so only Error/Critical findings block. The blocking findings, from `TableMetadataContext.ValidateCompleteness()`, are: (a) ENTITY_KEY empty [Critical]; (b) DISPLAY_NAME missing [Error]; (c) PARENT_KEY == ENTITY_KEY, circular inheritance [Critical]; (d) MALFORMED JSON in ANY of UX_CONFIG / SYS_CONFIG / RIBBON_CONFIG / EXPORT_CONFIG on the TableDefinition row [Error — `ConfigValidator.ValidateBag` yields `ValidationResult.Fail(..., CodeInvalidJson)`]; (e) "Table 'X' has no column definitions in SYS_SCHEMA_RULES" [Error]; (f) a CONVERSION table missing any of CONV_SOURCE / CONV_TARGET / CONV_FACTOR [Error]; (g) a LIBRARY / menu-source table with no MENU_KEY column AND no primary key [Error]. Everything else in ValidateCompleteness is a Warning and does NOT block: missing PK, >1 PK, a source whose PROFILE_KEY has no SYS_DATA_MAP rows, a mapping whose TARGET_ATTRIBUTE_KEY is not in SYS_SCHEMA_RULES, a COST table with no PRICE role, duplicate singular MENU_* roles. Item (d) is the highest-value target for the Console: one stray trailing comma in a JSON bag silently stops that table from ever syncing.

*certain* — mbiXaddin/Infrastructure/Services/Sync/SyncManager.cs:601 — `if (!report.IsValid) { … return new EntitySyncResult { EntityKey = context.EntityKey, Skipped = true, FailReason = $"Validation: {report.ErrorCount} error(s)" }; }`; Core/Models/TableMetadataContext.cs:346 — `report.Add(ValidationResult.Fail("Columns", $"Table '{EntityKey}' has no column definitions in SYS_SCHEMA_RULES.", …))`

### FAILURE MODE — what makes the SQLite table for an entity never get created?

`SqlBuilderService.BuildCreateTable` throws `InvalidOperationException($"Table '{context.EntityKey}' has no persisted columns.")` when `PersistedColumns` (all columns with IS_VIRTUAL=false) is empty — i.e. the entity has no SchemaRule rows at all, or every one of them has IS_VIRTUAL=true. `EnsureOperationalTable` catches that and only logs `Failed to create table '{ctx.EntityKey}'` — the entity stays registered, the physical table never exists, every later read of it fails and is swallowed into a blank sheet. Note the table name and every column name go through `Sanitize`, so odd characters in ENTITY_KEY/ATTRIBUTE_KEY are stripped rather than rejected.

*certain* — mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:52 — `if (cols.Count == 0) throw new InvalidOperationException($"Table '{context.EntityKey}' has no persisted columns.");`; MetadataOrchestrator.Tier1Schema.cs:56 — `catch (Exception ex) { _log.LogError($"Failed to create table '{ctx.EntityKey}'.", ex, SourceName); }`

### FAILURE MODE — what makes an export render a BLANK or empty sheet instead of erroring?

Four silent paths, all of which produce a created-but-empty worksheet: (1) `GetVisibleColumns` returns zero — every column IS_VIRTUAL=true, or all IS_VISIBLE=false for a non-Admin tier, or the view's COLUMNS list names no column that exists — RenderInternal logs `No visible columns for current user tier.` and RETURNS before writing anything. (2) A view's WHERE_FILTER or SORT_BY is bad SQL: `ExportQuerySql.BuildSelect` appends both fragments VERBATIM (it only truncates at the first ';' and bracket-quotes the table name — there is NO column-name or syntax validation), so a typo makes `ExecuteDataTable` throw, and `LoadFromSqlite` catches it and returns `UnifiedData.Empty`, logging only `Failed to load from SQLite`. (3) The physical table does not exist (see previous answer) — same catch, same blank sheet. (4) A view's COLUMNS list filters the column set down to nothing (GetVisibleColumns:1199-1203). None of these reach the user as a dialog.

*certain* — mbiXaddin/Infrastructure/Engines/ExportEngine.cs:1292 — `catch (Exception ex) { _log.LogWarning($"[{entityKey}] Failed to load from SQLite: {ex.Message}", SourceName); return UnifiedData.Empty; }`; Infrastructure/Database/ExportQuerySql.cs:41 — `if (where.Length > 0) sql.Append(" WHERE ").Append(where);`

### FAILURE MODE — what makes ingestion of a table's data fail after the config loaded fine?

Ten distinct hard failures in `DataIngestionService.PrepareSourceAsync` / `ValidateMappingCompleteness`, each returning `IngestionResult.Fail(...)` (existing rows untouched): SOURCE_URI blank → Skip(DeferredNoUrl) "No download URL available."; SOURCE_URI not starting with "http" → `[CONFIG ERROR] … has an INVALID URL` / "Invalid Source URL"; download failed; zero-byte response → "Empty response."; response over MaxSourceBytes → "Source exceeds size limit."; response sniffs as markup → "Source returned a web page, not TSV (check '?output=tsv')."; CONTEXT_PROPS.SkipRows < 0 → "…must be an integer >= 0"; no SYS_DATA_MAP rows for the resolved PROFILE_KEY → "No mappings for profile '{profile}'."; TOTAL HEADER MISMATCH — not one of the N mapped columns was found in the file's header row → fatal for every storage strategy; PK not mapped while STORAGE_STRATEGY = MergeUpsert → fatal; a column with IS_MANDATORY=true that no mapping can produce a value for → fatal. Each fatal one writes a multi-line "🔴 Fatal Error … Action Required" block naming the sheet and the cell to fix.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1461 — `if (SourceIntegrityGate.IsTotalHeaderMismatch(bindings, out int declaredHeaderBindings))`; :1494 — `if (context.Definition.STORAGE_STRATEGY == UpdateStrategy.MergeUpsert) { … hasFatalError = true; }`; :856 — `if (mappings == null || mappings.Count == 0) { … prep.EarlyResult = IngestionResult.Fail(…, $"No mappings for profile '{profile}'."); }`

### FAILURE MODE — how are individual bad CELLS handled by the TSV parser?

Three different behaviours, and the difference matters enormously for a validating Console. (1) ENUM cells (ENTITY_TYPE, LICENSE_TIER, STORAGE_STRATEGY, VIEW_MODE, BUSINESS_DOMAIN, SEMANTIC_ROLE, DATA_TYPE, SOURCE_TYPE, MATCH_MODE, MIN_LICENSE_REQ): `Enum.Parse` is allowed to THROW, the per-cell catch records a `FetchRowError` ("Cannot convert 'X' to {Type} for {Prop}"), and the property is left at its DECLARED DEFAULT — deliberately never enum value 0, because 0 for STORAGE_STRATEGY is ReplaceAll = delete-all. (2) NON-enum primitives (bool/int/decimal/DateTime/Guid) go through `SmartConverter.ChangeType`, which returns NULL on failure and does NOT throw — so `if (converted != null) prop.SetValue(...)` simply skips, NO error is recorded, and the property silently keeps its C# default. Concretely: IS_ACTIVE="Active" (not in the accepted bool set) leaves IS_ACTIVE at its default of TRUE with no error anywhere. (3) A whole ROW that throws is caught, recorded as a FetchRowError, and dropped. Empty cells are skipped entirely (declared default kept).

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:82 — `object converted = ConvertValue(raw, prop.PropertyType); if (converted != null) prop.SetValue(obj, converted);` … :164 `if (underlying.IsEnum) return Enum.Parse(underlying, NormalizeEnumAlias(raw), ignoreCase: true);` … :174 `return SmartConverter.ChangeType(raw, underlying);`

### What boolean spellings are accepted for IS_ACTIVE / IS_VISIBLE / IS_PK / IS_MANDATORY / IS_VIRTUAL / IS_DERIVED?

Case-insensitive. TRUE: 1, true, yes, y, on, نعم, صح, صحيح. FALSE: 0, false, no, n, off, لا, خطأ, غلط. Anything else is NOT an error — it is silently ignored and the property keeps its declared default (TableDefinition IS_ACTIVE/IS_VISIBLE default TRUE; SchemaRule IS_PK/IS_MANDATORY/IS_VIRTUAL/IS_DERIVED default false; DataSource IS_ACTIVE default TRUE). A Console drop-down should offer exactly TRUE/FALSE and reject free text, because a typo here fails OPEN, not closed.

**Accepted:** `1`, `true`, `yes`, `y`, `on`, `نعم`, `صح`, `صحيح`, `0`, `false`, `no`, `n`, `off`, `لا`, `خطأ`, `غلط`

**Blank means:** the property's declared C# default (IS_ACTIVE=true, IS_VISIBLE=true, IS_PK/IS_MANDATORY/IS_VIRTUAL/IS_DERIVED=false)

*certain* — mbiXaddin/Core/Utils/SmartConverter.cs:45 — `"1", "true", "yes", "y", "on", "نعم", "صح", "صحيح"`; :52 — `"0", "false", "no", "n", "off", "لا", "خطأ", "غلط"`

### What enum aliases does the loader silently normalise before parsing?

`TsvParser.NormalizeEnumAlias` upper-cases the raw cell and rewrites these BEFORE Enum.Parse, so they are legal input even though they are not enum member names: BOOLEAN→BOOL, STRING→TEXT, INTEGER→INT, NUMBER→DECIMAL, FLOAT→DECIMAL, DOUBLE→DECIMAL, VARCHAR→TEXT, NVARCHAR→TEXT, NUMERIC→DECIMAL, BIT→BOOL, CHAR→TEXT (all DATA_TYPE), and REPLACE→ReplaceAll, UPSERT→MergeUpsert, MERGE→MergeUpsert, INSERT→Append (STORAGE_STRATEGY). Everything else is passed through to `Enum.Parse(..., ignoreCase: true)`. A Console drop-down should offer the canonical enum names only, but must not REJECT these aliases if they already exist in the sheet.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:186 — `switch (raw.ToUpperInvariant()) { case "BOOLEAN": return "BOOL"; … case "INSERT": return "Append"; default: return raw; }`

### Does the add-in validate the config today — and does it refuse the whole workbook, skip the bad row, or fail at use time?

All three happen, at different layers, and NO layer refuses the whole workbook for a bad row. (1) FETCH layer — refuses a whole GENERATION only on transport failure or a degenerate 200-with-no-rows on the four critical sheets; falls back to the SQLite cache. (2) PARSE layer — per-cell (enum recorded as error + default kept; non-enum silently defaulted) and per-row (a throwing row is dropped). (3) SYNC-TIME batch validation — `ValidateAndAlertBatch` runs every entity's `Validate()` for all six sheets right after fetch, but is explicitly NON-FATAL: `catch (Exception ex) { … "Sync will continue without alerts for this batch." }`. Findings go to the developer log / ETL Inspector only. (4) PRE-INGEST gate — the only place a config problem actually STOPS something: `ValidateContext` skips the whole table's sync on any Error/Critical (see the earlier answer). (5) OFFLINE READ — `ReadEntities` rejects a ROW outright if its `Validate()` yields any Critical ("Row rejected (critical validation error)"); non-critical findings are accepted with a debug log. (6) FAIL-AT-USE — everything else: broken JSON bags resolve to a default config object, unknown JSON keys are ignored, a bad WHERE_FILTER blanks the sheet, a missing PARENT_KEY silently degrades to a root entity.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:884 — `_log.LogWarning($"[VALIDATE/{sourceTable}] Batch validation failed unexpectedly: {ex.Message}. " + "Sync will continue without alerts for this batch.", SourceName);`; MetadataOrchestrator.Tier1Schema.cs:601 — `if (hasCritical) { rejected++; _log.LogWarning($"[{tableName}] Row rejected (critical validation error): …"); continue; }`

### Which validation findings are Critical (row-rejecting on the offline read), and what are the severity levels?

Severities are Info=0, Warning=1, Error=2, Critical=3 (Validation.cs:32-45); `ValidationResult.Warn/Fail/Critical` map to Warning/Error/Critical. The CRITICAL findings — the ones that make `ReadEntities` drop the row on every offline load — are: TableDefinition: ENTITY_KEY blank, PARENT_KEY == ENTITY_KEY. SchemaRule: ENTITY_KEY blank, ATTRIBUTE_KEY blank. DataSource: SOURCE_KEY blank, TARGET_ENTITY_KEY blank, SOURCE_URI blank (this last one is SUPPRESSED on the offline read, because SOURCE_URI is deliberately never persisted — see SourceExcludeCols). DataMap: two Criticals (DataMapEntity.cs:238, :248 — PROFILE_KEY and TARGET_ATTRIBUTE_KEY). ExportView: two Criticals (ExportViewEntity.cs:310, :319 — VIEW_KEY and ENTITY_KEY). RibbonControl: two Criticals (RibbonControlEntity.cs:423, :498).

*certain* — mbiXaddin/Core/Validation/Validation.cs:166 — `public bool IsValid => !_results.Any(r => !r.IsValid && r.Severity >= ValidationSeverity.Error);`; Core/Entities/DataSourceEntity.cs:294 — `yield return ValidationResult.Critical(nameof(SOURCE_KEY), "[ERR_NULL] SOURCE_KEY is mandatory and cannot be empty. …")`

### Is there a schema/contract VERSION for the workbook, so the Console can refuse one it does not understand?

NO. There is no version cell, version column, version sheet, or version handshake anywhere in the six sheets — grepping for SCHEMA_VERSION / CONFIG_VERSION / CONTRACT_VERSION / WORKBOOK_VERSION / SHEET_VERSION across all 394 .cs files and docs/ returns nothing. The two things that look like versions are not: (a) `Tier1SchemaVersion = 8` is a LOCAL lever that forces a rebuild of the SQLite _SYS_* tables; the real trigger is a SHA-256 fingerprint over the guarded CREATE TABLE bodies stored in _SYS_SYNC_STATE[_TIER1_SCHEMA].SchemaHash — it describes the add-in's own DDL, never the sheet. (b) `VERSION_TAG` in the DataSource sheet is a per-source free-form change-detection token (any string — date, v4.2, hash), compared to skip an unchanged download. The workbook contract is implicit: it is whatever `[JsonProperty(...)]` names the six entity classes carry in the installed build. Practically the Console must version the workbook itself if it wants a refusal, and note the compatibility rule that IS enforced: an UNKNOWN column is ignored (safe to add), a MISSING column leaves its property at the declared default (safe to omit), header match is by name (case-insensitive, trimmed) so column ORDER is irrelevant — but a rename of a known column is a silent data loss.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.Tier1Schema.cs:76 — `private const int Tier1SchemaVersion = 8;` (its own doc: "Bump this only to force a rebuild WITHOUT a schema change"); Core/Entities/DataSourceEntity.cs:150 — `public string VERSION_TAG { get; set; }`

### How exactly are sheet columns bound to code, and what happens to columns the code does not know?

`TsvParser.BuildPropertyMap<T>` reflects over T's public instance properties, SKIPS any with `[JsonIgnore]`, and keys each by its `[JsonProperty("NAME")]` name (falling back to the CLR property name) into a case-INSENSITIVE dictionary. Header cells are trimmed, then looked up. Consequences the Console can rely on: column ORDER is irrelevant; header case is irrelevant; an UNKNOWN header is silently ignored; a MISSING header leaves the property at its declared default. This is why the five annotation columns in the live sheets — `Note` and `Drive` on DataSource, `Excel`, `File` and `Folder` on RibbonControls — load without complaint: no entity property matches them, so they are dropped at parse time (they also do not appear in SchemaGuardMap, so they raise no DEAD_COLUMN either). The parser also requires at least 2 lines (header + one row) or it returns an empty result.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:123 — `var byName = new Dictionary<string, System.Reflection.PropertyInfo>(StringComparer.OrdinalIgnoreCase);` … :143 `if (!string.IsNullOrWhiteSpace(header) && byName.TryGetValue(header, out var p)) map[i] = p;`

### What are the exception types involved in config loading, and where are they caught?

Only two are config-specific. (1) `MetadataFetchException` (MetadataFetch.cs:27) — thrown at MetadataOrchestrator.cs:303 and :308, caught at SyncManager.cs:480 → SQLite fallback. (2) `InvalidOperationException` — thrown by `SqlBuilderService.BuildCreateTable` ("has no persisted columns", :52) and `BuildSelectByPk` ("has no PK column", :190), caught and logged by `EnsureOperationalTable`; and thrown by `ExportEngine.EnsureRegistryReadyAsync` ("Data is still loading…" / "Table 'X' is not available…") and `ResolveContext` ("Entity 'X' not found in MetadataRegistry."), which propagate to ActionRouter and become the only config-caused DIALOGS a user sees: `DialogHelper.ShowError("Failed to export '{key}' to Excel.\n\nDetails: {ex.Message}", "Export Failed")` and `DialogHelper.ShowWarning($"'{entityKey}' was not updated.\n\n{result.FailReason}", "Update Skipped")`. Everywhere else in the load path is a total try/catch that degrades: `ConfigResolver.Resolve<T>` never throws and returns `new T()`, `EndpointCatalog.Parse` never throws and returns compiled defaults, `RunLinkIntegrityCheck` / `RunSchemaIntegrityCheck` / `ValidateAndAlertBatch` all swallow.

*certain* — mbiXaddin/UI/Commands/ActionRouter.cs:412 — `DialogHelper.ShowError($"Failed to export '{key}' to Excel.\n\n" + $"Details: {ex.Message}", "Export Failed");`; UI/Commands/ActionRouter.cs:442 — `DialogHelper.ShowWarning($"'{entityKey}' was not updated.\n\n{result.FailReason}", "Update Skipped");`

### What cross-reference problems does the loader detect but only WARN about (silent no-ops the Console should prevent)?

Seven, all log-only and none affecting the produced graph — these are the invisible failures a validating Console is worth the most against. `[ORPHAN_COLS]` SchemaRule rows whose ENTITY_KEY matches no active definition; `[ORPHAN_SRC]` DataSource rows whose TARGET_ENTITY_KEY matches no active definition ("These sources will never sync"); `[NO_MAPPING]` an active source whose PROFILE_KEY has no DataMap rows ("Table 'X' will be empty after sync"); `[DUPLICATE_SOURCE_KEY]` (logged at ERROR level, sync NOT aborted — "a duplicate can make a removed source delete another source's rows"); `[ERR_REF]` PARENT_KEY naming a non-existent entity ("Inheritance will be skipped"); `[LINK GUARD]` an EXPORT_CONFIG.LinkedEntities or VIEW_CONFIG link whose EntityKey is not registered, or whose ViewKey is not an ACTIVE view of that entity ("the full table is exported instead"); and `[ConfigResolver] [ERR_FORMAT]` a config bag that does not start with '{' or fails JObject.Parse ("Falling back to default"). PROFILE_KEY resolution is worth noting: blank or "DEFAULT" both resolve to the source's TARGET_ENTITY_KEY (`DataSourceEntity.ResolveProfileKey`), so a DataMap row for a blank-profile source must carry PROFILE_KEY = the entity key.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:620 — `$"[NO_MAPPING] Source '{src.SOURCE_KEY}' uses PROFILE_KEY='{profile}' but SYS_DATA_MAP has no mappings for this profile. Table '{src.TARGET_ENTITY_KEY}' will be empty after sync."`; Core/Entities/DataSourceEntity.cs:257 — `public string ResolveProfileKey() => (string.IsNullOrWhiteSpace(PROFILE_KEY) || string.Equals(PROFILE_KEY, "DEFAULT", StringComparison.OrdinalIgnoreCase)) ? TARGET_ENTITY_KEY : PROFILE_KEY;`

### Which sheets are treated as REGISTRY-CRITICAL versus OPTIONAL?

CRITICAL (4): TableDefinition (_SYS_DEFINITIONS), SchemaRule (_SYS_SCHEMA_RULES), DataSource (_SYS_DATA_SOURCES), DataMap (_SYS_DATA_MAP) — a failed fetch on any of these aborts the whole generation before anything is persisted. OPTIONAL (2): ExportViews and RibbonControls — on a failed fetch this run keeps the last-known cached rows (`viewsFresh` / `ribbonFresh`), passes NULL to the persist so their cached tables are left untouched rather than truncated, and continues. A Console can therefore treat an ExportViews or RibbonControls mistake as degrading only the ribbon/export menus, while a mistake in the other four sheets is a whole-workbook-generation risk.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:297 — `CollectCriticalFailure(criticalFailures, "SYS_DEFINITIONS", "_SYS_DEFINITIONS", rawDefs);` … :300 `CollectCriticalFailure(criticalFailures, "SYS_DATA_MAP", "_SYS_DATA_MAP", rawMaps);` :318 `bool viewsFresh = !rawViews.FetchFailed;`

### Is the SQLite persist of the config atomic, and can a partial write corrupt the cache?

No, it cannot. `PersistTier1ToSqlite` is all-or-nothing inside ONE transaction; if it cannot own a transaction it SKIPS entirely ("Cache left at the previous generation") rather than writing non-transactionally. Each table is truncate-then-refill via `PersistTable`, which throws if the truncate failed or if BulkInsert wrote 0 of N rows; a PARTIAL insert is tolerated and logged, because the insert is OR IGNORE so legitimately-duplicate PKs in a sheet must not nuke the run — meaning duplicate primary keys inside one sheet are DROPPED SILENTLY apart from a `[table] Partial insert: n/N rows (duplicates ignored by PK)` warning. On rollback the session still runs fully on the fresh in-memory data (BuildAndRegister always runs); only the freshness marker is withheld.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.Tier1Schema.cs:449 — `int inserted = _db.BulkInsert(tableName, rows); if (inserted == 0) throw new InvalidOperationException($"BulkInsert wrote 0/{rows.Count} rows into '{tableName}'.");`; :390 — `if (!_db.BeginTransaction()) { _log.LogError("TIER-1 persist SKIPPED: could not own a transaction …"); return false; }`


## the-datamap

### SOURCE_TYPE — complete accepted vocabulary, and what each value means

Exactly five values, from the C# enum MapSourceType: Header, Index, Context, Constant, Formula. Parsed by TsvParser via Enum.Parse(..., ignoreCase: true), so any casing works ("header", "HEADER"). Blank cell = property untouched = declared default Header. Meanings, taken from the runtime switch in ResolveRawValue (DataIngestionService.cs:1252-1273), NOT from the doc comments (they disagree — see below):
  • Header — value is read from the source row's cell at the column index resolved by matching SOURCE_EXPRESSION against the TSV header row (the ~90% case).
  • Index — value is read from cells[N] of the CURRENT row, i.e. a POSITIONAL COLUMN INDEX, 0-based. The XML doc and user guide both call it a "row number (metadata rows)" — that is wrong; the code indexes into the row's cells, never into the row list. Console should label it "column position", and must reject negative numbers (see the crash note in the Index question below).
  • Context — value comes from a closed 4-token runtime table (ResolveContextKey), NOT from arbitrary AddinState properties.
  • Constant — SOURCE_EXPRESSION is returned verbatim as the value for every row.
  • Formula — NOT IMPLEMENTED. It has no case in ResolveRawValue, so it falls into `default: return null` — every row gets null for that column, and if the target column is PK or IS_MANDATORY, EVERY ROW IS DROPPED (MapRow's critical-null gate, DataIngestionService.Mapping.cs:349-353). The Console should either not offer Formula or offer it with an explicit "not implemented — always yields NULL" warning.
There is also a parallel string table SystemConstants.SourceTypes (Header/Index/Context/Constant/Formula) that nothing in the mapping path reads — the enum is the authority.

**Accepted:** `Header`, `Index`, `Context`, `Constant`, `Formula`

**Blank means:** Header

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:38 `public enum MapSourceType` (members at :45 Header, :52 Index, :59 Context, :66 Constant, :73 Formula); default at :145 `public MapSourceType SOURCE_TYPE { get; set; } = MapSourceType.Header;`; runtime meaning at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1254 `switch (action.Map.SOURCE_TYPE)` … :1263 `case MapSourceType.Index: return int.TryParse(action.Map.SOURCE_EXPRESSION, out int idx) && idx < cells.Length ? cells[idx] : null;` … :1270 `default: return null;` (Formula falls here); mirror constants at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Constants/SystemConstants.cs:195-210

### MATCH_MODE — complete accepted vocabulary, what each does, and which SOURCE_TYPEs each is valid with

Exactly five values, from enum MapMatchMode: Exact, Contains, StartsWith, Regex, Fuzzy. Default Exact. All five are implemented in one switch, MappingHelpers.FindHeader, and every comparison is case-insensitive; the header cell is Trim()-ed first, SOURCE_EXPRESSION is NOT trimmed:
  • Exact (the switch's `default:`) — string.Equals(header, expr, OrdinalIgnoreCase).
  • Contains — header.IndexOf(expr, OrdinalIgnoreCase) >= 0.
  • StartsWith — header.StartsWith(expr, OrdinalIgnoreCase).
  • Regex — Regex.IsMatch(header, expr, RegexOptions.IgnoreCase). .NET regex syntax. An invalid pattern does NOT throw: it is logged and treated as no-match for every header (MappingHelpers.cs:84-91), which then surfaces as "header NOT FOUND". The Console should compile-test the pattern before saving.
  • Fuzzy — Levenshtein distance <= 2 (hard-coded tolerance, not configurable), after both sides are upper-cased, with an early-out when the length difference exceeds 2. First header within distance 2 wins, so it can silently bind the wrong column.
VALIDITY vs SOURCE_TYPE: MATCH_MODE is consumed ONLY for SOURCE_TYPE=Header — ResolveHeaderIndex returns -1 immediately for any other type (MappingHelpers.cs:63), so the value is dead for Index/Context/Constant/Formula. No combination is hard-rejected; a non-Exact MATCH_MODE on a non-Header row yields a Warning-level validation finding ("MATCH_MODE is only used when SOURCE_TYPE=Header") and is otherwise ignored. Console rule: when SOURCE_TYPE != Header, force/grey MATCH_MODE to Exact — anything else is a guaranteed warning with no effect.

**Accepted:** `Exact`, `Contains`, `StartsWith`, `Regex`, `Fuzzy`

**Blank means:** Exact

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:81 `public enum MapMatchMode` (:84 Exact, :87 Contains, :90 StartsWith, :93 Regex, :100 Fuzzy); default at :155; implementation C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/MappingHelpers.cs:75 `switch (mode)` … :106 `internal static bool IsFuzzyMatch(string a, string b, int tolerance = 2)`; Header-only gate at MappingHelpers.cs:63 `if (map.SOURCE_TYPE != MapSourceType.Header) return -1;`; warning at DataMapEntity.cs:265-273 `if (SOURCE_TYPE != MapSourceType.Header && MATCH_MODE != MapMatchMode.Exact) … ValidationResult.Warn`

### SOURCE_EXPRESSION — what syntax, and does it differ per SOURCE_TYPE? Real examples

Free string in the sheet; its meaning is entirely determined by SOURCE_TYPE. Per type:
  • Header → a TSV column header name, compared per MATCH_MODE. Examples from the code/tests: "Item Code", "Unit Price", "UOM"; with Regex mode a .NET pattern such as "^unit .*\\(sar\\)$" (MappingHelpersTests.cs:47) or "^Price.*SAR$"; Arabic headers are used too ("سعر الوحدة", DataMapEntity.cs:499). NOT trimmed before matching — leading/trailing spaces in the cell break Exact matching (the header side IS trimmed).
  • Index → a non-negative integer, 0-based, naming a COLUMN POSITION in the row ("0", "1", "2"). Validated: a non-integer or a negative value yields a Fail-level finding, but validation is advisory (logged/alerted, not blocking), and at runtime a negative value is a hard bug: int.TryParse("-1") succeeds and `-1 < cells.Length` is true, so `cells[-1]` throws IndexOutOfRangeException, which is caught one level up and rolls the whole source back with a generic "Streamed read/map failed" (DataIngestionService.cs:938-943). The Console MUST enforce integer >= 0.
  • Context → one of exactly 4 tokens (see the Context question). Anything else silently returns null.
  • Constant → the literal value, used verbatim for every row: "SAR", "0", "N/A", "ACTIVE".
  • Formula → documented as an arithmetic expression over other columns ("UNIT_PRICE * 1.15", "QTY * WEIGHT"), but no evaluator exists anywhere in the code; the value is always null.
No escaping/quoting syntax exists: the cell content is the expression, raw. Mandatory in practice — a blank SOURCE_EXPRESSION yields a Fail finding for every SOURCE_TYPE (the comment says "except Formula" but the check has no exemption).

**Blank means:** empty string; ValidationResult.Fail "is missing SOURCE_EXPRESSION" (advisory); Header→no index resolved→NULL, Constant→empty value

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:157-167 (per-type meaning) and :256-262 mandatory check, :276-285 `if (SOURCE_TYPE == MapSourceType.Index … !int.TryParse(SOURCE_EXPRESSION.Trim(), out int rowIdx) || rowIdx < 0)`; runtime at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1256-1272; regex example at C:/Users/User01/source/repos/mbiXaddin/tests/Core.Tests/MappingHelpersTests.cs:47

### SOURCE_TYPE=Context — what are the accepted SOURCE_EXPRESSION values?

A CLOSED list of 4 tokens, matched case-insensitively after Trim() and upper-casing, in DataIngestionService.ResolveContextKey: "SYNC_DATE" and "SYNCTIMESTAMP" (both → today's date, yyyy-MM-dd, InvariantCulture), "SYNCTIME" (→ yyyy-MM-dd HH:mm:ss), "CURRENTTIER" (→ the current license tier name, e.g. Free/Pro). Everything else returns null — including "CurrentCountry" and "CurrentUser", which the entity's own doc comments and the user guide advertise as examples (DataMapEntity.cs:57, :162, :501). Those two are documentation-only and produce NULL rows. The Console must offer a drop-down of exactly these four, not a free text box. Note the values are produced from DateTime.Now (local clock), pinned by a culture test.

**Accepted:** `SYNC_DATE`, `SYNCTIMESTAMP`, `SYNCTIME`, `CURRENTTIER`

**Blank means:** null value written to the column

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1275 `private string ResolveContextKey(string key)` … :1280-1284 `case "SYNC_DATE": case "SYNCTIMESTAMP": … case "SYNCTIME": … case "CURRENTTIER": … default: return null;`; contradicting docs at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:57 and :501; culture pin at C:/Users/User01/source/repos/mbiXaddin/tests/Core.Tests/SyncDateTokenCultureTests.cs:11

### TRANSFORM_CHAIN — the full list of implemented transforms, their arguments, and the chain separator

Separator is the pipe "|" (SystemConstants.Transforms.ChainSeparator). The chain is split with RemoveEmptyEntries, each command is Trim()-ed, then applied LEFT TO RIGHT; the parsed command array is memoized per chain string. Command names are matched case-insensitively (the switch upper-cases first), so "trim|upper" works. Arguments are appended after a colon: "NAME:arg1:arg2". Exactly TEN commands are implemented, in DataSanitizer.ApplySingle's switch (the same ten are listed in SystemConstants.Transforms and in DataMapEntity.Validate's knownCommands set):
  1. TRIM — no args. Trims a string; non-strings pass through.
  2. UPPER — no args. ToUpperInvariant.
  3. LOWER — no args. ToLowerInvariant.
  4. TO_DECIMAL — no args. SmartConverter.ToDecimal; tolerates thousands separators and currency symbols ("  1,234.56 $ " → 1234.56m). Unparseable → null.
  5. TO_INT — no args. Truncates toward zero ("12.7"→12, "-3.9"→-3). Unparseable → null.
  6. TO_DATE — no args. Returns a STRING in "yyyy-MM-dd", not a DateTime. Ambiguous slash dates are day-first ("05/06/2025" → "2025-06-05"). Unparseable → null.
  7. TO_BOOL — no args. Returns int 1/0 (accepts true/false/yes/no/1/0 and Arabic نعم/لا). Unparseable → null.
  8. ABS — no args. Absolute value; if the value cannot be parsed it returns the ORIGINAL value unchanged (not null).
  9. SUBSTRING:start[:length] — 1 or 2 integer args, 0-based start. start and length are clamped to the string; "SUBSTRING:10" on "ABC" → ""; a malformed arg ("SUBSTRING:x") leaves the value unchanged.
 10. JSON_EXTRACT:key — 1 arg, everything after the FIRST colon, case-sensitive as typed. Uses Newtonsoft JToken.SelectToken, so JSONPath works: "JSON_EXTRACT:Currency", "JSON_EXTRACT:addr.city", "JSON_EXTRACT:prices[0].amount". Integer→long, Float→decimal, Boolean→1/0, missing key or invalid JSON→null.
There is no registry/factory — the name→transform resolution is a single hard-coded string switch. Everything else listed in the file's roadmap (ROUND, REPLACE, MULTIPLY, DIVIDE, SPLIT, COALESCE, LOOKUP, MAP) is NOT implemented. An argument can never contain "|" (the split happens first) and SUBSTRING args are split on every ":".

**Accepted:** `TRIM`, `UPPER`, `LOWER`, `TO_DECIMAL`, `TO_INT`, `TO_DATE`, `TO_BOOL`, `ABS`, `SUBSTRING`, `JSON_EXTRACT`

**Blank means:** null/empty chain → raw string stored unchanged (ApplyTransformChain returns rawValue)

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Utils/DataSanitizer.cs:127 `switch (cmdName)` with cases at :130 TRIM, :133 UPPER, :136 LOWER, :140 TO_DECIMAL, :143 TO_INT, :146 TO_DATE, :149 TO_BOOL, :153 ABS, :157 SUBSTRING, :160 JSON_EXTRACT; separator at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Constants/SystemConstants.cs:316 `public const string ChainSeparator = "|";` (names at :298-313); parser at DataSanitizer.cs:93 `private static string[] ParseChain(string transformChain)`; behaviours pinned in C:/Users/User01/source/repos/mbiXaddin/tests/Core.Tests/DataSanitizerTests.cs:34,40,50,57,72,88,100-102,108-116,123-133

### What happens when a TRANSFORM_CHAIN name is unknown?

Nothing fails and nothing is dropped — the value passes through UNCHANGED and a warning is logged. Two separate layers see it:
  1. Fetch time: DataMapEntity.Validate splits the chain on "|", takes the text before the first ":" as the command name, and compares it case-insensitively against the ten known constants; an unknown name yields ValidationResult.Warn with code ERR_TRANSFORM ("uses unknown transform command '<X>'"). This is advisory — it becomes a log line / ETL alert, it does not block the sync.
  2. Run time: DataSanitizer.ApplySingle's `default:` branch. If an unknownCommandCallback was supplied it is called with the UPPER-CASED name and may substitute a value (returning null keeps the current value); the ingestion path supplies none, only logWarning, so the value is returned as-is with a warning naming the ten supported commands. Practical consequence for the Console: a typo like "TO_NUMBER" or "TRIM|toNumber" is silent data corruption of the useful kind — the raw text ("1,234.50") is stored where a number was expected, and the later DATA_TYPE cast may then store NULL. Worth blocking outright in the drop-down.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Utils/DataSanitizer.cs:164 `default:` … :174-180 `logWarning?.Invoke($"[{SystemConstants.ErrorCodes.UnknownTransform}] Unknown transform command: '{cmdName}'. … Value passed through unchanged.")`; fetch-time check at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:288-319 `if (!knownCommands.Contains(cmdName)) yield return ValidationResult.Warn(...)`; test at C:/Users/User01/source/repos/mbiXaddin/tests/Core.Tests/DataSanitizerTests.cs:147-155

### PROCESS_CONFIG — is it JSON, and exactly which keys does the code read?

Yes: a single JSON OBJECT, inline in the cell. It must start with '{' — anything else (including the retired "$preset" reference form) is logged as ERR_FORMAT and the whole bag falls back to defaults. It is deserialized once by ConfigResolver into MapProcessConfig; the class has exactly FIVE properties and the ingestion path reads all five:
  • "NullStrategy" (string) — one of Skip | UseDefault | Fail. Default "Skip".
  • "DefaultValue" (string) — the substitute used when a UseDefault strategy fires. Default null. Example "0", "USD", "1900-01-01".
  • "ErrorStrategy" (string) — same three values; applied when the transform chain THROWS. Default "Skip".
  • "AutoTrim" (bool) — trims the raw value before the chain. Default TRUE (so trimming happens even with no TRIM in the chain).
  • "RowFilter" (string) — "OPERATOR" or "OPERATOR:value"; a non-match DROPS THE WHOLE ROW. Default null.
Example from the tests: {"NullStrategy":"UseDefault","DefaultValue":"0"} and {"RowFilter":"IN:EG,SA,AE"}. Two Console-relevant sharp edges: (a) the unknown-key check is EXACT-CASE (ordinal HashSet), so "nullstrategy" is flagged as an unknown key with a "did you mean" hint even though Newtonsoft would still bind it; (b) a wrong JSON TYPE for a key (e.g. "AutoTrim":"yes") makes ToObject<T> throw and the ENTIRE bag reverts to defaults, not just that key. The SystemConstants.ConfigKeys block that mentions PROCESS_CONFIG keys "Default"/"Critical"/"CustomRegex"/"LookupTableKey" (SystemConstants.cs:278-282) is dead — grep shows zero references; do not offer those.

**Accepted:** `NullStrategy`, `DefaultValue`, `ErrorStrategy`, `AutoTrim`, `RowFilter`

**Blank means:** NullStrategy=Skip, ErrorStrategy=Skip, AutoTrim=true, DefaultValue=null, RowFilter=null

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:354 `public sealed class MapProcessConfig` (:361 NullStrategy="Skip", :367 DefaultValue, :374 ErrorStrategy="Skip", :381 AutoTrim=true, :396 RowFilter); reads at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:276 `if (cfg.AutoTrim && raw != null) raw = raw.Trim();`, :281 `switch (cfg.NullStrategy)`, :313 `switch (cfg.ErrorStrategy)`, :338 `if (!string.IsNullOrEmpty(cfg.RowFilter))`; must-be-JSON gate at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Configuration/ConfigResolver.cs:73 `if (!trimmed.StartsWith("{"))`; exact-case key check at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Configuration/ConfigValidator.cs:192 `new HashSet<string>(StringComparer.Ordinal)`

### PROCESS_CONFIG.NullStrategy / ErrorStrategy — accepted values, and a case-sensitivity trap

Vocabulary is exactly three, from ConfigVocabulary.MapStrategies: "Skip", "UseDefault", "Fail".
  • Skip (default) — the value stays null and the row is kept.
  • UseDefault — substitute DefaultValue. If DefaultValue is unset, validation warns that affected values fall back to an empty default.
  • Fail — for NullStrategy, the row is dropped ONLY if the target column is critical (IS_PK or IS_MANDATORY); for a non-critical column "Fail" does nothing at all. For ErrorStrategy, "Fail" drops the row unconditionally.
TRAP the Console must respect: validation accepts these case-INSENSITIVELY (ConfigValidator.ValidateAllowed uses OrdinalIgnoreCase) but the runtime is a C# string switch, i.e. case-SENSITIVE ordinal. So {"NullStrategy":"usedefault"} passes validation with no finding and then silently behaves as Skip. Emit exactly "Skip" / "UseDefault" / "Fail". The same exact-case assumption is baked into MapProcessConfig.Merge (`if (NullStrategy == "Skip")`).

**Accepted:** `Skip`, `UseDefault`, `Fail`

**Blank means:** Skip

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Configuration/ConfigVocabulary.cs:40-41 `public static readonly IReadOnlyList<string> MapStrategies = new[] { "Skip", "UseDefault", "Fail" };`; case-sensitive runtime at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:281-294 `switch (cfg.NullStrategy) { case "UseDefault": … case "Fail": if (action.IsCritical) … return null;` and :313-322; case-insensitive validation at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Configuration/ConfigValidator.cs:99 `if (allowed.Any(a => string.Equals(a, value, StringComparison.OrdinalIgnoreCase))) yield break;`

### PROCESS_CONFIG.RowFilter — accepted operators and syntax

Format "OPERATOR" or "OPERATOR:value", split on the FIRST colon at position > 0; the operator is upper-cased before the switch, so it is case-insensitive; the value part is Trim()-ed. Twelve operators, implemented in MappingHelpers.EvaluateRowFilter and mirrored in ConfigVocabulary.RowFilterOperators: EQ, NEQ, GT, LT, GTE, LTE, CONTAINS, NOT_CONTAINS, NOT_EMPTY, EMPTY, IN, NOT_IN. Semantics: true = KEEP the row, false = DROP THE ENTIRE ROW (not just the cell). EQ/NEQ/CONTAINS/NOT_CONTAINS are string comparisons, case-insensitive; GT/LT/GTE/LTE parse BOTH sides as invariant decimals and return false (drop) if either side fails to parse; IN/NOT_IN split the value on commas and trim each item ("IN:EG,SA,AE"); NOT_EMPTY/EMPTY take no value. The filter is evaluated on the value AFTER the transform chain and AFTER the DATA_TYPE cast. An unknown operator returns true (keeps every row) — a silently inert filter — and is flagged at fetch time as a Warning with the consequence spelled out and a "did you mean" suggestion.

**Accepted:** `EQ`, `NEQ`, `GT`, `LT`, `GTE`, `LTE`, `CONTAINS`, `NOT_CONTAINS`, `NOT_EMPTY`, `EMPTY`, `IN`, `NOT_IN`

**Blank means:** no filter — every row kept

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/MappingHelpers.cs:123 `internal static bool EvaluateRowFilter(object value, string filter)` with the operator switch at :144-181; vocabulary at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Configuration/ConfigVocabulary.cs:36-37; unknown-operator warning at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Configuration/ConfigValidator.cs:114-129 ("the filter is ignored and every row is kept"); row-drop wiring at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:338-345

### What happens when SOURCE_EXPRESSION names a column the source does not have?

Four escalating outcomes, none of which is an exception:
  1. Per-mapping: ResolveHeaderIndex returns -1 and BuildExecutionPlan logs an ERROR naming the expected header, the MATCH_MODE and the full list of headers actually found ('[MAPPING ERROR] … expects header 'X' (Mode=Exact) but it was NOT FOUND. Found columns: [...]'). The mapping stays in the plan.
  2. Per-cell: ResolveRawValue returns null → NullStrategy applies (Skip = column stored NULL; UseDefault = DefaultValue; Fail = row dropped only if the column is PK/mandatory). A final critical-null gate drops the row if a PK/mandatory column ended up null.
  3. Per-column, fatal: if the column is IS_MANDATORY and its binding never resolved, ValidateMappingCompleteness returns false and the SOURCE IS REJECTED before any write — with a message that distinguishes "no SYS_DATA_MAP row exists" from "a row exists but its SOURCE_EXPRESSION matches nothing in the file".
  4. Whole-source, fatal: if the profile declares N header-bound mappings and NOT ONE resolves, SourceIntegrityGate.IsTotalHeaderMismatch fires and the sync is aborted with nothing changed (this is the guard against a wrong tab / an HTML page returned with 200).
Separately, a TARGET_ATTRIBUTE_KEY that does not exist in SchemaRule is not an error at all: BuildExecutionPlan drops the mapping with a yellow 'Orphan mapping' warning and continues.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:89-97 `if (action.SourceIndex < 0 && map.SOURCE_TYPE == MapSourceType.Header) … "[MAPPING ERROR] … but it was NOT FOUND. Found columns: [{availableHeaders}]"`; orphan target at :56-69; mandatory-column fatal at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1531-1565 and the return at :1586 `return !hasFatalError;`; total mismatch at :1461 `if (SourceIntegrityGate.IsTotalHeaderMismatch(bindings, out int declaredHeaderBindings))` and C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/SourceIntegrityGate.cs:174-188

### PROFILE_KEY — what value must a DataMap row carry to be found?

The DataMap rows are indexed by their PROFILE_KEY verbatim (case-insensitive lookup), and the ingestion path looks them up by the SOURCE's RESOLVED profile key: DataSourceEntity.ResolveProfileKey() returns TARGET_ENTITY_KEY when the source's PROFILE_KEY is blank OR literally "DEFAULT", otherwise the custom PROFILE_KEY verbatim. Consequence the Console must encode: a DataMap row whose PROFILE_KEY is "DEFAULT" is a DEAD ROW unless some entity is literally named DEFAULT — for a source with a blank or "DEFAULT" profile, the DataMap rows must carry the ENTITY_KEY (e.g. PROFILE_KEY=T_SA_Aramco). The entity's own doc comment offers "DEFAULT" as an example (DataMapEntity.cs:121), which is misleading. So the correct drop-down for DataMap.PROFILE_KEY is the set of RESOLVED profile keys over DataSource rows: {PROFILE_KEY if set and != DEFAULT, else TARGET_ENTITY_KEY}. A profile with zero mapping rows aborts that source ("No mappings for profile 'X'") and is warned about at metadata load ([NO_MAPPING]).

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataSourceEntity.cs:257-261 `public string ResolveProfileKey() => (string.IsNullOrWhiteSpace(PROFILE_KEY) || string.Equals(PROFILE_KEY, "DEFAULT", …)) ? TARGET_ENTITY_KEY : PROFILE_KEY;`; index built verbatim at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:555-557 `allMaps.Where(m => … ).ToLookup(m => m.PROFILE_KEY, StringComparer.OrdinalIgnoreCase)`; lookup by resolved key at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:853-864

### Is (PROFILE_KEY, TARGET_ATTRIBUTE_KEY) unique? What happens with duplicate rows?

No — it is NOT enforced as a unique key. FullKey (PROFILE_KEY + "." + TARGET_ATTRIBUTE_KEY) is only used for message text. The only de-duplication is a three-part signature PROFILE_KEY|TARGET_ATTRIBUTE_KEY|SOURCE_EXPRESSION: an exact triple repeat is collapsed, but two rows with the same profile and the same target and DIFFERENT expressions both survive into the plan. Both are then executed in sheet order and both assign row[colKey] — the LAST one wins for the stored value, while BOTH rows' RowFilter conditions still apply to the row (either can drop it). The Console should treat a duplicate (PROFILE_KEY, TARGET_ATTRIBUTE_KEY) as an error to prevent, since the winning row depends on sheet ordering.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:749-753 `string sig = $"{profile}|{map.TARGET_ATTRIBUTE_KEY}|{map.SOURCE_EXPRESSION}"; if (seenSigs.Add(sig)) myMaps.Add(map);`; last-wins assignment at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:355 `row[colKey] = value;`; FullKey at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:215

### TARGET_ATTRIBUTE_KEY — what does the code accept, and how is it cleaned?

Free string, but silently rewritten before use: SanitizeKey Trim()s it and replaces every internal space with an underscore, logging a yellow warning each time ('Field ... contains internal spaces ... Auto-corrected'). The cleaned value is then looked up case-insensitively against SchemaRule.ATTRIBUTE_KEY; no match = the mapping is dropped with an 'Orphan mapping' warning and the column is simply never written. Mandatory (Critical finding if blank). Console rule: the drop-down should be the ATTRIBUTE_KEY list of the entity that the profile's source targets, with no spaces allowed — do not rely on the auto-correct.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1401-1433 `private static string SanitizeKey(...)` … :1412 `cleaned = cleaned.Replace(" ", "_");`; call site at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:48-51; mandatory check at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Core/Entities/DataMapEntity.cs:246-253

### How is a DataMap sheet cell actually turned into these typed values (enum parsing, blanks, bad values)?

TsvParser maps a TSV header name to the property whose [JsonProperty] name matches (case-insensitive), then converts. Rules a Console must respect:
  • A blank/whitespace cell is SKIPPED entirely — the property keeps its declared default (SOURCE_TYPE=Header, MATCH_MODE=Exact). Blank never means "enum value 0 by accident", but for these two enums the default happens to be member 0 anyway.
  • Enums are parsed with Enum.Parse(..., ignoreCase: true). That accepts far more than the member names: the underlying NUMBER ("2" → Context), an out-of-range number ("9" → an undefined MapSourceType that hits ResolveRawValue's `default: return null`), and comma-separated combinations. None of these throw, so the Console must restrict the cell to the exact member names.
  • A genuinely invalid enum string throws inside the per-cell try, is recorded in FetchResult.Errors, and the property is left at its declared DEFAULT (deliberate: never silently coerced to 0).
  • The alias table NormalizeEnumAlias contains no MapSourceType/MapMatchMode aliases — only data-type and update-strategy ones — so "Const", "Literal", "StartWith" etc. are all rejected.
  • JSON bag columns (PROCESS_CONFIG) are NOT parsed here; the raw string is stored and resolved later by ConfigResolver.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:78 `if (string.IsNullOrEmpty(raw)) continue;`, :164-165 `if (underlying.IsEnum) return Enum.Parse(underlying, NormalizeEnumAlias(raw), ignoreCase: true);`, :168-169 (class bags skipped), :182-208 NormalizeEnumAlias, and the file header at :8-10 ("A genuinely invalid enum/value is recorded as an error and the property is left at its declared default")

### What is the full order of operations MapRow applies to one cell? (what the Console's rules must be consistent with)

Per mapping, in this exact order: (1) masked-column gate — a licence-gated column writes the teaser text and skips everything else; (2) ResolveRawValue by SOURCE_TYPE; (3) AutoTrim; (4) NullStrategy if the raw is null/empty; (5) TRANSFORM_CHAIN — note it runs ONLY if the raw is non-empty, so a chain can never manufacture a value from nothing, and ErrorStrategy only fires on a THROWN exception, not on a transform that returns null (TO_DECIMAL of "N/A" quietly yields NULL and is reported as a ConvertFailed/'stored as NULL' aggregate, not as an error); (6) DATA_TYPE cast via SmartConverter.ParseToDbValue using the SchemaRule DATA_TYPE — this can turn a non-empty value into NULL; (7) RowFilter, evaluated on the post-cast value, dropping the whole row; (8) critical-null gate — null in a PK/mandatory column drops the row. A row where every column ended up dropped/empty is itself dropped as NO_VALUES_PRODUCED.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:260-363 — :265 masked, :272 ResolveRawValue, :276 AutoTrim, :279-295 NullStrategy, :299-324 `if (!string.IsNullOrEmpty(raw)) { try { value = DataSanitizer.ApplyTransformChain(...) } catch { … switch (cfg.ErrorStrategy) …` , :327-335 cast + RecordConvertFail, :338-345 RowFilter, :349-353 critical null, :362 NO_VALUES_PRODUCED

### Does any of the DataMap validation actually block a bad row, or is it advisory?

Advisory. DataMapEntity.Validate's findings (Critical/Fail/Warn) are collected by the ValidationOrchestrator at metadata-fetch time and turned into log lines and persistent ETL alerts — ValidateAndAlertBatch logs a summary and per-field findings and returns void; nothing filters the invalid rows out of the graph. The only things that actually STOP a sync are the ingestion-time gates: no mappings for the profile, a mandatory column whose binding did not resolve, a PK unmapped under MergeUpsert, and total header mismatch. This is precisely why the Console's own drop-downs and validation matter: for SOURCE_TYPE/MATCH_MODE/TRANSFORM_CHAIN/PROCESS_CONFIG, a wrong value reaches production as a warning plus wrong data, not as a refusal.

*certain* — C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:841-871 `private void ValidateAndAlertBatch<T>(…)` (logs only; called at :344 `ValidateAndAlertBatch(rawMaps.Valid, "SYS_DATA_MAP");`); blocking gates at C:/Users/User01/source/repos/mbiXaddin/mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:856-876 and :1440-1586


## the-schema-rule

### SEMANTIC_ROLE — what is the complete accepted vocabulary, and where is it defined?

A C# enum `SemanticRole` with exactly 24 members. It is parsed by name, case-insensitively (Enum.Parse ignoreCase:true), so "price", "PRICE", "Price" all bind. WARNING for the Console: Enum.Parse also accepts NUMERIC strings — "3" binds to TOTAL, and an out-of-range number like "99" binds to an undefined enum value WITHOUT throwing. The drop-down must offer only these 24 names and must reject digits. Note the legacy constant class `SystemConstants.SemanticRoles` (SystemConstants.cs:154-168) lists only 11 of the 24 (no MENU_*, no EXPORT_GROUP, no MENU_FACET) — it is DEAD CODE (no `SemanticRoles.` reference exists anywhere in the solution) and must NOT be used as the vocabulary source. The doc-panel list at SchemaGuidePanel.cs:330-331 is likewise stale (11 values).

**Accepted:** `NONE`, `PRICE`, `QTY`, `TOTAL`, `UNIT`, `NAME`, `CONV_SOURCE`, `CONV_TARGET`, `CONV_FACTOR`, `CONV_DATE_START`, `CONV_DATE_END`, `MENU_KEY`, `MENU_LABEL`, `MENU_SCREENTIP`, `MENU_SUPERTIP`, `MENU_ICON`, `MENU_ACTION`, `MENU_URL`, `MENU_DRIVE_URL`, `MENU_FORMAT`, `MENU_ORDER`, `MENU_GROUP`, `EXPORT_GROUP`, `MENU_FACET`

**Blank means:** NONE

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:40-173 — `public enum SemanticRole {` … members at :43 NONE, :46 PRICE, :49 QTY, :52 TOTAL, :55 UNIT, :58 NAME, :61 CONV_SOURCE, :64 CONV_TARGET, :67 CONV_FACTOR, :70 CONV_DATE_START, :73 CONV_DATE_END, :81 MENU_KEY, :84 MENU_LABEL, :87 MENU_SCREENTIP, :90 MENU_SUPERTIP, :93 MENU_ICON, :96 MENU_ACTION, :99 MENU_URL, :104 MENU_DRIVE_URL, :107 MENU_FORMAT, :110 MENU_ORDER, :117 MENU_GROUP, :136 EXPORT_GROUP, :162 MENU_FACET. Binding: SchemaRuleEntity.cs:281-283 `[JsonProperty("SEMANTIC_ROLE")] [JsonConverter(typeof(StringEnumConverter))] public SemanticRole SEMANTIC_ROLE { get; set; } = SemanticRole.NONE;`. Parse: TsvParser.cs:164-165 `if (underlying.IsEnum) return Enum.Parse(underlying, NormalizeEnumAlias(raw), ignoreCase: true);`

### SEMANTIC_ROLE — what does each role actually DO at runtime?

Three families. (1) ENGINE/COST roles — PRICE, QTY, TOTAL, UNIT, NAME: resolved via ctx.GetColumnByRole; PRICE/QTY/CONV_FACTOR/CONV_SOURCE/CONV_TARGET additionally get a CREATE INDEX. (2) CONVERSION roles — CONV_SOURCE, CONV_TARGET, CONV_FACTOR, CONV_DATE_START, CONV_DATE_END: required on a table whose ENTITY_TYPE makes IsConversionTable true. (3) MENU/EXPORT roles — MENU_KEY (row key passed to the action; falls back to the PK column), MENU_LABEL (button text), MENU_SCREENTIP / MENU_SUPERTIP (tooltips), MENU_ICON, MENU_ACTION (the routed action string), MENU_URL (direct download URL, used as-is), MENU_DRIVE_URL (Drive share link converted to uc?export=download), MENU_FORMAT (file extension + app to open with — authoritative, not guessed), MENU_ORDER (sort within deepest group; missing/invalid sorts last), MENU_GROUP (one nested sub-menu level per tagged column), EXPORT_GROUP (one export-tree level per tagged column; distinct values become menu items), MENU_FACET (tick-row attribute filter, never a tree level). NOTE: NONE is also stored in the ColumnByRole dictionary, so GetColumnByRole(NONE) returns the first untagged column — harmless but not a null.

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\UI\Commands\LibraryMenuBuilder.cs:211-241 (ResolveRoles: KeyCol = MENU_KEY ?? PrimaryKeyColumn; UrlCol = MENU_URL ?? MENU_DRIVE_URL; GroupCols/FacetCols ordered by ORDINAL_POS); UI\Commands\ActionRouter.cs:302-341 (MENU_URL preferred, else MENU_DRIVE_URL with ConvertDriveUrl=true; MENU_FORMAT → FormatColumn; MENU_GROUP → folder hierarchy); UI\Commands\ExportTreeMenuBuilder.cs:88-116 (EXPORT_GROUP levels, MENU_ORDER, MENU_FACET); Infrastructure\Database\SqlBuilderService.cs:117-121 (index on PRICE/QTY/CONV_FACTOR/CONV_SOURCE/CONV_TARGET); Core\Models\TableMetadataContext.cs:169-173 (ColumnByRole incl. NONE)

### SEMANTIC_ROLE — are any roles MANDATORY for an entity to work?

Yes, conditionally — never unconditionally. (a) A CONVERSION table (Definition.IsConversionTable) MUST have CONV_SOURCE, CONV_TARGET and CONV_FACTOR — each missing one is a Fail. (b) A COST table SHOULD have PRICE — Warn. (c) A LIBRARY entity (ENTITY_TYPE=LIBRARY or any MENU_KEY/MENU_URL/MENU_DRIVE_URL/MENU_LABEL tag present) MUST have MENU_KEY or a PK column — Fail; SHOULD have MENU_URL or MENU_DRIVE_URL — Warn (without it nothing can download); SHOULD have MENU_LABEL — Warn (falls back to file name then key). (d) An export-tree menu is hard-blocked without at least one EXPORT_GROUP column — the menu renders "No documents available". (e) MENU_ACTION has NO default: rows without it render disabled deliberately. IMPORTANT: none of these Fails abort the sync — they are log/alert only (AssembleContext validates "log only").

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Models\TableMetadataContext.cs:404-423 (conversion roles → ValidationResult.Fail), :426-431 (cost PRICE → Warn), :435-457 (LIBRARY MENU_KEY-or-PK Fail; MENU_URL/MENU_DRIVE_URL Warn; MENU_LABEL Warn); UI\Commands\ExportTreeMenuBuilder.cs:93-107 (`if (groupCols.Count == 0) … Unavailable`); UI\Commands\LibraryMenuBuilder.cs:434-452 (WarnAboutMissingActions — "There is deliberately no default action"); Infrastructure\Services\Sync\Metadata\MetadataOrchestrator.cs:704-708 (`// ── 8. Validate (log only) ──`)

### SEMANTIC_ROLE — which roles are repeatable and which are mutually exclusive?

Exactly THREE roles are repeatable per entity: MENU_GROUP, EXPORT_GROUP and MENU_FACET — tag several columns and each becomes one level / one facet block, ordered by ORDINAL_POS. Every other role is SINGULAR: the first column (in ORDINAL_POS order) wins and the rest are silently ignored, with a Warn emitted for the 10 explicitly-listed menu roles only. No role pair is hard mutually exclusive, but MENU_URL and MENU_DRIVE_URL are effectively exclusive in behaviour: if both are tagged MENU_URL wins and the Drive column is never converted. Engine roles (PRICE, QTY, TOTAL, UNIT, NAME, CONV_*) are singular by the same first-wins dictionary but get NO duplicate warning at all — two PRICE columns is silent.

**Accepted:** `MENU_GROUP (repeatable)`, `EXPORT_GROUP (repeatable)`, `MENU_FACET (repeatable)`

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Models\TableMetadataContext.cs:169-173 (`if (!byRole.ContainsKey(col.SEMANTIC_ROLE)) byRole[col.SEMANTIC_ROLE] = col;` over the ORDINAL_POS-sorted list at :131-133 → first wins), :459-478 (singularRoles = MENU_KEY, MENU_LABEL, MENU_URL, MENU_DRIVE_URL, MENU_SCREENTIP, MENU_SUPERTIP, MENU_ICON, MENU_ACTION, MENU_FORMAT, MENU_ORDER → Warn if >1; comment at :460 "MENU_GROUP is intentionally excluded — it is the one repeatable role"); SchemaRuleEntity.cs:112-117 (MENU_GROUP "the ONLY repeatable menu role"), :136 EXPORT_GROUP "the second repeatable role", :156-157 MENU_FACET "Repeatable, like the two grouping roles"; UI\Commands\ActionRouter.cs:302-310 (MENU_URL preferred over MENU_DRIVE_URL)

### DATA_TYPE — what is the complete accepted vocabulary?

A C# enum `ColumnDataType` with exactly 10 members. Parsed case-insensitively. The metadata parser ALSO normalises 11 typed aliases before parsing, so these extra spellings are accepted and silently rewritten: BOOLEAN→BOOL, BIT→BOOL, STRING→TEXT, VARCHAR→TEXT, NVARCHAR→TEXT, CHAR→TEXT, INTEGER→INT, NUMBER→DECIMAL, FLOAT→DECIMAL, DOUBLE→DECIMAL, NUMERIC→DECIMAL. Same numeric-string hazard as SEMANTIC_ROLE: "3" binds to BOOL and "42" binds to an undefined value without error. Same 10 values are mirrored (as strings) in SystemConstants.DataTypes, which IS live — it keys SmartConverter's DB-value converter table.

**Accepted:** `TEXT`, `DECIMAL`, `INT`, `BOOL`, `DATE`, `DATETIME`, `GUID`, `JSON`, `PERCENTAGE`, `BLOB`

**Blank means:** TEXT

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:179-215 — `public enum ColumnDataType {` :182 TEXT, :185 DECIMAL, :188 INT, :191 BOOL, :194 DATE, :197 DATETIME, :200 GUID, :203 JSON, :206 PERCENTAGE, :209 BLOB. Binding at :290-292 `[JsonProperty("DATA_TYPE")] … = ColumnDataType.TEXT;`. Aliases: Infrastructure\Services\Sync\Metadata\TsvParser.cs:186-198. Constants mirror: Core\Constants\SystemConstants.cs:174-186

### DATA_TYPE — how is each type parsed/coerced, and what SQLite type does it become?

Two independent consumers. (1) DDL — SqlBuilderService.MapToSqliteType: INT and BOOL → INTEGER; DECIMAL and PERCENTAGE → NUMERIC; BLOB → BLOB; everything else (TEXT, DATE, DATETIME, GUID, JSON) → TEXT. (2) Ingestion — SmartConverter.ParseToDbValue, keyed on the DATA_TYPE string: DECIMAL/PERCENTAGE/NUMERIC → decimal (handles 1,234.56 / 1.234,56 / Arabic-Indic digits / currency symbols ﷼ $ € £ ¥); INT/INTEGER → int (falls back to rounding a decimal, so 3.7 becomes 4); BOOL/BOOLEAN → 1/0 accepting ONLY the sets {1,true,yes,y,on,نعم,صح,صحيح} and {0,false,no,n,off,لا,خطأ,غلط}; DATE → "yyyy-MM-dd"; DATETIME → "yyyy-MM-dd HH:mm:ss" (8 explicit formats tried first, dd/MM before MM/dd, then invariant TryParse); GUID → canonical Guid string; TEXT, JSON, BLOB and any unrecognised type name fall through to the raw trimmed text. Excel-side defaults also key off DATA_TYPE: default column widths (DECIMAL/PERCENTAGE 14, INT 10, BOOL 8, DATE 12, DATETIME 18, GUID 22, JSON 30, else 16), default number formats ("#,##0.00", "0.00%", "#,##0", "dd/MM/yyyy", "dd/MM/yyyy HH:mm", "@"), default alignment (numeric right, BOOL centre, else left).

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Infrastructure\Database\SqlBuilderService.cs:576-587 (MapToSqliteType); Core\Utils\SmartConverter.cs:219-258 (ParseToDbValue + DbValueConverters dictionary), :42-53 (TrueValues/FalseValues sets), :56-66 (DateFormats), :318-376 (ToDecimal); Infrastructure\Engines\ExportEngine.cs:805-847 (GetDefaultWidth / GetDefaultFormat / GetDefaultAlignment)

### DATA_TYPE — what happens to a data value that does NOT parse? Row dropped, cell blanked, or table failed?

CELL BLANKED (stored as NULL) by default — the row survives and the table loads. ParseToDbValue returns null, the failure is recorded per-column and surfaced afterwards as ONE aggregated warning per column ("N value(s) could not be parsed as X and were stored as NULL"). EXCEPTION — the row IS dropped if that column is 'critical', which means IS_PK=true OR IS_MANDATORY=true: the critical-null check returns null for the whole row. SECOND ESCALATION — if EVERY row of a source is dropped this way while raw rows were parsed, the whole source write is rolled back and nothing is committed. Also note the metadata sheet itself behaves differently: an unparseable SEMANTIC_ROLE/DATA_TYPE cell throws inside Enum.Parse, is caught per-cell, recorded in FetchResult.Errors, and the property keeps its DECLARED DEFAULT (never enum value 0) — the SchemaRule row is still kept and used. So a typo'd DATA_TYPE silently makes the column TEXT.

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Infrastructure\Services\Ingestion\DataIngestionService.Mapping.cs:327-335 (`value = SmartConverter.ParseToDbValue(...)`; `if (value == null && !string.IsNullOrEmpty(beforeCast)) diag?.RecordConvertFail(...)`), :349-353 (`if (value == null && action.IsCritical) { LogError(... "NULL_CRITICAL_FINAL" ...); return null; }`), :84 (`IsCritical = col != null && (col.IS_PK || col.IS_MANDATORY)`), :211-215 (aggregated "stored as NULL" warning); DataIngestionService.cs:422-431 (zero-valid-rows → rebuild rolled back); TsvParser.cs:80-93 + :157-165 (metadata path: error recorded, declared default kept); verified by test tests\Core.Tests\TsvParserTests.cs:51-59

### How is a BLANK cell read for every SchemaRule column?

A blank (or whitespace-only) cell is SKIPPED entirely by the parser — the property is never assigned and keeps its C# declared default. There is no error, no warning. So: ENTITY_KEY→"" (then Critical), ATTRIBUTE_KEY→"" (then Critical), DISPLAY_HEADER→"" (Fail, but the export falls back to ATTRIBUTE_KEY), ORDINAL_POS→0, LICENSE_TIER→Free, SEMANTIC_ROLE→NONE, DATA_TYPE→TEXT, IS_PK→false, IS_MANDATORY→false, IS_VIRTUAL→false, IS_DERIVED→false, IS_VISIBLE→TRUE (the only flag whose blank default is true), UX_CONFIG→null, LOGIC_CONFIG→null. TRAP for the Console: for the four bool flags, a NON-blank but unrecognised value (e.g. "Y3S", "TRUE!", "1.0") does NOT throw — SmartConverter.IsTrue returns null, ChangeType returns null, and TsvParser only assigns when the conversion is non-null, so the flag silently keeps its default and NO error is recorded. Booleans must therefore be constrained to the accepted word lists by the drop-down; a typo is invisible.

**Accepted:** `1`, `true`, `yes`, `y`, `on`, `نعم`, `صح`, `صحيح`, `0`, `false`, `no`, `n`, `off`, `لا`, `خطأ`, `غلط`

**Blank means:** IS_VISIBLE=true; IS_PK/IS_MANDATORY/IS_VIRTUAL/IS_DERIVED=false; ORDINAL_POS=0; SEMANTIC_ROLE=NONE; DATA_TYPE=TEXT; LICENSE_TIER=Free

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Infrastructure\Services\Sync\Metadata\TsvParser.cs:77-78 (`string raw = cells[j]?.Trim(); if (string.IsNullOrEmpty(raw)) continue;`), :82-83 (`object converted = ConvertValue(raw, prop.PropertyType); if (converted != null) prop.SetValue(obj, converted);` — a null conversion is silently ignored); Core\Utils\SmartConverter.cs:140-144 + :293-304 (IsTrue returns null for anything outside the two sets, no throw); declared defaults at Core\Entities\SchemaRuleEntity.cs:237, 244, 255, 262, 270, 283, 292, 300, 349, 358, 367, 375

### IS_PK — does the code require exactly one, at least one, or allow none?

NONE is allowed and never blocks anything at metadata level — it produces a WARNING only ("MergeUpsert strategy will not work correctly"). But the consequence is severe and worth encoding in the Console: with no IS_PK column, BuildCreateTable emits no PRIMARY KEY constraint, so the INSERT OR REPLACE / INSERT OR IGNORE conflict clause can never fire and every sync appends duplicate rows. If STORAGE_STRATEGY=MergeUpsert AND a PK column exists but is not mapped in SYS_DATA_MAP, the sync is aborted with a FATAL error before any write. IS_PK is also incompatible with two other flags: IS_PK+IS_VIRTUAL → Fail, IS_PK+IS_DERIVED → Fail, and IS_PK without IS_MANDATORY → Warn (a null PK breaks MergeUpsert). A PK column is also forced NOT NULL in DDL.

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Models\TableMetadataContext.cs:352-358 (`if (pkCols.Count == 0) report.Add(ValidationResult.Warn(...))`); Infrastructure\Database\SqlBuilderService.cs:68 (`string nullable = (col.IS_MANDATORY || col.IS_PK) ? "NOT NULL" : "NULL";`), :72-77 (`if (col.IS_PK) pkCols.Add(...)`; `if (pkCols.Count > 0) definitions.Add($"    PRIMARY KEY ({string.Join(", ", pkCols)})")`); Infrastructure\Database\LocalDbManager.WriteSession.cs:101 (`string conflictClause = replaceOnConflict ? "OR REPLACE" : "OR IGNORE";`); Infrastructure\Services\Ingestion\DataIngestionService.cs:1484-1506 (MergeUpsert + unmapped PK → hasFatalError) and :870-876 (fatal → IngestionResult.Fail, sync stops); SchemaRuleEntity.cs:511-522, 542-547

### IS_PK — what actually happens with a composite PK (several IS_PK rows for one entity)?

Split behaviour — the DDL supports it, the rest of the system does not, and the validator's message is misleading. SqlBuilderService.BuildCreateTable collects ALL IS_PK columns and emits a genuine compound `PRIMARY KEY (colA, colB)`, so SQLite-level upsert/dedup DOES work on the full composite. But TableMetadataContext.PrimaryKeyColumn returns only `Columns.FirstOrDefault(c => c.IS_PK)` (first in ORDINAL_POS order), and that single column is what drives: the pre-flight "is the PK mapped?" fatal check, BuildSelectByPk, and the LIBRARY MENU_KEY fallback. ValidateCompleteness emits a Warn saying "Composite PK is not yet supported — only the first will be used" — true for those three call sites, false for the DDL. Practical Console guidance: allow at most one IS_PK=true per ENTITY_KEY unless the author knows the second column is enforced only by SQLite.

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Infrastructure\Database\SqlBuilderService.cs:60-77 (pkCols list → `PRIMARY KEY ({string.Join(", ", pkCols)})`); Core\Models\TableMetadataContext.cs:248-249 (`public SchemaRuleEntity PrimaryKeyColumn => Columns.FirstOrDefault(c => c.IS_PK);`), :359-365 (Warn "Composite PK is not yet supported — only the first will be used"); SqlBuilderService.cs:186-196 (BuildSelectByPk uses the single PrimaryKeyColumn); DataIngestionService.cs:1484 (`var pkCol = context.PrimaryKeyColumn;`)

### IS_MANDATORY — what does it actually change at runtime?

Four real effects, all live: (1) DDL — the column is emitted NOT NULL in CREATE TABLE. (2) Ingestion — it makes the column 'critical', so a row whose value for it ends up null is DROPPED entirely (not blanked). (3) Pre-flight — if a mandatory column has no working mapping in SYS_DATA_MAP (no row, or a header-bound row whose header is absent from the source file), the entire source sync is aborted FATALLY before any write, with a data-entry-facing message. (4) Validation logging — ValidateRawRow emits an ERR_NULL Fail per empty mandatory cell on the sampled rows. It is also part of the SchemaHash (a change forces schema-drift handling). The stale doc panel claiming "Currently warning only — data still inserted" is wrong.

**Blank means:** false

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Infrastructure\Database\SqlBuilderService.cs:68 (NOT NULL); Infrastructure\Services\Ingestion\DataIngestionService.Mapping.cs:84 (`IsCritical = col != null && (col.IS_PK || col.IS_MANDATORY)`) + :349-353 (critical null → `return null`, row dropped); DataIngestionService.cs:1530-1566 (`if (col.IS_MANDATORY) { … hasFatalError = true; }`); Core\Validation\ValidationOrchestrator.cs:289-307 (ERR_NULL, "Row will be REJECTED"); SqlBuilderService.cs:516 (`sb.Append("MAN:")…` in BuildSchemaHash). Stale contradicting doc: UI\TaskPane\Views\SchemaGuidePanel.cs:348-350

### IS_VIRTUAL — what does it actually change at runtime?

It removes the column from the physical SQLite table: ShouldPersist => !IS_VIRTUAL, and PersistedColumns (used by CREATE TABLE, index build, EnsurePhysicalSchema and the mandatory-coverage loop) filters on it. ExportEngine also excludes virtual columns from every export. It is part of the SchemaHash. TRAP the Console must guard: BuildExecutionPlan does NOT skip virtual columns, and BulkInsertCore builds its INSERT column list from the union of the mapped row keys with no physical-column filter — so a SYS_DATA_MAP row whose TARGET_ATTRIBUTE_KEY names an IS_VIRTUAL column produces an INSERT naming a column that does not exist in the table, which throws and rolls the whole source write back. Rule: never allow a DataMap row to target a column whose SchemaRule has IS_VIRTUAL=true. Also IS_PK+IS_VIRTUAL is a hard Fail, and IS_VIRTUAL+IS_DERIVED is a Warn (VIRTUAL wins).

**Blank means:** false

*likely* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:453-454 (`public bool ShouldPersist => !IS_VIRTUAL;`), :511-515 (PK+VIRTUAL Fail), :504-508 (VIRTUAL+DERIVED Warn); Core\Models\TableMetadataContext.cs:241-242 (PersistedColumns); Infrastructure\Database\SqlBuilderService.cs:47-49, :103 ; Infrastructure\Engines\ExportEngine.cs:1193-1196 (`.Where(c => !c.IS_VIRTUAL && (isAdmin || c.IS_VISIBLE))`); the trap: Infrastructure\Services\Ingestion\DataIngestionService.Mapping.cs:54-70 (plan skips only col==null) + :355 (`row[colKey] = value;`) + Infrastructure\Database\LocalDbManager.WriteSession.cs:91-105 (column list = union of row keys, no filter)

### IS_DERIVED — what does it actually change at runtime?

NOTHING. It is inert. Grepping the whole solution, IS_DERIVED appears only in (a) SchemaRuleEntity's own Validate() rules, (b) the read-only ETL/doc panels. It does not exclude the column from the mapping plan, from the DDL, from the export, or from the SchemaHash. Its companion LOGIC_CONFIG.Formula is likewise never evaluated anywhere — no engine reads it. The only live consequences of setting IS_DERIVED=true are three validation findings: with IS_PK → Fail; with IS_VIRTUAL → Warn (VIRTUAL takes priority); without a LOGIC_CONFIG.Formula → Warn ("this column will remain empty"). The doc panel claim "DataIngestionService skips mapping" is stale and false. For the Console: IS_DERIVED is safe to offer but must be described as declarative-only.

**Blank means:** false

*certain* — Whole-solution grep for IS_DERIVED under C:\Users\User01\source\repos\mbiXaddin\mbiXaddin returns only Core\Entities\SchemaRuleEntity.cs:366-367, 503-508, 517-522, 561-567 and UI\TaskPane\Views\SchemaGuidePanel.cs:354-357 — zero hits in Infrastructure. LOGIC_CONFIG.Formula grep returns only SchemaRuleEntity.cs:562, 654-658, 724 and UI\TaskPane\EtlInfoBuilder.cs:781-782. Stale contradicting doc: SchemaGuidePanel.cs:356 ("DataIngestionService skips mapping")

### IS_VISIBLE — what does it actually change at runtime?

It is display-and-access only; the column still exists in SQLite and is still ingested. Three live effects: (1) TableMetadataContext.VisibleColumns and SqlBuilderService.BuildSelectAll / BuildSelectByPk / BuildSelectWhere select only IS_VISIBLE columns; (2) ExportEngine hides them from the sheet — EXCEPT for an Admin-tier user, who sees IS_VISIBLE=false columns too; (3) it participates in the license mask during ingestion: a column is masked (written as the teaser placeholder instead of its real value) when LICENSE_TIER != Free AND NOT (tier allows AND IS_VISIBLE). It is part of the SchemaHash. Blank reads as TRUE — the only flag defaulting true.

**Blank means:** true

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:374-375 (`public bool IS_VISIBLE { get; set; } = true;`); Core\Models\TableMetadataContext.cs:235-236; Infrastructure\Database\SqlBuilderService.cs:168-176; Infrastructure\Engines\ExportEngine.cs:1187-1196 (`bool isAdmin = _security.GetCurrentTier() == LicenseTier.Admin;` … `(isAdmin || c.IS_VISIBLE)`); Infrastructure\Services\Ingestion\DataIngestionService.Mapping.cs:74-76 (`bool masked = col.LICENSE_TIER != LicenseTier.Free && !(ent.Allows(col.LICENSE_TIER) && col.IS_VISIBLE);`); SqlBuilderService.cs:517 (SchemaHash)

### ORDINAL_POS — is it required? What orders columns when it is blank or duplicated?

NOT required. Blank reads as 0 (parser skips the cell, declared default 0). It is the sole sort key everywhere columns are ordered — context construction, CREATE TABLE column order, every SELECT, the Excel export column order, MENU_GROUP / EXPORT_GROUP / MENU_FACET nesting depth order, and the first-wins tiebreak for singular semantic roles. On duplicates or blanks there is NO secondary sort key: LINQ OrderBy is a stable sort, so tied columns keep their upstream enumeration order, which is the resolved-columns dictionary insertion order (inherited PARENT_KEY columns first, then the entity's own columns in sheet row order). Negative values are accepted and DO sort first — the validator emits a Warn whose text says "Value 0 will be used", but no code anywhere clamps ORDINAL_POS, so that message is wrong. Console recommendation: require an integer >= 0, and warn on duplicates within an ENTITY_KEY since the resulting order is order-of-arrival rather than declared.

**Blank means:** 0

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:261-262 (`public int ORDINAL_POS { get; set; } = 0;`), :496-501 (negative → Warn "Value 0 will be used" — no clamping code exists); Core\Models\TableMetadataContext.cs:131-133 (`.OrderBy(c => c.ORDINAL_POS)` — the only sort); Infrastructure\Database\SqlBuilderService.cs:49, 176, 196, 214; Infrastructure\Engines\ExportEngine.cs:1196; UI\Commands\LibraryMenuBuilder.cs:230, 236; UI\Commands\ExportTreeMenuBuilder.cs:89, 114; enumeration order set at Infrastructure\Services\Sync\Metadata\MetadataOrchestrator.cs:679-703 (parent cols then local cols into a Dictionary keyed by ATTRIBUTE_KEY)

### UX_CONFIG — is it JSON, and which keys does the code actually read?

Yes — a JSON object literal only (the legacy {"$preset":"KEY"} mechanism was retired and is ignored). Exactly SIX keys are deserialised into ColumnUxConfig and all six are consumed by ExportEngine: Width (int, Excel character width; ignored when AutoFit is true; falls back to a DATA_TYPE default), Format (string, Excel number format e.g. "#,##0.00"; falls back to a DATA_TYPE default), Align (string; the switch accepts LEFT / RIGHT / CENTER / JUSTIFY case-insensitively, anything else silently becomes General), HeaderColor (hex header background; the validator accepts #RGB or #RRGGBB but the renderer HexToColor requires exactly 6 digits, so a 3-digit colour validates and is then silently dropped — the Console should require #RRGGBB), WrapText (bool; skipped entirely above the row limit), AutoFit (bool; overrides Width; substituted with a fixed width above the row limit). Any other top-level key produces a Warn "Unknown key … it has no effect" with a did-you-mean suggestion. Invalid JSON, or a value not starting with '{', discards the WHOLE bag and falls back to a default config with a log warning — it never throws and never blocks.

**Accepted:** `Width`, `Format`, `Align`, `HeaderColor`, `WrapText`, `AutoFit`

**Blank means:** null → empty ColumnUxConfig; all six unset → DATA_TYPE-derived defaults for width/format/alignment

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:387-388 (`[JsonProperty("UX_CONFIG")] public string UX_CONFIG_RAW`), :587-634 (class ColumnUxConfig — Width:590, Format:593, Align:596, HeaderColor:599, WrapText:602, AutoFit:605), :570-572 (ValidateBag + ValidateHexColor); Core\Configuration\ConfigResolver.cs:70-99, :140-150 (ResolveColumn); Core\Configuration\ConfigValidator.cs:47-88 (unknown-key Warn); Infrastructure\Engines\ExportEngine.cs:490-495 + 1340-1350 (Align switch), :621-637 (HeaderColor) + :1324-1336 (HexToColor requires length 6), :668-688 (Width/Format/Align), :706-745 (WrapText), :756-800 (AutoFit); ConfigVocabulary.cs:42-47 (IsHexColor accepts 3 or 6)

### LOGIC_CONFIG — is it JSON, and which keys does the code actually read?

Yes — JSON object literal only ($preset retired). EIGHT keys deserialise into ColumnLogicConfig, but only FIVE do anything at runtime: Min and Max (decimal — become an Excel xlValidateDecimal 'between' rule with a WARNING alert style, applied when either is present), ListSource (string; only two values are honoured, "Static" and "Distinct", compared case-insensitively — anything else non-empty makes HasList true but produces no formula, so the dropdown is silently skipped), ListItems (comma-separated values used when ListSource=Static; lists over 255 chars are written to a hidden helper column), ListStrict (bool; true = xlValidAlertStop i.e. reject, false/absent = xlValidAlertWarning i.e. warn only). THREE keys are declared, validated as known, shown in the ETL panel — and never read by any engine: Formula (the IS_DERIVED calculation — nothing evaluates it), LookupRef (its own doc comment says "FUTURE — not yet applied by ExportEngine"), DefaultVal (the ingestion default actually comes from SYS_DATA_MAP's PROCESS_CONFIG.DefaultValue, not from here). Unknown top-level keys → Warn only. Min>Max is not checked.

**Accepted:** `Min`, `Max`, `Formula`, `LookupRef`, `DefaultVal`, `ListSource`, `ListItems`, `ListStrict`

**Blank means:** null → empty ColumnLogicConfig; no Excel validation and no dropdown

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:411-412 (`[JsonProperty("LOGIC_CONFIG")] public string LOGIC_CONFIG_RAW`), :645-731 (class ColumnLogicConfig — Min:648, Max:651, Formula:658, LookupRef:665 with "FUTURE — not yet applied by ExportEngine" at :662-663, DefaultVal:668, ListSource:680, ListItems:687, ListStrict:695, IsStaticList:701, IsDistinctList:704), :571 (ValidateBag); Infrastructure\Engines\ExportEngine.cs:858-881 (ApplyValidation), :884-907 (ApplyMinMaxValidation), :909-955 (ApplyListDropdown — `logic.ListStrict == true ? xlValidAlertStop : xlValidAlertWarning`, 255-char split at :931). Dead keys proven by whole-solution grep: Formula → only SchemaRuleEntity.cs:562/654-658/724 + EtlInfoBuilder.cs:781; LookupRef → only SchemaRuleEntity.cs + EtlInfoBuilder.cs:785; DefaultVal → only SchemaRuleEntity.cs:668/726 + EtlInfoBuilder.cs:790, while ingestion reads DataMapEntity.cs:367 PROCESS_CONFIG.DefaultValue at DataIngestionService.Mapping.cs:284

### LICENSE_TIER (SchemaRule) — vocabulary and effect?

Enum LicenseTier with four members, parsed case-insensitively by name. On a column it gates masking during ingestion: a column with LICENSE_TIER != Free whose tier the run's entitlement does not allow (or which is IS_VISIBLE=false) has its value replaced by the teaser placeholder text at map time, so the real value never reaches SQLite. It is also part of the SchemaHash, so changing it forces schema-drift handling. Blank reads as Free.

**Accepted:** `Free`, `Standard`, `Premium`, `Admin`

**Blank means:** Free

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Licensing\UserProfile.cs:35-41 (`public enum LicenseTier { Free = 0, Standard = 1, Premium = 2, Admin = 99 }`); Core\Entities\SchemaRuleEntity.cs:268-270 (`[JsonProperty("LICENSE_TIER")] [JsonConverter(typeof(StringEnumConverter))] … = LicenseTier.Free;`); Infrastructure\Services\Ingestion\DataIngestionService.Mapping.cs:74-76 and :264-269 (`if (action.IsMasked) { row[colKey] = TeaserText; continue; }`); Infrastructure\Database\SqlBuilderService.cs:519 (SchemaHash)

### ENTITY_KEY / ATTRIBUTE_KEY / DISPLAY_HEADER — what does the code require, and what happens on a duplicate or an orphan?

ENTITY_KEY and ATTRIBUTE_KEY are the only two CRITICAL fields: blank on either yields ValidationResult.Critical and stops that row's validation immediately. On the offline SQLite readback path a Critical finding actually REJECTS the row; on the online fetch path validation is alert-only and the row is still persisted and used. ATTRIBUTE_KEY over 100 chars → Fail (row still kept). Both are the composite primary key of _SYS_SCHEMA_RULES, so the Console must enforce uniqueness of (ENTITY_KEY, ATTRIBUTE_KEY): in memory a duplicate ATTRIBUTE_KEY within an entity is resolved LAST-WINS silently (dictionary assignment), with no warning at all — unlike SYS_DEFINITIONS duplicates which are logged. Rows whose ENTITY_KEY matches no ACTIVE definition are dropped from the graph with an [ORPHAN_COLS] warning. If a definition has PARENT_KEY set, the parent's columns are inherited first and the child's same-named columns override them. DISPLAY_HEADER blank is a Fail but harmless in practice — the export falls back to alias → DISPLAY_HEADER → ATTRIBUTE_KEY.

*certain* — C:\Users\User01\source\repos\mbiXaddin\mbiXaddin\Core\Entities\SchemaRuleEntity.cs:463-487 (ENTITY_KEY / ATTRIBUTE_KEY Critical + yield break; 100-char Fail), :489-494 (DISPLAY_HEADER Fail); Infrastructure\Database\SqlBuilderService.cs:293 (`PRIMARY KEY (ENTITY_KEY, ATTRIBUTE_KEY)`); Infrastructure\Services\Sync\Metadata\MetadataOrchestrator.cs:679-703 (`resolvedCols[c.ATTRIBUTE_KEY] = c;` parent then local — last wins, no log), :586-596 ([ORPHAN_COLS] warning), :341-346 (ValidateAndAlertBatch — online path is alert-only); MetadataOrchestrator.Tier1Schema.cs:596-612 (offline readback rejects rows with a Critical finding); Core\Utils\ExportNaming.cs:70-75 (header fallback chain)


## the-entity-and-source

### 1.TableDefinition / ENTITY_TYPE — complete vocabulary

10 values, defined as the C# enum `EntityType`: COST, PERF, REF, COMP, CONVERSION, COST_ENG, AUDIT, ASSEMBLY, LIBRARY, SYSTEM. Blank is legal (the property is `EntityType?`, nullable, default null). Note the two in-file doc blocks and the SchemaGuidePanel list only 8 values (they predate LIBRARY and SYSTEM) — the enum is the authority.

**Accepted:** `COST`, `PERF`, `REF`, `COMP`, `CONVERSION`, `COST_ENG`, `AUDIT`, `ASSEMBLY`, `LIBRARY`, `SYSTEM`, ``

**Blank means:** null (no type). Validate() emits a Warn "has no ENTITY_TYPE", the entity is still built and synced.

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:43-66 `public enum EntityType { COST, PERF, REF, COMP, CONVERSION, COST_ENG, AUDIT, ASSEMBLY, LIBRARY, SYSTEM }`; :161 `public EntityType? ENTITY_TYPE { get; set; }`. Stale 8-value lists at TableDefinitionEntity.cs:157, :849 and UI/TaskPane/Views/SchemaGuidePanel.cs:255.

### 1.TableDefinition / ENTITY_TYPE — what does each value actually change in code?

Very little is functional. Only three effects exist: (1) COST and COST_ENG make `IsCostRelated` true, which triggers a Warn if no column carries SEMANTIC_ROLE=PRICE; (2) CONVERSION makes `IsConversionTable` true, which requires CONV_SOURCE/CONV_TARGET/CONV_FACTOR columns; (3) LIBRARY turns on the document-library completeness checks (MENU_KEY / MENU_URL / MENU_LABEL roles) — and even that is OR'd with `IsMenuSource`, so tagging LIBRARY is explicitly "a classifier/filter aid, not a functional switch". Everything else is filtering/display: MetadataRegistry.GetByType(), the ribbon "Cost Tables"/"Reference Tables" filters, ribbon group-by-Type, and ETL Inspector badges. PERF, COMP, AUDIT, ASSEMBLY and SYSTEM have no code that branches on them anywhere.

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:374-381 (IsCostRelated / IsConversionTable); mbiXaddin/Core/Models/TableMetadataContext.cs:435 `if (Definition.ENTITY_TYPE == EntityType.LIBRARY || IsMenuSource)`; :223 "tagging ENTITY_TYPE=LIBRARY is OPTIONAL (a classifier/filter aid), not a functional switch"; :426 COST/PRICE warn; mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataRegistry.cs:196; mbiXaddin/UI/Commands/RibbonContentBuilder.cs:86-87,165,493.

### 1.TableDefinition / STORAGE_STRATEGY — complete vocabulary and default

3 values, from the C# enum `UpdateStrategy`: ReplaceAll (ordinal 0), MergeUpsert (1), Append (2). Default when the cell is blank is MergeUpsert (the C# property initializer). The TSV parser also accepts these case-insensitive aliases and normalises them before Enum.Parse: REPLACE→ReplaceAll, UPSERT→MergeUpsert, MERGE→MergeUpsert, INSERT→Append.

**Accepted:** `ReplaceAll`, `MergeUpsert`, `Append`, `REPLACE`, `UPSERT`, `MERGE`, `INSERT`

**Blank means:** MergeUpsert

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:96-104 `public enum UpdateStrategy { ReplaceAll, MergeUpsert, Append }`; :198 `public UpdateStrategy STORAGE_STRATEGY { get; set; } = UpdateStrategy.MergeUpsert;`; aliases at mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:200-204.

### 1.TableDefinition / STORAGE_STRATEGY — what does each strategy do at write time, and what does MergeUpsert match ON?

The strategy resolves into exactly two booleans passed to the SQLite write session: `truncateFirst = (strategy == ReplaceAll)` and `replaceOnConflict = (strategy == MergeUpsert)`. Those become the SQL: `INSERT OR REPLACE INTO [table]` when MergeUpsert, `INSERT OR IGNORE INTO [table]` otherwise. So — ReplaceAll: DELETE everything for the entity once, then INSERT OR IGNORE. MergeUpsert: no truncate, INSERT OR REPLACE. Append: no truncate, INSERT OR IGNORE (duplicates silently dropped). MergeUpsert therefore matches on the SQLite conflict target, which is the table's PRIMARY KEY — and that PRIMARY KEY is generated from SchemaRule: every persisted column with IS_PK=true, in ORDINAL_POS order, emitted as one (possibly composite) `PRIMARY KEY (...)` clause. There are no UNIQUE indexes (BuildIndexScript emits plain CREATE INDEX), so the PK is the only conflict target. That is the hard tie between sheet 1 and sheet 2.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:966 `bool replaceOnConflict = context.Definition.STORAGE_STRATEGY == UpdateStrategy.MergeUpsert;` and :315 `context.Definition.STORAGE_STRATEGY == UpdateStrategy.ReplaceAll` (truncateFirst); mbiXaddin/Infrastructure/Database/LocalDbManager.WriteSession.cs:101 `string conflictClause = replaceOnConflict ? "OR REPLACE" : "OR IGNORE";` and :104 `INSERT {conflictClause} INTO [{tableName}]`; PK construction at mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:72-77 `if (col.IS_PK) pkCols.Add(...)` / `PRIMARY KEY ({string.Join(", ", pkCols)})`; non-unique indexes at SqlBuilderService.cs:126-128.

### 1.TableDefinition / STORAGE_STRATEGY — the two failure modes the Console must block

(a) MergeUpsert with the PK column not mapped in DataMap is FATAL and the sync is refused ("MergeUpsert strategy … requires a PK to prevent duplicates"); the same condition under ReplaceAll is only a warning. (b) A subtler hole: that fatal check runs only `if (pkCol != null)`, and `PrimaryKeyColumn` is `Columns.FirstOrDefault(c => c.IS_PK)`. If an entity has NO SchemaRule row with IS_PK=true at all, BuildCreateTable emits no PRIMARY KEY clause, `INSERT OR REPLACE` has nothing to conflict on, and MergeUpsert silently duplicates every row on every sync with no error. So the Console rule is: STORAGE_STRATEGY=MergeUpsert ⇒ the entity must have ≥1 SchemaRule row with IS_PK=true AND that attribute must have a DataMap row in the profile.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1484-1518 (`var pkCol = context.PrimaryKeyColumn; if (pkCol != null) { … if (STORAGE_STRATEGY == UpdateStrategy.MergeUpsert) { hasFatalError = true; } else { warning } }`); mbiXaddin/Core/Models/TableMetadataContext.cs:248-249 `PrimaryKeyColumn => Columns.FirstOrDefault(c => c.IS_PK)`; mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:76 `if (pkCols.Count > 0)`.

### 1/3 / LICENSE_TIER and MIN_LICENSE_REQ — vocabulary and ORDER

Both columns bind to the same C# enum `LicenseTier`, with explicit weights: Free = 0, Standard = 1, Premium = 2, Admin = 99. That numeric order IS the rank order the code uses — every gate is a `>=` on the integer value, so the Console must offer them as Free < Standard < Premium < Admin. Default for a blank cell is Free on all three carriers (TableDefinition.LICENSE_TIER, SchemaRule.LICENSE_TIER, DataSource.MIN_LICENSE_REQ). The gap between 2 and 99 is deliberate — the guide notes a future Enterprise(3) can be inserted without breaking the order.

**Accepted:** `Free`, `Standard`, `Premium`, `Admin`

**Blank means:** Free (weight 0)

*certain* — mbiXaddin/Core/Licensing/UserProfile.cs:35-41 `public enum LicenseTier { Free = 0, Standard = 1, Premium = 2, Admin = 99 }`; comparisons: mbiXaddin/Core/Security/SecurityContext.cs:207 `if (c.Weight < (int)requiredTier) return false;`, mbiXaddin/Infrastructure/Services/Ingestion/IngestionResult.cs:89 `public bool Allows(LicenseTier required) => IsActive && (int)Tier >= (int)required;`, mbiXaddin/Core/Entities/TableDefinitionEntity.cs:423 `if ((int)parent.LICENSE_TIER > (int)LICENSE_TIER) LICENSE_TIER = parent.LICENSE_TIER;`. Defaults: TableDefinitionEntity.cs:169, DataSourceEntity.cs:169.

### 1/3 / LICENSE_TIER vs MIN_LICENSE_REQ — how they interact

They are two independent gates, both applied. TableDefinition.LICENSE_TIER gates the whole entity (Gate 1: `ent.Allows(context.Definition.LICENSE_TIER)`; a blocked entity is rendered as a locked teaser rather than synced) and is escalated by inheritance — a parent with a higher tier overwrites a child's lower tier. DataSource.MIN_LICENSE_REQ gates the individual source (Gate 2: `IsSourceEligible`), and combines with SOURCE_REGION and IS_ACTIVE. A Free source is only region+active checked; a non-Free source additionally needs `ent.Allows(MIN_LICENSE_REQ)`. The guide's advice (not enforced anywhere in code) is MIN_LICENSE_REQ ≥ the parent table's LICENSE_TIER.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:153-164 (Gate 1) and :555-559 `IsSourceEligible(...) => source.MIN_LICENSE_REQ == LicenseTier.Free ? source.IS_ACTIVE && _security.IsRegionMatch(source.SOURCE_REGION) : ent.Allows(source.MIN_LICENSE_REQ) && source.IS_ACTIVE && _security.IsRegionMatch(source.SOURCE_REGION)`; escalation at mbiXaddin/Core/Entities/TableDefinitionEntity.cs:422-424; advisory note (comment only) at DataSourceEntity.cs:562.

### 1.TableDefinition / VIEW_MODE — what is it for?

Nothing functional today. Vocabulary is the enum `ViewMode`: Table, Card, Chart; default Table. The only reads in the whole codebase are the ETL Inspector row (`Kv("View Mode", def.VIEW_MODE.ToString())`) and the column's own DDL default. The in-code schema guide states it plainly: "How ExportEngine renders the table. Currently not used." Safe for the Console to offer as a 3-value drop-down, but changing it changes no behaviour.

**Accepted:** `Table`, `Card`, `Chart`

**Blank means:** Table

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:110-118 `public enum ViewMode { Table, Card, Chart }`; :217 `public ViewMode VIEW_MODE { get; set; } = ViewMode.Table;`; only consumer mbiXaddin/UI/TaskPane/EtlInfoBuilder.cs:138; "Currently not used" at mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:285; DDL default at mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:272.

### 1.TableDefinition / BUSINESS_DOMAIN — what is it for?

Ribbon/menu classification only — no engine behaviour. Vocabulary is the enum `BusinessDomain`: MATERIAL, LABOR, EQUIPMENT, VENDOR, PROJECT, FINANCE, SYSTEM, GARB (GARB = "the unified list of the General Authority for Roads and Bridges in Egypt"). Nullable, default null. Consumed by MetadataRegistry.GetByDomain(), the ribbon EntityFilter (`Materials => Domain = BusinessDomain.MATERIAL`), the ribbon group-by-Domain grouping (null groups as "General"), and the ETL Inspector. It is also inherited from PARENT_KEY when the child's cell is blank.

**Accepted:** `MATERIAL`, `LABOR`, `EQUIPMENT`, `VENDOR`, `PROJECT`, `FINANCE`, `SYSTEM`, `GARB`, ``

**Blank means:** null — entity appears under every domain filter and groups as "General"

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:72-90 (enum, GARB comment at :88-89); :230 `public BusinessDomain? BUSINESS_DOMAIN { get; set; }`; consumers mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataRegistry.cs:234, mbiXaddin/UI/Commands/RibbonContentBuilder.cs:95,166,494; inheritance at TableDefinitionEntity.cs:418.

### 1.TableDefinition / PARENT_KEY — is it a reference to another ENTITY_KEY, and what happens when the parent does not exist?

Yes: it is a free-text foreign key resolved case-insensitively against SYS_DEFINITIONS.ENTITY_KEY. A missing parent is NOT fatal — MetadataOrchestrator logs a warning ("Inheritance will be skipped — will be treated as a root entity") and carries on; there is no ValidationResult, so nothing blocks the sync. Crucially, the lookup dictionary is built from ACTIVE definitions only, so pointing at a row with IS_ACTIVE=false behaves identically to pointing at a nonexistent key. Pointing at itself IS blocked: Validate() returns a Critical CircularInheritance. There is no multi-level resolution — `MergeWithParent` is applied once per entity, so grandparent settings do not propagate.

**Blank means:** null → root entity (`IsRoot => string.IsNullOrWhiteSpace(PARENT_KEY)`, TableDefinitionEntity.cs:370)

*certain* — Warning path: mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:666-677 `if (!string.IsNullOrWhiteSpace(def.PARENT_KEY) && !defsMap.ContainsKey(def.PARENT_KEY)) _log.LogWarning("[ERR_REF] … Inheritance will be skipped …")`; apply path :682-690 `defsMap.TryGetValue(def.PARENT_KEY, out var parentDef) → def.MergeWithParent(parentDef)`; defsMap is active-only + OrdinalIgnoreCase at :528-544; self-reference Critical at mbiXaddin/Core/Entities/TableDefinitionEntity.cs:461-466.

### 1.TableDefinition / PARENT_KEY — exactly what is inherited?

Six things, child-wins, filling only nulls/defaults: ENTITY_TYPE (if child null), BUSINESS_DOMAIN (if child null), RIBBON_CONFIG (merged if parent resolved and child not), LICENSE_TIER (escalation only — the HIGHER tier always wins, parent can raise the child's tier but never lower it), UX_CONFIG and SYS_CONFIG (per-property null-fill via Merge()). Additionally, the parent's SchemaRule columns are copied to the child first and then overridden key-by-key by the child's own columns — so a child inherits its parent's column set. STORAGE_STRATEGY, VIEW_MODE, IS_ACTIVE, IS_VISIBLE, DISPLAY_NAME and EXPORT_CONFIG are NOT inherited.

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:413-429 `MergeWithParent`; column inheritance at mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:687-695.

### 3.DataSource / SOURCE_URI — how is it fetched? (client, headers, auth, redirects)

Plain HTTP GET, streamed straight to a temp file. DataIngestionService calls `_http.DownloadToFileAsync(source.SOURCE_URI, stagedPath, prep.Scope, ct)` on `HttpClientService`, a single static `HttpClient` (60s timeout) whose handler races IPv4/IPv6 (Happy Eyeballs) for direct connections and falls back to a stock HttpClientHandler with GZip/Deflate decompression and AllowAutoRedirect when a system proxy applies; the Happy-Eyeballs path follows up to 5 redirects itself (301/302/303/307/308). NO AUTHENTICATION of any kind — no Authorization header, no cookies, no OAuth; the code comments state "Currently all sources are public (Google Sheets published URLs — no auth needed)". Before the request the URL is cache-busted by appending `?cb=<UtcNow.Ticks>` or `&cb=…`, plus `Cache-Control: no-cache, no-store`, `Pragma: no-cache`, `If-Modified-Since: 2000-01-01`. Concurrency is capped by `_httpSemaphore`; 3 retries with exponential backoff + jitter on 408/429/5xx and on HttpRequestException/TaskCanceledException/IOException. Before download, the URI must be non-empty and must `StartsWith("http")`, otherwise it is a hard "Invalid Source URL" failure.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:718-762 (empty-URI defer, `!source.SOURCE_URI.StartsWith("http")` fail, `dl = await _http.DownloadToFileAsync(source.SOURCE_URI, stagedPath, prep.Scope, ct: ct)`); mbiXaddin/Infrastructure/Network/HttpClientService.cs:393-465 (DownloadToFileAsync), :175-193 (handlers), :593-620 (AppendCacheBuster / CreateRequest headers), :585 MaxRetries=3, :998-1002 retry predicates; redirects at mbiXaddin/Infrastructure/Network/HappyEyeballsHandler.cs:97-108,442; "no auth needed" at mbiXaddin/Core/Entities/DataSourceEntity.cs:666-668.

### 3.DataSource / SOURCE_URI — what content types are accepted, and how is the response turned into rows?

Content-Type is never inspected — the code says so explicitly ("nothing checks Content-Type"). Instead there are three post-download guards on the bytes: (1) empty response → fail; (2) size ceiling `MaxSourceBytes` → fail; (3) a markup sniff of the first 256 chars — if the payload starts (after BOM/whitespace) with `<!DOCTYPE`, `<HTML` or `<?XML` it is rejected with a message naming `?output=tsv` as the fix. Parsing is `StreamingTsvReader`: a UTF-8 StreamReader with BOM detection, it drops `CONTEXT_PROPS.SkipRows` leading lines, takes the NEXT line as the header, splits every line on `'\t'` only, and skips whitespace-only lines. There is no CSV quoting, no escaping, no delimiter option — a tab inside a cell will split it. `Encoding` and `Delimiter` from CONTEXT_PROPS are NOT applied here. A fourth structural guard then rejects the file if zero of the profile's header-bound mappings resolve against the header row.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:772-822 (empty / size / markup sniff), :843-845 `StreamingTsvReader.FromStream(File.OpenRead(stagedPath), skipRows: skipRows)`; mbiXaddin/Infrastructure/Services/Ingestion/StreamingTsvReader.cs:62-72 (skip-then-header) and :101-108 `line.Split('\t')`; markup openings at mbiXaddin/Infrastructure/Services/Ingestion/SourceIntegrityGate.cs:64-69; "nothing checks Content-Type" at mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:48-52; total-header-mismatch guard at DataIngestionService.cs:1461-1481.

### 3.DataSource / SOURCE_URI — does the code care that it is a published /d/e/2PACX- URL rather than a normal spreadsheet URL?

No. Nothing anywhere matches `/d/e/`, `2PACX`, `/pub`, or `/export`. The only URL shape rules are in SourceUriValidator: (a) must start with http:// or https:// OR look like a local path (leading '/', contains '\\', or drive-letter colon at index 1) — otherwise Error and validation stops; (b) http URL whose authority contains no '.' → Warning; (c) IF the URL contains the literal substring "docs.google.com" (case-insensitive), then it MUST contain "output=tsv" or "format=tsv" (Error if absent — this is the single most common data-entry mistake) and SHOULD contain "gid=" (Warning if absent, "always reads the first tab"). A published /d/e/2PACX-…/pub?gid=…&single=true&output=tsv URL satisfies all of these — the unit tests exercise exactly that shape. At runtime the extra requirement is only `StartsWith("http")`.

*certain* — mbiXaddin/Core/Validation/SourceUriValidator.cs:44-49 (http/local shape), :66-75 (domain dot), :80-118 (`bool isGoogleSheets = sourceUri.IndexOf("docs.google.com", …) >= 0;` then hasTsvParam / hasGid); tests/Core.Tests/SourceUriValidatorTests.cs:64,74 use `https://docs.google.com/spreadsheets/d/e/KEY/pub?gid=123456&single=true&output=tsv`; runtime check mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:734.

### 3.DataSource / VERSION_TAG — what does the code DO with it? Must the Console bump it after a write?

It is one hashed input to the v2 decision fingerprint that decides whether a source re-downloads — NOT a cache key, and NOT compared against anything remote. `DecisionFingerprint.Build` length-prefixes VERSION_TAG as field "VER" alongside IS_ACTIVE, SOURCE_REGION, MIN_LICENSE_REQ, resolved PROFILE_KEY, SOURCE_URI, SkipRows, the context-stable hash (STORAGE_STRATEGY + the full SchemaRule column set) and every DataMap facet (target key, SOURCE_TYPE, MATCH_MODE, SOURCE_EXPRESSION, TRANSFORM_CHAIN); the SHA-256 is stored as "v2:<64hex>" in _SYS_SYNC_STATE and compared on the next run. If it differs → re-ingest. So: the Console does NOT have to bump VERSION_TAG after editing SOURCE_URI, SkipRows, mappings, transforms, column definitions or STORAGE_STRATEGY — those already flip the hash. VERSION_TAG is the escape hatch for the case the hash cannot see: the remote sheet CONTENT changed while every configuration input stayed identical. In that case nothing re-downloads until VERSION_TAG (or another input) changes. Note null, "" and "0" are deliberately kept distinct by the length-prefix encoding. Elsewhere it is display-only (ribbon tooltip "Version: …", ETL Inspector, and the skip message "No changes (v=…)").

**Blank means:** null — hashed as the distinct "absent" marker (VER=-1:;); it does not force a sync by itself

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/IngestionFingerprint.cs:61-83 `BuildDecisionHashV2(... source.VERSION_TAG ...)`; mbiXaddin/Infrastructure/Services/Ingestion/DecisionFingerprint.cs:104-142 `AppendField(sb, "VER", versionTag)` … `V2Prefix + HashUtility.Sha256Hex(...)`, null-vs-empty note at :102-103 and :157-164; decision at mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:650-705 ("No changes (v={source.VERSION_TAG})"); display at mbiXaddin/UI/Commands/RibbonContentBuilder.cs:470 and mbiXaddin/UI/TaskPane/EtlInfoBuilder.cs:422.

### 3.DataSource / CONTEXT_PROPS — is it JSON, and which keys are actually read?

Yes — a plain JSON object, direct only (the old {"$preset":"KEY"} form was retired and now raises an UNKNOWN_KEY warning). It deserialises into `SourceContextProps`, whose complete key set is: SourceType, SyncFreq, SkipRows, Encoding, Delimiter, TimeoutSeconds, ActionUrl. What the running code actually READS: SkipRows (leading metadata lines dropped before the header row, and hashed into the fingerprint; must be >= 0 or the source fails with a named config error) and SyncFreq (throttles re-checks on a manual click, but ONLY when nothing else changed — a fingerprint change always wins). SourceType is read only by the computed `IsGoogleSheetSource` (which has no callers) and the ETL display. Encoding, Delimiter, TimeoutSeconds and ActionUrl are stored and displayed but applied nowhere — the reader is always UTF-8 tab-split and the timeout is always the client's 60s. Unknown top-level keys are flagged as an UNKNOWN_KEY warning with a "did you mean" suggestion, and are otherwise ignored.

**Accepted:** `SourceType`, `SyncFreq`, `SkipRows`, `Encoding`, `Delimiter`, `TimeoutSeconds`, `ActionUrl`

**Blank means:** null → all defaults: SourceType=GoogleSheetTsv, SyncFreq=Manual, SkipRows=0, Encoding="UTF-8", Delimiter=",", TimeoutSeconds=30, ActionUrl=null

*certain* — Class: mbiXaddin/Core/Entities/DataSourceEntity.cs:406-455 (SourceContextProps: SourceType/SyncFreq/SkipRows/Encoding/Delimiter/TimeoutSeconds/ActionUrl); reads: mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:826 `int skipRows = source.CONTEXT_PROPS?.SkipRows ?? 0;`, :831-840 (negative SkipRows = fail), :678 `var freq = source.CONTEXT_PROPS?.SyncFreq ?? SyncFrequency.Manual;`, :1083-1090 GetSyncInterval; fingerprint at IngestionFingerprint.cs:80; unused keys only in mbiXaddin/UI/TaskPane/EtlInfoBuilder.cs:503-538; unknown-key warning at mbiXaddin/Core/Configuration/ConfigValidator.cs:77-87 via DataSourceEntity.cs:390.

### 3.DataSource / CONTEXT_PROPS — the enum vocabularies for SourceType and SyncFreq, and the failure mode of a wrong value

SourceType (enum `SourceType`): GoogleSheetTsv | LocalCsv | RestApi | LocalSqlite. SyncFreq (enum `SyncFrequency`): Manual | Hourly | Daily | Weekly | Monthly. WARNING — the XML doc comment beside SyncFreq (DataSourceEntity.cs:419) and the user guide (:590) both list "OnStartup", which is NOT a member of the enum; the enum is the authority and the Console must not offer OnStartup. The failure mode is severe and worth a hard validation rule: CONTEXT_PROPS is deserialised with `JObject.ToObject<T>()` inside a try/catch that returns `new T()` on ANY exception, and an unknown enum name throws — so one bad SyncFreq or SourceType string silently discards the ENTIRE bag, including SkipRows, reverting it to 0. That mis-parses every row of a sheet with a title block.

**Accepted:** `GoogleSheetTsv`, `LocalCsv`, `RestApi`, `LocalSqlite`, `Manual`, `Hourly`, `Daily`, `Weekly`, `Monthly`

**Blank means:** SourceType=GoogleSheetTsv, SyncFreq=Manual

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:48-61 `enum SourceType { GoogleSheetTsv, LocalCsv, RestApi, LocalSqlite }`, :67-78 `enum SyncFrequency { Manual, Hourly, Daily, Weekly, Monthly }`; stale "OnStartup" text at :419 and :590; whole-bag loss at mbiXaddin/Core/Configuration/ConfigResolver.cs:158-159 → :225-233 → mbiXaddin/Core/Utils/JsonSafeParser.cs:138-155 `try { return obj.ToObject<T>() ?? new T(); } catch { … }`.

### How does the parser react to an invalid ENUM value in a TSV cell (the single most important Console guarantee)?

It is recorded as an error and the property keeps its DECLARED DEFAULT — it is never coerced to enum ordinal 0. TsvParser deliberately lets `Enum.Parse` throw so the per-cell catch adds a FetchRowError; the property is then left at the C# initializer value. The comment names the exact stakes: silently coercing STORAGE_STRATEGY to ordinal 0 would mean ReplaceAll = delete-all. So a misspelled STORAGE_STRATEGY yields MergeUpsert (safe), a misspelled LICENSE_TIER yields Free (an ACCESS WIDENING — the Console must still reject it), and a misspelled ENTITY_TYPE/BUSINESS_DOMAIN yields null. Contrast with BOOL columns: SmartConverter returns null rather than throwing, so an unrecognised IS_ACTIVE/IS_VISIBLE value produces NO error at all and silently keeps the default true.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:157-165 `if (underlying.IsEnum) return Enum.Parse(underlying, NormalizeEnumAlias(raw), ignoreCase: true);` with the rationale comment, and the catch at :85-93; bool path mbiXaddin/Core/Utils/SmartConverter.cs:191-192 → :140-144 → :293-304 `IsTrue` returns null when unrecognised; TsvParser.cs:83 `if (converted != null) prop.SetValue(obj, converted);`.

### What boolean strings do IS_ACTIVE / IS_VISIBLE accept?

Case-insensitive, trimmed. True: "1", "true", "yes", "y", "on", "نعم", "صح", "صحيح". False: "0", "false", "no", "n", "off", "لا", "خطأ", "غلط". Anything else (and any blank cell) leaves the declared default, which is TRUE for TableDefinition.IS_ACTIVE, TableDefinition.IS_VISIBLE and DataSource.IS_ACTIVE — and does so with no error recorded. The live sheet's "True" matches. Recommended Console drop-down: exactly TRUE / FALSE.

**Accepted:** `1`, `true`, `yes`, `y`, `on`, `نعم`, `صح`, `صحيح`, `0`, `false`, `no`, `n`, `off`, `لا`, `خطأ`, `غلط`

**Blank means:** true (for all three IS_ACTIVE / IS_VISIBLE columns)

*certain* — mbiXaddin/Core/Utils/SmartConverter.cs:41-53 (TrueValues / FalseValues sets) and :293-304 IsTrue; defaults at mbiXaddin/Core/Entities/TableDefinitionEntity.cs:176,185 and mbiXaddin/Core/Entities/DataSourceEntity.cs:177; blank-cell skip at mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:78 `if (string.IsNullOrEmpty(raw)) continue;`.

### 3.DataSource / SOURCE_REGION — accepted vocabulary

Free text, but validated: accepted are a 2-letter A–Z ISO country code (uppercased, e.g. SA, EG, AE), the literal "GLOBAL", or empty. Anything else yields a Warn and — per the message and the matching code — blocks ALL users from syncing that source, because IsRegionMatch compares the uppercased value against the user's region for exact equality. Empty and "GLOBAL" both mean "everyone"; Admin and Global users match everything.

**Accepted:** `GLOBAL`, `<any 2-letter A-Z ISO code>`, ``

**Blank means:** "" — treated as unrestricted (same as GLOBAL)

*certain* — Validation at mbiXaddin/Core/Entities/DataSourceEntity.cs:337-357 (`isGlobal`, `isIsoCode` = length 2 and both chars A–Z); runtime at mbiXaddin/Core/Security/SecurityContext.cs:220-232 (`if (string.IsNullOrWhiteSpace(sourceRegion)) return true; … srcUpper == GlobalRegion … string.Equals(state.Region, srcUpper, StringComparison.Ordinal)`), decision table at :249-255.

### 3.DataSource / PROFILE_KEY, TARGET_ENTITY_KEY, SOURCE_KEY — key rules the Console must enforce

TARGET_ENTITY_KEY: mandatory (Critical if blank); a case-insensitive FK to SYS_DEFINITIONS.ENTITY_KEY of an ACTIVE definition. If it matches nothing, the source is silently dropped from the graph with an [ORPHAN_SRC] warning — "These sources will never sync." PROFILE_KEY: mandatory (Error if blank) but free text; blank OR the literal "DEFAULT" (case-insensitive) both resolve to the TARGET_ENTITY_KEY, otherwise it is used verbatim to look up DataMap rows. No matching DataMap profile → the sync FAILS with "No mappings for profile". SOURCE_KEY: mandatory (Critical if blank, all further checks skipped), and must be globally unique — a duplicate is logged as an error because SOURCE_KEY keys _SYS_SYNC_STATE and per-row provenance, so "a duplicate can make a removed source delete another source's rows". DISPLAY_LABEL is only a Warn when blank.

**Blank means:** PROFILE_KEY blank → resolves to TARGET_ENTITY_KEY; SOURCE_REGION blank → GLOBAL; DISPLAY_LABEL blank → SOURCE_KEY shown in logs

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:292-328 (SOURCE_KEY Critical, TARGET_ENTITY_KEY Critical, PROFILE_KEY Fail), :257-261 `ResolveProfileKey()`; orphan check mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:597-611; duplicate SOURCE_KEY mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:628-652; missing-mapping failure mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:855-865.

### 1.TableDefinition / ENTITY_KEY, DISPLAY_NAME, IS_ACTIVE, IS_VISIBLE — constraints

ENTITY_KEY: mandatory (Critical, stops all further checks on that row), max 100 chars (over → Fail), must be unique — a duplicate row is dropped with a [DUPLICATE] warning and only the FIRST occurrence is used. Matching against SchemaRule/DataSource/DataMap is case-insensitive throughout. It also becomes the SQLite table name, sanitised. DISPLAY_NAME: mandatory (Fail if blank; free text, any language). IS_ACTIVE=false removes the definition from the context graph entirely — it is filtered before anything is built, so its sources never sync and it cannot be used as anyone's PARENT_KEY. IS_VISIBLE=false only hides it from ribbon menus (`IsVisibleInMenu => IS_ACTIVE && IS_VISIBLE && (RIBBON_CONFIG?.IsVisible ?? true)`); it still syncs.

**Blank means:** IS_ACTIVE=true, IS_VISIBLE=true

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:438-458 (ENTITY_KEY Critical + 100-char Fail, DISPLAY_NAME Fail), :402 IsVisibleInMenu; active filter + duplicate handling at mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:528-545; menu filter at mbiXaddin/UI/Commands/RibbonContentBuilder.cs:174-175; table name at mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:56.

### The sheet's extra columns (Note, Drive on DataSource) and the missing RIBBON_CONFIG — are they a problem?

No, and yes-but-only-as-a-gap. The TSV→entity mapper builds its column map by matching each header, case-insensitively, against the entity's [JsonProperty] names; a header with no match simply never enters the map and is ignored. So "Note" and "Drive" are inert — and adding columns is explicitly supported ("a sheet that GAINS a column this build does not know about is normal and must keep working"). The one hard rule: if NOT ONE header matches, the whole fetch is rejected as "not this sheet at all" (the captive-portal guard) — so the Console must never reorder/rename all recognised headers at once. Separately, DataSourceEntity DOES define a RIBBON_CONFIG column (raw JSON for the source's ribbon button) that the current sheet does not have; the persisted _SYS_DATA_SOURCES DDL carries it. Adding it is safe and would start being read.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:118-149 BuildPropertyMap (unmatched headers dropped), :43-60 the propMap.Count==0 rejection with the "GAINS a column … must keep working" comment; DataSource RIBBON_CONFIG at mbiXaddin/Core/Entities/DataSourceEntity.cs:214-215 and DDL at mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:308.

### 1.TableDefinition / UX_CONFIG, SYS_CONFIG, RIBBON_CONFIG, EXPORT_CONFIG — key sets (context for the Console, cluster 1 columns)

All four are raw JSON objects, direct JSON only ($preset retired). UX_CONFIG → TableUxConfig { TabColor (hex #RRGGBB, validated), Direction ("LTR"|"RTL", validated against ConfigVocabulary.Directions), FreezePanes, ZoomLevel (int?), ShowGridlines (bool?), AutoFitColumns (bool?) }. SYS_CONFIG → TableSysConfig { AllowEdit (bool?), TeaserRowCount (int?), TeaserText (string) }. RIBBON_CONFIG → RibbonDisplayConfig (Label, ScreenTip, SuperTip, Icon, Group, Order, IsVisible, ControlSize validated against ConfigVocabulary.ControlSizes …). EXPORT_CONFIG → ExportConfig (LinkedEntities, FooterText, HeaderStyle/FooterStyle validated against ConfigVocabulary.BannerStyles). Every bag is checked for JSON syntax (Error — a malformed bag is dropped WHOLE at runtime) and unknown top-level keys (Warning with a Levenshtein "did you mean").

**Blank means:** null → the resolved config object is empty defaults; the entity never throws

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:505-545 (TableUxConfig), :555-575 (TableSysConfig), :475-489 (the four ValidateBag calls plus ValidateAllowed for Direction / HeaderStyle / FooterStyle / ControlSize and ValidateHexColor for TabColor); mbiXaddin/Core/Configuration/ConfigValidator.cs:47-88.


## the-blanks

### MECHANISM.blank-cell (applies to all six sheets)

A blank cell is NEVER an error at parse time and NEVER writes anything. TsvParser skips the cell before any conversion, so the property setter is never called and the C# property keeps its DECLARED INITIALIZER value. This is the single rule that governs every column below: 'the default for a blank' = the property's field initializer in the entity class. A column with no initializer defaults to null (reference) / 0 (int) / false (bool). Blanks are only ever judged later, by each entity's Validate(), and only a Critical finding rejects the row.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:77-78 — `string raw = cells[j]?.Trim(); if (string.IsNullOrEmpty(raw)) continue;`

### MECHANISM.boolean-parsing — exactly which strings count as true

Case-INSENSITIVE (OrdinalIgnoreCase), trimmed first. TRUE: "1", "true", "yes", "y", "on", "نعم", "صح", "صحيح". FALSE: "0", "false", "no", "n", "off", "لا", "خطأ", "غلط". So "True", "TRUE", "true", "1", "yes", "Yes", "Y" ALL parse to true and are interchangeable. ANY OTHER non-blank string (e.g. "maybe", "2", "-", "x") returns null from IsTrue -> ChangeType returns null -> TsvParser's `if (converted != null)` guard skips the assignment -> the property SILENTLY keeps its declared default and NO error is recorded (no exception was thrown, so the per-cell catch never fires). A blank behaves identically to an unrecognised value. CONSOLE CONSEQUENCE: for the IS_* columns whose default is true, both "" and a typo silently mean TRUE.

**Accepted:** `1`, `true`, `yes`, `y`, `on`, `نعم`, `صح`, `صحيح`, `0`, `false`, `no`, `n`, `off`, `لا`, `خطأ`, `غلط`

*certain* — mbiXaddin/Core/Utils/SmartConverter.cs:42-46 (TrueValues), :49-53 (FalseValues), :293-304 (IsTrue returns null when unrecognised); mbiXaddin/Core/Utils/SmartConverter.cs:140-144 (bool converter returns null when IsTrue is null); mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:83 — `if (converted != null) prop.SetValue(obj, converted);`

### MECHANISM.blank-vs-error — when does a blank actually reject the row

A blank only rejects a row when the entity's Validate() returns a Critical finding for it. Fail and Warn findings are logged and the row is ACCEPTED. So the Console should hard-block only the Critical columns (the PKs and the two FKs listed below) and soft-warn the rest.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.Tier1Schema.cs:600-611 — `bool hasCritical = errors.Any(e => e.Severity == ValidationSeverity.Critical); if (hasCritical) { rejected++; ... continue; }` and :614-621 accepts rows with non-critical warnings

### MECHANISM.config-bag-columns (UX_CONFIG, SYS_CONFIG, RIBBON_CONFIG, EXPORT_CONFIG, LOGIC_CONFIG, CONTEXT_PROPS, PROCESS_CONFIG, VIEW_CONFIG, ALIASES)

A blank JSON bag is explicitly NOT an error. The raw string property stays null and ConfigResolver returns a fresh default-constructed config object. Note the two-stage default: blank bag -> `new T()` -> that T's own field initializers apply (named per column below).

*certain* — mbiXaddin/Core/Configuration/ConfigResolver.cs:64-65 — `if (string.IsNullOrWhiteSpace(rawJson)) return new T();` (preceded by the comment "Empty -> default config (not an error — many fields are optional)")

### MECHANISM.unknown-columns — Note, Drive, Excel, File, Folder

These five sheet columns are read by NOTHING. No entity declares a [JsonProperty] or property with those names anywhere in the ~350 .cs files. BuildPropertyMap only maps a header when it matches a property name, so these header indices are simply absent from the map and every cell in them is skipped by the `TryGetValue ... continue`. They are free-text scratch columns; the Console may treat them as unvalidated free text. Adding further unknown columns is safe (only a header row matching NOTHING aborts the parse).

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:140-148 (BuildPropertyMap maps only matching headers), :75 `if (!propMap.TryGetValue(j, out prop)) continue;`, :54-55 comment "a sheet that GAINS a column this build does not know about is normal and must keep working"; grep for JsonProperty("Note"|"Drive"|"Excel"|"File"|"Folder") returns zero hits

### TableDefinition.ENTITY_KEY

GENUINE ERROR. Blank leaves it as string.Empty, and Validate() yields Critical -> the row is REJECTED and all further validation for it is skipped (yield break).

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:146 `public string ENTITY_KEY { get; set; } = string.Empty;`; :438-445 ValidationResult.Critical + yield break

### TableDefinition.DISPLAY_NAME

Blank -> string.Empty. Validate() yields Fail (NOT Critical), so the row is ACCEPTED with a warning. CAUTION for the Console: the intended fallback is dead code. EffectiveLabel is `RIBBON_CONFIG?.Label ?? DISPLAY_NAME ?? ENTITY_KEY`, but because the initializer is string.Empty and not null, the `?? ENTITY_KEY` branch can never fire — a blank DISPLAY_NAME renders as an EMPTY ribbon label, not as ENTITY_KEY. Worth warning on.

**Blank means:** string.Empty (renders as an empty label; does NOT fall back to ENTITY_KEY)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:153 `= string.Empty`; :386 `public string EffectiveLabel => RIBBON_CONFIG?.Label ?? DISPLAY_NAME ?? ENTITY_KEY;`; :453-458 ValidationResult.Fail

### TableDefinition.ENTITY_TYPE

INHERITED, then null. The property is a nullable enum with no initializer, so blank -> null. MergeWithParent then copies the parent's ENTITY_TYPE when PARENT_KEY resolves. If there is no parent (or the parent's is also null) it stays null and Validate() yields Warn only — the row is accepted.

**Blank means:** null -> inherited from PARENT_KEY's row if present; otherwise stays null (Warn)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:159-161 `public EntityType? ENTITY_TYPE { get; set; }` (no initializer); :417 `if (ENTITY_TYPE == null) ENTITY_TYPE = parent.ENTITY_TYPE;`; :468-473 ValidationResult.Warn

### TableDefinition.LICENSE_TIER

Blank -> LicenseTier.Free. Then a security escalation applies: if the parent row's tier is higher it overwrites this one (higher tier always wins), so a blank on a child of a Premium parent effectively becomes Premium.

**Blank means:** LicenseTier.Free (raised to the parent's tier if the parent's is higher)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:167-169 `public LicenseTier LICENSE_TIER { get; set; } = LicenseTier.Free;`; :422-424 `if ((int)parent.LICENSE_TIER > (int)LICENSE_TIER) LICENSE_TIER = parent.LICENSE_TIER;`

### TableDefinition.IS_ACTIVE

Blank -> TRUE, not false. This is the most consequential blank in the sheet: an empty IS_ACTIVE means the table is ACTIVE.

**Blank means:** true

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:175-176 `public bool IS_ACTIVE { get; set; } = true;`

### TableDefinition.IS_VISIBLE

Blank -> TRUE. Combined with IS_ACTIVE in IsVisibleInMenu, where the RIBBON_CONFIG override also defaults to true when unset.

**Blank means:** true

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:184-185 `public bool IS_VISIBLE { get; set; } = true;`; :402 `IsVisibleInMenu => IS_ACTIVE && IS_VISIBLE && (RIBBON_CONFIG?.IsVisible ?? true)`

### TableDefinition.STORAGE_STRATEGY

Blank -> UpdateStrategy.MergeUpsert. This is a deliberately chosen SAFE default, not enum value 0: enum 0 is ReplaceAll, which would mean delete-all. TsvParser's header comment and its enum branch call this out explicitly — an invalid (not blank) value is recorded as an error and the property is left at MergeUpsert rather than being coerced to 0.

**Blank means:** UpdateStrategy.MergeUpsert

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:196-198 `public UpdateStrategy STORAGE_STRATEGY { get; set; } = UpdateStrategy.MergeUpsert;`; mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:9-10 and :160-163 ("NEVER silently coerced to enum value 0 (which for STORAGE_STRATEGY would mean ReplaceAll = delete-all)")

### TableDefinition.PARENT_KEY

Blank -> null, meaning the entity is a ROOT. No inheritance is applied. Legitimately blank for most rows — the Console must not flag it. (A non-blank value that does not match any ENTITY_KEY is only a logged warning, and inheritance is skipped.)

**Blank means:** null (treated as a root entity)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:205 `public string PARENT_KEY { get; set; }` (no initializer); :370 `public bool IsRoot => string.IsNullOrWhiteSpace(PARENT_KEY);`; mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:682-683 (inheritance only runs when the parent resolves)

### TableDefinition.VIEW_MODE

Blank -> ViewMode.Table.

**Blank means:** ViewMode.Table

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:215-217 `public ViewMode VIEW_MODE { get; set; } = ViewMode.Table;`

### TableDefinition.BUSINESS_DOMAIN

INHERITED, then null. Nullable enum with no initializer -> blank is null, then MergeWithParent copies the parent's value when PARENT_KEY resolves. No validation rule fires on a null BUSINESS_DOMAIN at all — it is entirely optional.

**Blank means:** null -> inherited from PARENT_KEY's row if present; otherwise null (no warning)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:228-230 `public BusinessDomain? BUSINESS_DOMAIN { get; set; }` (no initializer); :418 `if (BUSINESS_DOMAIN == null) BUSINESS_DOMAIN = parent.BUSINESS_DOMAIN;`

### TableDefinition.UX_CONFIG

Blank -> UX_CONFIG_RAW stays null -> ConfigResolver returns a default `new TableUxConfig()`, whose own fields (TabColor, Direction, FreezePanes, ZoomLevel, ShowGridlines, AutoFitColumns) are all null/nullable with no initializers. Additionally merged with the parent's UX_CONFIG when the parent is resolved. Not an error.

**Blank means:** new TableUxConfig() (all members null), merged with parent's

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:247-248 `public string UX_CONFIG_RAW { get; set; }`; :517-532 (TableUxConfig fields, all uninitialised nullables); mbiXaddin/Core/Configuration/ConfigResolver.cs:64-65; TableDefinitionEntity.cs:427 `if (parent.IsUxResolved) UX_CONFIG.Merge(parent.UX_CONFIG);`

### TableDefinition.SYS_CONFIG

Blank -> SYS_CONFIG_RAW null -> default `new TableSysConfig()` (AllowEdit, TeaserRowCount, TeaserText all null). Merged with the parent's SYS_CONFIG when the parent is resolved. Not an error.

**Blank means:** new TableSysConfig() (all members null), merged with parent's

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:275-276 `public string SYS_CONFIG_RAW { get; set; }`; :558-565 (TableSysConfig fields); :428 `if (parent.IsSysResolved) SYS_CONFIG.Merge(parent.SYS_CONFIG);`; ConfigResolver.cs:64-65

### TableDefinition.RIBBON_CONFIG

Blank -> RIBBON_CONFIG_RAW null -> default RibbonDisplayConfig. Inherited: when the parent is ribbon-resolved and this row is not, the parent's config is merged in. Its IsVisible member is treated as true when unset.

**Blank means:** default RibbonDisplayConfig, merged from parent when the parent has one

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:301-302 `public string RIBBON_CONFIG_RAW { get; set; }`; :419-421 `if (parent.IsRibbonResolved && !IsRibbonResolved) RIBBON_CONFIG = RIBBON_CONFIG.MergeWith(parent.RIBBON_CONFIG);`; :402 `(RIBBON_CONFIG?.IsVisible ?? true)`

### TableDefinition.EXPORT_CONFIG

Blank -> EXPORT_CONFIG_RAW null -> default ExportConfig. NOT inherited — unlike UX/SYS/RIBBON, EXPORT_CONFIG is absent from MergeWithParent, so a child never picks up its parent's export settings.

**Blank means:** new ExportConfig() (no parent inheritance)

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:336-337 `public string EXPORT_CONFIG_RAW { get; set; }`; :413-429 MergeWithParent — no EXPORT_CONFIG branch; ConfigResolver.cs:64-65

### SchemaRule.ENTITY_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED (yield break skips all further checks).

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:237 `= string.Empty`; :464-470 Critical + yield break (the block ending at :470-471)

### SchemaRule.ATTRIBUTE_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED.

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:244 `= string.Empty`; :473-481 `ValidationResult.Critical(nameof(ATTRIBUTE_KEY), ...)` + yield break

### SchemaRule.DISPLAY_HEADER

Blank -> string.Empty. Validate() yields Fail (NOT Critical), so the row is ACCEPTED and the Excel column simply gets an empty header. The in-app schema guide documents the same default.

**Blank means:** string.Empty

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:255 `= string.Empty`; :489-494 ValidationResult.Fail; mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:322 (documents default `"" (empty)`)

### SchemaRule.ORDINAL_POS

Blank -> 0. A negative value (not a blank) draws a Warn saying "Value 0 will be used". Many rows legitimately leave this blank and all such columns tie at 0.

**Blank means:** 0

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:261-262 `public int ORDINAL_POS { get; set; } = 0;`; :496-501 Warn for negatives

### SchemaRule.LICENSE_TIER

Blank -> LicenseTier.Free. Unlike TableDefinition.LICENSE_TIER there is no parent-escalation for column tiers.

**Blank means:** LicenseTier.Free

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:268-270 `public LicenseTier LICENSE_TIER { get; set; } = LicenseTier.Free;`

### SchemaRule.SEMANTIC_ROLE

Blank -> SemanticRole.NONE. NONE is an explicit member of the enum meaning 'no special engine meaning', so a blank is completely legitimate for ordinary data columns and must not be flagged.

**Blank means:** SemanticRole.NONE

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:281-283 `public SemanticRole SEMANTIC_ROLE { get; set; } = SemanticRole.NONE;`; mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:330 ("CRITICAL for engine columns, OPTIONAL for general data")

### SchemaRule.DATA_TYPE

Blank -> ColumnDataType.TEXT. Note the enum branch also normalises user aliases before parsing, so a non-blank "Boolean"/"String"/"Integer"/"Number"/"Float"/"Double"/"Varchar"/"Nvarchar"/"Numeric"/"Bit"/"Char" is accepted and mapped to BOOL/TEXT/INT/DECIMAL.

**Blank means:** ColumnDataType.TEXT

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:290-292 `public ColumnDataType DATA_TYPE { get; set; } = ColumnDataType.TEXT;`; mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:186-198 (NormalizeEnumAlias)

### SchemaRule.IS_PK

Blank -> FALSE. (Contrast with IS_VISIBLE on the same sheet, which defaults to true.)

**Blank means:** false

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:299-300 `public bool IS_PK { get; set; } = false;`

### SchemaRule.IS_MANDATORY

Blank -> FALSE.

**Blank means:** false

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:348-349 `public bool IS_MANDATORY { get; set; } = false;`

### SchemaRule.IS_VIRTUAL

Blank -> FALSE (the column IS stored in SQLite).

**Blank means:** false

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:357-358 `public bool IS_VIRTUAL { get; set; } = false;`

### SchemaRule.IS_DERIVED

Blank -> FALSE (the value comes from the source, not from LOGIC_CONFIG.Formula).

**Blank means:** false

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:366-367 `public bool IS_DERIVED { get; set; } = false;`

### SchemaRule.IS_VISIBLE

Blank -> TRUE. Note the asymmetry the Console must respect: on this sheet IS_PK/IS_MANDATORY/IS_VIRTUAL/IS_DERIVED all default to false, but IS_VISIBLE defaults to true.

**Blank means:** true

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:374-375 `public bool IS_VISIBLE { get; set; } = true;`

### SchemaRule.UX_CONFIG

Blank -> UX_CONFIG_RAW null -> default `new ColumnUxConfig()`, whose members (Width, Format, Align, HeaderColor, WrapText, AutoFit) are all uninitialised nullables. Not an error.

**Blank means:** new ColumnUxConfig() (all members null)

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:387-388 `public string UX_CONFIG_RAW { get; set; }`; :590-605 (ColumnUxConfig members); mbiXaddin/Core/Configuration/ConfigResolver.cs:64-65

### SchemaRule.LOGIC_CONFIG

Blank -> LOGIC_CONFIG_RAW null -> default `new ColumnLogicConfig()` (Min, Max, Formula, LookupRef, DefaultVal, ListSource, ListItems, ListStrict — all uninitialised null). Not an error.

**Blank means:** new ColumnLogicConfig() (all members null)

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:411-412 `public string LOGIC_CONFIG_RAW { get; set; }`; :648-695 (ColumnLogicConfig members); ConfigResolver.cs:64-65

### DataSource.SOURCE_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED, and the message states all further validation for the row is skipped.

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:101 `= string.Empty`; :291-302 Critical + yield break

### DataSource.TARGET_ENTITY_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED. (Unlike SOURCE_KEY it does not yield break, so other findings still accumulate, but the Critical alone rejects the row.)

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:109 `= string.Empty`; :304-313 `ValidationResult.Critical(nameof(TARGET_ENTITY_KEY), ...)`

### DataSource.PROFILE_KEY

Blank -> string.Empty. Validate() yields Fail, NOT Critical — so the row is ACCEPTED, but no column mapping can be resolved from DataMap and the table ends up EMPTY after sync. A silent-empty-table trap: the Console should warn strongly even though the add-in does not reject it.

**Blank means:** string.Empty (row accepted; sync yields an empty table)

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:118 `= string.Empty`; :316-329 `ValidationResult.Fail(nameof(PROFILE_KEY), ... "no column can be mapped and the table will be empty after sync")`

### DataSource.SOURCE_REGION

Blank -> string.Empty, which is explicitly treated as NO GEOGRAPHIC RESTRICTION — i.e. equivalent to GLOBAL, available to every user. Validation skips the check entirely when blank (the format rule only runs for non-blank values). Legitimately blank; do not flag.

**Blank means:** string.Empty == no restriction (behaves as GLOBAL)

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:127 `= string.Empty`; mbiXaddin/Core/Security/SecurityContext.cs:238-239 `// A source with no geographic restriction -> available to everyone` / `if (string.IsNullOrWhiteSpace(sourceRegion)) return true;`; DataSourceEntity.cs:335-337 (`if (!string.IsNullOrWhiteSpace(SOURCE_REGION))` guard)

### DataSource.SOURCE_URI

GENUINE ERROR on the live sheet. Blank -> string.Empty and SourceUriValidator yields Critical -> row REJECTED. IMPORTANT EXCEPTION: SOURCE_URI is deliberately never persisted to SQLite, so on the offline read-back path it is passed in skipValidationFields and its Critical is filtered out — otherwise every offline read would reject every source row. The Console edits the sheet, so for Console purposes: blank = hard error.

**Blank means:** string.Empty, then row rejected (Critical) on the sheet path

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:141 `= string.Empty`; mbiXaddin/Core/Validation/SourceUriValidator.cs:30-39 Critical + yield break; mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.Tier1Schema.cs:586-594 (skipValidationFields filter, comment names SOURCE_URI)

### DataSource.VERSION_TAG

Blank -> null (no initializer). Not validated at all — completely optional. Downstream, the change-detection fingerprint substitutes the literal string "0" for a null tag, so all blank-tag sources share the same tag component and change detection then rests on the other fingerprint inputs.

**Blank means:** null (fingerprinted as the string "0")

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:149-150 `public string VERSION_TAG { get; set; }` (no initializer); mbiXaddin/Infrastructure/Services/Ingestion/IngestionFingerprint.cs:40 `sb.Append(source.VERSION_TAG ?? "0").Append('|');`; mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:712 `Version={source.VERSION_TAG ?? "null"}`

### DataSource.DISPLAY_LABEL

Blank -> string.Empty; Validate() yields Warn only, so the row is accepted. CAUTION: the documented fallback is dead code. Four call sites write `DISPLAY_LABEL ?? SOURCE_KEY` or `?? PROFILE_KEY`, but the initializer is string.Empty and not null, so the `??` never fires and the UI/log shows an EMPTY label rather than the key. Only EtlInfoBuilder tests it correctly with IsNullOrEmpty. The Console should treat blank as cosmetically harmful.

**Blank means:** string.Empty (renders empty; the `?? SOURCE_KEY` fallback cannot fire)

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:157 `= string.Empty`; :395 `$"[{TARGET_ENTITY_KEY}/{PROFILE_KEY}] {DISPLAY_LABEL ?? SOURCE_KEY}"`; mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:312 and :404 (`?? prep.Source.PROFILE_KEY`); mbiXaddin/UI/Commands/RibbonContentBuilder.cs:280 (`?? src.SOURCE_KEY`); mbiXaddin/UI/TaskPane/EtlInfoBuilder.cs:417-418 and :471-472 (correct IsNullOrEmpty check); DataSourceEntity.cs:360-372 Warn

### DataSource.MIN_LICENSE_REQ

Blank -> LicenseTier.Free. Applied IN ADDITION to the table's own LICENSE_TIER, so a blank here does not weaken the table-level gate.

**Blank means:** LicenseTier.Free

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:167-169 `public LicenseTier MIN_LICENSE_REQ { get; set; } = LicenseTier.Free;`; mbiXaddin/Core/Security/SecurityContext.cs:203-208 (CanSyncSource checks tier weight then region); mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:399

### DataSource.IS_ACTIVE

Blank -> TRUE. The source will be synced. (A non-blank false is not an error either — it produces an informational Warn explaining the table will appear empty.)

**Blank means:** true

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:176-177 `public bool IS_ACTIVE { get; set; } = true;`; :374-386 Warn when false

### DataSource.CONTEXT_PROPS

Blank -> CONTEXT_PROPS_RAW null -> default `new SourceContextProps()` with real, named initializers: SourceType=GoogleSheetTsv, SyncFreq=Manual, SkipRows=0, Encoding="UTF-8", Delimiter=",", TimeoutSeconds=30. Only SkipRows is actually read by the pipeline; the other five are stored but not applied.

**Blank means:** new SourceContextProps(): SourceType=GoogleSheetTsv, SyncFreq=Manual, SkipRows=0, Encoding="UTF-8", Delimiter=",", TimeoutSeconds=30

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:188-189 `public string CONTEXT_PROPS_RAW { get; set; }`; :413 `= SourceType.GoogleSheetTsv`, :420 `= SyncFrequency.Manual`, :427 `= 0`, :434 `= "UTF-8"`, :441 `= ","`, :447 `= 30`; mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:404 ("SkipRows is the ONLY key the pipeline reads")

### DataSource.Note

NEVER READ. No property with this name exists in any entity; the header does not match anything in BuildPropertyMap, so every cell in the column is skipped. Blank and non-blank are equally inert. Free text — the Console needs no validation here.

**Blank means:** n/a — column is not read

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:140-148 (map built only from matching headers), :75 (`continue` on unmapped index); grep for `JsonProperty("Note")` across all .cs returns zero hits

### DataSource.Drive

NEVER READ. Same as Note — no matching property anywhere, so the column is skipped entirely by the parser.

**Blank means:** n/a — column is not read

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:140-148 and :75; grep for `JsonProperty("Drive")` across all .cs returns zero hits

### DataMap.PROFILE_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED (yield break).

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:124 `= string.Empty`; :235-243 Critical + yield break

### DataMap.TARGET_ATTRIBUTE_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED (yield break).

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:132 `= string.Empty`; :246-253 Critical + yield break

### DataMap.SOURCE_TYPE

Blank -> MapSourceType.Header. This is the overwhelmingly common case (the schema guide notes Header covers ~90% of rows), so a blank is normal and must not be flagged.

**Blank means:** MapSourceType.Header

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:143-145 `public MapSourceType SOURCE_TYPE { get; set; } = MapSourceType.Header;`; mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:420 ("Header (90%), Index, Context, Constant, Formula")

### DataMap.MATCH_MODE

Blank -> MapMatchMode.Exact. Only meaningful when SOURCE_TYPE=Header; a non-Exact value on a non-Header row draws a Warn. Because the blank default IS Exact, leaving it blank on a non-Header row is the correct, warning-free choice.

**Blank means:** MapMatchMode.Exact

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:153-155 `public MapMatchMode MATCH_MODE { get; set; } = MapMatchMode.Exact;`; :264-272 Warn when SOURCE_TYPE != Header && MATCH_MODE != Exact

### DataMap.SOURCE_EXPRESSION

Blank -> string.Empty. Validate() yields Fail (NOT Critical) -> the row is ACCEPTED but the mapping cannot locate a source value. The Index-type integer check is skipped when blank (guarded by IsNullOrWhiteSpace).

**Blank means:** string.Empty (row accepted, mapping non-functional)

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:167 `= string.Empty`; :256-262 ValidationResult.Fail; :275-276 (`SOURCE_TYPE == Index && !string.IsNullOrWhiteSpace(SOURCE_EXPRESSION)` guard)

### DataMap.TRANSFORM_CHAIN

Blank -> null; HasTransform is false and NO transform is applied — the raw source value passes through. Entirely optional; the whole validation block is guarded by IsNullOrWhiteSpace so a blank produces no finding at all.

**Blank means:** null — no transform applied

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:180-181 `public string TRANSFORM_CHAIN { get; set; }` (no initializer); :219 `public bool HasTransform => !string.IsNullOrWhiteSpace(TRANSFORM_CHAIN);`; :287-288 (`if (!string.IsNullOrWhiteSpace(TRANSFORM_CHAIN))` guard)

### DataMap.PROCESS_CONFIG

Blank -> PROCESS_CONFIG_RAW null -> default `new MapProcessConfig()` with named initializers: NullStrategy="Skip", ErrorStrategy="Skip", AutoTrim=true, DefaultValue=null, RowFilter=null. So a blank means: nulls skipped, errors skipped, values auto-trimmed.

**Blank means:** new MapProcessConfig(): NullStrategy="Skip", ErrorStrategy="Skip", AutoTrim=true, DefaultValue=null, RowFilter=null

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:191-192 `public string PROCESS_CONFIG_RAW { get; set; }`; :361 `= "Skip"`, :367 (DefaultValue, no initializer), :374 `= "Skip"`, :381 `= true`, :395-396 (RowFilter, no initializer); mbiXaddin/Core/Configuration/ConfigResolver.cs:64-65

### ExportViews.VIEW_KEY

GENUINE ERROR. Blank -> null (no initializer), Validate() yields Critical -> row REJECTED (yield break).

**Blank means:** null, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:61-62 `public string VIEW_KEY { get; set; }` (no initializer); :306-314 Critical + yield break

### ExportViews.ENTITY_KEY

GENUINE ERROR. Blank -> null, Validate() yields Critical -> row REJECTED (the parent entity cannot be determined).

**Blank means:** null, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:68-69 `public string ENTITY_KEY { get; set; }` (no initializer); :317-322 `ValidationResult.Critical(nameof(ENTITY_KEY), ...)`

### ExportViews.LABEL

Blank -> null, and here the fallback GENUINELY WORKS: EffectiveLabel is `LABEL ?? VIEW_KEY`, and because LABEL has no initializer it really is null, so VIEW_KEY is used as the button text. Validate() yields Warn only. Contrast with TableDefinition.DISPLAY_NAME and DataSource.DISPLAY_LABEL, where the same idiom is defeated by a string.Empty initializer.

**Blank means:** null -> falls back to VIEW_KEY

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:80-81 `public string LABEL { get; set; }` (no initializer); :285 `public string EffectiveLabel => LABEL ?? VIEW_KEY;`; :324-329 Warn ("VIEW_KEY will be used as button text")

### ExportViews.SCREEN_TIP

Blank -> null. No validation rule references it; purely optional tooltip text.

**Blank means:** null (no tooltip)

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:87-88 `public string SCREEN_TIP { get; set; }` (no initializer); :304-345 Validate() contains no SCREEN_TIP check

### ExportViews.SUPER_TIP

Blank -> null. No validation rule references it; purely optional.

**Blank means:** null (no tooltip)

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:94-95 `public string SUPER_TIP { get; set; }` (no initializer); :304-345 Validate() contains no SUPER_TIP check

### ExportViews.ICON

Blank -> null, which means the default icon is used. Not validated. IconRef.Apply is called with the possibly-null value.

**Blank means:** null -> default icon

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:101-102 `public string ICON { get; set; }` (no initializer); mbiXaddin/UI/Commands/RibbonContentBuilder.cs:354 `IconRef.Apply(btn, view.ICON, ...)`; mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:291 (documents `null — default icon`)

### ExportViews.COLUMNS

Blank -> null, which explicitly means SHOW ALL COLUMNS. This is a meaningful, common blank — flagging it would be wrong. (A non-blank value that parses to zero entries draws a Warn, but a blank does not.)

**Blank means:** null == show all columns

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:113-114 `public string COLUMNS { get; set; }` (no initializer); :265 `public bool ShowAllColumns => string.IsNullOrEmpty(COLUMNS);`; :190-193 comment "null = show all columns"; :331-336 Warn guarded by `!string.IsNullOrEmpty(COLUMNS)`

### ExportViews.ALIASES

Blank -> ALIASES_RAW null -> Aliases resolves to null -> no aliases, so each column keeps its SchemaRule DISPLAY_HEADER. GetColumnAlias returns null (deliberately, so the header fallback chain works). Not an error.

**Blank means:** null -> no aliases; DISPLAY_HEADER used

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:121-122 `public string ALIASES_RAW { get; set; }`; :217-233 (Aliases via JsonSafeParser.TryParse); :288-297 GetColumnAlias returns null when absent; :273 `HasAliases => Aliases != null && Aliases.Count > 0`

### ExportViews.WHERE_FILTER

Blank -> null -> HasFilter is false -> no row filter, the view exports all rows. Legitimately blank.

**Blank means:** null -> no filter

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:133-134 `public string WHERE_FILTER { get; set; }` (no initializer); :277 `public bool HasFilter => !string.IsNullOrEmpty(WHERE_FILTER);`

### ExportViews.SORT_BY

Blank -> null -> HasSortBy is false -> no explicit sort applied. Legitimately blank.

**Blank means:** null -> no sort

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:140-141 `public string SORT_BY { get; set; }` (no initializer); :281 `public bool HasSortBy => !string.IsNullOrEmpty(SORT_BY);`

### ExportViews.IS_ACTIVE

Blank -> TRUE. The view is active.

**Blank means:** true

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:170-171 `public bool IS_ACTIVE { get; set; } = true;`

### ExportViews.VIEW_CONFIG

Blank -> VIEW_CONFIG_RAW null -> JsonSafeParser.TryParse yields a default ExportConfig (documented as never null / empty bag when unset). LinkedViews is then null and HasLinkedEntities false. Not an error.

**Blank means:** default ExportConfig (empty bag); no linked entities

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:184-185 `public string VIEW_CONFIG_RAW { get; set; }`; :236-251 (VIEW_CONFIG getter, comment "Never null (empty bag when unset)"); :256 LinkedViews; :269 HasLinkedEntities

### RibbonControls.ITEM_KEY

GENUINE ERROR. Blank -> string.Empty, Validate() yields Critical -> row REJECTED (yield break). The SQLite read path rejects it even earlier, returning null from ParseRow before building the entity.

**Blank means:** string.Empty, then row rejected (Critical)

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:92-93 `= string.Empty`; :420-428 Critical + yield break; mbiXaddin/UI/Commands/RibbonControlService.cs:507-508 `if (string.IsNullOrWhiteSpace(key)) return null;`

### RibbonControls.CONTROL_KEY

Blank -> "mnuDynamic", applied consistently in all three places: the entity initializer, the EffectiveControlKey accessor, and the SQLite ParseRow. Validate() yields Warn only and names the default explicitly.

**Blank means:** "mnuDynamic"

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:109-110 `public string CONTROL_KEY { get; set; } = "mnuDynamic";`; :358-360 `EffectiveControlKey => string.IsNullOrWhiteSpace(CONTROL_KEY) ? "mnuDynamic" : CONTROL_KEY.Trim();`; mbiXaddin/UI/Commands/RibbonControlService.cs:509 `CONTROL_KEY = SafeStr(row, "CONTROL_KEY") ?? "mnuDynamic"`; RibbonControlEntity.cs:436-442 Warn

### RibbonControls.REGION

Blank -> "GLOBAL" (visible everywhere). Applied by the entity initializer and again by ParseRow. IsGlobal also treats an empty REGION as global. Validate() yields Warn only and names the default. Note the format check is skipped for blank, and a non-blank value may be comma-separated ("EG,SA").

**Blank means:** "GLOBAL"

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:148-149 `public string REGION { get; set; } = "GLOBAL";`; :344-347 `IsGlobal => string.IsNullOrEmpty(REGION) || REGION.Equals("GLOBAL", ...)`; mbiXaddin/UI/Commands/RibbonControlService.cs:510 `REGION = SafeStr(row, "REGION") ?? "GLOBAL"`; RibbonControlEntity.cs:450-455 Warn

### RibbonControls.PARENT_KEY

Blank -> null, meaning a TOP-LEVEL item. Legitimately blank for every root control; only a self-reference (ITEM_KEY == PARENT_KEY) is Critical, never a blank.

**Blank means:** null == top-level item

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:123-124 `public string PARENT_KEY { get; set; }` (no initializer); :341 `public bool IsTopLevel => string.IsNullOrEmpty(PARENT_KEY);`; :495-501 Critical only for a circular self-reference

### RibbonControls.ORDER

Blank -> 0. Both paths agree: the int property has no initializer (so 0), and SafeInt returns 0 for a null/unparseable cell. Blank rows therefore all tie at 0 and fall back to whatever secondary ordering applies.

**Blank means:** 0

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:131-132 `public int ORDER { get; set; }` (no initializer); mbiXaddin/UI/Commands/RibbonControlService.cs:1412-1416 `SafeInt` returns 0 when null or not parseable

### RibbonControls.ACTION_CLASS

Blank -> "Export". Both the entity initializer and ParseRow apply it, and the ParseRow comment records that this was corrected from an earlier default that ActionRouter never accepted. Validate() yields Fail (NOT Critical), so a blank row is still accepted and behaves as an Export.

**Blank means:** "Export"

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:176-177 `public string ACTION_CLASS { get; set; } = "Export";`; mbiXaddin/UI/Commands/RibbonControlService.cs:518-521 `ACTION_CLASS = SafeStr(row, "ACTION_CLASS") ?? "Export"` with the correcting comment; RibbonControlEntity.cs:470-476 Fail

### RibbonControls.ACTION_TAG

Blank -> null. CONDITIONAL: for a menu-producing row (ACTION_CLASS in Menu/Library/ExportTree/ViewList) a blank is correct and a non-blank draws a Warn saying it will be ignored. For any other (clickable) row a blank yields Fail — accepted but the button has nothing to execute. EntityKeyFromTag / ViewKeyFromTag both return null.

**Blank means:** null — required (Fail) for clickable rows, correct for menu rows

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:216-217 `public string ACTION_TAG { get; set; }` (no initializer); :478-485 Fail when `!IsMenuContainer && string.IsNullOrWhiteSpace(ACTION_TAG)`; :487-493 Warn when IsMenuContainer and set; :336 MenuActionClasses = { "Menu", "Library", "ExportTree", "ViewList" }; :371-379 EntityKeyFromTag returns null

### RibbonControls.MENU_LAYOUT

Blank -> MenuLayout.Nested, and the parser deliberately does NOT flag a blank as unrecognised — the code comments say a blank means 'no opinion, use the default' and that flagging it would fire a warning on every row. Kept as a string on the entity (not an enum property) because the SQLite hop reads every column as a string; it is parsed at the point of use. A blank is never an error.

**Blank means:** MenuLayout.Nested (blank is explicitly not flagged)

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:197-198 `public string MENU_LAYOUT { get; set; } = null;`; mbiXaddin/Core/UI/MenuLayout.cs:100 `public const MenuLayout Default = MenuLayout.Nested;`, :115 `if (string.IsNullOrWhiteSpace(raw)) return Default;`, :105-110 (comment: "A BLANK cell is not a defect"); mbiXaddin/UI/Commands/RibbonControlService.cs:525 `MENU_LAYOUT = SafeStr(row, "MENU_LAYOUT")`

### RibbonControls.LABEL

Blank -> null. CONDITIONAL: for a menu container it yields Warn — the code states menus, unlike buttons, cannot inherit a label, so a blank leaves the menu unlabelled. For non-menu (button) rows a blank is not flagged at all, because a button's label is resolved from the referenced entity/view.

**Blank means:** null — inherited for buttons; unlabelled (Warn) for menu containers

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:229-230 `public string LABEL { get; set; }` (no initializer); :503-508 `if (IsMenuContainer && string.IsNullOrWhiteSpace(LABEL))` Warn ("Unlike buttons, menus cannot inherit labels"); mbiXaddin/UI/Commands/RibbonControlService.cs:526

### RibbonControls.SCREEN_TIP

Blank -> null. Not validated; optional tooltip.

**Blank means:** null (no tooltip)

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:236-237 `public string SCREEN_TIP { get; set; }` (no initializer); mbiXaddin/UI/Commands/RibbonControlService.cs:527 `SCREEN_TIP = SafeStr(row, "SCREEN_TIP")`; :418-510 Validate() contains no SCREEN_TIP check

### RibbonControls.SUPER_TIP

Blank -> null. Not validated; optional.

**Blank means:** null (no tooltip)

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:243-244 `public string SUPER_TIP { get; set; }` (no initializer); mbiXaddin/UI/Commands/RibbonControlService.cs:528 `SUPER_TIP = SafeStr(row, "SUPER_TIP")`

### RibbonControls.ICON

Blank -> null -> the default icon is used. Not validated.

**Blank means:** null -> default icon

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:252-253 `public string ICON { get; set; }` (no initializer); mbiXaddin/UI/Commands/RibbonControlService.cs:529 `ICON = SafeStr(row, "ICON")`; mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:291 (documents `null — default icon`)

### RibbonControls.IS_ACTIVE

Blank -> TRUE on the sheet path. Note an asymmetry worth knowing: the SQLite read path does not read the column at all — ParseRow hardcodes IS_ACTIVE = true, so once a row is persisted it is unconditionally active on that path regardless of the stored value.

**Blank means:** true

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:265-266 `public bool IS_ACTIVE { get; set; } = true;`; mbiXaddin/UI/Commands/RibbonControlService.cs:531 `IS_ACTIVE = true` (hardcoded, not read from the row)

### RibbonControls.Excel

NEVER READ. No property with this name exists; the header matches nothing in BuildPropertyMap and every cell is skipped. Free text.

**Blank means:** n/a — column is not read

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:140-148 and :75; grep for `JsonProperty("Excel")` across all .cs returns zero hits; mbiXaddin/UI/Commands/RibbonControlService.cs:505-532 ParseRow hand-lists every column read and does not include it

### RibbonControls.File

NEVER READ. No matching property; the column is skipped entirely by the parser and is absent from ParseRow's hand-written column list.

**Blank means:** n/a — column is not read

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:140-148 and :75; grep for `JsonProperty("File")` across all .cs returns zero hits; mbiXaddin/UI/Commands/RibbonControlService.cs:505-532

### RibbonControls.Folder

NEVER READ. No matching property; skipped by the parser and absent from ParseRow.

**Blank means:** n/a — column is not read

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:140-148 and :75; grep for `JsonProperty("Folder")` across all .cs returns zero hits; mbiXaddin/UI/Commands/RibbonControlService.cs:505-532

### ExportViews.GROUP_NAME / ExportViews.SORT_ORDER (entity properties with no column in the live sheet)

NOT-FOUND in the sheet, but present in the entity: the ExportViewEntity declares GROUP_NAME (string, no initializer -> null) and SORT_ORDER (int, no initializer -> 0). Since the live sheet has no such headers, these always hold their defaults. Flagged because the Console could usefully add them, and because a Console that writes headers must not assume the entity and the sheet are the same set.

**Blank means:** GROUP_NAME=null, SORT_ORDER=0 (columns absent from the sheet)

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:152-153 `[JsonProperty("GROUP_NAME")] public string GROUP_NAME { get; set; }`; :159-160 `[JsonProperty("SORT_ORDER")] public int SORT_ORDER { get; set; }`

### DataSource.RIBBON_CONFIG (entity property with no column in the live sheet)

NOT-FOUND in the sheet, but present in the entity: DataSourceEntity declares RIBBON_CONFIG_RAW mapped to header "RIBBON_CONFIG". The live DataSource sheet has no such column, so it is always null -> default RibbonDisplayConfig. Its ControlSize is validated against ConfigVocabulary.ControlSizes when present.

**Blank means:** null -> default RibbonDisplayConfig (column absent from the sheet)

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:214-215 `[JsonProperty("RIBBON_CONFIG")] public string RIBBON_CONFIG_RAW { get; set; }`; :391 ConfigValidator.ValidateAllowed("RIBBON_CONFIG", "ControlSize", ...)


## the-views-and-ribbon

### ExportViews.COLUMNS — what syntax? Is it comma-separated attribute keys?

Comma-separated ATTRIBUTE_KEYs, whitespace-trimmed, empty entries dropped. ONLY the comma is a separator (no semicolon/newline/pipe support). Free-form strings — no vocabulary in code; each token must equal a SchemaRule.ATTRIBUTE_KEY of that entity (case-insensitive). Blank/empty cell = show ALL columns (ShowAllColumns, ExportViewEntity.cs:265). IMPORTANT: COLUMNS is a FILTER, not an order — the column order always comes from SchemaRule.ORDINAL_POS (ExportEngine.cs:1196 `.OrderBy(c => c.ORDINAL_POS)` runs before the filter at :1199-1203), so listing "RATE,ITEM" still renders ITEM first if its ORDINAL_POS is lower.

**Blank means:** null/empty = all visible, non-virtual columns are exported (ShowAllColumns)

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:202 — `_columnList = COLUMNS.Split(',').Select(c => c.Trim())` (:203 `.Where(c => !string.IsNullOrEmpty(c)).ToList();`); ExportViewEntity.cs:265 — `public bool ShowAllColumns => string.IsNullOrEmpty(COLUMNS);`

### Must each COLUMNS name exist in SchemaRule for that entity? What happens if one does not?

It is not required and it is NOT validated anywhere — an unknown name is silently ignored. The engine builds the visible-column list from SchemaRule (non-virtual + IS_VISIBLE, or everything for Admin) and then INTERSECTS it with COLUMNS using a case-insensitive HashSet. A name that matches nothing simply contributes nothing; there is no warning, no log line, no alert. Note the same silent drop applies to a name that DOES exist but is IS_VIRTUAL=true or IS_VISIBLE=false (non-Admin) — it is removed before the intersection. The only COLUMNS validation in the whole codebase is a format check that fires only when a non-empty cell parses to zero entries (ExportViewEntity.cs:332-336, Warning, code InvalidFormat).

*certain* — mbiXaddin/Infrastructure/Engines/ExportEngine.cs:1201 — `var allowed = new HashSet<string>(view.ColumnList, StringComparer.OrdinalIgnoreCase);` / :1202 — `cols = cols.Where(c => allowed.Contains(c.ATTRIBUTE_KEY)).ToList();` (filter of the list built at :1194-1197)

### What if EVERY name in COLUMNS is unknown (e.g. one typo per name, or the wrong entity's columns)?

The intersection yields zero columns and the export ABORTS silently mid-render: RenderInternal logs a warning whose text names the wrong cause ("No visible columns for current user tier") and returns. The worksheet has already been created (RenderToSheet order: LoadFromSqlite → CreateSheet → RenderInternal), so the user gets a brand-new, completely blank sheet named after the view, with no error dialog. This is the single worst failure mode in this cluster for a Console to prevent.

*certain* — mbiXaddin/Infrastructure/Engines/ExportEngine.cs:258-262 — `if (visibleCols.Count == 0) { _log.LogWarning($"[{entityKey}] No visible columns for current user tier.", SourceName); return; }`; sheet already created at ExportEngine.cs:112 — `var sheet = CreateSheet(ctx, view);`

### ALIASES — is it the same length as COLUMNS? What separator, and what if they disagree?

NOT a parallel list — the premise of the question does not hold. ALIASES is a JSON OBJECT mapping ATTRIBUTE_KEY → display header: {"RATE_2021":"Rate","ITEM_NAME":"Item"}. There is no separator and no length relationship with COLUMNS; they cannot 'disagree'. Keys not in COLUMNS are simply never looked up; columns with no alias key fall back to DISPLAY_HEADER then to the raw ATTRIBUTE_KEY. An alias whose VALUE is an empty string is treated as 'no alias' (GetColumnAlias returns null, ExportViewEntity.cs:296). Keys are matched case-SENSITIVELY (plain Dictionary<string,string>, no comparer), unlike COLUMNS — a Console should emit keys with the exact ATTRIBUTE_KEY casing.

**Blank means:** empty dictionary → every header falls back to DISPLAY_HEADER, then ATTRIBUTE_KEY

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:121-122 — `[JsonProperty("ALIASES")] public string ALIASES_RAW { get; set; }` with :119 doc `Example: {"RATE_2021": "Rate", "ITEM_NAME": "Item"}`; :228 — `_aliases = JsonSafeParser.TryParse<Dictionary<string, string>>(ALIASES_RAW, VIEW_KEY, "ALIASES_RAW");`; ExportEngine.cs:483 — `headers[i] = ExportNaming.ResolveHeader(alias, col.DISPLAY_HEADER, col.ATTRIBUTE_KEY);`

### ALIASES — what happens on invalid JSON (e.g. a human writes a comma list)?

The parse fails safe: JsonSafeParser catches and returns an EMPTY dictionary (never null), logs a warning with an 80-char preview, and every header falls back to DISPLAY_HEADER — the export still succeeds, just unrenamed. Separately, entity validation runs ConfigValidator.ValidateBag<object> on the raw cell, which checks JSON SYNTAX ONLY (L1) and yields an Error with code INVALID_JSON that becomes a persistent ETL alert. Passing `object` as T deliberately disables the unknown-key check, because alias keys are arbitrary column names.

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:339 — `foreach (var r in ConfigValidator.ValidateBag<object>("ALIASES", ALIASES_RAW)) yield return r;`; mbiXaddin/Core/Utils/JsonSafeParser.cs:106-110 — `catch (JsonException ex) { LogParseFailure(...); return new T(); }`; mbiXaddin/Core/Configuration/ConfigValidator.cs:75 — `if (known.Count == 0) yield break;   // unknown shape (T == object) — skip key check`

### WHERE_FILTER — what expression language? Where is the parser?

There is NO custom expression language and NO parser in this repository. WHERE_FILTER is a RAW SQLite WHERE-clause body, concatenated verbatim into `SELECT * FROM [Entity] WHERE <filter>` and handed to System.Data.SQLite — SQLite's own parser is the only validator. The sole sanitization is CleanFragment: trim, then truncate at the FIRST ';' so the fragment cannot chain a second statement. Nothing else is checked — not identifiers, not operators, not balance of quotes/parens. Confirmed by the file header comment: the fragments are treated as trusted metadata and 'appended verbatim'.

**Blank means:** blank → no WHERE clause at all (all rows)

*certain* — mbiXaddin/Infrastructure/Database/ExportQuerySql.cs:41 — `if (where.Length > 0) sql.Append(" WHERE ").Append(where);`; :61-62 — `int semicolon = f.IndexOf(';'); if (semicolon >= 0) f = f.Substring(0, semicolon).Trim();`; called from ExportEngine.cs:1278 — `var sql = ExportQuerySql.BuildSelect(entityKey, whereFilter, sortBy, MaxExportRows + 1);`

### WHERE_FILTER — what is the complete operator set, and what are real examples?

The complete operator set is SQLite's, not the add-in's — the code defines none, so any SQLite expression is accepted: = <> != < <= > >= , AND OR NOT, LIKE / GLOB / REGEXP(unregistered→error) / MATCH, IN (...), BETWEEN … AND …, IS NULL / IS NOT NULL, ||, arithmetic, CASE, subqueries, and any built-in SQLite function. Do NOT confuse this with ConfigVocabulary.RowFilterOperators (EQ, NEQ, GT, LT, GTE, LTE, CONTAINS, NOT_CONTAINS, NOT_EMPTY, EMPTY, IN, NOT_IN) — that is a DIFFERENT column (DataMap.PROCESS_CONFIG.RowFilter) and has nothing to do with WHERE_FILTER. Real examples from code/tests/docs: "PRICE > 0", "RATE_2021 > 0", "RATE_2021 > 5000", "REGION = 'EG'", "A=1". Practical Console rules: single-quote string literals (double quotes are identifiers in SQLite); column names must be real ATTRIBUTE_KEYs of the entity; no ';'; no ORDER BY/LIMIT (they belong in SORT_BY / are appended by the engine).

**Accepted:** `=`, `==`, `<>`, `!=`, `<`, `<=`, `>`, `>=`, `AND`, `OR`, `NOT`, `LIKE`, `GLOB`, `MATCH`, `IN`, `NOT IN`, `BETWEEN`, `IS NULL`, `IS NOT NULL`, `||`, `+`, `-`, `*`, `/`, `%`, `CASE WHEN`, `any SQLite built-in function`, `subquery`

*certain* — mbiXaddin/Infrastructure/Database/ExportQuerySql.cs:8-11 — header: "WHERE_FILTER / SORT_BY are raw SQL fragments authored in trusted metadata (SYS_EXPORT_VIEWS), so they are appended verbatim"; tests/Export.Tests/ExportQuerySqlTests.cs:26 — `ExportQuerySql.BuildSelect("T_X", "PRICE > 0")`; :69 — `BuildSelect("T_X", "A=1; DROP TABLE T_X")` (semicolon-truncation test); mbiXaddin/Core/Entities/ExportViewEntity.cs:131 — `Example: "RATE_2021 > 0" or "REGION = 'EG'"`

### WHERE_FILTER — what happens when a human writes something the code cannot parse?

Total silence, and a wrong-looking export rather than an error. The SQLite exception is swallowed TWICE: LocalDbManager.ExecuteDataTable runs inside ReadOp, which catches, logs an Error, and returns the FALLBACK empty DataTable; ExportEngine.LoadFromSqlite additionally catches and returns UnifiedData.Empty. The render then proceeds normally and produces a sheet with headers, formatting, header/footer banner — and ZERO data rows. No dialog, no in-sheet notice. A user cannot distinguish 'my filter is broken SQL' from 'no rows match'. This is the single strongest argument for validating WHERE_FILTER in the Console.

*certain* — mbiXaddin/Infrastructure/Database/LocalDbManager.cs:474-481 — `return ReadOp(() => { ... adapter.Fill(table); return table; }, new DataTable(), $"ExecuteDataTable SQL: ...")`; LocalDbManager.cs:138-141 — `catch (Exception ex) { _log.LogError($"{context} failed.", ex, SourceName); return fallback; }`; ExportEngine.cs:1292-1296 — `catch (Exception ex) { _log.LogWarning($"[{entityKey}] Failed to load from SQLite: {ex.Message}", SourceName); return UnifiedData.Empty; }`

### WHERE_FILTER — is the export the only consumer? Are the sanitization rules the same everywhere?

No — there is a SECOND consumer with WEAKER sanitization. Library menus (ACTION_CLASS=Library with ACTION_TAG="ENTITY|VIEW") pass the view's WHERE_FILTER to MenuRowReader.Read, which interpolates it raw into `SELECT <cols> FROM [Entity] WHERE <filter>;` with NO semicolon truncation (CleanFragment is not used on this path) and then appends its own ';'. So a WHERE_FILTER containing ';' behaves differently in a menu than in an export. Failure mode is the same class of silence: the SQLite error is swallowed by ExecuteDataTable's ReadOp fallback, rows come back empty, and the menu shows the disabled item "No documents found."

*certain* — mbiXaddin/UI/Commands/MenuRowReader.cs:55-58 — `string sql = $"SELECT {select} FROM [{SqlBuilderService.Sanitize(entityKey)}]"; if (!string.IsNullOrWhiteSpace(whereFilter)) sql += $" WHERE {whereFilter}"; sql += ";";`; mbiXaddin/UI/Commands/LibraryMenuBuilder.cs:110 — `var rows = ReadRows(db, ctx.EntityKey, roles, view?.WHERE_FILTER);`

### SORT_BY — syntax, direction markers, multiple keys?

Raw SQLite ORDER BY body, appended verbatim after the same CleanFragment (trim + truncate at first ';'). Everything SQLite's ORDER BY accepts works: bare column, ASC/DESC markers, multiple comma-separated keys, NULLS FIRST/LAST, COLLATE NOCASE, expressions, and 1-based ordinal positions. Direction markers are ASC and DESC (case-insensitive to SQLite); omitting one means ASC. Examples in code: "ITEM_NAME ASC", "RATE_2021 DESC", "NAME ASC". Caveat for the Console: the engine appends `LIMIT 100001` AFTER the ORDER BY (row cap = MaxExportRows + 1 truncation probe), so a SORT_BY that ends in its own LIMIT produces `LIMIT n LIMIT 100001` → SQL error → the silent empty sheet described above.

**Accepted:** `ASC`, `DESC`, `(omitted = ASC)`, `NULLS FIRST`, `NULLS LAST`, `COLLATE NOCASE / BINARY / RTRIM`, `comma-separated multiple keys`, `1-based ordinal position`

**Blank means:** blank → no ORDER BY (SQLite's arbitrary storage order)

*certain* — mbiXaddin/Infrastructure/Database/ExportQuerySql.cs:43-44 — `string order = CleanFragment(sortBy); if (order.Length > 0) sql.Append(" ORDER BY ").Append(order);`; :47-48 — `if (maxRows > 0) sql.Append(" LIMIT ").Append(maxRows...)`; ExportEngine.cs:74 — `private const int MaxExportRows = 100_000;`; tests/Export.Tests/ExportQuerySqlTests.cs:36 — `BuildSelect("T_X", "PRICE > 0", "NAME ASC")`

### VIEW_CONFIG — which JSON keys does the code read?

Exactly five, deserialized into the shared ExportConfig type (the same bag shape as the entity-level EXPORT_CONFIG, which VIEW_CONFIG OVERRIDES rather than inherits): HeaderText, HeaderStyle, FooterText, FooterStyle, LinkedEntities. HeaderText/FooterText are free strings. HeaderStyle/FooterStyle are a closed vocabulary: Note, Source, Warning, Marketing, TableHeader (case-insensitive; an out-of-set value yields a Warning INVALID_VALUE with a 'did you mean' suggestion and falls back to the default style). Unknown top-level keys are flagged as Warning UNKNOWN_KEY with a Levenshtein suggestion, and invalid JSON is Error INVALID_JSON with line/position — the whole bag is then ignored (JsonSafeParser returns an empty ExportConfig).

**Accepted:** `HeaderText`, `HeaderStyle`, `FooterText`, `FooterStyle`, `LinkedEntities`

*certain* — mbiXaddin/Core/Entities/DisplayModels.cs:137-171 — `[JsonProperty("LinkedEntities")]`, `[JsonProperty("FooterText")]`, `[JsonProperty("FooterStyle")]`, `[JsonProperty("HeaderText")]`, `[JsonProperty("HeaderStyle")]`; mbiXaddin/Core/Configuration/ConfigVocabulary.cs:21-22 — `public static readonly IReadOnlyList<string> BannerStyles = new[] { "Note", "Source", "Warning", "Marketing", "TableHeader" };`; ExportViewEntity.cs:343-345 — `ValidateBag<ExportConfig>("VIEW_CONFIG", VIEW_CONFIG_RAW)` + `ValidateAllowed("VIEW_CONFIG", "HeaderStyle", ..., ConfigVocabulary.BannerStyles)`

### VIEW_CONFIG.LinkedEntities — what syntax does it accept, and is it validated?

Two interchangeable forms via LinkedEntitiesConverter: (a) a compact STRING "ENTITY|VIEW, ENTITY2" where entries are split on comma, semicolon, CR or LF, and each entry is split on '|' into EntityKey|ViewKey (a bare entity = full table); or (b) a JSON ARRAY whose elements are either those same compact strings or objects {"EntityKey":"T_UNITS","ViewKey":"METRIC"}. It IS cross-validated after every sync by the link-integrity guard: an unknown EntityKey, or a ViewKey that is not an ACTIVE view of that entity, yields a Warning with code BROKEN_LINK — because at export time a missed ViewKey silently exports the full table instead.

*certain* — mbiXaddin/Core/Entities/DisplayModels.cs:234-243 — `ParseCompactList` splitting `new[] { ',', ';', '\n', '\r' }` and :220-228 `ParseOne` splitting on '|'; mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:521-527 — per-view `ConfigValidator.ValidateLink($"view {view.VIEW_KEY} · VIEW_CONFIG", link, entityKeys, ActiveViewKeys(link.EntityKey))`; ConfigValidator.cs:161-165 — BROKEN_LINK for an inactive/unknown ViewKey

### ExportViews — what are the hard (row-rejecting) rules on the remaining columns, and what is silently tolerated?

HARD: VIEW_KEY must be non-blank (Critical, MissingRequired — the offline read rejects the row entirely) and must be GLOBALLY UNIQUE across the whole sheet, not per entity: _SYS_EXPORT_VIEWS has `VIEW_KEY TEXT PRIMARY KEY`, and the sync inserts with `INSERT OR IGNORE`, so a duplicate VIEW_KEY (even for a different ENTITY_KEY) is silently discarded on persist. ENTITY_KEY blank is also Critical. SILENT: an ENTITY_KEY naming a non-existent/inactive entity is not warned about at all (contexts are built only from the definitions map; the orphan-warning pass covers columns and sources but NOT views) — the view simply never appears anywhere. LABEL blank = Warning only (falls back to VIEW_KEY). IS_ACTIVE=false hides the view from ViewList menus and from being a link target, but a direct ACTION_TAG="ENTITY|VIEW" still resolves it (GetExportView does not check IS_ACTIVE). Also note two columns the code READS that are absent from the current sheet — GROUP_NAME and SORT_ORDER — both are live in ViewList menus (grouping level and ordering); adding them to the sheet is supported today with no code change.

*certain* — mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:370 — `VIEW_KEY          TEXT PRIMARY KEY NOT NULL,`; mbiXaddin/Infrastructure/Database/LocalDbManager.WriteSession.cs:100 — `string conflictClause = replaceOnConflict ? "OR REPLACE" : "OR IGNORE";`; ExportViewEntity.cs:308-322 (Critical VIEW_KEY / ENTITY_KEY); mbiXaddin/Core/Models/TableMetadataContext.cs:266-271 — `GetExportView` matches VIEW_KEY only; mbiXaddin/UI/Commands/ViewListMenuBuilder.cs:144-145 — `GroupName = v.GROUP_NAME, SortOrder = v.SORT_ORDER,`

### RibbonControls.ACTION_CLASS — is it a .NET type name resolved by reflection?

NO. There is no reflection, no Type.GetType, no assembly scan anywhere on this path. ACTION_CLASS is a plain string matched by an upper-cased switch in ActionRouter (for click actions) and by four string-equality predicates on the entity (for menu-producing classes). The complete valid set is EIGHT values, matched CASE-INSENSITIVELY: four that run on click — Export, Download, Stream, UpdateTable — and four that build a menu instead and are never routed to the router — Menu, Library, ExportTree, ViewList. Both halves are pinned by tests (RibbonMenuActionClassTests). Historical spellings ExportEntity / ExportService / DownloadService / OpenView appear in stale doc comments (RibbonControlEntity.cs:159-171, :632) but were deliberately removed and are NOT accepted — a Console must not offer them.

**Accepted:** `Export`, `Download`, `Stream`, `UpdateTable`, `Menu`, `Library`, `ExportTree`, `ViewList`

**Blank means:** "Export" — applied twice: RibbonControlEntity.cs:177 and RibbonControlService.ParseRow:520

*certain* — mbiXaddin/UI/Commands/ActionRouter.cs:102 — `private static readonly string[] KnownActions = { "Download", "Stream", "Export", "UpdateTable" };` and :129 `switch ((actionName ?? "").ToUpperInvariant())`; mbiXaddin/Core/Entities/RibbonControlEntity.cs:337 — `public static readonly string[] MenuActionClasses = { "Menu", "Library", "ExportTree", "ViewList" };`; tests/Core.Tests/RibbonMenuActionClassTests.cs:41-46 pins the list

### ACTION_CLASS — what happens when the value does not resolve?

For a clickable row: nothing happens at build time (the button renders normally, tagged "<class>|<tag>"), and the failure surfaces only ON CLICK — ActionRouter's switch default logs a Warning and shows a modal warning dialog titled "Unknown Action" listing both vocabularies. So an invalid ACTION_CLASS is exactly the 'button that throws when pressed' the Console is meant to prevent — except it shows a dialog rather than throwing. Two more consequences: (1) a menu-producing class (Menu/Library/ExportTree/ViewList) placed on a single-BUTTON control is wrong — Menu rows are stripped with a warning and, if none remain, the button is disabled; (2) a row whose ACTION_CLASS is a near-miss like "ViewList ×2" does NOT partially match any predicate (pinned by test) and falls through to the click path.

*certain* — mbiXaddin/UI/Commands/ActionRouter.cs:147-167 — switch `default:` → `_logger.LogWarning($"Unknown ACTION_CLASS/onAction '{actionName}' for key '{key}'. ...")` + `DialogHelper.ShowWarning($"No action configured for '{actionName}'....", "Unknown Action")`; mbiXaddin/UI/Commands/RibbonControlService.cs:1159-1171 (Menu rows on a button → warning, then disabled); tests/Core.Tests/RibbonMenuActionClassTests.cs:71-79

### ACTION_TAG — what is its format per ACTION_CLASS, and what happens when it names something that does not exist?

One pipe at most; the leading segment is always the ENTITY_KEY. Per class: Export → "ENTITY_KEY" (full table) or "ENTITY_KEY|VIEW_KEY" (filtered view); Download / Stream → "ROW_KEY" (legacy default source) or "ENTITY_KEY|ROW_KEY" (library row); UpdateTable → bare ENTITY_KEY (a pipe is tolerated, the entity part is used); Library → "ENTITY_KEY" or "ENTITY_KEY|VIEW_KEY" (the view supplies a WHERE_FILTER); ExportTree and ViewList → "ENTITY_KEY" (EntityKeyFromTag; any |VIEW part is ignored); Menu → must be EMPTY (a value here is a Warning and is ignored). Blank ACTION_TAG on any non-Menu row is a validation Fail, and at runtime the click shows "No action configured for this button." Unknown ENTITY_KEY: for Export it is user-visible — EnsureRegistryReadyAsync throws "Table 'X' is not available..." which becomes an "Export Failed" error dialog. Unknown VIEW_KEY is the dangerous one: GetExportView returns null and the engine silently exports the FULL table with no filter, no alias, no column subset. For Library/ExportTree/ViewList an unregistered entity yields a disabled menu item "Not configured — see the log".

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:369-377 (`EntityKeyFromTag`) and :385-394 (`ViewKeyFromTag`); mbiXaddin/UI/Commands/ActionRouter.cs:395-407 (`int sep = key?.IndexOf('|')` → `SafeRenderToSheetAsync(entityKey, viewKey: viewKey, ...)`); ExportEngine.cs:110 — `var view = !string.IsNullOrEmpty(viewKey) ? ctx.GetExportView(viewKey) : null;` with TableMetadataContext.cs:270 returning null when not found; ExportEngine.cs:241-243 — `throw new InvalidOperationException($"Table '{entityKey}' is not available...")`; RibbonControlEntity.cs:479-485 (ACTION_TAG required for non-Menu)

### CONTROL_KEY — what is the vocabulary, and what happens when it does not match a real control?

A CLOSED set determined by the VSTO ribbon designer, discoverable but not declared in one place: a row renders only if its CONTROL_KEY equals (case-insensitively) the Name of a control that is wired to the data-driven handler. That is 21 menus — mnuMaterial, mnuLabor, mnuEquipment, mnuBOQ, mnuVendor, mnuSupplier, mnuSubContractor, mnuFuel, mnuRepository, mnuEurocode, mnuEgypt, mnuSaudiArabia, mnuSA_BuildingMaterialsPriceList, mnuUnitedArabEmirates, mnuKuwait, mnuQatar, mnuBahrain, mnuOman, mnuEG_BuildingMaterialsPriceList, mnuEG_BusinessDirectory, mnuEG_CompensationRates (each wired to mnuDynamic_ItemsLoading → FillMenu(menu, menu.Name)) — plus 2 single buttons registered with BindButton: btnDiesel, btnLiquidBitumen. CRITICAL TRAP: the DEFAULT for a blank cell is "mnuDynamic", and NO control of that name exists in the shipped designer — a blank CONTROL_KEY therefore renders nowhere. mnuExport is NOT sheet-driven either (it uses RibbonContentBuilder). An unmatched CONTROL_KEY produces no error: the row is simply never selected by any FillMenu/BindButton call; conversely a control with no rows shows the disabled item "No items configured."

**Accepted:** `mnuMaterial`, `mnuLabor`, `mnuEquipment`, `mnuBOQ`, `mnuVendor`, `mnuSupplier`, `mnuSubContractor`, `mnuFuel`, `mnuRepository`, `mnuEurocode`, `mnuEgypt`, `mnuSaudiArabia`, `mnuSA_BuildingMaterialsPriceList`, `mnuUnitedArabEmirates`, `mnuKuwait`, `mnuQatar`, `mnuBahrain`, `mnuOman`, `mnuEG_BuildingMaterialsPriceList`, `mnuEG_BusinessDirectory`, `mnuEG_CompensationRates`, `btnDiesel`, `btnLiquidBitumen`

**Blank means:** "mnuDynamic" — a control that does NOT exist in the shipped ribbon, so the row renders nowhere

*certain* — mbiXaddin/mbiXRibbon.cs:1099 — `_ribbon.FillMenu(menu, menu.Name);` (handler mnuDynamic_ItemsLoading, wired 21× in mbiXaddin/mbiXRibbon.Designer.cs:148,157,166,252,271,278,291,322,459,474,489,506,519,534,549,564,579,594,610,619,634); mbiXaddin/mbiXRibbon.cs:261-262 — `_ribbon.BindButton(this.btnDiesel); _ribbon.BindButton(this.btnLiquidBitumen);`; RibbonControlService.cs:184 — `string.Equals(x.EffectiveControlKey, controlKey, StringComparison.OrdinalIgnoreCase)`; RibbonControlService.cs:513 — `CONTROL_KEY = SafeStr(row, "CONTROL_KEY") ?? "mnuDynamic"`; RibbonControlService.cs:187-191 — `AddDisabled(menu, factory, "No items configured.");`

### RibbonControls.REGION — vocabulary and rules?

"GLOBAL" (or blank) = visible everywhere; otherwise a comma-separated list of 2-letter ISO country codes, e.g. "EG" or "EG,SA". Matching is case-insensitive and per-token trimmed; the special current-region value "ALL" shows everything. Validation warns (does not reject) when any token is not exactly 2 letters. The region dropdown's own vocabulary is DERIVED at runtime from the union of the REGION tokens found in this sheet and SOURCE_REGION values in SYS_DATA_SOURCES, so a typo like "EGY" both fails to match and pollutes the dropdown (tokens of length ≥ 2 are added). For a single-button control, region selection picks one row: region-specific beats GLOBAL, ties broken by lowest ORDER (with a warning); no match at all leaves the button visible but DISABLED.

**Accepted:** `GLOBAL`, `<2-letter ISO code>`, `<comma-separated list of 2-letter ISO codes>`, `(blank = GLOBAL)`

**Blank means:** GLOBAL (entity default and ParseRow fallback), with a Warning

*certain* — mbiXaddin/Core/Entities/RibbonControlEntity.cs:402-412 — `IsVisibleInRegion` (`REGION.Split(',').Any(r => r.Trim().Equals(currentRegion, ...))`, "ALL" short-circuit); :457-467 — `if (trimmed.Length != 2 || !char.IsLetter(...)) yield return ValidationResult.Warn(... "is not a valid 2-letter ISO code")`; :149 — `public string REGION { get; set; } = "GLOBAL";`; RibbonControlService.cs:1237-1238 — `var regionSpecific = exactMatches.Where(x => !x.IsGlobal).ToList(); var pick = regionSpecific.FirstOrDefault() ?? exactMatches.FirstOrDefault();`

### RibbonControls.PARENT_KEY and ORDER — vocabularies and rules?

PARENT_KEY: blank = top-level within its CONTROL_KEY; otherwise the ITEM_KEY of ANOTHER row, matched case-insensitively AND only among rows of the SAME CONTROL_KEY that survived the region filter. Consequences a Console should enforce: (a) a PARENT_KEY pointing at a row with a different CONTROL_KEY, an inactive row, or a row filtered out by region orphans the child — it simply never renders, with no warning; (b) the parent should be an ACTION_CLASS='Menu' container (children of a leaf row are never enumerated); (c) self-parenting is Critical (CircularInheritance) but a LONGER cycle (A→B→A) is NOT detected by validation — the recursive builder would loop; (d) PARENT_KEY is meaningless on single-button controls. ORDER: a free integer, ascending, applied at three levels (SQL `ORDER BY [ORDER]`, top-level `.OrderBy(x => x.ORDER)`, children `.OrderBy(x => x.ORDER)`); a non-numeric or blank cell becomes 0 (SafeInt); negatives are a Warning. Convention is gaps of 10.

**Blank means:** PARENT_KEY blank = top-level; ORDER blank/unparseable = 0

*certain* — mbiXaddin/UI/Commands/RibbonControlService.cs:687-689 — `.Where(x => string.Equals(x.PARENT_KEY, menuItem.ITEM_KEY, StringComparison.OrdinalIgnoreCase)).OrderBy(x => x.ORDER)`; :209-212 — `visible.Where(x => x.IsTopLevel).OrderBy(x => x.ORDER)`; :489 — `"SELECT * FROM [_SYS_RIBBON_CONTROLS] WHERE IS_ACTIVE = 1 ORDER BY [ORDER];"`; :1412-1416 — `SafeInt` → `int.TryParse(...) ? i : 0`; RibbonControlEntity.cs:496-501 (self-parent Critical) and :512-516 (negative ORDER Warning)

### RibbonControls.MENU_LAYOUT — complete vocabulary, default, and behaviour on a bad value?

A closed enum parsed by MenuLayoutParser, case-insensitively, by NAME only — six spellings for five distinct shapes: Nested (=0, default), Grouped (=1), GroupedLarge (=2), Tiles (alias of GroupedLarge, kept for a live sheet), Flat (=3), FlatLarge (=4), NestedLarge (=5). NUMERIC strings are deliberately REJECTED even when they name a defined value ("2" does not mean Tiles). A blank cell is not a defect — it means Nested. An unrecognised non-blank value logs a Warning naming every valid spelling and renders as Nested. Two placement rules the Console should enforce, because both are logged-only: MENU_LAYOUT only has an effect on a row that SUPPLIES a menu (ACTION_CLASS = Menu, Library, ExportTree or ViewList); on an Export/Download/Stream leaf it is warned as having no effect, and on a Menu container whose children include no further container it is warned as having nothing to fold. Also: the Large variants can be refused by Office on a designer-declared menu, in which case the structure is kept and only the size is dropped.

**Accepted:** `Nested`, `Grouped`, `GroupedLarge`, `Tiles`, `Flat`, `FlatLarge`, `NestedLarge`

**Blank means:** Nested

*certain* — mbiXaddin/Core/UI/MenuLayout.cs:49-93 (enum members Nested/Grouped/GroupedLarge/Tiles/Flat/FlatLarge/NestedLarge); :101 — `public const MenuLayout Default = MenuLayout.Nested;`; :124-131 — numeric rejection then `Enum.TryParse(text, ignoreCase: true, ...) && Enum.IsDefined(...)`; :139 — `public static string ValidValues => string.Join(", ", Enum.GetNames(typeof(MenuLayout)));`; RibbonControlService.cs:1067-1072 (unrecognised → Warning "Valid: {MenuLayoutParser.ValidValues}. Rendering as {layout}") and :1100-1106 (no-effect warning on a click row)

### RibbonControls.ICON (and ExportViews.ICON) — format rules?

Free string with a three-branch resolution and no closed vocabulary: (1) a value starting with "Mso:" (case-insensitive) → the remainder is an Office built-in imageMso id; (2) a value containing '.' and with an IconService available → a custom icon file (e.g. "fuel.svg") resolved by IconService, and if the file is missing it FALLS THROUGH to being tried as an Office id; (3) anything else → a bare Office built-in id. An unknown Office id is non-fatal — it is trace-logged and the control simply keeps its default icon. Blank = inherit (RibbonControls: ExportView.ICON → SYS_DEFINITIONS.RIBBON_CONFIG.Icon). Validation catches only format traps: leading/trailing whitespace (Warning), >200 chars (Fail), a trailing '.' with no extension (Warning), and '..' path traversal (Warning).

**Blank means:** inherit: ExportView.ICON → SYS_DEFINITIONS.RIBBON_CONFIG.Icon; no icon if none

*certain* — mbiXaddin/Infrastructure/Icon/RibbonControlAccessor.cs:221-222 — `if (value.StartsWith("Mso:", StringComparison.OrdinalIgnoreCase)) return TrySetOfficeId(accessor, control, value.Substring(4), ...)`; :225-238 (file branch, falls through when `img == null`); :250-265 — `TrySetOfficeId` catch → "An unknown built-in Office image id is non-fatal — the control keeps its default."; RibbonControlEntity.cs:522-558 (the four format checks)

### IS_ACTIVE (both sheets) — what values are accepted, and what does a garbage value do?

Parsed by SmartConverter.IsTrue with a fixed multilingual set — TRUE: 1, true, yes, y, on, نعم, صح, صحيح; FALSE: 0, false, no, n, off, لا, خطأ, غلط (all case-insensitive, trimmed). DANGEROUS ASYMMETRY: an unrecognised value ('Active', 'X', 'TRUE!') returns null, and TsvParser only assigns when the conversion produced a value — so the property keeps its declared default, which is TRUE for both ExportViewEntity and RibbonControlEntity. A typo in IS_ACTIVE therefore ACTIVATES the row rather than raising anything. An empty cell is skipped before conversion, with the same effect. The Console should hard-restrict this cell to one spelling (the live sheet uses True/False).

**Accepted:** `1`, `true`, `yes`, `y`, `on`, `نعم`, `صح`, `صحيح`, `0`, `false`, `no`, `n`, `off`, `لا`, `خطأ`, `غلط`

**Blank means:** true (blank OR unrecognised text both leave the row ACTIVE)

*certain* — mbiXaddin/Core/Utils/SmartConverter.cs:42-53 — `TrueValues = { "1", "true", "yes", "y", "on", "نعم", "صح", "صحيح" }` / `FalseValues = { "0", "false", "no", "n", "off", "لا", "خطأ", "غلط" }`; mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:83 — `if (converted != null) prop.SetValue(obj, converted);`; ExportViewEntity.cs:171 and RibbonControlEntity.cs:266 — `public bool IS_ACTIVE { get; set; } = true;`

### What are the Excel / File / Folder columns in RibbonControls for?

Nothing, as far as this codebase is concerned — they are spreadsheet-side helper columns, invisible to the add-in. Proof is structural, not merely a failed grep: the TSV parser maps sheet headers to properties BY NAME using [JsonProperty]/property names and silently skips any header with no match, RibbonControlEntity declares exactly thirteen JSON properties (ITEM_KEY, CONTROL_KEY, PARENT_KEY, ORDER, REGION, ACTION_CLASS, MENU_LAYOUT, ACTION_TAG, LABEL, SCREEN_TIP, SUPER_TIP, ICON, IS_ACTIVE) and none named Excel/File/Folder, the _SYS_RIBBON_CONTROLS DDL has no such columns, ParseRow reads none, and a dedicated guard test enumerates the sheet's column list — those three are absent from it. A repo-wide grep for them as column names returns only unrelated hits (a LogViewerPanel button labelled "File"). Safe conclusion for the Console: leave them untouched and do not validate them; they can be reordered or renamed without affecting the add-in, but note the parser tolerates extra columns only as long as at least one KNOWN header matches — a header row that matches nothing aborts the whole fetch.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/TsvParser.cs:141-146 — `if (!string.IsNullOrWhiteSpace(header) && byName.TryGetValue(header, out var p)) map[i] = p;` (unmatched headers never enter the map; :56-60 aborts only when NOTHING matches); tests/Sync.Tests/RibbonColumnWiringGuardTests.cs:26-30 — the authoritative column list, without Excel/File/Folder; mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:435-449 — the _SYS_RIBBON_CONTROLS DDL

### ITEM_KEY / row-identity rules for RibbonControls — anything the Console must guarantee?

ITEM_KEY is mandatory (blank = Critical, MissingRequired; ParseRow also drops such a row), max 100 chars (Fail beyond), and must be GLOBALLY UNIQUE across the entire sheet — it is the PRIMARY KEY of _SYS_RIBBON_CONTROLS and the sync persists with INSERT OR IGNORE, so a second row with the same ITEM_KEY (even under a different CONTROL_KEY or REGION) is silently discarded, with only a partial-count line in the log. CONTROL_KEY is likewise capped at 100 chars. Convention (not enforced): 'mnu_' prefix for containers, 'btn_' for actionable rows. Note also that RibbonControlService reads rows straight from SQLite with `SELECT * ... WHERE IS_ACTIVE = 1` and never calls Validate() — so at ribbon-render time none of the entity's own validation rules run; they only surface as ETL alerts during sync.

*certain* — mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:436 — `ITEM_KEY          TEXT PRIMARY KEY NOT NULL,`; LocalDbManager.WriteSession.cs:100 — `"OR IGNORE"`; RibbonControlEntity.cs:421-434 (Critical blank, Fail >100); RibbonControlService.cs:507-508 — `string key = row["ITEM_KEY"]?.ToString(); if (string.IsNullOrWhiteSpace(key)) return null;`

### Where does validation of these two sheets actually run, and does a bad row ever block a sync?

Never blocks. On the ONLINE path each fetched row's Validate() runs in phase 1.25 and findings become persistent ETL alerts only — rows are persisted regardless of severity, and SYS_EXPORT_VIEWS / SYS_RIBBON_CONTROLS are explicitly 'optional' sheets that degrade independently (a failed fetch keeps the cached rows rather than aborting). Severity only bites on the OFFLINE read path (ReadEntities from SQLite), where a Critical finding rejects that single row with a Warning log. Net effect for the Console: every rule described above is advisory inside the add-in — the sheet is the only enforcement point, which is precisely the gap the Console fills.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:345-346 — `ValidateAndAlertBatch(rawViews.Valid, "SYS_EXPORT_VIEWS"); ValidateAndAlertBatch(rawRibbonControls.Valid, "SYS_RIBBON_CONTROLS");` (then :352-355 persists the same lists); MetadataOrchestrator.Tier1Schema.cs:598-611 — offline read: `if (hasCritical) { rejected++; _log.LogWarning($"[{tableName}] Row rejected (critical validation error): ..."); continue; }`


## the-existing-validation

### Where does config validation live, and what is the complete set of entry points in the config-loading path?

Five layers, all funnelling into ONE result type (ValidationResult). (1) TSV parse guards — TsvParser.cs:56 rejects a payload where NO column is recognised; MetadataOrchestrator.cs:788 rejects a payload that looks like markup. (2) Per-row entity rules — each entity's Validate(), run over every fetched row by MetadataOrchestrator.ValidateAndAlertBatch for all six sheets (MetadataOrchestrator.cs:341-346). (3) Cross-sheet warnings — MetadataOrchestrator.LogCrossReferenceWarnings (MetadataOrchestrator.cs:579-653) + PARENT_KEY check (:666-677) + duplicate ENTITY_KEY (:532-545). (4) Per-entity completeness — TableMetadataContext.ValidateCompleteness (TableMetadataContext.cs:336-483), called at build time (MetadataOrchestrator.cs:713), at sync time (SyncManager.cs:593) and live by the ETL Console (EtlConsoleBuilder.cs:202). (5) Ingest-time gates — DataIngestionService.BuildExecutionPlan (Mapping.cs:37-103) and ValidateMappingCompleteness (DataIngestionService.cs:1440-1587). Orchestration entry points are ValidationOrchestrator.ValidateEntity:89, ValidateBatch:166, ValidateRawRow:259, ValidateContext:381.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:341-346 — `ValidateAndAlertBatch(rawDefs.Valid, "SYS_DEFINITIONS"); ValidateAndAlertBatch(rawCols.Valid, "SYS_SCHEMA_RULES"); ValidateAndAlertBatch(rawSources.Valid, "SYS_DATA_SOURCES"); ValidateAndAlertBatch(rawMaps.Valid, "SYS_DATA_MAP"); ValidateAndAlertBatch(rawViews.Valid, "SYS_EXPORT_VIEWS"); ValidateAndAlertBatch(rawRibbonControls.Valid, "SYS_RIBBON_CONTROLS");`

### CRITICAL SEMANTICS: does a Warning block anything? What is the difference between Warn / Fail / Critical at runtime?

NO — a Warning never blocks. ValidationReport.IsValid is `!results.Any(r => !r.IsValid && r.Severity >= Error)`, so Warnings are excluded. This is the single most important fact for the Console: the ONLY findings that stop work are Error (Fail) and Critical. SyncManager.cs:601 gates on `if (!report.IsValid)` → the entity's sync is SKIPPED. A report with 50 warnings and 0 errors syncs normally. So the Console must render Warn and Fail as visually distinct classes: Fail = 'this table will not sync', Warn = 'this will silently do the wrong thing'.

**Accepted:** `Info = 0 (never surfaced, skipped by ValidationLogBridge)`, `Warning = 1 (operation completes; does NOT affect IsValid)`, `Error = 2 (invalid; blocks sync at SyncManager:601)`, `Critical = 3 (halts; StopOnCritical aborts the entity's own Validate() loop)`

*certain* — mbiXaddin/Core/Validation/Validation.cs:166-167 — `public bool IsValid => !_results.Any(r => !r.IsValid && r.Severity >= ValidationSeverity.Error);` and SyncManager.cs:601-613 — `if (!report.IsValid) { ... Skipped = true, FailReason = $"Validation: {report.ErrorCount} error(s)" }`

### Is there a 'diagnostics' / 'health' / 'validate' command already in the add-in that reports config problems?

YES — the ETL Console, a ribbon button (btnETLinspector) opening EtlInspectorView. It is the exact rule set the Console should reproduce. It calls TableMetadataContext.ValidateCompleteness() for EVERY registered entity, live, on every open ('recomputed live from the registry each time you open this — nothing is read from a log'), and renders a fleet health band (N entities / N errors / N warnings), a 'Needs Attention' list, an all-entities grid, and a per-entity drill-in table with columns Severity | Field | Message | Code. IMPORTANT CAVEAT: it is Developer-build only — `grpConsole.Visible = LogMode.Current == RuntimeMode.Developer` — so no real user has ever seen it. There is NO CLI and no ribbon 'validate' button for end users.

*certain* — mbiXaddin/mbiXRibbon.cs:1246-1251 — `// Developer-only (button is hidden outside a Developer build). Live config review — no pipeline DB.` / `private void btnETLinspector_Click(...) { _taskPaneManager?.Toggle("etl", () => new EtlInspectorView(_registry, _db, _security)); }`; gate at mbiXRibbon.cs:128 — `this.grpConsole.Visible = LogMode.Current == RuntimeMode.Developer;`; rules at mbiXaddin/UI/TaskPane/EtlConsoleBuilder.cs:60,164,202

### REFERENTIAL INTEGRITY — DataSource.TARGET_ENTITY_KEY must exist in TableDefinition. Enforced?

YES, twice, but only as a WARNING (log-only) — never a hard failure. (a) DataSourceEntity.Validate() rule 2 fires Critical ONLY when TARGET_ENTITY_KEY is BLANK — it never checks that the value actually exists. (b) The existence check is MetadataOrchestrator.LogCrossReferenceWarnings: a source whose TARGET_ENTITY_KEY matches no ACTIVE definition logs `[ORPHAN_SRC] ... These sources will never sync. Fix: check TARGET_ENTITY_KEY spelling.` and is then simply never assembled into any context (sourcesByEntity lookup at :551-553 never matches). Note the check is against ACTIVE definitions only (defsMap is built from `d.IS_ACTIVE` rows at :528-530), so pointing at an existing-but-inactive entity produces the same orphan warning.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:604-612 — `foreach (var entityKey in allSourceKeys) { if (!defsMap.ContainsKey(entityKey)) _log.LogWarning($"[ORPHAN_SRC] SYS_DATA_SOURCES has source(s) targeting ENTITY_KEY='{entityKey}' but no matching active entity exists in SYS_DEFINITIONS. These sources will never sync. Fix: check TARGET_ENTITY_KEY spelling.", SourceName); }`

### MEASURED DEFECT 1 — 15 orphan PROFILE_KEYs. What does the add-in actually DO at runtime: silently ignore, log, or fail?

The answer DEPENDS ON WHICH DIRECTION the orphan runs, and the two are treated completely differently. DIRECTION A — a DataSource whose PROFILE_KEY has no DataMap rows: this HARD-FAILS that source. DataIngestionService.cs:856-865 returns IngestionResult.Fail('No mappings for profile X') and the source never ingests; it is also warned twice beforehand (MetadataOrchestrator [NO_MAPPING] at :619-626, ValidateCompleteness [ERR_REF] Warn at TableMetadataContext.cs:373-380). Because both pre-warnings are Warn, the entity still passes SyncManager's gate and the failure surfaces only per-source. DIRECTION B — a DataMap PROFILE_KEY that NO DataSource references: totally silent. Nothing loads it, nothing warns. MetadataOrchestrator.ResolveEntitySourceMaps only ever reads `mapsByProfile[profile]` for profiles reachable from a source (:731-754), so unreferenced map rows never enter any TableMetadataContext and are therefore invisible to ValidateCompleteness too. I grepped for any unreferenced-profile check across mbiXaddin/ and tests/ and found none. VERDICT: if your 15 are direction B they are inert noise the add-in cannot see; if direction A they are real defects that silently produce empty tables. The Console should flag BOTH, because the add-in only covers one.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:856-865 — `if (mappings == null || mappings.Count == 0) { _log.LogWarning($"No mappings found for PROFILE_KEY='{profile}' (original='{source.PROFILE_KEY}') in SYS_DATA_MAP. All columns will be empty..."); prep.EarlyResult = IngestionResult.Fail(source.SOURCE_KEY, context.EntityKey, $"No mappings for profile '{profile}'."); return prep; }` vs. MetadataOrchestrator.cs:749-753 — `foreach (var map in mapsByProfile[profile]) { ... }` (only source-reachable profiles are ever read)

### MEASURED DEFECT 2 — one DataMap row targeting an attribute that does not exist. What does the add-in actually DO?

LOGGED AS A WARNING, THEN SILENTLY DROPPED — the row is never written and the sync proceeds. Two places catch it. (1) Pre-sync: ValidateCompleteness check 4b adds a Warn with code ERR_REF: '...targets column X which is NOT defined in SYS_SCHEMA_RULES ... This mapping will be silently ignored during sync and its data will be lost.' Being a Warn it does NOT block SyncManager. (2) At ingest: BuildExecutionPlan looks the column up, gets null, logs a multi-line warning ('Orphan mapping ... automatically ignored to prevent database errors') and `continue`s — the mapping is excluded from the execution plan entirely. IMPORTANT SECOND-ORDER EFFECT: if the missing attribute happened to be the PK or an IS_MANDATORY column, the drop then trips ValidateMappingCompleteness CHECK 1/CHECK 2, which IS fatal and aborts the whole source. So the same defect is either harmless data-loss or a total sync abort depending on the column's flags. VERDICT: a real defect (data is silently lost), but one the add-in survives.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.Mapping.cs:57-70 — `if (col == null) { string msg = $"🟡 Warning: The field '{map.TARGET_ATTRIBUTE_KEY}' exists in SYS_DATA_MAP but is not defined in SYS_SCHEMA_RULES.\n   It has been automatically ignored to prevent database errors..."; _log.LogWarning($"[{context.EntityKey}] Orphan mapping: '{map.TARGET_ATTRIBUTE_KEY}' — not in schema.\n{msg}", SourceName); continue; }` and TableMetadataContext.cs:389-400 (Warn, ErrorCodes.InvalidReference)

### Complete enumeration of TableMetadataContext.ValidateCompleteness — the exact rule set the ETL Console renders and the Console should mirror

Nine checks, in order. (1) runs Definition.Validate() and folds in every result. (2) No columns at all → Fail/Error 'Table X has no column definitions in SYS_SCHEMA_RULES' (ERR_REQUIRED) — BLOCKS SYNC. (3a) zero IS_PK columns → Warn 'MergeUpsert strategy will not work correctly'; (3b) more than one IS_PK → Warn 'Composite PK is not yet supported — only the first will be used'. (4) each active source whose ResolveProfileKey() has no entry in Maps → Warn ERR_REF 'DataIngestionService will skip this source at sync time'. (4b) each mapping whose TARGET_ATTRIBUTE_KEY is not in ColumnByKey → Warn ERR_REF 'silently ignored during sync and its data will be lost'. (5) ENTITY_TYPE=CONVERSION missing any of CONV_SOURCE / CONV_TARGET / CONV_FACTOR → Fail/Error each — BLOCKS SYNC. (6) cost-related table with no SEMANTIC_ROLE=PRICE column → Warn. (7) LIBRARY (or any entity carrying a MENU_* role): no MENU_KEY and no PK → Fail/Error 'Menu rows cannot be keyed or downloaded' — BLOCKS SYNC; no MENU_URL and no MENU_DRIVE_URL → Warn; no MENU_LABEL → Warn; and any of the ten SINGULAR menu roles appearing on >1 column → Warn 'only the first (by ORDINAL_POS) is used'.

**Accepted:** `MENU_KEY`, `MENU_LABEL`, `MENU_URL`, `MENU_DRIVE_URL`, `MENU_SCREENTIP`, `MENU_SUPERTIP`, `MENU_ICON`, `MENU_ACTION`, `MENU_FORMAT`, `MENU_ORDER`

*certain* — mbiXaddin/Core/Models/TableMetadataContext.cs:336-483 — checks at :341 (Definition.Validate), :345 (HasColumns Fail), :352-365 (PK count), :369-381 (profile→maps Warn), :385-402 (TARGET_ATTRIBUTE_KEY Warn), :405-423 (conversion roles Fail), :426-431 (PRICE Warn), :435-479 (library roles)

### Complete enumeration of the cross-sheet checks in MetadataOrchestrator (the ones ValidateCompleteness does NOT cover)

Five, all log-only, none affecting the produced graph ('Log-only; does not affect the produced graph', :578). (1) [DUPLICATE] duplicate ENTITY_KEY in SYS_DEFINITIONS → LogWarning, first occurrence wins, duplicate row dropped (:535-543). (2) [ORPHAN_COLS] SchemaRule rows whose ENTITY_KEY has no active definition → LogWarning, columns ignored (:587-595). (3) [ORPHAN_SRC] DataSource rows whose TARGET_ENTITY_KEY has no active definition → LogWarning, 'will never sync' (:604-612). (4) [NO_MAPPING] active source whose PROFILE_KEY has no SYS_DATA_MAP rows → LogWarning, 'Table X will be empty after sync' (:616-626). (5) [DUPLICATE_SOURCE_KEY] SOURCE_KEY appearing more than once → LogError (the only Error-level one here) because SOURCE_KEY keys _SYS_SYNC_STATE and per-row provenance, so 'a duplicate can make a removed source delete another source's rows'; sync is NOT aborted (:633-652). Plus [ERR_REF] PARENT_KEY not found in SYS_DEFINITIONS → LogWarning, inheritance skipped, entity treated as root (:666-677). BUG WORTH MIRRORING CAREFULLY: check (4) uses the RAW `src.PROFILE_KEY` while every other site uses ResolveProfileKey(), so PROFILE_KEY='DEFAULT' produces a FALSE [NO_MAPPING] warning and a blank PROFILE_KEY is skipped entirely — the Console should use the resolved key, not this one.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:616-626 — `foreach (var src in allSources.Where(s => s != null && s.IS_ACTIVE)) { string profile = src.PROFILE_KEY; if (!string.IsNullOrWhiteSpace(profile) && !mapsByProfile[profile].Any()) _log.LogWarning($"[NO_MAPPING] Source '{src.SOURCE_KEY}' uses PROFILE_KEY='{profile}' but SYS_DATA_MAP has no mappings for this profile..."); }` — compare DataSourceEntity.cs:257-261 `ResolveProfileKey()`

### Is there a referential check on the JSON-embedded cross-references (LinkedEntities / ViewKey)? — the L4 link guard

YES — RunLinkIntegrityCheck, the only FK check that runs against the FULLY BUILT registry (so it can see all entities, unlike the per-entity checks). It walks every entity's EXPORT_CONFIG.LinkedEntities and every view's VIEW_CONFIG.LinkedViews, and via ConfigValidator.ValidateLink warns when: the linked EntityKey is not in the registry ('Linked entity X does not exist. Check the entity key in SYS_DEFINITIONS'), or the linked ViewKey is not one of THAT entity's ACTIVE views ('the full table is exported instead ... Ensure a row with that VIEW_KEY, ENTITY_KEY = X and IS_ACTIVE = true exists in SYS_EXPORT_VIEWS'). Both are Warn / code BROKEN_LINK. Wrapped in try/catch — 'Check skipped' on any exception. Value syntax: 'Entity|View, Entity, ...' compact form or an array of objects, both parsing to List<LinkedEntityRef>; separators are comma AND semicolon.

*certain* — mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:439-481 (RunLinkIntegrityCheck, called at :429) and mbiXaddin/Core/Configuration/ConfigValidator.cs:150-166 (ValidateLink); syntax pinned by tests/Core.Tests/LinkedEntitiesTests.cs:44-66

### What are the hard, sync-aborting gates at ingest time (ValidateMappingCompleteness)?

Three checks; the source is aborted (IngestionResult.Fail, 'Critical mapping issues — check PK and mandatory columns') if any is fatal. CHECK 0 — TOTAL HEADER MISMATCH: if the profile declares N header-bound columns and NOT ONE resolves against the file's header row → FATAL for every storage strategy, because a ReplaceAll table would otherwise truncate real data and commit all-null rows. Message names the three causes: wrong sheet/gid, URL returning a web page (must contain output=tsv), or SKIP_ROWS wrong. CHECK 1 — PK NOT MAPPED: fatal ONLY when STORAGE_STRATEGY=MergeUpsert ('every sync will create duplicate rows'); under ReplaceAll it is a Warning and the sync proceeds. CHECK 2 — MANDATORY COLUMN NOT PRODUCIBLE: any IS_MANDATORY persisted column not bound → FATAL. 'Mapped' here means the mapping can actually PRODUCE a value, not merely that a SYS_DATA_MAP row exists; the message distinguishes 'no mapping row at all' from 'row exists but its SOURCE_EXPRESSION matches no column in the file'. Non-mandatory unmapped columns → LogDebug only. CHECK 3 is a non-fatal coverage summary.

*certain* — mbiXaddin/Infrastructure/Services/Ingestion/DataIngestionService.cs:1440-1587, fatal return at :1586 `return !hasFatalError;` consumed at :870-876 — `bool integrityOk = ValidateMappingCompleteness(context, plan, mappings); if (!integrityOk) { prep.EarlyResult = IngestionResult.Fail(source.SOURCE_KEY, context.EntityKey, "Critical mapping issues — check PK and mandatory columns."); return prep; }`

### What does the JSON config-bag validator check, and what are the complete allowed-value vocabularies?

ConfigValidator has four layers, all emitting ValidationResult so they flow through the one pipeline. L1 ValidateBag — JSON syntax; a parse failure is an ERROR ('The whole X bag is ignored at runtime') with the hint 'booleans must be lowercase true/false, every string needs quotes, and no trailing commas'; empty/null raw is NOT an error. L2 — any top-level key that is not a [JsonProperty] of the target type is a WARNING with a Levenshtein 'Did you mean "X"?' suggestion (threshold = max(2, len/3)); passing `object` as T skips the key check. L3 ValidateAllowed (case-insensitive, empty skips) + ValidateHexColor (regex ^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$) + ValidateRowFilter (splits 'OP' or 'OP:value' on the first colon after position 0). L4 ValidateLink. Every vocabulary is a public IReadOnlyList in ConfigVocabulary — copy these verbatim into the drop-downs.

**Accepted:** `BannerStyles (HeaderStyle/FooterStyle in EXPORT_CONFIG + VIEW_CONFIG): Note, Source, Warning, Marketing, TableHeader`, `Directions (UX_CONFIG.Direction): LTR, RTL`, `ControlSizes (RIBBON_CONFIG.ControlSize): Large, Regular`, `RowFilterOperators (PROCESS_CONFIG.RowFilter): EQ, NEQ, GT, LT, GTE, LTE, CONTAINS, NOT_CONTAINS, NOT_EMPTY, EMPTY, IN, NOT_IN`, `MapStrategies (PROCESS_CONFIG.NullStrategy + .ErrorStrategy): Skip, UseDefault, Fail`

**Blank means:** Empty/null raw bag yields no findings at all (ValidateBag returns early at ConfigValidator.cs:50); an empty value in ValidateAllowed/ValidateHexColor/ValidateRowFilter also yields nothing — blank is always legal.

*certain* — mbiXaddin/Core/Configuration/ConfigVocabulary.cs:21-44 and ConfigValidator.cs:31-35 (codes INVALID_JSON, UNKNOWN_KEY, INVALID_VALUE, INVALID_COLOR, BROKEN_LINK), :226 (`int threshold = Math.Max(2, value.Length / 3);`)

### Complete per-row rules for sheet 1 (TableDefinition) — what TableDefinitionEntity.Validate() checks

Six rules. (1) ENTITY_KEY blank → CRITICAL, and `yield break` — no further rule runs for that row. (2) ENTITY_KEY > 100 chars → Error (ERR_LENGTH). (3) DISPLAY_NAME blank → Error 'Entity X is missing a DISPLAY_NAME'. (4) PARENT_KEY == ENTITY_KEY → CRITICAL 'Circular inheritance: X cannot be its own parent' (ERR_CIRCULAR). Note this only catches SELF-reference — there is no multi-hop cycle detection anywhere. (5) ENTITY_TYPE null → Warn 'The engine may not process it correctly'. (6) the four config bags UX_CONFIG / SYS_CONFIG / RIBBON_CONFIG / EXPORT_CONFIG through ConfigValidator, then UX_CONFIG.Direction, UX_CONFIG.TabColor (hex), EXPORT_CONFIG.HeaderStyle, EXPORT_CONFIG.FooterStyle, RIBBON_CONFIG.ControlSize against their vocabularies. Nothing validates LICENSE_TIER, IS_ACTIVE, IS_VISIBLE, STORAGE_STRATEGY, VIEW_MODE or BUSINESS_DOMAIN in Validate() — those are enum-typed and absorbed by the TSV parser instead.

*certain* — mbiXaddin/Core/Entities/TableDefinitionEntity.cs:435-490 — `if (string.IsNullOrWhiteSpace(ENTITY_KEY)) { yield return ValidationResult.Critical(nameof(ENTITY_KEY), "ENTITY_KEY is mandatory and cannot be empty.", ...); yield break; }`

### Complete per-row rules for sheet 2 (SchemaRule) — what SchemaRuleEntity.Validate() checks

Thirteen rules. (1) ENTITY_KEY blank → CRITICAL + yield break. (2) ATTRIBUTE_KEY blank → CRITICAL + yield break. (3) ATTRIBUTE_KEY > 100 → Error. (4) DISPLAY_HEADER blank → Error. (5) ORDINAL_POS < 0 → Warn 'Value 0 will be used'. (6) IS_VIRTUAL && IS_DERIVED → Warn 'VIRTUAL takes priority — column will not be stored'. (7) IS_PK && IS_VIRTUAL → Error 'cannot be both'. (8) IS_PK && IS_DERIVED → Error 'cannot be both'. (9) SEMANTIC_ROLE=CONV_FACTOR && DATA_TYPE != DECIMAL → Warn. (10) SEMANTIC_ROLE in {CONV_DATE_START, CONV_DATE_END} && DATA_TYPE not in {DATE, DATETIME} → Warn. (11) IS_PK && !IS_MANDATORY → Warn 'A null PK will cause MergeUpsert to fail'. (12) SEMANTIC_ROLE in {PRICE, QTY, TOTAL} && DATA_TYPE not in {DECIMAL, INT} → Warn. (13) IS_DERIVED with no LOGIC_CONFIG.Formula → Warn 'This column will remain empty'. Then UX_CONFIG + LOGIC_CONFIG bags and UX_CONFIG.HeaderColor as hex. These 4 cross-field conflicts (6,7,8,11) are exactly the pairs a Console checkbox UI should refuse to let a human tick together.

*certain* — mbiXaddin/Core/Entities/SchemaRuleEntity.cs:461-573 — e.g. :511-515 `if (IS_PK && IS_VIRTUAL) yield return ValidationResult.Fail(nameof(IS_PK), $"Column '{FullKey}' cannot be both a Primary Key and Virtual.", SystemConstants.ErrorCodes.InvalidFormat);`

### Complete per-row rules for sheet 3 (DataSource) — what DataSourceEntity.Validate() checks

Eight rules. (1) SOURCE_KEY blank → CRITICAL + yield break ('All further validation for this row is skipped'); convention stated as '{TARGET_ENTITY_KEY}_{PROFILE_KEY}'. (2) TARGET_ENTITY_KEY blank → CRITICAL. (3) PROFILE_KEY blank → Error 'no column can be mapped and the table will be empty after sync'. (4) SOURCE_URI → delegated to SourceUriValidator (see its own answer). (5) SOURCE_REGION, if non-blank, must be 'GLOBAL' or exactly two ASCII letters, else Warn — and the message states the consequence: 'An unrecognised region code will cause SecurityContext.CanSyncSource() to block all users from syncing this source.' (6) DISPLAY_LABEL blank → Warn. (7) IS_ACTIVE=false → Warn tagged [INFO] ('SyncManager will skip this source entirely'). (8) CONTEXT_PROPS + RIBBON_CONFIG bags, and RIBBON_CONFIG.ControlSize. Nothing validates VERSION_TAG, MIN_LICENSE_REQ, Note or Drive.

**Accepted:** `SOURCE_REGION: 'GLOBAL', OR any 2-letter A-Z code (e.g. SA, EG, AE), OR empty. Not a closed enum — any two letters pass.`

*certain* — mbiXaddin/Core/Entities/DataSourceEntity.cs:288-393 — region rule at :337-357 `bool isIsoCode = regionUpper.Length == 2 && regionUpper[0] >= 'A' && regionUpper[0] <= 'Z' && regionUpper[1] >= 'A' && regionUpper[1] <= 'Z';`

### Complete SOURCE_URI rules — the highest-value drop-down/validation target for the Console

Six rules, in a pure unit-tested class. (1) blank → CRITICAL, with the literal fix instructions 'File → Share → Publish to web → select sheet → TSV format'. (2) not starting with https:// or http:// AND not a local path (leading '/', contains '\\', or char[1]==':') → ERROR + yield break; 'FTP, relative paths, and bare filenames are not supported.' (3) http with no '.' after '//' → Warn. (4) URI containing 'docs.google.com' WITHOUT 'output=tsv' or 'format=tsv' → ERROR, described in the file header as 'the single most common data-entry mistake'. (5) docs.google.com without 'gid=' → Warn 'always reads the first tab'. (6) local path without .csv/.tsv/.txt anywhere in the string → Warn. All matching is case-insensitive substring, so the Console can implement rules 4 and 5 as literal substring tests.

*certain* — mbiXaddin/Core/Validation/SourceUriValidator.cs:85-104 — `bool hasTsvParam = sourceUri.IndexOf("output=tsv", StringComparison.OrdinalIgnoreCase) >= 0 || sourceUri.IndexOf("format=tsv", StringComparison.OrdinalIgnoreCase) >= 0; bool hasGid = sourceUri.IndexOf("gid=", StringComparison.OrdinalIgnoreCase) >= 0;`

### Complete per-row rules for sheet 4 (DataMap), including the TRANSFORM_CHAIN vocabulary

Eight rules. (1) PROFILE_KEY blank → CRITICAL + yield break. (2) TARGET_ATTRIBUTE_KEY blank → CRITICAL + yield break. (3) SOURCE_EXPRESSION blank → Error. (4) SOURCE_TYPE != Header while MATCH_MODE != Exact → Warn 'MATCH_MODE is only used when SOURCE_TYPE=Header'. (5) SOURCE_TYPE=Index with a SOURCE_EXPRESSION that is not a non-negative integer → Error. (6) TRANSFORM_CHAIN: pipe-separated; each segment's command name (text before the first ':') must be one of ten known commands, else Warn ERR_TRANSFORM. (7) PROCESS_CONFIG bag syntax/keys. (8) NullStrategy + ErrorStrategy against MapStrategies, RowFilter against RowFilterOperators, and a Warn when either strategy is 'UseDefault' but DefaultValue is null.

**Accepted:** `TRANSFORM_CHAIN commands (pipe-separated, case-insensitive, ':' introduces an argument): TRIM, UPPER, LOWER, TO_DECIMAL, TO_INT, TO_DATE, TO_BOOL, ABS, SUBSTRING, JSON_EXTRACT — resolved from SystemConstants.Transforms.{Trim,Upper,Lower,ToDecimal,ToInt,ToDate,ToBool,Abs,Substring,JsonExtract}`

*certain* — mbiXaddin/Core/Entities/DataMapEntity.cs:288-338 — known-command set built at :290-302, unknown → `ValidationResult.Warn(nameof(TRANSFORM_CHAIN), $"Mapping '{FullKey}' uses unknown transform command '{cmdName}'.", SystemConstants.ErrorCodes.UnknownTransform)` at :315-318

### Complete per-row rules for sheet 5 (ExportViews)

Six rules — the thinnest of the six sheets. (1) VIEW_KEY blank → CRITICAL + yield break. (2) ENTITY_KEY blank → CRITICAL 'Cannot determine parent entity'. (3) LABEL blank → Warn 'VIEW_KEY will be used as button text'. (4) COLUMNS non-empty but parsing to zero entries → Warn 'Check format (comma-separated)'. (5) ALIASES → JSON syntax ONLY, deliberately using ValidateBag<object> so the arbitrary alias keys are not key-checked. (6) VIEW_CONFIG bag + HeaderStyle/FooterStyle against BannerStyles. NOTHING validates that ENTITY_KEY actually exists (that only happens transitively via the L4 link guard when another entity links to this view), and nothing validates COLUMNS entries against SchemaRule.ATTRIBUTE_KEY, WHERE_FILTER, or SORT_BY — those are free strings here. That is a genuine gap the Console can close with a drop-down.

*certain* — mbiXaddin/Core/Entities/ExportViewEntity.cs:305-347 — `foreach (var r in ConfigValidator.ValidateBag<object>("ALIASES", ALIASES_RAW)) yield return r;` at :339 (the `object` shape deliberately skips L2)

### Complete per-row rules for sheet 6 (RibbonControls), and the complete ACTION_CLASS vocabulary

Ten rules: ITEM_KEY blank → CRITICAL + yield break; ITEM_KEY >100 → Error; CONTROL_KEY blank → Warn (defaults to 'mnuDynamic'); CONTROL_KEY >100 → Error; REGION blank → Warn (defaults GLOBAL); REGION non-GLOBAL split on ',' — each part must be exactly 2 letters else Warn; ACTION_CLASS blank → Error; non-menu row with blank ACTION_TAG → Error; menu container WITH an ACTION_TAG → Warn ('Menu containers are not clickable'); ITEM_KEY==PARENT_KEY → CRITICAL; ORDER < 0 → Warn; and four ICON format rules — leading/trailing whitespace → Warn, >200 chars → Error, a name containing '.' with nothing after the final '.' → Warn, and '..' path traversal → Warn. ACTION_CLASS is a closed vocabulary of EIGHT values in two disjoint groups, and matching is case-insensitive throughout. WARNING — STALE MESSAGE IN THE CODE: the ACTION_CLASS-blank error text at RibbonControlEntity.cs:475 says 'Allowed: Menu, ExportEntity, DownloadService, OpenView' — three of those four names are DEAD (ActionRouter's comment at :124-128 records that the ExportService/DownloadService aliases were deliberately removed). Do NOT build the drop-down from that message; build it from the two arrays below.

**Accepted:** `Clickable (routed by ActionRouter, case-insensitive): Download, Stream, Export, UpdateTable`, `Menu-producing (never routed; read when the menu is built): Menu, Library, ExportTree, ViewList`

**Blank means:** CONTROL_KEY blank → 'mnuDynamic' (RibbonControlEntity.cs:359-360). REGION blank → treated as GLOBAL (IsGlobal, :345-347). ACTION_CLASS blank → no default; the row errors and the click shows an 'Unknown Action' dialog.

*certain* — mbiXaddin/UI/Commands/ActionRouter.cs:102 — `private static readonly string[] KnownActions = { "Download", "Stream", "Export", "UpdateTable" };` and mbiXaddin/Core/Entities/RibbonControlEntity.cs:337 — `public static readonly string[] MenuActionClasses = { "Menu", "Library", "ExportTree", "ViewList" };` — both directions pinned by tests/Core.Tests/RibbonMenuActionClassTests.cs:38-47

### The tests over the config — name each file and what it asserts

Eight files in tests/Core.Tests are a direct statement of the config rules. ConfigValidatorTests.cs (190 lines) — the four layers: 4 malformed-JSON shapes are Error/INVALID_JSON with 'ignored at runtime' in the message; null/''/'   ' are NOT errors; unknown key is Warn with a suggestion; ValidateBag<object> skips key checking; allowed-value is case-insensitive with suggestion; hex color accepts #abc and #4472C4, rejects 'blue', '#12', '4472C4', '#GG0000'; ValidateLink warns BROKEN_LINK for unknown entity and unknown view, and a null known-set skips that side. EntityBagValidationTests.cs (215) — drives each of the five entities' Validate() end-to-end for its bags; pins the real incident '{"AutoFitColumns":TRUE}', 'FotterText'→FooterText, 'Marketng'→Marketing, RowFilter 'CONTAINZ'→CONTAINS with 'every row is kept', 'Skipp'→Skip, and UseDefault-without-DefaultValue. SchemaIntegrityCheckTests.cs (140) — GetEntityColumns honours [JsonProperty], skips [JsonIgnore], removes exclusions, is case-insensitive; Compare reports MISSING_COLUMN (Error) and DEAD_COLUMN (Warning) in both directions and yields NOTHING when the table has no columns (fresh DB). Tier1SchemaDriftTests.cs — SHIP-BLOCKING: executes the real DDL against in-memory SQLite and runs the guard over the real six entities. SourceUriValidatorTests.cs — one test per URI rule. RibbonControlEntityIconValidationTests.cs — the six ICON rules. RibbonMenuActionClassTests.cs — pins MenuActionClasses in BOTH directions plus the live regression 'ViewList ×2' must not partially match. LinkedEntitiesTests.cs — the 'Entity|View' compact syntax, comma AND semicolon separators. Plus ValidationResultTests.cs (the factory semantics) and DataSourceEntityProfileTests.cs (blank/'DEFAULT' → target entity; custom used verbatim).

*certain* — tests/Core.Tests/ — ConfigValidatorTests.cs:32-42, EntityBagValidationTests.cs:24 (`e.UX_CONFIG_RAW = "{\"AutoFitColumns\":TRUE}";   // uppercase boolean — the real incident`), SchemaIntegrityCheckTests.cs:127-131, Tier1SchemaDriftTests.cs:50-60, RibbonMenuActionClassTests.cs:71-80

### Is there a model-vs-database drift guard, and is it enforced in CI?

YES — SchemaGuard.cs holds both the map and the check, and it IS ship-blocking in CI. SchemaGuardMap.Entries names the six entity-backed tables (_SYS_DEFINITIONS, _SYS_SCHEMA_RULES, _SYS_DATA_SOURCES with SOURCE_URI deliberately excluded from persistence, _SYS_DATA_MAP, _SYS_EXPORT_VIEWS, _SYS_RIBBON_CONTROLS) — note the three operational tables (_SYS_PERSISTENT_ALERTS, _SYS_PIPELINE_LOG, _SYS_SYNC_STATE) are deliberately absent. SchemaIntegrityCheck.Compare yields MISSING_COLUMN (Error — 'the next sync INSERT will crash') for an entity property with no column, and DEAD_COLUMN (Warning — 'never populated') for the reverse. It runs at startup via MetadataOrchestrator.Tier1Schema.cs:184/205-216 AND as the ship-blocking test Tier1SchemaDriftTests.Every_guarded_entity_matches_the_Tier1_DDL. This matters to the Console: it is why the six sheets' column sets cannot silently drift from the add-in's model — but it guards the DB schema, NOT the Google Sheet's header row, which has no equivalent guard beyond TsvParser's 'nothing matched' check.

*certain* — mbiXaddin/Core/Configuration/SchemaGuard.cs:61-69 (the map) and :120-134 (Compare); enforced by tests/Core.Tests/Tier1SchemaDriftTests.cs:50 `public void Every_guarded_entity_matches_the_Tier1_DDL()`

### Where do findings actually GO, and would a real user ever see them? (decides how much the Console is adding)

Nowhere a user can see. The persistent-alert path was RETIRED: ValidationLogBridge's header states it 'Replaces the retired ValidationAlertBridge (which wrote rows to the _SYS_PERSISTENT_ALERTS DB table via PipelineLogger)'. Every fetch-time and sync-time finding now goes to the developer log at WARNING level only. In the shipped 'people' build LogPolicy.FileMinSeverity(User) == Severity.Error, so EVERY Warning-level config finding — which is the great majority of the rules above, including BOTH of your measured defects — is written nowhere at all. The only live surface is the ETL Console, and that is hidden outside a Developer build. CONFIRMING SIGNAL: AlertCatalog in PipelineDomain.cs still declares a full alert taxonomy (PK_MISSING, MANDATORY_UNMAPPED, ORPHAN_MAPPING, KEY_SPACES, SCHEMA_CHANGED, INVALID_JSON, VALIDATION_FAIL, VALIDATION_WARN, UNKNOWN) but I grepped all of mbiXaddin/ and NO production code references any AlertCatalog descriptor — it is dead. CONCLUSION FOR THE CONSOLE: it is not duplicating a working feedback loop; it is restoring one that was disconnected. BACKLOG.md:187-190 measures the cost: '701 ERROR + 45 FATAL in one day's log, all authoring issues ... and 10 rejected RibbonControlEntity rows — those ribbon rows are silently dead data.'

**Accepted:** `PK_MISSING`, `MANDATORY_UNMAPPED`, `ORPHAN_MAPPING`, `KEY_SPACES`, `SCHEMA_CHANGED`, `INVALID_JSON`, `VALIDATION_FAIL`, `VALIDATION_WARN`, `UNKNOWN`

*certain* — mbiXaddin/Infrastructure/Logging/LogSinks.cs:66-67 — `public static Severity FileMinSeverity(RuntimeMode mode) => mode == RuntimeMode.Developer ? Severity.Debug : Severity.Error;` and mbiXaddin/Core/Validation/ValidationLogBridge.cs:38 — `log.LogWarning($"[{ctx}] {result}", source);`

### Complete ErrorCodes vocabulary — the CODE column the ETL Console renders and the Console should reuse

SystemConstants.ErrorCodes defines 18 codes; the config-loading path uses eight of them (ERR_FORMAT, ERR_NULL, ERR_LENGTH, ERR_REF, ERR_DUPLICATE, ERR_CIRCULAR, ERR_REQUIRED, ERR_TRANSFORM). Separately, ConfigValidator and SchemaIntegrityCheck define their OWN string codes that do NOT come from this class — INVALID_JSON, UNKNOWN_KEY, INVALID_VALUE, INVALID_COLOR, BROKEN_LINK, MISSING_COLUMN, DEAD_COLUMN. A Console reproducing the Code column must merge both sets: there are two independent code namespaces here, which is worth knowing before you build a filter drop-down over them. Note also the default: ValidationResult.Warn and .Fail default errorCode to ERR_FORMAT while .Critical defaults to ERR_REQUIRED.

**Accepted:** `ERR_FORMAT`, `ERR_NULL`, `ERR_LENGTH`, `ERR_REF`, `ERR_DUPLICATE`, `ERR_TIER`, `ERR_CIRCULAR`, `ERR_REQUIRED`, `ERR_PRESET`, `ERR_FORMULA`, `ERR_TRANSFORM`, `ERR_DB_WRITE`, `ERR_DB_READ`, `ERR_SCHEMA`, `ERR_NO_RATE`, `ERR_NO_UNIT`, `ERR_OVERFLOW`, `ERR_NO_COST`, `INVALID_JSON`, `UNKNOWN_KEY`, `INVALID_VALUE`, `INVALID_COLOR`, `BROKEN_LINK`, `MISSING_COLUMN`, `DEAD_COLUMN`

**Blank means:** ValidationResult.Warn/.Fail default to ERR_FORMAT; .Critical defaults to ERR_REQUIRED (Validation.cs:85, :91, :97).

*certain* — mbiXaddin/Core/Constants/SystemConstants.cs:356-379 and mbiXaddin/Core/Configuration/ConfigValidator.cs:31-35; defaults at mbiXaddin/Core/Validation/Validation.cs:84-99

### Is there documentation of the workbook contract in docs/ or BACKLOG.md, and has it drifted?

There is NO workbook-contract document in docs/ — the five files there cover the icon pipeline, release automation, machine setup, a sync-architecture review, and ribbon button states. BACKLOG.md mentions the config only once, at :187-190, as a measurement rather than a contract. The real in-app documentation is SchemaGuidePanel.cs, a user-facing Schema Reference pane (reachable from the User Guide, not gated to Developer) with a column grid, allowed values, examples, defaults and per-column 'what happens if empty / duplicate / wrong' notes. VERIFY BEFORE TRUSTING IT — it has drifted: its own header claims to document only FOUR tables ('SYS_DEFINITIONS — 15 columns, SYS_SCHEMA_RULES — 14 columns, SYS_DATA_SOURCES — 10 columns, SYS_DATA_MAP — 7 columns'), so SYS_EXPORT_VIEWS and SYS_RIBBON_CONTROLS are undocumented entirely, and the counts disagree with your live sheets (TableDefinition has 14 columns not 15; DataSource has 12 including Note and Drive, not 10). Treat it as a lead for prose and consequence wording, never as the column list.

*certain* — mbiXaddin/UI/TaskPane/Views/SchemaGuidePanel.cs:15-19 — `* TABLES DOCUMENTED:\n *   1. SYS_DEFINITIONS     — 15 columns (PK_TYPE removed per TASK-001)\n *   2. SYS_SCHEMA_RULES    — 14 columns\n *   3. SYS_DATA_SOURCES    — 10 columns\n *   4. SYS_DATA_MAP        —  7 columns`; pane registered at mbiXRibbon.cs:1241

### What per-cell DATA_TYPE validation runs on the actual data rows (ValidateRawRow), and is it sampled or exhaustive?

SAMPLED, not exhaustive — ExecuteMapping runs it only while `validatedRows < MaxValidateSampleRows`, so a bad value beyond the sample is never reported by this path. Rules: an empty cell in an IS_MANDATORY column rejects the ROW ('Row will be REJECTED and not inserted into the database. Fix this cell in the Google Sheet and re-sync'); an empty optional cell is stored as NULL with no finding. Non-empty values are parsed by SmartConverter — the SAME converter DataIngestionService uses, so 'a value that passes validation will never fail ingestion'. DECIMAL/PERCENTAGE and INT failures are Errors (INT additionally rejects any value where parsed != Math.Floor(parsed)); BOOL failure is an Error; DATE/DATETIME failure is an Error, and a successfully parsed date with Year < 1900 is a WARNING ('Likely a data entry error ... Value will be stored'); GUID failure is only a WARNING ('stored as TEXT but FK lookups may fail'); TEXT / JSON / BLOB get no type validation at all. The accepted input formats are stated in the user-facing messages themselves and are worth copying into Console placeholder text.

**Accepted:** `DECIMAL / PERCENTAGE: 1234.56, 1,234.56, 1.234,56, ١٢٣٤, ﷼1200`, `INT: same formats as DECIMAL but must be whole (3.14 rejected)`, `BOOL: true/false, 1/0, yes/no, y/n, نعم/لا, on/off, صح/خطأ`, `DATE / DATETIME: yyyy-MM-dd, dd/MM/yyyy, dd-MM-yyyy, MM/dd/yyyy, dd MMM yyyy, plus Arabic-digit dates (٢٠٢٥-٠١-١٥)`, `GUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (failure is Warning only)`, `TEXT / JSON / BLOB: no validation — anything accepted as-is`

**Blank means:** Empty + IS_MANDATORY=true → row REJECTED (ValidationOrchestrator.cs:289-306). Empty + optional → stored as NULL, no finding (:310-318). A non-empty value that fails its type parse is stored as NULL and counted in the ConvertFailed lineage (DataIngestionService.Mapping.cs:211-215).

*certain* — mbiXaddin/Core/Validation/ValidationOrchestrator.cs:528-699 (ValidateDataTypeWithDetail) — INT rule at :574 `if (!parsed.HasValue || parsed.Value != Math.Floor(parsed.Value))`; pre-1900 Warn at :647; sampling gate at DataIngestionService.Mapping.cs:167 `if (validateSchema != null && validatedRows < MaxValidateSampleRows)`

### Summary: which validations does the add-in NOT perform — the gaps the Console must invent rather than mirror?

Eight real gaps. (1) DataMap PROFILE_KEYs referenced by no DataSource — no check anywhere (grepped mbiXaddin/ and tests/); silently inert. (2) ExportViews.ENTITY_KEY existence is never checked directly (only transitively, if some other entity links to the view). (3) ExportViews.COLUMNS / ALIASES keys / WHERE_FILTER / SORT_BY are never validated against SchemaRule.ATTRIBUTE_KEY — free strings. (4) RibbonControls.ACTION_TAG's entity/view halves are never resolved against the registry at load time. (5) RibbonControls.PARENT_KEY is checked only for SELF-reference; no check that the parent ITEM_KEY exists, and no multi-hop cycle detection (same for TableDefinition.PARENT_KEY). (6) No uniqueness check on ITEM_KEY, VIEW_KEY, or the (PROFILE_KEY, TARGET_ATTRIBUTE_KEY) pair — only ENTITY_KEY and SOURCE_KEY have duplicate detection. (7) DataSource.VERSION_TAG, MIN_LICENSE_REQ, Note, Drive and RibbonControls' Excel/File/Folder columns have no rules at all. (8) The [NO_MAPPING] check uses the raw PROFILE_KEY instead of ResolveProfileKey(), so it both false-positives on 'DEFAULT' and skips blank keys — the Console should use the resolved key.

*certain* — Absence confirmed by `grep -rn "unused profile|unreferenced|orphan profile|ORPHAN_MAP|ORPHAN_PROFILE" --include=*.cs mbiXaddin/ tests/` returning no production hit; the raw-key bug is visible at mbiXaddin/Infrastructure/Services/Sync/Metadata/MetadataOrchestrator.cs:618 — `string profile = src.PROFILE_KEY;` versus DataSourceEntity.cs:257-261 `ResolveProfileKey()`
