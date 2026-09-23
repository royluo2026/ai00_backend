# 桌面超管插件文件上传（advisory）

## 1. Change classification
新增 base.plugin.marketplace.release.submit@1，兼容扩展桌面原生文件选择类型 plugin_package；新增超管管理中心导航与上传/安装按钮。复用 Artifact、签名、提交、审核与安装契约，不引入不受治理的业务 HTTP。

## 2. Authoritative context inspected
Base official Provider/Catalog/Descriptor、Artifact SDK 的用户/租户和不可变摘要检查、Main DesktopArtifacts 与 IPC 参数白名单、PluginManifestV2、ZIP安全检查、发布者签名与服务端平台签名、OIS不可变存储、Gateway确认与超时策略。市场运行仍仅支持当前Manifest允许的web runtime，不加载任意Python/后端Provider。

## 3. Reuse, atomicity, and ownership result
上传文件由 Main 原生选择并通过固定 Artifact 上传协议产生引用；release.submit 只接受 ArtifactRef，重读 Base 超管身份，从 Artifact Service 检查当前用户权属、字节数和SHA，再验证包结构/描述/签名，复用OIS及submit_release。其单一业务效果为登记待审核版本；不自动批准、安装或启用。审核与安装由用户分别确认。安装复用 base.plugin.installation.request.create@1，直接提交选中版本和摘要，不以列表第一页判断版本是否存在。

## 4. Implementation boundary
Base/已有plugin_platform、共享桌面Artifact原生选择、App管理页及manifest消费声明。新增.zip/.ai00pkg MIME映射，plugin_package专用上限102MiB，其内plugin.zip上限100MiB，外层恰好3个常规文件。保持其他文件类型原有限额。服务端最多1000项/单资源25MiB/展开250MiB沿用原包校验，并补重复路径及缺入口拒绝。write external consistency，owner自己提交；idempotency required/admin确认，web/api暴露，plugin/agent/mcp不暴露。服务端同步提交期限600秒，Main请求660秒；不声称有分布式强事务或可靠取消。

## 5. Verification evidence
后端48项通过（恶意包形状、签名拒绝发生在持久化前、描述摘要一致性、管理权限/事务及生命周期）；重复名称恶意测试产生预期zipfile warning。前端11项通过，包括原生ZIP选择/固定上传协议/无本地路径泄露、取消无提交、重复点击锁、提交后切待审核，以及16.05秒模拟慢服务超过旧15秒超时仍成功。DesktopArtifacts及Electron生命周期安全检查通过。Catalog --check、完整test-governance构建通过，4个服务资源与构建字节一致。
已使用原本地测试launcher重启：Electron PID329644、后端PID331228；后端health/ready 200，本地Catalog包含submit@1及600秒预算。修复本次重启日志编码为UTF-8。真实登录后的文件选择、实际OIS上传/审核/安装尚未执行，不将单元模拟或健康探测当成认证桌面验收。

## 6. Governance status
machine_passed=false（此前整库无关回归失败仍未消除；本次专项通过）；human_approved=unverified；runtime_verified=unverified；advisory=true。真实GID/业务哈希/源文件与日志摘要见同日plugin-upload-evidence.json，未生成伪造Snapshot/TestRun或修改签名ReleaseReport。

## 7. Findings and unresolved risks
存储与SQL提交不属于同一事务；中断可能留下未引用不可变文件，后续重试不会覆盖已有内容。超时后的同步工作可能仍完成，UI要求刷新权威列表后重试；不可变版本会拒绝重复登记。签名发布需要服务端有效平台密钥和已登记发布者公钥，普通源码ZIP不等于可安装发布包。真实插件业务验收及治理精确哈希审批仍unverified。

## 上传包格式与操作
入口：超管管理中心 → 插件管理 → 选择并上传插件文件；插件市场右上角“超管管理”也进入同一页面。

一个.ai00pkg或.zip文件，外层ZIP根目录必须恰好包含：
- release.json：完整规范化Manifest v2，artifact记录内部plugin.zip的SHA-256、大小和规范OIS object_key。
- publisher.sig：已登记发布者Ed25519私钥对canonical_release签名的Base64文本。
- plugin.zip：插件资源ZIP，根目录plugin.json为同一描述去掉artifact，包含声明的web入口。

开发者已有这三个签名发布文件时，可在后端工作树执行：

```powershell
python backend/scripts/build_plugin_upload_bundle.py --release release.json --signature publisher.sig --package plugin.zip --output plugin.ai00pkg
```

脚本只组包和检查内容，不自动签名或批准，且不覆盖已存在输出。用户上传→审核并发布→安装到当前团队；安装后在市场“已安装”中启用。
