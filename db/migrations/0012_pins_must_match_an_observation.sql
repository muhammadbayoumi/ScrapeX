-- =====================================================================
-- migration 0012: a pin protects an observation that EXISTS.
--
-- v_retention_protected (0011) selected every retention_pin row straight
-- from the pin table, without checking that any observation carries that
-- (offer, business date, record hash). A pin that matched nothing was
-- therefore "protected" but could never be carried forward, so
-- verify_successor found it missing and refused EVERY compaction and
-- preview from then on — reporting it as "1 protected observation did
-- not survive", which reads like data loss rather than a stale bookmark.
--
-- The pin table is left exactly as it is: a pin is the owner's mark and
-- ScrapeX does not delete their marks. It simply stops claiming that a
-- mark pointing at nothing is an observation to preserve.
-- =====================================================================

DROP VIEW v_retention_protected;

CREATE VIEW v_retention_protected AS
    SELECT po.offer_id, po.business_date, po.record_hash, 'first' AS reason
      FROM price_observation po
      JOIN (SELECT offer_id, MIN(observed_at) AS edge FROM price_observation
             GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.observed_at
UNION
    SELECT po.offer_id, po.business_date, po.record_hash, 'latest'
      FROM price_observation po
      JOIN (SELECT offer_id, MAX(observed_at) AS edge FROM price_observation
             GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.observed_at
UNION
    SELECT po.offer_id, po.business_date, po.record_hash, 'minimum'
      FROM price_observation po
      JOIN (SELECT offer_id, MIN(effective_price) AS edge FROM price_observation
             WHERE effective_price IS NOT NULL GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.effective_price
UNION
    SELECT po.offer_id, po.business_date, po.record_hash, 'maximum'
      FROM price_observation po
      JOIN (SELECT offer_id, MAX(effective_price) AS edge FROM price_observation
             WHERE effective_price IS NOT NULL GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.effective_price
UNION
    -- The join is the fix: a pin protects a row only if that row is there.
    SELECT po.offer_id, po.business_date, po.record_hash, 'pinned'
      FROM retention_pin p
      JOIN price_observation po
        ON po.offer_id = p.offer_id
       AND po.business_date = p.business_date
       AND po.record_hash = p.record_hash;

PRAGMA user_version = 12;
