-- =====================================================================
-- 0046 — SEVEN GROUPS, AND EVERY FACT FILED BY WHAT IT IS
--
-- Owner rulings, 2026-07-26 and 2026-07-28. 0043 closed the vocabulary at
-- five; reading the warehouse afterwards showed the five were not enough
-- and that the boundary between two of them had never been stated.
--
-- TWO NEW GROUPS:
--   STORE          this store's handling of the product, not the product:
--                  shipping method (madar's «طريقة الشحن», which 0043 had
--                  wrongly filed under Specifications), stock counts, the
--                  store's own sku, and the warranty — a commitment made
--                  WITH the sale, since two shops selling one item can
--                  warrant it differently (owner's ruling on «الضمان»).
--   SITE METADATA  facts about the PAGE. madar publishes no_index /
--                  no_follow / no_archive on every product: robots
--                  directives for its own site, which reached the warehouse
--                  only because the connector takes every visible
--                  attribute. Kept rather than dropped, so nothing the site
--                  states is silently discarded — but filed where they
--                  cannot crowd out a product fact. sika's search keywords
--                  join them.
--
-- THE BOUNDARY, now stated: a property OF the product files under
-- SPECIFICATIONS; information ABOUT it files under MORE_INFORMATION. Under
-- that rule 41 facts move out of the catch-all they had been sitting in —
-- amperage, density, cement_type, moisture_content, poles, «المقاس»,
-- «نوع الكابل» — while manufacturer, origin and country_of_manufacture
-- stay exactly where they were.
--
-- GENERATED FROM vocab._DETAIL_GROUP_BY_CODE, deliberately: the code and
-- the stored rows now answer from one source. A hand-written list here
-- would be a second copy to keep in step, which is the defect this
-- codebase names in Q1 and the reason 0043 had to be written at all.
-- =====================================================================

-- Store --
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('am_shipping_type', 'am_shipping_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('availability', 'availability_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('max_stock_level', 'max_stock_level_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('min_stock_level', 'min_stock_level_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('pa_الضمان', 'pa_الضمان_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('sku', 'sku_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('stock_quantity', 'stock_quantity_ar');
UPDATE source_product_attribute SET attribute_group = 'Store'
 WHERE attribute_code IN ('trade_tier_price', 'trade_tier_price_ar');
-- Site metadata --
UPDATE source_product_attribute SET attribute_group = 'Site metadata'
 WHERE attribute_code IN ('keywords', 'keywords_ar');
UPDATE source_product_attribute SET attribute_group = 'Site metadata'
 WHERE attribute_code IN ('no_archive', 'no_archive_ar');
UPDATE source_product_attribute SET attribute_group = 'Site metadata'
 WHERE attribute_code IN ('no_follow', 'no_follow_ar');
UPDATE source_product_attribute SET attribute_group = 'Site metadata'
 WHERE attribute_code IN ('no_index', 'no_index_ar');
-- Specifications --
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('amperage', 'amperage_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('base_type', 'base_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('battery_capacity', 'battery_capacity_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('battery_type', 'battery_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('blade_size', 'blade_size_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('breaking_capacity_ka', 'breaking_capacity_ka_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('cct', 'cct_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('cement_type', 'cement_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('chuck_size', 'chuck_size_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('coating', 'coating_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('color', 'color_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('conduit_type', 'conduit_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('cylinder_size', 'cylinder_size_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('density', 'density_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('density_kgm3', 'density_kgm3_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('drill_bit_type', 'drill_bit_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('drying_method', 'drying_method_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('feature', 'feature_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('ff_type', 'ff_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('gangs', 'gangs_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('glue_type', 'glue_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('grade', 'grade_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('horse_power', 'horse_power_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('lock_body_size', 'lock_body_size_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('material_grade', 'material_grade_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('material_type', 'material_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('max_disc_diameter', 'max_disc_diameter_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('mesh_size', 'mesh_size_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('module_capacity', 'module_capacity_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('moisture_content', 'moisture_content_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('mounting_type', 'mounting_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('no_load_speed', 'no_load_speed_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('number_of_ways', 'number_of_ways_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('pa_color', 'pa_color_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('pa_التطبيق', 'pa_التطبيق_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('pa_المقاس', 'pa_المقاس_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('pa_توع-الفولت', 'pa_توع-الفولت_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('pa_نوع-الكابل', 'pa_نوع-الكابل_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('poles', 'poles_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('port_type', 'port_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('power_input', 'power_input_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('power_source', 'power_source_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('rated_current_a', 'rated_current_a_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('reinforcement_type', 'reinforcement_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('reinforcement_weight', 'reinforcement_weight_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('shape', 'shape_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('size', 'size_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('socket_type', 'socket_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('suction_force', 'suction_force_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('surface', 'surface_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('surface_finish', 'surface_finish_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('switch_function', 'switch_function_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('switch_type', 'switch_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('treatment', 'treatment_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('veneer_type', 'veneer_type_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('voltage', 'voltage_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('wattage', 'wattage_ar');
UPDATE source_product_attribute SET attribute_group = 'Specifications'
 WHERE attribute_code IN ('weight', 'weight_ar');
-- More information --
UPDATE source_product_attribute SET attribute_group = 'More information'
 WHERE attribute_code IN ('brand', 'brand_ar');
UPDATE source_product_attribute SET attribute_group = 'More information'
 WHERE attribute_code IN ('category', 'category_ar');
UPDATE source_product_attribute SET attribute_group = 'More information'
 WHERE attribute_code IN ('country_of_manufacture', 'country_of_manufacture_ar');
UPDATE source_product_attribute SET attribute_group = 'More information'
 WHERE attribute_code IN ('manufacturer', 'manufacturer_ar');
UPDATE source_product_attribute SET attribute_group = 'More information'
 WHERE attribute_code IN ('origin', 'origin_ar');
UPDATE source_product_attribute SET attribute_group = 'More information'
 WHERE attribute_code IN ('tag', 'tag_ar');

PRAGMA user_version = 46;
