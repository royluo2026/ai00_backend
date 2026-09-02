# BOP Bounded Navigation and Relation Design

## Goal

Restore BOP TC identity links and provide the Craft UI with complete, bounded, governed navigation, detail, and relation projections without direct table access or the generic legacy-read dispatcher.

## Change classification

- `craft.bop.entry.bulk.change.apply@1`: implementation defect fix. TC import already promises governed BOP entries and links; normal entity rows currently create an entity but fail to attach its primary link.
- `craft.bop.work_package.get@2`: compatible change. Add optional closed output fields while retaining pagination, ordering, errors, and all existing required fields.
- `craft.bop.entry.detail.get@1`: compatible change. Add optional closed primary-entity projection fields without removing existing entry or link fields.
- `craft.bop.entry.relation.list@1`: new atomic read capability replacing the `entry_links` operation of `craft.bop.entry.legacy_read@1`.
- `craft.bop.linked_entity.detail.get@1`: new atomic read capability replacing the `entity_detail` operation of `craft.bop.entry.legacy_read@1`.
- `ontology.concept.resolve@1`: compatible deterministic resolution extension for the already-governed `node_type_binding` external identity. No fuzzy fallback is added.

All descriptor-definition changes invalidate previous business-definition approval hashes. Machine evidence must be regenerated; human approval remains false until an authorized reviewer approves the new hashes.

## Architecture

Craft owns a single allowlisted primary-entity card projector in `services/bop_navigation.py`. Work-package pages batch primary links and their entity cards only for entries on the current page. Entry detail reuses the same projection for one entry. Unknown link types, deleted links, and missing entities close to `entity_data: null`; no dynamic table or column name enters SQL.

Relation reads live in a focused Craft capability module. They expose opaque link identity, source entry, typed target reference, primary/inherited flags, and an allowlisted summary. Recursive reads are constrained to one entry subtree, keyset paged, revision-pinned, and capped. Linked-entity detail accepts a link GID rather than an arbitrary table/ref pair and selects through a fixed link-type allowlist.

Ontology resolution recognizes `node_type_binding` as an exact external identity before human name/alias matching. The Craft compatibility route reads the returned `concept.stable_gid` and pins `concept.get` to the same immutable release.

## Output model

Work-package nodes and entry details may add:

- `meta`, `process_flow_pic`, `process_chart_pic`, `bom_row_id`
- `primary_link_count`, `primary_link`
- `entity_data`

`primary_link` is either null or a closed object containing `link_gid`, `link_type`, `entity_gid`, and `is_primary`. `entity_data` is either null or a closed card projection with common identity/title/VPPS fields plus allowlisted process, operation, station, operator, part, and resource card fields. JSON extension fields are decoded but remain bounded by the capability output budget.

## Invariants

1. Every TC-imported normal entity node has exactly one primary link to the entity created for that row.
2. Resource-demand nodes keep the existing exact/alias/staging resolution path and are never linked to the synthetic unused entity GID.
3. A page query loads entity cards only for the returned node GIDs.
4. Page size stays at most 200 and cursor ordering remains `(sort_order, gid)`.
5. Missing or unsupported primary entities never trigger dynamic SQL and produce a closed null projection.
6. Recursive relation reads cannot cross BOP versions and remain paged.
7. Ontology node-type resolution is exact and deterministic; unresolved bindings remain unresolved.

## Non-goals

- No frontend changes in this backend task.
- No production database migration or write.
- No generalized CRUD or `SELECT *` capability.
- No restoration of full-version entry loading.
- No automatic human approval.
