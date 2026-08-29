# A generic crawl is a run — `R-52` / `OP-68`

**Ruled 2026-08-24 («نفذ ب»).** Three of the eight row states rest on `newest`, the maximum
of `generic_record.last_seen_at`. A crawl writes its rows over half an hour and `newest` is
a timestamp to the second, so only the final second's rows compare equal to it.

**Measured, live:** **17,256 of 17,304** contractors read `absent` after a crawl that read
every one of them; **1** profile read `new` where **121** arrived that day. And it is not a
screen bug — `publish.py`'s `dataset_workbook_tables` turns every payload column into a
workbook column, so *"The most recent crawl did not show this row"* reaches the Google
Sheet the mbiX add-in reads.

---

## Two changes, and the first does not wait for the second

### Step 1 — `absent` comes off the ledger (no schema, no ruling needed)

`scrapex/sightings.py:398`:

```python
if last_seen_at is None or last_seen_at < newest:      # <- the defect
    return STATE_ABSENT
```

`mark_unavailable` exists to write a *proved* absence into `dataset_sighting.last_absent_at`,
and step 5 of the same ladder already reads it for `returned`. Step 3 ignores it. Measured:

```
dataset_sighting for 'contractors':  17,417 rows
   ever marked absent          0
   absent NOW                  0        <- the ledger's answer, and it is right
   the timestamp says absent  17,256    <- what the screen and the sheet publish
```

So step 3 becomes: absent when the ledger proved an absence more recent than the sighting.
`newest` stops being consulted for this state at all.

**This lands first and alone**, because it is the half that reaches the sheet and it is a
defect with a right answer rather than a decision.

### Step 2 — `dataset_crawl`, the run table (`0011`)

**One row per crawl.** `0006` already weighed a `(dataset_key, external_id, run_ref)`
attendance register and refused it at **17,403 rows per crawl**; this is three orders of
magnitude cheaper and answers a different question. That refusal stands.

| column | why it is load-bearing |
|---|---|
| `dataset_key` | which dataset this run crawled |
| `run_ref` | the ref the operator typed. **A partitioned crawl is 93 refs sharing a prefix**, so this is the BASE ref and the cells are its attempts |
| `started_at` | what `absent` compares against: a row not seen since before the last run began was not seen by it |
| `finished_at` | what makes the answer honest. **A run still in flight has not failed to see anybody**, and a crawl that never finished must not declare 17,000 departures |
| `status` | `running` / `success` / `failed`, so an interrupted run is distinguishable from a completed one |
| `pages_expected` | the denominator `declare_frontier` has never had. `STATE.md` records the complaint; the table that knows when a run began can say what it expected |
| `pages_stored` | what it actually got, so `expected` is checkable rather than decorative |

**Only a `success` run may define "the last crawl".** That is the whole reason
`finished_at` and `status` are here rather than just `started_at`.

---

## The seams to wire, and the trap at each

1. **`scrapex/contractors.py`** — `crawl` and `details` both take `--run-ref`. Open a
   `dataset_crawl` row at the start, close it at the end, and close it as `failed` on the
   way out of an exception. **The trap:** `--details` resumes, so a reused ref must not
   open a second run row for the same ref — or it must, and then "the last crawl" is the
   newest one. Decide it in the code with a comment, and test the resume.
2. **`scrapex/partitioncrawl.py`** — the 93 cells. They must all belong to ONE run row,
   keyed on the base ref, not 93 rows.
3. **`scrapex/extract/service.py:996`** — `newest` is computed here and handed to
   `derive_state`. It becomes "the newest `success` run's `started_at` for this dataset",
   read from `dataset_crawl`, and `None` when there is none — which the ladder already
   handles honestly (`STATE_CONFIRMED`).
4. **`scrapex/sightings.py`** — steps 4 and 6 (`new`, `updated`) then compare against a run
   boundary instead of a row maximum. **The trap:** `first_seen_at` is an APPROVAL time and
   `captured_at` is a FETCH time; the `R-51` recovery approved pages fetched two days
   earlier. A run's window must be the window of the phase that wrote the rows, or `new`
   will be wrong in the other direction.

---

## Verification

1. **A test that fails on the current code**, first: build a warehouse whose rows span
   two minutes, assert that none reads `absent`. Today all but the last second do.
2. **Mutation-test each new branch** — house standard. Specifically: `>=` for `>` on the
   run boundary; using `finished_at` where `started_at` is meant; letting a `running` or
   `failed` run define the last crawl.
3. **The published workbook.** Assert `observed_state` is not `absent` for a row the ledger
   never marked. This is the one that would have caught the shipped defect, and no test
   asserts on that column's VALUE today.
4. **`SCRAPEX_FULL_MIGRATIONS=1`** and the schema-template count, since `0011` changes
   `latest_schema_version()`.
5. **The live warehouse, read-only, before and after**: 17,256 → 0 `absent` for
   `contractors`, and 121 `new` for `contractor_profiles` rather than 1.

## Open, and not to be absorbed by a default

- **Does `contractor_profiles` get a sighting ledger at all?** It has **zero**
  `dataset_sighting` rows, which is why its absence bug is masked as `unsighted` for all
  17,371. Step 1 does not fix that — it makes it visible. Whether a profile crawl should
  write sightings is a question about what a profile crawl proves, and `OP-66`'s 8 refusals
  and `OP-64`'s 59 dead ids are the population it would be proving things about.
