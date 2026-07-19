# Generic Dataset Catalogue (G1 Foundation)

G1 introduces persistent definitions for arbitrary websites without changing
the existing product and price warehouse. It is deliberately a foundation, not
a claim that generic crawling or row extraction is finished.

## Model

- `site_profile` identifies one website and may optionally link to an existing
  price `source_site`.
- `dataset_definition` identifies each table, list, detail record, tree, stream,
  or still-unknown structure discovered on that site.
- `field_definition` gives every dataset its own dynamic field set, stable keys,
  preserved original names, inferred data types, and discovery order.
- `dataset_relationship` stores a directed relationship between two datasets on
  the same site.
- `relationship_field_pair` supports single-column and composite joins.

Definitions are additive. A disappeared definition is retired with `valid_to`;
it is never deleted or reused for a different meaning. Display labels are
separate from immutable original names and stable keys.

## Relationship safety

Discovery can only create relationships with `review_status = suggested`.
There is intentionally no automatic-confirmation endpoint in G1. Database
triggers reject cross-site relationships and field mappings whose fields do not
belong to the parent and child datasets.

## API

The typed local API is rooted at `/api/catalog`:

- `POST/GET /sites`
- `POST/GET /sites/{site_key}/datasets`
- `POST/GET /datasets/{dataset_id}/fields`
- `POST/GET /sites/{site_key}/relationships`

Every collection read is cursor-paginated with `after_id` and a `limit` capped
at 200. Repeating an identical discovery is idempotent. Reusing a stable key for
a different URL, original name, type, locator, or relationship is a conflict,
not a silent rewrite.

## Capability state

`generic_dataset_catalog` reports stage `foundation` but remains disabled. It
may only be enabled after a later vertical slice adds generic row storage and a
complete user-facing catalogue workflow with recovery and compatibility tests.
