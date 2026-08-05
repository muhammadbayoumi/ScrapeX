# Spike 2 — wa-sqlite + OPFS inside an MV3 extension

**Status: experiment. Nothing here ships, and nothing here is imported by
`scrapex/`, `extension/`, `db/` or `sources.yaml`.**

`docs/MASTER-PLAN.md:25-27` names this spike as the one thing left before
Topology A is "fully de-risked", and `docs/BACKLOG.md` DEC-1 records that it was
never attempted. This directory is the attempt. The answer is in
[FINDINGS.md](FINDINGS.md); this file is how to re-run it.

## Run it

```bash
cd spikes/opfs-sqlite
python prepare.py            # read-only snapshot of the live warehouse -> .work/
python baseline.py           # Python/SQLite reference numbers + the SQL trace
npm install && npm run vendor
python run.py                # launches Chromium with extension/ and measures
```

The runs FINDINGS.md quotes, reproduced exactly:

```bash
python run.py --phases env,import,describe,contend,journal,quota,restart --out main.json
```

```bash
python run.py --phases env,import,describe,migrate --out migrate.json
```

```bash
python run.py --phases queries,ingest --keep-profile --repeats 7 --engines sahpool,wa-sqlite-ahp --out speed-fast.json
```

```bash
python run.py --phases import,sw --heartbeat-seconds 420 --out sw.json
```

`--keep-profile` matters: phases share OPFS state, so a phase that reads the
warehouse needs the profile the `import` phase left behind. Without it every run
starts from an empty origin — which is exactly what the `restart` phase needs,
and exactly what breaks a lone `--phases queries`.

`python collect_evidence.py` then copies those results into `evidence/`, which
is committed; `results/` and `.work/` are scratch and are overwritten by the
next run.

`prepare.py` opens `~/.scrapex/marketlens/marketlens.db` with `?mode=ro` and
copies it with SQLite's backup API; it never writes to the live file, and the
rest of the spike only ever sees the copy under `.work/`.

## Why it is not in CI

`run.py` needs a real Chromium with an unpacked MV3 extension, a local HTTP
server, and a ~75 MB database that only exists on the owner's machine. CI's
`pytest` collects `tests/` only (`pyproject.toml:60`) and its Node job runs
`contract/parity` and `extension/tests` only (`.github/workflows/ci.yml`), so
nothing here is picked up by either. That is deliberate: a green suite must not
depend on a browser, and this spike's whole output is a document.

## What is in here

| File | What it is |
|---|---|
| `prepare.py` | Read-only snapshot of the live warehouse, plus a WAL-off copy (see FINDINGS §1) |
| `baseline.py` | Times the real Data-page query and a real crawl's ingest on Python/SQLite, and **records the statements** so the browser replays the same strings |
| `run.py` | Playwright driver: stages the extension, serves `.work/`, runs the phases, writes `results/` |
| `extension/` | A real MV3 extension — service worker, harness page, dedicated worker |
| `extension/engine.mjs` | Three OPFS VFSes behind one interface, plus the OPFS primitives |
| `collect_evidence.py` | Copies the quoted run into `evidence/` so the numbers outlive `results/` |
| `evidence/` | The committed run FINDINGS.md quotes |
| `FINDINGS.md` | The numbers and the verdict |

`extension/vendor/`, `.work/`, `results/` and `node_modules/` are generated and
git-ignored; `npm run vendor` and the two Python scripts refill them.
