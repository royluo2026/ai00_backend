# vismockup.scene.render@1

This additive Connector adapter operation is consumed by Simulation's existing prepared materialization and reverse-capture workflows. It does not expose a new HTTP endpoint or bypass Gateway, plan signatures, exact-action confirmation, device/session binding, or the App execution gate.

## Wire identity

- Adapter: `ai00.vismockup`, major 1.
- Product: Siemens VisMockup 14.x.
- Operation: `vismockup.scene.render@1`.
- Contract hash: `sha256:0cb32eaf55dc0a4ec477878ad9a3934fcf08273f4ab6e0b78a6fa5d504c0c1e2`.
- Canonical contract projection: operation_id, input_fields below in this order, output_fields below, contract_version=1. This is the same hash convention as the existing Connector scene operations, not a new Catalog capability identity.
- Side effect: write; V2 post-condition probe: `vismockup.document.snapshot@1`.

Input object has exactly:

1. `document_id`: existing bound active document identity.
2. `baseline_snapshot_hash`: immutable environment baseline.
3. `operation_id`: BOP process identity, equal to scene.operation_id.
4. `scene`: existing SceneStateV1 containing operation_id, visible_products, visible_resources, capture_profile and scene_hash.
5. `highlight_products`: explicit product node keys, a subset of scene.visible_products; empty for gray initialization and post-capture hiding.
6. `fit_all`: true only for initialization; false for subsequent process scenes so their context camera stays unchanged.

Output: `{ "actual_scene_hash": "sha256:..." }`.

## Behavior

Resolve authorized manifest keys to current document keys; expand selected assemblies to bounded leaf sets. Reset selected geometry to gray, enforce exact visible leaf scope, optionally FitAll, and verify visibility. If highlighting is requested, validate a temporary gray image before applying pure blue. The subsequent existing `vismockup.view.capture@1` validates actual gray/blue image differences and commits a unique final PNG only after validation. Invalid candidates are deleted and targets are not hidden.

After the uploaded capture step succeeds, the signed plan runs another render with no highlights and with completed, unshared product nodes removed. Previously blue targets are reset to gray before hiding. A final scene.verify step must succeed; a captured artifact alone does not complete the BOP step if hiding or verification fails.

Shared products remain when earlier BOP processes still reference them. Empty processes are marked skipped by the server, not rendered as empty screenshots. Each capture plan still contains exactly one artifact-producing capture step.

The installed `D:/Siemens/Visualization14/Program/VisAutomation.tlb` was read without controlling the application on 2026-09-30. It declares CaptureImage(path) at DISPID 27, FitAll at 23, BasicMaterial at node DISPID 24, and MMVUpdate at inner application DISPID 59. CaptureImage does not accept width/height arguments. Its native image is aspect-fitted, without cropping or scene substitution, to the existing 1920x1080 PNG output profile before verification.

## Failures and compatibility

Representative errors: scene_render_input_invalid, vismockup_document_changed, scene_node_not_found, scene_verification_failed, capture_gray_baseline_invalid, capture_empty_or_clipped_scene, capture_target_not_blue_or_occluded, capture_render_required and capture_dimension_mismatch.

Existing scene.apply@1 and view.capture@1 remain advertised. New environments require render@1 with the exact hash; old runtimes fail preflight. Old environments lacking this operation fail with simulation_capture_environment_upgrade_required and must be recomposed, rather than silently using legacy screenshots. No database schema migration is introduced.

This document is implementation evidence, not a signed Catalog release or runtime approval. Updating the adapter binary and recomposing the environment are required before a real demonstration.
