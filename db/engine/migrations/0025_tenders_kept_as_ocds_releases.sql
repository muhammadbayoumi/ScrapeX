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
-- THE AWARD TABLES ARE CREATED HERE AND STAY EMPTY UNTIL PART 4. His ruling on #1658,
-- 2026-10-17: awards, their suppliers, contracts, bids and beneficial owners (#1616 D3
-- to D7) go in this migration, where his rulings on #1647 placed them, and wait for their
-- writer, the award-text parser and `contractdata`, in part 4 of milestone 51. Until then
-- an award notice is kept as a release like any other, its structured award fields
-- inside the payload, so part 4 compiles awards from what is already stored.
--
-- PERSONS ARE NOT IN THE HISTORY. His ruling on #1647: every person is kept (contact
-- persons and beneficial owners), each in a table of its own and outside
-- `tender_releases`, which is append-only. So a person can be removed later, if the
-- Bank's reply or a person's request requires it, without breaking the history's
-- promise. `fetched_responses` still holds the raw response they arrived in; removing a
-- person from evidence is an archive, not an edit.
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

PRAGMA user_version = 25;

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

-- ---- Awards, contracts and bids: created here, empty until part 4 brings their writer ----
-- Each holds what #1647 §5.2 and §5.3 found the Bank publishing, under OCDS's name for
-- it. Where the Bank publishes more than OCDS has a field for, the column says so.

-- An award in a process (OCDS `awards`), compiled.
CREATE TABLE tender_awards (
    id                       INTEGER PRIMARY KEY,
    tender_process_id        INTEGER NOT NULL REFERENCES tender_processes(id),
    -- OCDS award id, unique within the process: the Bank's contract number (#1616 D3).
    award_ref                TEXT NOT NULL,
    -- OCDS award title: the Bank's "Scope of Contract" (#1616 D3).
    title                    TEXT,
    -- OCDS awardStatus code.
    status                   TEXT CHECK (status IN ('pending', 'active', 'cancelled',
                                 'unsuccessful')),
    -- OCDS award date, a date: when the award was notified.
    awarded_at               TEXT,
    -- The signed price in its own currency (ISO 4217): the award text's "Signed
    -- Contract price" (#1647 §5.2). Its one home; `tender_contracts` does not repeat it.
    value_amount             REAL,
    value_currency           TEXT CHECK (value_currency IS NULL OR (
                                 length(value_currency) = 3
                                 AND value_currency = upper(value_currency))),
    -- The Bank's own conversion to US dollars, beside the signed price and never in its
    -- place (#1616 D7). Departs from OCDS, whose value is one amount in one currency.
    value_amount_usd         REAL,
    -- How long the contract runs, as an ISO 8601 duration (`P30M`), because the Bank
    -- states months (#1616 D3). Departs from OCDS's contractPeriod.durationInDays: a
    -- month is not a fixed number of days.
    contract_period_duration TEXT CHECK (contract_period_duration IS NULL
                                 OR contract_period_duration GLOB 'P[0-9]*[DWMY]'),
    CHECK ((value_amount IS NULL) = (value_currency IS NULL)),
    UNIQUE (tender_process_id, award_ref)
) STRICT;

CREATE INDEX tender_awards_tender_process_id_idx ON tender_awards (tender_process_id);

-- A supplier an award is made to (OCDS `awards[].suppliers`), compiled.
CREATE TABLE tender_award_suppliers (
    id               INTEGER PRIMARY KEY,
    tender_award_id  INTEGER NOT NULL REFERENCES tender_awards(id),
    tender_party_id  INTEGER NOT NULL REFERENCES tender_parties(id),
    -- This member's share of the award in US dollars, as the Bank states it (#1616 D4).
    -- It is the Bank's figure, so it is named as `tender_awards.value_amount_usd` is.
    value_amount_usd REAL,
    -- 1 when that share is the Bank's equal division of the total among a joint
    -- venture's members, not a share the members stated (#1647 §6.2 C2).
    value_is_split   INTEGER NOT NULL DEFAULT 0 CHECK (value_is_split IN (0, 1)),
    CHECK (value_is_split = 0 OR value_amount_usd IS NOT NULL),
    UNIQUE (tender_award_id, tender_party_id)
) STRICT;

CREATE INDEX tender_award_suppliers_tender_award_id_idx
    ON tender_award_suppliers (tender_award_id);
CREATE INDEX tender_award_suppliers_tender_party_id_idx
    ON tender_award_suppliers (tender_party_id);

-- A contract signed for an award (OCDS `contracts`), compiled (#1616 D5).
CREATE TABLE tender_contracts (
    id              INTEGER PRIMARY KEY,
    -- OCDS awardID.
    tender_award_id INTEGER NOT NULL REFERENCES tender_awards(id),
    -- OCDS contract id, unique within its award.
    contract_ref    TEXT NOT NULL,
    -- OCDS dateSigned, a date: the Bank states no time.
    signed_at       TEXT,
    -- When the Bank gave its no-objection, a date (`contr_no_obj_dat`). Not in OCDS
    -- core: it is the funder's approval.
    no_objection_at TEXT,
    UNIQUE (tender_award_id, contract_ref)
) STRICT;

CREATE INDEX tender_contracts_tender_award_id_idx ON tender_contracts (tender_award_id);

-- A bid in a process (OCDS bids extension, `bids.details`), compiled (#1616 D6).
CREATE TABLE tender_bids (
    id                              INTEGER PRIMARY KEY,
    tender_process_id               INTEGER NOT NULL REFERENCES tender_processes(id),
    -- OCDS bid id, unique within the process.
    bid_ref                         TEXT NOT NULL,
    -- The bidder. OCDS lists a bid's tenderers; the Bank names each bidder as one
    -- party, a joint venture included.
    tender_party_id                 INTEGER NOT NULL REFERENCES tender_parties(id),
    -- OCDS bidStatus code: `valid` for an evaluated bid, `disqualified` for a rejected one.
    status                          TEXT CHECK (status IN ('invited', 'pending', 'valid',
                                        'disqualified', 'withdrawn')),
    -- The Bank's "Reason for Rejection", as written. Not in OCDS.
    rejection_reason                TEXT,
    -- "Bid Price at Opening", in its own currency: OCDS's one bid value.
    value_amount                    REAL,
    value_currency                  TEXT CHECK (value_currency IS NULL OR (
                                        length(value_currency) = 3
                                        AND value_currency = upper(value_currency))),
    -- "Evaluated Bid Price" and "Final Evaluation Price", each in its own currency and
    -- each under its own label, because #1647 §5.2 counted the two together and did
    -- not show they are one figure. Not in OCDS, whose bid has one value.
    evaluated_value_amount          REAL,
    evaluated_value_currency        TEXT CHECK (evaluated_value_currency IS NULL OR (
                                        length(evaluated_value_currency) = 3
                                        AND evaluated_value_currency
                                            = upper(evaluated_value_currency))),
    final_evaluation_value_amount   REAL,
    final_evaluation_value_currency TEXT CHECK (final_evaluation_value_currency IS NULL OR (
                                        length(final_evaluation_value_currency) = 3
                                        AND final_evaluation_value_currency
                                            = upper(final_evaluation_value_currency))),
    -- A quality-based selection's scores, as the Bank publishes them. Not in OCDS.
    technical_score                 REAL,
    financial_score                 REAL,
    combined_score                  REAL,
    -- OCDS bid rank: 1 is first.
    rank                            INTEGER CHECK (rank IS NULL OR rank >= 1),
    CHECK ((value_amount IS NULL) = (value_currency IS NULL)),
    CHECK ((evaluated_value_amount IS NULL) = (evaluated_value_currency IS NULL)),
    CHECK ((final_evaluation_value_amount IS NULL)
           = (final_evaluation_value_currency IS NULL)),
    UNIQUE (tender_process_id, bid_ref)
) STRICT;

CREATE INDEX tender_bids_tender_process_id_idx ON tender_bids (tender_process_id);
CREATE INDEX tender_bids_tender_party_id_idx ON tender_bids (tender_party_id);

-- A beneficial owner of a party, as one release states it: a PERSON (OCDS beneficial
-- owners extension, `parties[].beneficialOwners`). Outside the append-only history on
-- his ruling (#1647), so it can be removed.
CREATE TABLE tender_beneficial_owners (
    id                INTEGER PRIMARY KEY,
    tender_release_id INTEGER NOT NULL REFERENCES tender_releases(id),
    -- The party it owns, by its OCDS party id within the process.
    party_ref         TEXT NOT NULL,
    -- OCDS person id, unique within the party in this release.
    owner_ref         TEXT NOT NULL,
    name              TEXT NOT NULL,
    -- Nationality and country of residence, as the award text writes them. OCDS keeps
    -- nationalities as ISO 3166-1 codes; the Bank writes names.
    nationality       TEXT,
    residence         TEXT,
    -- The control the person holds, as the award text states it. Not in OCDS, which
    -- leaves the nature of control to the Beneficial Ownership Data Standard.
    control           TEXT,
    UNIQUE (tender_release_id, party_ref, owner_ref)
) STRICT;

CREATE INDEX tender_beneficial_owners_tender_release_id_idx
    ON tender_beneficial_owners (tender_release_id);
