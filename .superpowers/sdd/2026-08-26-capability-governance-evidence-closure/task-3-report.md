# Task 3 — Complete frontend `/api/` discovery and classification

## Status

**BLOCKED** for governance closure, with the complete scanner, canonical evidence, drift checks, exact inventories, and completion integration implemented. The source scan is complete and assigns exactly one disposition to every discovered occurrence, but 219 occurrences truthfully remain `unresolved`. Closing those occurrences requires source-level method evidence and/or exact stable route registrations that do not exist in the current authoritative inputs. The frontend checkout was not modified.

## Authoritative scan

- Frontend checkout: `E:\Projects\ai00\workmanship-web`
- Full frontend revision: `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`
- Source content SHA-256: `4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c`
- Scan roots: `web`, `packages`
- Exclusions: `**/.git/**`, `**/__tests__/**`, `**/build/**`, `**/coverage/**`, `**/dist/**`, `**/dist-*/**`, `**/.next*/**`, `**/node_modules/**`, `**/out/**`, `**/tests/**`, `**/*.bundle.js`, `**/*.min.js`, `**/*.spec.*`, `**/*.test.*`
- Canonical evidence: `docs/governance/capability-coverage-review/generated/web_route_inventory.json`

| Disposition | Occurrences |
| --- | ---: |
| `capability` | 37 |
| `legacy_registered` | 188 |
| `bff_registered` | 0 |
| `operations_excluded` | 17 |
| `unresolved` | 219 |
| **Total** | **461** |

Prefixes are retained only as optional classification metadata. Discovery walks all eligible source files below both roots and is not prefix-limited. Every canonical occurrence has source, line, column, raw route, normalized route, inferred method or `null`, disposition, and an occurrence identity.

An independent `/api/` token-position audit found all 461 canonical route-literal positions and four additional lexical non-routes only: one JSDoc sentence, one JavaScript line comment, and two handbook prose/code-example references. There are no canonical positions missing from that audit. Filename-level `*.test.*` and `*.spec.*` exclusions are covered by a RED/GREEN regression test and do not affect the content hash.

The dynamic Capability Gateway is classified as `capability` per occurrence and is not treated as one business target. `GET /api/projects/members/matrix` has no occurrence in this frontend revision. It was not added to Legacy evidence, operations exclusions, or the BFF inventory; no aggregation model was fabricated.

## Unresolved classification

- 117 occurrences have no source-local authoritative HTTP method. They remain unresolved even when the same route has an exact method-specific registration or exclusion.
- 102 occurrences have an inferred method but no exact stable governed route target, exact BFF registration, or approved operational exclusion.
- Dynamic normalized paths such as `/api/{dynamic}` and `/api/{dynamic}/{dynamic}` remain unresolved because an exact business route cannot be proved.
- `PATCH /api/notifications/prefs` was deliberately left unresolved: the only candidate umbrella target is replaced and its atomic replacements do not contain a preferences-update capability.

The authoritative unresolved occurrence identities are listed in the appendix below.

## Operations exclusions

The exclusion ledger is `docs/governance/web-api-operations-exclusions.json`, validated by `docs/governance/web-api-operations-exclusions.schema.json`. It is exact-method/exact-route only, rejects wildcards, requires owner/reason/approval/expiry, and fails closed on duplicate or expired entries. All approvals reference `capability-governance-evidence-closure/task-3` and expire at `2026-11-21T23:59:59+08:00`.

- `GET /api/ai/admin-config` — owner `agent`; administrator connectivity configuration read.
- `GET /api/ai/tools` — owner `agent`; runtime tool-catalog introspection.
- `GET /api/flows/capability-manifest` — owner `agent`; generated editor-runtime manifest read.
- `POST /api/ai/admin-config` — owner `agent`; administrator connectivity configuration update.
- `POST /api/ai/test-connection` — owner `agent`; provider connectivity test.
- `POST /api/bop/pics/upload` — owner `craft`; raw picture transfer for a later Craft reference.
- `POST /api/file-store/config` — owner `platform-runtime`; deployment file-transfer adapter configuration.
- `POST /api/file-store/ois-config` — owner `platform-runtime`; deployment OIS adapter configuration.
- `POST /api/file-store/ois-test` — owner `platform-runtime`; deployment OIS connectivity test.
- `POST /api/file-store/test` — owner `platform-runtime`; deployment file-store connectivity test.
- `POST /api/import-export/lark-bitable/read` — owner `craft`; raw Lark Bitable transport read.
- `POST /api/import-export/lark-bitable/write` — owner `craft`; raw Lark Bitable transport write.
- `POST /api/import-export/lark-sheets/read` — owner `craft`; raw Lark Sheets transport read.
- `POST /api/import-export/lark-sheets/write` — owner `craft`; raw Lark Sheets transport write.
- `POST /api/uploads` — owner `platform-runtime`; transport upload-session creation.
- `POST /api/uploads/ois/resolve` — owner `platform-runtime`; OIS transport-reference resolution.
- `PUT /api/uploads/{dynamic}` — owner `platform-runtime`; byte transfer into an upload session.

The 17 `operations_excluded` occurrences are:

- `packages/agent-plugin/web/automation_hub/ai_assistant.js:156:37:GET:/api/ai/admin-config`
- `packages/agent-plugin/web/automation_hub/ai_assistant.js:926:32:GET:/api/ai/tools`
- `packages/agent-plugin/web/automation_hub/ai_settings.html:427:26:POST:/api/ai/admin-config`
- `packages/agent-plugin/web/automation_hub/ai_settings.html:434:37:GET:/api/ai/admin-config`
- `packages/agent-plugin/web/automation_hub/ai_settings.html:449:28:POST:/api/ai/admin-config`
- `packages/agent-plugin/web/automation_hub/ai_settings.html:456:38:POST:/api/ai/test-connection`
- `packages/agent-plugin/web/automation_hub/ai_settings.html:538:31:GET:/api/ai/admin-config`
- `packages/craft-plugin/web/lineage_view/lineage.js:1217:35:POST:/api/uploads/ois/resolve`
- `web/canvas/types/flow_type.js:129:20:GET:/api/flows/capability-manifest`
- `web/components/attachments_widget.js:162:34:POST:/api/uploads`
- `web/components/attachments_widget.js:171:42:POST:/api/uploads/ois/resolve`
- `web/container_card/modes/mode_markdown.js:77:42:PUT:/api/uploads/{dynamic}`
- `web/container_card/modes/mode_spreadsheet.js:57:40:PUT:/api/uploads/{dynamic}`
- `web/settings/settings.js:292:38:POST:/api/file-store/config`
- `web/settings/settings.js:309:36:POST:/api/file-store/test`
- `web/settings/settings.js:334:38:POST:/api/file-store/ois-config`
- `web/settings/settings.js:357:32:POST:/api/file-store/ois-test`

The other exact ledger entries do not classify a source occurrence when the method is ambiguous or the route is absent; they do not act as route-only allowlists.

## TDD evidence

RED was captured before implementation for complete non-prefix discovery, exact disposition joins, dynamic normalization, sibling scan roots, method-first wrappers, operational-exclusion validation, canonical stored/fresh equality, occurrence deletion drift, revision drift, and stored unresolved evidence. The initial failures included missing scanner APIs, missed HTML/template/optional-chaining occurrences, incorrect common-root identities, and completion returning only generic drift.

GREEN after implementation:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py backend\tests\test_repair_legacy_route_targets.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-final-tests-2 -p no:cacheprovider
48 passed in 11.63s
```

The final Legacy target audit is also green; newly registered routes point only to exact stable, non-replaced atomic targets. A preferences route with no valid atomic target was removed rather than mapped to a replaced umbrella.

## Fresh-vs-stored and completion gates

Fresh canonical evidence equals the stored file byte-for-byte:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=188 bff_registered=0 operations_excluded=17 unresolved=219 total=461
exit 0
```

The repository-only strict completion gate remains green:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=true; failed=[]; web_consumer_bypasses=0
exit 0
```

The external-Web strict gate fails only on the truthful unresolved occurrences, with no revision/content/occurrence drift:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
failed=[web_consumer_bypasses:219, web_route_inventory_unresolved:219]
exit 1
```

`check_web_capability_routes.py --check --fail-on-unresolved` likewise exits 1 with `web-route-inventory unresolved=219`.

## Files changed

- `backend/capability_v2/consumer_routes.py`
- `backend/capability_v2/completion.py`
- `backend/scripts/check_web_capability_routes.py`
- `backend/governance/capability_v2_completion.json`
- `backend/tests/test_capability_v2_consumer_routes.py`
- `backend/tests/test_capability_v2_completion.py`
- `docs/governance/legacy_route_inventory.json`
- `docs/governance/web-api-operations-exclusions.json`
- `docs/governance/web-api-operations-exclusions.schema.json`
- `docs/governance/capability-coverage-review/generated/web_route_inventory.json`
- `.superpowers/sdd/2026-08-26-capability-governance-evidence-closure/task-3-report.md`

No frontend files, production database state, BFF inventory, deprecated umbrella lifecycle, or unrelated untracked files were changed.

## Concerns and required follow-up

1. Frontend wrappers/constants need method-resolvable source structure or a reviewed source-aware method registry for the 117 method-ambiguous occurrences. Route equality alone is insufficient.
2. The 102 method-known occurrences need exact stable Legacy/BFF/capability registrations or explicit product removal. Several groups are live knowledge-hub, external-datasource, workbench, bitable-sync, and Craft work-plan routes.
3. Operations exclusions expire on 2026-11-21 and must be renewed, converted to governed targets, or removed before then.
4. If the matrix aggregate route reappears in frontend source, its BFF evidence must model the aggregation boundary and constituents before it can be `bff_registered`.

## Appendix A — all unresolved canonical occurrence identities

- `packages/agent-plugin/web/automation_hub/skill_lib.js:137:18:UNKNOWN:/api/skills/{dynamic}`
- `packages/agent-plugin/web/flow_canvas/flow_editor.js:77:33:UNKNOWN:/api/flows/capability-manifest`
- `packages/agent-plugin/web/flow_canvas/flow_editor.js:756:33:POST:/api/flows/test-node`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:681:35:UNKNOWN:/api/ai/chat/stream`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:1461:34:UNKNOWN:/api/ai/confirm`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:1596:42:POST:/api/skills/canvas-options`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:1611:47:POST:/api/skills/resume-canvas`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:1967:27:UNKNOWN:/api/ai/tools`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:2007:27:UNKNOWN:/api/skills`
- `packages/agent-plugin/web/wfc_window/wfc_window.js:2254:47:POST:/api/skills/execute-canvas`
- `packages/craft-plugin/web/approval/approval.js:153:26:POST:/api/approval/orders/{dynamic}/reject`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:33:43:UNKNOWN:/api/craft_lib/tools`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:33:85:UNKNOWN:/api/craft_lib/tools`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:34:43:UNKNOWN:/api/craft_lib/equipments`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:34:86:UNKNOWN:/api/craft_lib/equipments`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:35:43:UNKNOWN:/api/craft_lib/fixtures`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:35:86:UNKNOWN:/api/craft_lib/fixtures`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:36:42:UNKNOWN:/api/craft_lib/fasteners`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:37:42:UNKNOWN:/api/craft_lib/part_names`
- `packages/craft-plugin/web/craft_element_lib/craft_element_lib.js:96:42:UNKNOWN:/api/self_ann/batch`
- `packages/craft-plugin/web/craft_table/table.js:78:31:GET:/api/craft/work_plans`
- `packages/craft-plugin/web/craft_table/table.js:82:31:GET:/api/craft/work_plans/{dynamic}/sections`
- `packages/craft-plugin/web/craft_table/table.js:88:33:GET:/api/craft/sections/{dynamic}/operations`
- `packages/craft-plugin/web/craft_table/table.js:100:31:POST:/api/std_op/operations/{dynamic}/clone-to-post`
- `packages/craft-plugin/web/craft_table/table.js:492:19:POST:/api/craft/sections/{dynamic}/operations`
- `packages/craft-plugin/web/craft_table/table.js:516:38:GET:/api/craft/work_plans`
- `packages/craft-plugin/web/craft_table/table.js:520:38:GET:/api/craft/work_plans/{dynamic}/sections`
- `packages/craft-plugin/web/craft_table/table.js:529:33:GET:/api/craft/sections/{dynamic}/operations`
- `packages/craft-plugin/web/ebom/ebom.js:304:8:UNKNOWN:/api/ebom/snapshots`
- `packages/craft-plugin/web/ebom/ebom.js:305:8:UNKNOWN:/api/ebom/snapshots`
- `packages/craft-plugin/web/ebom/ebom.js:316:10:UNKNOWN:/api/ebom/snapshots`
- `packages/craft-plugin/web/ebom/ebom.js:317:10:UNKNOWN:/api/ebom/snapshots`
- `packages/craft-plugin/web/issue/issue.js:224:38:GET:/api/{dynamic}`
- `packages/craft-plugin/web/lineage_view/layout_detail_panel.js:2190:37:GET:/api/rule-engine/check-entry`
- `packages/craft-plugin/web/lineage_view/layout_detail_panel.js:3521:37:GET:/api/rule-engine/check-entry`
- `packages/craft-plugin/web/pbom_check/pbom_check.js:103:43:UNKNOWN:/api/ebom/snapshots`
- `packages/craft-plugin/web/pbom_check/pbom_check.js:157:47:UNKNOWN:/api/ebom/snapshots/{dynamic}/parts`
- `packages/craft-plugin/web/pbom_check/pbom_check.js:228:27:UNKNOWN:/api/ebom/vpps_check`
- `packages/craft-plugin/web/pbom_check/pbom_check.js:229:27:UNKNOWN:/api/vpps-operations/rule4-ignores`
- `packages/craft-plugin/web/pbom_check/pbom_check.js:349:49:UNKNOWN:/api/craft_lib/part_names`
- `packages/craft-plugin/web/pbom_check/pbom_check.js:762:10:UNKNOWN:/api/vpps-operations`
- `packages/craft-plugin/web/project/project.js:347:19:UNKNOWN:/api/grants`
- `packages/craft-plugin/web/std_op_lib/std_op_lib.js:72:22:UNKNOWN:/api/std_op/operations`
- `packages/craft-plugin/web/std_op_lib/std_op_lib.js:86:31:UNKNOWN:/api/std_op/operations/{dynamic}`
- `packages/craft-plugin/web/std_op_lib/std_op_lib.js:87:22:UNKNOWN:/api/std_op/operations`
- `packages/craft-plugin/web/std_op_lib/std_op_lib.js:114:38:UNKNOWN:/api/std_op/operations`
- `packages/craft-plugin/web/task/task.js:129:38:GET:/api/{dynamic}`
- `packages/plugin-sdk/template/web/app.js:32:36:GET:/api/my-plugin/items`
- `packages/plugin-sdk/template/web/app.js:71:23:POST:/api/my-plugin/items`
- `web/admin/ai_audit.html:122:19:UNKNOWN:/api/ai/audit-logs`
- `web/canvas/types/flow_type.js:145:20:POST:/api/flows/test-node`
- `web/components/bitable_sync_manager.js:50:45:UNKNOWN:/api/bitable-sync/bindings/{dynamic}/status`
- `web/components/bitable_sync_manager.js:79:33:POST:/api/bitable-sync/rows/push`
- `web/components/bitable_sync_manager.js:94:33:POST:/api/bitable-sync/bindings/{dynamic}/push`
- `web/components/bitable_sync_manager.js:109:33:POST:/api/bitable-sync/bindings/{dynamic}/pull`
- `web/components/bitable_sync_manager.js:164:12:UNKNOWN:/api/bitable-sync/bindings/{dynamic}/schema-by-token`
- `web/components/bitable_sync_manager.js:246:35:POST:/api/bitable-sync/bindings/{dynamic}`
- `web/components/bitable_sync_manager.js:262:45:UNKNOWN:/api/bitable-sync/bindings/{dynamic}`
- `web/components/bitable_sync_manager.js:271:31:DELETE:/api/bitable-sync/bindings/{dynamic}`
- `web/components/diff_manager.js:589:43:UNKNOWN:/api/import-export/export/diff-report`
- `web/components/diff_manager.js:622:43:UNKNOWN:/api/import-export/export/diff-lark-sheet`
- `web/components/diff_manager.js:647:41:UNKNOWN:/api/import-export/import/parse-excel`
- `web/components/import_export.js:236:47:UNKNOWN:/api/import-export/import/parse-excel`
- `web/components/import_export.js:324:41:UNKNOWN:/api/import-export/import/parse-excel`
- `web/components/import_export.js:337:41:UNKNOWN:/api/import-export/lark-sheets/read`
- `web/components/import_export.js:351:41:UNKNOWN:/api/import-export/lark-bitable/read`
- `web/components/import_export.js:578:42:UNKNOWN:/api/import-export/templates`
- `web/components/import_export.js:752:35:UNKNOWN:/api/import-export/templates/{dynamic}`
- `web/components/import_export.js:754:47:UNKNOWN:/api/import-export/templates`
- `web/components/import_export.js:809:41:UNKNOWN:/api/import-export/export/excel`
- `web/components/import_export.js:847:28:UNKNOWN:/api/import-export/lark-sheets/write`
- `web/components/import_export.js:870:28:UNKNOWN:/api/import-export/lark-bitable/write`
- `web/components/list_shell.js:581:24:DELETE:/api/{dynamic}/{dynamic}`
- `web/components/list_shell.js:590:24:DELETE:/api/{dynamic}/{dynamic}`
- `web/components/list_shell.js:635:30:UNKNOWN:/api/tasks/{dynamic}`
- `web/components/list_shell.js:636:30:UNKNOWN:/api/issues/{dynamic}`
- `web/components/list_shell.js:637:30:UNKNOWN:/api/rules/{dynamic}`
- `web/components/list_shell.js:638:30:UNKNOWN:/api/knowledge_entries/{dynamic}`
- `web/components/list_shell.js:640:54:UNKNOWN:/api/{dynamic}/{dynamic}`
- `web/components/list_shell.js:696:81:UNKNOWN:/api/{dynamic}`
- `web/components/list_shell.js:1130:83:UNKNOWN:/api/{dynamic}`
- `web/components/list_shell.js:1270:66:UNKNOWN:/api/rules`
- `web/components/quick_list.html:286:28:UNKNOWN:/api/lists`
- `web/components/quick_list.html:286:63:UNKNOWN:/api/tasks`
- `web/components/quick_list.html:287:28:UNKNOWN:/api/lists`
- `web/components/quick_list.html:287:63:UNKNOWN:/api/issues`
- `web/components/quick_list.html:288:28:UNKNOWN:/api/lists`
- `web/components/quick_list.html:288:63:UNKNOWN:/api/knowledge/entries`
- `web/components/quick_list.html:291:29:UNKNOWN:/api/ebom/snapshots`
- `web/components/quick_list.html:703:14:UNKNOWN:/api/ebom/snapshots/{dynamic}/parts`
- `web/components/quick_list.html:705:49:UNKNOWN:/api/{dynamic}`
- `web/components/quick_list.html:741:19:PUT:/api/tasks`
- `web/components/quick_list.html:757:19:PUT:/api/issues`
- `web/components/self_annotation_panel.js:293:10:UNKNOWN:/api/self_ann/list`
- `web/components/self_annotation_panel.js:294:10:UNKNOWN:/api/self_ann/list`
- `web/components/view_manager.js:540:20:UNKNOWN:/api/views`
- `web/components/visibility_selector.js:76:30:GET:/api/teams`
- `web/container_card/modes/container_item_detail.js:107:28:GET:/api/{dynamic}/{dynamic}`
- `web/container_card/modes/container_item_detail.js:129:16:PUT:/api/{dynamic}/{dynamic}`
- `web/container_card/modes/container_item_detail.js:148:28:POST:/api/{dynamic}`
- `web/container_card/modes/mode_field_detail.js:31:28:GET:/api/{dynamic}/{dynamic}`
- `web/container_card/modes/mode_field_detail.js:39:16:PUT:/api/{dynamic}/{dynamic}`
- `web/container_card/modes/mode_richtext.js:66:30:GET:/api/knowledge_hub/items/{dynamic}`
- `web/container_card/modes/mode_richtext.js:75:25:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/container_card/modes/mode_text_image.js:25:35:UNKNOWN:/api/{dynamic}/{dynamic}`
- `web/core/global_search.js:114:29:UNKNOWN:/api/tasks`
- `web/core/global_search.js:115:29:UNKNOWN:/api/issues`
- `web/core/global_search.js:133:29:UNKNOWN:/api/knowledge_hub/items`
- `web/core/global_search.js:134:29:UNKNOWN:/api/rules`
- `web/core/global_search.js:207:29:UNKNOWN:/api/lists`
- `web/core/global_search.js:219:29:UNKNOWN:/api/tasks`
- `web/core/global_search.js:222:29:UNKNOWN:/api/issues`
- `web/core/global_search.js:229:29:UNKNOWN:/api/knowledge_hub/items`
- `web/core/global_search.js:232:29:UNKNOWN:/api/rules`
- `web/core/notification_manager.js:23:38:UNKNOWN:/api/notifications/unread_count`
- `web/core/notification_manager.js:48:38:UNKNOWN:/api/notifications`
- `web/core/web_compat.js:277:27:UNKNOWN:/api/plugin/list`
- `web/core/web_compat.js:285:27:UNKNOWN:/api/plugin/install`
- `web/core/web_compat.js:295:27:UNKNOWN:/api/plugin/uninstall/{dynamic}`
- `web/ext_datasource/ext_ds.js:148:29:GET:/api/ext-datasources`
- `web/ext_datasource/ext_ds.js:187:29:GET:/api/ext-mappings`
- `web/ext_datasource/ext_ds.js:341:29:GET:/api/ext-mappings/{dynamic}/columns`
- `web/ext_datasource/ext_ds.js:349:29:GET:/api/ext-field-mappings`
- `web/ext_datasource/ext_ds.js:457:16:PUT:/api/ext-field-mappings/batch`
- `web/ext_datasource/ext_ds.js:496:29:GET:/api/ext-mappings/{dynamic}/preview`
- `web/ext_datasource/ext_ds.js:549:29:POST:/api/ext-mappings/{dynamic}/import`
- `web/ext_datasource/ext_ds.js:605:26:POST:/api/ext-datasources/{dynamic}/test`
- `web/ext_datasource/ext_ds.js:623:20:PATCH:/api/ext-datasources/{dynamic}`
- `web/ext_datasource/ext_ds.js:625:20:POST:/api/ext-datasources`
- `web/ext_datasource/ext_ds.js:640:29:GET:/api/ext-datasources/{dynamic}/tables`
- `web/ext_datasource/ext_ds.js:677:18:POST:/api/ext-mappings`
- `web/feishu/feishu.js:23:31:GET:/api/feishu/config`
- `web/knowledge/knowledge.js:87:22:UNKNOWN:/api/knowledge_entries`
- `web/knowledge/knowledge.js:98:33:UNKNOWN:/api/knowledge_entries/{dynamic}`
- `web/knowledge/knowledge.js:99:24:UNKNOWN:/api/knowledge_entries`
- `web/knowledge/knowledge.js:139:87:UNKNOWN:/api/knowledge_entries`
- `web/knowledge/knowledge.js:144:32:POST:/api/knowledge_entries`
- `web/knowledge_hub/knowledge_hub.js:44:32:GET:/api/knowledge_hub/folders`
- `web/knowledge_hub/knowledge_hub.js:47:32:GET:/api/knowledge_hub/favorites`
- `web/knowledge_hub/knowledge_hub.js:49:32:GET:/api/knowledge_hub/recent`
- `web/knowledge_hub/knowledge_hub.js:52:32:GET:/api/knowledge_hub/items`
- `web/knowledge_hub/knowledge_hub.js:52:85:UNKNOWN:/api/knowledge_hub/items`
- `web/knowledge_hub/knowledge_hub.js:57:18:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:60:18:DELETE:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:62:32:POST:/api/knowledge_hub/folders`
- `web/knowledge_hub/knowledge_hub.js:64:18:PATCH:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:66:18:DELETE:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:68:18:PATCH:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:71:32:POST:/api/knowledge_hub/items`
- `web/knowledge_hub/knowledge_hub.js:74:18:POST:/api/knowledge_hub/items/{dynamic}/recent`
- `web/knowledge_hub/knowledge_hub.js:181:32:GET:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:360:16:UNKNOWN:/api/knowledge_hub/folders`
- `web/knowledge_hub/knowledge_hub.js:516:37:GET:/api/knowledge_hub/favorites`
- `web/knowledge_hub/knowledge_hub.js:526:37:GET:/api/knowledge_hub/recent`
- `web/knowledge_hub/knowledge_hub.js:541:18:UNKNOWN:/api/knowledge_hub/items`
- `web/knowledge_hub/knowledge_hub.js:729:25:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:765:25:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:795:15:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:819:25:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:839:25:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:858:25:DELETE:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1005:27:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1039:16:UNKNOWN:/api/knowledge_hub/items/{dynamic}/recent`
- `web/knowledge_hub/knowledge_hub.js:1129:33:GET:/api/knowledge_hub/items/{dynamic}/history`
- `web/knowledge_hub/knowledge_hub.js:1152:30:GET:/api/item-entries/knowledge_item/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1174:31:POST:/api/knowledge_hub/folders`
- `web/knowledge_hub/knowledge_hub.js:1205:25:PATCH:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1244:27:PATCH:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1274:25:DELETE:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1417:27:PATCH:/api/knowledge_hub/folders/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1435:27:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/knowledge_hub/knowledge_hub.js:1566:31:GET:/api/knowledge_hub/items`
- `web/knowledge_hub/knowledge_hub.js:1701:24:POST:/api/knowledge_hub/items`
- `web/main.js:655:44:UNKNOWN:/api/share-links/{dynamic}`
- `web/main.js:1203:42:UNKNOWN:/api/tasks`
- `web/main.js:1487:43:UNKNOWN:/api/tasks/{dynamic}/entries`
- `web/main.js:1520:39:PUT:/api/tasks/{dynamic}/entries`
- `web/org_mgmt/org_mgmt.js:92:10:GET:/api/org/teams`
- `web/org_mgmt/org_mgmt.js:688:12:GET:/api/org/teams`
- `web/org_mgmt/org_mgmt.js:728:12:GET:/api/org/teams`
- `web/rule_mgmt/rule_mgmt.js:133:22:UNKNOWN:/api/rules`
- `web/rule_mgmt/rule_mgmt.js:144:33:UNKNOWN:/api/rules/{dynamic}`
- `web/rule_mgmt/rule_mgmt.js:145:24:UNKNOWN:/api/rules`
- `web/rule_mgmt/rule_mgmt.js:168:26:POST:/api/rules/{dynamic}/{dynamic}`
- `web/rule_mgmt/rule_mgmt.js:210:38:POST:/api/rules/{dynamic}/deviations`
- `web/rule_mgmt/rule_mgmt.js:252:79:UNKNOWN:/api/rules`
- `web/settings/settings.js:386:34:UNKNOWN:/api/file-store/config`
- `web/settings/settings.js:1375:44:UNKNOWN:/api/follows`
- `web/settings/settings.js:1384:47:UNKNOWN:/api/tasks/{dynamic}`
- `web/settings/settings.js:1389:47:UNKNOWN:/api/issues/{dynamic}`
- `web/settings/settings.js:1435:38:UNKNOWN:/api/notifications/prefs`
- `web/settings/settings.js:1446:38:PATCH:/api/notifications/prefs`
- `web/share/issues.html:178:40:GET:/api/{dynamic}`
- `web/workbench/workbench.js:190:32:UNKNOWN:/api/tasks`
- `web/workbench/workbench.js:191:32:UNKNOWN:/api/issues`
- `web/workbench/workbench.js:918:32:GET:/api/knowledge_hub/items/{dynamic}`
- `web/workbench/workbench.js:1219:43:UNKNOWN:/api/tasks`
- `web/workbench/workbench.js:2475:34:GET:/api/knowledge_hub/folders`
- `web/workbench/workbench.js:2763:29:POST:/api/knowledge_hub/items`
- `web/workbench/workbench.js:2804:49:UNKNOWN:/api/tasks`
- `web/workbench/workbench.js:2971:13:GET:/api/knowledge_hub/items`
- `web/workbench/workbench.js:2972:13:GET:/api/knowledge_hub/folders`
- `web/workbench/workbench.js:2974:13:GET:/api/knowledge_hub/folders`
- `web/workbench/workbench.js:2975:13:GET:/api/knowledge_hub/items`
- `web/workbench/workbench.js:3219:48:UNKNOWN:/api/issues/{dynamic}`
- `web/workbench/workbench.js:3219:76:UNKNOWN:/api/tasks/{dynamic}`
- `web/workbench/workbench.js:3379:23:PATCH:/api/knowledge_hub/items/{dynamic}`
- `web/workbench/workbench.js:3687:40:UNKNOWN:/api/issues/{dynamic}`
- `web/workbench/workbench.js:3687:68:UNKNOWN:/api/tasks/{dynamic}`
- `web/workbench/workbench.js:3696:40:UNKNOWN:/api/issues/{dynamic}`
- `web/workbench/workbench.js:3696:68:UNKNOWN:/api/tasks/{dynamic}`
- `web/workbench/workbench.js:3772:48:UNKNOWN:/api/issues/{dynamic}`
- `web/workbench/workbench.js:3772:76:UNKNOWN:/api/tasks/{dynamic}`
- `web/workbench/workbench.js:4444:45:UNKNOWN:/api/tasks/{dynamic}`
- `web/workbench/workbench.js:4444:67:UNKNOWN:/api/issues/{dynamic}`
- `web/workbench/workbench.js:4989:30:GET:/api/workbench/panel1`
- `web/workbench/workbench.js:5014:30:GET:/api/workbench/home`
- `web/workbench/workbench.js:5085:20:POST:/api/knowledge_entries`
- `web/workspace/nav_manager.js:366:47:UNKNOWN:/api/ai/balance`
