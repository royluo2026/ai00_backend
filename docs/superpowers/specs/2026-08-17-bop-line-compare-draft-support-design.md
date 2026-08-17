# BOP 线体对比未发布版本支持设计

## 目标

取消“BOP 必须发布后才能在线体对比插件中使用”的限制。插件仍只读取一个精确、受控的 BOP 修订版，不读取不确定的最新状态。

## 根因

插件 1.0.0 使用 `craft.bop.execution_structure.get@1`。该能力只提供正式发布的执行结构，Provider 会对没有 `published_at` 的 BOP 返回 `version_not_published`。

## 设计

1. Manifest 将 `craft.bop.execution_structure.get@1` 替换为 `craft.bop.execution_structure.preview@1`，能力总数仍为五个。
2. `craft.bop.version.list@1` 返回的 `revision` 成为结构读取的必需输入。
3. 运行时调用：

```json
{
  "version_gid": "<selected-version-gid>",
  "expected_revision": 4
}
```

4. 已发布、草稿和其他未归档版本采用同一读取路径。返回结构的 `official=false` 仅表示本次使用的是精确修订版预览，不影响插件对比。
5. 若版本列表未提供有效正整数 `revision`，插件显示 `revision_required`，不得回退到不受控读取。
6. 界面文案从“正式执行结构”改为“指定修订版执行结构”，不再提示用户必须发布。

## 测试与发布

- 新增失败测试，证明未发布 BOP 使用 `preview@1` 且携带 `expected_revision`。
- 验证 Manifest 权限与实际调用完全一致。
- Plugin SDK 全量测试和相关后端 Mount 测试必须通过。
- 构建、签名并发布 `1.0.1`，升级现有 `devteam.ai00.bop-line-compare` 安装并验证五个 Mount 授权。

## 非目标

- 不修改 Craft Provider 的正式发布语义。
- 不新增 Capability。
- 不允许无修订号或自动追随最新修订版。
