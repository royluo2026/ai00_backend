# AI00 Web 能力插件模板

这是一个可直接打包、安装的最小模板，演示三件核心事情：

1. 等待 AI00 宿主完成安全握手；
2. 通过 Capability Kernel 调用 `system.echo`；
3. 使用按租户和插件隔离、带乐观版本控制的命名空间存储。

## 改成自己的插件

先复制整个目录，然后修改 `plugin.json`：

- `publisher_id`：已在市场登记的发布者 ID，至少 3 个小写字符；
- `plugin_id`：必须以 `publisher_id.` 开头，并保持小写反向域名格式；
- `name`、`description`、`version`；
- `permissions`：只保留实际调用的能力；
- `data`：如插件保存个人数据，必须如实修改数据策略。

插件不能直接访问 Cookie、数据库、OIS、内部接口、Python、Shell 或本机能力。新增业务能力应先由平台实现并登记为 `plugin_callable` Capability，再由插件申请权限。不要在插件代码里保存密钥。

## 构建与校验

在 `packages/plugin-sdk` 目录运行：

```powershell
python tools/build_release.py templates/web-capability --output-dir templates/web-capability/dist
```

构建器会自动把当前版本的 `ai00-plugin-sdk.js` 放入 ZIP，并生成：

- 不可变、可复现的插件 ZIP；
- 带哈希、大小和 OIS 对象键的 `.release.json`。

随后使用发布者 Ed25519 私钥签名（私钥和签名文件不要提交）：

```powershell
python tools/sign_release.py templates/web-capability/dist/example.ai00.capability-starter-0.1.0.release.json publisher-private.pem
```

上传、审核、安装、启用、升级回滚与卸载的完整步骤见仓库根目录 `PLUGIN_PLATFORM_ACCEPTANCE.md`。

## 使用量

插件不自行写使用量。每次成功通过宿主调用能力，平台按插件、版本、入口和请求标识自动去重计数，供月度使用量与增量排行使用。
