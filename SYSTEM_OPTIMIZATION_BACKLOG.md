# AI00 系统优化待办表

> 建立日期：2026-08-05
> 状态基线：基于 `IMPROVEMENT_PLAN.md` 1.6、Capability专项审计和 Phase 1—43 实施日志整理
> 用途：本表是未完成优化项的动态执行清单；总体架构决策仍以专项规范和 ADR 为准，已完成事项以实施日志和验证证据为准。

## 1. 使用规则

- 优先级：`P0` 阻断可信运行或后续主线；`P1` 核心闭环；`P2` 规模化增强。
- 状态：`待讨论 → 待设计 → 设计中 → 待实施 → 实施中 → 待验证 → 已完成`；无法继续时标记 `阻塞`，主动后置时标记 `暂缓`。
- 只有完成标准全部满足且有可复查证据，才能标记为 `已完成`。
- 每项必须只有一个责任领域；跨域协作方写入依赖，不采用共同 Owner。
- Capability 讨论未结束前，只更新候选和决策状态，不提前注册或实现。

## 2. 当前优化待办

| ID | 领域/Owner | 优化项 | 完成标准 | 优先级 | 前置依赖 | 状态 | 证据/备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SYS-001 | 基座 | 真实 OceanBase/OIS/JWT 环境发布验收 | OceanBase 4.3.5+ MySQL模式、严格SQL、正式Migration、OIS、签名密钥和JWT环境完成部署；核心健康检查、迁移、回滚演练和验收记录通过 | P0 | 可用预发环境及凭据 | 待验证 | `IMPROVEMENT_PLAN.md` Phase 0A/1/1P退出门槛 |
| SYS-002 | 基座 | Capability Kernel生产硬化 | 输入输出Schema、标准错误、幂等、共享确认存储、可靠审计、限流和契约测试工具全部落地并通过故障测试 | P0 | SYS-001 | 实施中 | 核心契约、证据、确认、Catalog过滤和首批消费者契约已落地；真实故障与限流验收仍依赖SYS-001 |
| SYS-003 | 基座 | 运行时OpenAPI与静态API审计对账 | 测试部署导出的真实OpenAPI与578项静态活动路由完成差异对账，差异有明确处置 | P0 | SYS-001 | 待验证 | `API_CAPABILITY_AUDIT.md` §3.1 |
| SYS-004 | 跨域治理 | 五域数据与调用边界持续清理 | 新增代码无跨域SQL/JOIN/FK和内部包导入；遗留依赖有下降指标、Owner和迁移计划；CI拒绝新增违规 | P0 | 领域Owner确认 | 实施中 | `DEVELOPMENT_COLLABORATION_SPEC.md`、Phase 19/21/22 |
| SYS-005 | 跨域治理 | 完成系统级Capability候选逐项审议 | Craft、Simulation、Work、Ontology/Semantic、Rule、Agent、Equipment候选逐项冻结唯一结果、Owner、Schema、权限、错误、证据、重叠与消费者 | P0 | 当前讨论持续进行 | 设计中 | Craft、Ontology和第一轮系统级边界已确认；Simulation、Work、Rule等后续另行治理 |
| SYS-006 | 基座 | Version Graph Kernel版本图内核 | 评审并冻结Artifact、不可变Commit、父版本图、内容Hash、OIS快照、活动指针、fork、diff、merge预览及非破坏性restore等通用原语；明确基座与领域适配器边界，并以BOP和Knowledge Revision完成验证 | P1 | SYS-002、SYS-005 | 待设计 | 参考Git语义但不直接暴露Git命令；各领域只开放有业务意义的Capability |
| SYS-007 | 基座 | 已确认系统级Capability与控制面协议落地 | 实现并验证system.search、activity.search、job.get/cancel、identity.principal.search、lineage.get和change_impact.preview；Catalog、确认、事件/通知、OIS传输和数据库运维保持内部协议 | P1 | SYS-002、SYS-005、SEM-001 | 待验证 | 首批九项共享能力及服务端Catalog过滤已实现，见Phase 55/57；真实部署和跨域Provider验收未完成 |
| CRAFT-001 | Craft | 首批BOP读取能力设计与实现 | 已批准的版本查询、执行结构、零件关联、版本比较、工作包等能力完成契约、注册、测试和首个真实消费者迁移 | P0 | SYS-002、SYS-005 | 待验证 | 契约、注册、测试及Web版本列表/Agent执行结构消费者已迁移；待OceanBase真实数据烟测 |
| CRAFT-002 | Craft | Craft校验规则与Validation Policy治理 | 重新梳理现有校验；每项登记来源、Owner、适用范围、严重级别和执行机制；规则成熟后再冻结并测试`draft_check`、`publish_check`、`simulation_check`、`workstation_check` | P2 | 本体与规则Owner明确 | 待完善 | Policy技术框架与四项VPPS候选盘点已实现；现有规则不完善，不进入当前强制校验，见Phase 56/63 |
| CRAFT-003 | Craft | `craft.bop.version.validate`权威校验能力 | 能按冻结Policy返回可复现结论、规则/程序/本体版本、BOP Hash及证据；发布流程强制重新执行`publish_check` | P2 | CRAFT-002、SYS-002 | 暂缓 | 等成熟规则获批后实施；不得把当前四项候选直接升级为阻断规则 |
| CRAFT-004 | Craft | BOP草稿受治理写能力 | 冻结类型化变更Schema和`draft.change.preview/apply`契约；完成无副作用预览、Hash绑定、乐观并发、幂等、事务回滚、权限和审计测试 | P1 | SYS-002、SYS-005 | 实施中 | Phase 64 已完成离线契约与能力注册；真实事务/持久化/权限烟测待授权环境，详见 `docs/audit/phase64-craft-write-capabilities-plan.md` |
| CRAFT-005 | Craft | BOP创建与非破坏归档能力 | `version.create`按empty/bop_version/template/import_preview来源创建草稿；按状态机完成非破坏归档，保留不可变快照、确认和审计 | P1 | SYS-002、SYS-005 | 实施中 | Phase 64 已完成离线契约、创建/归档 Capability 与 migration；真实事务/持久化/权限烟测待授权环境，发布仍拆到 CRAFT-009 |
| CRAFT-006 | Craft | PBOM VPPS规则与校验治理 | 把现有四条检查作为候选规则重新验证；冻结主数据、算法、阈值和证据后，再决定是否实现`craft.pbom.vpps.validate` | P2 | CRAFT-002、SYS-002 | 待完善 | 当前实现不完善；仅作待办，不注册Capability，不把页面ignore视为正式让步 |
| CRAFT-009 | Craft | BOP发布能力 | 成熟的`publish_check`获批后，实现发布前重跑、不可变快照、状态机、确认和审计 | P2 | CRAFT-002、CRAFT-003、CRAFT-005 | 暂缓 | 当前不实现无规则发布，也不以不完善规则阻断发布 |
| CRAFT-007 | Craft | 决策PBOM VPPS让步机制 | 结合真实业务场景决定是否允许让步、由谁审批、适用范围、有效期、撤销和对发布的影响；只有决策通过后才提案具体Capability | P2 | CRAFT-006、审批流程需求 | 暂缓 | 当前不加入`waiver.create/revoke`，不得提前实现或公开 |
| CRAFT-008 | Craft | 退役PBOM→GBOP错误匹配模型 | 盘点并迁移`gbop-match-preview/confirm`、auto-link、staging等消费者；删除错误关系或转为真实BOP/GBOP来源关系；全过程保留数据迁移与回归证据 | P0 | CRAFT-001、真实数据盘点 | 待设计 | PBOM与GBOP没有业务关系，相关接口不得Capability化 |
| SEM-001 | 语义层 | 系统级受治理语义查询 | 冻结`semantic.context.get`、领域命名空间视图、深度/节点上限、ACL、来源版本、冲突和证据语义；至少由Craft场景验收 | P1 | SYS-005、本体Owner确认 | 实施中 | 命名视图、深度/节点上限及稳定引用契约已实现；Craft真实场景和ACL验收未完成 |
| SEM-002 | 语义层 | 本体Capability治理总项 | 已确认概念读取、映射评估、变更提案、人工评审、不可变发布、激活和版本查询/比较边界；底层CRUD、实例API和通用图查询不公开 | P1 | SEM-001设计 | 待设计 | 详细拆分见ONT-001至ONT-004 |
| ONT-001 | 本体 | 概念解析与定义读取 | 实现`ontology.concept.resolve/get`，支持活动或固定版本、summary/schema视图、歧义候选、版本和证据 | P0 | SYS-002、SEM-002 | 待验证 | 不可变release读取、消歧、固定版本及Agent概念解释适配已实现；待真实本体数据烟测 |
| ONT-002 | 本体 | 本体变更提案与人工评审 | 实现proposal create/get/search/review.submit；所有变更类型化、绑定基准版本；Agent不能提交approve | P1 | ONT-001、身份和评审政策 | 待验证 | 追加式提案修订、人工评审与Agent禁止批准已实现；待真实身份/并发验收 |
| ONT-003 | 本体 | 不可变Release发布、比较与激活 | 实现release publish/get/search/diff/activate；发布与激活分离；激活检查兼容、迁移、插件和规则门槛 | P1 | ONT-002、SYS-006、SYS-007 | 待验证 | 发布/激活分离、语义diff和激活门槛已实现；待OceanBase/OIS迁移与真实插件/规则兼容验收 |
| ONT-004 | 本体 | 外部概念映射评估 | 实现`ontology.mapping.assess`的结构兼容、冲突和expert_review_required结论，接入插件/导入审核但不直接建立映射 | P2 | ONT-001、真实外部映射样本 | 实施中 | 非持久化结构评估已实现；真实外部映射样本与插件/导入消费者尚未接入 |
| RULE-001 | 规则领域 | 通用规则库与规则引擎治理 | 规则提案、评审、发布、生效范围、版本、评估证据和退役闭环完成；规则引擎结果与领域最终结论明确分层 | P1 | SYS-005 | 待设计 | CRAFT-002可先以Craft政策治理启动 |
| AGENT-001 | Agent | 清除Agent对内部REST的旁路依赖 | 当前36类内部`/api/*`依赖全部迁移为真实可用Capability或从Tool Catalog移除；9个不存在路由不再向模型宣称可用 | P0 | SYS-002、对应领域Capability | 实施中 | Knowledge上下文、BOP执行结构和本体概念解释已迁移；其余内部REST及失效工具仍按`API_CAPABILITY_AUDIT.md` §7治理 |
| AGENT-002 | Agent | Pi Runtime与Harness主路径收口 | Web Agent统一进入Runtime；会话、任务、确认、取消、恢复和Tool选择由Runtime治理；Pi保持可替换Harness Adapter | P1 | AGENT-001、SYS-002 | 待实施 | `ADR-007_SYSTEM_AGENT_RUNTIME_HARNESS_BOUNDARIES.md` |
| AGENT-003 | Agent | 用户私有会话、记忆与团队知识边界验收 | 私聊/群聊/Web会话权限、个人记忆、团队知识提案和审计隔离通过安全测试；聊天不自动进入团队知识 | P1 | AGENT-002、Knowledge能力 | 待设计 | 飞书入口后置但隐私模型先统一 |
| KNOW-001 | 基座/Knowledge | Knowledge Hub切换到Revision Capability | 编辑、读取、Diff、回滚均走Revision Capability；真实OIS迁移验收后才清理旧`content_md`路径 | P0 | SYS-001 | 待实施 | `IMPROVEMENT_PLAN.md` Phase 2检查点 |
| KNOW-002 | 基座/Knowledge | 团队Markdown实时共创闭环 | 多人编辑、冲突处理、不可变版本、评论、提案评审、引用证据和完整修改归因通过端到端测试 | P1 | KNOW-001 | 待实施 | 所有已认证人员可看可改；空间不作ACL边界；Agent默认提案优先 |
| KNOW-003 | 基座/Knowledge | 退役文档ACL兼容面 | Web不再展示文档ACL管理；未注册ACL helper和迁移写入完成真实数据盘点后退役；是否删除旧表单独决策 | P1 | KNOW-001、KNOW-002 | 实施中 | 正常Capability已停止ACL读写；Web死入口已在本地分支`codex/knowledge-open-collaboration-web`提交`a71a401`，待集成；helper/旧表仍待真实数据盘点 |
| PLUGIN-001 | 基座/插件 | 轻量插件中心真实环境E2E | 参考插件完成上传、审核、发布、安装授权、调用计量、停用、升级、回滚、吊销和月度快照；在真实OceanBase/OIS/JWT环境通过 | P0 | SYS-001 | 待验证 | 首期约30人范围不再扩张 |
| PLUGIN-002 | 基座/插件 | 领域Capability安全开放机制 | Manifest精确版本授权、租户安装授权、用户ACL、风险确认、配额和审计取交集；先开放单项低风险只读能力 | P1 | SYS-002、SYS-005、PLUGIN-001 | 待设计 | 第三方代码不得注入主后端进程 |
| SIM-001 | Simulation | Craft到Simulation可复现闭环 | Simulation使用已发布`execution_structure`及固定Hash创建环境；来源、重建、补偿和一致性校验可复现 | P1 | CRAFT-001、SYS-002 | 待讨论 | 草稿预览环境必须显式标记，不能冒充正式来源 |
| RUNTIME-001 | Local Runtime | Runtime控制面与自动升级闭环 | 安装、注册、心跳、能力广告、命令领取、结果回传、凭据保护、灰度升级、失败回滚和兼容协商通过测试 | P1 | SYS-002 | 待实施 | Runtime不承载LLM和业务权限判断 |
| VIS-001 | VisMockup集成 | VisMockup受控操作闭环 | 连接、启动、打开模型、模型树、高亮、显隐、截图使用明确Capability和本地适配器完成端到端验收 | P1 | RUNTIME-001 | 待实施 | 与生产设备领域严格分离 |
| API-001 | 基座 | Public REST API稳定映射 | 只映射已治理Capability；身份、版本、幂等、错误、确认、限流和审计语义与Web/Agent一致 | P1 | SYS-002、首批领域Capability | 待验证 | v1 Catalog/invoke已统一版本、错误、证据与审计结果；限流、真实JWT和部署验收仍未完成 |
| MCP-001 | 基座 | MCP Gateway稳定映射 | MCP Tool与Capability一对一或有明确复合契约；动态发现、权限、错误、证据和审计通过互操作测试 | P1 | API-001或共享Gateway内核 | 待验证 | MCP使用服务端过滤Catalog并保留完整CapabilityResult；真实客户端互操作与权限烟测仍未完成 |
| EQUIP-001 | Equipment | 设备领域模型与首批只读能力 | 设备资产、状态、时间戳、来源、安全边界和Owner冻结；首批读取能力完成，不复用VisMockup或Runtime语义 | P2 | 五域边界、真实设备场景 | 待设计 | 写操作按具体设备和联锁单独提案 |
| FEISHU-001 | Agent | 飞书Agent入口 | 私聊、群聊邀请、身份映射、会话隔离、权限、引用、确认和审计完成；仅开放适合飞书的能力 | P2 | AGENT-002、AGENT-003 | 暂缓 | Web Agent优先完成 |
| CLEAN-001 | 跨域治理 | 兼容API和遗留实现退役 | Web/Agent/插件消费者迁移完成后，旧Capability注册表、兼容API、Electron和遗留Bridge按登记顺序删除并验证无调用 | P2 | 各迁移项完成 | 暂缓 | 禁止在消费者未清零前直接删除 |

## 3. 当前推荐执行顺序

1. 完成已实现 Capability 的真实环境验收准备，并继续清理消费者和领域边界。
2. 先实施 `CRAFT-004/005` 的安全写入、创建和非破坏归档，不引入未成熟 VPPS 规则。
3. 并行推进 `SYS-001`、`PLUGIN-001`、`KNOW-001` 和 `AGENT-001` 的验收与消费者闭环。
4. `CRAFT-002/003/006/009` 保留为规则治理、权威校验和发布待办，规则成熟后再恢复。
5. 随后进入 Simulation、插件领域开放、Public API/MCP和Local Runtime。

## 4. CRAFT-002 未来治理要求

首轮盘点必须为每项校验建立以下字段：

| 字段 | 要求 |
| --- | --- |
| Check ID | 稳定、不可复用 |
| 名称与业务含义 | 业务专家可以直接审阅 |
| 来源 | 企业制度、外部标准、项目要求、系统不变量或经验候选 |
| 来源版本与证据 | 文档版本、条款、链接或决策记录 |
| Owner与审核人 | 唯一业务Owner及发布权限人 |
| 适用范围 | 产品、项目、工艺类型、对象类型、生效时间及例外 |
| 执行机制 | 程序、本体约束、规则引擎或人工审批 |
| 严重级别 | 阻断、错误、警告或提示 |
| 输入事实 | 明确字段、类型、版本和来源 |
| 输出与解释 | 命中对象、原因、修复建议和证据 |
| 测试 | 正例、反例、边界例和历史回放 |
| 生命周期 | 草稿、评审、已发布、已废弃及替代规则 |

任何尚未找到可靠来源或适用边界的“经验规则”，只能登记为候选或提示，不得进入强制发布校验。

## 5. CRAFT-002 候选规则待办（2026-08-06）

以下检查来自 `plugins/craft/craft_backend/routers/ebom.py` 的现有实现。业务决策确认这些规则目前不完善，因此它们降为候选规则待办，不作为当前开发或发布流程的强制规则：

| Check ID | 当前实现 | 缺失治理字段 | 当前处置 |
| --- | --- | --- | --- |
| `vpps.master_data` | VPPS主数据及名称/描述一致性 | source_ref、Owner、阈值、算法版本、Policy版本、正反/边界/历史回放 | 候选待办；重新验证后再决定保留、修改或删除 |
| `vpps.parent` | 父级字段与实际父零件VPPS一致性 | source_ref、Owner、阈值、算法版本、Policy版本、正反/边界/历史回放 | 候选待办；重新验证后再决定保留、修改或删除 |
| `vpps.hierarchy_prefix` | 子项VPPS层级前缀检查 | source_ref、Owner、阈值、算法版本、Policy版本、正反/边界/历史回放 | 候选待办；重新验证后再决定保留、修改或删除 |
| `vpps.fastener_main_part` | 紧固件几何/描述主件一致性 | source_ref、Owner、阈值、算法版本、Policy版本、正反/边界/历史回放 | 候选待办；重新验证后再决定保留、修改或删除；现有ignore不视为正式让步 |

在规则成熟并获得业务批准前，`craft.bop.version.validate`、`craft.bop.version.publish` 和 `craft.pbom.vpps.validate` 保持未注册。该限制只阻止权威校验和发布，不再阻止以下独立安全能力的开发：

- `craft.bop.version.create`
- `craft.bop.version.archive`
- `craft.bop.draft.change.preview/apply`
- `craft.bop.import.preview`
