# ScrapeX

ScrapeX collects published web data into a SQLite warehouse on your own machine, in
categories: products, organizations and tenders (`SourceCategory` in `scrapex/vocab.py`).
It has two parts: a Chrome extension, whose side panel is where all the work is done
(`extension/`), and a local engine, `scrapex-engine.exe`, built from `scrapex/`, which
crawls and writes the warehouse. The panel signs in to Google itself and writes the
collected tables to Google Sheets, where the mbiX Excel add-in reads them.

## Install and run

None of these steps needs a terminal.

1. In Chrome, open `chrome://extensions`, turn on **Developer mode**, choose
   **Load unpacked** and select this repository's `extension/` folder.
2. Open the ScrapeX side panel, go to **Engine** and press **Download engine**. It saves
   `scrapex-engine.exe` from the newest release on
   [mbiX-hub](https://github.com/muhammadbayoumi/mbiX-hub/releases).
3. Run that file and leave its window open: the window is the engine, and closing it
   stops it. **Check again** on the Engine page finds it.

## Setup for development (Windows)

Python is the version `.python-version` names, and the first line reads it from there:

```powershell
py -$(Get-Content .python-version) -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest
```

The browser tests report *skipped* until Playwright and its Chromium are installed:

```powershell
.venv\Scripts\python -m pip install -e .[dev,browser]
.venv\Scripts\python -m playwright install chromium
```

The two JavaScript suites, which `pytest` does not run, need Node.js. CI runs them under
bash, so run them from Git Bash:

```bash
node --test extension/tests/*.test.mjs
node --test apps_script/tests/*.test.mjs
```

Install the pre-push hook once per clone. It refuses a direct push to `main`, and an
`engine-v*` tag while this machine's warehouse is ahead of the code:

```powershell
git config core.hooksPath .githooks
```

## Where the data lives

The warehouse is one SQLite file, `%USERPROFILE%\.scrapex\engine\scrapex-engine.db`
(`DEFAULT_ENGINE_PATH` in `scrapex/databases/registry.py`). When
`%USERPROFILE%\.scrapex\databases.json` exists, the file it names is the live one. The
engine holds the write lock, so open the file read-only from anything else.

## Read on

- [`CLAUDE.md`](CLAUDE.md) — how this code is changed. Read it before changing anything.
- [`AGENTS.md`](AGENTS.md) — the same rules for other agents, generated from `CLAUDE.md`.
- `gh issue list` for open work, and `gh pr list` for work in flight.
