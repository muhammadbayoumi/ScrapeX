-- =====================================================================
-- 0005 — A SNAPSHOT SAYS HOW IT IS ENCODED
--
-- docs/STORAGE.md, on his instruction — «ليست الفكرة ضغط الملفات بل
-- دراسة نشوف احنا بنسحب اى ولية وبنحتفظ باية ولية وما الفائدة». The study
-- measured what the retention policy costs and what each option spends,
-- and its recommendation needs exactly one thing from the schema: a
-- snapshot has to be able to say how its body is encoded.
--
-- WHY NOT ZLIB, WHICH DEC-9 RECOMMENDED. Because its 15.6× is entirely
-- intra-page. A listing page is 363 KB and its non-card skeleton is
-- 121 KB, near-identical across all 871 pages; zlib's window is 32 KB, so
-- by the time page 2 begins page 1 is out of view. Measured on the 40
-- stored pages: ten skeletons concatenated cost 9.84× one skeleton, and
-- all 40 pages compressed as a single zlib block came to 15.8× — no
-- better than compressing them one at a time. The cross-page redundancy
-- DEC-9 credited for its ratio was never captured at all.
--
-- WHY A DICTIONARY AND NOT A BLOCK. As one zstd block those same 40
-- pages reach 219×, but a block is a CHAIN: row 700 cannot be read
-- without row 699 still existing, which is not a property a database
-- column may have. `zstd` with one real page as a RAW dictionary reaches
-- 187× on listings and 46× on profiles at 3.5 ms a page, and every row
-- stays independently decompressible — verified by round-trip, not
-- assumed. That is why this migration stores dictionaries as rows rather
-- than storing bodies as a stream.
--
-- 618 MB of listings becomes 3.3 MB; 3.95 GB of profiles becomes 87 MB.
--
-- THE CODEC IS THE `zstandard` WHEEL, NOT `compression.zstd`. The first draft
-- of this used the 3.14 standard library module, and requires-python is
-- ">=3.12" with CI on 3.12.14 -- where importing it stopped the package
-- loading at all, not merely the tests. Same libzstd, identical on 3.12 through
-- 3.14, which also means a page compressed on one of the owner's two machines
-- can be read on the other. Re-measured through the wheel on the same 40 stored
-- pages: 254x.
--
-- NOTHING EXISTING IS REWRITTEN, AND THAT IS NOT LAZINESS.
-- `trg_generic_page_snapshot_immutable_update` aborts any UPDATE to this
-- table, and it is right to: a stored page is evidence of what a site
-- published on a date. A backfill would have to drop that trigger, and
-- the trigger is worth more than 600 MB. So `html_codec` defaults to
-- 'plain' and the 1,728 rows already on disk keep working untouched,
-- read by exactly the code path that reads them today. The 3.95 GB this
-- is for has not been fetched yet, which is the whole reason the study
-- gated the crawl.
--
-- WHY THE BODY COLUMN IS NOT CHANGED EITHER. `html_content` is declared
-- TEXT and stays declared TEXT. SQLite column types are affinities, not
-- constraints, and TEXT affinity explicitly does not convert a BLOB — so
-- a compressed body is stored in the column it belongs in, NOT NULL is
-- satisfied honestly, and no table rebuild puts 1,728 rows of evidence
-- and four foreign keys at risk to add two columns.
--
-- `content_hash` KEEPS ITS MEANING: it is the SHA-256 of the DECODED
-- page, so identity remains a fact about content and never about
-- encoding. Two runs that fetch the same page agree on its hash whether
-- one compressed it and the other did not.
-- =====================================================================

-- A dictionary is not derived data. Every body compressed against it is
-- UNREADABLE without it, so it is stored here and guarded below rather
-- than rebuilt on demand from whatever page happens to be handy.
CREATE TABLE IF NOT EXISTS snapshot_dictionary (
    dict_id    INTEGER PRIMARY KEY,
    -- What this dictionary is FOR: host plus page kind, e.g.
    -- `muqawil.org/listing`. Per kind and not per host, because the study
    -- measured 187× on listings and 46× on profiles with a same-kind
    -- dictionary; one dictionary for both would be worse than either.
    label      TEXT NOT NULL UNIQUE,
    -- One real page, exactly as it arrived. A raw dictionary rather than a
    -- trained one: trained dictionaries were measured too and reached
    -- 19.7× against the raw page's 187×.
    body       BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- IMMUTABLE FOR A HARDER REASON THAN THE SNAPSHOTS ARE. A changed
-- snapshot loses one page; a changed dictionary loses every page
-- compressed against it, silently, and the loss only surfaces when
-- someone tries to read one. There is no repair — the plaintext is not
-- stored anywhere else.
CREATE TRIGGER IF NOT EXISTS trg_snapshot_dictionary_immutable_update
BEFORE UPDATE ON snapshot_dictionary
BEGIN
    SELECT RAISE(ABORT, 'a compression dictionary is immutable: every stored page compressed against it would become unreadable');
END;

CREATE TRIGGER IF NOT EXISTS trg_snapshot_dictionary_immutable_delete
BEFORE DELETE ON snapshot_dictionary
BEGIN
    SELECT RAISE(ABORT, 'a compression dictionary cannot be deleted: every stored page compressed against it would become unreadable');
END;

-- 'plain' means html_content is the page. Anything else names a codec the
-- reader must apply. DEFAULT rather than nullable, so a row can never be
-- ambiguous about how to read it -- including every row already on disk.
ALTER TABLE generic_page_snapshot
    ADD COLUMN html_codec TEXT NOT NULL DEFAULT 'plain';

-- Which dictionary decodes this body. NULL for 'plain', and NULL for any
-- future codec that needs none.
ALTER TABLE generic_page_snapshot
    ADD COLUMN html_dict_id INTEGER REFERENCES snapshot_dictionary(dict_id);

PRAGMA user_version = 5;
