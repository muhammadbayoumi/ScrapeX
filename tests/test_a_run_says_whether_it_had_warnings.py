"""A run that says "success, 3,149 rows" and nothing else.

SPARK_ESHOP was crawled on 2026-08-03. The run row reported success, 1,789
products, 3,149 rows, and nothing looked wrong. In the same moment 1,789
English product names were filed under the Arabic column, because the shop
serves English at its root and has no /en locale for the connector to ask for.

The explanation was never lost — it is in job_log_entry, verbatim:

    en locale unavailable - names stay single-language this run:
    Client error '404 Not Found' for url
    'https://www.spark-eshop.com/en/products.json?limit=250&page=1'

But the run could not say it HAD one. Finding that sentence needed a reader
who already suspected something, knew the log existed, and knew which job id
to join on. For two days nobody did.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from scrapex import db as dbmod


@pytest.fixture()
def conn():
    path = pathlib.Path(tempfile.mkdtemp()) / "runs.db"
    connection = dbmod.connect(path)
    dbmod.migrate(connection)
    return connection


def test_a_run_can_say_it_had_warnings(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_run)")}

    assert "warning_count" in columns
    assert "first_warning" in columns


def test_a_clean_run_is_visibly_clean_rather_than_merely_quiet(conn):
    """Zero is the default, so a run with nothing to report SAYS zero. A NULL
    would read as "not measured", which is the state this replaces."""
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar,"
                 " source_name, base_url, platform, currency, timezone, authority,"
                 " lifecycle) VALUES (1,'S','S','S','http://s','shopify-json','EGP',"
                 "'UTC','shop','active')")
    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status)"
                 " VALUES (1,1,'2026-08-03T00:00:00Z','success')")

    row = conn.execute("SELECT warning_count, first_warning FROM crawl_run"
                       " WHERE run_id = 1").fetchone()
    assert row[0] == 0
    assert row[1] == ""


def test_the_backfill_reads_the_log_the_warnings_were_always_written_to(conn):
    """A run that already happened can answer for itself. The count and the
    first line come from job_log_entry, which is where append_log has been
    putting connector warnings all along - so this is an index over a record
    that exists, not a second copy of it."""
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar,"
                 " source_name, base_url, platform, currency, timezone, authority,"
                 " lifecycle) VALUES (12,'SPARK','S','S','http://s','shopify-json',"
                 "'EGP','UTC','shop','active')")
    conn.execute("INSERT INTO crawl_job (job_id, job_ref, run_mode, status,"
                 " source_keys, created_at) VALUES (7,'job_x','update',"
                 "'completed','[\"SPARK\"]','2026-08-03T00:00:00Z')")
    conn.execute("INSERT INTO crawl_run (run_id, source_id, job_id, started_at,"
                 " status) VALUES (5,12,7,'2026-08-03T00:00:00Z','success')")
    for message in ("en locale unavailable - names stay single-language this run: 404",
                    "a second warning"):
        conn.execute("INSERT INTO job_log_entry (job_id, logged_at, level,"
                     " source_key, message) VALUES (7,'2026-08-03T00:00:01Z',"
                     "'warning','SPARK',?)", (message,))
    conn.commit()

    # The same two statements 0061 runs.
    conn.execute("""
        UPDATE crawl_run SET warning_count = (
          SELECT COUNT(*) FROM job_log_entry j
           WHERE j.job_id = crawl_run.job_id
             AND j.source_key = (SELECT source_key FROM source_site s
                                  WHERE s.source_id = crawl_run.source_id)
             AND j.level = 'warning') WHERE job_id IS NOT NULL""")
    conn.execute("""
        UPDATE crawl_run SET first_warning = COALESCE((
          SELECT SUBSTR(j.message,1,500) FROM job_log_entry j
           WHERE j.job_id = crawl_run.job_id
             AND j.source_key = (SELECT source_key FROM source_site s
                                  WHERE s.source_id = crawl_run.source_id)
             AND j.level = 'warning'
           ORDER BY j.job_log_id LIMIT 1), '') WHERE warning_count > 0""")

    count, first = conn.execute("SELECT warning_count, first_warning FROM"
                                " crawl_run WHERE run_id = 5").fetchone()
    assert count == 2, "the run still cannot say how many warnings it had"
    assert first.startswith("en locale unavailable"), (
        "the EARLIEST warning is the one worth showing; a later one buries the "
        "sentence that explains the run")


def test_the_worker_records_them_on_the_run_and_not_only_in_the_log():
    """The log keeps everything and this keeps the index. Both, because the log
    alone is what left SPARK_ESHOP looking clean for two days."""
    source = (pathlib.Path(dbmod.__file__).parent / "jobs.py").read_text(encoding="utf-8")

    assert "UPDATE crawl_run SET warning_count" in source, (
        "the worker writes warnings to the log only; a run row is silent again")
    assert "result.ingest.run_id" in source
