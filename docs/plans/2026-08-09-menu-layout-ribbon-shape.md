# MENU_LAYOUT — make a ribbon menu's SHAPE data, not code

## Context

The `feature/repository-menu-large-tiles` branch adds a second menu shape (Data-Types-style
tiles). It is a good feature with the wrong switch: the shape is chosen from
`RibbonMenu.ItemSize`, set in `mbiXRibbon.Designer.cs`. Changing one menu's appearance
therefore costs a code edit, a rebuild and a release to every user.

This is the same shape of problem as the 30 hand-authored sika rows: a decision living in
code that the data could carry. The ribbon already has `ACTION_CLASS` deciding **what an item
does**; what is missing is a column deciding **how a menu is drawn**. They are independent
axes — a library menu and an export tree may want the same shape for different actions, and
the same action may want different shapes in different menus.

Outcome: one new column, `MENU_LAYOUT`, giving four shapes across both tree-driven menu
builders, with today's behaviour as the default so nothing changes until a cell is filled.

## Owner decisions already taken

- A **new column**, not new `ACTION_CLASS` values — the two axes stay separate.
- **Four layouts** now: `Nested` (default, today), `Tiles` (the branch), `Grouped`, `Flat`.
- Scope: **`LibraryMenuBuilder` + `ExportTreeMenuBuilder`**. The authored-row engine
  (`BuildSubMenu`/`BuildButton`) is out of scope this round.

## Where the layout lives — settled by the data

`mnuRepository`, `mnuEurocode` etc. are declared in the Designer and are referenced from the
sheet only as `CONTROL_KEY`. There is **no row whose `ITEM_KEY` is a top-level menu name**
(verified against the live DB copy: the only `mnu*` ITEM_KEYs are sub-menu containers such as
`mnu_MaterialPriceList`, `ACTION_CLASS='Menu'`).

But the top-level menus that need reshaping have **exactly one row each**:

```
mnuRepository 1 · mnuEurocode 1 · mnuLabor 1 · mnuEquipment 1 · mnuMaterial 24 · mnuBOQ 19
```

So `MENU_LAYOUT` rides on **the row that supplies the menu's content** — no new rows, no new
concept for whoever edits the sheet:

| The row | Governs |
|---|---|
| the sole top-level `Library`/`ExportTree` row | that whole top-level menu (the `mnuRepository` case) |
| an `ACTION_CLASS='Menu'` container row | that sub-menu |
| blank | inherit the parent, ultimately `Nested` |

This reuses an existing precedent exactly: `rootLabel` already reaches for the same row's
`LABEL` (`RibbonControlService.cs:713-722` → `ExportTreeMenuBuilder.cs:119-121`).

## Step 0 — verify before writing anything

**Is `RibbonMenu.ItemSize` honoured when set after the ribbon has loaded?** The branch sets it
in `InitializeComponent`, i.e. before first render. If Office ignores a later change, the
layout is fixed at load and a region change or registry rebuild cannot reshape a menu until
Excel restarts. That is a real constraint the owner must know before the feature is promised,
not after.

Check: set `ItemSize` inside `FillMenu` (the `ItemsLoading` path) and confirm the tiles render.
If it does not hold, fall back to shapes that need no `ItemSize` change (`Grouped`, `Flat`,
`Nested` all work at regular size) and document `Tiles` as load-time only.

## The four layouts

Defined against the concrete differences the branch already implements:

| Layout | Nesting | Icon | Group levels | Footer |
|---|---|---|---|---|
| `Nested` *(default)* | sub-menus | regular | become sub-menus | count shown |
| `Tiles` | flattened | 32px, above label | titled separators | skipped |
| `Grouped` | flattened | regular | titled separators | count shown |
| `Flat` | flattened | regular | dropped | count shown |

`Tiles` and `Grouped` are the same renderer with a different icon size; `Flat` is the same
renderer with headers suppressed. Three of the four are one code path.

## Files to change

**Mandatory — a column added to fewer than all three of these is silently dropped:**

1. `mbiXaddin/Core/Entities/RibbonControlEntity.cs` — add `MENU_LAYOUT` beside `ACTION_CLASS`
   (~line 176). Type it `string`, matching every other column on this entity; parse it
   defensively at the point of use rather than as a `StringEnumConverter` property, because
   the second hop (below) is hand-written and would bypass a converter.
2. `mbiXaddin/Infrastructure/Database/SqlBuilderService.cs:435-448` — the TIER-1
   `CREATE TABLE` body. `SchemaIntegrityCheck` raises `MISSING_COLUMN` as a **hard failure**
   if the entity has a property the DDL lacks, so this is not optional. No
   `Tier1SchemaVersion` bump: the rebuild is triggered by the DDL fingerprint.
3. `mbiXaddin/UI/Commands/RibbonControlService.cs:468-488` `ParseRow` — hand-lists every
   column read back from SQLite. A column missing here is loaded by `SELECT *` and then
   dropped without a word.

**The switch and the renderers:**

4. New pure file `mbiXaddin/Core/UI/MenuLayout.cs` — the `MenuLayout` enum plus
   `MenuLayoutParser.Parse(string, out bool unrecognised)`. Follow
   `Core/Licensing/LicenseProfileMapper.cs:53-57` exactly: `Enum.TryParse` **and**
   `Enum.IsDefined` (TryParse accepts numeric strings), blank → default and NOT flagged,
   non-blank-but-unresolved → default and flagged. Core/UI so it links into `UI.Tests`.
5. `mbiXaddin/UI/Commands/LibraryMenuBuilder.cs` — `Fill(...)` gains a trailing optional
   `MenuLayout layout = MenuLayout.Nested`; `Render` branches to the existing nested path or a
   flattening path carrying `isLarge` and `showHeaders`.
6. `mbiXaddin/UI/Commands/ExportTreeMenuBuilder.cs` — the same trailing optional parameter and
   the same branch. Its tree is structurally the same, so the flattening helper is shared.
7. `mbiXaddin/UI/Commands/RibbonControlService.cs` — `FillLibraryInto` (~:739) and
   `FillExportTreeInto` (~:713) resolve the layout from the row and pass it down; log a warning
   naming the valid values on an unrecognised cell, mirroring `ActionRouter.cs:147-159`.

**Merge first:** the branch must be merged before step 5 — its `RenderFlat` is the `Tiles`
renderer. The merge was probed in a scratch worktree: clean, builds, 1367 tests pass.

## Two existing defects to fix while in these files

Both are stale spellings of the same value, found during exploration:

- `RibbonControlService.cs:480` writes `?? "ExportEntity"` and `SqlBuilderService.cs:441`
  defaults `ACTION_CLASS` to `'ExportEntity'` — a spelling `ActionRouter` no longer accepts
  after the unification to `Export`. Same stale literal at `RibbonControlService.cs:695`,
  `:835`, `:1015` and in `RibbonControlEntity.Validate()`'s message.
- The `COLUMNS (12)` header and the two column-reference tables in `RibbonControlEntity.cs`
  (~:50, :525, :565) go stale the moment the column lands.

## Verification

1. `MSBuild mbiXaddin.csproj -t:Build` — clean. (Close Excel first: it locks
   `SQLite.Interop.dll` and blocks `-t:Rebuild`.)
2. `dotnet test mbiXaddin.slnx` — baseline **1367 passing across 10 projects**. *(An explore
   agent reported "no test project exists"; that is wrong — it searched only under
   `mbiXaddin/`.)*
3. New `tests/UI.Tests/MenuLayoutTests.cs` — the parser truth table: each name round-trips,
   case-insensitive, blank → `Nested` and NOT flagged, unknown → `Nested` AND flagged,
   numeric string rejected. Mirrors `LicenseProfileMapperTests`.
4. New guard in `tests/Sync.Tests` — assert `MENU_LAYOUT` appears in all three mandatory
   sites, so the next column added cannot be half-wired. The `ParseRow` omission is invisible
   at runtime and is exactly what a source-text guard is for.
5. Live in Excel: put `Tiles` on the `mnuRepository` row, reload, confirm tiles; switch to
   `Grouped`, resync, confirm the shape changes **without** restarting Excel — this is the
   Step 0 constraint, observed rather than assumed.
6. Blank the cell on every row and confirm every existing menu is byte-identical to today.

## Rollout constraint

Do **not** fill `MENU_LAYOUT` in the live sheet until the build carrying it has reached all
users. Precedent: an unknown `SEMANTIC_ROLE` value in cached metadata threw and dropped the
whole `SchemaRuleEntity` row — which is why `EXPORT_GROUP` was held back. A `string` column
read through `SafeStr` is far safer than an enum property, but the ordering rule stands:
ship the reader first, fill the cell second.
