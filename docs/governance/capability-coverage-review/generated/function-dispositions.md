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
| Agent | `agent_tool:audit_entry_rules` | unreviewed | — |
| Agent | `agent_tool:calculate` | unreviewed | — |
| Agent | `agent_tool:check_rules` | unreviewed | — |
| Agent | `agent_tool:create_discussion_topic` | unreviewed | — |
| Agent | `agent_tool:find_similar_cases` | unreviewed | — |
| Agent | `agent_tool:flag_for_review` | unreviewed | — |
| Agent | `agent_tool:generate_canvas` | unreviewed | — |
| Agent | `agent_tool:get_canvas_state` | unreviewed | — |
| Agent | `agent_tool:get_entry_relations` | unreviewed | — |
| Agent | `agent_tool:get_selected_elements` | unreviewed | — |
| Agent | `agent_tool:global_search` | unreviewed | — |
| Agent | `agent_tool:list_memories` | unreviewed | — |
| Agent | `agent_tool:list_preferences` | unreviewed | — |
| Agent | `agent_tool:list_rules` | unreviewed | — |
| Agent | `agent_tool:open_in_container` | unreviewed | — |
| Agent | `agent_tool:recall_memory` | unreviewed | — |
| Agent | `agent_tool:recommend_practice` | unreviewed | — |
| Agent | `agent_tool:run_skill_canvas` | unreviewed | — |
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
| Base Platform | `rest:DELETE:/admin/config/{key}` | unreviewed | — |
| Base Platform | `rest:DELETE:/api/ext-datasources/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/api/ext-mappings/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/api/follows/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/api/grants/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/api/self_ann/{item_gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/api/views/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/teams/{gid}` | unreviewed | — |
| Base Platform | `rest:DELETE:/teams/{gid}/members/{user_gid}` | unreviewed | — |
| Base Platform | `rest:GET:/` | unreviewed | — |
| Base Platform | `rest:GET:/admin/cloud-db-config` | unreviewed | — |
| Base Platform | `rest:GET:/admin/config` | unreviewed | — |
| Base Platform | `rest:GET:/admin/config/{key}` | unreviewed | — |
| Base Platform | `rest:GET:/admin/debug-logs` | unreviewed | — |
| Base Platform | `rest:GET:/admin/plugin-registry` | unreviewed | — |
| Base Platform | `rest:GET:/api/annotations/{key}` | unreviewed | — |
| Base Platform | `rest:GET:/api/deploy` | unreviewed | — |
| Base Platform | `rest:GET:/api/deploy/current` | unreviewed | — |
| Base Platform | `rest:GET:/api/deploy/history` | unreviewed | — |
| Base Platform | `rest:GET:/api/deploy/pipeline` | unreviewed | — |
| Base Platform | `rest:GET:/api/ext-datasources` | unreviewed | — |
| Base Platform | `rest:GET:/api/ext-datasources/{gid}/tables` | unreviewed | — |
| Base Platform | `rest:GET:/api/ext-field-mappings` | unreviewed | — |
| Base Platform | `rest:GET:/api/ext-mappings` | unreviewed | — |
| Base Platform | `rest:GET:/api/ext-mappings/{gid}/columns` | unreviewed | — |
| Base Platform | `rest:GET:/api/ext-mappings/{gid}/preview` | unreviewed | — |
| Base Platform | `rest:GET:/api/feishu/im/contact-messages` | unreviewed | — |
| Base Platform | `rest:GET:/api/feishu/im/mentions` | unreviewed | — |
| Base Platform | `rest:GET:/api/file-store/config` | unreviewed | — |
| Base Platform | `rest:GET:/api/follows` | unreviewed | — |
| Base Platform | `rest:GET:/api/follows/check` | unreviewed | — |
| Base Platform | `rest:GET:/api/grants` | unreviewed | — |
| Base Platform | `rest:GET:/api/grants/me` | unreviewed | — |
| Base Platform | `rest:GET:/api/notifications` | unreviewed | — |
| Base Platform | `rest:GET:/api/notifications/prefs` | unreviewed | — |
| Base Platform | `rest:GET:/api/notifications/unread_count` | unreviewed | — |
| Base Platform | `rest:GET:/api/plugin/list` | unreviewed | — |
| Base Platform | `rest:GET:/api/self_ann/batch` | unreviewed | — |
| Base Platform | `rest:GET:/api/self_ann/list` | unreviewed | — |
| Base Platform | `rest:GET:/api/self_ann/{item_gid}` | unreviewed | — |
| Base Platform | `rest:GET:/api/users/` | unreviewed | — |
| Base Platform | `rest:GET:/api/users/me` | unreviewed | — |
| Base Platform | `rest:GET:/api/users/search` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/assets/{token}/{plugin_id}/{version}/{asset_path:path}` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/catalog` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/installations` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/installations/{plugin_id}/events` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/registry` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/releases` | unreviewed | — |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/usage/months/{month}` | unreviewed | — |
| Base Platform | `rest:GET:/api/v2/agent-capabilities/catalog` | unreviewed | — |
| Base Platform | `rest:GET:/api/v2/agent-capabilities/catalog-preview` | unreviewed | — |
| Base Platform | `rest:GET:/api/v2/capability-artifacts/{artifact_id}` | unreviewed | — |
| Base Platform | `rest:GET:/api/v2/capability-operations/{operation_id}` | unreviewed | — |
| Base Platform | `rest:GET:/api/views` | unreviewed | — |
| Base Platform | `rest:GET:/auth/feishu/callback` | unreviewed | — |
| Base Platform | `rest:GET:/auth/feishu/login-url` | unreviewed | — |
| Base Platform | `rest:GET:/auth/feishu/poll/{state}` | unreviewed | — |
| Base Platform | `rest:GET:/auth/me` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/cache/debug` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/calendar/events/{event_id}` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/calendar/today` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/org/dept-search` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/org/users` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/org/users/search` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/search/chats` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/search/docs` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/search/events` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/search/meetings` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/search/users` | unreviewed | — |
| Base Platform | `rest:GET:/feishu/sync/org/status` | unreviewed | — |
| Base Platform | `rest:GET:/health` | unreviewed | — |
| Base Platform | `rest:GET:/ready` | unreviewed | — |
| Base Platform | `rest:GET:/share/issues` | unreviewed | — |
| Base Platform | `rest:GET:/teams` | unreviewed | — |
| Base Platform | `rest:GET:/teams/{gid}/members` | unreviewed | — |
| Base Platform | `rest:GET:/users/` | unreviewed | — |
| Base Platform | `rest:GET:/users/me` | unreviewed | — |
| Base Platform | `rest:GET:/{capability_id}` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/ext-datasources/{gid}` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/ext-mappings/{gid}` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/follows/{gid}` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/notifications/prefs` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/notifications/read_all` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/notifications/{gid}/read` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/users/{user_gid}/role` | unreviewed | — |
| Base Platform | `rest:PATCH:/api/views/{gid}` | unreviewed | — |
| Base Platform | `rest:PATCH:/feishu/calendar/events/{event_id}` | unreviewed | — |
| Base Platform | `rest:PATCH:/feishu/calendar/events/{event_id}/rsvp` | unreviewed | — |
| Base Platform | `rest:PATCH:/teams/{gid}` | unreviewed | — |
| Base Platform | `rest:PATCH:/teams/{gid}/config` | unreviewed | — |
| Base Platform | `rest:POST:/admin/cloud-db-config` | unreviewed | — |
| Base Platform | `rest:POST:/admin/cloud-db-config/test` | unreviewed | — |
| Base Platform | `rest:POST:/admin/config/reload` | unreviewed | — |
| Base Platform | `rest:POST:/admin/server-restart` | unreviewed | — |
| Base Platform | `rest:POST:/api/deploy/rollback` | unreviewed | — |
| Base Platform | `rest:POST:/api/ext-datasources` | unreviewed | — |
| Base Platform | `rest:POST:/api/ext-datasources/{gid}/test` | unreviewed | — |
| Base Platform | `rest:POST:/api/ext-mappings` | unreviewed | — |
| Base Platform | `rest:POST:/api/ext-mappings/{gid}/import` | unreviewed | — |
| Base Platform | `rest:POST:/api/feishu/doc/read` | unreviewed | — |
| Base Platform | `rest:POST:/api/feishu/doc/write-cells` | unreviewed | — |
| Base Platform | `rest:POST:/api/file-store/config` | unreviewed | — |
| Base Platform | `rest:POST:/api/file-store/ois-config` | unreviewed | — |
| Base Platform | `rest:POST:/api/file-store/ois-test` | unreviewed | — |
| Base Platform | `rest:POST:/api/file-store/test` | unreviewed | — |
| Base Platform | `rest:POST:/api/follows` | unreviewed | — |
| Base Platform | `rest:POST:/api/grants` | unreviewed | — |
| Base Platform | `rest:POST:/api/mentions/notify` | unreviewed | — |
| Base Platform | `rest:POST:/api/org/sync-from-feishu` | unreviewed | — |
| Base Platform | `rest:POST:/api/uploads` | unreviewed | — |
| Base Platform | `rest:POST:/api/uploads/ois/resolve` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/mounts/{mount_session_id}/capabilities/{capability_id}:confirm` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/mounts/{mount_session_id}/capabilities/{capability_id}:invoke` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/publishers` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases/{plugin_id}/{version}/review` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases/{plugin_id}/{version}/revoke` | unreviewed | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/usage/months/{month}/close` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/agent-capabilities/delegations` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/agent-capabilities/{capability_id}:confirm` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/agent-capabilities/{capability_id}:invoke` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/capability-artifacts/uploads` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/capability-artifacts/uploads/{upload_id}:finalize` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/mcp-capabilities/delegations` | unreviewed | — |
| Base Platform | `rest:POST:/api/v2/mcp-capabilities/{capability_id}:invoke` | unreviewed | — |
| Base Platform | `rest:POST:/api/views` | unreviewed | — |
| Base Platform | `rest:POST:/api/views/{gid}/copy` | unreviewed | — |
| Base Platform | `rest:POST:/auth/logout` | unreviewed | — |
| Base Platform | `rest:POST:/auth/refresh` | unreviewed | — |
| Base Platform | `rest:POST:/feishu/cache/refresh` | unreviewed | — |
| Base Platform | `rest:POST:/feishu/chat-message/share-list` | unreviewed | — |
| Base Platform | `rest:POST:/feishu/message/send` | unreviewed | — |
| Base Platform | `rest:POST:/feishu/sync/org` | unreviewed | — |
| Base Platform | `rest:POST:/feishu/sync/org/structure` | unreviewed | — |
| Base Platform | `rest:POST:/feishu/webhook/bitable` | unreviewed | — |
| Base Platform | `rest:POST:/teams` | unreviewed | — |
| Base Platform | `rest:POST:/teams/{gid}/members` | unreviewed | — |
| Base Platform | `rest:POST:/{capability_id}:confirm` | unreviewed | — |
| Base Platform | `rest:POST:/{capability_id}:invoke` | unreviewed | — |
| Base Platform | `rest:PUT:/admin/config/{key}` | unreviewed | — |
| Base Platform | `rest:PUT:/api/annotations/{key}` | unreviewed | — |
| Base Platform | `rest:PUT:/api/ext-field-mappings/batch` | unreviewed | — |
| Base Platform | `rest:PUT:/api/self_ann/{item_gid}` | unreviewed | — |
| Base Platform | `rest:PUT:/api/uploads/{filename}` | unreviewed | — |
| Base Platform | `rest:PUT:/api/v2/capability-artifacts/uploads/{upload_id}/content` | unreviewed | — |
| Base Platform | `capability:identity.principal.search` | existing_capability | `identity.principal.search` |
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
| Base Platform | `capability:system.search` | existing_capability | `system.search` |
| Base Platform | `capability:system.worker.outbox.health` | existing_capability | `system.worker.outbox.health` |
| Craft | `rest:DELETE:/api/bitable-sync/bindings/{list_gid}` | unreviewed | — |
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
| Craft | `rest:DELETE:/api/issues/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/item-entries/{item_type}/{item_gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/lists/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/projects/vehicle_models/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/projects/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/projects/{gid}/members/{member_gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/rules/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/share-links/{token}` | unreviewed | — |
| Craft | `rest:DELETE:/api/shares/items/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/shares/lists/{list_gid}/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/std_op/operations/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/task-dependencies/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/task-templates/items/{item_gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/task-templates/{gid}` | unreviewed | — |
| Craft | `rest:DELETE:/api/tasks/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/approval/orders` | unreviewed | — |
| Craft | `rest:GET:/api/approval/orders/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bitable-sync/bindings/{list_gid}` | unreviewed | — |
| Craft | `rest:GET:/api/bitable-sync/bindings/{list_gid}/schema` | unreviewed | — |
| Craft | `rest:GET:/api/bitable-sync/bindings/{list_gid}/schema-by-token` | unreviewed | — |
| Craft | `rest:GET:/api/bitable-sync/bindings/{list_gid}/status` | unreviewed | — |
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
| Craft | `rest:GET:/api/change-logs` | unreviewed | — |
| Craft | `rest:GET:/api/collab/sessions` | unreviewed | — |
| Craft | `rest:GET:/api/collab/sessions/{gid}` | unreviewed | — |
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
| Craft | `rest:GET:/api/issues` | unreviewed | — |
| Craft | `rest:GET:/api/issues/promote` | unreviewed | — |
| Craft | `rest:GET:/api/issues/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/item-entries/{item_type}/{item_gid}` | unreviewed | — |
| Craft | `rest:GET:/api/lists` | unreviewed | — |
| Craft | `rest:GET:/api/permission-requests` | unreviewed | — |
| Craft | `rest:GET:/api/projects` | unreviewed | — |
| Craft | `rest:GET:/api/projects/members/matrix` | unreviewed | — |
| Craft | `rest:GET:/api/projects/vehicle_models` | unreviewed | — |
| Craft | `rest:GET:/api/projects/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/projects/{gid}/bop-lines` | unreviewed | — |
| Craft | `rest:GET:/api/projects/{gid}/members` | unreviewed | — |
| Craft | `rest:GET:/api/rules` | unreviewed | — |
| Craft | `rest:GET:/api/rules/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/share-links/{token}` | unreviewed | — |
| Craft | `rest:GET:/api/shares/lists/{list_gid}` | unreviewed | — |
| Craft | `rest:GET:/api/std_op/operations` | unreviewed | — |
| Craft | `rest:GET:/api/std_op/operations/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/task-dependencies` | unreviewed | — |
| Craft | `rest:GET:/api/task-templates` | unreviewed | — |
| Craft | `rest:GET:/api/task-templates/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/tasks` | unreviewed | — |
| Craft | `rest:GET:/api/tasks/promote` | unreviewed | — |
| Craft | `rest:GET:/api/tasks/{gid}` | unreviewed | — |
| Craft | `rest:GET:/api/vpps-operations` | unreviewed | — |
| Craft | `rest:GET:/api/vpps-operations/rule4-ignores` | unreviewed | — |
| Craft | `rest:GET:/api/workbench/home` | unreviewed | — |
| Craft | `rest:GET:/api/workbench/panel1` | unreviewed | — |
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
| Craft | `rest:PATCH:/api/issues/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/lists/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/projects/vehicle_models/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/projects/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/rules/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/std_op/operations/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/task-templates/items/{item_gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/task-templates/{gid}` | unreviewed | — |
| Craft | `rest:PATCH:/api/tasks/{gid}` | unreviewed | — |
| Craft | `rest:POST:/api/approval/orders` | unreviewed | — |
| Craft | `rest:POST:/api/approval/orders/scope_upgrade` | unreviewed | — |
| Craft | `rest:POST:/api/approval/orders/{gid}/approve` | unreviewed | — |
| Craft | `rest:POST:/api/approval/orders/{gid}/start` | unreviewed | — |
| Craft | `rest:POST:/api/approval/orders/{gid}/withdraw` | unreviewed | — |
| Craft | `rest:POST:/api/bitable-sync/bindings/{list_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/bitable-sync/bindings/{list_gid}/pull` | unreviewed | — |
| Craft | `rest:POST:/api/bitable-sync/bindings/{list_gid}/push` | unreviewed | — |
| Craft | `rest:POST:/api/bitable-sync/rows/push` | unreviewed | — |
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
| Craft | `rest:POST:/api/collab/sessions` | unreviewed | — |
| Craft | `rest:POST:/api/collab/sessions/{gid}/end` | unreviewed | — |
| Craft | `rest:POST:/api/collab/sessions/{gid}/join` | unreviewed | — |
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
| Craft | `rest:POST:/api/issues` | unreviewed | — |
| Craft | `rest:POST:/api/issues/promote` | unreviewed | — |
| Craft | `rest:POST:/api/lists` | unreviewed | — |
| Craft | `rest:POST:/api/lists/{gid}/retarget` | unreviewed | — |
| Craft | `rest:POST:/api/permission-requests` | unreviewed | — |
| Craft | `rest:POST:/api/permission-requests/{gid}/approve` | unreviewed | — |
| Craft | `rest:POST:/api/permission-requests/{gid}/reject` | unreviewed | — |
| Craft | `rest:POST:/api/projects` | unreviewed | — |
| Craft | `rest:POST:/api/projects/vehicle_models` | unreviewed | — |
| Craft | `rest:POST:/api/projects/{gid}/members` | unreviewed | — |
| Craft | `rest:POST:/api/rule-engine/audit/bop-version/{version_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/rule-engine/check` | unreviewed | — |
| Craft | `rest:POST:/api/rules` | unreviewed | — |
| Craft | `rest:POST:/api/share-links` | unreviewed | — |
| Craft | `rest:POST:/api/shares/items` | unreviewed | — |
| Craft | `rest:POST:/api/shares/lists/{list_gid}` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations/{gid}/clone-to-post` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations/{gid}/deprecate` | unreviewed | — |
| Craft | `rest:POST:/api/std_op/operations/{gid}/publish` | unreviewed | — |
| Craft | `rest:POST:/api/task-dependencies` | unreviewed | — |
| Craft | `rest:POST:/api/task-templates` | unreviewed | — |
| Craft | `rest:POST:/api/task-templates/{gid}/instantiate` | unreviewed | — |
| Craft | `rest:POST:/api/task-templates/{template_gid}/items` | unreviewed | — |
| Craft | `rest:POST:/api/tasks` | unreviewed | — |
| Craft | `rest:POST:/api/tasks/promote` | unreviewed | — |
| Craft | `rest:POST:/api/vpps-operations/rule4-bulk-ignore` | unreviewed | — |
| Craft | `rest:POST:/api/vpps-operations/{gid}/revert` | unreviewed | — |
| Craft | `rest:PUT:/api/bitable-sync/bindings/{list_gid}` | unreviewed | — |
| Craft | `rest:PUT:/api/bop/versions/{gid}/layout-config` | unreviewed | — |
| Craft | `rest:PUT:/api/issues/{gid}` | unreviewed | — |
| Craft | `rest:PUT:/api/item-entries/{item_type}/{item_gid}` | unreviewed | — |
| Craft | `rest:PUT:/api/projects/{gid}/line-assignment` | unreviewed | — |
| Craft | `rest:PUT:/api/task-dependencies/{gid}` | unreviewed | — |
| Craft | `rest:PUT:/api/tasks/{gid}` | unreviewed | — |
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
| Knowledge | `agent_tool:get_knowledge_document` | unreviewed | — |
| Knowledge | `agent_tool:get_knowledge_entry` | unreviewed | — |
| Knowledge | `rest:DELETE:/api/knowledge_entries/{gid}` | unreviewed | — |
| Knowledge | `rest:DELETE:/api/knowledge_hub/folders/{gid}` | unreviewed | — |
| Knowledge | `rest:DELETE:/api/knowledge_hub/items/{gid}` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_entries` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_entries/{gid}` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_hub/favorites` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_hub/folders` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_hub/items/{gid}` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_hub/items/{gid}/history` | unreviewed | — |
| Knowledge | `rest:GET:/api/knowledge_hub/recent` | unreviewed | — |
| Knowledge | `rest:PATCH:/api/knowledge_entries/{gid}` | unreviewed | — |
| Knowledge | `rest:PATCH:/api/knowledge_hub/folders/{gid}` | unreviewed | — |
| Knowledge | `rest:PATCH:/api/knowledge_hub/items/{gid}` | unreviewed | — |
| Knowledge | `rest:POST:/api/knowledge_entries` | unreviewed | — |
| Knowledge | `rest:POST:/api/knowledge_entries/vector-search` | unreviewed | — |
| Knowledge | `rest:POST:/api/knowledge_hub/folders` | unreviewed | — |
| Knowledge | `rest:POST:/api/knowledge_hub/items` | unreviewed | — |
| Knowledge | `rest:POST:/api/knowledge_hub/items/{gid}/favorite` | unreviewed | — |
| Knowledge | `rest:POST:/api/knowledge_hub/items/{gid}/recent` | unreviewed | — |
| Knowledge | `agent_tool:search_knowledge` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `capability:knowledge.context.retrieve` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `rest:GET:/api/knowledge_hub/items` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `capability:knowledge.document.acl.grant` | existing_capability | `knowledge.document.acl.grant` |
| Knowledge | `capability:knowledge.document.acl.list` | existing_capability | `knowledge.document.acl.list` |
| Knowledge | `capability:knowledge.document.acl.revoke` | existing_capability | `knowledge.document.acl.revoke` |
| Knowledge | `capability:knowledge.document.create` | existing_capability | `knowledge.document.create` |
| Knowledge | `capability:knowledge.document.diff` | existing_capability | `knowledge.document.diff` |
| Knowledge | `capability:knowledge.document.get` | existing_capability | `knowledge.document.get` |
| Knowledge | `capability:knowledge.document.history.get` | existing_capability | `knowledge.document.history.get` |
| Knowledge | `capability:knowledge.document.restore` | existing_capability | `knowledge.document.restore` |
| Knowledge | `capability:knowledge.document.revise` | existing_capability | `knowledge.document.revise` |
| Knowledge | `capability:knowledge.document.revisions` | existing_capability | `knowledge.document.revisions` |
| Knowledge | `capability:knowledge.document.rollback` | existing_capability | `knowledge.document.rollback` |
| Knowledge | `capability:knowledge.document.search` | existing_capability | `knowledge.document.search` |
| Knowledge | `capability:knowledge.get` | existing_capability | `knowledge.get` |
| Knowledge | `capability:knowledge.migration.status` | existing_capability | `knowledge.migration.status` |
| Knowledge | `capability:knowledge.proposal.get` | existing_capability | `knowledge.proposal.get` |
| Knowledge | `capability:knowledge.proposal.list` | existing_capability | `knowledge.proposal.list` |
| Knowledge | `capability:knowledge.proposal.outbox.list` | existing_capability | `knowledge.proposal.outbox.list` |
| Knowledge | `capability:knowledge.proposal.outbox.retry` | existing_capability | `knowledge.proposal.outbox.retry` |
| Knowledge | `capability:knowledge.proposal.review` | existing_capability | `knowledge.proposal.review` |
| Knowledge | `capability:knowledge.propose` | existing_capability | `knowledge.propose` |
| Knowledge | `capability:knowledge.search` | existing_capability | `knowledge.search` |
| Knowledge | `capability:knowledge.space.create` | existing_capability | `knowledge.space.create` |
| Knowledge | `capability:knowledge.space.list` | existing_capability | `knowledge.space.list` |
| Knowledge | `capability:knowledge.space.search` | existing_capability | `knowledge.space.search` |
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
| Ontology | `rest:DELETE:/api/ontology/axioms/{gid}` | unreviewed | — |
| Ontology | `rest:DELETE:/api/ontology/classes/{gid}` | unreviewed | — |
| Ontology | `rest:DELETE:/api/ontology/properties/{gid}` | unreviewed | — |
| Ontology | `rest:DELETE:/api/ontology/relations/{gid}` | unreviewed | — |
| Ontology | `rest:GET:/api/bop/entries/{entry_gid}/entity-props` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/agent-schema` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/classes` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/classes/{gid}/axioms` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/classes/{gid}/full` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/classes/{gid}/individuals` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/db-tables` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/graph` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/node-type-config` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/node-type-suggestions` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/schema-diff` | unreviewed | — |
| Ontology | `rest:GET:/api/ontology/unbound-classes` | unreviewed | — |
| Ontology | `rest:PATCH:/api/bop/entries/{entry_gid}/entity-props` | unreviewed | — |
| Ontology | `rest:PATCH:/api/ontology/classes/{gid}` | unreviewed | — |
| Ontology | `rest:PATCH:/api/ontology/properties/{gid}` | unreviewed | — |
| Ontology | `rest:PATCH:/api/ontology/relations/{gid}` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/axioms` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/classes` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/classes/{gid}/sync-from-table` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/properties` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/relations` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/seed` | unreviewed | — |
| Ontology | `rest:POST:/api/ontology/validate/{entry_gid}` | unreviewed | — |
| Ontology | `capability:ontology.change.proposal.create` | existing_capability | `ontology.change.proposal.create` |
| Ontology | `capability:ontology.change.proposal.get` | existing_capability | `ontology.change.proposal.get` |
| Ontology | `capability:ontology.change.proposal.review.submit` | existing_capability | `ontology.change.proposal.review.submit` |
| Ontology | `capability:ontology.change.proposal.search` | existing_capability | `ontology.change.proposal.search` |
| Ontology | `capability:ontology.concept.get` | existing_capability | `ontology.concept.get` |
| Ontology | `agent_tool:get_ontology_schema` | existing_capability | `ontology.concept.resolve` |
| Ontology | `capability:ontology.concept.resolve` | existing_capability | `ontology.concept.resolve` |
| Ontology | `rest:GET:/api/ontology/schema/{node_type}` | existing_capability | `ontology.concept.resolve` |
| Ontology | `capability:ontology.mapping.assess` | existing_capability | `ontology.mapping.assess` |
| Ontology | `capability:ontology.release.activate` | existing_capability | `ontology.release.activate` |
| Ontology | `capability:ontology.release.diff` | existing_capability | `ontology.release.diff` |
| Ontology | `capability:ontology.release.get` | existing_capability | `ontology.release.get` |
| Ontology | `capability:ontology.release.publish` | existing_capability | `ontology.release.publish` |
| Ontology | `capability:ontology.release.search` | existing_capability | `ontology.release.search` |
| Project Management | `agent_tool:add_task_progress_log` | unreviewed | — |
| Project Management | `agent_tool:create_approval_order` | unreviewed | — |
| Project Management | `agent_tool:create_issue` | unreviewed | — |
| Project Management | `agent_tool:create_task` | unreviewed | — |
| Project Management | `agent_tool:get_issue` | unreviewed | — |
| Project Management | `agent_tool:get_task` | unreviewed | — |
| Project Management | `agent_tool:list_approval_orders` | unreviewed | — |
| Project Management | `agent_tool:list_issue_lists` | unreviewed | — |
| Project Management | `agent_tool:list_issues` | unreviewed | — |
| Project Management | `agent_tool:list_projects` | unreviewed | — |
| Project Management | `agent_tool:list_task_lists` | unreviewed | — |
| Project Management | `agent_tool:list_tasks` | unreviewed | — |
| Project Management | `agent_tool:search` | unreviewed | — |
| Project Management | `agent_tool:update_issue` | unreviewed | — |
| Project Management | `agent_tool:update_task` | unreviewed | — |
| Project Management | `rest:DELETE:/api/workbenches/{gid}` | unreviewed | — |
| Project Management | `rest:DELETE:/api/workbenches/{gid}/override` | unreviewed | — |
| Project Management | `rest:GET:/api/workbenches` | unreviewed | — |
| Project Management | `rest:GET:/api/workbenches/{gid}/override` | unreviewed | — |
| Project Management | `rest:PATCH:/api/workbenches/{gid}` | unreviewed | — |
| Project Management | `rest:POST:/api/workbenches` | unreviewed | — |
| Project Management | `rest:PUT:/api/workbenches/{gid}/override` | unreviewed | — |
| Project Management | `capability:base.project.search` | existing_capability | `base.project.search` |
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
