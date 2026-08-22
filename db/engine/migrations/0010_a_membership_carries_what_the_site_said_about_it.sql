-- =====================================================================
-- 0010 — A MEMBERSHIP CARRIES WHAT THE SITE SAID ABOUT IT
--
-- `R-45`, his ruling of 2026-08-22, and it arrived as a refusal of the
-- question I asked him. `Q-17` offered two options for the licences' readiness
-- level — a column on the contractors table, or read it and do not store it —
-- and he took neither:
--
--     «لا داعى لوضعها فى عمود خاص فى الجدول ولكن عند الضغط على صف معين وهو
--      يحملها تظهر فى الكارد الخاص بالمقاول · لان المقاولون سيكون هناك عدة
--      مصادر له فى المستقبل»
--
-- A field is not a column. The readiness level is a real fact the site
-- publishes and it is stored; it is simply not a column on the contractors
-- table, because a column is a promise every source in the category must keep
-- and `المقاولون` will have Balady, the UAE registries and the Gulf sources.
--
-- SO IT BELONGS TO THE MEMBERSHIP, NOT TO THE CONTRACTOR, and that is a fact
-- about the data rather than a convenience. `مستوى الجاهزية` is published in
-- the licences table BESIDE each activity — one readiness per activity, not one
-- per company. A contractor with six licences can hold `أساسي | Basic` on one
-- and nothing on the other five, which is exactly what the committed fixture
-- does. On the contractors table that fact has nowhere to live that is not a
-- lie about which activity it describes.
--
-- WHY THREE GENERIC COLUMNS AND NOT ONE CALLED `readiness`. `generic_record_node`
-- is the link table for EVERY site's groups, and a column named for muqawil's
-- vocabulary on a generic table repeats the mistake his ruling was about, one
-- level down: Balady's per-membership attribute would want a fourth column and
-- the UAE's a fifth. So the SITE names the attribute — `attribute_label` holds
-- `مستوى الجاهزية` as published — and `R-45`'s other half is why that is the
-- honest shape: «ما يقوله الموقع هو مصدر الحقيقة الوحيد لا نعدل عليه».
--
-- AND WHY COLUMNS RATHER THAN A CHILD TABLE, which `R-19` would otherwise
-- suggest. `R-19` rules that MULTI-VALUED groups go in child tables; a
-- membership attribute measured over 1,685 real licence rows is
-- SINGLE-valued — one label, one value, on 10 of 1,500 rows, five distinct
-- values (`ذهبي | Gold`, `فضي | Silver`, `ماسي | Dimond` as the site spells
-- it, `أساسي | Basic`). A child table for one nullable value would be the
-- machinery `0009`'s own header warns about: *"Existing machinery that has
-- never carried a row is not an asset."* If a second attribute ever appears,
-- the child table is that migration — and the snapshots make it a re-parse
-- with no network, not a re-crawl.
--
-- NO CHECK CONSTRAINT ON THE VALUE, deliberately. The five levels are a closed
-- set today and a `CHECK` would turn the site adding a sixth into an error we
-- invented. `R-45` again: the site is the record, and this schema does not get
-- a vote on its vocabulary.
--
-- NULLABLE, AND THAT IS THE COMMON CASE. 1,490 of 1,500 measured licence rows
-- publish no readiness at all, and interests publish none by construction —
-- there is no column beside them. An empty attribute is a contractor whose
-- activity the site has not graded, which is a real state and not a gap.
--
-- ADDITIVE ONLY. Three nullable columns on a `WITHOUT ROWID` table: every one
-- of the 15,559 memberships already stored keeps its row untouched and reads
-- NULL, and the next `--approve` over the snapshots on disk fills in the ten
-- per fifteen hundred that have something to say.
-- =====================================================================

-- What the SITE calls this attribute, in the site's own words. `مستوى الجاهزية`
-- for muqawil's licences. NULL where the group publishes no attribute column at
-- all, which is every interest.
ALTER TABLE generic_record_node ADD COLUMN attribute_label TEXT;

-- The value as published, Latin half. `Basic` out of `أساسي | Basic`.
--
-- SPLIT ON THE SITE'S OWN PIPE AND NEVER TRANSLATED. Measured over 1,500 rows,
-- the readiness cell is `<arabic> | <latin>` and nothing else; where the site
-- publishes no Latin half this stays NULL rather than borrowing the Arabic,
-- for the same reason `classification_node.node_name` does — an empty English
-- name is repairable by a later page and a wrong one is not.
ALTER TABLE generic_record_node ADD COLUMN attribute_value TEXT;

-- The value as published, Arabic half. `أساسي`.
ALTER TABLE generic_record_node ADD COLUMN attribute_value_ar TEXT;

-- "Which contractors hold a GRADED licence, and at what level" is the read this
-- exists for — the question the card asks per row and an export asks per table.
-- Partial, because 99.3% of the rows measured have nothing here and an index
-- over 15,559 NULLs would be paid for on every write to buy nothing.
CREATE INDEX IF NOT EXISTS ix_record_node_by_attribute
    ON generic_record_node(group_key, attribute_value_ar)
    WHERE attribute_value_ar IS NOT NULL;
