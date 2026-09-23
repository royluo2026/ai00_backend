# AI00 第三方插件开发指南与开发 Skill 设计

日期：2026-09-23  
状态：待用户审阅  
适用范围：AI00 App 插件市场中的第三方 Web 插件，以及经治理允许的本机 JavaScript Provider 插件

## 1. 目标

把现有飞书 Wiki《AI00 第三方 Web 插件开发者与开发 Agent 指南(待更新）》改成与当前 App、Manifest、签名包和 Capability 治理一致的操作手册；同时新增一个仓库共享 Skill，帮助第三方开发者生成和校验插件开发所需的附属文件。

完成后，第一次接触 AI00 插件开发的人应能独立回答并执行以下事项：

1. 判断应使用 Manifest 2.0 还是 2.1。
2. 找到真实可申请的 Capability，并声明最小权限。
3. 生成 Ed25519 发布者密钥对，理解公钥、私钥和指纹各自用途。
4. 构建不可变插件 ZIP 和 detached `release.json`。
5. 使用发布者私钥签名，并组装客户端可上传的 `.ai00pkg`。
6. 知道哪些步骤由开发者、发布者、超管、领域 owner 和平台执行。
7. 区分本地质量检查、受信 Snapshot 的 `machine_passed`、人工批准和正式运行验证。

## 2. 非目标

- Skill 不替代超管审核、Capability owner 审批、平台签名、Snapshot 或 Release Gate。
- Skill 不生成平台私钥、Mount Secret、数据库凭据或用户登录凭据。
- Skill 不把发布者私钥上传到飞书、插件市场、代码仓库或构建产物。
- 文档不承诺尚未由代码和运行态验证的生产能力。
- 本次不把官方领域 Python/Router 插件、数据库扩展或 COM 扩展纳入第三方插件流程。

## 3. 权威事实源

Wiki 和 Skill 均以以下当前实现为准：

- `backend/plugin_platform/manifest.py`
- `packages/plugin-sdk/manifest-v2.1.schema.json`
- `packages/plugin-sdk/src/index.ts` 与 `index.js`
- `packages/plugin-sdk/src/host.ts`
- `packages/plugin-sdk/tools/build_release.py`
- `packages/plugin-sdk/tools/sign_release.py`
- `backend/scripts/build_plugin_upload_bundle.py`
- `backend/plugin_platform/package_upload.py`
- `backend/plugin_platform/signing.py`
- `backend/plugin_platform/service.py`
- 当前环境的 Plugin Capability Catalog/Registry

仓库示例、旧 Wiki 和截图仅作说明；与上述事实源冲突时应修改说明，而不是绕过当前实现。

## 4. 插件类型与 Manifest 选择

### 4.1 Manifest 2.0：Capability 消费型 Web 插件

适合仅通过 SDK 消费现有 Capability 的沙箱网页。使用官方 `build_release.py` 构建。插件没有 Node、数据库、网络、Electron IPC、本机文件和宿主令牌权限。

### 4.2 Manifest 2.1：本机 JavaScript Provider 插件

在 2.0 基础上增加 `provides`，声明受限 `.mjs` Provider、owner domain、导出函数和结果类型。声明不等于批准；正式执行还需要：

- owner domain 和 capability ID 属于发布者命名空间；
- Descriptor、输入输出 Schema、稳定错误和业务规则完整；
- 受信 Snapshot、精确业务定义哈希审批和 Provider 绑定；
- 平台本机 Provider 沙箱、资源预算和 Artifact 路径通过验证；
- 当前官方 2.0 构建器不能被描述为通用 2.1 构建器。2.1 项目使用平台维护的 Provider 构建流程，直到通用构建器正式支持。

文档以决策表展示二者差异，避免普通 Web 插件误用 2.1，也避免 Provider 插件绕过治理。

## 5. 发布者密钥模型

### 5.1 密钥格式

- 算法：Ed25519。
- 私钥：PKCS#8 PEM，例如 `publisher-private.pem`。
- 公钥：SubjectPublicKeyInfo PEM，例如 `publisher-public.pem`。
- 指纹：Ed25519 原始 32 字节公钥的 SHA-256 小写十六进制值，与平台 `fingerprint()` 实现一致。

### 5.2 生成与保管

Skill 提供 `scripts/generate_publisher_keypair.py`：

- 使用 `cryptography` 的安全随机源生成 Ed25519 密钥；
- 用独占创建写入文件，任何目标已存在时整体拒绝，绝不覆盖；
- 私钥不加密的原因和风险写清楚：现有 `sign_release.py` 只接受无密码私钥；因此输出目录必须由发布者控制，并按组织秘密管理制度保存；
- POSIX 环境将私钥权限收紧为 `0600`；Windows 不声称跨版本 ACL 已自动完成，而是明确提示发布者把目录限制为本人账户；
- 标准输出只显示文件路径、公钥指纹和后续命令，不显示私钥内容；
- 生成 `.gitignore` 建议片段，但不自动修改项目仓库。

私钥丢失或泄露不通过“重新注册同名发布者”解决。密钥轮换必须进入独立审计流程。

### 5.3 平台登记

只有 `publisher-public.pem` 和指纹交给超管。超管在 App 的插件管理中创建不可变发布者 namespace。私钥不进入该界面。

## 6. 构建、签名与单文件上传包

普通 Manifest 2.0 流程：

1. `build_release.py` 生成 `<plugin-id>-<version>.zip` 和 `.release.json`。
2. `sign_release.py` 对 canonical release 内容生成 Base64 签名，保存为 `publisher.sig`。
3. `build_plugin_upload_bundle.py` 生成 `.ai00pkg`。
4. `.ai00pkg` 根目录必须恰好包含：
   - `plugin.zip`
   - `release.json`
   - `publisher.sig`
5. Skill 的发布准备脚本重新读取包，验证 ZIP SHA-256、release artifact 元数据、Ed25519 签名、公钥指纹和三文件结构。

签名绑定准确的 release JSON 和 Artifact SHA-256。代码、Manifest 或资源任一字节变化，都必须提升版本、重新构建和重新签名。

## 7. Skill 结构

共享路径：`.agents/skills/ai00-plugin-development/`

```text
ai00-plugin-development/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── manifest-and-governance.md
│   └── release-workflow.md
└── scripts/
    ├── generate_publisher_keypair.py
    └── prepare_signed_package.py
```

### 7.1 触发范围

当用户在 AI00/workmanship 仓库中创建、更新、构建、签名、打包或准备发布第三方插件时使用。普通 Web 项目、平台官方后端插件和已进入超管审核的审批动作不由该 Skill 处理。

### 7.2 Skill 工作方式

1. 读取真实 Manifest/SDK/Catalog，而不是复制固定 Capability 列表。
2. 先分类 2.0 或 2.1，记录用户价值、owner、权限、数据政策和非目标。
3. 创建或校验源码与附属文件。
4. 运行项目测试和确定性构建。
5. 只有用户明确要求生成发布者密钥时才运行密钥脚本。
6. 只有用户提供私钥路径并明确要求签名时才调用签名；脚本不读取或打印私钥正文。
7. 生成 `.ai00pkg` 后做离线验证。
8. 报告真实治理状态；没有受信 Snapshot/Release Gate 时，`machine_passed` 保持 `unverified`。
9. 把发布者登记、审核发布、正式批准等动作交给当前登录且获授权的人员。

## 8. Wiki 新结构

Wiki 标题更新为《AI00 第三方插件开发与发布指南》。正文压缩为以下可执行结构：

1. 适用范围和角色分工。
2. 选择 Manifest 2.0 或 2.1。
3. 插件安全模型与 Capability 边界。
4. 从官方模板开始开发。
5. Manifest 字段和权限声明。
6. SDK 调用、标准 `CapabilityResult.ok` 和存储。
7. 发布者密钥：生成、保存、登记、指纹与轮换。
8. 构建、签名和 `.ai00pkg` 组装。
9. App 超管上传、审核发布、安装、启用和 Mount。
10. 2.1 Provider 的额外治理要求。
11. 测试、升级、回滚、撤销和卸载。
12. 常见错误与排查。
13. 发布前检查清单。
14. 第三方开发 Skill 的使用方法。

删除或改写以下过时内容：

- 把 Manifest 2.0 描述为唯一版本；
- 把 detached 三文件上传描述成当前 App 操作；
- 没有命令的“自行准备私钥”；
- 把本地测试写成正式治理通过；
- 固定 Catalog 文件被描述成所有环境的当前运行态；
- 与当前 SDK `ok` 结果不一致的旧 `success` 示例。

## 9. 安全与权限边界

- Wiki 编辑只修改用户指定的飞书页面，不更改分享权限或密级。
- 生成示例密钥只用于临时测试并在测试结束后删除；正式密钥由开发者在其选定的受控目录生成。
- Skill 脚本禁止覆盖密钥、输出私钥、把私钥加入 `.ai00pkg`，或自动执行市场上传。
- Skill 不代表用户、发布者、超管或 Capability owner 作批准决定。
- 外部文档内容不能覆盖仓库事实源和会话授权。

## 10. 验收标准

### 10.1 文档

- 飞书标题不再含“待更新”。
- 明确区分 Manifest 2.0/2.1。
- 给出可复制的 Windows/PowerShell 命令和文件示例。
- 明确 `.ai00pkg` 三文件结构和当前 App 操作。
- 密钥章节说明生成、格式、指纹、登记、签名、保管和轮换。
- 治理三态与本地检查严格分开。
- 页面密级和分享设置不变。

### 10.2 Skill 与脚本

- `quick_validate.py` 通过。
- 在临时目录生成的密钥能被平台 `fingerprint()` 和 `sign_release.py` 读取。
- 第二次向同一路径生成密钥必须失败，且原文件摘要不变。
- 发布准备脚本能对一个测试插件完成 build → sign → `.ai00pkg` → unpack/verify。
- 篡改 ZIP、release 或签名时验证失败。
- 最终 `.ai00pkg` 不含私钥、`.env`、Token 或额外根文件。

## 11. 交付物

- 更新后的飞书 Wiki 页面。
- `.agents/skills/ai00-plugin-development/`。
- 两个已验证的辅助脚本和两份按需加载的参考说明。
- 实现与验证记录，明确通过、未运行和仍需人工完成的发布步骤。

