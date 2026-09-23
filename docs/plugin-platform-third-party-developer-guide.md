# AI00 第三方插件开发与发布指南

更新日期：2026-09-23  
适用产品：AI00 客户端 App 插件市场  
适用对象：第三方开发者、发布者、Capability Owner、平台超管、租户管理员

> 本文以当前仓库的 Manifest 解析器、Plugin SDK、签名校验、上传包和 Capability 治理实现为准。旧文档、截图和测试包只能作为示例，不能替代当前 Catalog、受信 Snapshot 或 Release Gate。

## 1. 适用范围和角色分工

本文覆盖两类第三方 App 插件：消费现有 Capability 的沙箱 Web 插件，以及经治理允许、提供本机 JavaScript Provider 的插件。它不覆盖官方 Python/Router 插件、数据库扩展、COM 扩展或平台私钥。

| 角色 | 负责事项 |
|---|---|
| 开发者 | 源码、Manifest、最小权限、本地测试、构建和离线校验 |
| 发布者 | 保管发布者私钥、签名不可变版本、提交审核 |
| Capability Owner | 确认业务定义、Schema、稳定错误、权限和治理证据 |
| 平台超管 | 登记发布者公钥、上传或接收包、审核、发布、撤销 |
| 租户管理员 | 安装、启用、停用、卸载，以及租户范围授权 |
| 平台 | 校验签名与状态、执行沙箱和 Provider runtime fence、记录审计 |

开发、签名和本地验证均不等同于审核、发布、安装或治理批准。

## 2. 选择 Manifest 2.0 或 2.1

| 需求 | 版本 | 构建方式 | 额外治理 |
|---|---|---|---|
| Web UI 只调用已登记的 Capability | Manifest 2.0 | 官方通用构建器，本文 Skill 可完整准备包 | 常规发布者审核与插件生命周期 |
| 插件自己提供本机 JavaScript Provider | Manifest 2.1 | Provider 项目专用流程；通用助手会拒绝 | Owner、Descriptor、Provider 绑定、runtime fence、受信证据 |

如果只是做页面、读写插件命名空间存储、调用已有业务能力，应选 2.0。只有确实需要提供新业务执行能力时才选 2.1。`provides` 只是声明，不是批准，也不会自动让 Capability 可调用。

## 3. 安全模型与 Capability 边界

Web 插件在 `allow-scripts` 沙箱中运行，通过宿主注入的 SDK 与平台通信。它不能直接获得宿主登录令牌、Electron IPC、Node.js、数据库、本机文件或任意网络访问。插件只能调用已安装版本的 Manifest 中声明、当前租户授予、Catalog 主版本匹配的 Capability。

开始开发前必须查询当前环境的 Catalog，确认 Capability ID、major、输入输出和权限。不要从旧示例猜 ID。运行时可用：

```js
const granted = await client.ready();
console.log(client.catalogRelease());
console.log(client.capabilityMajor("craft.bop.version.list"));
```

权限遵循最小化原则。`permissions` 和 `capabilities.required/optional` 不能扩大 Provider 自身的授权边界。

## 4. 从官方模板开始

复制 `packages/plugin-sdk/templates/web-capability/` 到独立插件目录，再修改源码。不要把密钥、`.env`、令牌、构建输出或 `.ai00pkg` 放进源码目录。

推荐结构：

```text
my-plugin/
├── plugin.json
├── index.html
├── app.js
└── style.css
```

构建器会注入 `ai00-plugin-sdk.js`；源码目录中不要自行放置同名文件。

## 5. Manifest 字段与权限声明

最小 Manifest 2.0 示例：

```json
{
  "schema_version": "2.0",
  "plugin_id": "huangjing.demo.hello",
  "publisher_id": "huangjing",
  "name": "Hello Capability",
  "description": "列出可访问的 BOP 草稿版本",
  "version": "1.0.0",
  "compatibility": {
    "platform_api": ">=1.0.0 <2.0.0",
    "web_sdk": ">=0.1.0 <1.0.0"
  },
  "runtimes": {
    "web": {
      "entry": "index.html",
      "sandbox": "allow-scripts"
    }
  },
  "permissions": ["craft.bop.version.list"],
  "capabilities": {
    "required": [{"id": "craft.bop.version.list", "major": 1}],
    "optional": []
  },
  "plugins": {"required": [], "optional": []},
  "data": {
    "stores_personal_data": false,
    "retention": "none",
    "uninstall": "delete"
  }
}
```

要求：

- `plugin_id` 是小写反向域名式标识，并位于 `publisher_id` 命名空间下；
- `version` 是 SemVer。已提交的同一版本不可变；任何字节变化都应使用新版本；
- Web `entry` 必须是包内安全相对路径；
- 权限和依赖不得重复；
- `artifact` 不写在源码 `plugin.json` 中，由构建器生成 detached release envelope；
- 数据策略必须与实际存储行为一致。

## 6. SDK 调用、结果和插件存储

```html
<script type="module">
  import { Ai00PluginClient, isCapabilityResultV2 } from "./ai00-plugin-sdk.js";

  const client = new Ai00PluginClient();
  await client.ready();

  const result = await client.invoke("craft.bop.version.list", { limit: 20 });
  if (!isCapabilityResultV2(result)) throw new Error("unexpected_result");
  if (!result.ok) {
    document.body.textContent = `${result.status}: ${result.error?.code ?? "unknown_error"}`;
  } else {
    document.body.textContent = JSON.stringify(result.data, null, 2);
  }
</script>
```

新代码以 `CapabilityResult.ok` 为准。`success` 仅是迁移期兼容别名，不应继续写入新示例。

插件存储只在自己的命名空间内工作，并使用乐观版本：

```js
const current = await client.storageGet("settings/theme");
await client.storagePut("settings/theme", { mode: "dark" }, current.data?.version);
```

写入失败时保留平台错误码，不要把版本冲突吞掉或改成成功。

## 7. 发布者密钥：生成、保管和登记

### 7.1 格式

- 算法：Ed25519；
- 私钥：PKCS#8 PEM，通用示例名 `publisher-private.pem`；
- 公钥：SubjectPublicKeyInfo PEM，通用示例名 `publisher-public.pem`；
- 指纹：原始 32 字节 Ed25519 公钥的 SHA-256 小写十六进制。

### 7.2 生成

从仓库根目录运行：

```powershell
python .agents\skills\ai00-plugin-development\scripts\generate_publisher_keypair.py --publisher-id huangjing --output-dir D:\AI00-Secrets\huangjing
```

实际文件为 `huangjing-private.pem` 和 `huangjing-public.pem`。脚本使用独占创建；任一目标存在即失败，原文件保持不变。标准输出只包含路径和指纹，不包含私钥正文。

私钥必须保存在仓库和同步盘之外的受控目录。Windows 上把目录 ACL 限制为开发者本人，并使用组织认可的加密备份。当前签名工具读取无密码 PKCS#8 私钥，因此目录保护是必需条件。私钥丢失或泄露必须走审计密钥轮换，不能重新注册同名发布者来绕过。

### 7.3 超管登记和指纹核对

只把 `huangjing-public.pem` 与脚本显示的指纹交给获授权的超管。超管在客户端 App 的管理中心登记不可变 `publisher_id` 与 Ed25519 公钥。登记后，通过另一条可信通道核对平台显示指纹和本地指纹完全一致。

发布者私钥始终留在发布者受控环境；不进入市场、飞书、源码仓库、工单或插件包。

## 8. 构建、签名和 `.ai00pkg`

推荐使用 Skill 的一体化助手，它调用所选 SDK 根目录中的官方 2.0 构建器，签名并回读验证：

```powershell
python .agents\skills\ai00-plugin-development\scripts\prepare_signed_package.py --source .\my-plugin --sdk-root .\packages\plugin-sdk --private-key D:\AI00-Secrets\huangjing\huangjing-private.pem --public-key D:\AI00-Secrets\huangjing\huangjing-public.pem --output .\dist\huangjing.demo.hello-1.0.0.ai00pkg
```

`.ai00pkg` 是当前 App 上传的单文件压缩包，其根目录必须恰好包含：

```text
plugin.zip
release.json
publisher.sig
```

`publisher.sig` 是发布者私钥对 canonical release 内容的 Ed25519 Base64 签名。签名同时绑定完整 release Manifest 与 `plugin.zip` 的 SHA-256。助手会检查公私钥匹配、Artifact 大小和摘要、签名、插件 ID、版本及三文件结构，并拒绝覆盖任何已有输出。

如果需要分别调试底层工具，可查看帮助：

```powershell
python packages\plugin-sdk\tools\build_release.py --help
python packages\plugin-sdk\tools\sign_release.py --help
python backend\scripts\build_plugin_upload_bundle.py --help
```

日常提交应使用一体化助手，减少选错文件或签错 canonical bytes 的机会。

## 9. App 中的上传、审核、安装和打开

1. 平台超管先在“管理中心 → 插件管理”登记发布者公钥。
2. 超管上传一个 `.ai00pkg`，平台校验结构、版本、摘要、签名和 publisher namespace。
3. 超管审核并发布该不可变版本。
4. 租户管理员在一级 App“插件市场”安装并启用已发布版本。
5. 用户从工作台 App 面板或插件市场打开插件；平台为安装实例建立受限 Mount。

状态变化使用最新页面状态和服务端版本。审核、发布、安装、启用、停用、撤销是不同动作。不要重复提交已完成动作，也不要用浏览器网页版代替客户端 App 生命周期。

## 10. Manifest 2.1 Provider 的额外治理

2.1 的 `provides` 片段示例：

```json
{
  "schema_version": "2.1",
  "provides": [
    {
      "id": "huangjing.cad.layout.generate",
      "major": 1,
      "owner_domain": "huangjing.cad",
      "module": "providers/layout.mjs",
      "export": "invoke",
      "result": "artifact"
    }
  ]
}
```

必须同时满足：

- `owner_domain` 位于发布者命名空间下，Capability ID 位于 owner domain 下；
- `(id, major)` 唯一；module 是安全的包内 `.mjs` 路径；
- 真实 owner 与维护团队已登记；
- Descriptor 包含业务效果、不变量、closed 输入/输出/错误 Schema、副作用、授权、事务、幂等、生命周期、消费者、Provider/API/test refs 与 Catalog release；
- Provider Artifact 哈希、安装版本和治理绑定完全一致；
- 受信 Snapshot、精确业务定义哈希审批、runtime fence 和资源预算成立。

声明不代表批准。本文通用 `prepare_signed_package.py` 明确拒绝 2.1；使用项目维护的 Provider 构建和治理流程，不能降级成 2.0 包来绕过检查。

## 11. 测试、升级、回滚、撤销和卸载

发布前至少验证 Manifest、SDK 调用、权限拒绝、存储版本冲突、确定性构建、签名、包回读和实际 App Mount。2.1 还需 Provider 合约、稳定错误、资源限制、Artifact、绑定和 runtime fence 测试。

每个发布版本不可变。升级使用更高 SemVer 和新签名；回滚通过安装一个已发布的可用版本或发布修复版本完成，不能改写旧 Artifact。签名密钥泄露时由超管执行撤销和审计轮换。卸载行为必须符合 Manifest 的数据策略，尤其是 `delete`、`retain` 或 `export-then-delete`。

## 12. 常见错误与排查

| 错误 | 含义 | 处理 |
|---|---|---|
| `marketplace_state_conflict` | 页面基于旧状态提交，或当前状态不允许该动作 | 刷新市场/管理页，读取最新状态，只执行当前允许的下一步；不要重复点击 |
| `authentication_stale` | 当前登录新鲜度无法满足安装等敏感操作 | 在客户端重新完成登录或授权，刷新后再操作；不要复用旧令牌 |
| `plugin_mount_unavailable` | 插件尚未安装/启用、Mount 未建立，或运行实例不可用 | 确认版本已发布、租户已安装并启用，再重新打开；查看 Mount 审计 |
| `signature mismatch` / `invalid release signature` | 公钥、签名、release 或 ZIP 不是同一构建 | 核对 publisher 指纹，用匹配私钥重新构建新版本，禁止手改包内文件 |
| immutable version conflict | 同一 `plugin_id + version` 已存在但内容不同 | 提升 SemVer，重新构建和签名；不要覆盖旧版本 |
| missing governed Provider binding | 2.1 声明没有匹配的受信 Provider/owner/Snapshot/Artifact 绑定 | 补齐治理流程与精确版本绑定；不能只改 Manifest 或权限 |
| `Capability not granted` | Capability 未声明、未授权或 major 不匹配 | 查询当前 Catalog，修正 Manifest，重新发布并由管理员授权 |
| 打开后只有原始 JSON | 测试插件 UI 只用于验证 SDK 链路 | 这是示例展示方式；业务插件应渲染明确状态、错误和数据视图 |

## 13. 发布前检查清单

- [ ] 已选择正确的 Manifest 版本；2.1 已进入专用治理路径。
- [ ] `plugin_id` 属于已登记 publisher namespace，SemVer 是新版本。
- [ ] 当前 Catalog 中存在所有 Capability ID 和 major。
- [ ] 权限、必选/可选依赖、数据策略均为最小且真实。
- [ ] 新代码读取 `CapabilityResult.ok`，错误码不会被吞掉。
- [ ] 私钥位于仓库外并受 ACL/秘密管理保护；公钥指纹已核对。
- [ ] `.ai00pkg` 只有 `plugin.zip`、`release.json`、`publisher.sig`。
- [ ] 离线验证通过，包内没有私钥、令牌、`.env` 或额外根文件。
- [ ] 上传、审核、发布、安装、启用分别由获授权角色执行。
- [ ] 本地测试结果没有被写成正式治理批准。

治理三态独立记录。没有当前受信 Snapshot 和 Release Gate 时，应明确写：

```text
machine_passed=unverified
human_approved=unverified
runtime_verified=unverified
```

本地测试、签名成功和 `.ai00pkg` 回读成功只是候选证据，不能自行创建上述正式状态。

## 14. 使用第三方开发 Skill

仓库共享 Skill 位于：

```text
.agents/skills/ai00-plugin-development/
```

在 Codex 中可说：

```text
使用 $ai00-plugin-development，为这个 Manifest 2.0 插件检查权限、生成发布者密钥并准备可上传的 .ai00pkg。
```

Skill 会先读取当前 Manifest、SDK 与 Catalog，再选择 2.0/2.1 路径；它可以生成和验证附属文件，但不会自动登记发布者、上传、审核、发布、安装或改变治理状态。密钥生成与签名必须使用开发者明确指定的受控路径。

相关文件：

- `SKILL.md`：触发条件和工作流；
- `references/manifest-and-governance.md`：版本选择与治理边界；
- `references/release-workflow.md`：密钥、签名和包命令；
- `scripts/generate_publisher_keypair.py`：生成 Ed25519 发布者密钥；
- `scripts/prepare_signed_package.py`：构建、签名、组包和离线校验 Manifest 2.0。
