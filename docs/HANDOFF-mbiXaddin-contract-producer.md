# Handoff — make mbiXaddin publish its own configuration contract

*Paste everything below into a session working in
`C:\Users\User01\source\repos\mbiXaddin`. It is self-contained; that session
needs no knowledge of the conversation this came from.*

---

## The problem you are solving

mbiXaddin is configured entirely by six Google Sheets tabs — TableDefinition,
SchemaRule, DataSource, DataMap, ExportViews, RibbonControls. Today those tabs
are edited **by hand in Google Sheets**, which is editing a database through a
text box: every reference is a string nobody checks, and a mistake surfaces as a
table that fails to load in front of whoever is using Excel that morning.

A separate tool — **ScrapeX**, a Chrome extension — is being given a Console
that edits that workbook through the Sheets API with drop-down lists and
validation, so a bad value is caught before it ships. To do that, the Console
must know what your C# actually accepts: every enum, every allowed value, every
JSON config key.

**Right now it knows because seven agents read your ~350 `.cs` files and
transcribed the answers.** That transcript is a snapshot dated 2026-08-12. The
first `enum` anyone adds makes it wrong, and nothing anywhere fails.

**Your job: make mbiXaddin emit that contract itself, so nobody transcribes it
again.**

---

## What to build

### 1. `contract/addin-contract.json`, generated from the code

A single file at the repository root under `contract/`, emitted by reflecting
over the real enums and constants — not typed by hand. The exact shape is
below; ScrapeX already consumes this shape, so **do not redesign it**. Add
fields if you need to; do not rename or remove.

The values it must carry come from (paths verified 2026-08-12):

| what | where it lives |
|---|---|
| the six tab gids | `mbiXaddin/Core/EndpointCatalog.cs` — the compiled defaults at ~`:56-62` |
| transforms | `SystemConstants.Transforms.*` |
| enums for SOURCE_TYPE, MATCH_MODE, SEMANTIC_ROLE, DATA_TYPE, ENTITY_TYPE, STORAGE_STRATEGY, LICENSE_TIER, VIEW_MODE, MENU_LAYOUT, ACTION_CLASS | `mbiXaddin/Core/Constants/SystemConstants.cs` and the entity types in `mbiXaddin/Core/Entities/` |
| the JSON config-bag keys | UX_CONFIG, LOGIC_CONFIG, PROCESS_CONFIG, CONTEXT_PROPS, VIEW_CONFIG readers |
| boolean spellings | `SmartConverter.IsTrue` — **note it accepts Arabic**: `نعم صح صحيح` / `لا خطأ غلط` |
| severities and error codes | the validation layer's `ValidationResult` severities and `ErrorCodes` |

```jsonc
{
  "contractVersion": 1,        // bump when a vocabulary gains or loses a value
  "behaviourVersion": 1,       // see below — a HUMAN raises this
  "readOn": "2026-08-12",
  "readFrom": "muhammadbayoumi/mbiXaddin",

  "sheets": {
    "1.TableDefinition": {
      "gid": "1974308164",
      "key": "ENTITY_KEY",       // the sheet's primary key, or null if composite
      "registryCritical": true,  // does a fetch failure here abort the whole sync
      "columns": ["ENTITY_KEY", "DISPLAY_NAME", "…"]
    }
    // … all six, in order
  },

  "vocabularies": {
    "SOURCE_TYPES": ["Header", "Index", "Context", "Constant", "Formula"],
    "TRANSFORMS":   ["TRIM", "UPPER", "…"]
    // … one array per enum, UPPER_SNAKE plural names
  },

  "constants": {
    "TRANSFORM_SEPARATOR": "|",
    "TRANSFORM_ARGUMENT_SEPARATOR": ":",
    "BLOCKS_SYNC_FROM": "Error"
  }
}
```

A working copy — the current values, hand-transcribed — is in the ScrapeX
repository at `contract/addin-contract.json`. **Read it, then make your
generator reproduce it.** Where your generated output disagrees with it, your
output is right and that file is stale: say so in your report, listing every
difference, because each one is a place the Console is currently wrong.

### 2. A test that fails when the file is stale

This is the whole point. Put it in `tests/Core.Tests`. It regenerates the
contract in memory and compares it against the committed file; on a mismatch it
fails and prints the diff.

**A developer who adds an enum value and does not regenerate must not be able to
commit.** That is the only mechanism here that does not depend on somebody
remembering.

### 3. Publish it to mbiX-hub

`.github/workflows/publish-assets.yml` already pushes `Icons/` and `plans.json`
to the delivery repos with `DELIVERY_REPO_TOKEN`. Add `contract/addin-contract.json`
to what it publishes, at a stable path — `mbiXaddin/contract/addin-contract.json`
is the suggestion, but any stable path is fine as long as you **report the exact
final URL**. ScrapeX already reads from `mbiX-hub`, so no new secret and no new
permission is needed.

### 4. `behaviourVersion` — and read this part carefully

`contractVersion` is mechanical. `behaviourVersion` is not, and pretending
otherwise would be the failure mode of this whole design.

Behaviour means things like:

- an **empty** `IS_ACTIVE` leaves the C# default, which is `true` — so a blank
  means the row is LIVE
- an **unrecognised** boolean (`Active`, `X`, `TRUE!`) also returns null, the
  TSV parser assigns only on a successful conversion, and the property therefore
  keeps that same `true` — **a typo switches a table on, silently**
- an unknown TRANSFORM name is dropped rather than refused
- a mapping targeting an attribute that does not exist is warned about and then
  **silently dropped** — "its data will be lost", in your own wording
- a source whose PROFILE_KEY has no DataMap rows **hard-fails** that source

None of that is in an enum, so no generator can find it. Raise
`behaviourVersion` by hand whenever you change any of it — error handling,
defaults, what is dropped versus what fails.

Raising it **deliberately breaks ScrapeX's gate**, with a message telling that
side to re-read the behaviour from your code before shipping. That is the design:
behaviour cannot be automated, so instead it is made impossible to change
*silently*.

### 5. A ledger, appended and never rewritten

`docs/addin-contract-changes.md`: one entry per change — what changed, when, and
which version was raised. The gate says *what* differs; the ledger says *why*.

---

## Rules

- **Do not modify the ScrapeX repository.** It consumes this; it does not
  co-author it. If the shape needs to change, say so in your report and stop.
- **Generate, never transcribe.** A hand-maintained list is what this replaces.
- **The test is the deliverable**, not the JSON. A generated file with no test
  guarding it goes stale exactly as fast as a typed one.
- If reflection cannot reach a vocabulary — a `switch` over string literals with
  no enum behind it — say so explicitly rather than hard-coding the values into
  the generator. A list the generator cannot derive is a list that will drift,
  and it is better named as a gap than hidden inside the tool.

## When you are done, report

1. The exact published URL.
2. Every difference between your generated output and ScrapeX's
   `contract/addin-contract.json` — each one is a live defect in the Console.
3. Any vocabulary you could not derive by reflection, and why.
4. The test's name and how to run it.
