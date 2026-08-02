-- =====================================================================
-- 0058 — A UNIT THAT CAN NAME WHO SAID IT
--
-- The owner, looking at sikaegshop: «المشكلة التى لم تحل 100% فى sika هى
-- الوحدات اصلا». He is right, and the shape of the problem is not an empty
-- column. It is one column trying to be two things.
--
-- Plywood is sold by the SHEET — but one sheet is not another sheet, they
-- differ by thickness and by size. Pipe is sold by the pipe or by the metre
-- — but pipes differ by length, diameter, wall thickness and pressure
-- rating. `source_offer.selling_unit_id` has been asked to carry both "what
-- one of these is" and "which one of these it is", and a field asked to be
-- two things ends up being neither. Measured on the live warehouse
-- 2026-08-02: 92 of MADAR's 3,537 offers carry it, ALL of them the single
-- value kg, and 3,445 carry nothing at all.
--
-- WORSE THAN EMPTY. 52 MADAR offers publish a variant option reading
-- «N كجم/صندوق» or "N Pcs/Box" — the shop naming a BOX and saying what is
-- in it — and 18 of those are already stored as kg with basis 3 or 4. That
-- is not an unpopulated field. That is this schema overwriting what the
-- shop said, today, in the owner's own data, against the first rule the
-- project has: source truth is never edited.
--
-- THE SPLIT THIS MIGRATION MAKES
--
--   selling_unit_id + basis_quantity   what one priced thing IS   (already here)
--   content_quantity + content_unit_id what is INSIDE one of them (new)
--
-- Sika Swell 2010 states «10 متر» in its name and 3 kg in its spec row.
-- Under one column those two facts fight and one has to be silenced — and
-- silencing a published statement to protect a rule is precisely what this
-- project may not do. Under two, both survive: unit m, basis 10, content
-- (3, kg), and price-per-kg is arithmetic rather than a rewrite.
--
-- AND A UNIT MUST NOW BE ABLE TO SAY WHERE IT CAME FROM
--
-- The warehouse holds 1,472 units today and not one of them can name the
-- field it was read from. A number whose origin cannot be stated is not a
-- fact; it is a number someone typed. The owner may not edit source truth,
-- so he must at minimum be able to SEE which part of it he is looking at —
-- and to tell «the shop said this» from «we worked this out» at a glance.
--
--   unit_basis_provenance   a closed vocabulary, never blank
--   unit_basis_witness      the field, its language, the charter version
--                           and the literal text that was read
--
-- The two triggers below make that a rule of the database rather than a
-- habit of the connectors. A unit without both is refused. There is no
-- point adding a provenance column that a future connector can forget.
--
-- NOTHING HERE ENTERS ux_source_offer_identity. No offer changes identity,
-- none is split, no history moves — the same argument 0057 made in writing
-- when it added the weight basis, and for the same reason.
--
-- The vocabulary rows have carried NULL names since they were created. A
-- unit the owner reads has to have a word in both languages or the AR/EN
-- switch shows him a code, so the five that exist are filled. The ones this
-- work will meet are NOT seeded — see below.
-- =====================================================================

ALTER TABLE source_offer ADD COLUMN selling_unit_raw TEXT;
ALTER TABLE source_offer ADD COLUMN selling_unit_raw_lang TEXT;
ALTER TABLE source_offer ADD COLUMN content_quantity REAL;
ALTER TABLE source_offer ADD COLUMN content_unit_id INTEGER REFERENCES selling_unit(selling_unit_id);
ALTER TABLE source_offer ADD COLUMN unit_basis_provenance TEXT;
ALTER TABLE source_offer ADD COLUMN unit_basis_witness TEXT;

-- The words the owner reads. `name` is English by the naming rule; `name_ar`
-- is the site's own Arabic term where one exists.
UPDATE selling_unit SET name = 'metre',  name_ar = 'متر'  WHERE unit_code = 'm';
UPDATE selling_unit SET name = 'kilogram', name_ar = 'كيلوجرام' WHERE unit_code = 'kg';
UPDATE selling_unit SET name = 'litre',  name_ar = 'لتر'  WHERE unit_code = 'liter';
UPDATE selling_unit SET name = 'kilowatt hour', name_ar = 'كيلوواط ساعة' WHERE unit_code = 'kWh';
UPDATE selling_unit SET name = 'tonne',  name_ar = 'طن'   WHERE unit_code = 'tonne';

-- The vocabulary is NOT seeded here. It is created on demand as units are
-- actually met, and `selling_unit` holding only units something is priced in
-- is an invariant a test already asserts. Seeding gm, ml and piece ahead of
-- their first use would add three rows nobody has encountered and quietly
-- turn that invariant into a fiction. ingest.py names them at the moment it
-- creates them instead, from the word list in scrapex/units.py.

-- THE 1,064 THAT ARE ALREADY HERE. Every offer carrying a unit today was
-- written before any of this existed, so none can name a witness — and the
-- triggers below would refuse the next crawl that touched one. They are
-- marked rather than deleted: the value stands, and it says out loud that
-- nobody can say where it came from. Under the resolution metric it counts
-- as unresolved, which is the truth about it.
UPDATE source_offer
   SET unit_basis_provenance = 'legacy_unwitnessed',
       unit_basis_witness    = 'pre-0058: written by normalize.selling_unit_from '
                               || 'or a connector constant; the field it was read '
                               || 'from was not recorded'
 WHERE selling_unit_id IS NOT NULL
   AND (unit_basis_provenance IS NULL OR unit_basis_provenance = '');

-- A unit with no named source is not a fact. Both triggers exist because a
-- column a connector can forget is a column that will be forgotten — this
-- schema has watched exactly that happen to selling_unit_id itself.
CREATE TRIGGER IF NOT EXISTS trg_offer_unit_needs_a_witness_insert
BEFORE INSERT ON source_offer
WHEN NEW.selling_unit_id IS NOT NULL
 AND (NEW.unit_basis_provenance IS NULL OR NEW.unit_basis_provenance = ''
   OR NEW.unit_basis_witness IS NULL OR NEW.unit_basis_witness = '')
BEGIN
  SELECT RAISE(ABORT, 'a selling unit must carry its provenance and its witness');
END;

CREATE TRIGGER IF NOT EXISTS trg_offer_unit_needs_a_witness_update
BEFORE UPDATE OF selling_unit_id, unit_basis_provenance, unit_basis_witness ON source_offer
WHEN NEW.selling_unit_id IS NOT NULL
 AND (NEW.unit_basis_provenance IS NULL OR NEW.unit_basis_provenance = ''
   OR NEW.unit_basis_witness IS NULL OR NEW.unit_basis_witness = '')
BEGIN
  SELECT RAISE(ABORT, 'a selling unit must carry its provenance and its witness');
END;

PRAGMA user_version = 58;
