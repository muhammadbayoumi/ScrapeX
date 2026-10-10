-- Tenders, kept as OCDS releases, with the responses they came from.
--
-- HIS RULINGS, 2026-10-10, on #1616 and #1647: the shape is OCDS's own (ES-3). Every
-- release read is kept whole and never changed: the history. The current state is
-- compiled from the releases into typed tables, which can be rebuilt from them at any
-- time. New tables follow Supabase's style (ES-4): plural names, an `id` key, a foreign
-- key named after the singular of the table it references, an index on every foreign
-- key, `STRICT`, and a comment on every definition. The old tables keep their style.
--
-- THE FIRST SOURCE IS THE WORLD BANK (#1647), and every column below is one it fills.
-- #1616 drew columns no studied source fills yet (a tender's start, its lots, its
-- documents, a party's Arabic name); they wait for the source that fills them, because
-- an empty column is a promise, not a fact.
--
-- WHAT IS DEFERRED TO THE NEXT MIGRATION, AND WHY. Awards, their suppliers, contracts
-- and bids (#1616 D3, D4, D5, D6, D7) arrive with their writer, the award-text parser and
-- `contractdata`, in part 4 of milestone 51. #1616 §5 is the rule: a table ships with its
-- first writer. Until then an award notice is kept here as a release like any other, so
-- part 4 compiles awards from what is already stored and fetches nothing twice.
--
-- PERSONS ARE NOT IN THE HISTORY. His ruling on #1647: every person is kept (contact
-- persons), in a table of its own and outside `tender_releases`, which is append-only.
-- So a person can be removed later, if the Bank's reply or a person's request requires
-- it, without breaking the history's promise. `fetched_responses` still holds the raw
-- response they arrived in; removing a person from evidence is an archive, not an edit.
--
-- `fetched_responses` IS THE EVIDENCE OF ANY MEDIA TYPE that `generic_page_snapshot`
-- cannot hold (`content_type = 'text/html'` only, `db/engine/schema.sql:194-195`). Its
-- columns are WARC's record fields (#1614 §3.6): the target URI, the date, the status,
-- the content type, the headers and the payload's digest. It belongs to no category.
--
-- `tender_classifications` DEPARTS FROM #1616, which drew it as a link to
-- `classification_node`. That table keys a node on its ARABIC name
-- (`node_name_ar TEXT NOT NULL`, `db/engine/schema.sql:83`; `taxonomy.ensure_path`
-- matches on it), and the Bank publishes its sectors in English only. An English label
-- stored as the Arabic name would be a false fact. So the source's own code and label
-- are stored here, and mapping them to a hub stays the later choice #1614 §5 names.
--
-- `tender_locations` keeps the source's country code beside the ISO one. The Bank
-- writes regions (`3W`, Western and Central Africa) and codes ISO 3166-1 does not
-- assign (`XK`); for those `country_code` is NULL and the Bank's code is what remains.
--
-- CREATE TABLE ONLY: nothing that exists changes, so no existing row can fail this.

PRAGMA user_version = 24;

-- One response as fetched, whatever its media type. Immutable.
CREATE TABLE fetched_responses (
    id           INTEGER PRIMARY KEY,
    -- The URL asked for, exactly as sent (WARC-Target-URI).
    target_uri   TEXT NOT NULL,
    -- When it arrived, RFC 3339 UTC (WARC-Date).
    fetched_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    status_code  INTEGER NOT NULL CHECK (status_code BETWEEN 100 AND 599),
    -- The Content-Type header as the server sent it.
    content_type TEXT NOT NULL,
    -- Every response header, as a JSON object.
    headers      TEXT NOT NULL CHECK (json_valid(headers) AND json_type(headers) = 'object'),
    -- The body, compressed by `body_codec`. A new codec is a new value here, never a guess.
    body         BLOB NOT NULL,
    body_codec   TEXT NOT NULL CHECK (body_codec IN ('zstd')),
    -- sha256 of the body as it arrived, before compression (WARC-Payload-Digest), hex.
    body_sha256  TEXT NOT NULL CHECK (length(body_sha256) = 64),
    -- The job that fetched it, when a job did.
    crawl_job_id INTEGER REFERENCES crawl_job(job_id)
) STRICT;

CREATE INDEX fetched_responses_crawl_job_id_idx ON fetched_responses (crawl_job_id);

CREATE TRIGGER fetched_responses_immutable_update
BEFORE UPDATE ON fetched_responses
BEGIN
    SELECT RAISE(ABORT, 'a fetched response is evidence and never changes');
END;

CREATE TRIGGER fetched_responses_immutable_delete
BEFORE DELETE ON fetched_responses
BEGIN
    SELECT RAISE(ABORT, 'a fetched response is evidence and never changes');
END;

-- One contracting process (OCDS `ocid`).
CREATE TABLE tender_processes (
    id               INTEGER PRIMARY KEY,
    -- OCDS ocid. Minted here, because the source publishes no OCDS; never published as one.
    ocid             TEXT NOT NULL UNIQUE,
    source_site_id   INTEGER NOT NULL REFERENCES source_site(source_id),
    -- The process's key at its source. The World Bank: project id and the borrower's
    -- reference (#1647 Q3), or the notice id when the notice states no reference.
    source_record_id TEXT NOT NULL,
    -- The source's project id (#1616 D1).
    project_ref      TEXT,
    first_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (source_site_id, source_record_id)
) STRICT;

CREATE INDEX tender_processes_source_site_id_idx ON tender_processes (source_site_id);

-- One release as read: the history. Append-only.
CREATE TABLE tender_releases (
    id                  INTEGER PRIMARY KEY,
    tender_process_id   INTEGER NOT NULL REFERENCES tender_processes(id),
    -- OCDS release id: the source's own notice id.
    release_ref         TEXT NOT NULL,
    -- OCDS date: when the source published it (valid time).
    released_at         TEXT NOT NULL,
    -- The source's own change stamp, when it gives one (#1616 D10).
    source_modified_at  TEXT,
    -- OCDS tag: a JSON array of releaseTag codes.
    tags                TEXT NOT NULL CHECK (json_valid(tags) AND json_type(tags) = 'array'),
    -- The language the source states for it, as a BCP 47 tag (#1616 D10).
    language            TEXT,
    -- The release as OCDS JSON, without persons.
    payload             TEXT NOT NULL CHECK (json_valid(payload) AND json_type(payload) = 'object'),
    -- sha256 of `payload`, hex: the same release read twice is stored once.
    payload_sha256      TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    -- The response it was read from.
    fetched_response_id INTEGER REFERENCES fetched_responses(id),
    -- When it was stored here (system time).
    recorded_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (tender_process_id, release_ref, payload_sha256)
) STRICT;

CREATE INDEX tender_releases_tender_process_id_idx ON tender_releases (tender_process_id);
CREATE INDEX tender_releases_fetched_response_id_idx ON tender_releases (fetched_response_id);

CREATE TRIGGER tender_releases_append_only_update
BEFORE UPDATE ON tender_releases
BEGIN
    SELECT RAISE(ABORT, 'tender releases are append-only');
END;

CREATE TRIGGER tender_releases_append_only_delete
BEFORE DELETE ON tender_releases
BEGIN
    SELECT RAISE(ABORT, 'tender releases are append-only');
END;

-- The tender as compiled from its process's releases (OCDS `tender`), one per process.
CREATE TABLE tenders (
    id                           INTEGER PRIMARY KEY,
    tender_process_id            INTEGER NOT NULL UNIQUE REFERENCES tender_processes(id),
    -- OCDS tender.id: the borrower's own reference (#1616 D2).
    tender_ref                   TEXT,
    title                        TEXT,
    -- OCDS tenderStatus code; `status_details` keeps the source's own word.
    status                       TEXT CHECK (status IN ('planning', 'planned', 'active',
                                     'cancelled', 'unsuccessful', 'complete', 'withdrawn')),
    status_details               TEXT,
    -- OCDS method code; the source's method name stays in the release.
    procurement_method           TEXT CHECK (procurement_method IN ('open', 'selective',
                                     'limited', 'direct')),
    main_procurement_category    TEXT CHECK (main_procurement_category IN ('goods', 'works',
                                     'services')),
    -- The estimate, in `value_currency` (ISO 4217).
    value_amount                 REAL,
    value_currency               TEXT CHECK (value_currency IS NULL OR (
                                     length(value_currency) = 3
                                     AND value_currency = upper(value_currency))),
    -- The deadline's date (OCDS tenderPeriod.endDate) ...
    tender_period_end            TEXT,
    -- ... its local time of day, HH:MM, as the source writes it (#1616 D8) ...
    tender_period_end_local_time TEXT CHECK (tender_period_end_local_time IS NULL
                                     OR tender_period_end_local_time GLOB '[0-2][0-9]:[0-5][0-9]'),
    -- ... and its IANA zone, NULL while the source states none (#1647 Q6).
    tender_period_end_zone       TEXT,
    published_at                 TEXT,
    -- The newest release the compiled fields were merged from. A second key to
    -- `tender_releases` beside none other, so its role leads the name (ES-4).
    compiled_from_tender_release_id INTEGER NOT NULL REFERENCES tender_releases(id)
) STRICT;

CREATE INDEX tenders_compiled_from_tender_release_id_idx
    ON tenders (compiled_from_tender_release_id);

-- A party in a process (OCDS `parties`), compiled.
CREATE TABLE tender_parties (
    id                INTEGER PRIMARY KEY,
    tender_process_id INTEGER NOT NULL REFERENCES tender_processes(id),
    -- OCDS party id, unique within the process.
    party_ref         TEXT NOT NULL,
    name              TEXT NOT NULL,
    -- An org-id.guide list code and the id within it, when the source states one.
    identifier_scheme TEXT,
    identifier_id     TEXT,
    -- ISO 3166-1 alpha-2, when the source's country maps to one.
    country_code      TEXT CHECK (country_code IS NULL OR (
                          length(country_code) = 2 AND country_code = upper(country_code))),
    UNIQUE (tender_process_id, party_ref)
) STRICT;

CREATE INDEX tender_parties_tender_process_id_idx ON tender_parties (tender_process_id);

-- A party's role in its process (OCDS partyRole codelist), compiled.
CREATE TABLE tender_party_roles (
    id              INTEGER PRIMARY KEY,
    tender_party_id INTEGER NOT NULL REFERENCES tender_parties(id),
    role            TEXT NOT NULL CHECK (role IN ('buyer', 'procuringEntity', 'supplier',
                        'tenderer', 'funder', 'enquirer', 'payer', 'payee', 'reviewBody',
                        'interestedParty')),
    UNIQUE (tender_party_id, role)
) STRICT;

CREATE INDEX tender_party_roles_tender_party_id_idx ON tender_party_roles (tender_party_id);

-- A party's contact point as one release states it: a PERSON's details. Outside the
-- append-only history on his ruling (#1647), so it can be removed.
CREATE TABLE tender_contact_points (
    id                INTEGER PRIMARY KEY,
    tender_release_id INTEGER NOT NULL REFERENCES tender_releases(id),
    -- The party it is the contact of, by its OCDS party id within the process.
    party_ref         TEXT NOT NULL,
    name              TEXT,
    -- Not in OCDS's contactPoint; the World Bank states it.
    job_title         TEXT,
    email             TEXT,
    telephone         TEXT,
    fax_number        TEXT,
    url               TEXT,
    UNIQUE (tender_release_id, party_ref)
) STRICT;

CREATE INDEX tender_contact_points_tender_release_id_idx
    ON tender_contact_points (tender_release_id);

-- An item the tender buys, by its classification (OCDS `tender.items`), compiled.
CREATE TABLE tender_items (
    id                    INTEGER PRIMARY KEY,
    tender_process_id     INTEGER NOT NULL REFERENCES tender_processes(id),
    -- OCDS item id, unique within the process.
    item_ref              TEXT NOT NULL,
    description           TEXT,
    -- The scheme and the code in it: 'UNSPSC' for the World Bank.
    classification_scheme TEXT NOT NULL,
    classification_code   TEXT NOT NULL,
    UNIQUE (tender_process_id, item_ref)
) STRICT;

CREATE INDEX tender_items_tender_process_id_idx ON tender_items (tender_process_id);

-- A process's sector in its source's own vocabulary, compiled (a departure: see above).
CREATE TABLE tender_classifications (
    id                INTEGER PRIMARY KEY,
    tender_process_id INTEGER NOT NULL REFERENCES tender_processes(id),
    -- The vocabulary, named by this warehouse: 'worldbank-sector'.
    scheme            TEXT NOT NULL,
    code              TEXT NOT NULL,
    description       TEXT,
    UNIQUE (tender_process_id, scheme, code)
) STRICT;

CREATE INDEX tender_classifications_tender_process_id_idx
    ON tender_classifications (tender_process_id);

-- A country the process is carried out in, compiled (a departure: see above).
CREATE TABLE tender_locations (
    id                  INTEGER PRIMARY KEY,
    tender_process_id   INTEGER NOT NULL REFERENCES tender_processes(id),
    -- ISO 3166-1 alpha-2; NULL when the source's code names a region or no ISO country.
    country_code        TEXT CHECK (country_code IS NULL OR (
                            length(country_code) = 2 AND country_code = upper(country_code))),
    -- The source's own code and name, as written.
    source_country_code TEXT NOT NULL,
    source_country_name TEXT,
    UNIQUE (tender_process_id, source_country_code)
) STRICT;

CREATE INDEX tender_locations_tender_process_id_idx ON tender_locations (tender_process_id);
