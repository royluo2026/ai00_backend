# Phase 33：插件开发者模板与可部署 SDK 包

## 目标

提供一个第三方开发者可以直接复制、修改、构建和提交的 AI00 Web 插件模板，同时修复参考插件在打包后无法加载 SDK 的问题。

## 已完成

1. 新增 `packages/plugin-sdk/templates/web-capability`：
   - 有效的 Manifest v2；
   - 严格 CSP 和 `allow-scripts` 沙箱入口；
   - 宿主握手和授权能力展示；
   - `system.echo` Capability 调用；
   - 插件命名空间计数的读取、乐观写入和删除；
   - 数据策略、发布者命名空间和最小权限修改说明。
2. SDK 新增 `client.ready()`，插件可明确等待宿主握手，不再依赖用户点击时序。
3. 确定性构建器统一把当前 `ai00-plugin-sdk.js` 注入 ZIP 根目录：
   - 插件源码统一引用 `./ai00-plugin-sdk.js`；
   - 插件若自行放置同名文件，构建失败，避免 SDK 版本漂移；
   - 参考插件也改为使用包内 SDK。
4. 新增模板发布包回归：验证清单、哈希、ZIP、SDK 文件和模块引用均有效。
5. 模板使用量不自行记账；能力调用继续由平台按插件身份和请求标识自动统计、去重和月度汇总。

## 验证结果

- 三个 JavaScript 文件通过语法检查。
- 模板成功生成确定性 ZIP 和 detached release JSON。
- `test_plugin_acceptance_tooling` 4/4通过。
- 插件相关标准库测试19项通过；另2个插件测试模块依赖当前环境未安装的`pytest`，未执行，不计为失败回归。
- 扩大到全部不直接依赖pytest的测试后共运行136项：134项通过，2项在导入阶段因当前环境缺`pymysql`未运行；这是既有预发依赖门槛。
- OceanBase静态兼容审计通过；领域扫描保持136 tables / 0 unowned / 0 violations / 0 new / 603 resolved。
- ZIP实检包含`plugin.json`、入口资源和自动注入的`ai00-plugin-sdk.js`，并通过平台`validate_package`。

## 尚未宣称完成的事项

- 没有发布者私钥，因此没有生成真实发布签名。
- 当前环境仍缺真实OceanBase、OIS和预发管理员配置，因此没有执行上传、审核、安装、启用、升级回滚和卸载的真实链路。
- 真实验收继续按`PLUGIN_PLATFORM_ACCEPTANCE.md`执行，模板本身不绕过任何预发门禁。

## 审计重点

- 构建器注入的 SDK 与`web_sdk`兼容范围是否保持同步。
- 新增Capability必须先在平台登记为`plugin_callable`，模板不得诱导插件直连内部接口。
- 开发者修改模板时必须同步修改`permissions`和`data`，不能沿用不真实的数据声明。
