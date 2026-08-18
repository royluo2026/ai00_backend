# Function dispositions

| Domain | Function | Resolution | Capability |
|---|---|---|---|

| Agent | `agent_runtime:GET:/health` | excluded | — |
| Agent | `agent_runtime:GET:/v1/tools` | excluded | — |
| Agent | `agent_tool:calculate` | excluded | — |
| Agent | `rest:GET:/api/ai/admin-config` | excluded | — |
| Agent | `rest:GET:/api/ai/tools` | excluded | — |
| Agent | `rest:GET:/api/flows/capability-manifest` | excluded | — |
| Agent | `rest:POST:/api/ai/admin-config` | excluded | — |
| Agent | `rest:POST:/api/ai/test-connection` | excluded | — |
| Agent | `rest:POST:/api/skills/seed-system` | excluded | — |
| Agent | `capability:agent.audit.read` | existing_capability | `agent.audit.read` |
| Agent | `rest:GET:/api/ai/audit-logs` | existing_capability | `agent.audit.read` |
| Agent | `rest:GET:/api/ai/balance` | existing_capability | `agent.audit.read` |
| Agent | `capability:agent.audit.record` | existing_capability | `agent.audit.record` |
| Agent | `rest:POST:/api/ai/audit` | existing_capability | `agent.audit.record` |
| Agent | `capability:agent.flow.change.apply` | existing_capability | `agent.flow.change.apply` |
| Agent | `rest:DELETE:/api/flows/{gid}` | existing_capability | `agent.flow.change.apply` |
| Agent | `rest:POST:/api/flows` | existing_capability | `agent.flow.change.apply` |
| Agent | `rest:POST:/api/flows/gen-script` | existing_capability | `agent.flow.change.apply` |
| Agent | `rest:POST:/api/flows/runs/{run_gid}/step` | existing_capability | `agent.flow.change.apply` |
| Agent | `rest:POST:/api/flows/{gid}/run` | existing_capability | `agent.flow.change.apply` |
| Agent | `rest:PUT:/api/flows/{gid}` | existing_capability | `agent.flow.change.apply` |
| Agent | `capability:agent.flow.read` | existing_capability | `agent.flow.read` |
| Agent | `rest:GET:/api/flows` | existing_capability | `agent.flow.read` |
| Agent | `rest:GET:/api/flows/runs` | existing_capability | `agent.flow.read` |
| Agent | `rest:GET:/api/flows/runs/{run_gid}` | existing_capability | `agent.flow.read` |
| Agent | `rest:GET:/api/flows/{gid}` | existing_capability | `agent.flow.read` |
| Agent | `agent_tool:ask_for_clarification` | existing_capability | `agent.interaction.request` |
| Agent | `agent_tool:create_discussion_topic` | existing_capability | `agent.interaction.request` |
| Agent | `agent_tool:flag_for_review` | existing_capability | `agent.interaction.request` |
| Agent | `capability:agent.interaction.request` | existing_capability | `agent.interaction.request` |
| Agent | `agent_tool:save_memory` | existing_capability | `agent.memory.change.apply` |
| Agent | `agent_tool:save_preference` | existing_capability | `agent.memory.change.apply` |
| Agent | `capability:agent.memory.change.apply` | existing_capability | `agent.memory.change.apply` |
| Agent | `agent_tool:list_memories` | existing_capability | `agent.memory.read` |
| Agent | `agent_tool:list_preferences` | existing_capability | `agent.memory.read` |
| Agent | `agent_tool:recall_memory` | existing_capability | `agent.memory.read` |
| Agent | `capability:agent.memory.read` | existing_capability | `agent.memory.read` |
| Agent | `agent_runtime:POST:/v1/runs` | existing_capability | `agent.run.change.apply` |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/(pause|resume|cancel)` | existing_capability | `agent.run.change.apply` |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/approvals/{parameter_2}/decision` | existing_capability | `agent.run.change.apply` |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/messages` | existing_capability | `agent.run.change.apply` |
| Agent | `agent_runtime:POST:/v1/runs/{session_gid}/messages/stream` | existing_capability | `agent.run.change.apply` |
| Agent | `capability:agent.run.change.apply` | existing_capability | `agent.run.change.apply` |
| Agent | `rest:POST:/api/ai/abort` | existing_capability | `agent.run.change.apply` |
| Agent | `rest:POST:/api/ai/chat` | existing_capability | `agent.run.change.apply` |
| Agent | `rest:POST:/api/ai/chat/stream` | existing_capability | `agent.run.change.apply` |
| Agent | `rest:POST:/api/ai/confirm` | existing_capability | `agent.run.change.apply` |
| Agent | `rest:POST:/api/ai/confirm/sync` | existing_capability | `agent.run.change.apply` |
| Agent | `agent_runtime:GET:/v1/runs/{session_gid}` | existing_capability | `agent.run.read` |
| Agent | `agent_runtime:GET:/v1/runs/{session_gid}/approvals` | existing_capability | `agent.run.read` |
| Agent | `capability:agent.run.read` | existing_capability | `agent.run.read` |
| Agent | `agent_runtime:DELETE:/v1/sessions/{session_gid}` | existing_capability | `agent.session.change.apply` |
| Agent | `agent_runtime:POST:/v1/sessions` | existing_capability | `agent.session.change.apply` |
| Agent | `capability:agent.session.change.apply` | existing_capability | `agent.session.change.apply` |
| Agent | `rest:DELETE:/api/ai/sessions/{gid}` | existing_capability | `agent.session.change.apply` |
| Agent | `rest:POST:/api/ai/sessions/new` | existing_capability | `agent.session.change.apply` |
| Agent | `agent_runtime:GET:/v1/sessions` | existing_capability | `agent.session.read` |
| Agent | `agent_runtime:GET:/v1/sessions/{session_gid}` | existing_capability | `agent.session.read` |
| Agent | `capability:agent.session.read` | existing_capability | `agent.session.read` |
| Agent | `rest:GET:/api/ai/sessions` | existing_capability | `agent.session.read` |
| Agent | `rest:GET:/api/ai/sessions/{gid}` | existing_capability | `agent.session.read` |
| Agent | `capability:agent.skill.change.apply` | existing_capability | `agent.skill.change.apply` |
| Agent | `rest:DELETE:/api/skills/{gid}` | existing_capability | `agent.skill.change.apply` |
| Agent | `rest:POST:/api/skills` | existing_capability | `agent.skill.change.apply` |
| Agent | `rest:PUT:/api/skills/{gid}` | existing_capability | `agent.skill.change.apply` |
| Agent | `capability:agent.skill.read` | existing_capability | `agent.skill.read` |
| Agent | `rest:GET:/api/skills` | existing_capability | `agent.skill.read` |
| Base Platform | `capability:plugin.upgrade.finish` | excluded | — |
| Base Platform | `capability:system.worker.outbox.health` | excluded | — |
| Base Platform | `rest:DELETE:/admin/config/{key}` | excluded | — |
| Base Platform | `rest:GET:/` | excluded | — |
| Base Platform | `rest:GET:/admin/cloud-db-config` | excluded | — |
| Base Platform | `rest:GET:/admin/config` | excluded | — |
| Base Platform | `rest:GET:/admin/config/{key}` | excluded | — |
| Base Platform | `rest:GET:/admin/debug-logs` | excluded | — |
| Base Platform | `rest:GET:/admin/plugin-registry` | excluded | — |
| Base Platform | `rest:GET:/admin/runtime-diagnostics` | excluded | — |
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
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/installations/{plugin_id}/upgrade-health` | excluded | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/mounts/{mount_session_id}/capabilities/{capability_id}:confirm` | excluded | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/mounts/{mount_session_id}/capabilities/{capability_id}:invoke` | excluded | — |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/usage/months/{month}/close` | excluded | — |
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
| Base Platform | `rest:DELETE:/api/self_ann/{item_gid}` | existing_capability | `base.annotation.change.apply` |
| Base Platform | `rest:PUT:/api/annotations/{key}` | existing_capability | `base.annotation.change.apply` |
| Base Platform | `rest:PUT:/api/self_ann/{item_gid}` | existing_capability | `base.annotation.change.apply` |
| Base Platform | `rest:GET:/api/annotations/{key}` | existing_capability | `base.annotation.read` |
| Base Platform | `rest:GET:/api/self_ann/batch` | existing_capability | `base.annotation.read` |
| Base Platform | `rest:GET:/api/self_ann/list` | existing_capability | `base.annotation.read` |
| Base Platform | `rest:GET:/api/self_ann/{item_gid}` | existing_capability | `base.annotation.read` |
| Base Platform | `rest:DELETE:/api/grants/{gid}` | existing_capability | `base.authorization.grant.change.apply` |
| Base Platform | `rest:POST:/api/grants` | existing_capability | `base.authorization.grant.change.apply` |
| Base Platform | `rest:GET:/api/grants` | existing_capability | `base.authorization.grant.read` |
| Base Platform | `rest:GET:/api/grants/me` | existing_capability | `base.authorization.grant.read` |
| Base Platform | `rest:DELETE:/api/import-export/templates/{gid}` | existing_capability | `base.export_template.change.apply` |
| Base Platform | `rest:PATCH:/api/import-export/templates/{gid}` | existing_capability | `base.export_template.change.apply` |
| Base Platform | `rest:POST:/api/import-export/templates` | existing_capability | `base.export_template.change.apply` |
| Base Platform | `rest:GET:/api/import-export/templates` | existing_capability | `base.export_template.read` |
| Base Platform | `rest:POST:/api/org/sync-from-feishu` | existing_capability | `base.identity.directory.sync` |
| Base Platform | `rest:PATCH:/api/users/{user_gid}/role` | existing_capability | `base.identity.role.assign` |
| Base Platform | `rest:GET:/api/users/me` | existing_capability | `base.identity.session.get` |
| Base Platform | `rest:GET:/users/me` | existing_capability | `base.identity.session.get` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/publishers` | existing_capability | `base.plugin.marketplace.publisher.register` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases` | existing_capability | `base.plugin.marketplace.release.change.apply` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases/{plugin_id}/{version}/review` | existing_capability | `base.plugin.marketplace.release.change.apply` |
| Base Platform | `rest:POST:/api/v1/plugin-marketplace/releases/{plugin_id}/{version}/revoke` | existing_capability | `base.plugin.marketplace.release.change.apply` |
| Base Platform | `rest:GET:/api/plugin/list` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/catalog` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/installations` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/installations/{plugin_id}/events` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/registry` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/releases` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:GET:/api/v1/plugin-marketplace/usage/months/{month}` | existing_capability | `base.plugin.marketplace.search` |
| Base Platform | `rest:DELETE:/api/views/{gid}` | existing_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:PATCH:/api/views/{gid}` | existing_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:POST:/api/views` | existing_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:POST:/api/views/{gid}/copy` | existing_capability | `base.saved_view.change.apply` |
| Base Platform | `rest:GET:/api/views` | existing_capability | `base.saved_view.read` |
| Base Platform | `rest:DELETE:/teams/{gid}` | existing_capability | `base.team.change.apply` |
| Base Platform | `rest:PATCH:/teams/{gid}` | existing_capability | `base.team.change.apply` |
| Base Platform | `rest:PATCH:/teams/{gid}/config` | existing_capability | `base.team.change.apply` |
| Base Platform | `rest:POST:/teams` | existing_capability | `base.team.change.apply` |
| Base Platform | `rest:DELETE:/teams/{gid}/members/{user_gid}` | existing_capability | `base.team.membership.change.apply` |
| Base Platform | `rest:POST:/teams/{gid}/members` | existing_capability | `base.team.membership.change.apply` |
| Base Platform | `rest:GET:/teams` | existing_capability | `base.team.read` |
| Base Platform | `rest:GET:/teams/{gid}/members` | existing_capability | `base.team.read` |
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
| Base Platform | `capability:semantic.context.get` | existing_capability | `semantic.context.get` |
| Base Platform | `capability:system.activity.search` | existing_capability | `system.activity.search` |
| Base Platform | `capability:system.change_impact.preview` | existing_capability | `system.change_impact.preview` |
| Base Platform | `capability:system.job.cancel` | existing_capability | `system.job.cancel` |
| Base Platform | `capability:system.job.get` | existing_capability | `system.job.get` |
| Base Platform | `capability:system.lineage.get` | existing_capability | `system.lineage.get` |
| Base Platform | `agent_tool:global_search` | existing_capability | `system.search` |
| Base Platform | `agent_tool:search` | existing_capability | `system.search` |
| Base Platform | `capability:system.search` | existing_capability | `system.search` |
| Craft | `rest:POST:/api/bop/pics/upload` | excluded | — |
| Craft | `rest:POST:/api/bop/resolve-gids` | excluded | — |
| Craft | `rest:POST:/api/import-export/lark-bitable/read` | excluded | — |
| Craft | `rest:POST:/api/import-export/lark-bitable/write` | excluded | — |
| Craft | `rest:POST:/api/import-export/lark-sheets/read` | excluded | — |
| Craft | `rest:POST:/api/import-export/lark-sheets/write` | excluded | — |
| Craft | `capability:craft.bop.draft.change.apply` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/entries/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/entry-links/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/operations/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/posts/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/resources/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/staging/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:DELETE:/api/bop/steps/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/entity-detail` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/entries/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/operations/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/pbom-diff-queue/{item_gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/posts/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/staging/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/steps/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/versions/{gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/versions/{gid}/lifecycle/init-state` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/versions/{gid}/pbom-match` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PATCH:/api/bop/versions/{gid}/vehicle-ops-stats` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/entries` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/entries/{gid}/demote` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/entries/{gid}/history/{log_gid}/rollback` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/entry-links` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/operations/{gid}/reset-fields` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/operations/{op_gid}/resources` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/operations/{op_gid}/steps` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/pbom-versions/{pbom_gid}/gbop-match-confirm` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/posts/{post_gid}/operations` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/staging/{gid}/promote` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{bop_gid}/gbop-auto-link` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{bop_gid}/posts` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/freeze` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/freeze-snapshot` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/confirm-phase` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/checkpoints` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/redo` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/rollback/{checkpoint_gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/undo` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/refresh-stats` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/lifecycle/undo-step` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/pbom-diff-queue` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/promote` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/publish` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{gid}/unfreeze` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{src_gid}/save-as-template` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{src_gid}/stage-advance` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{template_gid}/update-from/{src_gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/auto-link` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/copy-from-gbop/{src_gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/copy-from/{src_gid}` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/import-tc` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/purge-entries` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/bop/versions/{version_gid}/staging` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/vpps-operations/rule4-bulk-ignore` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:POST:/api/vpps-operations/{gid}/revert` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `rest:PUT:/api/bop/versions/{gid}/layout-config` | existing_capability | `craft.bop.draft.change.apply` |
| Craft | `agent_tool:audit_entry_rules` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `agent_tool:check_rules` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `capability:craft.bop.draft.change.preview` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:GET:/api/bop/operations/{gid}/drift-check` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:GET:/api/bop/versions/{gid}/pbom-diff-queue` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:GET:/api/bop/versions/{gid}/pbom-link-stats` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/auto-link-preview` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:GET:/api/vpps-operations` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:GET:/api/vpps-operations/rule4-ignores` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:POST:/api/rule-engine/audit/bop-version/{version_gid}` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `rest:POST:/api/rule-engine/check` | existing_capability | `craft.bop.draft.change.preview` |
| Craft | `capability:craft.bop.entry.detail.get` | existing_capability | `craft.bop.entry.detail.get` |
| Craft | `agent_tool:get_entry_relations` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `capability:craft.bop.execution_structure.get` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/entity-detail` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/entries/search` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/entries/{gid}` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/entries/{gid}/history` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/entry-links` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/canvas` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/layout-config` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/history` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/checkpoints` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/history` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/lifecycle/lines/{line_gid}/operation-log` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/alt-hier` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/bop-tree` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/entries` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/history` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/line-operations` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/link-summary` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/staging` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/station-part-map` | existing_capability | `craft.bop.execution_structure.get` |
| Craft | `capability:craft.bop.execution_structure.preview` | existing_capability | `craft.bop.execution_structure.preview` |
| Craft | `capability:craft.bop.import.preview` | existing_capability | `craft.bop.import.preview` |
| Craft | `rest:POST:/api/import-export/import/parse-excel` | existing_capability | `craft.bop.import.preview` |
| Craft | `capability:craft.bop.linked_parts.get` | existing_capability | `craft.bop.linked_parts.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}/pbom-change-point` | existing_capability | `craft.bop.linked_parts.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/line-op-catia-parts` | existing_capability | `craft.bop.linked_parts.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/linked-parts` | existing_capability | `craft.bop.linked_parts.get` |
| Craft | `rest:GET:/api/bop/versions/{version_gid}/pbom` | existing_capability | `craft.bop.linked_parts.get` |
| Craft | `capability:craft.bop.structure.outline.get` | existing_capability | `craft.bop.structure.outline.get` |
| Craft | `capability:craft.bop.validation.get` | existing_capability | `craft.bop.validation.get` |
| Craft | `capability:craft.bop.validation.run` | existing_capability | `craft.bop.validation.run` |
| Craft | `capability:craft.bop.version.archive` | existing_capability | `craft.bop.version.archive` |
| Craft | `rest:DELETE:/api/bop/version-families/{family_gid}/archive` | existing_capability | `craft.bop.version.archive` |
| Craft | `rest:POST:/api/bop/version-families/{family_gid}/archive` | existing_capability | `craft.bop.version.archive` |
| Craft | `capability:craft.bop.version.compare` | existing_capability | `craft.bop.version.compare` |
| Craft | `capability:craft.bop.version.create` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:DELETE:/api/bop/fork-presets/{gid}` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:GET:/api/bop/fork-presets` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:GET:/api/bop/fork-presets/{gid}` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:PATCH:/api/bop/fork-presets/{gid}` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:POST:/api/bop/fork-presets` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:POST:/api/bop/versions` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:POST:/api/bop/versions/{source_gid}/fork` | existing_capability | `craft.bop.version.create` |
| Craft | `rest:POST:/api/bop/versions/{source_gid}/smart-fork` | existing_capability | `craft.bop.version.create` |
| Craft | `capability:craft.bop.version.get` | existing_capability | `craft.bop.version.get` |
| Craft | `rest:GET:/api/bop/versions/{gid}` | existing_capability | `craft.bop.version.get` |
| Craft | `capability:craft.bop.version.list` | existing_capability | `craft.bop.version.list` |
| Craft | `rest:GET:/api/bop/versions` | existing_capability | `craft.bop.version.list` |
| Craft | `capability:craft.bop.work_package.get` | existing_capability | `craft.bop.work_package.get` |
| Craft | `rest:GET:/api/bop/operations/{op_gid}/resources` | existing_capability | `craft.bop.work_package.get` |
| Craft | `agent_tool:generate_canvas` | existing_capability | `craft.canvas.change.apply` |
| Craft | `agent_tool:run_skill_canvas` | existing_capability | `craft.canvas.change.apply` |
| Craft | `capability:craft.canvas.change.apply` | existing_capability | `craft.canvas.change.apply` |
| Craft | `rest:DELETE:/api/canvases/{gid}` | existing_capability | `craft.canvas.change.apply` |
| Craft | `rest:PATCH:/api/canvases/{gid}/shared` | existing_capability | `craft.canvas.change.apply` |
| Craft | `rest:POST:/api/canvases` | existing_capability | `craft.canvas.change.apply` |
| Craft | `agent_tool:get_canvas_state` | existing_capability | `craft.canvas.read` |
| Craft | `agent_tool:get_selected_elements` | existing_capability | `craft.canvas.read` |
| Craft | `capability:craft.canvas.read` | existing_capability | `craft.canvas.read` |
| Craft | `rest:GET:/api/canvases` | existing_capability | `craft.canvas.read` |
| Craft | `rest:GET:/api/canvases/{gid}` | existing_capability | `craft.canvas.read` |
| Craft | `capability:craft.data_exchange.export` | existing_capability | `craft.data_exchange.export` |
| Craft | `rest:POST:/api/import-export/export/diff-lark-sheet` | existing_capability | `craft.data_exchange.export` |
| Craft | `rest:POST:/api/import-export/export/diff-report` | existing_capability | `craft.data_exchange.export` |
| Craft | `rest:POST:/api/import-export/export/excel` | existing_capability | `craft.data_exchange.export` |
| Craft | `capability:craft.ebom.change.apply` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:DELETE:/api/ebom/parts/{gid}` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:DELETE:/api/ebom/snapshots/{gid}` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:PATCH:/api/ebom/parts/{gid}` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:PATCH:/api/ebom/snapshots/{gid}` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:PATCH:/api/ebom/snapshots/{gid}/status` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:PATCH:/api/ebom/snapshots/{gid}/vpps-stats` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:POST:/api/ebom/snapshots` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:POST:/api/ebom/snapshots/{gid}/parts` | existing_capability | `craft.ebom.change.apply` |
| Craft | `rest:POST:/api/ebom/snapshots/{gid}/parts/batch` | existing_capability | `craft.ebom.change.apply` |
| Craft | `capability:craft.ebom.read` | existing_capability | `craft.ebom.read` |
| Craft | `rest:GET:/api/ebom/diff` | existing_capability | `craft.ebom.read` |
| Craft | `rest:GET:/api/ebom/snapshots` | existing_capability | `craft.ebom.read` |
| Craft | `rest:GET:/api/ebom/snapshots/{gid}` | existing_capability | `craft.ebom.read` |
| Craft | `rest:GET:/api/ebom/snapshots/{gid}/parts` | existing_capability | `craft.ebom.read` |
| Craft | `rest:GET:/api/ebom/vpps_check` | existing_capability | `craft.ebom.read` |
| Craft | `capability:craft.gbop.change.apply` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:DELETE:/api/gbop/entries/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:DELETE:/api/gbop/entry-links/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:DELETE:/api/gbop/operations/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:DELETE:/api/gbop/processes/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:DELETE:/api/gbop/version-families/{family_gid}/archive` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:PATCH:/api/gbop/entries/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:PATCH:/api/gbop/operations/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:PATCH:/api/gbop/processes/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:PATCH:/api/gbop/versions/{gid}` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/bop-versions/{bop_gid}/station-autolink` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/bop-versions/{bop_gid}/station-autolink-undo` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/entries` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/entry-links` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/operations` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/pbom-versions/{pbom_gid}/vpps-auto-link` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/pbom-versions/{pbom_gid}/vpps-auto-link-confirm` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/processes` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/version-families/{family_gid}/archive` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/versions` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/versions/{gid}/freeze` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/versions/{source_gid}/fork` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/versions/{version_gid}/import-entries` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/versions/{version_gid}/import-tc-excel` | existing_capability | `craft.gbop.change.apply` |
| Craft | `rest:POST:/api/gbop/versions/{version_gid}/import-vpps-parts` | existing_capability | `craft.gbop.change.apply` |
| Craft | `capability:craft.gbop.draft.change.apply` | existing_capability | `craft.gbop.draft.change.apply` |
| Craft | `capability:craft.gbop.draft.change.preview` | existing_capability | `craft.gbop.draft.change.preview` |
| Craft | `capability:craft.gbop.draft.create` | existing_capability | `craft.gbop.draft.create` |
| Craft | `capability:craft.gbop.draft.get` | existing_capability | `craft.gbop.draft.get` |
| Craft | `capability:craft.gbop.draft.search` | existing_capability | `craft.gbop.draft.search` |
| Craft | `capability:craft.gbop.draft.submit` | existing_capability | `craft.gbop.draft.submit` |
| Craft | `capability:craft.gbop.item.knowledge.list` | existing_capability | `craft.gbop.item.knowledge.list` |
| Craft | `capability:craft.gbop.item.search` | existing_capability | `craft.gbop.item.search` |
| Craft | `capability:craft.gbop.item.usage.get` | existing_capability | `craft.gbop.item.usage.get` |
| Craft | `capability:craft.gbop.read` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/bop-versions/{bop_gid}/station-autolink-preview` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/entries/{entry_gid}/links` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/pbom-versions/{pbom_gid}/gbop-nav-link-summary` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/pbom-versions/{pbom_gid}/process-hierarchy` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/pbom-versions/{pbom_gid}/vpps-auto-link-status` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/versions` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/versions/{version_gid}/entries` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/versions/{version_gid}/operations` | existing_capability | `craft.gbop.read` |
| Craft | `rest:GET:/api/gbop/versions/{version_gid}/processes` | existing_capability | `craft.gbop.read` |
| Craft | `capability:craft.gbop.release.activate` | existing_capability | `craft.gbop.release.activate` |
| Craft | `capability:craft.gbop.release.archive` | existing_capability | `craft.gbop.release.archive` |
| Craft | `capability:craft.gbop.release.compare` | existing_capability | `craft.gbop.release.compare` |
| Craft | `capability:craft.gbop.release.get` | existing_capability | `craft.gbop.release.get` |
| Craft | `capability:craft.gbop.release.publish` | existing_capability | `craft.gbop.release.publish` |
| Craft | `capability:craft.gbop.release.search` | existing_capability | `craft.gbop.release.search` |
| Craft | `capability:craft.manufacturing_resource.change.apply` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/bop/factories/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/bop/factory_sections/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/bop/factory_stations/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/bop/layout_templates/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/craft_lib/fasteners/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/craft_lib/part_names/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/craft_lib/tools/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/factory/equipments/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/factory/fixtures/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/factory/sections/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/factory/stations/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/factory/tools/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:DELETE:/api/std_op/operations/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/bop/factories/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/bop/factory_sections/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/bop/factory_stations/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/bop/layout_templates/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/craft_lib/equipments/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/craft_lib/fasteners/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/craft_lib/fixtures/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/craft_lib/part_names/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/craft_lib/tools/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/factory/equipments/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/factory/fixtures/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/factory/sections/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/factory/stations/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/factory/tools/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:PATCH:/api/std_op/operations/{gid}` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/bop/factories` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/bop/factories/{factory_gid}/layout_templates` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/bop/factories/{factory_gid}/sections` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/bop/factory_sections/{section_gid}/stations` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/bop/layout_templates/{gid}/apply` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/equipments` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/equipments/{gid}/obsolete` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/fasteners` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/fixtures` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/fixtures/{gid}/obsolete` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/part_names` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/part_names/batch_accept_alias` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/part_names/batch_add_from_pbom` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/part_names/{gid}/accept_alias` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/tools` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/craft_lib/tools/{gid}/obsolete` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/equipments` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/equipments/{gid}/maintenance` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/equipments/{gid}/return` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/equipments/{gid}/scrap` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/fixtures` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/fixtures/{gid}/maintenance` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/fixtures/{gid}/return` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/fixtures/{gid}/scrap` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/sections` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/stations` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/tools` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/tools/{gid}/maintenance` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/tools/{gid}/return` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/factory/tools/{gid}/scrap` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/std_op/operations` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/std_op/operations/{gid}/clone-to-post` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/std_op/operations/{gid}/deprecate` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `rest:POST:/api/std_op/operations/{gid}/publish` | existing_capability | `craft.manufacturing_resource.change.apply` |
| Craft | `capability:craft.manufacturing_resource.read` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/bop/factories` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/bop/factories/{factory_gid}/layout_templates` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/bop/factories/{factory_gid}/sections` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/bop/factories/{gid}` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/bop/factory_sections/{section_gid}/stations` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/bop/layout_templates/{gid}` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/craft_lib/equipments` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/craft_lib/fasteners` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/craft_lib/fixtures` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/craft_lib/part_names` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/craft_lib/tools` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/factory/equipments` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/factory/fixtures` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/factory/sections` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/factory/stations` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/factory/tools` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/std_op/operations` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `rest:GET:/api/std_op/operations/{gid}` | existing_capability | `craft.manufacturing_resource.read` |
| Craft | `capability:craft.pbom.draft.change.apply` | existing_capability | `craft.pbom.draft.change.apply` |
| Craft | `capability:craft.pbom.draft.change.preview` | existing_capability | `craft.pbom.draft.change.preview` |
| Craft | `capability:craft.pbom.import.preview` | existing_capability | `craft.pbom.import.preview` |
| Craft | `capability:craft.pbom.part.search` | existing_capability | `craft.pbom.part.search` |
| Craft | `rest:GET:/api/bop/pbom/search` | existing_capability | `craft.pbom.part.search` |
| Craft | `capability:craft.pbom.version.archive` | existing_capability | `craft.pbom.version.archive` |
| Craft | `capability:craft.pbom.version.compare` | existing_capability | `craft.pbom.version.compare` |
| Craft | `capability:craft.pbom.version.create` | existing_capability | `craft.pbom.version.create` |
| Craft | `capability:craft.pbom.version.get` | existing_capability | `craft.pbom.version.get` |
| Craft | `rest:GET:/api/bop/pbom-versions/{pbom_gid}/gbop-match-preview` | existing_capability | `craft.pbom.version.get` |
| Craft | `capability:craft.pbom.version.publish` | existing_capability | `craft.pbom.version.publish` |
| Craft | `capability:craft.pbom.version.search` | existing_capability | `craft.pbom.version.search` |
| Craft | `rest:GET:/api/bop/pbom-snapshots` | existing_capability | `craft.pbom.version.search` |
| Craft | `rest:GET:/api/bop/pbom-versions` | existing_capability | `craft.pbom.version.search` |
| Craft | `capability:craft.pbom.version.submit` | existing_capability | `craft.pbom.version.submit` |
| Craft | `capability:craft.rule.change.apply` | existing_capability | `craft.rule.change.apply` |
| Craft | `rest:DELETE:/api/rules/{gid}` | existing_capability | `craft.rule.change.apply` |
| Craft | `rest:PATCH:/api/rules/{gid}` | existing_capability | `craft.rule.change.apply` |
| Craft | `rest:POST:/api/rules` | existing_capability | `craft.rule.change.apply` |
| Craft | `capability:craft.rule.draft.create` | existing_capability | `craft.rule.draft.create` |
| Craft | `capability:craft.rule.draft.get` | existing_capability | `craft.rule.draft.get` |
| Craft | `capability:craft.rule.draft.revise` | existing_capability | `craft.rule.draft.revise` |
| Craft | `capability:craft.rule.draft.search` | existing_capability | `craft.rule.draft.search` |
| Craft | `capability:craft.rule.draft.submit` | existing_capability | `craft.rule.draft.submit` |
| Craft | `capability:craft.rule.evaluate` | existing_capability | `craft.rule.evaluate` |
| Craft | `agent_tool:list_rules` | existing_capability | `craft.rule.read` |
| Craft | `capability:craft.rule.read` | existing_capability | `craft.rule.read` |
| Craft | `rest:GET:/api/rules` | existing_capability | `craft.rule.read` |
| Craft | `rest:GET:/api/rules/{gid}` | existing_capability | `craft.rule.read` |
| Craft | `capability:craft.rule.release.activate` | existing_capability | `craft.rule.release.activate` |
| Craft | `capability:craft.rule.release.get` | existing_capability | `craft.rule.release.get` |
| Craft | `capability:craft.rule.release.publish` | existing_capability | `craft.rule.release.publish` |
| Craft | `capability:craft.rule.release.search` | existing_capability | `craft.rule.release.search` |
| Craft | `capability:craft.rule.waiver.create` | existing_capability | `craft.rule.waiver.create` |
| Craft | `capability:craft.rule.waiver.revoke` | existing_capability | `craft.rule.waiver.revoke` |
| Craft | `capability:craft.rule.waiver.search` | existing_capability | `craft.rule.waiver.search` |
| Device | `rest:GET:/api/v1/device-runtime/commands/{command_gid}/artifacts/{artifact_id}` | excluded | — |
| Device | `rest:POST:/api/v1/device-runtime/activate` | excluded | — |
| Device | `rest:POST:/api/v1/device-runtime/commands/lease` | excluded | — |
| Device | `rest:POST:/api/v1/device-runtime/commands/{command_gid}/complete` | excluded | — |
| Device | `rest:POST:/api/v1/device-runtime/heartbeat` | excluded | — |
| Device | `rest:PUT:/api/v1/device-runtime/commands/{command_gid}/result-artifact` | excluded | — |
| Device | `capability:local.command.get` | existing_capability | `local.command.get` |
| Device | `capability:local.device.change.apply` | existing_capability | `local.device.change.apply` |
| Device | `rest:DELETE:/api/v1/devices/{device_gid}` | existing_capability | `local.device.change.apply` |
| Device | `rest:POST:/api/v1/devices/enrollments` | existing_capability | `local.device.change.apply` |
| Device | `capability:local.device.read` | existing_capability | `local.device.read` |
| Device | `rest:GET:/api/v1/devices` | existing_capability | `local.device.read` |
| Device | `capability:vismockup.capture` | existing_capability | `vismockup.capture` |
| Device | `local_command:vismockup.capture` | existing_capability | `vismockup.capture` |
| Device | `capability:vismockup.highlight` | existing_capability | `vismockup.highlight` |
| Device | `local_command:vismockup.highlight` | existing_capability | `vismockup.highlight` |
| Device | `agent_tool:open_in_container` | existing_capability | `vismockup.launch` |
| Device | `capability:vismockup.launch` | existing_capability | `vismockup.launch` |
| Device | `local_command:vismockup.launch` | existing_capability | `vismockup.launch` |
| Device | `capability:vismockup.model.open` | existing_capability | `vismockup.model.open` |
| Device | `local_command:vismockup.model.open` | existing_capability | `vismockup.model.open` |
| Device | `capability:vismockup.status` | existing_capability | `vismockup.status` |
| Device | `local_command:vismockup.status` | existing_capability | `vismockup.status` |
| Device | `capability:vismockup.tree` | existing_capability | `vismockup.tree` |
| Device | `local_command:vismockup.tree` | existing_capability | `vismockup.tree` |
| Device | `capability:vismockup.visibility` | existing_capability | `vismockup.visibility` |
| Device | `local_command:vismockup.visibility` | existing_capability | `vismockup.visibility` |
| Digital Model | `capability:digital_model.component.search` | existing_capability | `digital_model.component.search` |
| Digital Model | `capability:digital_model.model.create` | existing_capability | `digital_model.model.create` |
| Digital Model | `capability:digital_model.model.get` | existing_capability | `digital_model.model.get` |
| Digital Model | `capability:digital_model.model.search` | existing_capability | `digital_model.model.search` |
| Digital Model | `capability:digital_model.version.compare` | existing_capability | `digital_model.version.compare` |
| Digital Model | `capability:digital_model.version.create` | existing_capability | `digital_model.version.create` |
| Digital Model | `capability:digital_model.version.get` | existing_capability | `digital_model.version.get` |
| Digital Model | `capability:digital_model.version.search` | existing_capability | `digital_model.version.search` |
| Factory | `capability:factory.asset.get` | existing_capability | `factory.asset.get` |
| Factory | `capability:factory.asset.maintenance.complete` | existing_capability | `factory.asset.maintenance.complete` |
| Factory | `capability:factory.asset.maintenance.start` | existing_capability | `factory.asset.maintenance.start` |
| Factory | `capability:factory.asset.register` | existing_capability | `factory.asset.register` |
| Factory | `capability:factory.asset.scrap` | existing_capability | `factory.asset.scrap` |
| Factory | `capability:factory.asset.search` | existing_capability | `factory.asset.search` |
| Factory | `capability:factory.asset.update` | existing_capability | `factory.asset.update` |
| Factory | `capability:factory.resource.read` | existing_capability | `factory.resource.read` |
| Factory | `capability:factory.resource_catalog.create` | existing_capability | `factory.resource_catalog.create` |
| Factory | `capability:factory.resource_catalog.deprecate` | existing_capability | `factory.resource_catalog.deprecate` |
| Factory | `capability:factory.resource_catalog.get` | existing_capability | `factory.resource_catalog.get` |
| Factory | `capability:factory.resource_catalog.publish` | existing_capability | `factory.resource_catalog.publish` |
| Factory | `capability:factory.resource_catalog.revise` | existing_capability | `factory.resource_catalog.revise` |
| Factory | `capability:factory.resource_catalog.search` | existing_capability | `factory.resource_catalog.search` |
| Factory | `capability:factory.structure.archive` | existing_capability | `factory.structure.archive` |
| Factory | `capability:factory.structure.create` | existing_capability | `factory.structure.create` |
| Factory | `capability:factory.structure.get` | existing_capability | `factory.structure.get` |
| Factory | `capability:factory.structure.search` | existing_capability | `factory.structure.search` |
| Factory | `capability:factory.structure.update` | existing_capability | `factory.structure.update` |
| Integration | `capability:integration.connector.archive` | existing_capability | `integration.connector.archive` |
| Integration | `capability:integration.connector.connection.test` | existing_capability | `integration.connector.connection.test` |
| Integration | `capability:integration.connector.create` | existing_capability | `integration.connector.create` |
| Integration | `capability:integration.connector.schema.discover` | existing_capability | `integration.connector.schema.discover` |
| Integration | `capability:integration.connector.search` | existing_capability | `integration.connector.search` |
| Integration | `capability:integration.connector.update` | existing_capability | `integration.connector.update` |
| Integration | `capability:integration.mapping.archive` | existing_capability | `integration.mapping.archive` |
| Integration | `capability:integration.mapping.create` | existing_capability | `integration.mapping.create` |
| Integration | `capability:integration.mapping.get` | existing_capability | `integration.mapping.get` |
| Integration | `capability:integration.mapping.preview` | existing_capability | `integration.mapping.preview` |
| Integration | `capability:integration.mapping.search` | existing_capability | `integration.mapping.search` |
| Integration | `capability:integration.mapping.update` | existing_capability | `integration.mapping.update` |
| Integration | `capability:integration.sync.start` | existing_capability | `integration.sync.start` |
| Knowledge | `agent_tool:recommend_practice` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `agent_tool:search_knowledge` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `capability:knowledge.context.retrieve` | existing_capability | `knowledge.context.retrieve` |
| Knowledge | `capability:knowledge.document.acl.grant` | existing_capability | `knowledge.document.acl.grant` |
| Knowledge | `capability:knowledge.document.acl.list` | existing_capability | `knowledge.document.acl.list` |
| Knowledge | `capability:knowledge.document.acl.revoke` | existing_capability | `knowledge.document.acl.revoke` |
| Knowledge | `capability:knowledge.document.archive` | existing_capability | `knowledge.document.archive` |
| Knowledge | `capability:knowledge.document.create` | existing_capability | `knowledge.document.create` |
| Knowledge | `capability:knowledge.document.diff` | existing_capability | `knowledge.document.diff` |
| Knowledge | `agent_tool:get_knowledge_document` | existing_capability | `knowledge.document.get` |
| Knowledge | `capability:knowledge.document.get` | existing_capability | `knowledge.document.get` |
| Knowledge | `capability:knowledge.document.history.get` | existing_capability | `knowledge.document.history.get` |
| Knowledge | `capability:knowledge.document.restore` | existing_capability | `knowledge.document.restore` |
| Knowledge | `capability:knowledge.document.revise` | existing_capability | `knowledge.document.revise` |
| Knowledge | `capability:knowledge.document.revisions` | existing_capability | `knowledge.document.revisions` |
| Knowledge | `capability:knowledge.document.rollback` | existing_capability | `knowledge.document.rollback` |
| Knowledge | `capability:knowledge.document.search` | existing_capability | `knowledge.document.search` |
| Knowledge | `capability:knowledge.entry.change.apply` | existing_capability | `knowledge.entry.change.apply` |
| Knowledge | `agent_tool:get_knowledge_entry` | existing_capability | `knowledge.get` |
| Knowledge | `capability:knowledge.get` | existing_capability | `knowledge.get` |
| Knowledge | `capability:knowledge.migration.status` | existing_capability | `knowledge.migration.status` |
| Knowledge | `capability:knowledge.personalization.change.apply` | existing_capability | `knowledge.personalization.change.apply` |
| Knowledge | `capability:knowledge.personalization.read` | existing_capability | `knowledge.personalization.read` |
| Knowledge | `capability:knowledge.proposal.get` | existing_capability | `knowledge.proposal.get` |
| Knowledge | `capability:knowledge.proposal.list` | existing_capability | `knowledge.proposal.list` |
| Knowledge | `capability:knowledge.proposal.outbox.list` | existing_capability | `knowledge.proposal.outbox.list` |
| Knowledge | `capability:knowledge.proposal.outbox.retry` | existing_capability | `knowledge.proposal.outbox.retry` |
| Knowledge | `capability:knowledge.proposal.review` | existing_capability | `knowledge.proposal.review` |
| Knowledge | `capability:knowledge.propose` | existing_capability | `knowledge.propose` |
| Knowledge | `capability:knowledge.reference_data.change.apply` | existing_capability | `knowledge.reference_data.change.apply` |
| Knowledge | `capability:knowledge.reference_data.read` | existing_capability | `knowledge.reference_data.read` |
| Knowledge | `agent_tool:find_similar_cases` | existing_capability | `knowledge.search` |
| Knowledge | `capability:knowledge.search` | existing_capability | `knowledge.search` |
| Knowledge | `capability:knowledge.space.change.apply` | existing_capability | `knowledge.space.change.apply` |
| Knowledge | `capability:knowledge.space.create` | existing_capability | `knowledge.space.create` |
| Knowledge | `capability:knowledge.space.list` | existing_capability | `knowledge.space.list` |
| Knowledge | `capability:knowledge.space.search` | existing_capability | `knowledge.space.search` |
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
| Ontology | `capability:ontology.mapping.change.apply` | existing_capability | `ontology.mapping.change.apply` |
| Ontology | `rest:PATCH:/api/bop/entries/{entry_gid}/entity-props` | existing_capability | `ontology.mapping.change.apply` |
| Ontology | `capability:ontology.release.activate` | existing_capability | `ontology.release.activate` |
| Ontology | `capability:ontology.release.diff` | existing_capability | `ontology.release.diff` |
| Ontology | `rest:GET:/api/ontology/schema-diff` | existing_capability | `ontology.release.diff` |
| Ontology | `capability:ontology.release.get` | existing_capability | `ontology.release.get` |
| Ontology | `capability:ontology.release.publish` | existing_capability | `ontology.release.publish` |
| Ontology | `capability:ontology.release.search` | existing_capability | `ontology.release.search` |
| Ontology | `capability:ontology.schema.change.apply` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/axioms/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/classes/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/properties/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:DELETE:/api/ontology/relations/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:PATCH:/api/ontology/classes/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:PATCH:/api/ontology/properties/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:PATCH:/api/ontology/relations/{gid}` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/axioms` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/classes` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/classes/{gid}/sync-from-table` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/properties` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/relations` | existing_capability | `ontology.schema.change.apply` |
| Ontology | `rest:POST:/api/ontology/seed` | existing_capability | `ontology.schema.change.apply` |
| Project Management | `rest:GET:/share/issues` | excluded | — |
| Project Management | `agent_tool:list_projects` | existing_capability | `base.project.search` |
| Project Management | `capability:base.project.search` | existing_capability | `base.project.search` |
| Project Management | `rest:GET:/api/projects` | existing_capability | `base.project.search` |
| Project Management | `agent_tool:aggregate_history` | existing_capability | `project.activity.aggregate` |
| Project Management | `capability:project.activity.aggregate` | existing_capability | `project.activity.aggregate` |
| Project Management | `agent_tool:create_approval_order` | existing_capability | `project.approval.change.apply` |
| Project Management | `capability:project.approval.change.apply` | existing_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders` | existing_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/scope_upgrade` | existing_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/{gid}/approve` | existing_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/{gid}/start` | existing_capability | `project.approval.change.apply` |
| Project Management | `rest:POST:/api/approval/orders/{gid}/withdraw` | existing_capability | `project.approval.change.apply` |
| Project Management | `agent_tool:list_approval_orders` | existing_capability | `project.approval.read` |
| Project Management | `capability:project.approval.read` | existing_capability | `project.approval.read` |
| Project Management | `rest:GET:/api/approval/orders` | existing_capability | `project.approval.read` |
| Project Management | `rest:GET:/api/approval/orders/{gid}` | existing_capability | `project.approval.read` |
| Project Management | `capability:project.bitable_binding.change.apply` | existing_capability | `project.bitable_binding.change.apply` |
| Project Management | `capability:project.bitable_binding.read` | existing_capability | `project.bitable_binding.read` |
| Project Management | `capability:project.change_log.read` | existing_capability | `project.change_log.read` |
| Project Management | `rest:GET:/api/change-logs` | existing_capability | `project.change_log.read` |
| Project Management | `capability:project.collaboration.change.apply` | existing_capability | `project.collaboration.change.apply` |
| Project Management | `rest:POST:/api/collab/sessions` | existing_capability | `project.collaboration.change.apply` |
| Project Management | `rest:POST:/api/collab/sessions/{gid}/end` | existing_capability | `project.collaboration.change.apply` |
| Project Management | `rest:POST:/api/collab/sessions/{gid}/join` | existing_capability | `project.collaboration.change.apply` |
| Project Management | `capability:project.collaboration.read` | existing_capability | `project.collaboration.read` |
| Project Management | `rest:GET:/api/collab/sessions` | existing_capability | `project.collaboration.read` |
| Project Management | `rest:GET:/api/collab/sessions/{gid}` | existing_capability | `project.collaboration.read` |
| Project Management | `capability:project.craft_scope.read` | existing_capability | `project.craft_scope.read` |
| Project Management | `rest:GET:/api/projects/{gid}/bop-lines` | existing_capability | `project.craft_scope.read` |
| Project Management | `capability:project.follow.change.apply` | existing_capability | `project.follow.change.apply` |
| Project Management | `rest:DELETE:/api/follows/{gid}` | existing_capability | `project.follow.change.apply` |
| Project Management | `rest:PATCH:/api/follows/{gid}` | existing_capability | `project.follow.change.apply` |
| Project Management | `rest:POST:/api/follows` | existing_capability | `project.follow.change.apply` |
| Project Management | `capability:project.follow.read` | existing_capability | `project.follow.read` |
| Project Management | `rest:GET:/api/follows` | existing_capability | `project.follow.read` |
| Project Management | `rest:GET:/api/follows/check` | existing_capability | `project.follow.read` |
| Project Management | `agent_tool:create_issue` | existing_capability | `project.issue.change.apply` |
| Project Management | `agent_tool:update_issue` | existing_capability | `project.issue.change.apply` |
| Project Management | `capability:project.issue.change.apply` | existing_capability | `project.issue.change.apply` |
| Project Management | `rest:DELETE:/api/issues/{gid}` | existing_capability | `project.issue.change.apply` |
| Project Management | `rest:GET:/api/issues/promote` | existing_capability | `project.issue.change.apply` |
| Project Management | `rest:PATCH:/api/issues/{gid}` | existing_capability | `project.issue.change.apply` |
| Project Management | `rest:POST:/api/issues` | existing_capability | `project.issue.change.apply` |
| Project Management | `rest:POST:/api/issues/promote` | existing_capability | `project.issue.change.apply` |
| Project Management | `rest:PUT:/api/issues/{gid}` | existing_capability | `project.issue.change.apply` |
| Project Management | `agent_tool:get_issue` | existing_capability | `project.issue.read` |
| Project Management | `agent_tool:list_issue_lists` | existing_capability | `project.issue.read` |
| Project Management | `agent_tool:list_issues` | existing_capability | `project.issue.read` |
| Project Management | `capability:project.issue.read` | existing_capability | `project.issue.read` |
| Project Management | `rest:GET:/api/issues` | existing_capability | `project.issue.read` |
| Project Management | `rest:GET:/api/issues/{gid}` | existing_capability | `project.issue.read` |
| Project Management | `capability:project.list.change.apply` | existing_capability | `project.list.change.apply` |
| Project Management | `rest:DELETE:/api/item-entries/{item_type}/{item_gid}` | existing_capability | `project.list.change.apply` |
| Project Management | `rest:DELETE:/api/lists/{gid}` | existing_capability | `project.list.change.apply` |
| Project Management | `rest:PATCH:/api/lists/{gid}` | existing_capability | `project.list.change.apply` |
| Project Management | `rest:POST:/api/lists` | existing_capability | `project.list.change.apply` |
| Project Management | `rest:POST:/api/lists/{gid}/retarget` | existing_capability | `project.list.change.apply` |
| Project Management | `rest:PUT:/api/item-entries/{item_type}/{item_gid}` | existing_capability | `project.list.change.apply` |
| Project Management | `capability:project.list.read` | existing_capability | `project.list.read` |
| Project Management | `rest:GET:/api/item-entries/{item_type}/{item_gid}` | existing_capability | `project.list.read` |
| Project Management | `rest:GET:/api/lists` | existing_capability | `project.list.read` |
| Project Management | `capability:project.member.change.apply` | existing_capability | `project.member.change.apply` |
| Project Management | `rest:DELETE:/api/projects/{gid}/members/{member_gid}` | existing_capability | `project.member.change.apply` |
| Project Management | `rest:POST:/api/projects/{gid}/members` | existing_capability | `project.member.change.apply` |
| Project Management | `capability:project.member.read` | existing_capability | `project.member.read` |
| Project Management | `rest:GET:/api/projects/members/matrix` | existing_capability | `project.member.read` |
| Project Management | `rest:GET:/api/projects/{gid}/members` | existing_capability | `project.member.read` |
| Project Management | `capability:project.notification.change.apply` | existing_capability | `project.notification.change.apply` |
| Project Management | `rest:PATCH:/api/notifications/prefs` | existing_capability | `project.notification.change.apply` |
| Project Management | `rest:PATCH:/api/notifications/read_all` | existing_capability | `project.notification.change.apply` |
| Project Management | `rest:PATCH:/api/notifications/{gid}/read` | existing_capability | `project.notification.change.apply` |
| Project Management | `rest:POST:/api/mentions/notify` | existing_capability | `project.notification.change.apply` |
| Project Management | `capability:project.notification.read` | existing_capability | `project.notification.read` |
| Project Management | `rest:GET:/api/notifications` | existing_capability | `project.notification.read` |
| Project Management | `rest:GET:/api/notifications/prefs` | existing_capability | `project.notification.read` |
| Project Management | `rest:GET:/api/notifications/unread_count` | existing_capability | `project.notification.read` |
| Project Management | `capability:project.permission_request.change.apply` | existing_capability | `project.permission_request.change.apply` |
| Project Management | `rest:POST:/api/permission-requests` | existing_capability | `project.permission_request.change.apply` |
| Project Management | `rest:POST:/api/permission-requests/{gid}/approve` | existing_capability | `project.permission_request.change.apply` |
| Project Management | `rest:POST:/api/permission-requests/{gid}/reject` | existing_capability | `project.permission_request.change.apply` |
| Project Management | `capability:project.permission_request.read` | existing_capability | `project.permission_request.read` |
| Project Management | `rest:GET:/api/permission-requests` | existing_capability | `project.permission_request.read` |
| Project Management | `capability:project.project.change.apply` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:DELETE:/api/projects/vehicle_models/{gid}` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:DELETE:/api/projects/{gid}` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:PATCH:/api/projects/vehicle_models/{gid}` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:PATCH:/api/projects/{gid}` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:POST:/api/projects` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:POST:/api/projects/vehicle_models` | existing_capability | `project.project.change.apply` |
| Project Management | `rest:PUT:/api/projects/{gid}/line-assignment` | existing_capability | `project.project.change.apply` |
| Project Management | `capability:project.project.read` | existing_capability | `project.project.read` |
| Project Management | `rest:GET:/api/projects/vehicle_models` | existing_capability | `project.project.read` |
| Project Management | `rest:GET:/api/projects/{gid}` | existing_capability | `project.project.read` |
| Project Management | `capability:project.sharing.change.apply` | existing_capability | `project.sharing.change.apply` |
| Project Management | `rest:DELETE:/api/share-links/{token}` | existing_capability | `project.sharing.change.apply` |
| Project Management | `rest:DELETE:/api/shares/items/{gid}` | existing_capability | `project.sharing.change.apply` |
| Project Management | `rest:DELETE:/api/shares/lists/{list_gid}/{gid}` | existing_capability | `project.sharing.change.apply` |
| Project Management | `rest:POST:/api/share-links` | existing_capability | `project.sharing.change.apply` |
| Project Management | `rest:POST:/api/shares/items` | existing_capability | `project.sharing.change.apply` |
| Project Management | `rest:POST:/api/shares/lists/{list_gid}` | existing_capability | `project.sharing.change.apply` |
| Project Management | `capability:project.sharing.read` | existing_capability | `project.sharing.read` |
| Project Management | `rest:GET:/api/share-links/{token}` | existing_capability | `project.sharing.read` |
| Project Management | `rest:GET:/api/shares/lists/{list_gid}` | existing_capability | `project.sharing.read` |
| Project Management | `agent_tool:add_task_progress_log` | existing_capability | `project.task.change.apply` |
| Project Management | `agent_tool:create_task` | existing_capability | `project.task.change.apply` |
| Project Management | `agent_tool:update_task` | existing_capability | `project.task.change.apply` |
| Project Management | `capability:project.task.change.apply` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:DELETE:/api/task-dependencies/{gid}` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:DELETE:/api/tasks/{gid}` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:GET:/api/tasks/promote` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:PATCH:/api/tasks/{gid}` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:POST:/api/task-dependencies` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:POST:/api/tasks` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:POST:/api/tasks/promote` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:PUT:/api/task-dependencies/{gid}` | existing_capability | `project.task.change.apply` |
| Project Management | `rest:PUT:/api/tasks/{gid}` | existing_capability | `project.task.change.apply` |
| Project Management | `agent_tool:get_task` | existing_capability | `project.task.read` |
| Project Management | `agent_tool:list_task_lists` | existing_capability | `project.task.read` |
| Project Management | `agent_tool:list_tasks` | existing_capability | `project.task.read` |
| Project Management | `capability:project.task.read` | existing_capability | `project.task.read` |
| Project Management | `rest:GET:/api/task-dependencies` | existing_capability | `project.task.read` |
| Project Management | `rest:GET:/api/tasks` | existing_capability | `project.task.read` |
| Project Management | `rest:GET:/api/tasks/{gid}` | existing_capability | `project.task.read` |
| Project Management | `capability:project.task_template.change.apply` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:DELETE:/api/task-templates/items/{item_gid}` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:DELETE:/api/task-templates/{gid}` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:PATCH:/api/task-templates/items/{item_gid}` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:PATCH:/api/task-templates/{gid}` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:POST:/api/task-templates` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:POST:/api/task-templates/{gid}/instantiate` | existing_capability | `project.task_template.change.apply` |
| Project Management | `rest:POST:/api/task-templates/{template_gid}/items` | existing_capability | `project.task_template.change.apply` |
| Project Management | `capability:project.task_template.read` | existing_capability | `project.task_template.read` |
| Project Management | `rest:GET:/api/task-templates` | existing_capability | `project.task_template.read` |
| Project Management | `rest:GET:/api/task-templates/{gid}` | existing_capability | `project.task_template.read` |
| Project Management | `capability:project.workbench.change.apply` | existing_capability | `project.workbench.change.apply` |
| Project Management | `rest:DELETE:/api/workbenches/{gid}` | existing_capability | `project.workbench.change.apply` |
| Project Management | `rest:DELETE:/api/workbenches/{gid}/override` | existing_capability | `project.workbench.change.apply` |
| Project Management | `rest:PATCH:/api/workbenches/{gid}` | existing_capability | `project.workbench.change.apply` |
| Project Management | `rest:POST:/api/workbenches` | existing_capability | `project.workbench.change.apply` |
| Project Management | `rest:PUT:/api/workbenches/{gid}/override` | existing_capability | `project.workbench.change.apply` |
| Project Management | `capability:project.workbench.read` | existing_capability | `project.workbench.read` |
| Project Management | `rest:GET:/api/workbenches` | existing_capability | `project.workbench.read` |
| Project Management | `rest:GET:/api/workbenches/{gid}/override` | existing_capability | `project.workbench.read` |
| Simulation | `capability:simulation.environment.archive` | existing_capability | `simulation.environment.archive` |
| Simulation | `capability:simulation.environment.create` | existing_capability | `simulation.environment.create` |
| Simulation | `rest:POST:/api/simulation/environments` | existing_capability | `simulation.environment.create` |
| Simulation | `capability:simulation.environment.get` | existing_capability | `simulation.environment.get` |
| Simulation | `rest:GET:/api/simulation/environments/{environment_gid}` | existing_capability | `simulation.environment.get` |
| Simulation | `capability:simulation.environment.search` | existing_capability | `simulation.environment.search` |
| Simulation | `rest:GET:/api/simulation/environments` | existing_capability | `simulation.environment.search` |
| Simulation | `capability:simulation.parameter_set.create` | existing_capability | `simulation.parameter_set.create` |
| Simulation | `capability:simulation.parameter_set.get` | existing_capability | `simulation.parameter_set.get` |
| Simulation | `capability:simulation.parameter_set.search` | existing_capability | `simulation.parameter_set.search` |
| Simulation | `capability:simulation.result.compare` | existing_capability | `simulation.result.compare` |
| Simulation | `capability:simulation.result.get` | existing_capability | `simulation.result.get` |
| Simulation | `capability:simulation.run.get` | existing_capability | `simulation.run.get` |
| Simulation | `capability:simulation.run.search` | existing_capability | `simulation.run.search` |
| Simulation | `capability:simulation.run.start` | existing_capability | `simulation.run.start` |
| Simulation | `capability:simulation.solver_profile.create` | existing_capability | `simulation.solver_profile.create` |
| Simulation | `capability:simulation.solver_profile.get` | existing_capability | `simulation.solver_profile.get` |
| Simulation | `capability:simulation.solver_profile.search` | existing_capability | `simulation.solver_profile.search` |
