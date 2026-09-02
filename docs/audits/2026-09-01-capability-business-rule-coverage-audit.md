# Capability 业务规则覆盖审计

> 审计口径：只认 Catalog 可查询的规则登记、输入约束、业务错误码和专用测试引用；不根据函数名猜测 Provider 内部行为。
> 数据源：`docs/governance/capability-catalog-release.json`；Catalog Release：`rel_320fd769fb6f96517c261c72271a7a9f`。

## 结论

- stable Capability：**479**
- 业务不变量已登记且有证据：**0**
- 业务不变量登记不完整：**0**
- 明确声明不适用：**0**
- 只有 Schema、错误码或专用测试等局部信号：**383**
- 没有可证明业务规则信号：**96**
- 其中发现 Schema 约束信号：**258**；非通用错误码信号：**298**；Capability 专用测试引用：**0**
- 无法证明且具有写副作用：**65**（应优先人工核查）

业务目的登记同样存在缺口：
- 由构建器添加 `Business outcome:` 前缀的自动投影：**454**
- 内容近乎空泛的 `Execute the governed ... outcome`：**59**
- 非模板、可进入领域 Owner 复核的候选业务目的：**25**

因此，不能断言所有 Capability 的 Provider 都没有业务判断；可以确定的是，当前没有 Capability 通过统一的 `business_invariants` 登记链证明规则、执行点和测试证据完整闭环。

## 分类含义

| 分类 | 含义 |
|---|---|
| registered_and_evidenced | 规则、执行位置、稳定错误码和测试引用均已登记 |
| registered_incomplete | 已登记规则，但必要字段或测试证据不完整 |
| explicitly_not_applicable | 领域 Owner 明确说明该能力不承载业务不变量 |
| partial_signal_only | 发现范围/枚举等 Schema 约束、业务错误码或专用测试，但无法形成完整证明链 |
| unproven | Catalog 中没有发现上述任何可审计信号；不等同于代码里一定没有 if 判断 |

## 领域统计

| 领域 | stable | 已闭环 | 登记不完整 | 不适用 | 局部信号 | 无法证明 |
|---|---:|---:|---:|---:|---:|---:|
| agent | 22 | 0 | 0 | 0 | 21 | 1 |
| base | 75 | 0 | 0 | 0 | 75 | 0 |
| craft | 126 | 0 | 0 | 0 | 126 | 0 |
| device | 8 | 0 | 0 | 0 | 8 | 0 |
| digital_model | 8 | 0 | 0 | 0 | 8 | 0 |
| factory | 19 | 0 | 0 | 0 | 19 | 0 |
| integration | 19 | 0 | 0 | 0 | 19 | 0 |
| knowledge | 52 | 0 | 0 | 0 | 52 | 0 |
| ontology | 15 | 0 | 0 | 0 | 7 | 8 |
| project_management | 120 | 0 | 0 | 0 | 33 | 87 |
| simulation | 15 | 0 | 0 | 0 | 15 | 0 |

## 全量明细

| Capability | 领域 | 副作用 | 业务目的质量 | 规则分类 | Schema 规则信号 | 非通用错误码 | 专用测试证据 |
|---|---|---|---|---|---|---|---|
| `agent.audit.read@1` | agent | read | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.audit.record@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.canvas.execution.resume@1` | agent | write | vacuous | partial_signal_only | $.run_token.maxLength<br>$.run_token.minLength<br>$.pause_token.maxLength；另有 13 项 | — | — |
| `agent.canvas.execution.start@1` | agent | write | vacuous | partial_signal_only | $.skill_gid.maxLength<br>$.skill_gid.minLength<br>$.expected_revision.minimum；另有 11 项 | — | — |
| `agent.canvas.options.resolve@1` | agent | read | vacuous | partial_signal_only | $.skill_gid.maxLength<br>$.skill_gid.minLength<br>$.node_id.maxLength；另有 15 项 | — | — |
| `agent.flow.change.apply@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.flow.read@1` | agent | read | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.interaction.cancel@1` | agent | write | vacuous | partial_signal_only | $.session_gid.minLength | — | — |
| `agent.interaction.chat.change.apply@1` | agent | write | generated_from_description | partial_signal_only | $.operation.enum | — | — |
| `agent.interaction.request@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.memory.change.apply@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.memory.read@1` | agent | read | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.run.change.apply@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.run.read@1` | agent | read | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.runtime.config.read@1` | agent | read | vacuous | unproven | — | — | — |
| `agent.script.generate@1` | agent | write | vacuous | partial_signal_only | $.description.maxLength<br>$.description.minLength | — | — |
| `agent.session.change.apply@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.session.read@1` | agent | read | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.skill.change.apply@1` | agent | write | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.skill.read@1` | agent | read | vacuous | partial_signal_only | $.resource_gid.minLength<br>$.expected_version.minimum<br>$.status.minLength；另有 23 项 | — | — |
| `agent.tool_catalog.read@1` | agent | read | vacuous | partial_signal_only | $.operation.enum | — | — |
| `agent.workflow.node.test.execute@1` | agent | write | vacuous | partial_signal_only | $.flow_gid.maxLength<br>$.flow_gid.minLength<br>$.node_id.maxLength；另有 12 项 | — | — |
| `base.annotation.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.annotation.read@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.approval.request.cancel@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.approval.request.create@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.approval.request.decide@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.approval.request.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.approval.request.search@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.authorization.grant.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.authorization.grant.create@1` | base | write | explicit_candidate | partial_signal_only | $.grantee_gid.maxLength<br>$.grantee_gid.minLength<br>$.grant_type.maxLength；另有 4 项 | authentication_stale<br>plugin_state_conflict | — |
| `base.authorization.grant.list@1` | base | read | explicit_candidate | partial_signal_only | $.user_gid.maxLength | authentication_stale<br>plugin_state_conflict | — |
| `base.authorization.grant.read@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.authorization.grant.revoke@1` | base | write | explicit_candidate | partial_signal_only | $.gid.maxLength<br>$.gid.minLength | authentication_stale<br>plugin_state_conflict | — |
| `base.export_template.change.apply@1` | base | write | generated_from_description | partial_signal_only | $.operation.enum | authentication_stale<br>plugin_state_conflict | — |
| `base.export_template.read@1` | base | read | generated_from_description | partial_signal_only | $.module.maxLength<br>$.limit.maximum<br>$.limit.minimum | authentication_stale<br>plugin_state_conflict | — |
| `base.file_store.public_config.get@1` | base | read | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.admin_user.list@1` | base | read | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.directory.feishu.sync@1` | base | write | explicit_candidate | partial_signal_only | $.department_id.maxLength | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.directory.sync@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.role.assign.atomic@1` | base | write | explicit_candidate | partial_signal_only | $.user_gid.maxLength<br>$.user_gid.minLength<br>$.new_role.enum；另有 1 项 | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.role.assign@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.session.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.identity.session.profile.get@1` | base | read | explicit_candidate | partial_signal_only | — | identity_not_found<br>tenant_mismatch | — |
| `base.identity.user.search@1` | base | read | explicit_candidate | partial_signal_only | $.query.maxLength<br>$.limit.maximum<br>$.limit.minimum | authentication_stale<br>plugin_state_conflict | — |
| `base.notification.preference.atomic.get@1` | base | read | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.notification.preference.atomic.update@1` | base | write | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.notification.preference.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.notification.preference.update@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.notification.read_state.set@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.notification.search@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.organization.team.directory.list@1` | base | read | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.plugin.installation.request.create@1` | base | write | explicit_candidate | partial_signal_only | $.plugin_id.maxLength<br>$.plugin_id.minLength<br>$.release_version.maxLength；另有 7 项 | already_installed<br>release_not_verified | — |
| `base.plugin.installation.transition.uninstall@1` | base | write | explicit_candidate | partial_signal_only | $.plugin_id.maxLength<br>$.plugin_id.minLength<br>$.expected_revision.minimum；另有 3 项 | invalid_transition<br>release_not_verified<br>revision_conflict | — |
| `base.plugin.installed.list@1` | base | read | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.plugin.marketplace.publisher.register@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.plugin.marketplace.release.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.plugin.marketplace.search@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.runtime.database_config.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.runtime.database_config.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.runtime.database_connection.test@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.saved_view.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.saved_view.copy@1` | base | write | explicit_candidate | partial_signal_only | $.view_gid.maxLength<br>$.view_gid.minLength<br>$.name.maxLength；另有 3 项 | legacy_config_unsupported | — |
| `base.saved_view.create@1` | base | write | explicit_candidate | partial_signal_only | $.name.maxLength<br>$.name.minLength<br>$.module.maxLength；另有 20 项 | — | — |
| `base.saved_view.delete@1` | base | write | explicit_candidate | partial_signal_only | $.view_gid.maxLength<br>$.view_gid.minLength<br>$.expected_revision.minimum；另有 2 项 | legacy_config_unsupported<br>revision_conflict | — |
| `base.saved_view.read@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.saved_view.search@1` | base | read | explicit_candidate | partial_signal_only | $.module.maxLength<br>$.list_gid.maxLength<br>$.limit.maximum；另有 3 项 | — | — |
| `base.saved_view.update@1` | base | write | explicit_candidate | partial_signal_only | $.view_gid.maxLength<br>$.view_gid.minLength<br>$.expected_revision.minimum；另有 23 项 | legacy_config_unsupported<br>revision_conflict | — |
| `base.self_annotation.batch.get@1` | base | read | explicit_candidate | partial_signal_only | $.item_gids.maxItems<br>$.item_gids.minItems<br>$.item_gids[].maxLength；另有 1 项 | — | — |
| `base.self_annotation.change.apply@1` | base | write | explicit_candidate | partial_signal_only | $.item_gid.maxLength<br>$.item_gid.minLength<br>$.expected_revision.minimum；另有 16 项 | attachment_not_visible<br>revision_conflict | — |
| `base.self_annotation.record.get@1` | base | read | explicit_candidate | partial_signal_only | $.item_gid.maxLength<br>$.item_gid.minLength | — | — |
| `base.self_annotation.search@1` | base | read | explicit_candidate | partial_signal_only | $.limit.maximum<br>$.limit.minimum<br>$.status.maxLength；另有 1 项 | — | — |
| `base.team.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.team.directory.list@1` | base | read | explicit_candidate | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.team.membership.change.apply@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.team.read@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.workspace.template.publish@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `base.workspace.template.read@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `identity.principal.search@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.disable@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.enable@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.install@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.revoke@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.rollback@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.storage.delete@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.storage.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.storage.list@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.storage.put@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.uninstall@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `plugin.upgrade@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `semantic.context.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `system.activity.search@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `system.change_impact.preview@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `system.job.cancel@1` | base | write | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `system.job.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `system.lineage.get@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `system.search@1` | base | read | generated_from_description | partial_signal_only | — | authentication_stale<br>plugin_state_conflict | — |
| `craft.bop.alt_hierarchy.read@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.draft.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.preview_gid.minLength<br>$.idempotency_key.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.draft.change.preview@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.expected_revision.minimum<br>$.idempotency_key.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.entry.bulk.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.bop_version_gid.minLength；另有 10 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.entry.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.entry_gid.minLength<br>$.properties.maxItems；另有 2 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.entry.detail.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.revision.minimum<br>$.entry_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.entry.legacy_read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.limit.maximum<br>$.limit.minimum；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.entry.search@1` | craft | read | generated_from_description | partial_signal_only | $.node_types.maxItems<br>$.limit.maximum<br>$.limit.minimum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.entry_link.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.entry_gid.minLength<br>$.link_gid.minLength；另有 2 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.execution_structure.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.execution_structure.preview@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.expected_revision.minimum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.fork.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.source_version_gid.minLength<br>$.target_version_tag.minLength；另有 3 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.fork_preset.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.name.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.fork_preset.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.team_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.gbop.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.pbom_gid.minLength<br>$.bop_gid.minLength；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.gbop.legacy_read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.import.preview@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.pbom_version_gid.minLength；另有 7 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.checkpoint.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.line_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.checkpoint.rollback.apply@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.line_gid.minLength<br>$.checkpoint_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.history.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.line_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.limit.maximum<br>$.limit.minimum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.state.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.state.read@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.stats.refresh.apply@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.lifecycle.step.rollback.apply@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.step_key.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.line_operation_catia.read@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.linked_parts.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.cursor.pattern<br>$.page_size.maximum；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.pbom.change_point.get@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.pbom_lifecycle.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.picture.upload@1` | craft | write | generated_from_description | partial_signal_only | $.filename.minLength<br>$.mime.minLength<br>$.data_b64.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.staging.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.staging_gid.minLength；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.staging.lifecycle.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.entry_gid.minLength<br>$.staging_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.staging.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.structure.outline.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.revision.minimum<br>$.cursor.minLength；另有 2 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.template.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.source_version_gid.minLength<br>$.template_gid.minLength；另有 2 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.validation.get@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.validation.run@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.archive@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.expected_revision.minimum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.compare@1` | craft | read | generated_from_description | partial_signal_only | $.from_version_gid.minLength<br>$.to_version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.create@1` | craft | write | generated_from_description | partial_signal_only | $.source.enum<br>$.version_tag.minLength<br>$.bop_name.minLength；另有 12 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.freeze.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.layout.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.legacy_read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.lifecycle.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.list@1` | craft | read | generated_from_description | partial_signal_only | $.project_gid.minLength<br>$.factory_gid.minLength<br>$.status.minLength；另有 3 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.version.snapshot.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.work_package.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.scope.kind.enum<br>$.scope.gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.bop.work_package.get@2` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength<br>$.revision.minimum<br>$.scope_kind.enum；另有 4 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.canvas.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.canvas.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.data_exchange.export@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.rows.maxItems<br>$.columns.maxItems；另有 3 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.data_exchange.lark.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.user_access_token.minLength<br>$.spreadsheet_token.minLength；另有 3 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.data_exchange.lark.write@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.user_access_token.minLength<br>$.spreadsheet_token.minLength；另有 5 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.snapshot_gid.minLength<br>$.status.minLength；另有 2 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.legacy_read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.base_gid.minLength<br>$.target_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.part.bulk_create@1` | craft | write | generated_from_description | partial_signal_only | $.snapshot_gid.minLength<br>$.parts.maxItems | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.part.create@1` | craft | write | generated_from_description | partial_signal_only | $.snapshot_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.part.delete@1` | craft | write | generated_from_description | partial_signal_only | $.part_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.part.update@1` | craft | write | generated_from_description | partial_signal_only | $.part_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.snapshot.delete@1` | craft | write | generated_from_description | partial_signal_only | $.snapshot_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.snapshot.status.update@1` | craft | write | generated_from_description | partial_signal_only | $.snapshot_gid.minLength<br>$.status.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.snapshot.update@1` | craft | write | generated_from_description | partial_signal_only | $.snapshot_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.snapshot.vpps_stats.update@1` | craft | write | generated_from_description | partial_signal_only | $.snapshot_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.ebom.vpps_check.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.snapshot_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.catalog.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.entry_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.draft.change.apply@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.draft.change.preview@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.draft.create@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.draft.get@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.draft.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.draft.submit@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.entity.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.version_gid.minLength；另有 5 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.import.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.levels.maxItems；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.import.tc.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.version_gid.minLength<br>$.filename.minLength；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.item.knowledge.list@1` | craft | read | generated_from_description | partial_signal_only | $.item_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.item.search@1` | craft | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.item.usage.get@1` | craft | read | generated_from_description | partial_signal_only | $.item_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.navigation.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.navigation.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.pbom_version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.process_hierarchy.read@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.release.activate@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.release.archive@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.release.compare@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.release.get@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.release.publish@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.release.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.station_autolink.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.bop_gid.minLength<br>$.line_gids[].minLength；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.station_autolink.preview@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.bop_gid.minLength<br>$.pbom_version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.gbop.version.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.family_gid.minLength；另有 2 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.library.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.maxLength<br>$.items.maxItems；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.library.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.q.maxLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.draft.change.apply@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.draft.change.preview@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.import.preview@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.part.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.archive@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.compare@1` | craft | read | generated_from_description | partial_signal_only | $.from_version_gid.minLength<br>$.to_version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.create@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.get@1` | craft | read | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.publish@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.pbom.version.submit@1` | craft | write | generated_from_description | partial_signal_only | $.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.definition.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.rule_gid.maxLength<br>$.rule_gid.minLength<br>$.expected_revision.minimum；另有 19 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.draft.create@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.draft.get@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.draft.revise@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.draft.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.draft.submit@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.engine.evaluate@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.rule_gid.minLength<br>$.version_gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.entry.evaluate@1` | craft | read | generated_from_description | partial_signal_only | $.rule_gid.maxLength<br>$.rule_gid.minLength<br>$.rule_revision.maximum；另有 1 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.evaluate@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.library.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.library.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.status.minLength；另有 4 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.release.activate@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.release.get@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.release.publish@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.release.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.waiver.create@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.waiver.revoke@1` | craft | write | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.rule.waiver.search@1` | craft | read | generated_from_description | partial_signal_only | — | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.standard_operation.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.standard_operation.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.status.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.vpps_audit.change.apply@1` | craft | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.gid.minLength<br>$.pbom_version_gid.minLength；另有 4 项 | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `craft.vpps_audit.read@1` | craft | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.pbom_version_gid.minLength<br>$.operation_type.minLength | active_gbop_item_not_found<br>active_gbop_not_found<br>archive_forbidden；另有 22 项 | — |
| `local.command.get@1` | device | read | generated_from_description | partial_signal_only | $.command_id.minLength | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.capture@1` | device | write | generated_from_description | partial_signal_only | $.device_id.minLength | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.highlight@1` | device | write | generated_from_description | partial_signal_only | $.device_id.minLength<br>$.catia_names.maxItems<br>$.catia_names.minItems；另有 1 项 | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.launch@1` | device | write | generated_from_description | partial_signal_only | $.device_id.minLength | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.model.open@1` | device | write | generated_from_description | partial_signal_only | $.device_id.minLength<br>$.artifact_ref.artifact_id.minLength<br>$.artifact_ref.media_type.enum；另有 3 项 | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.status@1` | device | read | generated_from_description | partial_signal_only | $.device_id.minLength | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.tree@1` | device | read | generated_from_description | partial_signal_only | $.device_id.minLength<br>$.max_depth.maximum<br>$.max_depth.minimum | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `vismockup.visibility@1` | device | write | generated_from_description | partial_signal_only | $.device_id.minLength<br>$.action.enum | device_capability_unavailable<br>device_not_found<br>local_operation_failed；另有 2 项 | — |
| `digital_model.component.search@1` | digital_model | read | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.model.create@1` | digital_model | write | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.model.get@1` | digital_model | read | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.model.search@1` | digital_model | read | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.version.compare@1` | digital_model | read | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.version.create@1` | digital_model | write | generated_from_description | partial_signal_only | $.artifact_ref.sha256.pattern | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.version.get@1` | digital_model | read | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `digital_model.version.search@1` | digital_model | read | generated_from_description | partial_signal_only | — | artifact_not_found<br>component_not_found<br>model_not_found；另有 1 项 | — |
| `factory.asset.get@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.asset.maintenance.complete@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.asset.maintenance.start@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.asset.register@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.asset.scrap@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.asset.search@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.asset.update@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource.read@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource_catalog.create@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource_catalog.deprecate@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource_catalog.get@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource_catalog.publish@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource_catalog.revise@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.resource_catalog.search@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.structure.archive@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.structure.create@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.structure.get@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.structure.search@1` | factory | read | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `factory.structure.update@1` | factory | write | vacuous | partial_signal_only | $.expected_version.minimum<br>$.expected_revision.minimum<br>$.kind.enum；另有 7 项 | — | — |
| `integration.connector.archive@1` | integration | write | vacuous | partial_signal_only | $.gid.minLength<br>$.expected_revision.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.connector.connection.test@1` | integration | write | vacuous | partial_signal_only | $.gid.minLength<br>$.idempotency_key.maxLength<br>$.idempotency_key.minLength | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.connector.create@1` | integration | write | vacuous | partial_signal_only | $.name.minLength<br>$.connector_type.minLength<br>$.host.minLength；另有 8 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.connector.schema.discover@1` | integration | read | vacuous | partial_signal_only | $.gid.minLength<br>$.limit.maximum<br>$.limit.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.connector.search@1` | integration | read | vacuous | partial_signal_only | $.query.minLength<br>$.limit.maximum<br>$.limit.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.connector.update@1` | integration | write | vacuous | partial_signal_only | $.gid.minLength<br>$.expected_revision.minimum<br>$.name.minLength；另有 10 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.field_mapping.batch.update@1` | integration | write | vacuous | partial_signal_only | $.mapping_gid.minLength<br>$.expected_revision.minimum<br>$.items.maxItems；另有 6 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.field_mapping.search@1` | integration | read | vacuous | partial_signal_only | $.mapping_gid.minLength<br>$.limit.maximum<br>$.limit.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.archive@1` | integration | write | vacuous | partial_signal_only | $.gid.minLength<br>$.expected_revision.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.create@1` | integration | write | vacuous | partial_signal_only | $.datasource_gid.minLength<br>$.name.minLength<br>$.source_object.minLength；另有 7 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.get@1` | integration | read | vacuous | partial_signal_only | $.gid.minLength | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.import.start@1` | integration | write | vacuous | partial_signal_only | $.mapping_gid.minLength<br>$.idempotency_key.maxLength<br>$.idempotency_key.minLength | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.preview@1` | integration | read | vacuous | partial_signal_only | $.gid.minLength<br>$.limit.maximum<br>$.limit.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.search@1` | integration | read | vacuous | partial_signal_only | $.datasource_gid.minLength<br>$.query.minLength<br>$.limit.maximum；另有 1 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.source_columns.discover@1` | integration | read | vacuous | partial_signal_only | $.mapping_gid.minLength<br>$.limit.maximum<br>$.limit.minimum | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping.update@1` | integration | write | vacuous | partial_signal_only | $.gid.minLength<br>$.expected_revision.minimum<br>$.field_mappings.maxItems；另有 3 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping_target.search@1` | integration | read | vacuous | partial_signal_only | $.ontology_object_gids.maxItems<br>$.ontology_object_gids.minItems<br>$.ontology_object_gids[].minLength | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.mapping_target.upsert@1` | integration | write | vacuous | partial_signal_only | $.binding_id.minLength<br>$.ontology_object_gid.minLength<br>$.target_domain.minLength；另有 11 项 | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `integration.sync.start@1` | integration | write | vacuous | partial_signal_only | $.mapping_gid.minLength | connector_runtime_unavailable<br>credential_enrollment_invalid<br>credential_enrollment_unavailable；另有 4 项 | — |
| `knowledge.context.retrieve@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum<br>$.attachments.maxItems；另有 1 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.acl.grant@1` | knowledge | write | generated_from_description | partial_signal_only | $.subject_type.enum<br>$.permission.enum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.acl.list@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.acl.revoke@1` | knowledge | write | generated_from_description | partial_signal_only | $.subject_type.enum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.archive.atomic.documents_archive@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.archive@1` | knowledge | write | generated_from_description | partial_signal_only | $.operation.enum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.create@1` | knowledge | write | generated_from_description | partial_signal_only | $.title.maxLength<br>$.title.minLength<br>$.slug.pattern；另有 3 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.diff@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.get@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.history.get@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.restore@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.revise@1` | knowledge | write | generated_from_description | partial_signal_only | $.markdown.minLength<br>$.title.maxLength<br>$.change_summary.maxLength | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.document.search@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.entry.change.apply.atomic.entries_create@1` | knowledge | write | generated_from_description | partial_signal_only | $.contributors.maxItems<br>$.attachments.maxItems<br>$.tags.maxItems；另有 7 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.entry.change.apply.atomic.entries_delete@1` | knowledge | write | generated_from_description | partial_signal_only | $.contributors.maxItems<br>$.attachments.maxItems<br>$.tags.maxItems；另有 7 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.entry.change.apply.atomic.entries_update@1` | knowledge | write | generated_from_description | partial_signal_only | $.contributors.maxItems<br>$.attachments.maxItems<br>$.tags.maxItems；另有 7 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.entry.change.apply@1` | knowledge | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.arguments.contributors.maxItems<br>$.arguments.attachments.maxItems；另有 8 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.get@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply.atomic.folders_create@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.sort_order.maximum<br>$.sort_order.minimum；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply.atomic.folders_delete@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.sort_order.maximum<br>$.sort_order.minimum；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply.atomic.folders_update@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.sort_order.maximum<br>$.sort_order.minimum；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply.atomic.items_create@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.sort_order.maximum<br>$.sort_order.minimum；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply.atomic.items_delete@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.sort_order.maximum<br>$.sort_order.minimum；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply.atomic.items_update@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.sort_order.maximum<br>$.sort_order.minimum；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.change.apply@1` | knowledge | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.arguments.name.maxLength<br>$.arguments.sort_order.maximum；另有 7 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.read.atomic.folders_list@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.read.atomic.items_get@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.read.atomic.items_history_get@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.read.atomic.items_list@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.hub.read@1` | knowledge | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.arguments.limit.maximum<br>$.arguments.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.migration.status@1` | knowledge | read | generated_from_description | partial_signal_only | $.scan_limit.maximum<br>$.scan_limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.personalization.change.apply.atomic.favorites_toggle@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.personalization.change.apply.atomic.recent_record@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.personalization.change.apply@1` | knowledge | write | generated_from_description | partial_signal_only | $.operation.enum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.personalization.read.atomic.favorites_list@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.personalization.read.atomic.recent_list@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.personalization.read@1` | knowledge | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.arguments.limit.maximum<br>$.arguments.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.proposal.get@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.proposal.list@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.proposal.outbox.list@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.proposal.outbox.retry@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.proposal.review@1` | knowledge | write | generated_from_description | partial_signal_only | $.decision.enum<br>$.review_note.maxLength | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.propose@1` | knowledge | write | generated_from_description | partial_signal_only | $.tags.maxItems | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.reference_data.change.apply@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.reference_data.read@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.reference_dataset.publish@1` | knowledge | write | generated_from_description | partial_signal_only | $.dataset_gid.minLength<br>$.expected_version.minimum<br>$.schema.fields.maxItems；另有 6 项 | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.search@1` | knowledge | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.space.change.apply.atomic.spaces_archive@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.space.change.apply.atomic.spaces_update@1` | knowledge | write | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.space.change.apply@1` | knowledge | write | generated_from_description | partial_signal_only | $.operation.enum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.space.create@1` | knowledge | write | generated_from_description | partial_signal_only | $.name.maxLength<br>$.name.minLength<br>$.visibility.enum | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `knowledge.space.search@1` | knowledge | read | generated_from_description | partial_signal_only | — | knowledge_storage_unavailable<br>proposal_state_conflict<br>publication_in_progress；另有 2 项 | — |
| `ontology.change.proposal.create@1` | ontology | write | generated_from_description | partial_signal_only | $.changes.minItems | — | — |
| `ontology.change.proposal.get@1` | ontology | read | generated_from_description | unproven | — | — | — |
| `ontology.change.proposal.review.submit@1` | ontology | write | generated_from_description | partial_signal_only | $.content_sha256.pattern<br>$.decision.enum<br>$.comment.maxLength | — | — |
| `ontology.change.proposal.search@1` | ontology | read | generated_from_description | unproven | — | — | — |
| `ontology.concept.get@1` | ontology | read | generated_from_description | partial_signal_only | $.kind.enum<br>$.view.enum | — | — |
| `ontology.concept.resolve@1` | ontology | read | generated_from_description | unproven | — | — | — |
| `ontology.mapping.assess@1` | ontology | read | generated_from_description | partial_signal_only | $.source.kind.enum<br>$.target.kind.enum | — | — |
| `ontology.mapping.change.apply@1` | ontology | write | generated_from_description | unproven | — | — | — |
| `ontology.object.list@1` | ontology | read | generated_from_description | partial_signal_only | $.kinds.maxItems<br>$.kinds[].enum<br>$.limit.maximum；另有 3 项 | — | — |
| `ontology.release.activate@1` | ontology | write | generated_from_description | partial_signal_only | $.release_sha256.pattern<br>$.attestations[].blocking_count.minimum | — | — |
| `ontology.release.diff@1` | ontology | read | generated_from_description | unproven | — | — | — |
| `ontology.release.get@1` | ontology | read | generated_from_description | unproven | — | — | — |
| `ontology.release.publish@1` | ontology | write | generated_from_description | partial_signal_only | $.content_sha256.pattern | — | — |
| `ontology.release.search@1` | ontology | read | generated_from_description | unproven | — | — | — |
| `ontology.schema.change.apply@1` | ontology | write | generated_from_description | unproven | — | — | — |
| `base.project.search@1` | project_management | read | generated_from_description | partial_signal_only | $.query.maxLength<br>$.query.minLength<br>$.limit.maximum；另有 1 项 | — | — |
| `project.approval.change.apply.atomic.approval_orders_approve@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.approval.change.apply.atomic.approval_orders_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.approval.change.apply.atomic.approval_orders_reject@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.approval.change.apply.atomic.approval_orders_start@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.approval.change.apply.atomic.approval_orders_withdraw@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.approval.change.apply.atomic.approval_scope_upgrade_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.approval.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.approval.order.reject@1` | project_management | write | generated_from_description | partial_signal_only | $.order_gid.maxLength<br>$.order_gid.minLength<br>$.comment.maxLength；另有 2 项 | — | — |
| `project.approval.read.atomic.approval_orders_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.approval.read.atomic.approval_orders_search@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.approval.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.change_log.read.atomic.change_logs_search@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.change_log.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.collaboration.change.apply.atomic.collaboration_sessions_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.collaboration.change.apply.atomic.collaboration_sessions_end@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.collaboration.change.apply.atomic.collaboration_sessions_join@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.collaboration.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.collaboration.read.atomic.collaboration_sessions_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.collaboration.read.atomic.collaboration_sessions_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.collaboration.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.follow.change.apply.atomic.follows_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.follow.change.apply.atomic.follows_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.follow.change.apply.atomic.follows_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.follow.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.follow.read.atomic.follows_check@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.follow.read.atomic.follows_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.follow.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.issue.change.apply.atomic.issues_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.issue.change.apply.atomic.issues_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.issue.change.apply.atomic.issues_promote@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.issue.change.apply.atomic.issues_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.issue.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.issue.read.atomic.issues_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.issue.read.atomic.issues_search@1` | project_management | read | generated_from_description | partial_signal_only | $.arguments.page_size.maximum<br>$.arguments.page_size.minimum<br>$.arguments.scope.team_gids.maxItems；另有 2 项 | — | — |
| `project.issue.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.list.change.apply.atomic.item_entries_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.list.change.apply.atomic.item_entries_replace@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.list.change.apply.atomic.lists_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.list.change.apply.atomic.lists_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.list.change.apply.atomic.lists_retarget@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.list.change.apply.atomic.lists_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.list.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.list.read.atomic.item_entries_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.list.read.atomic.lists_search@1` | project_management | read | generated_from_description | partial_signal_only | $.arguments.scope.team_gids.maxItems<br>$.arguments.scope.team_member_gids.maxItems<br>$.arguments.scope.project_gids.maxItems | — | — |
| `project.list.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.member.change.apply.atomic.members_add@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.member.change.apply.atomic.members_line_assignment_replace@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.member.change.apply.atomic.members_remove@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.member.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.member.read.atomic.members_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.member.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.notification.change.apply.atomic.notifications_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.notification.change.apply.atomic.notifications_mark_all_read@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.notification.change.apply.atomic.notifications_mark_read@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.notification.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.notification.read.atomic.notifications_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.notification.read.atomic.notifications_unread_count@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.notification.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.permission_request.change.apply.atomic.permission_requests_approve@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.permission_request.change.apply.atomic.permission_requests_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.permission_request.change.apply.atomic.permission_requests_reject@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.permission_request.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.permission_request.read.atomic.permission_requests_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.permission_request.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.project.change.apply.atomic.projects_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.project.change.apply.atomic.projects_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.project.change.apply.atomic.projects_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.project.change.apply.atomic.vehicle_models_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.project.change.apply.atomic.vehicle_models_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.project.change.apply.atomic.vehicle_models_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.project.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.project.read.atomic.projects_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.project.read.atomic.projects_search@1` | project_management | read | generated_from_description | partial_signal_only | $.arguments.scope.team_gids.maxItems<br>$.arguments.scope.team_member_gids.maxItems<br>$.arguments.scope.project_gids.maxItems | — | — |
| `project.project.read.atomic.vehicle_models_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.project.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.sharing.change.apply.atomic.share_links_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.sharing.change.apply.atomic.share_links_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.sharing.change.apply.atomic.shares_item_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.sharing.change.apply.atomic.shares_item_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.sharing.change.apply.atomic.shares_list_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.sharing.change.apply.atomic.shares_list_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.sharing.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.sharing.read.atomic.share_links_resolve@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.sharing.read.atomic.shares_list_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.sharing.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.task.change.apply.atomic.task_dependencies_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply.atomic.task_dependencies_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply.atomic.task_dependencies_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply.atomic.tasks_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply.atomic.tasks_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply.atomic.tasks_promote@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply.atomic.tasks_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.task.read.atomic.task_dependencies_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.task.read.atomic.tasks_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.task.read.atomic.tasks_search@1` | project_management | read | generated_from_description | partial_signal_only | $.arguments.page_size.maximum<br>$.arguments.page_size.minimum<br>$.arguments.scope.team_gids.maxItems；另有 2 项 | — | — |
| `project.task.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.task_template.change.apply.atomic.task_templates_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply.atomic.task_templates_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply.atomic.task_templates_instantiate@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply.atomic.task_templates_items_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply.atomic.task_templates_items_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply.atomic.task_templates_items_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply.atomic.task_templates_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.task_template.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.task_template.read.atomic.task_templates_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.task_template.read.atomic.task_templates_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.task_template.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.workbench.change.apply.atomic.annotations_put@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.workbench.change.apply.atomic.workbenches_create@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.workbench.change.apply.atomic.workbenches_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.workbench.change.apply.atomic.workbenches_overrides_delete@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.workbench.change.apply.atomic.workbenches_overrides_upsert@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.workbench.change.apply.atomic.workbenches_update@1` | project_management | write | generated_from_description | unproven | — | — | — |
| `project.workbench.change.apply@1` | project_management | write | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `project.workbench.read.atomic.annotations_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.workbench.read.atomic.workbenches_list@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.workbench.read.atomic.workbenches_overrides_get@1` | project_management | read | generated_from_description | unproven | — | — | — |
| `project.workbench.read@1` | project_management | read | generated_from_description | partial_signal_only | $.operation.enum<br>$.operation.maxLength<br>$.operation.minLength | — | — |
| `simulation.environment.archive@1` | simulation | write | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.environment.create@1` | simulation | write | generated_from_description | partial_signal_only | $.execution_plan_ref.revision.minimum<br>$.execution_plan_ref.content_hash.pattern<br>$.model_snapshot_ref.snapshot_hash.pattern；另有 7 项 | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.environment.get@1` | simulation | read | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.environment.search@1` | simulation | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.parameter_set.create@1` | simulation | write | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.parameter_set.get@1` | simulation | read | generated_from_description | partial_signal_only | $.parameter_set_ref.version.minimum<br>$.parameter_set_ref.content_hash.pattern | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.parameter_set.search@1` | simulation | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.result.compare@1` | simulation | read | generated_from_description | partial_signal_only | $.left_result_ref.source_fingerprint.pattern<br>$.left_result_ref.result_hash.pattern<br>$.right_result_ref.source_fingerprint.pattern；另有 1 项 | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.result.get@1` | simulation | read | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.run.get@1` | simulation | read | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.run.search@1` | simulation | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.run.start@1` | simulation | write | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.solver_profile.create@1` | simulation | write | generated_from_description | partial_signal_only | — | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.solver_profile.get@1` | simulation | read | generated_from_description | partial_signal_only | $.simulation_profile_ref.version.minimum<br>$.simulation_profile_ref.content_hash.pattern | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |
| `simulation.solver_profile.search@1` | simulation | read | generated_from_description | partial_signal_only | $.limit.maximum<br>$.limit.minimum | parameter_set_not_found<br>simulation_environment_not_found<br>simulation_profile_not_found；另有 5 项 | — |

## 限制与下一步

1. 当前 `provider_ref` 只精确到领域 Provider，例如 `craft.provider`，不能把某条业务判断可靠映射到某个 Capability。
2. 当前 `test_refs` 均指向通用 mandatory contract cases，不能证明某一条领域规则的边界值和拒绝路径。
3. 下一步应先为写能力和高风险读取能力补登记；不要把 479 个能力机械地各写一条虚假通用规则。
4. 对确实不承载业务不变量的能力，由领域 Owner 填写 `no_business_invariant_reason`，并接受 Release Gate 校验。
