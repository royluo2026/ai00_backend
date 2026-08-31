# Capability V2 Structural Owner-Service Remediation Plan

This plan preserves the reviewed historical Web source scope while reconciling each group to current canonical unresolved, migrated-capability, or removed-dead-entry evidence. It is an implementation sequence, not an operations or BFF exemption.

- Historical scope: **45 occurrences / 37 root-cause groups**.
- Current progress: **28 migrated groups**, **5 removed dead-entry groups**; unresolved groups are retained rather than erased.
- Implementation disposition: unresolved groups remain `owner_service_required`; source-proved dead controls are `removed_dead_entry` with no target Capability.
- Global prohibitions: no private-router import; no direct SQL provider; no generic JSON contracts; no secret logging; no auto-confirm; no unbounded runtime execution; no fabricated atomicity; no silent REST fallback.

## Ordered packages

### 1. `base_plugin_lifecycle`

- Owner service: `backend.plugin_platform.service` (base).
- Boundary: Public marketplace lifecycle service; REST compatibility and Gateway provider call the same signed-release transition API.
- Dependencies: signed marketplace release registry, plugin installation migration.
- Cross-domain links: Base identity/tenant context is supplied through the public context port; no router import.
- Decision gate: Product/security must decide whether the obsolete arbitrary-URL flows are retired or mapped to signed marketplace acquisition.

### 2. `base_annotations`

- Owner service: `base.self_annotation_service` (base).
- Boundary: New public Base self-annotation service, with compatibility handlers and providers delegating to it rather than sharing router SQL.
- Dependencies: annotation aggregate migration, attachment reference policy.
- Cross-domain links: Attachment metadata is reached only through a typed Base attachment-reference port.
- Decision gate: Product/security must select the closed attachment projection and retention semantics; the existing arbitrary attachment records are not safely inferable.

### 3. `base_identity_profile`

- Owner service: `base.identity_profile_service` (base).
- Boundary: Public Base identity projection service shared by session compatibility handler and Gateway provider.
- Dependencies: identity projection contract.
- Cross-domain links: None; this remains a Base-only projection.
- Decision gate: Security/product must approve which profile and effective-grant fields are browser-visible.

### 4. `base_saved_views`

- Owner service: `base.saved_view_service` (base).
- Boundary: New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions.
- Dependencies: saved-view storage migration, approved semantic view configuration.
- Cross-domain links: None; sharing is enforced in the Base aggregate rather than delegated to a router.
- Decision gate: Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.

### 5. `integration_connector`

- Owner service: `plugins.integration.integration_backend.application.service.IntegrationApplication` (integration).
- Boundary: Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary.
- Dependencies: credential-vault write channel, connector runtime policy, connector aggregate migration.
- Cross-domain links: Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence.
- Decision gate: Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.

### 6. `integration_mapping`

- Owner service: `plugins.integration.integration_backend.application.service.IntegrationApplication` (integration).
- Boundary: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter.
- Dependencies: connector package, mapping aggregate migration, target-capability validation.
- Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query.
- Decision gate: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.

### 7. `craft_library`

- Owner service: `plugins.craft.craft_backend.application.library_lifecycle_service` (craft).
- Boundary: New public Craft library lifecycle service that validates references and performs one lifecycle transition; no route-shaped SQL provider.
- Dependencies: library reference index, Craft lifecycle audit migration.
- Cross-domain links: Reference checks use typed Craft ports only; no direct reads into other domain tables.
- Decision gate: Product must decide hard-delete versus obsolete/archive behavior because the only existing outcome is obsolete, not delete.

### 8. `craft_rules`

- Owner service: `plugins.craft.craft_backend.application.rules.RuleService` (craft).
- Boundary: Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it.
- Dependencies: rule aggregate migration, approved closed rule-definition vocabulary.
- Cross-domain links: None; rule evaluation remains within Craft's public service boundary.
- Decision gate: Product/security must approve the finite rule-definition and mutable lifecycle semantics; existing routes have no equivalent public service.

### 9. `craft_bop_lifecycle`

- Owner service: `plugins.craft.craft_backend.application.bop_version_lifecycle_service` (craft).
- Boundary: New public Craft BOP-version lifecycle service selected before Project list dispatch; it owns the conditional bop_version branch only.
- Dependencies: BOP version aggregate, conditional dispatch adapter.
- Cross-domain links: Project compatibility adapter selects item_type=bop_version then invokes Craft; it neither owns nor queries BOP tables.
- Decision gate: Product must confirm BOP-version archive/delete lifecycle and list projection; these are distinct from Project list semantics.

### 10. `agent_bounded_runtime`

- Owner service: `plugins.agent.agent_backend.application.bounded_runtime_service` (agent).
- Boundary: New public Agent bounded-runtime service with a fixed tool/node allowlist, sandbox executor, durable run records and audit lineage.
- Dependencies: sandbox runtime, durable run/pause-token store, Agent execution audit.
- Cross-domain links: Any Craft/Project data access is a bounded Gateway capability invocation, not direct SQL or imported routers.
- Decision gate: Security/product must approve the executable allowlist, sandbox/resource policy, confirmation policy and recovery behavior before implementation.

### 11. `project_approval`

- Owner service: `plugins.project_management.project_management_backend.application.service.ProjectManagementApplication` (project_management).
- Boundary: Existing ProjectManagementApplication approval.orders.reject boundary, extended in-package with notification outbox, audit and idempotency rather than a fabricated Project service.
- Dependencies: Project approval aggregate, notification outbox migration.
- Cross-domain links: Notifications are emitted through the transactional outbox, not a best-effort cross-domain HTTP call.
- Decision gate: Product must confirm rejection notification recipients/templates because current candidate omits the legacy notification effect.

## Group execution cards

### `DELETE /api/craft_lib/equipments/{dynamic}`

- Historical occurrences: web/knowledge_hub/pages/gbop_vpps.html:771:58:DELETE:/api/craft_lib/equipments/{dynamic}
- Current status: `removed_dead_entry` (`removed_dead_entry`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.library_lifecycle_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `None`; {'input': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.', 'output': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.', 'side_effects': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.'}
- Service boundary and transaction: New public Craft library lifecycle service that validates references and performs one lifecycle transition; no route-shaped SQL provider. not_applicable.
- Target: `None`. Scope: Craft workspace/object scope.
- Contract/security: Craft workspace/object scope; reference/lifecycle validation; audit event and revision lock.
- Migration: No migration: retain source-derived removal evidence.
- Tests: referenced/unreferenced delete behavior; owner/non-owner authorization; replay and lifecycle conflict. Dependencies: library reference index, Craft lifecycle audit migration. Cross-domain links: Reference checks use typed Craft ports only; no direct reads into other domain tables..
- Approval: None; implement from existing source evidence.
- Exit: interactive control absent; network path absent; no candidate capability; canonical inventory has no occurrence.

### `DELETE /api/craft_lib/fixtures/{dynamic}`

- Historical occurrences: web/knowledge_hub/pages/gbop_vpps.html:714:58:DELETE:/api/craft_lib/fixtures/{dynamic}
- Current status: `removed_dead_entry` (`removed_dead_entry`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.library_lifecycle_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `None`; {'input': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.', 'output': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.', 'side_effects': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.'}
- Service boundary and transaction: New public Craft library lifecycle service that validates references and performs one lifecycle transition; no route-shaped SQL provider. not_applicable.
- Target: `None`. Scope: Craft workspace/object scope.
- Contract/security: Craft workspace/object scope; reference/lifecycle validation; audit event and revision lock.
- Migration: No migration: retain source-derived removal evidence.
- Tests: referenced/unreferenced delete behavior; owner/non-owner authorization; replay and lifecycle conflict. Dependencies: library reference index, Craft lifecycle audit migration. Cross-domain links: Reference checks use typed Craft ports only; no direct reads into other domain tables..
- Approval: None; implement from existing source evidence.
- Exit: interactive control absent; network path absent; no candidate capability; canonical inventory has no occurrence.

### `DELETE /api/lists/{dynamic}`

- Historical occurrences: web/core/existing_capability_client.js:331:12:DELETE:/api/lists/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.bop_version_lifecycle_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/craft/craft_backend/capabilities/bop_writes.py:462-484`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Craft BOP-version lifecycle service selected before Project list dispatch; it owns the conditional bop_version branch only. one Craft BOP-version revision-locked archive transaction with audit.
- Target: `craft.bop.version.archive@1`. Scope: Craft version scope and expected revision.
- Contract/security: Craft version scope and expected revision; archive lifecycle/audit; no Project-list relabeling or direct SQL dispatch.
- Migration: Migrate only bop_version conditional branch with expected_revision; preserve Project delete behavior.
- Tests: conditional branch selection; BOP revision/authorization; Project list branch remains unchanged. Dependencies: BOP version aggregate, conditional dispatch adapter. Cross-domain links: Project compatibility adapter selects item_type=bop_version then invokes Craft; it neither owns nor queries BOP tables..
- Approval: Product must confirm BOP-version archive/delete lifecycle and list projection; these are distinct from Project list semantics.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `DELETE /api/plugin/uninstall/{dynamic}`

- Historical occurrences: web/core/web_compat.js:294:29:DELETE:/api/plugin/uninstall/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `backend.plugin_platform.service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Public marketplace lifecycle service; REST compatibility and Gateway provider call the same signed-release transition API. one tenant installation transaction with release/data-policy lock and audit event.
- Target: `base.plugin.installation.transition.uninstall@1`. Scope: signed publisher release and dependency compatibility.
- Contract/security: signed publisher release and dependency compatibility; tenant-scoped installation lock and audit event; no arbitrary URL or secret logging.
- Migration: Replace only after signed marketplace uninstall contract; otherwise retire the dead browser call.
- Tests: Gateway permission/tenant allow-deny; replay/rollback/data-policy boundary; signature/dependency/audit regression. Dependencies: signed marketplace release registry, plugin installation migration. Cross-domain links: Base identity/tenant context is supplied through the public context port; no router import..
- Approval: Product/security must decide whether the obsolete arbitrary-URL flows are retired or mapped to signed marketplace acquisition.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `DELETE /api/views/{dynamic}`

- Historical occurrences: web/components/view_manager.js:1002:28:DELETE:/api/views/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.saved_view_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions. one revision-locked delete transaction with audit.
- Target: `base.saved_view.delete@1`. Scope: owner/team/share visibility.
- Contract/security: owner/team/share visibility; closed semantic view schema; optimistic revision and idempotency key for writes.
- Migration: Use expected revision; migrate after ownership and retention policy are approved.
- Tests: owner/non-owner/team visibility; copy/update/delete replay and conflict; schema rejects arbitrary configuration. Dependencies: saved-view storage migration, approved semantic view configuration. Cross-domain links: None; sharing is enforced in the Base aggregate rather than delegated to a router..
- Approval: Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/ext-datasources`

- Historical occurrences: web/ext_datasource/ext_ds.js:148:36:GET:/api/ext-datasources
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary. read-only actor/team bound query.
- Target: `integration.connector.search@1`. Scope: opaque credential_ref only.
- Contract/security: opaque credential_ref only; network allowlist, timeout and bounded discovery; masked outputs, structured external failure and no secret evidence.
- Migration: Decide retention, then normalize browser projection to the existing closed connector search contract.
- Tests: tenant/cross-workspace Gateway authorization; credential redaction; connector-runtime timeout/outcome-unknown and idempotency. Dependencies: credential-vault write channel, connector runtime policy, connector aggregate migration. Cross-domain links: Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence..
- Approval: Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/ext-datasources/{dynamic}/tables`

- Historical occurrences: web/ext_datasource/ext_ds.js:640:36:GET:/api/ext-datasources/{dynamic}/tables
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary. bounded external read through runtime port; no fabricated atomic DB transaction.
- Target: `integration.connector.schema.discover@1`. Scope: opaque credential_ref only.
- Contract/security: opaque credential_ref only; network allowlist, timeout and bounded discovery; masked outputs, structured external failure and no secret evidence.
- Migration: Add timeout/result cap/error policy and return safe schema metadata.
- Tests: tenant/cross-workspace Gateway authorization; credential redaction; connector-runtime timeout/outcome-unknown and idempotency. Dependencies: credential-vault write channel, connector runtime policy, connector aggregate migration. Cross-domain links: Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence..
- Approval: Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/ext-field-mappings`

- Historical occurrences: web/ext_datasource/ext_ds.js:349:36:GET:/api/ext-field-mappings
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. read-only actor/team bound bounded query.
- Target: `integration.field_mapping.search@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Define exact field-mapping list projection instead of adapting singular mapping.get.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/ext-mappings`

- Historical occurrences: web/ext_datasource/ext_ds.js:187:36:GET:/api/ext-mappings
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. read-only actor/team bound query.
- Target: `integration.mapping.search@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Normalize browser projection to closed mapping search after retention decision.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/ext-mappings/{dynamic}/columns`

- Historical occurrences: web/ext_datasource/ext_ds.js:341:36:GET:/api/ext-mappings/{dynamic}/columns
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. bounded external discovery through connector runtime.
- Target: `integration.mapping.source_columns.discover@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Bind mapping to connector, cap result and apply runtime timeout policy.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/ext-mappings/{dynamic}/preview`

- Historical occurrences: web/ext_datasource/ext_ds.js:496:36:GET:/api/ext-mappings/{dynamic}/preview
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. bounded external preview through runtime port.
- Target: `integration.mapping.preview@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Cap preview rows, redact values and expose structured timeout/outcome status.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/lists`

- Historical occurrences: web/core/existing_capability_client.js:326:51:GET:/api/lists
- Current status: `migrated` (`migrated`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.bop_version_lifecycle_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/craft/craft_backend/capabilities/bop_versions.py:368-395`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Craft BOP-version lifecycle service selected before Project list dispatch; it owns the conditional bop_version branch only. read-only Craft BOP-version query selected by item_type before Project dispatch.
- Target: `craft.bop.version.list@1`. Scope: Craft version scope and expected revision.
- Contract/security: Craft version scope and expected revision; archive lifecycle/audit; no Project-list relabeling or direct SQL dispatch.
- Migration: Migrate only bop_version conditional branch; preserve Project list behavior.
- Tests: conditional branch selection; BOP revision/authorization; Project list branch remains unchanged. Dependencies: BOP version aggregate, conditional dispatch adapter. Cross-domain links: Project compatibility adapter selects item_type=bop_version then invokes Craft; it neither owns nor queries BOP tables..
- Approval: Product must confirm BOP-version archive/delete lifecycle and list projection; these are distinct from Project list semantics.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/rule-engine/check-entry`

- Historical occurrences: packages/craft-plugin/web/lineage_view/layout_detail_panel.js:2192:40:GET:/api/rule-engine/check-entry, packages/craft-plugin/web/lineage_view/layout_detail_panel.js:3524:40:GET:/api/rule-engine/check-entry
- Current status: `migrated` (`migrated`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.rules.RuleService`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/craft/craft_backend/capabilities/rule_engine.py:174-183`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it. bounded read/evaluation with audit record; no arbitrary executable expression.
- Target: `craft.rule.entry.evaluate@1`. Scope: workspace rule ownership.
- Contract/security: workspace rule ownership; closed rule-definition grammar; audit, revision lock, explicit confirmation and no generic JSON.
- Migration: Implement exact entry-check semantics, not CEL or BOP audit substitution.
- Tests: rule lifecycle authorization and revision conflict; definition/schema rejection; evaluation/waiver audit and idempotency. Dependencies: rule aggregate migration, approved closed rule-definition vocabulary. Cross-domain links: None; rule evaluation remains within Craft's public service boundary..
- Approval: Product/security must approve the finite rule-definition and mutable lifecycle semantics; existing routes have no equivalent public service.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/self_ann/list`

- Historical occurrences: web/components/self_annotation_panel.js:292:27:GET:/api/self_ann/list, web/components/self_annotation_panel.js:293:27:GET:/api/self_ann/list, web/knowledge_hub/knowledge_hub.js:499:42:GET:/api/self_ann/list
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.self_annotation_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base self-annotation service, with compatibility handlers and providers delegating to it rather than sharing router SQL. read-only self-scoped bounded query.
- Target: `base.self_annotation.search@1`. Scope: self-only user scope.
- Contract/security: self-only user scope; closed attachment summary/reference schema; no opaque attachment JSON or secret-derived fields.
- Migration: Add bounded search/pagination and closed attachment projection before Gateway migration.
- Tests: self/non-self Gateway authorization; closed input/output validation; write replay and attachment-retention boundary. Dependencies: annotation aggregate migration, attachment reference policy. Cross-domain links: Attachment metadata is reached only through a typed Base attachment-reference port..
- Approval: Product/security must select the closed attachment projection and retention semantics; the existing arbitrary attachment records are not safely inferable.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/self_ann/{dynamic}`

- Historical occurrences: web/components/self_annotation_panel.js:146:36:GET:/api/self_ann/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.self_annotation_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base self-annotation service, with compatibility handlers and providers delegating to it rather than sharing router SQL. read-only self-scoped query.
- Target: `base.self_annotation.record.get@1`. Scope: self-only user scope.
- Contract/security: self-only user scope; closed attachment summary/reference schema; no opaque attachment JSON or secret-derived fields.
- Migration: Add a closed attachment summary/reference projection and migrate through Gateway.
- Tests: self/non-self Gateway authorization; closed input/output validation; write replay and attachment-retention boundary. Dependencies: annotation aggregate migration, attachment reference policy. Cross-domain links: Attachment metadata is reached only through a typed Base attachment-reference port..
- Approval: Product/security must select the closed attachment projection and retention semantics; the existing arbitrary attachment records are not safely inferable.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/users/me`

- Historical occurrences: packages/craft-plugin/web/lineage_view/lineage.js:511:34:GET:/api/users/me
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.identity_profile_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Public Base identity projection service shared by session compatibility handler and Gateway provider. read-only actor-bound projection.
- Target: `base.identity.session.profile.get@1`. Scope: actor-bound self scope.
- Contract/security: actor-bound self scope; allowlisted profile/grant projection; never expose raw grants or permission blobs.
- Migration: Create a redacted closed profile projection and migrate the session call.
- Tests: anonymous/self/other-user denial; closed output schema; redaction of grants and permissions. Dependencies: identity projection contract. Cross-domain links: None; this remains a Base-only projection..
- Approval: Security/product must approve which profile and effective-grant fields are browser-visible.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `GET /api/views`

- Historical occurrences: web/admin/task_planning.html:1068:26:GET:/api/views, web/components/view_manager.js:541:40:GET:/api/views
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.saved_view_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions. read-only owner/team/share scoped query.
- Target: `base.saved_view.search@1`. Scope: owner/team/share visibility.
- Contract/security: owner/team/share visibility; closed semantic view schema; optimistic revision and idempotency key for writes.
- Migration: Define finite saved-view query/config schema then migrate list callers.
- Tests: owner/non-owner/team visibility; copy/update/delete replay and conflict; schema rejects arbitrary configuration. Dependencies: saved-view storage migration, approved semantic view configuration. Cross-domain links: None; sharing is enforced in the Base aggregate rather than delegated to a router..
- Approval: Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `PATCH /api/ext-datasources/{dynamic}`

- Historical occurrences: web/ext_datasource/ext_ds.js:623:29:PATCH:/api/ext-datasources/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary. one revision-locked connector aggregate transaction.
- Target: `integration.connector.update@1`. Scope: opaque credential_ref only.
- Contract/security: opaque credential_ref only; network allowlist, timeout and bounded discovery; masked outputs, structured external failure and no secret evidence.
- Migration: Use closed update and credential_ref rotation semantics; no raw config pass-through.
- Tests: tenant/cross-workspace Gateway authorization; credential redaction; connector-runtime timeout/outcome-unknown and idempotency. Dependencies: credential-vault write channel, connector runtime policy, connector aggregate migration. Cross-domain links: Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence..
- Approval: Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `PATCH /api/views/{dynamic}`

- Historical occurrences: web/components/view_manager.js:1011:28:PATCH:/api/views/{dynamic}, web/components/view_manager.js:651:30:PATCH:/api/views/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.saved_view_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions. one revision-locked update transaction with audit.
- Target: `base.saved_view.update@1`. Scope: owner/team/share visibility.
- Contract/security: owner/team/share visibility; closed semantic view schema; optimistic revision and idempotency key for writes.
- Migration: Use closed patch grammar and expected revision.
- Tests: owner/non-owner/team visibility; copy/update/delete replay and conflict; schema rejects arbitrary configuration. Dependencies: saved-view storage migration, approved semantic view configuration. Cross-domain links: None; sharing is enforced in the Base aggregate rather than delegated to a router..
- Approval: Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/approval/orders/{dynamic}/reject`

- Historical occurrences: packages/craft-plugin/web/approval/approval.js:153:26:POST:/api/approval/orders/{dynamic}/reject
- Current status: `migrated` (`migrated`).
- Owner/service: `project_management` / `plugins.project_management.project_management_backend.application.service.ProjectManagementApplication`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/project_management/project_management_backend/capabilities/reviewed.py:244-281`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing ProjectManagementApplication approval.orders.reject boundary, extended in-package with notification outbox, audit and idempotency rather than a fabricated Project service. one Project approval transition transaction with audit and transactional notification outbox.
- Target: `project.approval.order.reject@1`. Scope: tenant/order scope and approver authorization.
- Contract/security: tenant/order scope and approver authorization; revision/idempotency; transactional audit plus durable notification outbox.
- Migration: Implement exact reject plus notification semantics; do not use candidate that omits notification.
- Tests: approver/non-approver/cross-tenant denial; rejection replay and notification outbox; state conflict and outcome recovery. Dependencies: Project approval aggregate, notification outbox migration. Cross-domain links: Notifications are emitted through the transactional outbox, not a best-effort cross-domain HTTP call..
- Approval: Product must confirm rejection notification recipients/templates because current candidate omits the legacy notification effect.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/ext-datasources`

- Historical occurrences: web/ext_datasource/ext_ds.js:625:28:POST:/api/ext-datasources
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary. one connector aggregate transaction; credential material is written only through vault port.
- Target: `integration.connector.create@1`. Scope: opaque credential_ref only.
- Contract/security: opaque credential_ref only; network allowlist, timeout and bounded discovery; masked outputs, structured external failure and no secret evidence.
- Migration: Replace plaintext browser credentials with credential_ref secure enrolment.
- Tests: tenant/cross-workspace Gateway authorization; credential redaction; connector-runtime timeout/outcome-unknown and idempotency. Dependencies: credential-vault write channel, connector runtime policy, connector aggregate migration. Cross-domain links: Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence..
- Approval: Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/ext-datasources/{dynamic}/test`

- Historical occurrences: web/ext_datasource/ext_ds.js:605:34:POST:/api/ext-datasources/{dynamic}/test
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication with a credential-vault port and connector-runtime port; both legacy adapters and providers invoke that boundary. bounded external probe with durable operation result when outcome is uncertain.
- Target: `integration.connector.connection.test@1`. Scope: opaque credential_ref only.
- Contract/security: opaque credential_ref only; network allowlist, timeout and bounded discovery; masked outputs, structured external failure and no secret evidence.
- Migration: Use runtime port test double in tests and disclose outcome-unknown semantics.
- Tests: tenant/cross-workspace Gateway authorization; credential redaction; connector-runtime timeout/outcome-unknown and idempotency. Dependencies: credential-vault write channel, connector runtime policy, connector aggregate migration. Cross-domain links: Credential vault and connector runtime are typed ports; credentials never cross into browser/Gateway evidence..
- Approval: Product/security must decide whether each stale browser connector flow is retained and authorize credential enrolment plus external-network policy.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/ext-mappings`

- Historical occurrences: web/ext_datasource/ext_ds.js:677:26:POST:/api/ext-mappings
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. one mapping aggregate transaction with target-capability validation.
- Target: `integration.mapping.create@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Use restricted transform grammar and exact target version validation.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/ext-mappings/{dynamic}/import`

- Historical occurrences: web/ext_datasource/ext_ds.js:549:37:POST:/api/ext-mappings/{dynamic}/import
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. durable asynchronous import operation with idempotency and recoverable status.
- Target: `integration.mapping.import.start@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Replace synthetic sync.start response with a real run/outcome resource.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/flows/test-node`

- Historical occurrences: packages/agent-plugin/web/flow_canvas/flow_editor.js:754:36:POST:/api/flows/test-node, web/canvas/types/flow_type.js:145:29:POST:/api/flows/test-node
- Current status: `unresolved` (`unresolved`).
- Owner/service: `agent` / `plugins.agent.agent_backend.application.bounded_runtime_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/agent/agent_backend/routers/flows.py`; No node-test handler or runtime service exists in the Agent provider.
- Service boundary and transaction: New public Agent bounded-runtime service with a fixed tool/node allowlist, sandbox executor, durable run records and audit lineage. durable bounded sandbox run with timeout/resource limits and auditable result.
- Target: `agent.workflow.node.test.execute@1`. Scope: no eval or browser supplied executable config.
- Contract/security: no eval or browser supplied executable config; authorization, sandbox, timeout and resource limits; confirmation, pause-token integrity and outcome recovery.
- Migration: Route through fixed node allowlist and public runtime service; never arbitrary dispatch.
- Tests: allowlist/sandbox/timeout/resource limit; cross-workspace authorization; resume idempotency and audit lineage. Dependencies: sandbox runtime, durable run/pause-token store, Agent execution audit. Cross-domain links: Any Craft/Project data access is a bounded Gateway capability invocation, not direct SQL or imported routers..
- Approval: Security/product must approve the executable allowlist, sandbox/resource policy, confirmation policy and recovery behavior before implementation.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/plugin/install`

- Historical occurrences: web/core/web_compat.js:287:27:POST:/api/plugin/install
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `backend.plugin_platform.service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Public marketplace lifecycle service; REST compatibility and Gateway provider call the same signed-release transition API. one tenant installation transaction; release verification and mount activation are explicit lifecycle steps.
- Target: `base.plugin.installation.request.create@1`. Scope: signed publisher release and dependency compatibility.
- Contract/security: signed publisher release and dependency compatibility; tenant-scoped installation lock and audit event; no arbitrary URL or secret logging.
- Migration: Replace arbitrary URL input with signed release selection and explicit grants; otherwise retire.
- Tests: Gateway permission/tenant allow-deny; replay/rollback/data-policy boundary; signature/dependency/audit regression. Dependencies: signed marketplace release registry, plugin installation migration. Cross-domain links: Base identity/tenant context is supplied through the public context port; no router import..
- Approval: Product/security must decide whether the obsolete arbitrary-URL flows are retired or mapped to signed marketplace acquisition.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/rules/{dynamic}/activate`

- Historical occurrences: web/rule_mgmt/rule_mgmt.js:173:26:POST:/api/rules/{dynamic}/activate
- Current status: `removed_dead_entry` (`removed_dead_entry`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.rules.RuleService`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `None`; {'input': '/api/rules/{dynamic}/activate: REST activates mutable rule gid; candidate activates a published immutable release contract.', 'output': '/api/rules/{dynamic}/activate: REST returns rule status; candidate returns accepted release outcome.', 'side_effects': '/api/rules/{dynamic}/activate: Candidate lifecycle handler does not mutate the legacy rule record.'}
- Service boundary and transaction: Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it. not_applicable.
- Target: `None`. Scope: workspace rule ownership.
- Contract/security: workspace rule ownership; closed rule-definition grammar; audit, revision lock, explicit confirmation and no generic JSON.
- Migration: No migration: retain source-derived removal evidence.
- Tests: rule lifecycle authorization and revision conflict; definition/schema rejection; evaluation/waiver audit and idempotency. Dependencies: rule aggregate migration, approved closed rule-definition vocabulary. Cross-domain links: None; rule evaluation remains within Craft's public service boundary..
- Approval: None; implement from existing source evidence.
- Exit: interactive control absent; network path absent; no candidate capability; canonical inventory has no occurrence.

### `POST /api/rules/{dynamic}/deviations`

- Historical occurrences: web/rule_mgmt/rule_mgmt.js:220:36:POST:/api/rules/{dynamic}/deviations
- Current status: `removed_dead_entry` (`removed_dead_entry`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.rules.RuleService`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `None`; {'input': '/api/rules/{dynamic}/deviations: REST deviation body is tied to rule gid; candidate waiver contract expects governed release/evidence fields.', 'output': '/api/rules/{dynamic}/deviations: REST returns deviation record; candidate returns accepted waiver outcome.', 'side_effects': '/api/rules/{dynamic}/deviations: Candidate does not persist the legacy deviation model.'}
- Service boundary and transaction: Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it. not_applicable.
- Target: `None`. Scope: workspace rule ownership.
- Contract/security: workspace rule ownership; closed rule-definition grammar; audit, revision lock, explicit confirmation and no generic JSON.
- Migration: No migration: retain source-derived removal evidence.
- Tests: rule lifecycle authorization and revision conflict; definition/schema rejection; evaluation/waiver audit and idempotency. Dependencies: rule aggregate migration, approved closed rule-definition vocabulary. Cross-domain links: None; rule evaluation remains within Craft's public service boundary..
- Approval: None; implement from existing source evidence.
- Exit: interactive control absent; network path absent; no candidate capability; canonical inventory has no occurrence.

### `POST /api/rules/{dynamic}/suspend`

- Historical occurrences: web/rule_mgmt/rule_mgmt.js:175:26:POST:/api/rules/{dynamic}/suspend
- Current status: `removed_dead_entry` (`removed_dead_entry`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.rules.RuleService`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `None`; {'input': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.', 'output': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.', 'side_effects': 'Catalog and provider review found no exact provider-equivalent stable outcome; similar names were rejected.'}
- Service boundary and transaction: Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it. not_applicable.
- Target: `None`. Scope: workspace rule ownership.
- Contract/security: workspace rule ownership; closed rule-definition grammar; audit, revision lock, explicit confirmation and no generic JSON.
- Migration: No migration: retain source-derived removal evidence.
- Tests: rule lifecycle authorization and revision conflict; definition/schema rejection; evaluation/waiver audit and idempotency. Dependencies: rule aggregate migration, approved closed rule-definition vocabulary. Cross-domain links: None; rule evaluation remains within Craft's public service boundary..
- Approval: None; implement from existing source evidence.
- Exit: interactive control absent; network path absent; no candidate capability; canonical inventory has no occurrence.

### `POST /api/skills/canvas-options`

- Historical occurrences: packages/agent-plugin/web/wfc_window/wfc_window.js:1599:35:POST:/api/skills/canvas-options
- Current status: `unresolved` (`unresolved`).
- Owner/service: `agent` / `plugins.agent.agent_backend.application.bounded_runtime_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/agent/agent_backend/routers/skills_v2.py`; No bounded canvas-option resolver exists in the Agent provider.
- Service boundary and transaction: New public Agent bounded-runtime service with a fixed tool/node allowlist, sandbox executor, durable run records and audit lineage. bounded deterministic resolver with actor/workspace audit.
- Target: `agent.canvas.options.resolve@1`. Scope: no eval or browser supplied executable config.
- Contract/security: no eval or browser supplied executable config; authorization, sandbox, timeout and resource limits; confirmation, pause-token integrity and outcome recovery.
- Migration: Expose only approved option resolvers; browser configuration is data, never executable code.
- Tests: allowlist/sandbox/timeout/resource limit; cross-workspace authorization; resume idempotency and audit lineage. Dependencies: sandbox runtime, durable run/pause-token store, Agent execution audit. Cross-domain links: Any Craft/Project data access is a bounded Gateway capability invocation, not direct SQL or imported routers..
- Approval: Security/product must approve the executable allowlist, sandbox/resource policy, confirmation policy and recovery behavior before implementation.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/skills/execute-canvas`

- Historical occurrences: packages/agent-plugin/web/wfc_window/wfc_window.js:2264:40:POST:/api/skills/execute-canvas
- Current status: `unresolved` (`unresolved`).
- Owner/service: `agent` / `plugins.agent.agent_backend.application.bounded_runtime_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/agent/agent_backend/routers/skills_v2.py`; No canvas execution provider exists; generic run mutation is not provider-equivalent.
- Service boundary and transaction: New public Agent bounded-runtime service with a fixed tool/node allowlist, sandbox executor, durable run records and audit lineage. durable sandbox run with confirmation, idempotency, pause token and outcome recovery.
- Target: `agent.canvas.execution.start@1`. Scope: no eval or browser supplied executable config.
- Contract/security: no eval or browser supplied executable config; authorization, sandbox, timeout and resource limits; confirmation, pause-token integrity and outcome recovery.
- Migration: Do not substitute generic agent.run mutation; build exact canvas runtime path.
- Tests: allowlist/sandbox/timeout/resource limit; cross-workspace authorization; resume idempotency and audit lineage. Dependencies: sandbox runtime, durable run/pause-token store, Agent execution audit. Cross-domain links: Any Craft/Project data access is a bounded Gateway capability invocation, not direct SQL or imported routers..
- Approval: Security/product must approve the executable allowlist, sandbox/resource policy, confirmation policy and recovery behavior before implementation.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/skills/resume-canvas`

- Historical occurrences: packages/agent-plugin/web/wfc_window/wfc_window.js:1615:40:POST:/api/skills/resume-canvas
- Current status: `unresolved` (`unresolved`).
- Owner/service: `agent` / `plugins.agent.agent_backend.application.bounded_runtime_service`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/agent/agent_backend/routers/skills_v2.py`; No pause-token resume provider exists; generic run mutation is not provider-equivalent.
- Service boundary and transaction: New public Agent bounded-runtime service with a fixed tool/node allowlist, sandbox executor, durable run records and audit lineage. durable resume transaction locking validated pause token and run state.
- Target: `agent.canvas.execution.resume@1`. Scope: no eval or browser supplied executable config.
- Contract/security: no eval or browser supplied executable config; authorization, sandbox, timeout and resource limits; confirmation, pause-token integrity and outcome recovery.
- Migration: Validate signed pause token, replay behavior and sandbox policy; no generic run mutation.
- Tests: allowlist/sandbox/timeout/resource limit; cross-workspace authorization; resume idempotency and audit lineage. Dependencies: sandbox runtime, durable run/pause-token store, Agent execution audit. Cross-domain links: Any Craft/Project data access is a bounded Gateway capability invocation, not direct SQL or imported routers..
- Approval: Security/product must approve the executable allowlist, sandbox/resource policy, confirmation policy and recovery behavior before implementation.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/views`

- Historical occurrences: web/components/view_manager.js:657:42:POST:/api/views, web/components/view_manager.js:713:40:POST:/api/views
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.saved_view_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions. one saved-view create transaction with owner/share validation.
- Target: `base.saved_view.create@1`. Scope: owner/team/share visibility.
- Contract/security: owner/team/share visibility; closed semantic view schema; optimistic revision and idempotency key for writes.
- Migration: Use closed config, idempotency key and returned revision.
- Tests: owner/non-owner/team visibility; copy/update/delete replay and conflict; schema rejects arbitrary configuration. Dependencies: saved-view storage migration, approved semantic view configuration. Cross-domain links: None; sharing is enforced in the Base aggregate rather than delegated to a router..
- Approval: Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `POST /api/views/{dynamic}/copy`

- Historical occurrences: web/components/view_manager.js:978:42:POST:/api/views/{dynamic}/copy
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.saved_view_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base saved-view aggregate service, used by Gateway and legacy adapter; it owns view records, sharing, copying, and revisions. one source-read plus destination-create transaction with idempotency.
- Target: `base.saved_view.copy@1`. Scope: owner/team/share visibility.
- Contract/security: owner/team/share visibility; closed semantic view schema; optimistic revision and idempotency key for writes.
- Migration: Define copy/share/ownership semantics and migrate with an idempotency key.
- Tests: owner/non-owner/team visibility; copy/update/delete replay and conflict; schema rejects arbitrary configuration. Dependencies: saved-view storage migration, approved semantic view configuration. Cross-domain links: None; sharing is enforced in the Base aggregate rather than delegated to a router..
- Approval: Product must choose the finite saved-view configuration language and copy/share semantics; current dynamic config cannot be inferred safely.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `PUT /api/ext-field-mappings/batch`

- Historical occurrences: web/ext_datasource/ext_ds.js:457:23:PUT:/api/ext-field-mappings/batch
- Current status: `migrated` (`migrated`).
- Owner/service: `integration` / `plugins.integration.integration_backend.application.service.IntegrationApplication`
- Blocker evidence: `docs/governance/integration-structural-web-remediation.json`; `{'end_line': 42, 'sha256': 'fe1bfdd9844a78f786f85287e44d451fc0bf96b4538c37411558624b2aec7d0d', 'source_path': 'plugins/integration/integration_backend/capabilities/provider.py', 'start_line': 42}`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Existing public IntegrationApplication mapping operations backed by Integration repository and connector-runtime ports; no cross-domain database adapter. one bounded batch transaction with per-item revision conflicts.
- Target: `integration.field_mapping.batch.update@1`. Scope: closed field-mapping grammar and restricted transforms.
- Contract/security: closed field-mapping grammar and restricted transforms; owner/team binding; bounded preview/import and safe external error classes.
- Migration: Define batch limit and all-or-partial success contract; do not relabel generic mapping.update.
- Tests: mapping scope and revision conflict; transform schema rejection; preview/import timeout and outcome recovery. Dependencies: connector package, mapping aggregate migration, target-capability validation. Cross-domain links: Exact stable target capability is resolved through the Catalog target index, never a cross-domain database query..
- Approval: Product must decide whether absent legacy mapping routes become supported governed flows or are removed; that intent is not encoded in a provider.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `PUT /api/rules/{dynamic}`

- Historical occurrences: web/container_card/modes/container_item_detail.js:137:53:PUT:/api/rules/{dynamic}, web/container_card/modes/mode_field_detail.js:47:50:PUT:/api/rules/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `craft` / `plugins.craft.craft_backend.application.rules.RuleService`
- Blocker evidence: `docs/governance/craft-agent-project-structural-web-remediation.json`; `plugins/craft/craft_backend/capabilities/rule_library.py:149-176`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: Public Craft RuleService expanded into bounded definition/lifecycle/evaluation/waiver operations; compatibility and Gateway must share it. one revision-locked rule-definition transaction plus audit.
- Target: `craft.rule.definition.change.apply@1`. Scope: workspace rule ownership.
- Contract/security: workspace rule ownership; closed rule-definition grammar; audit, revision lock, explicit confirmation and no generic JSON.
- Migration: Define finite rule grammar before migration; reject arbitrary rule_definition JSON.
- Tests: rule lifecycle authorization and revision conflict; definition/schema rejection; evaluation/waiver audit and idempotency. Dependencies: rule aggregate migration, approved closed rule-definition vocabulary. Cross-domain links: None; rule evaluation remains within Craft's public service boundary..
- Approval: Product/security must approve the finite rule-definition and mutable lifecycle semantics; existing routes have no equivalent public service.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.

### `PUT /api/self_ann/{dynamic}`

- Historical occurrences: web/components/self_annotation_panel.js:175:35:PUT:/api/self_ann/{dynamic}
- Current status: `migrated` (`migrated`).
- Owner/service: `base` / `base.self_annotation_service`
- Blocker evidence: `docs/governance/base-structural-web-remediation.json`; `backend/base/web_atomic.py:HANDLERS: dict`; Migrated through the reviewed public owner service and generated capability evidence.
- Service boundary and transaction: New public Base self-annotation service, with compatibility handlers and providers delegating to it rather than sharing router SQL. one self-annotation revision transaction with attachment reference validation.
- Target: `base.self_annotation.change.apply@1`. Scope: self-only user scope.
- Contract/security: self-only user scope; closed attachment summary/reference schema; no opaque attachment JSON or secret-derived fields.
- Migration: Use expected revision and idempotency key; migrate only after attachment contract approval.
- Tests: self/non-self Gateway authorization; closed input/output validation; write replay and attachment-retention boundary. Dependencies: annotation aggregate migration, attachment reference policy. Cross-domain links: Attachment metadata is reached only through a typed Base attachment-reference port..
- Approval: Product/security must select the closed attachment projection and retention semantics; the existing arbitrary attachment records are not safely inferable.
- Exit: public owner service and Gateway provider share this boundary; closed contract and scope tests pass; fresh canonical occurrence migrates without REST fallback; no operations/BFF/canonical-disposition relabeling.
