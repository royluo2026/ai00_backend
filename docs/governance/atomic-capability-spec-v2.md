# 原子业务能力开发治理规范 V2.5

> **版本说明：** V2.5 在 V2.4“业务目的—业务规则—执行证据”证明链上增加可执行的审核与发布闭环：机器负责确定性检查，AI 仅提供建议，`super_admin` 对精确业务定义哈希作出人工决定，发布报告分别披露机器、人工和运行时证据状态。V2.5 与旧条款冲突时，以本版本为准。
> V1.0 原文来源：飞书 wiki `UA1pwx3iZisRCMkmWgTcsI4MnKf`，docx `AAM3d7sxJoR18axFKFmc8ic3nMg`，读取时间：2026-08-21。
> 上位依据：《总装业务智能化四层治理指南》（wiki `Kmhowf4BiimR5mkWRZqc12Nvnve`）、《总装柔性智能基座协作开发规范 V1.0》（wiki `My2FwMxp9i82QkkvhqkcmcFknwe`）。

---

## 一、目的、适用范围与强制性

本规范适用于所有领域开发者、Capability Provider、API 适配器、插件作者和编码 Agent，覆盖 Capability 的提出、登记、实现、测试、发布、维护、变更、废弃和审计。Capability 是跨域共享的正式业务能力边界，不是普通函数名、数据库表名或某个页面的临时接口。

**MUST/必须：** 不满足即不得合并或发布；**MUST NOT/禁止：** 任何情况下不得执行；**SHOULD/应该：** 除非获得记录在案的例外批准，否则必须遵守。

治理中心、代码评审、自动化测试和发布闸门以本规范为判定依据；口头约定、聊天记录或未登记的本地脚本不能替代正式契约。

### V2.5 强制治理闭环

一次 Capability 治理不是“检查权限”或“跑一次测试”，而是以下连续且可追溯的控制环：

1. **登记与扫描：** 从受信 Catalog、Descriptor、Provider、API、测试和消费者来源形成不可变 Snapshot；扫描只读取治理输入，不得写业务领域表或生产 Catalog。
2. **七层机器分析：** 分别检查 L0 登记、L1 目的、L2 规则声明、L3 执行与测试映射、L4 机器检查、L5 人工批准、L6 运行效果；Finding 证据行和根因组必须分别计数。
3. **关系辅助识别：** 机器根据业务对象、动作、适用范围、输入输出、权限、规则区间和领域边界提出覆盖、重复、冲突、缺口候选。跨域候选必须同时列出全部相关 Capability，不能只把问题挂在其中一个能力上。
4. **人工决定：** 第一阶段只允许具有服务端可信有效身份的 `super_admin` 批准、拒绝或要求修改。页面自报角色、Agent、服务账号、委托身份和 AI 均不得批准。
5. **精确哈希绑定：** 人工决定必须同时绑定 `capability_version_gid`、`business_definition_hash`、证据 Snapshot 和决定理由。业务目的、规则、输入输出、Provider、执行位置等任何进入业务定义投影的内容变化后，旧批准立即失效。
6. **签名发布：** Release Gate 重新从受信 Catalog、持久化 Snapshot/Finding、当前精确哈希批准和受控测试证据推导结论，再生成不可变签名报告。报告重建禁止再次调用不可信 analysis runner，也不得接受调用方自报的通过状态。
7. **效果回流：** 运行效果证据按 Capability 版本和业务定义哈希追加记录。效果记录不能覆盖历史记录，也不能反向伪造机器通过或人工批准。

发布报告中的三个状态相互独立，禁止互相推导：

- `machine_passed`：当前 Snapshot 没有确定性 blocker；不表示人已经认可业务规则。
- `human_approved`：当前 Capability 版本的当前 `business_definition_hash` 已由可信 `super_admin` 批准；不表示已在受控环境运行。
- `runtime_verified`：当前版本与哈希已有受控环境、当前提交和当前测试运行绑定的效果证据；离线测试或模拟证据只能证明控制环可运行，不能冒充生产运行证明。

AI 输出必须标记为 advisory。AI 可以解释机器证据、对已存在的关系候选排序或建议审核问题，但 **MUST NOT** 创建确定性 blocker、降低 blocker 严重级别、批准、拒绝、合并、废弃、豁免或替审核人签名。

治理持久化采用职责分离：Catalog 保存受信业务定义投影及其哈希；治理 Snapshot/Store 保存扫描事实、Finding、关系候选、审核决定和效果证据；领域 Provider 保存并执行领域业务数据与业务规则。治理中心不得复制一套可写领域业务数据，也不得建立中央业务规则执行引擎。

存量 Capability 在 V2.5 切换基线中按精确历史定义哈希登记。定义未变化且不存在确定性 blocker 时，可保持可测试状态，但必须显示为 `legacy_pending_review` 并进入人工审核队列；新 Capability 或发生实质变化的 Capability 在当前精确哈希批准前必须阻断 stable 发布。存量状态不能豁免确定性 blocker。

---

## 二、原子业务 Capability 的定义

原子业务 Capability 是一个领域对外提供的、可独立授权、可独立测试、可独立审计、具有稳定输入输出和明确业务效果的最小业务能力单元。原子不等于代码行数最少，而是业务责任不可再合理拆分。

一个 Capability **MUST** 只表达一个主要业务效果，例如"获取某个 BOP 版本""发布某个模型快照""查询仿真运行"，不得把查询、校验、写入、审批和发布混成一个无边界动作。

如果两个动作可以分别授权、分别失败、分别重试、分别被不同消费者使用，通常就必须拆成两个 Capability；如果拆分会破坏业务不变量，必须在契约中明确说明不可拆分的原因。

### A.2 原子性判定清单

- 能力名称可以用一个动词短语描述，并且能用一句话写出唯一业务效果；若必须使用"并且/同时/以及"连接多个动词，应重新拆分评估。
- 能力拥有单一领域 owner、单一数据边界、单一授权意图和单一审计事件；不能由多个领域共同"拥有"一个 Capability。
- 能力的成功结果、业务拒绝、权限拒绝、输入错误、依赖失败和重试语义必须可区分；不能只返回一个布尔值或吞掉下游错误。

---

## 三、身份、GID、版本与登记字段

每个 Capability 使用稳定的 `capability_id` 表示逻辑身份，使用雪花算法生成的 `capability_version_gid` 表示某个具体版本。逻辑 ID 一旦对外发布不得改名复用；GID 一旦分配不得回收后重新指向其他能力。

登记记录 **MUST** 包含：`capability_id`、`capability_version_gid`、`domain`、`owner`、`business_effect`、`business_invariants`、`input_schema`、`output_schema`、`error_schema`、`side_effect_level`、`side_effects`、`authorization_policy`、`transaction_policy`、`idempotency_policy`、`lifecycle_status`、`consumer_refs`、`provider_ref`、`api_refs`、`test_refs` 和 `catalog_release`。确实不承载业务不变量的能力可以登记空数组，但必须同时填写由领域 Owner 确认的 `no_business_invariant_reason`。

> **命名说明：** `side_effect_level` 是机器可判定的枚举值（`none` / `read` / `write` / `high_risk_write`），对应代码中的 `SideEffectLevel` 枚举，用于自动分类和门禁判断；`side_effects` 是人类可读的叙述性描述，说明该能力实际写入哪些表、发出哪些事件、产生哪些外部调用。两者分别填写，不能互相替代。
>
> **`business_effect`** 是独立的业务登记字段，必须是一句话、可由业务人员验收的主要业务效果；不得把 `CapabilityDescriptorV2.description` 或 `title` 直接当作合规登记值。迁移期间可以将 `description` 作为候选初值，但必须由领域 owner 确认后写入正式投影。

`business_effect` 回答的是“这个能力成功后，业务世界发生了什么有价值且可验收的变化”，不是“代码执行了哪个函数”，也不是“它受哪些限制”。合规表述必须包含明确的业务对象和成功结果；查询能力说明交付了什么可用信息，写能力说明对象从什么业务状态变成什么状态或新增了什么可信记录。

以下内容 **MUST NOT** 作为 `stable` 的正式业务效果：Capability ID 的同义复述、`Execute the governed ... outcome`、`Business outcome: + description` 等机械生成文本、技术实现步骤、权限描述或错误处理说明。生成器可以产生候选文本，但候选值必须标记为 `unverified`，经领域 Owner 确认前不得满足 Release Gate。

例如 `person.height.write@1` 的业务效果可以是“为人员档案形成一条单位统一、来源可追溯的身高测量记录，供后续人员配置使用”；“调用身高写入 Provider”不是业务效果，“身高不得超过 2.5m”则是保护该效果的业务不变量，而不是能力存在的目的。

登记记录 **SHOULD** 同时包含数据表/对象范围、敏感数据等级、超时与重试建议、幂等键规则、审计事件名、依赖 Capability、弃用时间和迁移说明。

### V2 新增：登记字段的层级与结构约束

以上字段的登记 **MUST** 同时出现在：① 官方 Registry snapshot entry；② 已发布的 Catalog descriptor 的可查询投影层；③ 治理数据库的持久化记录。仅存在于代码注释或"计划登记"中的字段不满足本节要求。新发布和 `stable` descriptor 必须完整满足；`deprecated`/`retired` 历史 descriptor 可以保持不可变旧投影，但不得作为新版本发布证据。

以下字段的结构约束（**MUST** 以 JSON Schema 或对应 dataclass 表达）：

- **`capability_version_gid`：** int64 雪花 GID，**MUST** 同时出现在 Registry snapshot entry、Catalog descriptor 和每条测试证据记录中，不能仅由治理扩展内存计算或仅存在于内部 Store。

- **`error_schema`：** 数组，每项 **MUST** 包含 `error_code`（machine-stable 字符串）、`is_retryable`（bool）、`is_caller_error`（bool）；**SHOULD** 包含 `message_template`（不含 PII）、`recovery_hint`。空数组仅在所有错误均为 Gateway 标准错误时被接受。

  > **与现有实现的映射：** `error_schema` 对应代码中 `CapabilityDescriptorV2.domain_errors`（`tuple[DomainErrorContract, ...]`），但不是字段名的机械复制：`DomainErrorContract.code → error_code`、`retryable → is_retryable`、`meaning → message_template`；`is_caller_error` 必须在登记/投影适配层显式补齐，不能默认省略。Gateway 层统一处理的标准错误（如权限拒绝、资源不存在、版本不兼容）**不**计入 Provider 的 `error_schema`，由 Gateway 在响应中单独携带。`is_caller_error=true` 仅表示调用方修正输入、权限或资源选择后可自行解决，不能由 `retryable` 字段推断。

- **`transaction_policy`：** 对象，**MUST** 包含 `requires_transaction`（bool）；`side_effect_level` 为 `write` 或 `high_risk_write` 时，**MUST** 还包含 `participants`（table_owners 或 capability_ids 列表）和 `compensation_strategy`（`rollback` / `saga` / `none-with-justification`）。

- **`consumer_refs`：** 数组，每项 **MUST** 包含 `consumer_id`、`consumer_type`（`web` / `plugin` / `agent` / `api` / `mcp` / `worker` / `local_runtime`）、`version_constraint`（如 `">=1 <3"`）；发布时 **MUST** 有至少一个已验证消费者，或提供 `no_consumer_reason` 说明。

- **`provider_ref`：** 对象，**MUST** 包含 `module`（Python 模块路径）和 `artifact_hash`（与 `official_domains.json` 中值一致）；不能只填模块名而不包含 hash。

- **`api_refs`：** 数组，每项 **MUST** 包含 `path`（router 路径）、`method`（HTTP 方法）、`router_module`；`exposure.rest = true` 时此字段不得为空；遗留 REST 和 BFF 路由均须登记。

- **`test_refs`：** 数组，每项 **MUST** 包含 `test_type`（`contract` / `provider` / `e2e` / `acceptance`）、`test_node_id`（`path::function` 格式）、`code_revision`、`result`（`pass` / `fail` / `not_run`）；`result = not_run` 时不得作为发布证据。

- **`business_invariants`：** 数组，每项 **MUST** 包含：
  - `rule_id`：在同一 major 内稳定且唯一的规则 ID；
  - `statement`：业务人员能够理解和验收的一句话规则；
  - `enforcement_ref`：实际执行该规则的 Schema、Provider 函数、领域策略或数据库防线位置；
  - `error_code`：规则不成立时返回的稳定业务错误码；
  - `test_refs`：至少包含一个通过值和一个拒绝值的可运行测试引用；存在边界值时还必须覆盖边界。

  `type`、`required`、`additionalProperties=false` 等结构正确性不能自动算作业务不变量；只有能够回答“这个值或操作在该业务场景下为什么允许或拒绝”的约束才算业务规则。权限、Confirmation、幂等和 Provider Hash 属于技术治理规则，也不能替代业务不变量。

### V2.4 新增：业务规则的声明与执行

Capability 必须同时通过两条治理线：

在进入两条治理线之前，必须先确定并登记 Capability 的唯一业务目的。约束服务于目的：没有可验收 `business_effect` 的“能力”只是一个受控技术入口；只有目的而没有业务不变量的能力，则可能稳定地产生错误业务结果。

1. **技术治理线：** 身份、版本、消费者资格、权限、Confirmation、幂等、事务、Provider 制品和审计证据正确。
2. **业务治理线：** 字段含义、单位、合理范围、跨字段关系、对象当前状态和领域政策允许产生该业务结果。

两条线缺一不可。技术调用完全合规，但业务值不合理时，Provider 仍必须返回登记的业务错误；业务值合理，但身份、权限或版本不合规时，Gateway 仍必须拒绝调用。

以 `person.height.write@1` 为例，`height` 为数字和 `unit` 为字符串只是结构契约；“统一换算为米后必须满足 `0 < height <= 2.5`”才是业务不变量。`3.2m` 必须稳定返回 `HEIGHT_OUT_OF_RANGE`，不得写入数据库，也不得仅依赖前端提示。

业务规则按最小充分位置执行：

- 单字段、静态、与状态无关的规则 **SHOULD** 写入 closed `input_schema`，例如枚举和固定数值范围；
- 跨字段、依赖当前对象状态、租户政策或其他领域事实的规则 **MUST** 在所属领域 Provider 或正式领域策略中执行；
- 数据库约束可以作为最后一道一致性防线，但 **MUST NOT** 成为唯一业务规则实现；
- Web、Task Tool、Agent Skill 和 API 适配器 **MUST NOT** 各自复制一份领域业务规则。

`stable` Capability 的 `business_invariants` 必须非空，或者具有非空的 `no_business_invariant_reason`。后者不是自动豁免：必须由领域 Owner 确认，并由 Release Gate 检查。通用说明“该能力没有业务规则”不构成有效理由。

---

## 四、新增 Capability 的标准流程

1. **提出：** 先在治理中心或变更提案中登记业务效果、领域 owner、数据范围、预计消费者、是否跨域以及为什么现有 Capability 不能复用。
2. **设计：** 补齐输入/输出/错误/权限/事务/幂等/审计契约和 `business_invariants`，明确成功、业务拒绝和技术失败边界；跨域能力必须先由被调用域 owner 评审契约。
3. **登记：** 分配新的 `capability_id` 和版本 GID，写入 Catalog/Descriptor、Provider 计划、API 绑定、消费者计划和验收用例；未登记不得开始对外实现。
4. **实现：** Provider 只能访问本领域授权的数据源；API 只能通过正式 Gateway 调用 Capability；实现、Descriptor、OpenAPI 片段和文档必须在同一变更中完成。
5. **验证：** 先跑契约测试、Provider 测试、权限矩阵、事务/幂等测试和跨域边界扫描，再跑前端、插件和端到端联调；测试证据必须绑定代码修订和 Capability 版本 GID。
6. **评审与发布：** 领域 owner 审核业务语义，平台 owner 审核 Gateway/权限/审计，测试负责人审核证据；三者缺一不可。

任何新增能力在正式发布前必须能回答：谁消费、谁负责、读写什么、失败如何处理、如何回滚、如何证明它真的被测试过。

---

## 五、实现约束：数据、事务、权限与副作用

Provider **MUST** 通过领域仓储或正式数据端口访问数据；**MUST NOT** 直接读取其他领域的表、内部 ORM、数据库连接或未登记的缓存。

强写 Capability **MUST** 声明事务要求、参与者和失败补偿；没有事务提供者时必须拒绝执行，不能降级成"看起来成功"的部分写入。

每个写能力 **MUST** 支持幂等键或明确声明不可幂等的原因；重复请求、超时重试和客户端重复点击不得产生不可控的重复副作用。

权限判断 **MUST** 在 Gateway/Provider 边界执行，不能只依赖前端隐藏按钮；能力必须声明读取、写入、管理员、团队或资源级授权要求。

输入中的用户、团队、项目、资源和租户标识 **MUST** 经过服务端身份上下文校验；**MUST NOT** 信任前端传入的 owner、actor、权限或审计字段。

Provider **MUST** 执行本 Capability 登记的全部 `business_invariants`，并使用登记的稳定业务错误码拒绝不合法业务请求。通用 `invalid_input` 只能表示无法解析或不满足基础输入契约，不能吞掉本应明确表达的领域拒绝原因。

每次调用 **MUST** 产生可追踪审计事件，至少记录调用者、Capability 版本 GID、请求 GID、结果、错误码、目标资源和代码/快照版本；敏感数据不得写入日志。

Capability **MUST** 明确是否允许插件、Agent、页面或其他 Capability 消费；未登记的消费者调用应被拒绝并形成治理 Finding。

---

## 六、Capability、API、插件与 Agent 的关系

Capability 是稳定业务能力；API 是对外入口或编排适配器。一个 API 可以调用多个 Capability，一个 Capability 也可以被多个 API、页面、插件和 Agent 消费。

API 可以编排多个原子能力，但编排逻辑必须显式记录：调用顺序、条件、失败处理、补偿、事务边界和使用的 Capability 版本；不得把编排细节偷偷塞进某个原子 Provider。

插件和 Agent **MUST** 通过 SDK Mount/Gateway 调用已声明的 Capability；**MUST NOT** 直连 REST、数据库、Cookie、Electron IPC 或其他领域内部模块。

---

## 七、变更、兼容性与版本规则

补充可选输出字段、增加不影响旧调用的只读过滤条件、修复不改变契约语义的实现缺陷，通常属于兼容变更，可升级 minor 或 patch；必须保留旧字段和旧错误语义。

删除/重命名字段、改变字段含义、改变权限、改变副作用、改变事务边界、改变错误码、改变结果排序保证、改变幂等语义，或收紧业务不变量使原来合法的请求变为拒绝，均属于破坏性变更，**MUST** 新建 major 版本。

放宽业务不变量也必须由领域 Owner 评审其业务语义和消费者影响；如果会改变 Capability 的业务效果、风险边界或下游假设，同样 **MUST** 新建 major 版本。仅修复 Provider 使其重新符合当前版本已登记的不变量，可以作为兼容缺陷修复，但必须补充回归证据。

已发布版本的 Descriptor、Provider 和文档不得原地改写。变更必须创建新版本 GID，并同时更新消费者兼容矩阵、迁移说明、测试证据和弃用时间。

新增 major 版本时，旧版本必须进入 `active → deprecated → retired` 的可追踪生命周期；deprecated 版本必须保留迁移指南和最后支持日期。

只有在所有已登记消费者完成迁移、旧 Mount/路由已失效、审计确认无调用后，才能 `retired`；删除代码前必须保留不可变的历史 Descriptor 和变更记录。

Provider 修复实现缺陷但不改变契约时，不得偷偷改变返回结构或业务语义；若确实需要改变，必须按破坏性变更流程发布新 major。

### A.3 变更分类示例

- **兼容：** 新增可选 query 参数、增加可选输出字段、修复慢查询但保持结果和错误语义不变，可发布 minor/patch。
- **破坏：** 把"草稿查询"改成"自动发布"、把项目标识从可选改成必填、把权限从成员改成管理员、把成功状态改成排队状态，必须发布新 major。
- **禁止：** 在同一个版本里既修改字段语义又声称是 patch；禁止为了让旧测试通过而伪造旧响应或吞掉真实错误。

---

## 八、跨域、数据库和表所有权规则

每张业务表、迁移文件和领域对象 **MUST** 有唯一 owner；领域代码只能读写自有表，跨域数据必须通过公开 Capability 获取。

**MUST NOT** 通过跨域 SQL、共享 ORM Model、内部 Python import、临时 REST 或复制数据库连接绕过 Capability 边界；发现此类调用必须生成 blocking Finding。

跨域 Capability 必须声明调用方、被调用方、数据最小范围、超时、重试、事务和降级策略；调用双方都要登记消费者关系和版本兼容范围。

同一数据库不等于同一所有权。生产环境可以只有一个数据库账号，但应用仍必须遵守表 owner、Gateway 权限、审计和事务边界。

---

## 九、测试、治理扫描与发布门禁

- **契约测试：** 验证输入、输出、错误码、版本、字段约束和幂等语义；必须覆盖合法、非法、空值、边界和重复请求。
- **Provider 测试：** 验证真实数据访问、事务参与者、权限拒绝、资源不存在、下游超时和异常映射；不得只用"返回固定成功值"的假 Provider。
- **边界测试：** 扫描 API/Provider/Descriptor/表/迁移/页面/插件/Agent 的一一对应关系，禁止 `provider_missing`、`provider_without_descriptor`、`exposure_without_capability`、`required_test_missing` 和 `repository_table_mismatch` 阻塞项。

治理扫描必须使用实际运行的官方 Capability Registry 快照，而不是只读取 Catalog 文件；Provider 绑定、代码修订和扫描快照 hash 必须一致。

测试证据 **MUST** 绑定 `capability_version_gid`、`snapshot_gid`、`code_revision`、测试运行 GID 和结果 hash；缺少来源或完整性校验的"通过"不得作为发布证据。

发布闸门 **MUST** 重新从权威存储读取候选版本、测试、Finding、审批和签名证据，不能接受调用方直接传入的 `available=true`、`findings=[]` 等自报状态。

普通成员可以查看目录和健康结果，但不能执行发布、批准、豁免、启停或修改治理记录；这些动作必须经过 Gateway 确认令牌、幂等键和审计。

---

## 十、编码 Agent 的强制工作协议

- 开始修改前 **MUST** 读取 Capability Catalog、Descriptor、Provider、domain ownership、消费者关系、相关 migration 和现有测试；不得只根据用户一句话直接写代码。
- Agent **MUST** 先输出变更分类：新增、兼容变更、破坏性变更、实现修复或废弃；若无法判断，必须暂停并请求领域 owner 确认。
- Agent **MUST** 先检查是否已有可复用 Capability；发现重复、跨域冲突、owner 缺失、Provider 缺失或消费者不明时，先生成治理 Finding，不得绕过登记继续实现。
- Agent 修改时 **MUST** 只触碰声明的领域路径和共享平台获批路径；跨域变更必须列出双方 owner、接口契约和影响范围。
- Agent **MUST** 在提交说明中给出 `capability_id`、版本/GID、修改类型、Provider、API、消费者、表/迁移、测试命令和未解决风险。
- Agent **MUST** 运行真实测试并报告原始结果；不得把未执行、跳过、离线模拟或旧快照结果写成"通过"。
- Agent **MUST NOT** 伪造 Provider 绑定、测试证据、审批、Finding 清零、生产检查或权限结果；无法验证时必须报告 `unverified/blocked`。

---

## 十一、新增或变更提案模板

- **Capability：** `capability_id` / 版本 GID / domain / owner / `lifecycle_status`
- **业务效果：** 只写一个业务效果；输入、输出、错误码、权限、事务、幂等、副作用、审计和数据范围
- **关系：** Provider、API、页面、插件、Agent、工作流消费者、依赖 Capability、表/迁移、兼容版本和弃用计划

---

## 十二、提交前强制检查清单

- □ **原子性：** 是否只有一个业务效果？是否可以独立授权、失败、重试、审计和测试？
- □ **身份：** 是否有新的 Capability ID/版本 GID？是否更新 Catalog、Descriptor、Provider、API、消费者和文档？
- □ **安全与数据：** 是否只访问 owner 负责的数据？是否声明权限、事务、幂等、副作用和敏感数据？
- □ **关系：** Provider、API、页面、插件、Agent 和工作流消费者是否都有真实绑定？是否存在重复、冲突、未绑定或未声明入口？
- □ **验证：** 契约、Provider、权限、事务、幂等、跨域边界、迁移、前端构建和端到端测试是否全部通过，并绑定当前代码修订、快照 GID 和测试 GID？
- □ **发布：** 是否完成领域 owner、平台 owner 和测试负责人评审？是否仍有 blocking/critical Finding、unverified 证据或外部前置条件？有则不得发布。

---

## 十三、禁止事项与最终原则

禁止为了快速交付把多个业务动作合并成"万能 Capability"；禁止为了减少 Finding 删除登记、测试或消费者关系。

禁止把领域之间的偶然复用升级为共享底层实现；应先判断是否形成稳定业务能力，再通过正式 Capability/Gateway 共享。

禁止把旧版本改成"看起来兼容"；所有契约变化都必须可追踪、可审计、可回滚、可通知消费者。

**最终原则：** Capability 是可治理的业务边界，不是隐藏实现的包装。任何能力都必须有明确 owner、唯一业务效果、稳定契约、真实 Provider、受控消费者、可验证证据和可追溯生命周期。

---

## 十四、能力治理中心提供的正式 Capability

治理中心自身也是一个 Capability 消费者和提供者。以下能力属于 `test-governance` 扩展，必须通过统一 Gateway/SDK 使用；它们读取或产生的是带 GID、快照 hash、代码修订和审计证据的治理数据，不直接暴露内部 Store。

### A.4 查询类（READ）

- `base.capability_registry.search`：按关键词、领域、分页查询 Capability 清单
- `base.capability_registry.get`：按 `capability_version_gid` 获取单个能力的完整登记投影
- `base.capability_governance.snapshot.summary.get`：读取已验证快照的汇总，返回能力总数、Finding 总数、阻塞数、按领域统计和按根因聚合；支持领域、严重级别、关键词和分页
- `base.capability_graph.get`：从 Capability 或治理对象出发，读取有界的节点/关系/Provider/API/消费者图；必须传 `target_gid`、`max_depth`、`max_nodes`
- `base.capability_finding.search`：按领域、严重级别、状态、原因类别和关键词分页查询 Finding
- `base.capability_analysis.get`：读取已有分析运行结果，不主动启动分析
- `base.capability_proposal.search`：查询提案及其阶段、版本和快照关系
- `base.capability_health.get`：按领域读取基于固定快照的健康状态；未返回快照或依赖不可用时必须显示 `unverified/不可用`
- `base.capability_audit.search`：查询脱敏审计记录；只读，不允许前端修改或删除

### A.5 分析与修复辅助类（ANALYZE）

- `base.capability_analysis.run`：针对 `snapshot_gid` 启动有界分析
- `base.capability_repair_prompt.generate`：根据 Finding、证据和变更边界生成脱敏修复 Prompt；只提供建议，不自动修改领域代码

### A.6 治理写操作（GOVERN）

- `base.capability_scan.run`：以 `code_revision` 绑定当前代码，执行扫描并持久化新的治理快照
- `base.capability_test.run`：对指定快照启动治理测试
- `base.capability_proposal.submit`：提交新增/变更提案
- `base.capability_review.decide`：对提案进行评审决定
- `base.capability_waiver.grant` / `base.capability_waiver.revoke`：管理临时豁免（须提供充分理由、范围、代码 hash、证据 hash 和到期时间）

### A.7 发布类（RELEASE）

- `base.capability_release_gate.evaluate`：基于 code revision、Catalog release、snapshot、test run、Finding、豁免、审批和签名证据评估发布结论；调用方不得自报"全部通过"

---

## 十五、能力治理中心的使用规范

治理中心用于测试环境的能力资产治理和发布前验证，不是业务数据编辑器，也不是绕过领域 owner 的自动修复工具。所有结论都必须绑定一个明确快照；没有快照、快照过期或数据源不可用时，界面必须显示 `unverified/不可用`。

治理中心使用者分为三类：普通开发者可查询和分析；领域 owner 可提交提案、查看本域 Finding 并参与评审；管理员/平台 owner 才能执行扫描、测试、豁免、发布闸门和治理配置。

### A.8 标准使用顺序

1. **先读：** 调用 `registry.search` / `registry.get` 确认能力身份、owner、版本、生命周期、Provider、API 和消费者
2. **再看快照：** 调用 `snapshot.summary.get` 或 `health.get`，确认 `snapshot_gid`、`snapshot_hash`、Catalog release 和数据新鲜度；不要把目录条目数量当成健康结论
3. **再定位：** 用 `finding.search` 分页查看问题，用 `graph.get` 查看具体 Capability 与 Provider/API/消费者/证据的关系；每次使用 `limit`/`offset` 或 `max_nodes` 上限
4. **要修复时：** 先读取 Finding 根因和 graph 证据，再用 `repair_prompt.generate` 生成给领域 Agent 的脱敏 Prompt；Prompt 只描述边界和证据，不授予自动写代码权限
5. **修复后：** 先提交提案，完成双 owner 评审，再由管理员执行重新扫描和测试
6. **发布前：** 执行 `release_gate.evaluate`；只有服务端重新读取完整证据并返回 `signed/passed`，才允许进入发布流程

---

## 十六、治理中心的安全与数据使用规则

所有调用必须携带当前登录身份；不得在 URL、Prompt、日志、截图或聊天消息中输出 Token、Cookie、数据库凭据或未脱敏业务数据。

查询必须分页和限界：列表默认使用 `limit/offset`，图查询使用 `max_depth/max_nodes`，禁止一次性拉取无界全量数据或在 Agent 上下文中复制整库结果。

写操作必须使用唯一幂等键；系统返回 `expected_resource_version`、确认令牌、权限拒绝、快照过期或依赖不可用时，必须停止并按错误语义处理，不能盲目重试写入。

低风险的环境写入可以声明 `confirmation_policy=none`，但必须同时满足：只影响当前主体的派生或可重建状态、`automation_level=A1`、要求幂等键、声明窄资源选择器、没有跨主体或外部副作用，并在验收门禁的显式 allowlist 中逐项登记。最近访问记录属于此类；业务实体变更、审批、发布、删除和跨主体写入不得使用该例外。

页面显示"正在显示上次成功数据"时，只能作为诊断提示，不能当作当前代码已经通过；使用者必须检查 `last_success`、`snapshot_gid`、`snapshot_hash`、`code_revision` 和 `error code`。

治理中心的任何结论都必须能追溯到真实快照和证据；不能通过手工修改页面、删除 Finding 或降低严重级别来"解决"问题。

---

## 十七、给 Agent 的最小调用协议

- **只查一个能力：** `registry.search` → `registry.get` → `graph.get`
- **只查全局治理：** `snapshot.summary.get` → `finding.search` 分页 → `health.get`
- **只生成修复建议：** `finding.search` → `graph.get` → `repair_prompt.generate`
- **任何写操作：** 先读取当前 snapshot 和 `row_version` → 生成唯一 `idempotency_key` → 请求确认令牌 → invoke → 读取审计结果；遇到冲突必须重新读取后再决定是否重试
- **任何发布判断：** 先确认 `code_revision`、Catalog release、`snapshot_gid`、`test_run_gid`、Finding、豁免和审批均来自服务端权威数据，再调用 `release_gate.evaluate`

---

## 十八、Task Tool、Capability Pack、Skill 与 Workflow 骨架的治理（V2 新增）

> **上位依据：** 《总装业务智能化四层治理指南》第 2.3 节"可组合编排原语"和第 8.2 节"Capability 评审"。

编排原语（Task Tool、Capability Pack、Skill、Workflow 骨架）是 Capability 和消费者之间的稳定中间层，必须和 Capability 本身一样受版本治理和发布门禁约束。

### 18.1 Task Tool 治理要求

Task Tool 完成一个小而有意义的任务，在内部稳定组合少量 Capability，并向 UI、插件和 Agent 屏蔽它们的版本和调用细节。

- **登记 MUST 包含：** `tool_id`（全局唯一，建议格式 `{domain}.{context}.{verb}`）、`major_version`、`owner_domain`、`owner_team`、`description`、`use_when`、`input_schema`（closed）、`output_schema`（closed）、`consumed_capabilities`（每项含 Capability ID + major 版本约束）、`lifecycle_status`。
- **版本规则：** 与 Capability 相同；任何影响 `input_schema`、`consumed_capabilities` 或 `output_schema` 的变更 **MUST** 新建 major 版本。
- **权限边界：** Task Tool 的权限声明 **MUST** 等于其 `consumed_capabilities` 中每项 Capability 所需权限的并集（最大需求边界）；Task Tool **MUST NOT** 声明超出 `consumed_capabilities` 实际需要之外的额外权限。单次调用时，Gateway 按调用方已授权范围对此进一步约束，调用方实际获得的权限是"Task Tool 声明范围"与"调用方已授权范围"的交集。
- **发布前 MUST：** `consumed_capabilities` 全部处于 stable 状态；至少一个真实消费者测试案例绑定至 `test_refs`；Gateway 路由和 SDK 适配完成。
- **MUST NOT** 在 Task Tool 内复制 Capability 的业务规则；Task Tool 只负责调用和参数传递，不实现领域逻辑。

### 18.2 Capability Pack 治理要求

Capability Pack 针对某类业务上下文整理的候选能力包，用于发现、授权和工具投影；它不是固定执行流程。

- **登记 MUST 包含：** `pack_id`、`version`、`target_context`（业务节点或场景描述）、`curated_capabilities`（引用 Capability ID + major 版本）、`granted_permissions`（明确哪些权限随 Pack 开放）、`lifecycle_status`。
- Pack **MUST NOT** 承载执行逻辑；不得把 Pack 当作执行入口或绕过 Gateway 的快捷方式。
- Pack 引用的每个 Capability 在 Pack 版本固化时 **MUST** 是 `stable` 状态；Pack 变更须更新 `curated_capabilities` 版本引用并重新测试。
- **消费者使用 Pack 时：** Gateway **MUST** 仍然验证调用者对每项 Capability 的实际权限；Pack 只是发现层，不是授权凭证。

### 18.3 Skill 治理要求

Skill 说明何时选择哪些 Task Tool、如何准备上下文、如何解释结果和何时转人工；它不增加权限，也不承载核心业务规则。

- **登记 MUST 包含：** `skill_id`、`version`、`owner_team`、`use_when`（明确触发条件）、`referenced_tools`（Task Tool ID + major 版本）、`output_hints`（结果解释建议）、`lifecycle_status`。
- Skill **MUST NOT** 直接调用 Capability；**MUST NOT** 包含事务、权限判断或产生副作用的逻辑；所有执行仍通过 Task Tool 和 Gateway 完成。
- **版本变更：** 新增 `referenced_tools` SHOULD 升 minor；移除 `referenced_tools` 或改变 `use_when` 语义 **MUST** 升 major 或提交变更提案并获批。

### 18.4 Workflow 骨架治理要求

Workflow 骨架只固化法规、审批、安全、事务或强顺序要求等不可变部分；可变化的分支、参数、工具选择和人工决策保留为插槽。

- **登记 MUST 包含：** `workflow_id`、`version`、`owner_team`、`entry_schema`（输入契约）、`exit_schema`（输出契约）、`mandatory_steps`（不可跳过的步骤，含每步的 Capability 或 Task Tool 约束）、`pluggable_slots`（可替换插槽及其约束类型）、`lifecycle_status`。
- `mandatory_steps` 中涉及审批、权限、安全或事务的步骤 **MUST NOT** 被覆盖、绕过或省略。
- `pluggable_slots` 只能在声明类型内替换，不能替换为非声明类型；消费者 **MUST** 为每个 `pluggable_slot` 的实现提供 Capability 或 Task Tool 绑定证据。
- Workflow 骨架变更 **MUST** 通知所有已登记消费者，并允许其在宽限期内迁移。

### 18.5 编排原语的通用约束

- 所有编排原语 **MUST** 通过 Gateway/SDK 调用 Capability；**MUST NOT** 绕过 Capability 边界直接访问领域内部。
- Release Gate **MUST** 检查 Task Tool 的 `consumed_capabilities` 全部为 stable，且版本约束与已发布 Catalog release 一致。
- **MUST NOT** 在同一个 Task Tool 中同时承载"UI 视图逻辑"和"业务规则"；UI 逻辑属于页面层，不得混入 Task Tool。
- Task Tool **允许**在调用 Capability 前后对 input/output 做 schema 适配（字段名映射、格式转换、单位转换等）；但 **MUST NOT** 在适配过程中引入业务判断逻辑或改变数据语义。Schema 适配规则须在 Task Tool 文档中明确记录，并在 `test_refs` 中包含对应的适配正确性测试案例。

---

## 十九、业务全景节点台账与度量（V2 新增）

> **上位依据：** 《总装业务智能化四层治理指南》第 1 节"部门全业务全景"、第 6 节"从总装业务大图到智能化拼图"和第 7 节"一块智能化拼图的完成标准"。

### 19.1 全景节点台账字段要求

每个在全景业务图中的业务节点 **MUST** 在治理台账（文件或治理数据库）中维护以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_id` | string | 全局唯一节点标识 |
| `business_objective` | string | 一句话业务目标，必须可被业务人员理解 |
| `owner` | string | 实名负责人 |
| `inputs` | string[] | 输入来源及格式 |
| `outputs` | string[] | 输出目标用途及格式 |
| `preconditions` | string | 前置条件 |
| `covered_by_system` | string | 当前覆盖方式（UI 页面、服务路径或"无"） |
| `covered_by_capabilities` | string[] | 对应 Capability ID 列表 |
| `status` | enum | `green` / `yellow` / `red`，**MUST** 基于代码和运行证据，不能只根据计划或估算 |
| `quality_metrics` | string | 可量化的质量指标（如检查通过率、返工率） |
| `efficiency_metrics` | string | 效率/周期/返工指标 |
| `development_tasks` | string | 未完成事项 |
| `acceptance_criteria` | string | 可验收的完成条件 |

### 19.2 节点状态定义（MUST 遵守）

- **绿色（green）：** 有稳定系统支持 + 接口和责任边界清楚 + 对应 Capability 为 `stable` + 至少一个真实消费者已迁移 + 生产可观测（调用量/成功率/失败分布/P95 延迟可查）。
- **黄色（yellow）：** 有 UI 或代码，但业务规则、接口、权限或数据边界需要收敛；或对应 Capability 为 `experimental`/`deprecated`；或消费者迁移未完成。
- **红色（red）：** 依赖人工操作、Excel、临时脚本或直接 SQL；或缺少完整闭环；或所有 Capability 均为 `experimental`；或完全没有对应 Capability。

状态 **MUST** 随着代码、测试和真实消费者迁移结果同步更新，不得长期停留在计划状态。

### 19.3 节点完成的八个必要条件

一个业务节点只有同时满足以下八个条件，才允许标为 `green`（完成）：

1. 在全景业务图中有明确位置、上下游和责任人。
2. 输入输出、数据来源和业务规则明确，可被业务人员验收。
3. 稳定业务动作已经形成受治理 `stable` Capability（或有书面批准的例外，且附有例外原因和截止日期）。
4. 至少有一个真实 UI 或插件消费者完成迁移，并已在测试环境通过业务验收。
5. 权限、确认、审计、证据、错误和版本策略完整，且已通过治理扫描无 blocking Finding。
6. 测试环境完成契约、权限、异常和业务验收，测试证据绑定至当前代码修订。
7. 生产环境可以观察调用、失败、性能和业务结果；可观测性必须在发布后第一个迭代内补齐。
8. 有质量、效率、周期或返工方面的可量化指标，并已测量基线值（非估算）。

未满足第 7 条的节点 **MUST NOT** 标为 `green`，即使其他条件全部满足。

### 19.4 生产可观测性要求

- 每个 `green` 节点 **MUST** 有生产可观测的运行指标，至少包含：调用量/成功率/失败分布/P95 延迟。
- 质量指标 **MUST** 可被业务人员理解（如返工率、检查通过率），不只是技术监控指标。
- 业务结果观测 **MUST** 在发布后的第一个迭代内补齐；若无法在生产中观测业务结果，节点状态 **MUST NOT** 标为 `green`，应标为 `yellow` 并记录为待完成事项。

---

## 二十、遗留 UI/API 迁移策略与 BFF 边界（V2 新增）

> **上位依据：** 《总装业务智能化四层治理指南》第 5.1 节"传统 UI"和《总装柔性智能基座协作开发规范 V1.0》第五节"Capability 与跨域协作规则"。

### 20.1 遗留路由的合规条件

遗留 REST/UI 路由要保持合规，**MUST** 同时满足以下条件：

1. 该路由已在 `legacy_route_inventory`（路径：`docs/governance/legacy_route_inventory.json` 或等价治理台账）中登记，每条记录至少包含：`route_path`、`owner`、`allowed_consumers`（允许消费者列表）、`migration_target_capability`（目标 Capability ID）、`migration_deadline`（绝对日期，如 `2026-11-21`）、`exception_approval_reference`（豁免审批记录，如适用）。
2. 对应的业务能力已经登记为 `stable` Capability；仅前端/消费者尚未完成迁移，不属于 Capability 缺失。
3. 迁移截止日期 **MUST** 是绝对日期，且不晚于该路由**首次进入 `legacy_route_inventory` 时所对应发布版本的发布日期**后 90 天（默认上限）；**MUST NOT** 以每次 CI 扫描的机器当前日期动态推算截止日期。截止日期一经登记不得自动延长；如需延长，须重新提交豁免申请并获得 domain owner + platform owner 的书面批准记录。超出 90 天的原始截止日期同样需要此豁免。

### 20.2 新代码禁止增加遗留路由

- 任何新 UI 页面、插件、Agent 工具 **MUST** 从第一个功能起调用 Task Tool 或 Capability Gateway，**MUST NOT** 使用绕过 Gateway 的遗留 REST 路由，不允许"先旧接口开发再计划迁移"。

  > **说明：** 此处禁止的是"直接调用、绕过 Capability Gateway 的 REST 入口"。通过 Gateway 内部的 REST 适配器（如 `CapabilityDescriptorV2.exposure.rest = true` 暴露的正式 REST 端点）访问 Capability，不在禁止范围内。

- 向静态扫描器（如 `consumer_routes.py`）识别为 `legacy` 的路径添加新的调用字面量，视为违反此规定，Release Gate **MUST** 将其计为 blocking。

### 20.3 BFF 路由的允许范围

BFF（Backend-for-Frontend）路由是指单页面聚合查询或视图格式化，允许存在的条件（**MUST** 同时满足）：

- 只服务单一页面，不共享给插件、Agent 或其他页面。
- 不包含跨域业务规则或副作用；只允许调用本领域 Capability 聚合。
- 已在 `bff_route_inventory.json`（或等价台账）中登记，每条记录包含 `route_path`、`page_id`、`owner`。
- 路由数量不超过该领域在 `legacy_route_inventory` 中登记的唯一 `(route_path, method)` 对数量的 20%。**分母以台账登记数量为准，不以静态扫描的路由字面量出现次数为准**（扫描计数因多处引用同一路由而偏高，不能作为比例计算基准）；超出须 platform owner 批准并记录在案。
- BFF 路由 **MUST NOT** 持续承载跨领域 SQL、事务或写操作。

### 20.4 遗留路由退役验证标准

遗留路由进入 `retired` 状态前 **MUST** 满足以下全部条件：

1. 所有已登记消费者已切换到 Capability Gateway；治理扫描中该路由的 `legacy` 计数为 0。
2. 路由返回 HTTP 410（Gone）；连续 7 天生产流量日志确认零有效调用（非 410 响应）。
3. 对应 Capability 版本为 `stable` 并已在测试环境完成验证。
4. 审计日志中已无该路由的非-410 调用记录。

### 20.5 Release Gate 追加条件（V2.1 继承并强化，与第九节合并执行）

在 V1 发布门禁基础上，**MUST** 追加以下检查项（任一不满足即 blocking）：

- `legacy_route_inventory` 中存在 `migration_deadline` 早于当前日期且未标为 `retired` 的路由 → **blocking**。
- BFF 路由占比超过上限（20%）且无 platform owner 批准记录 → **blocking**。
- 有新增的、未在 `legacy_route_inventory` 或 `bff_route_inventory` 中登记的 `legacy` 路由调用字面量 → **blocking**。
- `generic_operation_count > 0` 且无原子性豁免（`atomicity_justification`）记录 → **blocking**。该条款意味着仅检查 `arguments` 是否 closed 不足以放行；Release Gate **MUST** 对每项 `operation + arguments` Capability 要求显式的原子性论证或拆分，否则视为 blocking。

---

## 二十一、V2.3 可信治理闭环（优先适用）

### 21.1 权威来源和版本身份

同一个逻辑 Capability 必须使用以下相互独立的身份，禁止复用同一字段表达多个对象：

| 身份 | 语义 | 变更规则 |
|---|---|---|
| `capability_id` | 逻辑业务能力 | 发布后不可复用或原地改名 |
| `major_version` | 对消费者可见的破坏性契约版本 | 发生不兼容变化必须递增 |
| `capability_version_gid` | `capability_id@major_version` 的持久化治理身份，采用不透明字符串 | 一经分配不可改变；不得与数据库行号混用 |
| `descriptor_revision_gid` | 某次完整 Descriptor 内容的不可变修订身份 | 任何 Descriptor 字段变化都产生新值 |
| `catalog_release_id` | 一组 Descriptor 修订和 Provider 制品的内容寻址发布 | Catalog 内容变化即产生新 release |
| `provider_artifact_hash` | 实际执行 Provider 制品的 SHA-256 | Provider 实现变化即产生新值 |

V2.1 中将 `capability_version_gid` 限定为 int64 雪花 GID 的条款由本节替代。治理数据库可以使用独立的数值主键，但公开契约和治理关系只能使用上述不透明身份，不得把内部主键暴露为 Capability 版本身份。

权威顺序为：本规范 → 已签名 Release Report → 不可变 Catalog Release → 官方 Registry/Provider Artifact → 派生文档和页面。下位来源与上位来源冲突时必须 fail closed 并产生 blocking Finding，禁止自动选择“看起来更新”的一方。

### 21.2 Catalog 声明与运行证据分离

Catalog 只登记预期契约、预期测试节点和证据策略，**MUST NOT** 在构建 Catalog 时自动写入未经本次运行验证的 `result=pass`。

`test_refs` 是覆盖声明，至少包含 `test_type`、`test_node_id` 和适用的 Capability 版本；实际结果必须存在独立、不可变的 Test Run 中，并至少绑定：

- `test_run_gid`
- `snapshot_gid`
- `catalog_release_id`
- `descriptor_revision_gid`
- `provider_artifact_hash`
- 后端和前端完整代码修订
- 测试节点、参数化 case ID、开始/结束时间、结果和输出摘要 hash

多个 Capability 可以复用同一个参数化测试函数，但每个 `Capability@major` 必须产生可独立查询的 case 结果。一个只验证“Descriptor 字段存在”的通用测试不能单独满足 stable 准入。

### 21.3 stable 与发布状态分离

`stable` 只表示契约已稳定，不等于已经通过测试或允许生产发布。发布候选还必须分别满足：`evidence_complete`、`runtime_verified`、`approved` 和 `release_signed`。业务节点的 `green` 状态不得仅由 Capability 的 `stable` 推导。

### 21.4 Catalog、Gateway 与 Provider 的强绑定

Gateway 每次调用必须验证：

1. 请求使用当前 active Catalog Release，或位于显式批准的兼容窗口内且不低于 minimum release floor。
2. Capability 在该 release 中存在且生命周期允许调用；`retired` 必须拒绝，`deprecated` 必须产生可观测告警并遵守最后支持日期。
3. 当前 Registry Provider 的 `provider_artifact_hash` 与 Catalog 固定值完全一致。
4. 输入验证、授权、确认、幂等、事务、超时、证据和审计策略均来自同一 Descriptor revision。

任一绑定不一致必须在 Provider 执行前拒绝，禁止回退到当前 Registry、默认 Provider 或历史未签名 Catalog。

### 21.5 运行时策略必须执行

Descriptor 中的下列策略是运行时强制项，不是文档字段：生命周期、consumer allowlist、授权和认证新鲜度、资源选择器、数据范围、确认、幂等、事务、deadline/timeout、证据、审计和输出投影。

- `write` 必须声明并验证事务策略；`strong` 一致性必须获得真实事务参与者和提交/回滚证明，装饰器或布尔标记不能作为事务证据。
- 审批令牌和幂等记录必须绑定 Catalog Release、Descriptor revision、Provider artifact 和规范化 payload hash；跨 release 不得复用。
- 输出必须先验证 Provider schema，再执行消费者投影，并对投影结果使用对应投影 schema 二次验证。
- 强写、高风险写和发布类操作在持久化审计不可用时必须 fail closed；读取类降级必须有界、可告警且可补偿落库。

机器枚举以代码契约为准，V2.3 标准值为 `read`、`write`、`destructive`；`none` 作为无调用能力的治理对象值，不得用于可执行 Provider。旧文档中的 `high_risk_write` 必须映射为 `destructive` 后再进入门禁。

### 21.6 唯一 Release Gate

正式发布只能由一个权威 Release Gate 产生结论。静态扫描、Catalog Audit、Acceptance、运行时 Snapshot/Finding、审批和 Waiver 都只是 Gate 输入，不能各自对外声称“发布通过”。

Gate 必须：

- 对所有 invalid、missing、failed、skipped、not-run、stale 指标 fail closed；禁止只检查部分计数。
- 从权威存储读取候选、Snapshot、Test Run、Finding、审批和 Waiver，不接受调用方自报结论。
- 绑定完整代码修订、Catalog/Descriptor/Provider hash 和消费者证据 hash。
- 生成持久化、可回读、可验签、可过期的 Release Report；输入变化后旧报告自动失效。
- 将扫描配置错误转换为结构化 blocking Finding；命令可以非零退出，但不得只抛出无报告异常。

### 21.7 例外与自动补全

治理生成器可以生成候选值，但候选值必须标记 `unverified`，不得直接满足 stable 或 Release Gate。通用 `business_effect`、通用 `provider_ref`、通用 `api_refs`、通用 `no_consumer_reason` 和静态 `result=pass` 均不得作为正式证据。

所有例外必须是结构化对象，包含范围、原因、owner、审批人、创建时间、绝对到期时间、证据引用和签名。例外到期、源文件 hash 变化或关联版本变化时自动失效。

### 21.8 V2.4 最小验收矩阵

每个 stable Capability 必须在同一 Test Run 中获得可追溯的业务目的确认、业务不变量证据、契约、Registry/Provider 解析、版本固定、授权和输出契约结果。write 额外要求资源范围、确认、幂等和事务结果；destructive 额外要求高风险审批、不可逆影响和恢复/补偿结果。具体业务行为可以按领域和共享 Provider 分组测试，不要求一个 Capability 一个测试文件，但每条业务不变量必须能反查到覆盖它的测试节点和结果。

治理系统自身必须保留反向测试，至少证明它能阻止：伪造 pass、过期证据、旧 Catalog 降级、Provider hash 漂移、retired 调用、跨版本审批/幂等复用、无事务 strong write、无资源选择器写入和审计不可用写入。

---

## 附录：V1 → V2 → V2.1 → V2.3 → V2.4 变更摘要

| 章节 | 类型 | 摘要 |
|---|---|---|
| 第三节 | V2 强化 | 登记字段必须同时出现在 Catalog 投影层和持久化存储；七个字段新增结构约束（GID、error_schema、transaction_policy、consumer_refs、provider_ref、api_refs、test_refs） |
| 第三节 | V2.1 澄清 | `side_effects`（叙述）与 `side_effect_level`（枚举）拆开定义；`error_schema` 明确映射到代码中的 `domain_errors` 字段并补齐 `is_caller_error`；`business_effect` 作为独立登记字段，不得以 `description/title` 直接替代 |
| 第十八节 | V2 新增 | Task Tool、Capability Pack、Skill、Workflow 骨架的完整治理要求 |
| 第十八.1 节 | V2.1 澄清 | Task Tool 权限边界从"消费者权限交集"改为"`consumed_capabilities` 所需权限并集（最大需求边界）"，单次调用时 Gateway 再按调用方实际授权约束 |
| 第十八.5 节 | V2.1 新增 | 明确 Task Tool 允许做 schema 适配（字段映射/格式转换），但不得引入业务判断；适配规则须记录在文档和 `test_refs` |
| 第十九节 | V2 新增 | 全景节点台账字段、绿黄红状态定义、节点完成八条件、生产可观测要求 |
| 第二十节 | V2 新增 | 遗留路由合规条件、新代码禁止规则、BFF 边界、退役验证标准、Release Gate 追加条件（含原子性 blocking） |
| 第二十.1 节 | V2.1 澄清 | `migration_deadline` 必须绑定到首次进入台账时对应发布版本日期，禁止用 CI 当前机器日期动态计算 |
| 第二十.2 节 | V2.1 澄清 | "禁止 REST"明确为"禁止绕过 Gateway 的直接 REST 调用"；通过 Gateway REST 适配器暴露的正式端点不在禁止范围内 |
| 第二十.3 节 | V2.1 澄清 | BFF 20% 比例分母明确为台账中唯一 `(route_path, method)` 对数量，不以静态扫描字面量计数为准 |
| 第二十一节 | V2.3 新增 | 分离六类版本身份，分离 Catalog 声明与 Test Run 证据，强制 active release/Provider 制品绑定、运行时策略执行和唯一签名 Release Gate |
| 第三、四、五、七、二十一节 | V2.4 新增 | 明确“能力目的先于约束”；禁止用机械生成文本满足 `business_effect`；新增 `business_invariants`、执行位置、稳定错误码、逐规则测试证据及相应版本规则 |
