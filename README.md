# ScrapeX Ecosystem

Contract-driven web data collection into a SQLite price-tracking warehouse,
publishing curated data to the Google Sheet the mbiX Excel add-in reads.
**The add-in is never touched** — the two systems meet only at the sheets.

> **Working on this project? Start at [CLAUDE.md](CLAUDE.md)** — the entry point
> for where the work stands, what the owner has ruled, and the lessons that are
> not visible in the code.

Rules: [ENGINEERING.md](ENGINEERING.md) ·
Compatibility contract: [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) ·
Generic catalogue: [docs/GENERIC_CATALOG.md](docs/GENERIC_CATALOG.md) ·
Current state: [docs/STATE.md](docs/STATE.md) ·
Plans: [docs/plans/](docs/plans/README.md)

```
{connectors, extension} → funnel (Apps Script) → staging sheet (_INBOX/_RUNS)
                        → scrapex ingest → harvest.db (the 13-section warehouse)
                        → census/curation (owner decides) → scrapex publish
                        → production sheet → SYS_* config tables → Excel add-in
```

## Setup (developer machine)

```powershell
cd ScrapeX
pip install -e .[dev]                    # + .[browser] for Playwright, .[ui] for the web UI
python -m pytest                         # tests must be green
python -m scrapex.cli init-db            # creates %USERPROFILE%\.scrapex\harvest.db
python -m scrapex.cli validate-manifest  # checks sources.yaml (same gate runs in CI)
```

> **`scrapex` command not found?** pip installs `scrapex.exe` into your Python
> Scripts dir, which may not be on PATH. Either use the always-works form
> `python -m scrapex.cli <command>`, or add Scripts to PATH once:
> ```powershell
> [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:APPDATA\Python\Python314\Scripts", "User")
> ```
> then reopen PowerShell. The rest of this README writes `scrapex …` for brevity —
> prefix with `python -m scrapex.cli` if you skipped the PATH step.

## One-time funnel setup (owner)

1. Create a Google Sheet named **ScrapeX Staging** (separate from production).
2. Extensions → Apps Script → paste `apps_script/StagingAppScript.txt`.
3. Project Settings → Script Properties → add `FUNNEL_TOKEN` = long random string:
   ```powershell
   -join ((48..57)+(97..122) | Get-Random -Count 48 | % {[char]$_})
   ```
4. Deploy → New deployment → **Web app** → Execute as: *Me* · Access: *Anyone*.
   Copy the `/exec` URL. *Anyone* is required — ScrapeX posts without a Google
   sign-in, so a narrower setting answers the login page instead of the script.
5. Set the environment and self-test:
   ```powershell
   $env:SCRAPEX_FUNNEL_URL   = "<exec url>"
   $env:SCRAPEX_FUNNEL_TOKEN = "<token>"
   scrapex funnel-test        # expect a FUNNEL_SELFTEST row in the _INBOX tab
   ```
6. Reload the spreadsheet once. A **ScrapeX** menu appears with *Rebuild tables
   from _INBOX*, which turns the raw chunk rows into one readable tab per
   `source_key` (newest complete batch wins, tab replaced wholesale — that is
   the sync). `doPost` is untouched by it: the sync only reads `_INBOX`, so the
   audit log Python ingests stays exactly as it was.

The token lives ONLY in: Script Properties, your env, GitHub Secrets (later),
and the extension's chrome.storage (later). Never in code or the repo (A4).

## Layout

| Path | Role |
|---|---|
| `ENGINEERING.md` | The build rules (derived from the owner's review protocol) |
| `sources.yaml` | The Harvest Manifest — per-source extraction contracts |
| `db/schema.sql` | Warehouse DDL (migration 0001) — the only DDL truth |
| `scrapex/` | `vocab` · `payload` (T8 contract) · `db` · `config` · `normalize` · `funnel` · `connectors/` · `cli` |
| `contracts/` | Exported payload JSON schema + golden fixtures (shared with the extension & GAS) |
| `apps_script/StagingAppScript.txt` | The funnel (S1: token + LockService + append + ack) |
| `tests/` | 68 tests: schema triggers, contract, chunking, manifest, db, normalize |

## Command surface (grows by phase)

Now: `init-db` · `validate-manifest` · `crawl` · `ingest` · `peek` · `ui` · `export` · `status`
Later: `census` · `apply-decisions` · `feeds` · `publish`

## Local export (no Google needed)

The offline twin of `push`: writes the **same columns in the same arrangement**
(a workbook with one tab per source) to a local `.xlsx` file — same
`export_source_table` data, just a different sink.

```powershell
pip install -e .[local]                 # once
scrapex export ELSEWEDYSHOP             # -> %USERPROFILE%\ScrapeX\ScrapeX Data.xlsx
scrapex export ELSEWEDYSHOP --folder D:\prices --workbook "Q3 prices"
```
Re-running replaces that source's tab; other sources' tabs are left intact
(one workbook, a tab per source — mirrors the Drive layout exactly).

## Google Sheets and Drive — in the side panel

Signing in to Google, backing the warehouse up to Drive, creating a spreadsheet
and writing rows into it are all done by the **ScrapeX extension**, not by this
engine. The owner ruled on 2026-08-11 that the engine fetches data and saves it
locally, and that every Google operation belongs to the panel.

That is not only tidier. Chrome already holds a Google token for the extension,
so the panel needs no `client_secret.json`, no second consent screen and no
OAuth libraries — and the scope stays `drive.file`, which is non-sensitive.
The engine used to ask for `spreadsheets` as well, which is Google's SENSITIVE
scope, for work that `drive.file` covers.

`scrapex export` is unchanged: it writes an .xlsx on this machine and involves
no account at all.

## Browse UI

```powershell
pip install -e .[ui]     # once
scrapex ui               # opens http://127.0.0.1:8000 in your browser
```
Read-only browse of the warehouse: sources overview + per-source price table with
search, availability filter, and pagination. Local only (127.0.0.1); the web layer
holds zero SQL — it reuses the same `reports.py` queries as `peek`.
