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

## Fix Round 1 — formal fail-closed evidence and semantic re-review

### Status

Fix Round 1 resolves both Critical, all three Important, and the Minor review findings. Governance closure remains **BLOCKED** by 391 explicit unresolved frontend route occurrences. The higher count is intentional: generic method guesses and semantically unproven Legacy registrations were removed rather than preserved for a lower number.

### RED/GREEN evidence

The clean initial RED run produced 12 expected failures covering generic callee inference, nested payload `method`, missing lexical audit, stored-evidence fail-open behavior, missing/non-Git frontend roots, lexical omission blocking, false AI targets, incorrect Lark operational exclusions, and missing semantic review evidence. Six further isolated RED cases proved arbitrary `.get()` inference, internally inconsistent lexical evidence, arbitrary method-first and options calls, quoted direct-fetch method keys, and commented method text were handled incorrectly before their fixes.

GREEN:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py backend\tests\test_repair_legacy_route_targets.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix1\focused-final-3 -p no:cacheprovider
66 passed in 20.59s
```

### Formal completion

Strict completion now always evaluates checked-in Web evidence even when `--web-root` is omitted. The repository-only progress view remains informational, while formal strict/static completion fails on stored unresolved evidence:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:391, web_route_inventory_unresolved:391]
exit 1
```

Supplying the frontend root performs a fresh verification and produces the same two blockers with no drift. Missing roots and directories that are not the exact Git top-level now raise a completion configuration error; `unversioned` is no longer accepted.

### Semantic review of Legacy additions

All 109 Legacy entries added in Task 3 were re-reviewed by exact method/route family against handler and provider evidence. The machine-readable review is `docs/governance/web-api-legacy-addition-review.json`.

- Original additions retained with exact traceable evidence: **90**.
- Original additions removed because one capability outcome was not proven: **19**.
- New exact Lark business registrations: **4**.
- Final Legacy inventory size: **317** entries (223 baseline + 90 retained + 4 Lark).

Named corrections:

- `POST /api/ai/chat`, `/api/ai/chat/stream`, and `/api/ai/confirm/sync` now target `agent.interaction.chat.change.apply`.
- `POST /api/ai/abort` now targets `agent.interaction.cancel`.
- `GET /api/ai/balance` was removed because its handler is an explicit HTTP 410 endpoint.
- Annotation routes now target the exact Project Workbench atomic outcomes and use the matching owner.
- Rule-engine and VPPS audit routes now target the capabilities their handlers actually invoke.
- Direct service/SQL routes without proven equivalence were removed, including grants, organization sync, self-annotations, users, views, and conditional list routes.

The four Lark Sheets/Bitable read/write endpoints were removed from operational exclusions and registered against `craft.data_exchange.lark.read` or `craft.data_exchange.lark.write`. Their frontend occurrences remain unresolved when source-local method evidence is absent.

### Fail-closed method inference

Only direct native `fetch` options, direct options on the tested `_cloudFetch(route, options)` wrapper, and the tested `_cf(method, route, ...)` wrapper contract infer methods. Generic final callees (`api`, `cf`, `fn`), arbitrary object methods such as `.get`, arbitrary options/method-first calls, nested payload `method` fields, and comments no longer determine the HTTP verb. Direct quoted or unquoted top-level `method` keys remain supported for the two options contracts.

### Independent lexical audit

The canonical report now contains an independently generated lexical `/api/` token count and hash:

- Lexical token count: **480**.
- Lexical token hash: `dfd56d82755c45bcb309f2093a1aa8e1434476e0fc3943574a690e261c3bd258`.
- Canonical route-literal tokens: **461**.
- Exact reviewed non-route tokens: **19** in `docs/governance/web-api-lexical-non-routes.json`.
- Unmatched/omitted tokens: **0**.

Any new syntax missed by the primary extractor becomes a listed lexical unmatched token and blocks completion. Stored evidence is also checked for internal count/hash/list consistency.

### Final authoritative dispositions

- `capability`: **37**
- `legacy_registered`: **24**
- `bff_registered`: **0**
- `operations_excluded`: **9**
- `unresolved`: **391** (**378** method-ambiguous, **13** method-known without an exact governed disposition)
- Total canonical route occurrences: **461**

Frontend revision remains `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`; source content hash remains `4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c`.

This report is retained locally for SDD coordination and is removed from the Git index in the Fix Round 1 commit, as required.

## Fix Round 2 — stored canonical validation and anchored semantic proof

### Status

Fix Round 2 resolves both remaining Critical findings and the Important full-callee finding. Formal completion remains **BLOCKED** by 408 explicit unresolved frontend occurrences. The increase from 391 is deliberate: qualified/object callees no longer inherit direct-wrapper contracts, and 38 additional Legacy registrations were removed when exact handler evidence could not prove their proposed targets.

### RED evidence

Stored artifact configuration, file presence, and count reconciliation:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_requires_stored_web_artifact_configuration backend\tests\test_capability_v2_completion.py::test_strict_completion_requires_stored_web_artifact_file backend\tests\test_capability_v2_completion.py::test_strict_completion_recomputes_unresolved_from_stored_routes -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\stored-red-2 -p no:cacheprovider
FFF
missing configuration: expected web_route_inventory_artifact_unconfigured:1, got no failure
missing file: raised CompletionConfigurationError instead of a stable blocker
forged count: expected recomputed unresolved=1, got web_consumer_bypasses=0
3 failed in 1.87s
```

Canonical route identity validation:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_noncanonical_stored_route -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\canonical-red -p no:cacheprovider
F
expected web_route_inventory_routes_invalid:1; only unresolved blockers were returned
1 failed in 1.54s
```

Full-callee method contracts:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_qualified_callee_does_not_inherit_direct_http_contract -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\callee-red -p no:cacheprovider
FFF
client.fetch, client._cf, and client._cloudFetch each incorrectly inferred POST
3 failed in 1.01s
```

Machine-verifiable Legacy proof:

```text
python -m pytest backend\tests\test_capability_v2_route_inventory.py::test_task3_legacy_addition_review_is_complete_and_traceable -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\ledger-red -p no:cacheprovider
F
KeyError: retained_count (the ledger had no anchored proof schema)
1 failed in 0.85s
```

### GREEN evidence

Stored artifact and canonical route checks:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_requires_stored_web_artifact_configuration backend\tests\test_capability_v2_completion.py::test_strict_completion_requires_stored_web_artifact_file backend\tests\test_capability_v2_completion.py::test_strict_completion_recomputes_unresolved_from_stored_routes backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_noncanonical_stored_route -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\stored-final -p no:cacheprovider
4 passed in 2.64s
```

Missing and non-Git frontend checks:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_fresh_web_verification_rejects_missing_frontend_root backend\tests\test_capability_v2_completion.py::test_fresh_web_verification_rejects_non_git_frontend_root -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\frontend-root-final -p no:cacheprovider
2 passed in 0.80s
```

Focused suite:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py backend\tests\test_repair_legacy_route_targets.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix2\focused-final-2 -p no:cacheprovider
73 passed in 23.40s
```

Fresh stored-evidence equality:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=7 bff_registered=0 operations_excluded=9 unresolved=408 total=461
exit 0
```

Stored and fresh strict gates agree:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:408, web_route_inventory_unresolved:408]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:408, web_route_inventory_unresolved:408]
exit 1
```

### Stored evidence validation

Strict/static completion now requires `web_route_inventory_artifact` and its file. Missing configuration and missing files produce stable blockers. Every stored route is checked for canonical fields, method/disposition, exact occurrence identity, and uniqueness. The five disposition counts are recomputed from those records; stored count mismatches cannot hide unresolved occurrences. The independent lexical evidence checks remain mandatory.

### Legacy semantic revalidation

The 109 original Task 3 additions were revalidated from exact Python handler AST ranges:

- Original additions retained with machine-verifiable proof: **52**.
- Original additions removed after revalidation: **57** (**38** newly removed in this round).
- Lark business registrations retained: **4**.
- Total anchored retained entries in the review ledger: **56**.
- Final Legacy inventory size: **279** entries (223 baseline + 52 proven original additions + 4 Lark).
- Proof kinds: **27** direct target invocations and **29** exact one-hop delegations.

Each retained ledger entry now records the exact source path, handler line range, SHA-256 of the anchored span, evidence kind, expected target invocation or delegation call, target capability/major, and—when delegated—the helper binding range/hash and target-bearing binding. The validator reads those source ranges, verifies their hashes and exact calls, and checks the target major against the stable catalog. Generic proof assertions and malformed Lark fragments were removed. Atomic registrations whose handlers only named a broader compatibility target, nonexistent cited handlers, and direct SQL/service outcomes remain removed.

### Full-callee inference

HTTP method contracts are matched against the complete callee. Only direct `fetch(...)`, direct `_cloudFetch(...)`, and direct `_cf(method, route, ...)` receive their tested contracts. Qualified forms such as `client.fetch`, `client._cloudFetch`, and `client._cf` remain `UNKNOWN` unless a future source-aware contract explicitly registers them.

### Final authoritative evidence

- `capability`: **37**
- `legacy_registered`: **7**
- `bff_registered`: **0**
- `operations_excluded`: **9**
- `unresolved`: **408** (**403** method-ambiguous, **5** method-known without an exact governed disposition)
- Total canonical route occurrences: **461**
- Lexical `/api/` tokens: **480** = **461** mapped + **19** exact reviewed non-routes + **0** unmatched
- Frontend revision: `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`
- Source content hash: `4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c`

## Fix Round 3 — authoritative stored disposition derivation

### Status

Fix Round 3 closes the remaining stored-label bypass. Formal completion remains **BLOCKED** by the same 408 truthful unresolved occurrences; the authoritative occurrence set and disposition counts did not change.

### RED evidence

The primary regression gives the stored artifact a method-ambiguous business route, forges its label to `legacy_registered`, and forges matching counts while an authoritative `GET /api/tasks` Legacy registration exists:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rederives_forged_stored_disposition -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\disposition-red-3 -p no:cacheprovider
F
expected web_consumer_bypasses=1; got 0 with failed=()
1 failed in 1.56s
```

The initial stored/fresh gate after classifier reuse exposed that stored indexes also needed the scanner's parameter canonicalization: the two session `{dynamic}` routes were re-derived differently. A mutation check that removes shared index canonicalization proves the parameterized regression catches that failure:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rederives_parameterized_stored_registration -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\parameter-index-red-2 -p no:cacheprovider
F
expected web_consumer_bypasses=0; got 1 with web_route_inventory_disposition_mismatch:1
1 failed in 1.59s
```

The stored validator must also derive the canonical route from the captured raw route rather than trusting an independently supplied normalized value:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_normalized_route_not_derived_from_raw -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\raw-normalized-red -p no:cacheprovider
F
expected web_route_inventory_routes_invalid:1; got no route-invalid failure
1 failed in 1.64s
```

### GREEN evidence

Primary forged-label regression:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rederives_forged_stored_disposition -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\regression-final -p no:cacheprovider
1 passed in 1.32s
```

Shared parameter index regression:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rederives_parameterized_stored_registration -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\parameter-index-green -p no:cacheprovider
1 passed in 1.31s
```

Raw-to-normalized canonical identity regression:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_normalized_route_not_derived_from_raw -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\raw-normalized-green-final -p no:cacheprovider
1 passed in 1.64s
```

Completion and consumer-route suites:

```text
python -m pytest backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_consumer_routes.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix3\focused-final-3 -p no:cacheprovider
60 passed in 24.49s
```

Fresh canonical evidence remains byte-identical:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=7 bff_registered=0 operations_excluded=9 unresolved=408 total=461
exit 0
```

Stored and fresh strict gates agree exactly:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:408, web_route_inventory_unresolved:408]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:408, web_route_inventory_unresolved:408]
exit 1
```

### Implementation

Stored validation now imports the scanner's public `classify_route_disposition`, `canonical_route_index`, and route normalizer. It rebuilds authoritative Legacy and BFF indexes from the current governed inventories, loads the exact operations exclusions through the same helper as a fresh scan, derives the canonical route from each captured raw route, re-derives every valid stored occurrence, and counts those derived dispositions. Any supplied label that differs emits `web_route_inventory_disposition_mismatch:<count>`; forged matching counts also fail against the derived totals. A supplied normalized route that does not equal the raw-route derivation is invalid. The shared classifier preserves the Capability Gateway contract before method matching, while UNKNOWN business routes remain unresolved and cannot match a method-specific registration by route alone.

## Fix Round 4 — source-anchored wrapper contracts and exact atomic route proofs

### Status

**BLOCKED.** This round makes a truthful backend improvement but does not claim the Task 3 acceptance target. The canonical frontend inventory is reduced from 408 unresolved occurrences to 182; stored and fresh strict gates agree on those 182. No frontend file was modified, no umbrella capability was revived, no aggregate route was forced into a single unrelated target, and the 66 remaining UNKNOWN-method occurrences retain the conservative unresolved fallback.

The backend improvement is committed as `4b112e5c07ada72536c5f26a6ee4bdaea045e002` (`fix: prove web wrapper and route contracts`). The frontend remains branch `test` at `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`; there is no frontend commit. Its untracked `dist-production/` and `dist-test-governance/` directories were not touched.

### Root-cause counts before and after

| Checkpoint | Capability | Legacy | BFF | Operations | Unresolved | Unresolved method split |
|---|---:|---:|---:|---:|---:|---|
| Round 4 baseline | 37 | 7 | 0 | 9 | 408 | 403 UNKNOWN, 5 known |
| Source-aware wrapper contracts only | 37 | 93 | 0 | 19 | 312 | 66 UNKNOWN, 246 known |
| Exact route proofs and one reviewed exclusion | 37 | 222 | 0 | 20 | 182 | 66 UNKNOWN, 116 known |

The wrapper registry therefore proves 337 previously UNKNOWN methods without changing the scanner's UNKNOWN fallback. Exact Legacy proofs then resolve 129 further occurrences, and the reviewed operations exclusion resolves one. Total source occurrences remain 461 throughout.

The final 182 blockers are partitioned without overlap, in precedence order:

| Root-cause family | Count | Required next action |
|---|---:|---|
| Method still UNKNOWN after checked contracts | 66 | Add only source-derived finite branches/contracts, or minimally refactor the frontend helper so its route and method are statically explicit. |
| Method-known runtime resource builders (`/api/{dynamic}` or `/api/{dynamic}/{dynamic}`) | 11 | Derive a finite route set from source constants/branches or refactor the builder; a wildcard inventory entry is forbidden. |
| Aggregate/conditional List and Workbench routes | 19 | Model a BFF boundary with constituents, or split the frontend calls. The current BFF schema carries one `capability_id` and cannot truthfully express these aggregates. |
| Base identity/view/grant/annotation/org/notification contract gaps | 37 | Introduce exact reviewed Base outcomes only where the existing handler semantics justify them, then bind the handlers. |
| Other exact method-known routes lacking a proven stable atomic target | 49 | Remove/remap stale frontend APIs or introduce the exact owning-domain contract after handler/provider review. This includes bitable sync, external datasource/mapping, retired Craft work-plan/section calls, Agent canvas/test calls, rule-engine checks, task entries, plugin-template examples, and remaining exact Craft/approval routes. |
| **Total** | **182** | |

The named load-bearing domain blocker is `GET /api/users` (six frontend occurrences). Its handler is `backend/routers/users.py::list_users`, which calls `user_service.list_users()` directly. The catalog has the write/synchronization outcome `base.identity.directory.sync`, but no stable read/search outcome matching this handler. The missing contract is proposed as `base.identity.directory.search`, owned by Base. Creating that domain capability is outside this evidence/route-repair round.

### Checked wrapper-contract registry

`docs/governance/web-api-wrapper-contracts.json` is schema version 1 with 63 contracts over 55 caller sources: 54 exact options-argument contracts and 9 constant-method contracts. The loader also supports a checked method-argument position, exercised by behavior tests, but no current production entry needs that mode.

Each entry is keyed by the exact `(source, callee)` pair and contains:

- the full caller-source SHA-256;
- an exact callee without glob characters;
- an exact route argument position;
- one of `constant`, `method_argument`, or `options_argument` method semantics;
- for options mode, an exact options argument position and explicit default method;
- an anchored wrapper-definition `source_path`, inclusive line span, SHA-256, and required definition substring.

Representative anchors include `packages/core/electron/preload.js:264-278` for `window._cloudFetch`, `web/components/list_shell.js:1211-1215` for `ListShell._cf`, `web/components/list_shell.js:1160-1163` for `this.cf`, and `packages/plugin-sdk/frontend/plugin-sdk.js:47-50` for `AI00.fetch`. The registry rejects stale caller hashes, stale definition hashes/ranges, absent sources, duplicate `(source, callee)` keys, wildcard paths/callees, unexpected fields, and invalid/overlapping argument positions. A contract applies only to its exact caller source and full callee; all other calls remain on the existing direct-call inference and UNKNOWN fallback.

The scanner report now records the semantic wrapper registry hash. Strict stored evidence requires the configured registry to exist and parse, and rejects a stored report whose `wrapper_contracts_hash` differs from the current registry.

### Exact governed targets and exclusion added

Against the round-start review, 76 exact route specifications gained retained proofs. They resolve through the shared classifier and are grouped as follows:

- Project, 46 specifications: task and task-dependency read/change atoms; issue read/change atoms; exact List create/item-entry atoms; follow read/change atoms; notification read/change atoms; approval read/change and scope-upgrade atoms; sharing/share-link atoms; task-template read/instantiate atoms; permission-request create; change-log read; and Workbench annotation read/change.
- Knowledge, 18 specifications: hub folder/item read/change atoms; item history; favorites and recent read/change atoms; entry create/update/delete atoms; and the existing exact `knowledge.search`/`knowledge.get` outcomes.
- Craft, 8 specifications: rule library read/change, EBOM VPPS check read, VPPS audit read, and exact data-export outcomes.
- Base, 3 specifications: export-template read/change.
- Agent, 1 specification: `POST /api/ai/confirm` to `agent.interaction.chat.change.apply`.

The retained semantic evidence uses six checked proof kinds: `capability_invocation`, `exact_delegation`, `facade_operation_invocation`, `facade_operation_delegation`, `facade_operation_delegation_chain`, and `atomic_composition_invocation`. Every proof has an anchored source span and SHA-256. Facade-operation proofs additionally verify the exact operation literal and require the target to be an atomic replacement declared by `capability-atomicity-dispositions.json`. Knowledge composition proofs anchor the exact construction `capability_id = f"{capability_id}.atomic.{operation.replace('.', '_')}"`. Approval transition proofs anchor both delegation hops. No production router was changed.

The only new operations exclusion is `GET /api/file-store/config`, owned by `platform-runtime`, approved under `capability-governance-evidence-closure/task-3-fix-round-4`, expiring `2026-11-21T23:59:59+08:00`. It reads deployment file-transfer adapter configuration and does not execute a business outcome.

No BFF registration was added. `GET /api/workbench/home`, `GET /api/workbench/panel1`, and conditional List routes remain unresolved because the current BFF inventory cannot encode their constituent capabilities.

### RED evidence

Wrapper anchoring and modes failed before the registry API existed:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_source_anchored_wrapper_contract_resolves_group_through_shared_classifier backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_modes_use_exact_signature_positions backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_stale_source_and_definition_anchors backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_ambiguous_and_wildcard_contracts -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix4\wrapper-red-3 -p no:cacheprovider
4 failed
AttributeError: module 'backend.capability_v2.consumer_routes' has no attribute 'load_wrapper_contracts'
```

Stored wrapper-registry drift initially was not enforced:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_stored_wrapper_contract_hash_drift -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix4\wrapper-hash-red-1 -p no:cacheprovider
1 failed
expected web_wrapper_contracts_evidence_drift:1; blocker absent
```

Exact adapter-family expectations failed before their governed targets existed:

```text
python -m pytest backend\tests\test_capability_v2_route_inventory.py::test_round4_exact_adapter_families_have_governed_targets -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix4\routes-red-1 -p no:cacheprovider
1 failed
expected exact route targets were missing
```

An initial attempt to reuse broad facade targets was rejected by the existing replacement guard:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py backend\tests\test_repair_legacy_route_targets.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix4\focused-green-1 -p no:cacheprovider
82 passed, 2 failed
45 legacy_route_inventory_artifact:target_replaced failures
```

Those failures forced the final exact atomic targets; no umbrella exception was added.

### GREEN evidence

Wrapper contracts and exact signature positions:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_source_anchored_wrapper_contract_resolves_group_through_shared_classifier backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_modes_use_exact_signature_positions backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_stale_source_and_definition_anchors backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_ambiguous_and_wildcard_contracts -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix4\wrapper-green-1 -p no:cacheprovider
4 passed in 1.28s
```

The two former Round 4 registry/hash command blocks were removed because they
cited stale pytest node names. They are not accepted as verification evidence;
Fix Round 5 below replaces them with a fresh command over the real test files.

Final focused scanner, completion, inventory-proof, and replacement-guard suites:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py backend\tests\test_repair_legacy_route_targets.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix4\focused-final-5 -p no:cacheprovider
84 passed in 25.45s
```

`python -m compileall -q backend\capability_v2\consumer_routes.py backend\capability_v2\completion.py backend\scripts\check_web_capability_routes.py` and `git diff --check` both exit 0.

### Canonical evidence and strict gates

The regenerated canonical artifact is pinned to:

- frontend revision: `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`
- frontend content hash: `4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c`
- wrapper-contract semantic hash: `f46a3c3d1653b6dc7db5af0e6e977a74c83bb158ddbf5d9cf2f748da703ce75d`
- lexical token count/hash: `480` / `dfd56d82755c45bcb309f2093a1aa8e1434476e0fc3943574a690e261c3bd258`
- mapped/reviewed-non-route/unmatched lexical counts: `461` / `19` / `0`

Fresh regeneration is byte-identical:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=222 bff_registered=0 operations_excluded=20 unresolved=182 total=461
exit 0
```

Stored and fresh strict gates agree exactly and fail only on the truthful residual inventory:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:182, web_route_inventory_unresolved:182]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:182, web_route_inventory_unresolved:182]
exit 1
```

There is no revision drift, content drift, lexical omission, wrapper-registry drift, stored/fresh mismatch, wildcard contract, or forged disposition blocker. The remaining blocker is semantic coverage, not evidence integrity.

## Fix Round 5 — fail-closed wrapper and Legacy proof hardening

### Status

**BLOCKED on the truthful residual route inventory.** The six review findings
are fixed and committed as `e14d3105` (`fix: harden web governance evidence`).
The strict stored and fresh gates agree on 356 unresolved occurrences; neither
gate reports a wrapper-contract, Legacy-proof, lifecycle, source-anchor, drift,
or metadata failure. Task 3 therefore remains incomplete rather than claiming
false zero coverage.

The frontend remains revision
`dd67726d4881ec56eb8bb1df88b3c6e938166fa9`. No frontend file was changed, and
the pre-existing untracked `dist-production/` and `dist-test-governance/`
directories remain untouched.

### Review findings closed

1. Options-mode inference now rejects spreads, shorthand `method`, computed
   properties/methods, method accessors, and duplicate method keys. Default GET
   is retained only for a checked options-mode contract and an absent,
   `undefined`, or unambiguous literal options object. Direct `fetch` options
   with an override spread no longer fall back to GET.
2. Wrapper contracts are schema version 2. The original 63 heuristic contracts
   were reduced to 14 proved function declarations/assignments with 97 exact
   hashed call-site ranges. Each contract checks its exact callee, declaration
   kind, full declared parameter list, definition range/hash, caller source
   hash, and call-site range/hash. Definitions injected in comments, strings,
   or regex text cannot satisfy a binding. Five preload exposure patterns and
   all other unproved definitions were removed rather than parsed heuristically.
3. Strict completion now loads
   `docs/governance/web-api-legacy-addition-review.json` and audits both sides of
   the Legacy proof relation. The inventory has 355 entries, exactly 132 of
   which carry the durable
   `web-api-legacy-addition-review/<scope>` provenance marker. The proof artifact
   has exactly 132 active retained proofs and 22 removed review records. Missing,
   orphaned, duplicate, stale-anchor, target mismatch, and non-stable target
   states are blocking production failures.
4. The unapproved `GET /api/file-store/config` exclusion was deleted. That GET
   occurrence is unresolved again; the existing POST exclusion and all other
   pre-existing exclusion records were left unchanged.
5. The stale Round 4 pytest-node citations above were removed. The commands in
   this section name tests that exist in the committed tree and use fresh
   basetemps with `-p no:cacheprovider`.
6. The Round 4 delta is exactly **76** route keys/proofs: **35 re-retained + 41
   new**. These values are stored as independently checked entry markers and
   derived metadata. No five additional records were created.

### RED evidence

Options ambiguity, exact binding/scope, and declared signatures all failed
before the schema-v2 implementation:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_options_contract_fails_closed_on_runtime_method_overrides backend\tests\test_capability_v2_consumer_routes.py::test_options_contract_defaults_get_only_for_unambiguous_object backend\tests\test_capability_v2_consumer_routes.py::test_direct_fetch_options_spread_does_not_fall_back_to_get backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_applies_only_to_anchored_call_scope backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_mismatched_declared_signature -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix5\wrapper-red-valid-2 -p no:cacheprovider
8 failed
```

The production Legacy proof relation, exclusion removal, and 35/41/76 metadata
were not enforced before this round:

```text
python -m pytest backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_inventory_entry_without_active_proof backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_active_proof_without_inventory_entry backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_duplicate_active_legacy_proof backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_stale_legacy_proof_source_hash backend\tests\test_capability_v2_completion.py::test_strict_completion_rejects_invalid_legacy_proof_target_lifecycle backend\tests\test_capability_v2_route_inventory.py::test_unapproved_file_store_read_is_not_operations_excluded backend\tests\test_capability_v2_route_inventory.py::test_task3_legacy_addition_review_is_complete_and_traceable -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix5\proof-red -p no:cacheprovider
7 failed
```

A final adversarial binding test exposed regex-literal definition spoofing and
forced declaration-prefix anchoring:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_injected_definition_text -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix5\regex-injection-red -p no:cacheprovider
1 failed, 1 passed
```

### GREEN evidence

The final focused scanner, completion, inventory/proof, and target-repair suites:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py backend\tests\test_repair_legacy_route_targets.py -q --basetemp=E:\Projects\ai00_v3\.tmp\task3-fix5\focused-final-2 -p no:cacheprovider
102 passed in 29.82s
```

`python -m compileall -q backend\capability_v2\consumer_routes.py
backend\capability_v2\route_inventory.py backend\capability_v2\completion.py
backend\scripts\check_web_capability_routes.py` and `git diff --check` both exit
0.

### Canonical evidence and strict gates

The schema-v2 registry hash is
`92683f26e54d6eb1f6d8de0f71a33aba1f765595fd1cbfe02e83e8a015f39a60`.
Fresh generation is byte-identical to the stored artifact:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=53 bff_registered=0 operations_excluded=15 unresolved=356 total=461
exit 0
```

The residual is 313 UNKNOWN-method and 43 method-known occurrences. Stored and
fresh strict gates agree and fail only on that residual:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:356, web_route_inventory_unresolved:356]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:356, web_route_inventory_unresolved:356]
exit 1
```

## Task 3B.1 — Close Proof Scope and Wrapper Occurrence Integrity

### Status and commit

**COMPLETE for the Task 3B.1 integrity scope; Task 3 remains blocked only on
the truthful 356 unresolved Web occurrences.** The implementation is committed
as `9657f41ab04ae7c0d70311334f88293bc271c7f7` (`fix: bind governance proof
scope and wrapper occurrences`). The stored and fresh strict gates report no
Legacy-baseline, Legacy-proof, wrapper-contract, source-anchor, lifecycle,
revision, content, occurrence, lexical, or artifact drift failure.

The frontend remains read-only at
`dd67726d4881ec56eb8bb1df88b3c6e938166fa9`. Its pre-existing untracked
`dist-production/` and `dist-test-governance/` directories remain untouched.

### Immutable Legacy proof scope

`docs/governance/legacy_route_baseline.json` is generated only from:

```text
git show 565b00a0fdd13ea7d163d6b0ec0e9cb9bf05d924:docs/governance/legacy_route_inventory.json
```

The canonical artifact records the full source commit, source artifact, exact
sorted `(method, normalized_route)` keys, key count, and canonical key hash:

- immutable source commit:
  `565b00a0fdd13ea7d163d6b0ec0e9cb9bf05d924`;
- immutable key count: `223`;
- canonical-key SHA-256:
  `5fb96dafb709888877589ae8e54e68415d87fca837d55cf1a3ea0e2a28f92b04`;
- baseline artifact file SHA-256:
  `490ae62827c03cef42a1918a1af103fcd21916eda0e6086125471d0256263ba2`.

`backend/scripts/build_legacy_route_baseline.py --write|--check` executes the
Git lookup and never reads the current inventory as its source. Strict
completion independently pins the expected commit, count, source artifact,
and canonical-key hash. Commit, hash, count, ordering, duplicate-key, or
source-artifact drift returns a stable blocking reason.

The active proof scope is now exactly:

```text
normalized current Legacy keys - immutable baseline keys
```

The current inventory has `355` normalized keys; its difference from the
`223`-key baseline is exactly `132` keys. The proof artifact has exactly `132`
active retained proofs and `22` removed review records. The active proof keys
biject exactly to the difference. `evidence_provenance` no longer selects the
scope; it remains a checked descriptive binding after the independent scope
is established. Missing proof, orphan proof, duplicate proof, duplicate
normalized inventory key, removed/mismatched provenance, stale evidence
anchor, target mismatch, and non-stable target all fail closed.

### Exact wrapper occurrence binding

`docs/governance/web-api-wrapper-contracts.json` is schema version `3`. It
preserves the `14` grouped wrapper-definition/signature contracts from Round 5
and replaces the `97` line-range call sites with `97` unique exact occurrence
anchors. Each call anchor contains:

- exact source path;
- line and column of the `/api/` route token;
- raw route and normalized route;
- full call-source SHA-256.

The call-source hash must equal the grouped contract source hash even for the
stored-only gate. During a fresh scan, an anchor applies only when source,
callee, line, column, raw route, normalized route, and source hash all match
the discovered occurrence, while the existing definition range/hash,
declaration kind, parameters, expected definition, and signature checks also
pass. Same-line calls and shadowed same-name wrappers therefore do not inherit
one another's method contract. A moved column, changed route, stale source
hash, duplicate identity, or missing occurrence fails as contract drift.

- wrapper-contract semantic SHA-256:
  `8c2a0bfec9e2cc3034054951425db869464e32d7ef10199eb421178eb674ac1d`;
- wrapper artifact file SHA-256:
  `551e17846bd20d9d7515dca8672c30a1fda769a3526b2f29b7ea63a30e847197`;
- regenerated Web evidence file SHA-256:
  `2edde3aaec4a4f6a515fd09170cc46172682c0397306fa7ab9e577611e316621`.

No weak contract removed in Round 5 was restored.

### RED evidence

The initial completion RED established the provenance-removal bypass and the
absence of immutable-baseline enforcement:

```text
python -m pytest backend/tests/test_capability_v2_completion.py -q -p no:cacheprovider --basetemp=.pytest-task3b1-red-baseline
3 failed, 39 passed in 23.22s
failures: provenance+proof removal was accepted; changed baseline commit and changed baseline hash were accepted
```

The exact wrapper schema and occurrence behavior failed before production
changes:

```text
python -m pytest backend/tests/test_capability_v2_consumer_routes.py -q -p no:cacheprovider --basetemp=.pytest-task3b1-red-wrapper -k "exact_wrapper"
4 failed, 45 deselected in 0.75s
failures: schema v3/exact anchors unsupported for same-line shadowing, moved column, stale call-source hash, and bijection
```

Three subsequent one-case RED mutations closed independently required edges:

```text
removed descriptive provenance: 1 failed; expected legacy_route_proof_target_mismatch:1, got no failure
duplicate normalized current inventory key: 1 failed; expected legacy_route_proof_inventory_duplicate:1, got no failure
stale per-call source hash at loader boundary: 1 failed; expected RouteScanConfigurationError, got no exception
```

Each was followed by a one-case GREEN run before proceeding. The baseline
phase reached `42 passed`; the four exact-wrapper cases reached `4 passed`;
the final focused suite below includes every regression.

### Final focused tests and static checks

```text
python -m pytest backend/tests/test_capability_v2_consumer_routes.py backend/tests/test_capability_v2_completion.py backend/tests/test_capability_v2_route_inventory.py backend/tests/test_repair_legacy_route_targets.py -q -p no:cacheprovider --basetemp=.pytest-task3b1-final-focusedc
112 passed in 31.59s
exit 0
```

The first attempted combined run used a fresh path under
`E:\Projects\ai00_v3\.tmp`, whose inherited Windows ACL denied pytest access;
it produced setup errors and is not treated as test evidence. The command was
rerun unchanged with the fresh writable worktree basetemp shown above.

```text
python -c "... jsonschema.validate(wrapper contracts, wrapper schema) ..."
wrapper-schema valid

python -m compileall -q backend/capability_v2/completion.py backend/capability_v2/consumer_routes.py backend/capability_v2/route_inventory.py backend/scripts/build_legacy_route_baseline.py
exit 0

git diff --check
exit 0
```

### Canonical evidence and strict gates

The immutable baseline check is byte-identical to the Git-derived artifact:

```text
python backend/scripts/build_legacy_route_baseline.py --check
legacy-route-baseline checked: commit=565b00a0fdd13ea7d163d6b0ec0e9cb9bf05d924 keys=223 sha256=5fb96dafb709888877589ae8e54e68415d87fca837d55cf1a3ea0e2a28f92b04
exit 0
```

The fresh frontend scan is byte-identical to stored evidence:

```text
python backend/scripts/check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=53 bff_registered=0 operations_excluded=15 unresolved=356 total=461
exit 0
```

Stored-only and fresh strict completion agree exactly. Both exit `1` only for
the truthful unresolved-route residual:

```text
python backend/scripts/check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:356, web_route_inventory_unresolved:356]
exit 1

python backend/scripts/check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:356, web_route_inventory_unresolved:356]
exit 1
```

There is no integrity or drift failure in either gate. Canonical occurrence
counts remain `461 = 37 capability + 53 Legacy + 0 BFF + 15 operations + 356
unresolved`; this task intentionally performs no missing-capability or
frontend remediation.

### Files changed

- `backend/capability_v2/completion.py`
- `backend/capability_v2/consumer_routes.py`
- `backend/capability_v2/route_inventory.py`
- `backend/governance/capability_v2_completion.json`
- `backend/scripts/build_legacy_route_baseline.py`
- `backend/tests/test_capability_v2_completion.py`
- `backend/tests/test_capability_v2_consumer_routes.py`
- `backend/tests/test_capability_v2_route_inventory.py`
- `docs/governance/capability-coverage-review/generated/web_route_inventory.json`
- `docs/governance/legacy_route_baseline.json`
- `docs/governance/web-api-wrapper-contracts.json`
- `docs/governance/web-api-wrapper-contracts.schema.json`

### Self-review

- Confirmed proof scope is never selected by current provenance markers.
- Confirmed every current non-baseline normalized key has exactly one active
  proof and every active proof has exactly one current non-baseline key.
- Confirmed all 132 active targets remain stable and all proof anchors validate.
- Confirmed every wrapper call anchor is unique and its source hash equals the
  grouped contract source hash; canonical fresh scan validates every exact
  occurrence against the read-only frontend.
- Confirmed no dependency, production database, BFF inventory, umbrella
  lifecycle, frontend file, or unrelated/untracked backend file was changed.
- Confirmed frontend status is unchanged with only the two pre-existing
  untracked distribution directories.

### Fix Round 1 — wrapper binding-resolution integrity

**COMPLETE.** Commit
`fec80716a3b2dc8549d65ae9a27701394578997c` (`fix: reject ambiguous wrapper
bindings`) closes the remaining exact-anchor resolution bypass. Definition and
call occurrence proof is now accepted only when the definition anchor is in the
same source as the contracted calls and the contracted callee has exactly one
conservatively recognized binding/assignment in that complete source. The
same-source invariant is enforced both while loading the JSON artifact and
again by the scanner, so constructing a `WrapperContract` directly cannot
bypass it.

The binding uniqueness check runs over the complete comment-masked source,
rather than the definition anchor fragment. It recognizes exact supported
function/member definitions and conservative same-name declaration,
assignment, class, catch-binding, and single-argument arrow forms. A nested
same-name wrapper or later reassignment invalidates the entire grouped
contract before any call occurrence can inherit its method semantics.

#### Strict RED/GREEN evidence

The three required negative cases all failed against the pre-fix loader and
scanner. The first test explicitly anchored both the outer call and the
different-semantics inner shadowed call; both were incorrectly accepted before
the fix:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_exact_wrapper_contract_rejects_anchored_shadowed_binding backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_cross_source_definition backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_additional_callee_assignment -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix1-red
3 failed in 1.07s
failures: anchored nested shadow accepted; cross-source definition accepted; additional same-name assignment accepted
```

A separate loader-bypass RED proved that the scanner did not itself enforce
the cross-source invariant:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_scanner_rejects_cross_source_definition_if_loader_is_bypassed -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix1-red-scanner
1 failed in 0.76s
expected definition-source ambiguity; received only missing-definition-source drift
```

After the production changes, the four exact negative regressions passed:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_exact_wrapper_contract_rejects_anchored_shadowed_binding backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_cross_source_definition backend\tests\test_capability_v2_consumer_routes.py::test_scanner_rejects_cross_source_definition_if_loader_is_bypassed backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_additional_callee_assignment -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix1-green2
4 passed in 0.98s
```

The two older shadowing expectations were then aligned with the new
fail-closed invariant: exact occurrence scope remains covered with a unique
definition, while any source containing a second binding is rejected even if
only the outer occurrence was anchored.

#### Final focused tests and canonical evidence

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix1
107 passed in 31.07s
exit 0
```

All current production wrapper definitions are already in the same source as
their calls and each has one accepted binding. No production contract or call
anchor was removed or added:

```text
contracts=14 call_sites=97 semantic_hash=8c2a0bfec9e2cc3034054951425db869464e32d7ef10199eb421178eb674ac1d
contract delta=0 call-site delta=0
```

The read-only canonical Web check remains byte-identical to stored evidence:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=53 bff_registered=0 operations_excluded=15 unresolved=356 total=461
exit 0
```

Stored-only and fresh strict completion again agree exactly and contain no
wrapper-contract, source-binding, occurrence, revision, content, or artifact
drift failure:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:356, web_route_inventory_unresolved:356]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:356, web_route_inventory_unresolved:356]
exit 1
```

`python -m compileall -q backend\capability_v2\consumer_routes.py
backend\tests\test_capability_v2_consumer_routes.py` and `git diff --check`
both exited `0` before commit. The frontend remained at
`dd67726d4881ec56eb8bb1df88b3c6e938166fa9`; only its pre-existing untracked
`dist-production/` and `dist-test-governance/` directories were present and
neither was touched.

### Fix Round 2 — closed-world wrapper reference proof

**COMPLETE.** Commit
`169c912c3e887f4ad69308af901e7629fa18e704` (`fix: close wrapper reference
scope`) replaces the enumerated binding-pattern check from Fix Round 1 with a
closed-world identifier-reference proof.

For each contract, the scanner now derives the exact identifier span of the
machine-proved grouped definition and the exact callee span of every anchored
call occurrence. After comment/string masking, including preservation of code
inside template-literal interpolations, the complete source must contain no
other matching terminal callee identifier. The comparison is exact-set
equality, so an ordinary parameter, nested binding, import, destructuring,
assignment, alias, property key/shorthand, unanchored call, or other unmatched
reference invalidates the entire grouped contract before method inference.
Qualified contracts are conservative as well: the terminal property identifier
is checked everywhere, not only behind the originally contracted object.

#### Strict RED/GREEN evidence

The review's ordinary-parameter reproducer explicitly anchored both the outer
and parameter-shadowed calls. Along with destructuring, static import, alias,
and unrelated property-name cases, all five negative cases were incorrectly
accepted before the closed-world implementation:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_exact_wrapper_contract_rejects_anchored_parameter_shadow backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_unproved_callee_reference -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix2-red
5 failed in 0.88s
```

A second RED demonstrated that masking a whole template literal would hide a
real `${request}` code reference:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_unproved_callee_reference -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix2-template-red
1 failed, 4 passed in 0.68s
failure: `${request}` interpolation was accepted
```

The initial closed-world cases and the positive definition-plus-exact-anchors
case passed after replacing the syntax enumeration:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_exact_wrapper_contract_rejects_anchored_parameter_shadow backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_unproved_callee_reference backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_accepts_only_definition_and_exact_call_references -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix2-green
6 passed in 0.99s
```

The template-aware masking repair then passed all five unmatched-reference
variants plus the positive case:

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_rejects_unproved_callee_reference backend\tests\test_capability_v2_consumer_routes.py::test_wrapper_contract_accepts_only_definition_and_exact_call_references -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix2-template-green
6 passed in 0.76s
```

#### Contract and canonical evidence changes

The closed-world production audit retained only the approval, task-planning,
and container-item-detail contracts. Eleven grouped contracts and 73 call
anchors were removed; none were weakened or replaced:

```text
before: contracts=14 call_sites=97 semantic_hash=8c2a0bfec9e2cc3034054951425db869464e32d7ef10199eb421178eb674ac1d
after:  contracts=3  call_sites=24 semantic_hash=32d10dab46359a55ca2a0c9c48648c4f313b27cee7f0371d14bd4f08162ff68a
delta:  contracts=-11 call_sites=-73
wrapper artifact SHA-256=9f9b726021c001cd97d42da0b5394e9704a1a8d02218eb24b1cdc0d6af66b602
Web evidence SHA-256=865df1648c70351e19427da58c040202194babbf00a87c31ce18dc8e92a2ebd2
```

Regeneration intentionally increased unresolved occurrences from 356 to 387.
The 31-count increase is smaller than the 73 removed anchors because calls with
independently explicit methods remain classified without a wrapper contract.
The final stored evidence is:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00\workmanship-web --check
frontend_revision=dd67726d4881ec56eb8bb1df88b3c6e938166fa9 content_hash=4ff63012ef42c69f1bfde891ba0dfa096a0708cf7c332a5844f3a554d517794c capability=37 legacy_registered=28 bff_registered=0 operations_excluded=9 unresolved=387 total=461
exit 0
```

#### Final tests, static checks, and strict gates

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.tmp\task3b1-fix2
114 passed in 30.74s
exit 0
```

Wrapper schema validation, `python -m compileall -q
backend\capability_v2\consumer_routes.py
backend\tests\test_capability_v2_consumer_routes.py`, and `git diff --check`
all exited `0` before commit.

Stored-only and fresh strict completion agree exactly and fail only for the
truthful unresolved residual:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:387, web_route_inventory_unresolved:387]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00\workmanship-web
complete=false
failed=[web_consumer_bypasses:387, web_route_inventory_unresolved:387]
exit 1
```

The frontend remained read-only at
`dd67726d4881ec56eb8bb1df88b3c6e938166fa9`. Its only status entries remained
the pre-existing untracked `dist-production/` and `dist-test-governance/`
directories.

## Task 3B.2

### Status and commits

Task 3B.2 is complete. All 379 frontend call occurrences whose HTTP method was
previously `UNKNOWN` now have explicit, statically provable source methods.
Runtime route selection, request payloads, headers, response handling, and
error behavior were preserved; no capability target was guessed, no backend
scanner rule was weakened, and no operations exclusion was added.

The frontend was committed first, then the backend artifacts were regenerated
against that exact commit and committed separately:

```text
frontend 06fb5da0a05707a61dcf5ab0ea86e6ce4c1c794a
         fix: make frontend HTTP methods explicit
backend  0e3f52f1206d66a39e03d8a2013fc1da95ebe6fc
         docs: refresh explicit web method evidence
```

The frontend commit contains 69 tracked files. The backend commit contains
only the canonical Web route inventory and lexical-anchor ledger. This report
is local task evidence and is intentionally not part of either commit.

### Canonical evidence before and after

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Total call occurrences | 461 | 476 | +15 |
| Capability | 37 | 37 | 0 |
| Legacy registered | 28 | 272 | +244 |
| BFF registered | 0 | 0 | 0 |
| Operations excluded | 9 | 19 | +10 |
| Unresolved, all methods | 387 | 148 | -239 |
| Unresolved `UNKNOWN` method | 379 | 0 | -379 |
| Lexically unmatched calls | 379 | 0 | -379 |

The total rose by 15 because finite configuration branches that previously
hid a method behind a value now contain explicit source occurrences. This is
truthful evidence expansion, not duplicated runtime behavior.

The final canonical scan is:

```text
python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check
frontend_revision=06fb5da0a05707a61dcf5ab0ea86e6ce4c1c794a
content_hash=5f8831d642713d7be7504e5819b6029654e9fba6b36d83e78b5cb4688b8c68e5
capability=37 legacy_registered=272 bff_registered=0 operations_excluded=19 unresolved=148 total=476
exit 0
```

The 148 residuals all have known methods: `GET=81`, `POST=30`, `PATCH=17`,
`DELETE=10`, and `PUT=10`. The Task 3B.2 acceptance condition is therefore
met: unresolved `UNKNOWN=0`.

### Frontend families closed

Work proceeded by wrapper/component family rather than by assigning targets to
individual routes. The table partitions the 379 baseline unknown-method calls
exactly:

| Source family | Before `UNKNOWN` | After `UNKNOWN` |
| --- | ---: | ---: |
| Workbench and generic list orchestration (`workbench`, `list_shell`, `quick_list`, `list_sidebar`, `list_tree`, `list_nav`) | 73 | 0 |
| Knowledge and rule surfaces (`knowledge_hub`, `gbop_vpps`, `knowledge`, `factory_info`, `rule_mgmt`) | 79 | 0 |
| Craft plugin modules (EBOM/PBOM, task/issue, craft element/table, standard operation, BOP/lineage/project) | 80 | 0 |
| Shared HTTP-enabled components (import/export, bitable, view, scope/self-annotation, diff, subscribe, attachment, detail/container modes, notification, visibility) | 54 | 0 |
| Agent, canvas, and plugin surfaces (WFC, skill/workflow/flow canvas, canvas type, SDK sample, AI audit) | 32 | 0 |
| Platform, organization, settings, and search (external datasource, settings, org/team, global search/main, ontology, Web compatibility, Feishu/navigation) | 61 | 0 |
| **Total** | **379** | **0** |

The implementation uses explicit method-first wrapper signatures, scoped local
aliases whose method is fixed at definition time, and explicit finite method
branches for configuration-driven components. `ListShell` callback extensions
carry the already-known method to `ListSidebar`. A semantic audit found and
fixed one primary `ListSidebar` bridge that had dropped that method, then added
a regression assertion. It also replaced unsafe bare `_cloudFetch` references
in WFC, PBOM, bitable, main, and global-search code with scoped/bound aliases,
preserving the prior absent-client behavior.

### TDD and frontend verification

The new dependency-free regression test is
`scripts/test_batch_explicit_http_methods.js`. Its first wrapper assertion was
run before implementation and failed because the method-first route/options
ordering did not yet exist. The same test passed after the wrapper conversion.
The later `ListSidebar` semantic audit produced an additional regression case
for forwarding the explicit method through the primary bridge.

Final frontend verification:

```text
npm test
134 passed, 0 failed

node --check <each of 60 changed production/configuration JavaScript files and the new test>
all passed

npm run build:web (existing dependency tree read-only; temporary Vite config;
output E:\Projects\ai00_v3\.runtime\task3b2-web-build)
passed

git -c core.whitespace=cr-at-eol diff --check
exit 0
```

No package install or dependency change was made. The existing original
frontend dependency tree was used read-only through `NODE_PATH`; the original
frontend checkout and both of its untracked `dist` directories were never
modified. Build output was isolated under `.runtime`, and the temporary scan
helper was removed before the frontend commit.

### Backend verification and strict gates

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.runtime\pytest-task3b2-final
114 passed in 26.99s

python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check
exit 0; byte-equal canonical evidence

python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check --fail-on-unresolved
web-route-inventory unresolved=148
exit 1 (expected known-method Task 3B.3 residual only)

python backend\scripts\check_capability_v2_completion.py --mode strict
complete=false
failed=[web_consumer_bypasses:148, web_route_inventory_unresolved:148]
exit 1

python backend\scripts\check_capability_v2_completion.py --mode strict --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance
complete=false
failed=[web_consumer_bypasses:148, web_route_inventory_unresolved:148]
exit 1
```

Stored-only and fresh strict completion agree exactly. There are no evidence
drift, revision, content-hash, lexical-integrity, wrapper-contract, or test
failures. The lexical ledger changed only five line anchors caused by the
frontend edits: `list_shell 1158 -> 1182`, `list_sidebar 898 -> 902`,
`web_compat 335 -> 331`, `main 1063 -> 1068`, and `workbench 4963 -> 4956`.
Their exact comment tokens and reasons are unchanged. The operations ledger,
legacy inventory, and wrapper contracts are unchanged.

### Exact known-method residual families for Task 3B.3

The 148 residual occurrences cover 76 normalized route families. The repeated
families are:

```text
12  GET     /api/lists
10  DELETE=2 GET=3 PATCH=3 PUT=2  /api/{dynamic}/{dynamic}
 8  DELETE=2 PATCH=6                /api/lists/{dynamic}
 6  GET                               /api/users
 5  GET                               /api/self_ann/batch
 4  GET=3 POST=1                      /api/{dynamic}
 4  GET=2 POST=2                      /api/views
 3  DELETE=1 GET=1 POST=1             /api/bitable-sync/bindings/{dynamic}
 3  GET=2 POST=1                      /api/craft/sections/{dynamic}/operations
 3  GET=1 POST=2                      /api/grants
 3  GET                               /api/org/teams
 3  GET                               /api/self_ann/list
 3  GET                               /api/users/search
 3  DELETE=1 PATCH=2                  /api/views/{dynamic}
 2  GET                               /api/ai/audit-logs
 2  GET                               /api/ai/balance
 2  GET                               /api/craft/work_plans
 2  GET                               /api/craft/work_plans/{dynamic}/sections
 2  GET=1 POST=1                      /api/ext-datasources
 2  GET=1 POST=1                      /api/ext-mappings
 2  POST                              /api/flows/test-node
 2  PUT                               /api/issues
 2  GET=1 POST=1                      /api/my-plugin/items
 2  GET=1 PATCH=1                     /api/notifications/prefs
 2  GET                               /api/rule-engine/check-entry
 2  GET=1 PUT=1                       /api/self_ann/{dynamic}
 2  PATCH                             /api/std_op/operations/{dynamic}
 2  PUT                               /api/tasks
 2  GET=1 PUT=1                       /api/tasks/{dynamic}/entries
 2  PATCH                             /api/users/{dynamic}/role
```

The 46 singleton families are:

```text
/api/approval/orders/{dynamic}/reject
/api/bitable-sync/bindings/{dynamic}/pull
/api/bitable-sync/bindings/{dynamic}/push
/api/bitable-sync/bindings/{dynamic}/schema-by-token
/api/bitable-sync/bindings/{dynamic}/status
/api/bitable-sync/rows/push
/api/craft_lib/equipments/{dynamic}
/api/craft_lib/equipments/{dynamic}/obsolete
/api/craft_lib/equipments${listGid
/api/craft_lib/fasteners${listGid
/api/craft_lib/fixtures/{dynamic}
/api/craft_lib/fixtures/{dynamic}/obsolete
/api/craft_lib/fixtures${listGid
/api/craft_lib/part_names${listGid
/api/craft_lib/tools/{dynamic}/obsolete
/api/craft_lib/tools${listGid
/api/ext-datasources/{dynamic}
/api/ext-datasources/{dynamic}/tables
/api/ext-datasources/{dynamic}/test
/api/ext-field-mappings
/api/ext-field-mappings/batch
/api/ext-mappings/{dynamic}/columns
/api/ext-mappings/{dynamic}/import
/api/ext-mappings/{dynamic}/preview
/api/feishu/config
/api/file-store/config
/api/grants/{dynamic}
/api/issues${listGid
/api/knowledge/entries
/api/knowledge/entries${listGid
/api/org/sync-from-feishu
/api/plugin/install
/api/plugin/list
/api/plugin/uninstall/{dynamic}
/api/rules/{dynamic}/{dynamic}
/api/rules/{dynamic}/deviations
/api/skills/canvas-options
/api/skills/execute-canvas
/api/skills/resume-canvas
/api/std_op/operations/{dynamic}/clone-to-post
/api/tasks${listGid
/api/teams
/api/users/me
/api/views/{dynamic}/copy
/api/workbench/home
/api/workbench/panel1
```

The `${listGid` spellings above are the scanner's truthful normalization of
existing dynamic template forms; they must not be mapped until Task 3B.3 has
exact stable target evidence. The canonical inventory is the exhaustive
source of file, line, method, and classification evidence for every residual.

### Self-review and concerns

The frontend and backend tracked worktrees are clean at their respective
commits. Review found no invented target mapping, new exclusion, dependency
change, dist artifact, or scanner weakening. The only remaining concern is the
intentional known-method residual of 148 occurrences. That is Task 3B.3 scope:
it requires evidence-backed route-to-capability/BFF/legacy classification and
must not be closed by guessing from route shape, especially for dynamic
templates.

### Fix Round 1

Review identified two concrete gaps: the dependency-free regression test did
not execute every transformation shape claimed by the implementation report,
and `web/org_mgmt/org_mgmt.js` had routed capability calls through the shared
best-effort `_cf` helper. Because `_cf` catches transport exceptions and
returns `null`, that change replaced the original unavailable/network errors
with a generic capability error.

#### Commits

```text
frontend 7848e30803ada6cc687c9e8b3b14ce4020254886
         fix: preserve explicit frontend request behavior
backend  800ec6ba559db3301221e674b2a5026d354214ff
         docs: refresh web evidence after behavior review
```

The frontend commit extends the existing dependency-free test and restores
the original `invokeCapability` error semantics. The backend commit contains
only the regenerated canonical Web inventory for the exact frontend SHA.

#### Review-added behavior coverage

This is review-added regression proof, not a claim of historical test-first
coverage for the original batch rewrite. The expanded harness executes real
production definitions in controlled VM contexts and asserts exact route,
method, argument order, dispatch count, headers/body/options, and signals:

| Transformation shape | Executed representative | Protected behavior |
| --- | --- | --- |
| Method-first wrapper | `web/ext_datasource/ext_ds.js` `_cf` | explicit method overrides stale `opts.method`; route, headers, body, signal, and single dispatch preserved |
| Bound/local alias | `web/components/bitable_sync_manager.js` `pushAll` | bound receiver, POST route/body/headers, state transition, and single dispatch preserved |
| Finite configuration closures | `web/components/quick_list.html` `TYPE_API.issue` | list/data/save branches select exact GET/GET/PUT requests without duplicate dispatch |
| Streaming and abort signal | WFC SSE `_cf` | POST order, runtime URL, auth headers, JSON body, signal identity, one fetch, and streamed token/done callbacks preserved |
| Import/export consolidation | `ImportExportManager._cf` | PATCH body serialization and GET body omission preserved through the consolidated transport |
| ListShell/ListSidebar delegates | `buildLoadHandler`, `buildRowsChangeHandler`, and `ListSidebar._cf` | canonical query, update/create payloads, reload count, explicit method precedence, and arbitrary options preserved |
| Error semantics | `org_mgmt.invokeCapability` | explicit unavailable-service error and original transport exception propagate unchanged |

The harness accepts an optional frontend root. Against the untouched base
checkout at `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`, six of nine cases fail:

```text
node scripts\test_batch_explicit_http_methods.js E:\Projects\ai00\workmanship-web
failed 6/9
failed: method-first wrapper; finite configuration closures; streaming/signal;
        import/export consolidation; ListShell delegates; ListSidebar forwarding
passed: bound/local alias; both original org error-semantics cases
exit 1
```

The bound-alias base case passes because that source rewrite deliberately
preserved runtime behavior; the test protects against a future unbound alias
losing the transport receiver. Both org cases passing on the base is direct
evidence of the feature regression.

Before the production repair, the same harness against the feature worktree
passed all six transformation shapes but failed both org error cases:

```text
7 passed, 2 failed
failed: org unavailable-service error; org transport-error propagation
exit 1
```

After the repair:

```text
node scripts\test_batch_explicit_http_methods.js
9 passed, 0 failed
exit 0
```

#### Runtime repair and scanner check

`invokeCapability` now resolves the underlying transport into a scoped
`_cloudFetch` alias, throws `云端服务未连接` when it is absent, and calls it
directly with explicit POST. It no longer crosses the exception-swallowing
`_cf` path, so request exceptions propagate with their original message and
identity. The shared `_cf` remains unchanged for existing callers that
intentionally use best-effort/null behavior.

An intermediate direct alias named `cf` preserved runtime behavior but the
fail-closed scanner correctly could not prove its method (`method=null`). The
final scoped `_cloudFetch` spelling is the existing recognized direct-call
shape. A temporary generation probe then showed `method=null=0` before the
frontend commit was finalized. No wrapper contract or scanner rule changed.

#### Final frontend verification

```text
npm test
134 passed, 0 failed; all dependency-free entrypoint/default/docs/fixture/runtime checks passed

node --check scripts\test_batch_explicit_http_methods.js
node --check web\org_mgmt\org_mgmt.js
git -c core.whitespace=cr-at-eol diff --check
all exit 0

AI00_WEB_BUILD_PROFILE=production vite build --config E:\Projects\ai00_v3\.runtime\task3b2-vite.config.mjs
174 modules transformed; built in 938ms; exit 0
output only E:\Projects\ai00_v3\.runtime\task3b2-web-build
```

The Vite warnings about classic scripts lacking `type="module"` are the
repository's existing warnings. No dependency was installed. The original
frontend remained at `dd67726d` with only its pre-existing untracked
`dist-production/` and `dist-test-governance/` directories, and the feature
worktree acquired no dist directory.

#### Final backend evidence and gates

```text
python -m pytest backend\tests\test_capability_v2_consumer_routes.py backend\tests\test_capability_v2_completion.py backend\tests\test_capability_v2_route_inventory.py -q -p no:cacheprovider --basetemp=E:\Projects\ai00_v3\.runtime\pytest-task3b2-fix1-final
114 passed in 27.30s
exit 0

python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check
frontend_revision=7848e30803ada6cc687c9e8b3b14ce4020254886
content_hash=227927b5c91ae24747115ccea4ab72097b951be0dd4d96c8f954455984a71b38
capability=37 legacy_registered=272 bff_registered=0 operations_excluded=19 unresolved=148 total=476
method=null=0 lexical_unmatched=0
exit 0

python backend\scripts\check_web_capability_routes.py --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check --fail-on-unresolved
web-route-inventory unresolved=148
exit 1 (expected Task 3B.3 known-method residual only)

stored strict completion:
failed=[web_consumer_bypasses:148, web_route_inventory_unresolved:148]
exit 1

fresh strict completion against frontend 7848e308:
failed=[web_consumer_bypasses:148, web_route_inventory_unresolved:148]
exit 1
```

Stored and fresh strict gates remain identical. Counts and the 148
known-method residual families are unchanged from the main Task 3B.2 report;
only the frontend provenance/content hash and `org_mgmt` line anchors changed.
There are no new exclusions, mappings, dependencies, or unresolved UNKNOWN
methods.

## Task 3B.3a — Classify and Close Existing-Outcome Route Families

**COMPLETE for the Task 3B.3a scope.** The pinned 148 known-method
occurrences are represented exactly once in a reviewed 93-key root-cause
ledger. Every exact existing stable mapping, proven dead/410/sample call, and
finite route normalization authorized by this task is closed. No Capability,
BFF, operations approval, or same-name target guess was created. Formal Task 3
completion remains blocked only by the explicit residual contract families
recorded below.

### Baselines and commits

```text
backend base  800ec6ba559db3301221e674b2a5026d354214ff
frontend base 7848e30803ada6cc687c9e8b3b14ce4020254886

frontend b6d154dd75acf6eb0555a365591e20bb41c70c54
         fix: close classified legacy web routes
backend  2198c9b08d93687f65bd14468cc8f376aa24f29f
         docs: classify existing web route outcomes
```

The baseline canonical content hash is
`227927b5c91ae24747115ccea4ab72097b951be0dd4d96c8f954455984a71b38`.
The final frontend content hash is
`1bce0e94067b98dfa159dc5ccc74262ea7da3c18b59f29e5c9bdfb1701de00fb`.
Canonical evidence is bound to the exact frontend commit `b6d154dd`.

### Root-cause ledger

`docs/governance/web-route-root-cause-ledger.json` contains all 93 baseline
`(method, normalized_route)` groups and all 148 immutable occurrence IDs. The
loader/auditor validates the pinned frontend revision/content hash, duplicate
keys and occurrence IDs, counts, per-source baseline blob hashes, backend
source anchors, stable lifecycle/owner for exact existing targets, stable BFF
constituents, retirement/normalization evidence, absence of operations
approval, and exact reconciliation to the final canonical unresolved set.
`build_web_route_root_cause_ledger.py --check` independently reconstructs the
pinned source hashes from frontend Git blobs and compares the rendered ledger
byte-for-byte.

| Disposition | Groups | Baseline occurrences | Task 3B.3a result |
| --- | ---: | ---: | --- |
| `existing_stable_capability` | 5 | 7 | Exact Legacy registrations and production proof added |
| `frontend_retire` | 17 | 21 | Dead, 410, or sample-only network calls removed |
| `frontend_route_normalize` | 14 | 22 | Malformed/dynamic expressions replaced by finite branches |
| `truthful_bff_required` | 51 | 91 | Deferred as explicit BFF gaps |
| `new_atomic_capability_required` | 4 | 4 | Deferred as explicit atomic-outcome gaps |
| `operations_candidate` | 2 | 3 | Kept unresolved; no approval exists |
| **Total** | **93** | **148** | **Every pinned occurrence appears exactly once** |

### Exact existing-stable closures

Only the five handler-proven keys below were added to the Legacy inventory.
Each proof has an immutable handler/invocation or delegation/binding anchor in
`web-api-legacy-addition-review.json`; the production proof bijection passes.

| Route key | Baseline occurrences | Exact stable target |
| --- | ---: | --- |
| `GET /api/ai/audit-logs` | 2 | `agent.audit.read@1` |
| `PATCH /api/std_op/operations/{gid}` | 2 | `craft.standard_operation.change.apply@1` |
| `POST /api/craft_lib/tools/{gid}/obsolete` | 1 | `craft.library.change.apply@1` |
| `POST /api/craft_lib/equipments/{gid}/obsolete` | 1 | `craft.library.change.apply@1` |
| `POST /api/craft_lib/fixtures/{gid}/obsolete` | 1 | `craft.library.change.apply@1` |

The reviewed retained-proof count moves from 132 to 137. No direct
SQL/service handler was mapped merely because a Capability name looked
similar.

### Frontend retirement and finite normalization

The 17 retired groups / 21 occurrences comprise eight Bitable sync calls,
two AI-balance polling occurrences whose backend is HTTP 410, seven V1 craft
work-plan/section/operation occurrences whose router is an explicit tombstone,
one HTTP-410 standard-operation clone call, two plugin-SDK sample calls, and
one Feishu mock-config call. The retained compatibility/sample surfaces now
resolve locally and do not dispatch network requests.

The 14 normalized groups / 22 occurrences comprise eight malformed query
templates and six generic item-route shapes. Each dynamic item type is now a
closed task/issue/knowledge/rule branch, unsupported types fail explicitly,
and concrete route, HTTP method, body/options, and runtime error behavior are
preserved. The obsolete five-call `_cf` wrapper contract was removed because
those call sites are now explicit finite method-first requests; the exact
wrapper-anchor invariant is 19 rather than 24.

The retirement removed 21 scanner occurrences while finite expansion added 21
concrete occurrences, so total discovered calls remain 476. The meaningful
coverage change is:

| Evidence | Before | After |
| --- | ---: | ---: |
| Total discovered | 476 | 476 |
| Capability | 37 | 37 |
| Legacy registered | 272 | 311 |
| Operations excluded | 19 | 19 |
| Unresolved occurrences | 148 | 109 |
| Unresolved route groups | 93 | 64 |
| UNKNOWN methods | 0 | 0 |
| Lexical unmatched | 0 | 0 |

### Exact residual contract families

The final 64 groups / 109 occurrences reconcile exactly as follows:

- **Truthful BFF required — 51 groups / 91 occurrences.** Exact families are
  external datasource/mapping (12); authorization grants (3); conditional
  project/craft lists (3); notification preferences (2); organization/team
  (3); self annotations (4); identity/users (4); saved views (5); workbench
  aggregates (2); approval rejection (1); task/issue/knowledge collection
  update facades (3); task entry adapters (2); plugin install/uninstall (2);
  rule evaluate/deviation (2); and skill-canvas options/execute/resume (3).
  Every ledger entry records its exact stable constituents and why the current
  REST handler is not provider-equivalent proof.
- **New atomic Capability required — 4 groups / 4 occurrences:**
  `DELETE /api/craft_lib/equipments/{dynamic}`,
  `DELETE /api/craft_lib/fixtures/{dynamic}`, `GET /api/plugin/list`, and
  `POST /api/rules/{dynamic}/{dynamic}`. Each entry records the proposed
  owner, bounded outcome/input/output, provider/handler evidence, and why no
  exact stable target exists.
- **Operations approval gap — 2 groups / 3 occurrences:**
  `GET /api/file-store/config` and `POST /api/flows/test-node`. Both remain
  `approval_status=not_approved`; this task adds no exclusion.
- **Finite post-normalization contract gaps — 7 groups / 11 occurrences:**
  `DELETE /api/knowledges/{dynamic}` (1),
  `GET /api/knowledge/entries` (1),
  `GET /api/knowledges/{dynamic}` (3),
  `PATCH /api/knowledges/{dynamic}` (1), `POST /api/knowledges` (1),
  `PUT /api/knowledges/{dynamic}` (2), and
  `PUT /api/rules/{dynamic}` (2). These are the explicit concrete
  Capability/BFF adapter gaps exposed by removing generic route ambiguity;
  no target was invented in this package.

### TDD evidence

RED was captured before implementation. The backend ledger test initially
failed during collection because `backend.capability_v2.route_root_cause_ledger`
did not exist. The frontend behavior/source harness initially failed the
retired-Bitable no-dispatch check and the Task 3B.3a finite-source closure.
After the wrapper contract was removed, the combined backend run also exposed
the stale exact anchor count (`24` versus the reviewed artifact's `19`); that
focused regression was kept and turned green before the full rerun.

GREEN/final verification:

```text
NODE_PATH=E:\Projects\ai00_v3\workmanship-web\node_modules npm test
Task 3B.3a behavior/source cases pass; full Web suite 134/134 passes;
all web-only defaults/docs/entrypoint/fixture/runtime checks pass
exit 0

node --check <all 14 modified JavaScript files>
14 files pass
exit 0

AI00_WEB_BUILD_PROFILE=production NODE_PATH=E:\Projects\ai00_v3\workmanship-web\node_modules \
  E:\Projects\ai00_v3\workmanship-web\node_modules\.bin\vite.cmd build \
  --outDir E:\Projects\ai00_v3\.tmp\workmanship-web-3b3a-final-build-20260827-a
172 modules transformed; built in 1.17s
exit 0

python -m pytest backend\tests\test_capability_v2_consumer_routes.py \
  backend\tests\test_capability_v2_route_inventory.py \
  backend\tests\test_capability_v2_completion.py -q \
  --basetemp E:\Projects\ai00_v3\.tmp\pytest-task3b3a-postcommit-20260827-a \
  -p no:cacheprovider
115 passed in 27.17s
exit 0

python -m compileall -q backend\capability_v2\route_root_cause_ledger.py \
  backend\scripts\build_web_route_root_cause_ledger.py \
  backend\scripts\check_web_capability_routes.py
exit 0

python backend\scripts\build_web_route_root_cause_ledger.py \
  --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance \
  --check
baseline_occurrences=148 baseline_groups=93 final_unresolved=109 final_groups=64
exit 0

python backend\scripts\check_web_capability_routes.py \
  --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance \
  --check
frontend_revision=b6d154dd75acf6eb0555a365591e20bb41c70c54
content_hash=1bce0e94067b98dfa159dc5ccc74262ea7da3c18b59f29e5c9bdfb1701de00fb
capability=37 legacy_registered=311 bff_registered=0 operations_excluded=19
unresolved=109 total=476
exit 0
```

The explicit unresolved gate fails truthfully rather than masking the residual:

```text
python backend\scripts\check_web_capability_routes.py \
  --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance \
  --check --fail-on-unresolved
web-route-inventory unresolved=109
exit 1 (expected residual contract gaps)
```

Stored-only and fresh strict completion agree exactly:

```text
python backend\scripts\check_capability_v2_completion.py --mode strict
python backend\scripts\check_capability_v2_completion.py --mode strict \
  --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance

failed=[web_consumer_bypasses:109, web_route_inventory_unresolved:109]
exit 1 for each (expected residual contract gaps only)
```

There is no revision/content/occurrence drift, proof-bijection failure,
wrapper-registry drift, lexical omission, unknown method, new dependency,
production DB mutation, new approval, push, merge, force operation, or
subagent work. The frontend's existing untracked `dist-production/` directory
was preserved. The production build emitted the repository's existing classic
script `type="module"` warnings only. Unrelated backend untracked files and
restricted historical pytest directories were left untouched.

### Fix Round 1 — Existing-outcome classification and proof hardening

**COMPLETE for all six Fix Round 1 findings.** The ledger now reconstructs
its immutable baseline independently from backend Git commit
`800ec6ba559db3301221e674b2a5026d354214ff`, preserves every baseline
occurrence field verbatim, promotes every post-normalization residual to a
first-class group, and distinguishes true aggregation from conditional
dispatch and from migration to an existing stable outcome. No Capability,
BFF, approval, exclusion, dependency, production-DB change, push, or merge was
created.

#### Exact commits and evidence identity

```text
frontend c1804e94ad8a3c4660be6bebb1b010744ed8da6f
         fix: make finite route outcomes explicit
backend  2c17617c28e0bed2411763e9ae5520128f2804e0
         fix: validate existing route outcome classifications

baseline backend inventory commit
         800ec6ba559db3301221e674b2a5026d354214ff
baseline inventory SHA-256
         55f3de074e060a71dc6acab4bee993d42d7af05026e6acd4c0e8d7f6d06b9694
baseline frontend content hash
         227927b5c91ae24747115ccea4ab72097b951be0dd4d96c8f954455984a71b38
final frontend content hash
         58400ca2fc26c2c29f87d1b43def748bd3f32d515714fe7084258893037779a0
```

The generator obtains the baseline bytes only with
`git show 800ec6ba...:docs/governance/capability-coverage-review/generated/web_route_inventory.json`.
It no longer reads the mutable current inventory or falls back to a previous
ledger. The auditor compares all persisted baseline fields, including optional
classification fields, by occurrence ID and rejects a fabricated or replaced
record. It also rechecks the full commit, artifact path, byte hash, frontend
revision/content hash, all baseline frontend blob hashes, final frontend file
hashes, and exact raw-route removal.

#### Complete classified ledger

The artifact now contains 93 immutable baseline groups / 148 occurrences and
9 first-class post-normalization groups / 13 occurrences: 102 groups / 161
classified occurrence records in total.

| Disposition | Groups | Classified occurrences | Conclusion |
| --- | ---: | ---: | --- |
| `existing_stable_capability` | 5 | 7 | Existing exact Legacy registrations remain proven |
| `frontend_retire` | 17 | 21 | Removal plus independent lifecycle evidence passes |
| `frontend_route_normalize` | 15 | 23 | Finite source expressions, including rule action split |
| `truthful_bff_required` | 2 | 2 | Only the two anchored workbench multi-result merges |
| `conditional_dispatch_required` | 3 | 20 | List GET/PATCH/DELETE choose one branch; no aggregation claim |
| `existing_capability_migration_required` | 53 | 80 | Exact stable outcome exists, but provider equivalence is not proven |
| `new_atomic_capability_required` | 6 | 7 | No exact stable target exists |
| `operations_candidate` | 1 | 1 | Unapproved runtime configuration read only |
| **Total** | **102** | **161** | **Every persisted occurrence is first-class and validated** |

The five existing-stable closures / seven occurrences are unchanged. Direct
SQL/service handlers were not registered by name. When one exact stable target
exists without provider-equivalent execution, the ledger records a migration
gap instead of inventing a duplicate atomic contract.

Retirement proofs cover all 17 groups / 21 occurrences and are
machine-verifiable by kind: eight explicit Bitable product retirements, four
backend-router retirements, two HTTP-410 handlers, two plugin-template-only
groups, and one absent Feishu configuration route. Each proof has a non-empty
anchor and final source/hash record; the final source must no longer contain
each baseline raw route. Empty or generic `reviewed` evidence fails closed.

The seven previously hidden concrete knowledge/rule residuals are now ledger
entries, not strings beneath normalization parents. Explicit rule-action
normalization adds `POST /api/rules/{dynamic}/activate` and
`POST /api/rules/{dynamic}/suspend`; all three rule residuals point to
`plugins/craft/craft_backend/routers/rules.py`. `GET /api/plugin/list` points
to its actual registered handler in `backend/routers/plugins.py`. Every
registered handler evidence object is parsed from its exact FastAPI decorator
and function range, and path/method/normalized-route/hash drift fails.

#### Canonical before/after and residual contract gaps

The explicit rule action replaces one dynamic occurrence with two concrete
occurrences. Therefore a lower residual is neither claimed nor required:

| Evidence | Original baseline | Before Fix Round 1 | After Fix Round 1 |
| --- | ---: | ---: | ---: |
| Total discovered | 476 | 476 | 477 |
| Capability | 37 | 37 | 37 |
| Legacy registered | 272 | 311 | 311 |
| Operations excluded | 19 | 19 | 19 |
| Unresolved occurrences | 148 | 109 | 110 |
| Unresolved groups | 93 | 64 | 65 |
| UNKNOWN methods | 0 | 0 | 0 |
| Lexical unmatched | 0 | 0 | 0 |

The final 65 groups / 110 occurrences reconcile exactly to:

- **Existing stable migration — 53 groups / 80 occurrences.** The 45
  baseline families / 68 occurrences cover external datasource/mapping,
  grants, notification preferences, organization/team, self annotation,
  users/identity, saved views, approval rejection, task/issue/knowledge
  collection updates, task entry adapters, plugin install/uninstall, rule
  evaluation/deviation, and skill-canvas execute/resume. Eight promoted
  groups / 12 occurrences cover the concrete knowledge CRUD/search routes,
  rule update, and rule activation. Each records one exact stable target and
  explicitly says provider equivalence is not proven.
- **New atomic Capability — 6 groups / 7 occurrences:**
  `DELETE /api/craft_lib/equipments/{dynamic}`,
  `DELETE /api/craft_lib/fixtures/{dynamic}`, `GET /api/plugin/list`,
  `POST /api/flows/test-node` (two occurrences),
  `POST /api/skills/canvas-options`, and
  `POST /api/rules/{dynamic}/suspend`. `flows/test-node` is owned by Agent and
  is a business authoring-test outcome, not an operations exclusion.
- **Truthful BFF — 2 groups / 2 occurrences:** `GET /api/workbench/home` and
  `GET /api/workbench/panel1`. Each has two distinct stable constituents and
  a hash-anchored handler range that merges their results. A one-constituent
  or generic/conditional aggregation claim is rejected.
- **Conditional dispatch — 3 groups / 20 occurrences:** GET, PATCH, and DELETE
  `/api/lists...`; each selects one reviewed branch and is explicitly not a
  BFF aggregation.
- **Operations approval — 1 group / 1 occurrence:**
  `GET /api/file-store/config`, owned by `platform-runtime`, anchored to
  `backend/routers/file_store.py`, marked `approval_needed=true` and
  `approval_status=not_approved`. No exclusion was activated.

#### Frontend behavior repair

The retired Craft-table import callback now rejects with
`V1 工段工序导入已停用，不支持导入`. The import/export manager therefore renders
its failure state and never displays `导入完成`, a success count, or a success
footer. This restores the pre-retirement failure semantics while keeping the
network route removed.

Rule management now dispatches only the explicit `activate` and `suspend`
routes. Any other action throws a clear unsupported-action error before a
request. Existing methods, payload/options, reload-on-success behavior, and
error display are preserved.

#### TDD and verification

RED was captured before implementation:

```text
backend ledger focused RED: 11 failed, 10 passed
  missing independent baseline/schema, truthful BFF/conditional checks,
  retirement proof, first-class residual, handler, operations, and totals

frontend focused RED: 2/12 failed
  retired import resolved instead of rejecting
  arbitrary rule action dispatched a third dynamic route
```

Final GREEN evidence:

```text
node scripts\test_batch_explicit_http_methods.js
12/12 passed

NODE_PATH=E:\Projects\ai00\workmanship-web\node_modules npm test
focused cases pass; full Web suite 134/134; all web-only checks pass

node --check packages\craft-plugin\web\craft_table\table.js
node --check web\rule_mgmt\rule_mgmt.js
node --check scripts\test_batch_explicit_http_methods.js
exit 0

AI00_WEB_BUILD_PROFILE=production NODE_PATH=E:\Projects\ai00\workmanship-web\node_modules \
  E:\Projects\ai00\workmanship-web\node_modules\.bin\vite.cmd build
172 modules transformed; build passed

python -m pytest backend\tests\test_capability_v2_route_inventory.py -q
21 passed

python -m pytest backend\tests\test_capability_v2_consumer_routes.py \
  backend\tests\test_capability_v2_route_inventory.py \
  backend\tests\test_capability_v2_completion.py -q
125 passed

python -m pytest backend\tests\test_repair_legacy_route_targets.py -q
9 passed

python backend\scripts\build_web_route_root_cause_ledger.py \
  --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check
baseline_occurrences=148 baseline_groups=93
classified_occurrences=161 classified_groups=102
final_unresolved=110 final_groups=65
exit 0

python backend\scripts\check_web_capability_routes.py \
  --web-root E:\Projects\ai00_v3\.worktrees\workmanship-web-capability-governance --check
frontend_revision=c1804e94ad8a3c4660be6bebb1b010744ed8da6f
content_hash=58400ca2fc26c2c29f87d1b43def748bd3f32d515714fe7084258893037779a0
capability=37 legacy_registered=311 operations_excluded=19 unresolved=110 total=477
exit 0
```

The explicit unresolved and strict completion gates remain truthfully red and
stored/fresh identical:

```text
check_web_capability_routes.py --check --fail-on-unresolved
web-route-inventory unresolved=110
exit 1 (expected remaining contract gaps)

check_capability_v2_completion.py --mode strict
check_capability_v2_completion.py --mode strict --web-root <exact frontend>
failed=[web_consumer_bypasses:110, web_route_inventory_unresolved:110]
exit 1 for each (expected remaining contract gaps only)
```

The frontend still has only the preserved untracked `dist-production/`
directory. Pre-existing backend untracked files and inaccessible historical
pytest directories remain untouched. The production build emitted only the
repository's existing classic-script `type="module"` warnings.

## Task 3B.3b

### Result and exact commits

- Frontend commit: `bf53e888cdb1c06528543c1f22dc5205a8a3b772`
  (`fix: migrate existing capability web consumers`).
- Backend commit: `ad325871885b68d103d57062768399eb83ccd026`
  (`fix: govern existing capability web migrations`).
- Before: 53 `existing_capability_migration_required` groups / 80 occurrences;
  canonical Web inventory 65 unresolved groups / 110 occurrences.
- After: 0 `existing_capability_migration_required` groups / 0 occurrences;
  canonical Web inventory 53 unresolved groups / 92 occurrences.
- Reviewed decisions: 12 groups / 18 occurrences migrated through the exact
  stable Capability Gateway target; 41 groups / 62 occurrences transparently
  reclassified because Provider/contract equivalence was not proven.

The exact final evidence is pinned to frontend revision
`bf53e888cdb1c06528543c1f22dc5205a8a3b772` and content hash
`dea9fc41773dc51891a91c0be640e9ddf7ef60783f6d9662af7750637a1caf38`.
Canonical counts are capability 38, legacy registered 311, BFF registered 0,
operations excluded 19, unresolved 92, total 460. UNKNOWN method count is 0.
Lexical audit reconciles 479 tokens as 460 mapped plus 19 reviewed non-route
tokens, with unmatched count 0.

### Migrated families

- Knowledge compatibility adapters: 7 groups / 10 occurrences covering exact
  search/get/create/update/delete outcomes.
- Project atomic adapters: 4 groups / 6 occurrences covering task update,
  issue update, and task item-entry read/replace.
- Craft rule-library adapter: 1 group / 2 occurrences covering exact rule
  update.

All migrated consumers use one shared `existing_capability_client.js` adapter.
It performs `POST /api/v1/capabilities/{id}:invoke`, sends the closed
`{version: 1, payload}` envelope, preserves the legacy `{success,data}` caller
projection, and propagates stable Gateway error code/message without a REST
fallback.

### Evidence-backed reclassifications

The 41 groups / 62 occurrences remain visibly unresolved, grouped by reviewed
reason (groups / occurrences):

- `provider_equivalence_missing`: 17 / 30
- `contract_shape_mismatch`: 14 / 14
- `outcome_mismatch`: 5 / 6
- `projection_mismatch`: 2 / 9
- `state_model_mismatch`: 2 / 2
- `adapter_side_effect_missing`: 1 / 1

Follow-up classes are `atomic_capability_review` 21 / 29,
`provider_adapter_review` 19 / 32, and `bff_review` 1 / 1. These cover the
non-equivalent Base reviewed-outcome ports, legacy notification state,
URL/unrestricted plugin lifecycle, skill-canvas execution, rule lifecycle and
waiver outcomes, Integration legacy projections, identity admin projections,
and the approval notification composition side effect. No Capability or BFF
was created and no ownership boundary or gate was weakened.

### RED/GREEN and verification

RED was captured before implementation:

```text
node scripts\test_existing_capability_migrations.js
MODULE_NOT_FOUND: web/core/existing_capability_client.js

python -m pytest backend\tests\test_existing_capability_web_migrations.py -q
collection error: backend.capability_v2.existing_capability_migrations missing

route inventory total assertion after changing expectations
failed because the ledger still contained migration_required=53/80
```

Final GREEN evidence:

```text
NODE_PATH=E:\Projects\ai00\workmanship-web\node_modules npm test
migration and batch transport tests passed; Web suite 134/134; all web-only checks passed

node --check <all eight changed/new JavaScript files>
all exit 0

AI00_WEB_BUILD_PROFILE=production NODE_PATH=E:\Projects\ai00\workmanship-web\node_modules \
  E:\Projects\ai00\workmanship-web\node_modules\.bin\vite.cmd build \
  --outDir E:\Projects\ai00_v3\.tmp\workmanship-web-task3b3b-final
172 modules transformed; build passed

python -m pytest backend\tests\test_existing_capability_web_migrations.py \
  backend\tests\test_capability_v2_consumer_routes.py \
  backend\tests\test_capability_v2_completion.py \
  backend\tests\test_capability_v2_route_inventory.py \
  backend\tests\test_capability_v2_catalog_targets.py \
  backend\tests\test_repair_legacy_route_targets.py -q
141 passed

python backend\scripts\build_existing_capability_web_migrations.py
groups=53 occurrences=80 migrated=12 reclassified=41

python backend\scripts\build_web_route_root_cause_ledger.py --web-root <exact frontend> --check
baseline=93/148 classified=102/161 final=53/92; exit 0

python backend\scripts\check_web_capability_routes.py --web-root <exact frontend> --check
frontend_revision=bf53e888cdb1c06528543c1f22dc5205a8a3b772
content_hash=dea9fc41773dc51891a91c0be640e9ddf7ef60783f6d9662af7750637a1caf38
unresolved=92 total=460; exit 0

compileall, build_capability_catalog --check, generate_capability_docs --check,
build_capability_acceptance_manifest --check, check_domain_dependencies
all exit 0
```

Stored and fresh strict completion are identical and truthfully remain red only
for the reviewed residual categories:

```text
check_web_capability_routes.py --check --fail-on-unresolved
web-route-inventory unresolved=92; exit 1

check_capability_v2_completion.py --mode strict
check_capability_v2_completion.py --mode strict --web-root <exact frontend>
failed=[web_consumer_bypasses:92, web_route_inventory_unresolved:92]
exit 1 for both
```

The broader `build_user_function_registry.py --strict` baseline also remains
red on the repository's pre-existing `target_replaced` / `target_not_stable`
registry drift; Task 3B.3b does not alter that registry. The frontend still has
only the preserved untracked `dist-production/`; unrelated backend untracked
artifacts and inaccessible historical pytest directories were left untouched.

### Fix Round 1

Review commits:

- Frontend `4980eb7264fbca95f00e38ee2322783f21c987db`
  (`fix: govern migrated capability writes`).
- Backend `1e9da776474a7e73df7fe7df5e1569177712037c`
  (`fix: make capability migration evidence independent`).

The seven write operations now follow the public Gateway contract: one stable
idempotency key is used for the initial invoke, exact confirmation request, and
single approved retry; only `confirmation_required` enters that flow. The
Project task/issue/item-entry payloads use the provider's direct atomic
arguments rather than the compatibility wrapper's `{arguments: ...}` shape.
All ten shared operations are behavior-tested for request/response transforms;
the seven writes additionally cover idempotency, confirmation, retry, ordinary
failure, confirmation failure, and representative quick-list UI recovery.

The evidence chain now starts from the immutable baseline revision
`2c17617c28e0bed2411763e9ae5520128f2804e0` plus an explicit reviewed-decision
module, then independently parses the actual frontend operation map and exact
`.call(...)` sites, resolves Catalog lifecycle/owner, verifies Provider source
anchors/hashes, and joins final inventory and current ledger. Mutation tests
reject a wrong target, missing frontend call site, altered occurrence, altered
decision, and coordinated ledger/manifest drift. The ledger generator consumes
this audited result instead of generating decisions from the current ledger.

Every one of the 41 reclassified route groups now records an exact candidate
Provider source/line/hash plus route-specific input, output, and side-effect
differences. No route-prefix or target-name heuristic selects a decision. The
same 41 groups / 62 occurrences remain visibly unresolved because those
contract comparisons are non-equivalent; none was force-bound, and no new
Capability, BFF, approval, provider wiring, or cross-domain ownership was
introduced.

Canonical before/after for this fix round:

- Before: frontend `bf53e888cdb1c06528543c1f22dc5205a8a3b772`, content hash
  `dea9fc41773dc51891a91c0be640e9ddf7ef60783f6d9662af7750637a1caf38`,
  total 460, unresolved 92/53, `UNKNOWN/method:null=1`.
- After: frontend `4980eb7264fbca95f00e38ee2322783f21c987db`, content hash
  `f6e4c27bb14a489854518422fb862446c4869b468b6bc6014cb039e6bc41ebbb`,
  capability 38, legacy registered 311, operations excluded 19, unresolved
  92/53, total 460, `UNKNOWN/method:null=0`, lexical unmatched 0.
- Package disposition remains fully closed: 53/80 before Task 3B.3b to 0/0
  `existing_capability_migration_required`, represented by 12/18 migrated and
  41/62 evidence-backed reclassified.

Fix-round TDD and verification evidence:

```text
RED: node scripts/test_existing_capability_migrations.js
realistic fake Gateway rejected the old write client with idempotency_key_required

RED: python -m pytest backend/tests/test_existing_capability_web_migrations.py \
  backend/tests/test_capability_v2_route_inventory.py::test_canonical_web_inventory_has_no_unknown_method -q
4 failed, 2 passed: independent audit inputs/evidence fields and canonical method proof absent

RED: python -m pytest backend/tests/test_capability_v2_consumer_routes.py::test_canonical_gate_rejects_ambiguous_method -q
failed because canonical generation did not reject an unknown method

GREEN: NODE_PATH=E:\Projects\ai00_v3\workmanship-web\node_modules npm test
all transport/migration checks passed; Web suite 134/134; all web-only checks passed

GREEN: node --check web/core/existing_capability_client.js and both changed test scripts
all exit 0

GREEN: production Vite build from a disposable clone of frontend HEAD
172 modules transformed; exit 0; disposable clone removed after verification

GREEN: python -m pytest backend/tests/test_existing_capability_web_migrations.py \
  backend/tests/test_capability_v2_consumer_routes.py \
  backend/tests/test_capability_v2_completion.py \
  backend/tests/test_capability_v2_route_inventory.py \
  backend/tests/test_capability_v2_catalog_targets.py \
  backend/tests/test_repair_legacy_route_targets.py -q
145 passed in 40.88s

GREEN: build_existing_capability_web_migrations.py --web-root <frontend>
groups=53 occurrences=80 migrated=12 reclassified=41

GREEN: build_web_route_root_cause_ledger.py --web-root <frontend> --check
baseline=93/148 classified=102/161 final=53/92; exit 0

GREEN: check_web_capability_routes.py --web-root <frontend> --check
frontend_revision=4980eb7264fbca95f00e38ee2322783f21c987db
content_hash=f6e4c27bb14a489854518422fb862446c4869b468b6bc6014cb039e6bc41ebbb
capability=38 legacy_registered=311 operations_excluded=19 unresolved=92 total=460; exit 0
```

Stored and fresh strict Web gates both remain truthfully blocked only by the
92 occurrences in other reviewed residual categories; both report exit 1 with
`web-route-inventory unresolved=92`. The fresh and stored canonical files had
the identical SHA256
`9CB49B5FDAD687F9711CFF7C835A9D107BC98BABA4CEBBA9B0C1B0C0D4284B61`.
This is the expected fail-closed result and no completion criterion was
weakened. The first local `npm test` attempt stopped before the Web suite
because this worktree has no local `jsdom`; rerunning against the repository's
already-installed dependency tree produced the complete 134/134 result without
installing dependencies or changing lockfiles.

A post-commit focused rerun using an outer-workspace basetemp completed
`7 passed in 4.90s`. An initial worktree-local basetemp attempt hit Windows
`PermissionError [WinError 5]` during pytest temporary-directory access/cleanup;
the same tests passed unchanged after relocating basetemp. Both exact pytest
temporary directories were then removed, leaving no test artifact to retain.

## Task 3B.3b Fix Round 2 — real Catalog validation and exact compatibility

Fix Round 2 commits:

- Frontend `e4a8136dad3d1781ae16ec7122e52dc1849bfe18`
  (`fix: align migrated capability contracts`).
- Frontend `fbd86ad7065d91b1740dbcb25889b3430bb8e452`
  (`fix: reclassify incompatible rule migration`).
- Backend `5cc460e5ed0aa0227549f7eca3017707777d51a5`
  (`fix: validate migrated capability payloads`).

The production Catalog validator is now exercised against payloads captured
from the actual frontend client. It initially rejected five operations: four
Project operations sent direct fields instead of the stable provider's required
`{arguments:{...}}` envelope, and Craft rule update sent a non-empty `record`
to a published closed schema with no permitted record properties. The four
Project operations now use the exact provider envelope and all nine operations
that remain classified as migrations pass the production validator.

Craft rule update was not made artificially green. The legacy REST path accepts
a non-empty record and the provider filters ten meaningful rule fields, while
the published stable Catalog permits no non-empty record. Emptying the record
would lose the update and fail in the provider. Expanding the stable schema
would create a new Catalog release outside this task. The two frontend call
sites therefore retain their prior legacy PUT behavior and the one route group
is transparently reclassified with exact contract/source/hash evidence. No
Capability, BFF, approval, provider behavior, or stable schema was added or
changed; the temporary Catalog/docs regeneration was fully removed, leaving
zero schema/docs/release diff.

Knowledge update and delete now preserve the exact legacy response
`{success:true}` and discard provider data. The migration behavior tests verify
request and response transforms for every migrated operation, and verify the
six migrated writes' stable idempotency key, confirmation, approved retry,
ordinary failure, and confirmation failure. They also assert that the
reclassified Craft operation cannot dispatch through the shared Capability
client.

Canonical and disposition results:

- Before Fix Round 2: 12 migrated groups / 18 occurrences and 41 reclassified
  groups / 62 occurrences; canonical total 460, unresolved 92 occurrences / 53
  groups.
- After Fix Round 2: 11 migrated groups / 16 occurrences and 42 reclassified
  groups / 64 occurrences; canonical total 462, unresolved 94 occurrences / 54
  groups.
- The package remains closed over all 53 groups / 80 occurrences with zero
  `existing_capability_migration_required`; `UNKNOWN/method:null=0` and lexical
  unmatched remains zero.
- Final frontend revision is
  `fbd86ad7065d91b1740dbcb25889b3430bb8e452`, content hash
  `c960574d6b4156a9535c20300efad032c5333426c9642232acc45ef8f59abb62`.

Fix Round 2 verification:

```text
RED: production Catalog validation of actual frontend payloads
5 failures: four Project envelope violations plus Craft record.name rejected

GREEN: NODE_PATH=E:\Projects\ai00_v3\workmanship-web\node_modules npm test
all migration/transport checks passed; Web suite 134/134; all web-only checks passed

GREEN: python -m pytest backend/tests/test_existing_capability_web_migrations.py \
  backend/tests/test_capability_v2_consumer_routes.py \
  backend/tests/test_capability_v2_completion.py \
  backend/tests/test_capability_v2_route_inventory.py \
  backend/tests/test_capability_v2_catalog_targets.py \
  backend/tests/test_repair_legacy_route_targets.py -q
146 passed in 41.05s

GREEN: run_capability_v2_acceptance.py --mode offline --strict
status=passed; declared=3080; validated=3080; failed=0; skipped=0;
acceptance pytest summary=3091 passed in 7.34s

GREEN: build_existing_capability_web_migrations.py --web-root <frontend>
groups=53 occurrences=80 migrated=11 reclassified=42

GREEN: build_web_route_root_cause_ledger.py --web-root <frontend> --check
baseline=93/148 classified=102/161 final=54/94; exit 0

GREEN: check_web_capability_routes.py --web-root <frontend> --check
capability=38 legacy_registered=311 operations_excluded=19 unresolved=94 total=462;
UNKNOWN/method:null=0; exit 0

GREEN: freeze official domains, Catalog, generated docs, and acceptance manifest checks
Catalog release rel_40ed2fbd3abc82881c2856c99c4b200a; 456 descriptors;
456 generated pages; 440 stable capabilities; all exit 0
```

## Task 3B.3c

Task 3B.3c conserved the independently audited atomic scope at exactly 48
route groups / 71 frontend occurrences. Exact provider and schema evidence made
23 groups / 44 occurrences safe to migrate; 25 groups / 27 occurrences remain
explicitly reclassified. No entry was hidden, merged into an umbrella
capability, or forced green by weakening a contract.

| Owner domain | Scope groups/occurrences | Migrated groups/occurrences | Reclassified groups/occurrences |
| --- | ---: | ---: | ---: |
| Base | 24 / 44 | 22 / 42 | 2 / 2 |
| Integration | 12 / 12 | 0 / 0 | 12 / 12 |
| Craft | 7 / 9 | 1 / 2 | 6 / 7 |
| Agent | 4 / 5 | 0 / 0 | 4 / 5 |
| Project | 1 / 1 | 0 / 0 | 1 / 1 |
| **Total** | **48 / 71** | **23 / 44** | **25 / 27** |

The 23 exact capabilities published in this release are:

| Domain | Capability ids (`@1`) |
| --- | --- |
| Base authorization | `base.authorization.grant.list`, `base.authorization.grant.create`, `base.authorization.grant.revoke` |
| Base preferences and directory | `base.notification.preference.atomic.get`, `base.notification.preference.atomic.update`, `base.identity.directory.feishu.sync`, `base.team.directory.list` |
| Base plugin and annotations | `base.plugin.installed.list`, `base.annotation.get`, `base.annotation.upsert`, `base.annotation.batch.get`, `base.annotation.list` |
| Base identity and team | `base.team.list`, `base.identity.user.list`, `base.identity.user.role.assign`, `base.identity.session.get.atomic`, `base.identity.user.search` |
| Base saved views | `base.saved_view.list`, `base.saved_view.create`, `base.saved_view.delete`, `base.saved_view.update`, `base.saved_view.copy` |
| Craft rules | `craft.rule.definition.update` |

Every published descriptor has a closed production request/output schema and a
real owner provider. Writes preserve confirmation and stable idempotency
semantics; reads preserve authorization and exact response projection.
Annotation attachments, saved-view configuration, and Craft rule changes use a
bounded JSON-string transport (1 MiB maximum) and are parsed and type-checked
inside the owner provider. This preserves dynamic nested data without opening
the Catalog schema or silently closing arbitrary objects to `{}`. Base provider
delegation reaches the existing production handlers through the approved
`backend.platform_sdk.base_web_outcomes` boundary; the domain dependency gate
reports zero reviewed violations and no provider uses public REST fallback or
cross-domain direct SQL.

The reclassifications are evidence-backed rather than placeholders:

- Base 2/2: arbitrary-URL plugin install and unrestricted uninstall lack a safe
  exact handler/lifecycle contract.
- Integration 12/12: the legacy routes are absent and the governed connector
  and mapping contracts are not response/side-effect equivalent.
- Craft 6/7: the exact handlers are absent or their lifecycle semantics do not
  match a stable atomic outcome.
- Agent 4/5: no runtime provider exists for the audited operations.
- Project 1/1: direct approval rejection would drop the legacy adapter's
  notification side effect, so the frontend occurrence remains on its exact
  REST path pending a provider/BFF design that can preserve it.

The machine manifest `atomic-web-capability-contracts.json` binds all 48/71
entries to method/route, occurrence and source hashes, owner, handler/provider
anchor, closed schemas, side effects, atomicity, confirmation/idempotency
policy, and final disposition. Its final result is `migrated=23` and
`reclassified=25`. The root ledger independently reconciles to 34 migrated
groups / 60 occurrences, 20 reclassified groups / 21 occurrences, and 5 new
atomic groups / 6 occurrences after combining Task 3B.3b with this task.

Catalog and canonical evidence:

- Catalog release `rel_b6846f0f3faea2788a65130a4a59a5fe` contains 479
  descriptors and 479 generated pages; 463 stable capabilities produce 3,241
  strict acceptance cases.
- Official manifest hash is
  `sha256:f2e589f211385f0ccfa6bd08b7940f9b2dd4900b85a6cb13687b97a95e1f6d05`.
- Frontend revision is `078951be722a48b4e151ee8cd4d6b3091cf207be` and
  canonical content hash is
  `028307827053e31c950a06ab1671cb061e25335a39aac9468dae56797d4473d6`.
- Canonical inventory is total 418: capability 38, legacy registered 311,
  operations excluded 19, unresolved 50; `UNKNOWN/method:null=0` and lexical
  unmatched is zero.
- Final residual is 50 occurrences / 31 groups: the 27 occurrences
  reclassified here plus the 23 occurrences predeclared for Task 3B.3d.

TDD and verification evidence:

```text
RED: exact manifest conservation/provider proof-shape/schema tests
missing 48/71 manifest, providers, closed schemas, authorization,
confirmation/idempotency, exact invocation, error propagation, and projections

GREEN: focused atomic contract/provider and production Catalog validation
36 passed

GREEN: broad backend capability/provider/audit suite
154 passed in 43.86s

GREEN: check_domain_dependencies.py
reviewed violations=0; new dependencies=0

GREEN: run_capability_v2_acceptance.py --mode offline --strict
release=rel_b6846f0f3faea2788a65130a4a59a5fe; stable=463;
declared=3241; validated=3241; failed=0; skipped=0

GREEN: official domain freeze, Catalog, docs, acceptance manifest, atomic
manifest, existing migration manifest, root ledger, and canonical inventory
generator checks; all generated artifacts reproduce without drift

GREEN: frontend migration/transport tests and full Web suite
23 exact migration cases; Web 134/134; web-only checks passed

GREEN: frontend syntax and production build
node --check passed; Vite built 172 modules (pre-existing non-module warnings)

EXPECTED FAIL-CLOSED: stored and fresh strict Web gates
only web_consumer_bypasses:50 and web_route_inventory_unresolved:50;
canonical total=418, unresolved=50
```

Exact implementation commits:

- Frontend `078951be722a48b4e151ee8cd4d6b3091cf207be`
  (`feat: migrate exact atomic web outcomes`).
- Backend `6ee736052f6ea631e959129c6e37075a34025163`
  (`feat: close exact atomic web capability gaps`).

No dependencies were installed, and no push, merge, production database,
BFF/operations approval, or cross-domain direct database access was performed.

## Task 3B.3c Fix Round 1

Fix Round 1 resolves the review's Critical permission failure and four
Important contract/provider/evidence failures without granting the rejected
`base.read`, `base.write`, or `craft.rule.write` umbrella permissions. The
48-group / 71-occurrence atomic scope remains conserved exactly. Eight Base
outcomes covering 11 occurrences remain migrated; 40 groups / 60 occurrences
are transparently reclassified and their Web consumers use their original REST
paths.

| Owner domain | Scope groups/occurrences | Migrated groups/occurrences | Reclassified groups/occurrences |
| --- | ---: | ---: | ---: |
| Base | 24 / 44 | 8 / 11 | 16 / 33 |
| Integration | 12 / 12 | 0 / 0 | 12 / 12 |
| Craft | 7 / 9 | 0 / 0 | 7 / 9 |
| Agent | 4 / 5 | 0 / 0 | 4 / 5 |
| Project Management | 1 / 1 | 0 / 0 | 1 / 1 |
| **Total** | **48 / 71** | **8 / 11** | **40 / 60** |

The retained stable capabilities are:

- `base.authorization.grant.list@1`
- `base.authorization.grant.create@1`
- `base.authorization.grant.revoke@1`
- `base.notification.preference.atomic.get@1`
- `base.notification.preference.atomic.update@1`
- `base.identity.directory.feishu.sync@1`
- `base.plugin.installed.list@1`
- `base.identity.user.search@1`

All eight use closed typed business outputs; no `result_json` transport
remains. REST and Capability providers share explicit Base owner services.
Grant management retains the legacy `system.user.manage` coarse permission and
the owner service rechecks super-admin/team-admin/scoped-grant object
authorization. Feishu synchronization requires `system.tech_config` at the
Gateway and rechecks `super_admin` inside the provider. Authenticated reads do
not acquire broad write permissions. The production Gateway suite covers
super-admin, team-admin, member, and unauthorized actors, approval,
idempotency replay, malformed provider output, and outcome persistence failure
after an external mutation.

The private-router re-export `backend.platform_sdk.base_web_outcomes` was
removed. The dependency checker now inspects Platform SDK private-router
imports and reports zero new violations; the sole older
`backend/platform_sdk/auth.py -> backend.routers.deps` edge is represented by
an explicit narrow baseline rather than hidden by the shared-prefix rule.
Manifest side effects, authorization, confirmation, idempotency, consistency,
and atomicity are derived from the registered production spec/descriptor and
handler evidence instead of HTTP method.

Final generated evidence:

- Catalog release `rel_5915db601d7c6ce939a106d76a78b90a`: 464
  descriptors/pages, 448 stable capabilities.
- Official-domain manifest hash
  `sha256:1db4cca91b3ae5bbc50aa697fee8dbcb99e45ae77628074cdf97cba45a6d4776`.
- Frontend revision `af7f8e1f71e11c3f255bcf632d8eb91d8a0f86f1`, content hash
  `5b1c2e258eb0b41fb7f3e558578ac18dff02f6f24a5747ef1b640700a9410643`.
- Canonical Web inventory: total 451, capability 38, legacy registered 311,
  operations excluded 19, unresolved 83; root ledger 102 groups / 161
  occurrences with 46 unresolved groups.
- Root-ledger final dispositions: 19 migrated groups / 27 occurrences and 35
  reclassified groups / 54 occurrences, plus the unchanged retirement,
  normalization, conditional, BFF, operations, stable, and new-atomic classes.

Verification evidence:

```text
GREEN: focused production Gateway/provider/schema/dependency suite: 26 passed
GREEN: consumer/completion/route-proof suite: 151 passed
GREEN: strict offline acceptance: 3,136/3,136 validated; failed=0; skipped=0
GREEN: Catalog/docs/acceptance/atomic/domain/root-ledger/inventory checks
GREEN: frontend npm test, including Web 134/134
GREEN: frontend production Vite build: 172 modules
GREEN: frontend/backend diff --check and Python compileall
KNOWN GLOBAL DRIFT: build_user_function_registry.py --strict still reports
pre-existing deprecated/replaced Catalog targets across unrelated domains;
the Fix R1 implementation does not weaken or baseline those findings.
```

Exact implementation commits:

- Frontend `af7f8e1f71e11c3f255bcf632d8eb91d8a0f86f1`
  (`fix: restore unsafe atomic web consumers`).
- Backend `15cfe69fdc63890940ab6a4c9b1b04175b24c5a3`
  (`fix: enforce exact atomic capability contracts`).

No dependency was installed and no push, merge, production database mutation,
BFF/operations approval, public REST fallback, or cross-domain direct database
access was performed.
