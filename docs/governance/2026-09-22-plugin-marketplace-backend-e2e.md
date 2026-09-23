# 插件市场后台全链路验收

## 1. Change classification
复用 Hello Capability 测试插件，生成1.0.20260922与1.1.20260922签名上传包；新增受控后台集成验收，修复 Base 安装/卸载声明强事务却返回普通对象的问题。保留既有 major/schema/strong consistency，不降低契约。

## 2. Authoritative context inspected
当前两工作树，已有Hello源码/SDK builder/发布者测试公钥，Artifact SDK、Gateway确认/可靠性、Base原子安装/卸载、SqlPluginLifecycleRepository、平台签名、升级/回滚、SqlMountSessionStore和真实插件资源route。旧桌面测试令牌已过期，不复用或伪造当前用户登录身份；用户随后明确选择后台虚拟上传，客户端上传由用户后验。

## 3. Reuse, atomicity, and ownership result
使用真实Capability Provider、Gateway、ArtifactService、Ed25519验签与平台签名、真实owner SQL、mount route。结果保存失败注入后，安装记录、幂等行与同连接outcome行均回滚。修复采用借入SQL连接，Provider返回TransactionalCapabilityOutput；Gateway负责结果入库与commit/rollback/close。异常关闭明确走rollback分支。该修复已独立只读复查。

## 4. Implementation boundary
实现修改仅backend/base/web_atomic.py与既有plugin_platform/service.py的事务所有权；不改变安装/卸载输入、权限、确认和保留数据规则。测试在临时SQLite和FilesystemObjectStorage中运行；MySQL语法由明确的测试适配层转换，Artifact元数据/审批/outcome身份为隔离测试替身，Craft只使用暴露元数据替身，不验证真实BOP业务。未操作当前业务账号或真实OIS。

## 5. Verification evidence
后台全链路及相关回归：50 passed；SDK基础协议2 passed；独立审查相关14 passed。完整步骤在backend-e2e-evidence.json：登记发布者→两版Artifact虚拟上传→签名提交→审核发布→安装停用态→启用→真实资源route返回200和sandbox CSP→升级使旧mount失效→回滚旧版→再次升级并确认启用新版→停用使mount失效→错误revision卸载拒绝→正确卸载并保留namespace数据。注入outcome持久化失败后业务、幂等、outcome三者回滚。
首次测试受pytest临时目录ACL/Windows长路径影响，改在工作区短路径隔离目录运行后发现真实transaction_participant_required阻断并修复；不是将初次失败记为通过。Catalog重新构建且--check通过。当前测试后端已加载修复。

## 6. Governance status
advisory=true；本次受控后台链路passed。
machine_passed=false（此前整库无关失败未解决）；human_approved=unverified；runtime_verified=unverified（本地隔离测试不替代服务器受控Snapshot/TestRun和桌面实机证据）。没有写入正式治理批准或修改可信ReleaseReport。

## 7. Findings and unresolved risks
已修复：安装/卸载Gateway强事务输出缺失，导致真实Gateway拒绝结果的问题。
未验收：真实OIS/当前业务数据库、Electron文件选择上传、窗口内插件页面实际加载和SDK业务按钮。backend mount route返回页面资源不等于Electron已打开插件。静态检查显示当前市场“已安装”列表尚无“打开插件”按钮；桌面挂载入口与SDK宿主接线仍需进一步核验，不能宣称桌面全链路完成。

## 手工验收包
- 初装：acme.ai00.hello-1.0.20260922.ai00pkg
- 升级：acme.ai00.hello-1.1.20260922.ai00pkg
- 发布者ID：acme；公钥文件：publisher-public.pem（复用已有测试发布者密钥）。若当前库未登记acme，可通过发布者登记界面录入公钥；已有不同公钥时不可覆盖，需新测试命名空间重新打包。

在超管管理中心→插件管理上传初装包，审核发布后安装；再上传升级包，审核后在市场选择更新。批准是用户实际业务操作，不代表对新增Capability的治理审批。真实环境版本若已存在，不重复提交相同不可变版本。
