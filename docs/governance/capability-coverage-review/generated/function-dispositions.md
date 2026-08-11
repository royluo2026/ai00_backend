# Function dispositions

| Domain | Function | Resolution | Capability |
|---|---|---|---|

| Agent | `agent_runtime:DELETE:/v1/sessions/{session_gid}` | unreviewed | — |
| Agent | `agent_runtime:GET:/health` | unreviewed | — |
| Agent | `agent_runtime:GET:/v1/runs/{session_gid}` | unreviewed | — |
| Agent | `agent_runtime:GET:/v1/runs/{session_gid}/approvals` | unreviewed | — |
| Agent | `agent_runtime:GET:/v1/sessions` | unreviewed | — |
| Agent | `agent_runtime:GET:/v1/sessions/{session_gid}` | unreviewed | — |
| Agent | `agent_runtime:GET:/v1/tools` | unreviewed | — |
| Agent | `agent_runtime:POST:/v1/runs` | unreviewed | — |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/(pause|resume|cancel)` | unreviewed | — |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/approvals/{parameter_2}/decision` | unreviewed | — |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/messages` | unreviewed | — |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/messages/stream` | unreviewed | — |
| Agent | `agent_runtime:POST:/v1/sessions` | unreviewed | — |
| Agent | `agent_tool:aggregate_history` | unreviewed | — |
| Agent | `agent_tool:ask_for_clarification` | unreviewed | — |
| Agent | `agent_tool:calculate` | unreviewed | — |
| Agent | `agent_tool:create_discussion_topic` | unreviewed | — |
| Agent | `agent_tool:flag_for_review` | unreviewed | — |
| Agent | `agent_tool:list_memories` | unreviewed | — |
| Agent | `agent_tool:list_preferences` | unreviewed | — |
| Agent | `agent_tool:recall_memory` | unreviewed | — |
| Agent | `agent_tool:save_memory` | unreviewed | — |
| Agent | `agent_tool:save_preference` | unreviewed | — |
| Agent | `rest:DELETE:/api/ai/sessions/{gid}` | unreviewed | — |
| Agent | `rest:DELETE:/api/flows/{gid}` | unreviewed | — |
| Agent | `rest:DELETE:/api/skills/{gid}` | unreviewed | — |
| Agent | `rest:GET:/api/ai/admin-config` | unreviewed | — |
| Agent | `rest:GET:/api/ai/audit-logs` | unreviewed | — |
| Agent | `rest:GET:/api/ai/balance` | unreviewed | — |
| Agent | `rest:GET:/api/ai/sessions` | unreviewed | — |
| Agent | `rest:GET:/api/ai/sessions/{gid}` | unreviewed | — |
| Agent | `rest:GET:/api/ai/tools` | unreviewed | — |
| Agent | `rest:GET:/api/flows` | unreviewed | — |
| Agent | `rest:GET:/api/flows/capability-manifest` | unreviewed | — |
| Agent | `rest:GET:/api/flows/runs` | unreviewed | — |
| Agent | `rest:GET:/api/flows/runs/{run_gid}` | unreviewed | — |
| Agent | `rest:GET:/api/flows/{gid}` | unreviewed | — |
| Agent | `rest:GET:/api/skills` | unreviewed | — |
| Agent | `rest:POST:/api/ai/abort` | unreviewed | — |
| Agent | `rest:POST:/api/ai/admin-config` | unreviewed | — |
| Agent | `rest:POST:/api/ai/audit` | unreviewed | — |
| Agent | `rest:POST:/api/ai/chat` | unreviewed | — |
| Agent | `rest:POST:/api/ai/chat/stream` | unreviewed | — |
| Agent | `rest:POST:/api/ai/confirm` | unreviewed | — |
| Agent | `rest:POST:/api/ai/confirm/sync` | unreviewed | — |
| Agent | `rest:POST:/api/ai/sessions/new` | unreviewed | — |
| Agent | `rest:POST:/api/ai/test-connection` | unreviewed | — |
| Agent | `rest:POST:/api/flows` | unreviewed | — |
| Agent | `rest:POST:/api/flows/gen-script` | unreviewed | — |
| Agent | `rest:POST:/api/flows/runs/{run_gid}/step` | unreviewed | — |
| Agent | `rest:POST:/api/flows/{gid}/run` | unreviewed | — |
| Agent | `rest:POST:/api/skills` | unreviewed | — |
| Agent | `rest:POST:/api/skills/seed-system` | unreviewed | — |
| Agent | `rest:PUT:/api/flows/{gid}` | unreviewed | — |
| Agent | `rest:PUT:/api/skills/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/admin/config/{key}` | excluded | — |
| Base Platform | `rest:GET:/` | excluded | — |
| Base Platform | `rest:GET:/admin/cloud-db-config` | excluded | — |
| Base Platform | `rest:GET:/admin/config` | excluded | — |
| Base Platform | `rest:GET:/admin/config/{key}` | excluded | — |
| Base Platform | `rest:GET:/admin/debug-logs` | excluded | — |
| Base Platform | `rest:GET:/admin/plugin-registry` | excluded | — |
| Base Platform | `rest:GET:/api/deploy` | excluded | — |
| Base Platform | `rest:GET:/api/deploy/current` | excluded | — |
| Base Platform | `rest:GET:/api/deploy/history` | excluded | — |
| Base Platform | `rest:GET:/api/deploy/pipeline` | excluded | — |
| Base Platform | `rest:GET:/api/feishu/im/contact-messages` | excluded | — |
| Base Platform | `rest:GET:/api/feishu/im/mentions` | excluded | — |
| Base Platform | `rest:GET:/api/file-store/config` | excluded | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/assets/{token}/{plugin_id}/{version}/{asset_path:path}` | excluded | — |
| Base Platform | `rest:GET:/api/v2/agent-capabilities/catalog` | excluded | — |
| Base Platform | `rest:GET:/api/v2/agent-capabilities/catalog-preview` | excluded | — |
| Base Platform | `rest:GET:/api/v2/capability-artifacts/{artifact_id}` | excluded | — |
| Base Platform | `rest:GET:/api/v2/capability-operations/{operation_id}` | excluded | — |
| Base Platform | `rest:GET:/auth/feishu/callback` | excluded | — |
| Base Platform | `rest:GET:/auth/feishu/login-url` | excluded | — |
| Base Platform | `rest:GET:/auth/feishu/poll/{state}` | excluded | — |
| Base Platform | `rest:GET:/auth/me` | excluded | — |
| Base Platform | `rest:GET:/feishu/cache/debug` | excluded | — |
| Base Platform | `rest:GET:/feishu/calendar/events/{event_id}` | excluded | — |
| Base Platform | `rest:GET:/feishu/calendar/today` | excluded | — |
| Base Platform | `rest:GET:/feishu/org/dept-search` | excluded | — |
| Base Platform | `rest:GET:/feishu/org/users` | excluded | — |
| Base Platform | `rest:GET:/feishu/org/users/search` | excluded | — |
| Base Platform | `rest:GET:/feishu/search/chats` | excluded | — |
| Base Platform | `rest:GET:/feishu/search/docs` | excluded | — |
| Base Platform | `rest:GET:/feishu/search/events` | excluded | — |
| Base Platform | `rest:GET:/feishu/search/meetings` | excluded | — |
| Base Platform | `rest:GET:/feishu/search/users` | excluded | — |
| Base Platform | `rest:GET:/feishu/sync/org/status` | excluded | — |
| Base Platform | `rest:GET:/health` | excluded | — |
| Base Platform | `rest:GET:/ready` | excluded | — |
| Base Platform | `rest:GET:/{capability_id}` | excluded | — |
| Base Platform | `rest:PATCH:/feishu/calendar/events/{event_id}` | excluded | — |
| Base Platform | `rest:PATCH:/feishu/calendar/events/{event_id}/rsvp` | excluded | — |
| Base Platform | `rest:POST:/admin/cloud-db-config` | excluded | — |
| Base Platform | `rest:POST:/admin/cloud-db-config/test` | excluded | — |
| Base Platform | `rest:POST:/admin/config/reload` | excluded | — |
| Base Platform | `rest:POST:/admin/server-restart` | excluded | — |
| Base Platform | `rest:POST:/api/deploy/rollback` | excluded | — |
| Base Platform | `rest:POST:/api/feishu/doc/read` | excluded | — |
| Base Platform | `rest:POST:/api/feishu/doc/write-cells` | excluded | — |
| Base Platform | `rest:POST:/api/file-store/config` | excluded | — |
| Base Platform | `rest:POST:/api/file-store/ois-config` | excluded | — |
| Base Platform | `rest:POST:/api/file-store/ois-test` | excluded | — |
| Base Platform | `rest:POST:/api/file-store/test` | excluded | — |
| Base Platform | `rest:POST:/api/uploads` | excluded | — |
| Base Platform | `rest:POST:/api/uploads/ois/resolve` | excluded | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/mounts/{mount_session_id}/capabilities/{capability_id}:confirm` | excluded | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/mounts/{mount_session_id}/capabilities/{capability_id}:invoke` | excluded | — |
| Base Platform | `rest:POST:/api/v2/agent-capabilities/delegations` | excluded | — |
| Base Platform | `rest:POST:/api/v2/agent-capabilities/{capability_id}:confirm` | excluded | — |
| Base Platform | `rest:POST:/api/v2/agent-capabilities/{capability_id}:invoke` | excluded | — |
| Base Platform | `rest:POST:/api/v2/capability-artifacts/uploads` | excluded | — |
| Base Platform | `rest:POST:/api/v2/capability-artifacts/uploads/{upload_id}:finalize` | excluded | — |
| Base Platform | `rest:POST:/api/v2/mcp-capabilities/delegations` | excluded | — |
| Base Platform | `rest:POST:/api/v2/mcp-capabilities/{capability_id}:invoke` | excluded | — |
| Base Platform | `rest:POST:/auth/logout` | excluded | — |
| Base Platform | `rest:POST:/auth/refresh` | excluded | — |
| Base Platform | `rest:POST:/feishu/cache/refresh` | excluded | — |
| Base Platform | `rest:POST:/feishu/chat-message/share-list` | excluded | — |
| Base Platform | `rest:POST:/feishu/message/send` | excluded | — |
| Base Platform | `rest:POST:/feishu/sync/org` | excluded | — |
| Base Platform | `rest:POST:/feishu/sync/org/structure` | excluded | — |
| Base Platform | `rest:POST:/feishu/webhook/bitable` | excluded | — |
| Base Platform | `rest:POST:/{capability_id}:confirm` | excluded | — |
| Base Platform | `rest:POST:/{capability_id}:invoke` | excluded | — |
| Base Platform | `rest:PUT:/admin/config/{key}` | excluded | — |
| Base Platform | `rest:PUT:/api/uploads/{filename}` | excluded | — |
| Base Platform | `rest:PUT:/api/v2/capability-artifacts/uploads/{upload_id}/content` | excluded | — |
| Base Platform | `rest:DELETE:/api/self_ann/{item_gid}` | new_capability | `base.annotation.change.apply` |
| Base Platform | `rest:PUT:/api/annotations/{key}` | new_capability | `base.annotation.change.apply` |
| Base Platform | `rest:PUT:/api/self_ann/{item_gid}` | new_capability | `base.annotation.change.apply` |
| Base Platform | `rest:GET:/api/annotations/{key}` | new_capability | `base.annotation.read` |
| Base Platform | `rest:GET:/api/self_ann/batch` | new_capability | `base.annotation.read` |
| Base Platform | `rest:GET:/api/self_ann/list` | new_capability | `base.annotation.read` |
| Base Platform | `rest:GET:/api/self_ann/{item_gid}` | new_capability | `base.annotation.read` |
| Base Platform | `rest:DELETE:/api/grants/{gid}` | new_capability | `base.authorization.grant.change.apply` |
| Base Platform | `rest:POST:/api/grants` | new_capability | `base.authorization.grant.change.apply` |
| Base Platform | `rest:GET:/api/grants` | new_capability | `base.authorization.grant.read` |
| Base Platform | `rest:GET:/api/grants/me` | new_capability | `base.authorization.grant.read` |
| Base Platform | `rest:DELETE:/api/ext-datasources/{gid}` | new_capability | `base.external_datasource.change.apply` |
| Base Platform | `rest:PATCH:/api/ext-datasources/{gid}` | new_capability | `base.external_datasource.change.apply` |
| Base Platform | `rest:POST:/api/ext-datasources` | new_capability | `base.external_datasource.change.apply` |
| Base Platform | `rest:POST:/api/ext-datasources/{gid}/test` | new_capability | `base.external_datasource.connection.test` |
| Base Platform | `rest:GET:/api/ext-datasources` | new_capability | `base.external_datasource.search` |
| Base Platform | `rest:GET:/api/ext-datasources/{gid}/tables` | new_capability | `base.external_datasource.search` |
| Base Platform | `rest:DELETE:/api/ext-mappings/{gid}` | new_capability | `base.external_mapping.change.apply` |
| Base Platform | `rest:PATCH:/api/ext-mappings/{gid}` | new_capability | `base.external_mapping.change.apply` |
| Base Platform | `rest:POST:/api/ext-mappings` | new_capability | `base.external_mapping.change.apply` |
| Base Platform | `rest:POST:/api/ext-mappings/{gid}/import` | new_capability | `base.external_mapping.change.apply` |
| Base Platform | `rest:PUT:/api/ext-field-mappings/batch` | new_capability | `base.external_mapping.change.apply` |
| Base Platform | `rest:GET:/api/ext-field-mappings` | new_capability | `base.external_mapping.read` |
| Base Platform | `rest:GET:/api/ext-mappings` | new_capability | `base.external_mapping.read` |
| Base Platform | `rest:GET:/api/ext-mappings/{gid}/columns` | new_capability | `base.external_mapping.read` |
| Base Platform | `rest:GET:/api/ext-mappings/{gid}/preview` | new_capability | `base.external_mapping.read` |
| Base Platform | `rest:POST:/api/org/sync-from-feishu` | new_capability | `base.identity.directory.sync` |
| Base Platform | `rest:PATCH:/api/users/{user_gid}/role` | new_capability | `base.identity.role.assign` |
| Base Platform | `rest:GET:/api/users/me` | new_capability | `base.identity.session.get` |
| Base Platform | `rest:GET:/users/me` | new_capability | `base.identity.session.get` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/publishers` | new_capability | `base.plugin.marketplace.publisher.register` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases` | new_capability | `base.plugin.marketplace.release.change.apply` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases/{plugin_id}/{version}/review` | new_capability | `base.plugin.marketplace.release.change.apply` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases/{plugin_id}/{version}/revoke` | new_capability | `base.plugin.marketplace.release.change.apply` |
| Base Platform | `rest:GET:/api/plugin/list` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/catalog` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/installations` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/installations/{plugin_id}/events` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/registry` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/releases` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/usage/months/{month}` | new_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/usage/months/{month}/close` | new_capability | `base.plugin.marketplace.usage.close` |
| Base Platform | `rest:DELETE:/api/views/{gid}` | new_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:PATCH:/api/views/{gid}` | new_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:POST:/api/views` | new_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:POST:/api/views/{gid}/copy` | new_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:GET:/api/views` | new_capability | `base.saved_view.read` |
| Base Platform | `rest:DELETE:/teams/{gid}` | new_capability | `base.team.change.apply` |
| Base Platform | `rest:PATCH:/teams/{gid}` | new_capability | `base.team.change.apply` |
| Base Platform | `rest:PATCH:/teams/{gid}/config` | new_capability | `base.team.change.apply` |
| Base Platform | `rest:POST:/teams` | new_capability | `base.team.change.apply` |
| Base Platform | `rest:DELETE:/teams/{gid}/members/{user_gid}` | new_capability | `base.team.membership.change.apply` |
| Base Platform | `rest:POST:/teams/{gid}/members` | new_capability | `base.team.membership.change.apply` |
| Base Platform | `rest:GET:/teams` | new_capability | `base.team.read` |
| Base Platform | `rest:GET:/teams/{gid}/members` | new_capability | `base.team.read` |
| Base Platform | `capability:identity.principal.search` | existing_capability | `identity.principal.search` |
| Base Platform | `rest:GET:/api/users/` | existing_capability | `identity.principal.search` |
| Base Platform | `rest:GET:/api/users/search` | existing_capability | `identity.principal.search` |
| Base Platform | `rest:GET:/users/` | existing_capability | `identity.principal.search` |
| Base Platform | `capability:plugin.disable` | existing_capability | `plugin.disable` |
| Base Platform | `capability:plugin.enable` | existing_capability | `plugin.enable` |
| Base Platform | `capability:plugin.install` | existing_capability | `plugin.install` |
| Base Platform | `capability:plugin.revoke` | existing_capability | `plugin.revoke` |
| Base Platform | `capability:plugin.rollback` | existing_capability | `plugin.rollback` |
| Base Platform | `capability:plugin.storage.delete` | existing_capability | `plugin.storage.delete` |
| Base Platform | `capability:plugin.storage.get` | existing_capability | `plugin.storage.get` |
| Base Platform | `capability:plugin.storage.list` | existing_capability | `plugin.storage.list` |
| Base Platform | `capability:plugin.storage.put` | existing_capability | `plugin.storage.put` |
| Base Platform | `capability:plugin.uninstall` | existing_capability | `plugin.uninstall` |
| Base Platform | `capability:plugin.upgrade` | existing_capability | `plugin.upgrade` |
| Base Platform | `capability:plugin.upgrade.finish` | existing_capability | `plugin.upgrade.finish` |
| Base Platform | `capability:semantic.context.get` | existing_capability | `semantic.context.get` |
| Base Platform | `capability:system.activity.search` | existing_capability | `system.activity.search` |
| Base Platform | `capability:system.change_impact.preview` | existing_capability | `system.change_impact.preview` |
| Base Platform | `capability:system.echo` | existing_capability | `system.echo` |
| Base Platform | `capability:system.job.cancel` | existing_capability | `system.job.cancel` |
| Base Platform | `capability:system.job.get` | existing_capability | `system.job.get` |
| Base Platform | `capability:system.lineage.get` | existing_capability | `system.lineage.get` |
| Base Platform | `agent_tool:global_search` | existing_capability | `system.search` |
| Base Platform | `agent_tool:search` | existing_capability | `system.search` |
| Base Platform | `capability:system.search` | existing_capability | `system.search` |
| Base Platform | `capability:system.worker.outbox.health` | existing_capability | `system.worker.outbox.health` |
| Craft | `agent_tool:audit_entry_rules` | unreviewed | — |
| Craft | `agent_tool:check_rules` | unreviewed | — |
| Craft | `agent_tool:generate_canvas` | unreviewed | — |
| Craft | `agent_tool:get_canvas_state` | unreviewed | — |
| Craft | `agent_tool:get_entry_relations` | unreviewed | — |
| Craft | `agent_tool:get_selected_elements` | unreviewed | — |
| Craft | `agent_tool:list_rules` | unreviewed | — |
| Craft | `agent_tool:run_skill_canvas` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/entries/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/entry-links/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/factories/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/factory_sections/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/factory_stations/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/fork-presets/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/layout_templates/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/operations/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/posts/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/resources/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/staging/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/steps/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/bop/version-families/{family_gid}/archive` | unreviewed | — |
| Craft | `rest:DELETE:/api/canvases/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/craft_lib/fasteners/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/craft_lib/part_names/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/craft_lib/tools/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/ebom/parts/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/ebom/snapshots/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/factory/equipments/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/factory/fixtures/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/factory/sections/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/factory/stations/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/factory/tools/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/gbop/entries/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/gbop/entry-links/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/gbop/operations/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/gbop/processes/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/gbop/version-families/{family_gid}/archive` | unreviewed | — |
| Craft | `rest:DELETE:/api/import-export/templates/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/rules/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/std_op/operations/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bop/entity-detail` | unreviewed | — |
| Craft | `rest:GET:/api/bop/entries/search` | unreviewed | — |
| Craft | `rest:GET:/api/bop/entries/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bop/entries/{gid}/history` | unreviewed | — |
| Craft | `rest:GET:/api/bop/entry-links` | unreviewed | — |
| Craft | `rest:GET:/api/bop/factories` | unreviewed | — |
| Craft | `rest:GET:/api/bop/factories/{factory_gid}/layout_templates` | unreviewed | — |
| Craft | `rest:GET:/api/bop/factories/{factory_gid}/sections` | unreviewed | — |
| Craft | `rest:GET:/api/bop/factories/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bop/factory_sections/{section_gid}/stations` | unreviewed | — |
| Craft | `rest:GET:/api/bop/fork-presets` | unreviewed | — |
| Craft | `rest:GET:/api/bop/fork-presets/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bop/layout_templates/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bop/operations/{gid}/drift-check` | unreviewed | — |
| Craft | `rest:GET:/api/bop/operations/{op_gid}/resources` | unreviewed | — |
| Craft | `rest:GET:/api/bop/pbom-snapshots` | unreviewed | — |
| Craft | `rest:GET:/api/bop/pbom-versions` | unreviewed | — |
| Craft | `rest:GET:/api/bop/pbom-versions/{pbom_gid}/gbop-match-preview` | unreviewed | — |
| Craft | `rest:GET:/api/bop/pbom/search` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/canvas` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/layout-config` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/history` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/checkpoints` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/history` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/operation-log` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/pbom-change-point` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/pbom-diff-queue` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{gid}/pbom-link-stats` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/alt-hier` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/auto-link-preview` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/bop-tree` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/history` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/line-op-catia-parts` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/line-operations` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/link-summary` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/linked-parts` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/pbom` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/staging` | unreviewed | — |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/station-part-map` | unreviewed | — |
| Craft | `rest:GET:/api/canvases` | unreviewed | — |
| Craft | `rest:GET:/api/canvases/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/craft_lib/equipments` | unreviewed | — |
| Craft | `rest:GET:/api/craft_lib/fasteners` | unreviewed | — |
| Craft | `rest:GET:/api/craft_lib/fixtures` | unreviewed | — |
| Craft | `rest:GET:/api/craft_lib/part_names` | unreviewed | — |
| Craft | `rest:GET:/api/craft_lib/tools` | unreviewed | — |
| Craft | `rest:GET:/api/ebom/diff` | unreviewed | — |
| Craft | `rest:GET:/api/ebom/snapshots` | unreviewed | — |
| Craft | `rest:GET:/api/ebom/snapshots/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/ebom/snapshots/{gid}/parts` | unreviewed | — |
| Craft | `rest:GET:/api/ebom/vpps_check` | unreviewed | — |
| Craft | `rest:GET:/api/factory/equipments` | unreviewed | — |
| Craft | `rest:GET:/api/factory/fixtures` | unreviewed | — |
| Craft | `rest:GET:/api/factory/sections` | unreviewed | — |
| Craft | `rest:GET:/api/factory/stations` | unreviewed | — |
| Craft | `rest:GET:/api/factory/tools` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/bop-versions/{bop_gid}/station-autolink-preview` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/entries/{entry_gid}/links` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/pbom-versions/{pbom_gid}/gbop-nav-link-summary` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/pbom-versions/{pbom_gid}/process-hierarchy` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/pbom-versions/{pbom_gid}/vpps-auto-link-status` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/versions` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/versions/{version_gid}/entries` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/versions/{version_gid}/operations` | unreviewed | — |
| Craft | `rest:GET:/api/gbop/versions/{version_gid}/processes` | unreviewed | — |
| Craft | `rest:GET:/api/import-export/templates` | unreviewed | — |
| Craft | `rest:GET:/api/rules` | unreviewed | — |
| Craft | `rest:GET:/api/rules/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/std_op/operations` | unreviewed | — |
| Craft | `rest:GET:/api/std_op/operations/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/vpps-operations` | unreviewed | — |
| Craft | `rest:GET:/api/vpps-operations/rule4-ignores` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/entity-detail` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/entries/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/factories/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/factory_sections/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/factory_stations/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/fork-presets/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/layout_templates/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/operations/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/pbom-diff-queue/{item_gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/posts/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/staging/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/steps/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/versions/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/versions/{gid}/lifecycle/init-state` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/versions/{gid}/pbom-match` | unreviewed | — |
| Craft | `rest:PATCH:/api/bop/versions/{gid}/vehicle-ops-stats` | unreviewed | — |
| Craft | `rest:PATCH:/api/canvases/{gid}/shared` | unreviewed | — |
| Craft | `rest:PATCH:/api/craft_lib/equipments/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/craft_lib/fasteners/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/craft_lib/fixtures/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/craft_lib/part_names/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/craft_lib/tools/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/ebom/parts/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/ebom/snapshots/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/ebom/snapshots/{gid}/status` | unreviewed | — |
| Craft | `rest:PATCH:/api/ebom/snapshots/{gid}/vpps-stats` | unreviewed | — |
| Craft | `rest:PATCH:/api/factory/equipments/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/factory/fixtures/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/factory/sections/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/factory/stations/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/factory/tools/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/gbop/entries/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/gbop/operations/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/gbop/processes/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/gbop/versions/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/import-export/templates/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/rules/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/std_op/operations/{gid}` | unreviewed | — |
| Craft | `rest:POST:/api/bop/entries` | unreviewed | — |
| Craft | `rest:POST:/api/bop/entries/{gid}/demote` | unreviewed | — |
| Craft | `rest:POST:/api/bop/entries/{gid}/history/{log_gid}/rollback` | unreviewed | — |
| Craft | `rest:POST:/api/bop/entry-links` | unreviewed | — |
| Craft | `rest:POST:/api/bop/factories` | unreviewed | — |
| Craft | `rest:POST:/api/bop/factories/{factory_gid}/layout_templates` | unreviewed | — |
| Craft | `rest:POST:/api/bop/factories/{factory_gid}/sections` | unreviewed | — |
| Craft | `rest:POST:/api/bop/factory_sections/{section_gid}/stations` | unreviewed | — |
| Craft | `rest:POST:/api/bop/fork-presets` | unreviewed | — |
| Craft | `rest:POST:/api/bop/layout_templates/{gid}/apply` | unreviewed | — |
| Craft | `rest:POST:/api/bop/operations/{gid}/reset-fields` | unreviewed | — |
| Craft | `rest:POST:/api/bop/operations/{op_gid}/resources` | unreviewed | — |
| Craft | `rest:POST:/api/bop/operations/{op_gid}/steps` | unreviewed | — |
| Craft | `rest:POST:/api/bop/pbom-versions/{pbom_gid}/gbop-match-confirm` | unreviewed | — |
| Craft | `rest:POST:/api/bop/pics/upload` | unreviewed | — |
| Craft | `rest:POST:/api/bop/posts/{post_gid}/operations` | unreviewed | — |
| Craft | `rest:POST:/api/bop/resolve-gids` | unreviewed | — |
| Craft | `rest:POST:/api/bop/staging/{gid}/promote` | unreviewed | — |
| Craft | `rest:POST:/api/bop/version-families/{family_gid}/archive` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{bop_gid}/gbop-auto-link` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{bop_gid}/posts` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/freeze` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/freeze-snapshot` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/confirm-phase` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/checkpoints` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/redo` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/rollback/{checkpoint_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/undo` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/refresh-stats` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/undo-step` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/pbom-diff-queue` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/promote` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/publish` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{gid}/unfreeze` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{source_gid}/fork` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{source_gid}/smart-fork` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{src_gid}/save-as-template` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{src_gid}/stage-advance` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{template_gid}/update-from/{src_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/auto-link` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/copy-from-gbop/{src_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/copy-from/{src_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/import-tc` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/purge-entries` | unreviewed | — |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/staging` | unreviewed | — |
| Craft | `rest:POST:/api/canvases` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/equipments` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/equipments/{gid}/obsolete` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/fasteners` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/fixtures` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/fixtures/{gid}/obsolete` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/part_names` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/part_names/batch_accept_alias` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/part_names/batch_add_from_pbom` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/part_names/{gid}/accept_alias` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/tools` | unreviewed | — |
| Craft | `rest:POST:/api/craft_lib/tools/{gid}/obsolete` | unreviewed | — |
| Craft | `rest:POST:/api/ebom/snapshots` | unreviewed | — |
| Craft | `rest:POST:/api/ebom/snapshots/{gid}/parts` | unreviewed | — |
| Craft | `rest:POST:/api/ebom/snapshots/{gid}/parts/batch` | unreviewed | — |
| Craft | `rest:POST:/api/factory/equipments` | unreviewed | — |
| Craft | `rest:POST:/api/factory/equipments/{gid}/maintenance` | unreviewed | — |
| Craft | `rest:POST:/api/factory/equipments/{gid}/return` | unreviewed | — |
| Craft | `rest:POST:/api/factory/equipments/{gid}/scrap` | unreviewed | — |
| Craft | `rest:POST:/api/factory/fixtures` | unreviewed | — |
| Craft | `rest:POST:/api/factory/fixtures/{gid}/maintenance` | unreviewed | — |
| Craft | `rest:POST:/api/factory/fixtures/{gid}/return` | unreviewed | — |
| Craft | `rest:POST:/api/factory/fixtures/{gid}/scrap` | unreviewed | — |
| Craft | `rest:POST:/api/factory/sections` | unreviewed | — |
| Craft | `rest:POST:/api/factory/stations` | unreviewed | — |
| Craft | `rest:POST:/api/factory/tools` | unreviewed | — |
| Craft | `rest:POST:/api/factory/tools/{gid}/maintenance` | unreviewed | — |
| Craft | `rest:POST:/api/factory/tools/{gid}/return` | unreviewed | — |
| Craft | `rest:POST:/api/factory/tools/{gid}/scrap` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/bop-versions/{bop_gid}/station-autolink` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/bop-versions/{bop_gid}/station-autolink-undo` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/entries` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/entry-links` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/operations` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/pbom-versions/{pbom_gid}/vpps-auto-link` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/pbom-versions/{pbom_gid}/vpps-auto-link-confirm` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/processes` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/version-families/{family_gid}/archive` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/versions` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/versions/{gid}/freeze` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/versions/{source_gid}/fork` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/versions/{version_gid}/import-entries` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/versions/{version_gid}/import-tc-excel` | unreviewed | — |
| Craft | `rest:POST:/api/gbop/versions/{version_gid}/import-vpps-parts` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/export/diff-lark-sheet` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/export/diff-report` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/export/excel` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/import/parse-excel` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/lark-bitable/read` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/lark-bitable/write` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/lark-sheets/read` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/lark-sheets/write` | unreviewed | — |
| Craft | `rest:POST:/api/import-export/templates` | unreviewed | — |
| Craft | `rest:POST:/api/rule-engine/audit/bop-version/{version_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/rule-engine/check` | unreviewed | — |
| Craft | `rest:POST:/api/rules` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations/{gid}/clone-to-post` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations/{gid}/deprecate` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations/{gid}/publish` | unreviewed | — |
| Craft | `rest:POST:/api/vpps-operations/rule4-bulk-ignore` | unreviewed | — |
| Craft | `rest:POST:/api/vpps-operations/{gid}/revert` | unreviewed | — |
| Craft | `rest:PUT:/api/bop/versions/{gid}/layout-config` | unreviewed | — |
| Craft | `capability:craft.bop.draft.change.apply` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `capability:craft.bop.draft.change.preview` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `capability:craft.bop.execution_structure.get` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/entries` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `capability:craft.bop.execution_structure.preview` | existing_capability | `craft.bop.execution_structure.preview` |
| Craft | `capability:craft.bop.import.preview` | existing_capability | `craft.bop.import.preview` |
| Craft | `capability:craft.bop.linked_parts.get` | existing_capability | `craft.bop.linked_parts.get` |
| Craft | `capability:craft.bop.version.archive` | existing_capability | `craft.bop.version.archive` |
| Craft | `capability:craft.bop.version.compare` | existing_capability | `craft.bop.version.compare` |
| Craft | `capability:craft.bop.version.create` | existing_capability | `craft.bop.version.create` |
| Craft | `capability:craft.bop.version.get` | existing_capability | `craft.bop.version.get` |
| Craft | `capability:craft.bop.version.list` | existing_capability | `craft.bop.version.list` |
| Craft | `rest:GET:/api/bop/versions` | existing_capability | `craft.bop.version.list` |
| Craft | `capability:craft.bop.work_package.get` | existing_capability | `craft.bop.work_package.get` |
| Craft | `capability:craft.gbop.item.knowledge.list` | existing_capability | `craft.gbop.item.knowledge.list` |
| Craft | `capability:craft.gbop.item.search` | existing_capability | `craft.gbop.item.search` |
| Craft | `capability:craft.gbop.item.usage.get` | existing_capability | `craft.gbop.item.usage.get` |
| Craft | `capability:craft.pbom.part.search` | existing_capability | `craft.pbom.part.search` |
| Craft | `capability:craft.pbom.snapshot.compare` | existing_capability | `craft.pbom.snapshot.compare` |
| Craft | `capability:craft.pbom.snapshot.get` | existing_capability | `craft.pbom.snapshot.get` |
| Digital Model | `capability:digital_model.component.search` | existing_capability | `digital_model.component.search` |
| Digital Model | `capability:digital_model.model.create` | existing_capability | `digital_model.model.create` |
| Digital Model | `capability:digital_model.model.get` | existing_capability | `digital_model.model.get` |
| Digital Model | `capability:digital_model.model.search` | existing_capability | `digital_model.model.search` |
| Digital Model | `capability:digital_model.snapshot.compare` | existing_capability | `digital_model.snapshot.compare` |
| Digital Model | `capability:digital_model.snapshot.get` | existing_capability | `digital_model.snapshot.get` |
| Digital Model | `capability:digital_model.version.create` | existing_capability | `digital_model.version.create` |
| Knowledge | `agent_tool:recommend_practice` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `agent_tool:search_knowledge` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `capability:knowledge.context.retrieve` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `rest:GET:/api/knowledge_hub/items` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `capability:knowledge.document.acl.grant` | existing_capability | `knowledge.document.acl.grant` |
| Knowledge | `capability:knowledge.document.acl.list` | existing_capability | `knowledge.document.acl.list` |
| Knowledge | `capability:knowledge.document.acl.revoke` | existing_capability | `knowledge.document.acl.revoke` |
| Knowledge | `rest:DELETE:/api/knowledge_hub/items/{gid}` | new_capability | `knowledge.document.archive` |
| Knowledge | `capability:knowledge.document.create` | existing_capability | `knowledge.document.create` |
| Knowledge | `rest:POST:/api/knowledge_hub/items` | existing_capability | `knowledge.document.create` |
| Knowledge | `capability:knowledge.document.diff` | existing_capability | `knowledge.document.diff` |
| Knowledge | `agent_tool:get_knowledge_document` | existing_capability | `knowledge.document.get` |
| Knowledge | `capability:knowledge.document.get` | existing_capability | `knowledge.document.get` |
| Knowledge | `rest:GET:/api/knowledge_hub/items/{gid}` | existing_capability | `knowledge.document.get` |
| Knowledge | `capability:knowledge.document.history.get` | existing_capability | `knowledge.document.history.get` |
| Knowledge | `rest:GET:/api/knowledge_hub/items/{gid}/history` | existing_capability | `knowledge.document.history.get` |
| Knowledge | `capability:knowledge.document.restore` | existing_capability | `knowledge.document.restore` |
| Knowledge | `capability:knowledge.document.revise` | existing_capability | `knowledge.document.revise` |
| Knowledge | `rest:PATCH:/api/knowledge_hub/items/{gid}` | existing_capability | `knowledge.document.revise` |
| Knowledge | `capability:knowledge.document.revisions` | existing_capability | `knowledge.document.revisions` |
| Knowledge | `capability:knowledge.document.rollback` | existing_capability | `knowledge.document.rollback` |
| Knowledge | `capability:knowledge.document.search` | existing_capability | `knowledge.document.search` |
| Knowledge | `rest:DELETE:/api/knowledge_entries/{gid}` | new_capability | `knowledge.entry.change.apply` |
| Knowledge | `rest:PATCH:/api/knowledge_entries/{gid}` | new_capability | `knowledge.entry.change.apply` |
| Knowledge | `rest:POST:/api/knowledge_entries` | new_capability | `knowledge.entry.change.apply` |
| Knowledge | `agent_tool:get_knowledge_entry` | existing_capability | `knowledge.get` |
| Knowledge | `capability:knowledge.get` | existing_capability | `knowledge.get` |
| Knowledge | `rest:GET:/api/knowledge_entries/{gid}` | existing_capability | `knowledge.get` |
| Knowledge | `capability:knowledge.migration.status` | existing_capability | `knowledge.migration.status` |
| Knowledge | `rest:POST:/api/knowledge_hub/items/{gid}/favorite` | new_capability | `knowledge.personalization.change.apply` |
| Knowledge | `rest:POST:/api/knowledge_hub/items/{gid}/recent` | new_capability | `knowledge.personalization.change.apply` |
| Knowledge | `rest:GET:/api/knowledge_hub/favorites` | new_capability | `knowledge.personalization.read` |
| Knowledge | `rest:GET:/api/knowledge_hub/recent` | new_capability | `knowledge.personalization.read` |
| Knowledge | `capability:knowledge.proposal.get` | existing_capability | `knowledge.proposal.get` |
| Knowledge | `capability:knowledge.proposal.list` | existing_capability | `knowledge.proposal.list` |
| Knowledge | `capability:knowledge.proposal.outbox.list` | existing_capability | `knowledge.proposal.outbox.list` |
| Knowledge | `capability:knowledge.proposal.outbox.retry` | existing_capability | `knowledge.proposal.outbox.retry` |
| Knowledge | `capability:knowledge.proposal.review` | existing_capability | `knowledge.proposal.review` |
| Knowledge | `capability:knowledge.propose` | existing_capability | `knowledge.propose` |
| Knowledge | `agent_tool:find_similar_cases` | existing_capability | `knowledge.search` |
| Knowledge | `capability:knowledge.search` | existing_capability | `knowledge.search` |
| Knowledge | `rest:GET:/api/knowledge_entries` | existing_capability | `knowledge.search` |
| Knowledge | `rest:POST:/api/knowledge_entries/vector-search` | existing_capability | `knowledge.search` |
| Knowledge | `rest:DELETE:/api/knowledge_hub/folders/{gid}` | new_capability | `knowledge.space.change.apply` |
| Knowledge | `rest:PATCH:/api/knowledge_hub/folders/{gid}` | new_capability | `knowledge.space.change.apply` |
| Knowledge | `capability:knowledge.space.create` | existing_capability | `knowledge.space.create` |
| Knowledge | `rest:POST:/api/knowledge_hub/folders` | existing_capability | `knowledge.space.create` |
| Knowledge | `capability:knowledge.space.list` | existing_capability | `knowledge.space.list` |
| Knowledge | `rest:GET:/api/knowledge_hub/folders` | existing_capability | `knowledge.space.list` |
| Knowledge | `capability:knowledge.space.search` | existing_capability | `knowledge.space.search` |
| Local Integration | `agent_tool:open_in_container` | unreviewed | — |
| Local Integration | `rest:DELETE:/api/v1/devices/{device_gid}` | unreviewed | — |
| Local Integration | `rest:GET:/api/v1/devices` | unreviewed | — |
| Local Integration | `rest:POST:/api/v1/devices/enrollments` | unreviewed | — |
| Local Integration | `rest:GET:/api/v1/device-runtime/commands/{command_gid}/artifacts/{artifact_id}` | excluded | — |
| Local Integration | `rest:POST:/api/v1/device-runtime/activate` | excluded | — |
| Local Integration | `rest:POST:/api/v1/device-runtime/commands/lease` | excluded | — |
| Local Integration | `rest:POST:/api/v1/device-runtime/commands/{command_gid}/complete` | excluded | — |
| Local Integration | `rest:POST:/api/v1/device-runtime/heartbeat` | excluded | — |
| Local Integration | `rest:PUT:/api/v1/device-runtime/commands/{command_gid}/result-artifact` | excluded | — |
| Local Integration | `capability:local.command.get` | existing_capability | `local.command.get` |
| Local Integration | `capability:vismockup.capture` | existing_capability | `vismockup.capture` |
| Local Integration | `local_command:vismockup.capture` | existing_capability | `vismockup.capture` |
| Local Integration | `capability:vismockup.highlight` | existing_capability | `vismockup.highlight` |
| Local Integration | `local_command:vismockup.highlight` | existing_capability | `vismockup.highlight` |
| Local Integration | `capability:vismockup.launch` | existing_capability | `vismockup.launch` |
| Local Integration | `local_command:vismockup.launch` | existing_capability | `vismockup.launch` |
| Local Integration | `capability:vismockup.model.open` | existing_capability | `vismockup.model.open` |
| Local Integration | `local_command:vismockup.model.open` | existing_capability | `vismockup.model.open` |
| Local Integration | `capability:vismockup.status` | existing_capability | `vismockup.status` |
| Local Integration | `local_command:vismockup.status` | existing_capability | `vismockup.status` |
| Local Integration | `capability:vismockup.tree` | existing_capability | `vismockup.tree` |
| Local Integration | `local_command:vismockup.tree` | existing_capability | `vismockup.tree` |
| Local Integration | `capability:vismockup.visibility` | existing_capability | `vismockup.visibility` |
| Local Integration | `local_command:vismockup.visibility` | existing_capability | `vismockup.visibility` |
| Ontology | `rest:GET:/api/ontology/db-tables` | excluded | — |
| Ontology | `capability:ontology.change.proposal.create` | existing_capability | `ontology.change.proposal.create` |
| Ontology | `capability:ontology.change.proposal.get` | existing_capability | `ontology.change.proposal.get` |
| Ontology | `capability:ontology.change.proposal.review.submit` | existing_capability | `ontology.change.proposal.review.submit` |
| Ontology | `capability:ontology.change.proposal.search` | existing_capability | `ontology.change.proposal.search` |
| Ontology | `capability:ontology.concept.get` | existing_capability | `ontology.concept.get` |
| Ontology | `rest:GET:/api/ontology/classes/{gid}/axioms` | existing_capability | `ontology.concept.get` |
| Ontology | `rest:GET:/api/ontology/classes/{gid}/full` | existing_capability | `ontology.concept.get` |
| Ontology | `rest:GET:/api/ontology/classes/{gid}/individuals` | existing_capability | `ontology.concept.get` |
| Ontology | `agent_tool:get_ontology_schema` | existing_capability | `ontology.concept.resolve` |
| Ontology | `capability:ontology.concept.resolve` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/agent-schema` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/classes` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/graph` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/node-type-config` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/node-type-suggestions` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/schema/{node_type}` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/unbound-classes` | existing_capability | `ontology.concept.resolve` |
| Ontology | `capability:ontology.mapping.assess` | existing_capability | `ontology.mapping.assess` |
| Ontology | `rest:GET:/api/bop/entries/{entry_gid}/entity-props` | existing_capability | `ontology.mapping.assess` |
| Ontology | `rest:POST:/api/ontology/validate/{entry_gid}` | existing_capability | `ontology.mapping.assess` |
| Ontology | `rest:PATCH:/api/bop/entries/{entry_gid}/entity-props` | new_capability | `ontology.mapping.change.apply` |
| Ontology | `capability:ontology.release.activate` | existing_capability | `ontology.release.activate` |
| Ontology | `capability:ontology.release.diff` | existing_capability | `ontology.release.diff` |
| Ontology | `rest:GET:/api/ontology/schema-diff` | existing_capability | `ontology.release.diff` |
| Ontology | `capability:ontology.release.get` | existing_capability | `ontology.release.get` |
| Ontology | `capability:ontology.release.publish` | existing_capability | `ontology.release.publish` |
| Ontology | `capability:ontology.release.search` | existing_capability | `ontology.release.search` |
| Ontology | `rest:DELETE:/api/ontology/axioms/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/classes/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/properties/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/relations/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:PATCH:/api/ontology/classes/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:PATCH:/api/ontology/properties/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:PATCH:/api/ontology/relations/{gid}` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/axioms` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/classes` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/classes/{gid}/sync-from-table` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/properties` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/relations` | new_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/seed` | new_capability | `ontology.schema.change.apply` |
| Project Management | `rest:GET:/share/issues` | excluded | — |
| Project Management | `agent_tool:list_projects` | existing_capability | `base.project.search` |
| Project Management | `capability:base.project.search` | existing_capability | `base.project.search` |
| Project Management | `rest:GET:/api/projects` | existing_capability | `base.project.search` |
| Project Management | `agent_tool:create_approval_order` | new_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders` | new_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/scope_upgrade` | new_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/{gid}/approve` | new_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/{gid}/start` | new_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/{gid}/withdraw` | new_capability | `project.approval.change.apply` |
| Project Management | `agent_tool:list_approval_orders` | new_capability | `project.approval.read` |
| Project Management | `rest:GET:/api/approval/orders` | new_capability | `project.approval.read` |
| Project Management | `rest:GET:/api/approval/orders/{gid}` | new_capability | `project.approval.read` |
| Project Management | `rest:DELETE:/api/bitable-sync/bindings/{list_gid}` | new_capability | `project.bitable_binding.change.apply` |
| Project Management | `rest:POST:/api/bitable-sync/bindings/{list_gid}` | new_capability | `project.bitable_binding.change.apply` |
| Project Management | `rest:POST:/api/bitable-sync/bindings/{list_gid}/pull` | new_capability | `project.bitable_binding.change.apply` |
| Project Management | `rest:POST:/api/bitable-sync/bindings/{list_gid}/push` | new_capability | `project.bitable_binding.change.apply` |
| Project Management | `rest:POST:/api/bitable-sync/rows/push` | new_capability | `project.bitable_binding.change.apply` |
| Project Management | `rest:PUT:/api/bitable-sync/bindings/{list_gid}` | new_capability | `project.bitable_binding.change.apply` |
| Project Management | `rest:GET:/api/bitable-sync/bindings/{list_gid}` | new_capability | `project.bitable_binding.read` |
| Project Management | `rest:GET:/api/bitable-sync/bindings/{list_gid}/schema` | new_capability | `project.bitable_binding.read` |
| Project Management | `rest:GET:/api/bitable-sync/bindings/{list_gid}/schema-by-token` | new_capability | `project.bitable_binding.read` |
| Project Management | `rest:GET:/api/bitable-sync/bindings/{list_gid}/status` | new_capability | `project.bitable_binding.read` |
| Project Management | `rest:GET:/api/change-logs` | new_capability | `project.change_log.read` |
| Project Management | `rest:POST:/api/collab/sessions` | new_capability | `project.collaboration.change.apply` |
| Project Management | `rest:POST:/api/collab/sessions/{gid}/end` | new_capability | `project.collaboration.change.apply` |
| Project Management | `rest:POST:/api/collab/sessions/{gid}/join` | new_capability | `project.collaboration.change.apply` |
| Project Management | `rest:GET:/api/collab/sessions` | new_capability | `project.collaboration.read` |
| Project Management | `rest:GET:/api/collab/sessions/{gid}` | new_capability | `project.collaboration.read` |
| Project Management | `rest:GET:/api/projects/{gid}/bop-lines` | new_capability | `project.craft_scope.read` |
| Project Management | `rest:DELETE:/api/follows/{gid}` | new_capability | `project.follow.change.apply` |
| Project Management | `rest:PATCH:/api/follows/{gid}` | new_capability | `project.follow.change.apply` |
| Project Management | `rest:POST:/api/follows` | new_capability | `project.follow.change.apply` |
| Project Management | `rest:GET:/api/follows` | new_capability | `project.follow.read` |
| Project Management | `rest:GET:/api/follows/check` | new_capability | `project.follow.read` |
| Project Management | `agent_tool:create_issue` | new_capability | `project.issue.change.apply` |
| Project Management | `agent_tool:update_issue` | new_capability | `project.issue.change.apply` |
| Project Management | `rest:DELETE:/api/issues/{gid}` | new_capability | `project.issue.change.apply` |
| Project Management | `rest:GET:/api/issues/promote` | new_capability | `project.issue.change.apply` |
| Project Management | `rest:PATCH:/api/issues/{gid}` | new_capability | `project.issue.change.apply` |
| Project Management | `rest:POST:/api/issues` | new_capability | `project.issue.change.apply` |
| Project Management | `rest:POST:/api/issues/promote` | new_capability | `project.issue.change.apply` |
| Project Management | `rest:PUT:/api/issues/{gid}` | new_capability | `project.issue.change.apply` |
| Project Management | `agent_tool:get_issue` | new_capability | `project.issue.read` |
| Project Management | `agent_tool:list_issue_lists` | new_capability | `project.issue.read` |
| Project Management | `agent_tool:list_issues` | new_capability | `project.issue.read` |
| Project Management | `rest:GET:/api/issues` | new_capability | `project.issue.read` |
| Project Management | `rest:GET:/api/issues/{gid}` | new_capability | `project.issue.read` |
| Project Management | `rest:DELETE:/api/item-entries/{item_type}/{item_gid}` | new_capability | `project.list.change.apply` |
| Project Management | `rest:DELETE:/api/lists/{gid}` | new_capability | `project.list.change.apply` |
| Project Management | `rest:PATCH:/api/lists/{gid}` | new_capability | `project.list.change.apply` |
| Project Management | `rest:POST:/api/lists` | new_capability | `project.list.change.apply` |
| Project Management | `rest:POST:/api/lists/{gid}/retarget` | new_capability | `project.list.change.apply` |
| Project Management | `rest:PUT:/api/item-entries/{item_type}/{item_gid}` | new_capability | `project.list.change.apply` |
| Project Management | `rest:GET:/api/item-entries/{item_type}/{item_gid}` | new_capability | `project.list.read` |
| Project Management | `rest:GET:/api/lists` | new_capability | `project.list.read` |
| Project Management | `rest:DELETE:/api/projects/{gid}/members/{member_gid}` | new_capability | `project.member.change.apply` |
| Project Management | `rest:POST:/api/projects/{gid}/members` | new_capability | `project.member.change.apply` |
| Project Management | `rest:GET:/api/projects/members/matrix` | new_capability | `project.member.read` |
| Project Management | `rest:GET:/api/projects/{gid}/members` | new_capability | `project.member.read` |
| Project Management | `rest:PATCH:/api/notifications/prefs` | new_capability | `project.notification.change.apply` |
| Project Management | `rest:PATCH:/api/notifications/read_all` | new_capability | `project.notification.change.apply` |
| Project Management | `rest:PATCH:/api/notifications/{gid}/read` | new_capability | `project.notification.change.apply` |
| Project Management | `rest:POST:/api/mentions/notify` | new_capability | `project.notification.change.apply` |
| Project Management | `rest:GET:/api/notifications` | new_capability | `project.notification.read` |
| Project Management | `rest:GET:/api/notifications/prefs` | new_capability | `project.notification.read` |
| Project Management | `rest:GET:/api/notifications/unread_count` | new_capability | `project.notification.read` |
| Project Management | `rest:POST:/api/permission-requests` | new_capability | `project.permission_request.change.apply` |
| Project Management | `rest:POST:/api/permission-requests/{gid}/approve` | new_capability | `project.permission_request.change.apply` |
| Project Management | `rest:POST:/api/permission-requests/{gid}/reject` | new_capability | `project.permission_request.change.apply` |
| Project Management | `rest:GET:/api/permission-requests` | new_capability | `project.permission_request.read` |
| Project Management | `rest:DELETE:/api/projects/vehicle_models/{gid}` | new_capability | `project.project.change.apply` |
| Project Management | `rest:DELETE:/api/projects/{gid}` | new_capability | `project.project.change.apply` |
| Project Management | `rest:PATCH:/api/projects/vehicle_models/{gid}` | new_capability | `project.project.change.apply` |
| Project Management | `rest:PATCH:/api/projects/{gid}` | new_capability | `project.project.change.apply` |
| Project Management | `rest:POST:/api/projects` | new_capability | `project.project.change.apply` |
| Project Management | `rest:POST:/api/projects/vehicle_models` | new_capability | `project.project.change.apply` |
| Project Management | `rest:PUT:/api/projects/{gid}/line-assignment` | new_capability | `project.project.change.apply` |
| Project Management | `rest:GET:/api/projects/vehicle_models` | new_capability | `project.project.read` |
| Project Management | `rest:GET:/api/projects/{gid}` | new_capability | `project.project.read` |
| Project Management | `rest:DELETE:/api/share-links/{token}` | new_capability | `project.sharing.change.apply` |
| Project Management | `rest:DELETE:/api/shares/items/{gid}` | new_capability | `project.sharing.change.apply` |
| Project Management | `rest:DELETE:/api/shares/lists/{list_gid}/{gid}` | new_capability | `project.sharing.change.apply` |
| Project Management | `rest:POST:/api/share-links` | new_capability | `project.sharing.change.apply` |
| Project Management | `rest:POST:/api/shares/items` | new_capability | `project.sharing.change.apply` |
| Project Management | `rest:POST:/api/shares/lists/{list_gid}` | new_capability | `project.sharing.change.apply` |
| Project Management | `rest:GET:/api/share-links/{token}` | new_capability | `project.sharing.read` |
| Project Management | `rest:GET:/api/shares/lists/{list_gid}` | new_capability | `project.sharing.read` |
| Project Management | `agent_tool:add_task_progress_log` | new_capability | `project.task.change.apply` |
| Project Management | `agent_tool:create_task` | new_capability | `project.task.change.apply` |
| Project Management | `agent_tool:update_task` | new_capability | `project.task.change.apply` |
| Project Management | `rest:DELETE:/api/task-dependencies/{gid}` | new_capability | `project.task.change.apply` |
| Project Management | `rest:DELETE:/api/tasks/{gid}` | new_capability | `project.task.change.apply` |
| Project Management | `rest:GET:/api/tasks/promote` | new_capability | `project.task.change.apply` |
| Project Management | `rest:PATCH:/api/tasks/{gid}` | new_capability | `project.task.change.apply` |
| Project Management | `rest:POST:/api/task-dependencies` | new_capability | `project.task.change.apply` |
| Project Management | `rest:POST:/api/tasks` | new_capability | `project.task.change.apply` |
| Project Management | `rest:POST:/api/tasks/promote` | new_capability | `project.task.change.apply` |
| Project Management | `rest:PUT:/api/task-dependencies/{gid}` | new_capability | `project.task.change.apply` |
| Project Management | `rest:PUT:/api/tasks/{gid}` | new_capability | `project.task.change.apply` |
| Project Management | `agent_tool:get_task` | new_capability | `project.task.read` |
| Project Management | `agent_tool:list_task_lists` | new_capability | `project.task.read` |
| Project Management | `agent_tool:list_tasks` | new_capability | `project.task.read` |
| Project Management | `rest:GET:/api/task-dependencies` | new_capability | `project.task.read` |
| Project Management | `rest:GET:/api/tasks` | new_capability | `project.task.read` |
| Project Management | `rest:GET:/api/tasks/{gid}` | new_capability | `project.task.read` |
| Project Management | `rest:DELETE:/api/task-templates/items/{item_gid}` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:DELETE:/api/task-templates/{gid}` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:PATCH:/api/task-templates/items/{item_gid}` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:PATCH:/api/task-templates/{gid}` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:POST:/api/task-templates` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:POST:/api/task-templates/{gid}/instantiate` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:POST:/api/task-templates/{template_gid}/items` | new_capability | `project.task_template.change.apply` |
| Project Management | `rest:GET:/api/task-templates` | new_capability | `project.task_template.read` |
| Project Management | `rest:GET:/api/task-templates/{gid}` | new_capability | `project.task_template.read` |
| Project Management | `rest:DELETE:/api/workbenches/{gid}` | new_capability | `project.workbench.change.apply` |
| Project Management | `rest:DELETE:/api/workbenches/{gid}/override` | new_capability | `project.workbench.change.apply` |
| Project Management | `rest:PATCH:/api/workbenches/{gid}` | new_capability | `project.workbench.change.apply` |
| Project Management | `rest:POST:/api/workbenches` | new_capability | `project.workbench.change.apply` |
| Project Management | `rest:PUT:/api/workbenches/{gid}/override` | new_capability | `project.workbench.change.apply` |
| Project Management | `rest:GET:/api/workbench/home` | new_capability | `project.workbench.read` |
| Project Management | `rest:GET:/api/workbench/panel1` | new_capability | `project.workbench.read` |
| Project Management | `rest:GET:/api/workbenches` | new_capability | `project.workbench.read` |
| Project Management | `rest:GET:/api/workbenches/{gid}/override` | new_capability | `project.workbench.read` |
| Simulation | `capability:simulation.environment.create` | existing_capability | `simulation.environment.create` |
| Simulation | `rest:POST:/api/simulation/environments` | existing_capability | `simulation.environment.create` |
| Simulation | `capability:simulation.environment.get` | existing_capability | `simulation.environment.get` |
| Simulation | `rest:GET:/api/simulation/environments/{environment_gid}` | existing_capability | `simulation.environment.get` |
| Simulation | `capability:simulation.environment.list` | existing_capability | `simulation.environment.list` |
| Simulation | `rest:GET:/api/simulation/environments` | existing_capability | `simulation.environment.list` |
| Simulation | `capability:simulation.parameter_set.create` | existing_capability | `simulation.parameter_set.create` |
| Simulation | `capability:simulation.parameter_set.get` | existing_capability | `simulation.parameter_set.get` |
| Simulation | `capability:simulation.profile.create` | existing_capability | `simulation.profile.create` |
| Simulation | `capability:simulation.profile.get` | existing_capability | `simulation.profile.get` |
| Simulation | `capability:simulation.result.get` | existing_capability | `simulation.result.get` |
| Simulation | `capability:simulation.run.get` | existing_capability | `simulation.run.get` |
| Simulation | `capability:simulation.run.start` | existing_capability | `simulation.run.start` |
