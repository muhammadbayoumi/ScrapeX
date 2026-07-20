-- =====================================================================
-- 0018 — TAX EVIDENCE (الإثبات الضريبي)
--
-- Until now a source carried one flag, vat_mode: incl or excl. That flag
-- was stamped onto every observation as vat_included, including all ~169
-- globalpetrolprices countries, from a manifest default nobody had checked.
-- A fabricated tax fact, asserted 169 times.
--
-- The owner's rule is that we must be CERTAIN of what is written, never
-- assume. A live search of globalpetrolprices established that a site can
-- be in exactly one of three states, so that is what this table records:
--
--   'stated'   a clause naming a RATE          -> rate_pct is set
--   'general'  a clause confirming inclusion    -> rate_pct is NULL
--              without naming a rate               (e.g. GPP: "the retail
--                                                   price ... differs due to
--                                                   the various taxes")
--   'unknown'  the source publishes nothing     -> rate_pct is NULL, and the
--                                                  interface must say so
--
-- statement_text and statement_url are what make this evidence rather than
-- an opinion: the owner can open the page and read the sentence.
--
-- Rules are TEMPORAL. A VAT change is a real event, and price_observation is
-- append-only, so a rule may never be edited in place — it is closed with
-- valid_to and a successor opens. Otherwise correcting today's rate would
-- silently restate every price ever recorded.
-- =====================================================================

CREATE TABLE tax_rule (
    tax_rule_id     INTEGER PRIMARY KEY,
    source_key      TEXT NOT NULL,
    -- '*' is the source-wide rule; an ISO country code overrides it. GPP needs
    -- both: one general statement for the site, and per-country rules when the
    -- owner supplies evidence for a country that matters to them.
    region          TEXT NOT NULL DEFAULT '*',
    vat_mode        TEXT NOT NULL CHECK (vat_mode IN ('incl','excl','unknown')),
    rate_pct        REAL CHECK (rate_pct IS NULL OR (rate_pct >= 0 AND rate_pct <= 100)),
    evidence        TEXT NOT NULL CHECK (evidence IN ('stated','general','unknown')),
    statement_text  TEXT,
    statement_url   TEXT,
    statement_lang  TEXT,
    verified_at     TEXT,
    valid_from      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d','now')),
    valid_to        TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    -- A rate without a source is exactly the assertion this table exists to
    -- prevent. 'stated' must carry both the clause and where to read it.
    CHECK (evidence <> 'stated' OR (rate_pct IS NOT NULL AND statement_url IS NOT NULL)),
    -- A general statement still has to be readable somewhere.
    CHECK (evidence <> 'general' OR statement_url IS NOT NULL)
);

-- One CURRENT rule per (source, region); superseded rules stay, closed.
CREATE UNIQUE INDEX ux_tax_rule_current
    ON tax_rule (source_key, region) WHERE valid_to IS NULL;

CREATE INDEX ix_tax_rule_lookup
    ON tax_rule (source_key, region, valid_from DESC);
