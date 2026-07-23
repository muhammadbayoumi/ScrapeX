-- =====================================================================
-- 0031 — THE ONE-OPEN-PERIOD BACKSTOP, RESTORED (استعادة صمام الأمان)
--
-- 0030 rebuilt price_period and recreated only one of the two indexes
-- 0016 gave it: ix_price_period_offer came back, ux_price_period_open
-- did not. That partial UNIQUE index IS the invariant "at most one open
-- period per offer — two would mean two current prices": without it a
-- writer bug double-opens silently, _still_the_same_price confirms an
-- arbitrary one of the two, and timeline() reports two concurrent
-- current prices. Found by the adversarial review, reproduced by
-- execution.
--
-- Defensive close first: any database that lived at v30 may already
-- hold duplicate open periods (the window this migration closes). The
-- NEWEST open period per offer keeps its claim to the present; the
-- others are closed at their own last confirmation — the most honest
-- end we can state for them.
-- =====================================================================

UPDATE price_period
SET closed_at = last_confirmed_at
WHERE closed_at IS NULL
  AND price_period_id NOT IN (
      SELECT MAX(price_period_id) FROM price_period
      WHERE closed_at IS NULL GROUP BY offer_id);

CREATE UNIQUE INDEX ux_price_period_open
    ON price_period (offer_id) WHERE closed_at IS NULL;

PRAGMA user_version = 31;
