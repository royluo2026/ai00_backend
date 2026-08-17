# BOP 线体对比插件

这是一个 Manifest v2 Web Plugin 演示：它选择两个车型项目的 BOP 线体，按 VPPS、描述相似度或用户手工搜索对齐操作，再双列比较工艺、零件与工具。

插件只通过 SDK Mount 调用五个已声明能力：

1. `base.project.search@1` 搜索车型项目。
2. `craft.bop.version.list@1` 发现项目 BOP。
3. `craft.bop.execution_structure.get@1` 读取正式层级并选择线体。
4. `craft.bop.work_package.get@1` 投影线体的操作和资源。
5. `craft.bop.linked_parts.get@1` 补充零件名称、编号和使用位置。

比对逻辑运行在插件沙箱中，不访问 Cookie、数据库、内部 REST、OIS、Electron IPC 或宿主 DOM。工具详情当前只由工作包提供受控引用；缺少名称时界面明确显示引用，不虚构业务数据。

构建发布包：

```powershell
python ../../tools/build_release.py . --output-dir dist
```

运行 SDK 测试：

```powershell
npm test --prefix packages/plugin-sdk
```
