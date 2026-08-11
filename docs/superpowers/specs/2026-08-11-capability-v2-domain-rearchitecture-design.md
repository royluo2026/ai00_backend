# Capability V2 领域重构详细设计

**日期：** 2026-08-11

**状态：** 已完成业务语义评审，待书面复核

**适用范围：** Base、Project Management、Factory、Craft、Knowledge、Ontology、Agent、Integration、Local Runtime、Digital Model、Simulation、Plugin Platform

**实现约束：** 本文仅定义目标设计，不授权立即修改业务代码

## 1. 文档目的

本文把 Capability V2 覆盖审计中已经确认的业务边界转化为可实施的代码与数据库重构设计。目标不是把现有每个路由包装成 Capability，也不是追求某个 Capability 数量，而是建立一套长期可维护的系统：同一个业务结果在 Web、REST、Plugin、Agent、MCP 和 Local Runtime 中使用同一个 Capability ID、同一个 Descriptor、同一个 Provider 和同一条 Gateway 治理链；每个领域独立维护代码、数据库、迁移、测试和发布边界。

当前业务数据为空，因此本次重构不设计旧业务数据搬迁、回填、双写或旧状态兼容。现有表结构只作为识别业务意图的证据，不约束目标模型。为完成前端和调用方切换，可以短期保留薄 REST 兼容适配器，但适配器不得包含业务逻辑、直接访问数据库或形成第二套实现。

## 2. 已确认的关键决策

1. Web、REST、Plugin、Agent、MCP、Local Runtime 共用一套 Capability 体系，不维护消费者专属业务实现。
2. Capability 表达稳定业务结果，不与路由、按钮、页面或内部函数一一对应。
3. 能力是否存在由业务语义决定，不以总数为设计目标，也不为了减少数量而合并权限、风险或状态机不同的动作。
4. 每个一级领域独立拥有代码、数据库、数据库用户、迁移流、Provider、测试和发布单元。
5. 禁止跨域 SQL、跨域 JOIN、跨域外键以及导入其他领域的 Router、Repository、ORM、数据库连接或具体 Service。
6. 跨域同步调用通过 Capability Gateway 或稳定 Public Port；异步协作通过带 Outbox 的版本化领域事件。
7. 跨域只保存不透明 ResourceRef、ArtifactRef、OperationRef 和不可变版本引用。
8. PBOM 是本产品唯一的生产物料结构名称；代码、表、API、Capability 和文档中的 eBOM 全部改为 PBOM。
9. Factory 的物理线体、物理工位和实物资产，与 BOP 的计划线体、计划工位、岗位、工序和操作严格分离。
10. BOP 的规范层级为 BOP Version → LineProcess → StationProcess → WorkPosition → Process → Operation。
11. Base 提供公共治理机制，但不能通过通用写能力修改任意领域对象。
12. 审批确认、心跳、租约、传输、健康检查、重试和内部状态不是业务 Capability。

## 3. 方案选择

### 3.1 未采用：原地修补

原地修改现有 Router、SQL 和 Capability 映射看似改动较小，但会继续保留 Craft 承载 Project、Factory、Ontology、Workspace 等职责的结构性问题。每次修改都需要理解跨域隐式依赖，无法达到独立维护和独立发布目标。

### 3.2 采用：干净领域包并行建设，逐域切换

为每个目标领域建立统一结构和独立数据库，按领域完成完整垂直切片：领域模型、应用服务、Provider、Capability、Repository、迁移、适配器、测试和文档同时交付。一个领域切换完成后，旧实现停止承担业务职责并被删除。

该方案允许逐步交付，又避免长期双写。由于现有数据为空，新旧实现不做数据同步；切换点只决定请求由旧 Router 还是新 Gateway 路径处理。

### 3.3 未采用：一次性全量重写

一次性替换全部领域虽然边界最整齐，但无法在中途获得可验证的垂直结果，联调失败时也难以定位责任。本文采用依赖有序的逐域切换。

## 4. 总体架构

正式业务请求采用以下唯一调用链：

~~~text
Web / REST / Plugin / Agent / MCP / Local Runtime
                         │
                         ▼
              CapabilityGatewayService
                         │
       identity / tenant / release / authorization
       approval / idempotency / concurrency / audit
                         │
                         ▼
                 Domain Provider
                         │
                         ▼
              Application Command/Query
                         │
                         ▼
             Domain Model + Owned Repository
                         │
                         ▼
                  Domain Database
~~~

Gateway 负责统一治理，不承载领域规则。Provider 是 Capability 与应用用例之间的稳定适配层。Application 层编排本领域用例。Domain 层包含实体、值对象、状态机和领域规则。Infrastructure 层实现数据库、OIS、Outbox 和外部端口适配。

### 4.1 保留的 Capability V2 内核

以下部分继续作为共享内核演进，而不是重写：

- Capability Descriptor、Catalog Release 和版本解析。
- Consumer Identity、委托身份和 Tenant 上下文。
- Capability Gateway 的授权、确认、幂等、并发和审计管道。
- EvidenceRef、Outcome、ArtifactRef、OperationRef 等公共契约。
- Web、REST、Plugin、Agent、MCP、Local Runtime 的统一暴露策略。
- Catalog、SDK、文档和验收清单生成器。

内核只允许依赖稳定公共契约，不允许依赖某个业务领域实现。

### 4.2 需要替换的部分

- Router 内的业务规则和 SQL。
- backend/capabilities 下跨领域、重复或临时的 Capability 定义。
- agreed_catalog.py 一类人工维护的并行能力清单。
- Agent Tool Handler 对业务 Router 或具体 Service 的直接调用。
- Craft 对 Project、Factory、Ontology、Canvas、共享、审批和外部集成的承载。
- Base 对 Knowledge、Project 等领域表的直接访问。
- 通过表名或 entity_table 动态查询其他领域数据的实现。

## 5. 统一领域包结构

除 Base 内核外，每个领域采用相同结构。Base 也应遵守等价的分层，只是物理位置可以保留在 backend/base。

~~~text
plugins/{domain}/
  {domain}_backend/
    domain/
      entities.py
      value_objects.py
      policies.py
      events.py
      errors.py
    application/
      commands/
      queries/
      services.py
      unit_of_work.py
    capabilities/
      descriptors.py
      contracts.py
      provider.py
      exposure.py
    ports/
      inbound.py
      outbound.py
      public.py
    infrastructure/
      repositories/
      database.py
      ois.py
      outbox.py
      external_clients.py
    api/
      rest.py
      compatibility.py
    bootstrap.py
  migrations/
    0001_initial.sql
    schema_manifest.json
  tests/
    domain/
    application/
    provider/
    integration/
    contract/
  pyproject.toml
~~~

文件可以按对象进一步拆分，禁止重新形成数千行的全领域 Router 或 Service。一个模块只处理一个聚合或一类稳定策略。

### 5.1 依赖方向

允许的依赖方向为：

~~~text
api → capability gateway contracts
provider → application → domain
infrastructure → application ports + domain
bootstrap → provider + infrastructure
~~~

Domain 不依赖 FastAPI、数据库驱动、Gateway 或其他领域。Application 不依赖具体 Repository。Provider 不直接执行 SQL。API 不绕过 Gateway 调用 Application。

## 6. Capability 定义与注册

### 6.1 唯一事实来源

每个领域的 descriptors.py 是该领域 Capability 定义的唯一事实来源。Descriptor 至少声明：

- capability_id、major_version、owner。
- 业务结果、适用条件和明确非目标。
- 输入、输出和完整领域错误契约。
- side effect、execution mode、automation level。
- authorization、resource selector、delegation 和 data classification。
- confirmation、idempotency、concurrency 和 consistency 策略。
- Artifact、Operation、Evidence 和 audit 要求。
- Web、REST、Plugin、Agent、MCP、Worker、Local Runtime 暴露矩阵。

一个 stable Descriptor 必须有且只有一个生产 Provider。Descriptor 不能使用宽泛 union schema 隐藏权限或风险不同的动作。

### 6.2 Provider 约束

Provider 只执行以下职责：

1. 将 Gateway 已验证的输入转换成 Application Command 或 Query。
2. 传递可信 CapabilityContext。
3. 将领域结果转换成稳定输出、Evidence 和 Operation。
4. 将已声明的领域错误映射成 Capability 错误。

Provider 不负责身份解析，不读取 HTTP Header，不直接访问其他领域，也不根据 consumer 类型实现不同业务规则。

### 6.3 Catalog 构建

构建流程按以下顺序执行：

1. 加载每个领域发布的 Descriptor Bundle 和 Provider Manifest。
2. 检查 ID、major、owner 和 Provider 唯一性。
3. 检查 Schema、错误、权限、资源选择器和策略完整性。
4. 检查暴露矩阵满足消费者安全要求。
5. 冻结 Catalog Release，计算 Catalog Hash。
6. 生成 Web SDK、REST OpenAPI、Plugin SDK、Agent Tool、MCP Tool 和 Local Runtime 契约。
7. 生成文档和 acceptance manifest。

所有调用固定 catalog_release、capability_id 和 major_version。禁止 latest 隐式回退。

## 7. 消费者适配

### 7.1 Web

Web 使用生成的 Capability Client。正式业务按钮不再直接调用旧领域 Router。客户端只负责输入收集、确认交互、Operation 状态展示和错误呈现。

个人布局、临时选择状态、流式显示等 UI 偏好不是业务 Capability，可调用 Base Workspace 的专用低风险 API；团队共享模板等正式状态仍走 Capability。

### 7.2 REST 兼容层

旧 REST 路径可以在切换期间保留，但只能：

1. 解析旧请求。
2. 转换成 Capability 输入。
3. 调用 Gateway。
4. 转换稳定结果为旧响应格式。

兼容层不得访问数据库、调用 Repository、执行业务校验或吞掉 Gateway 错误。Web 切换完成并通过契约测试后删除兼容路由。

### 7.3 Plugin

插件安装时固定签名版本、Catalog Release 和授权能力集合。每次调用携带不可伪造的安装身份、Tenant、Plugin ID、版本和委托用户。安装或升级不自动获得全部能力；升级新增权限时必须重新取得管理员同意。

### 7.4 Agent 与 MCP

Agent 和 MCP 工具由 Descriptor 自动生成，不能继续维护手写业务 Tool Handler。工具调用必须绑定 Agent Run、委托用户、预算、确认结果和 Catalog Release。Agent 不能作为人类审批者。

### 7.5 Local Runtime

Local Runtime 只执行明确列出的本地应用动作。平台不提供任意 local.command.execute。设备激活、心跳、租约、完成和 Artifact 传输属于签名协议，不进入业务 Catalog。

## 8. Tenant、身份与授权

### 8.1 Tenant 模型

Tenant 是最高安全边界。Tenant 下包含 Team，Project Membership 再决定项目访问。所有领域表必须包含不可为空的 tenant_gid，所有 Repository 查询必须首先限定 tenant_gid。

禁止以下做法：

- team_id 缺失时使用默认团队。
- 使用 owner_gid 或 team_gid 推导 Tenant。
- 从请求 payload 接受任意 tenant_gid 后直接信任。
- 只按资源 GID 查询再做应用层过滤。

Tenant 只能来自经过认证的 ConsumerIdentity 和 DelegationContext。

### 8.2 授权分层

授权按以下顺序执行：

1. Consumer 是否允许使用该 Capability。
2. Plugin 安装或 Agent Definition 是否被授予该 Capability major。
3. 委托用户是否拥有业务权限。
4. Resource Selector 是否解析到同一 Tenant 且用户可访问。
5. 是否满足审批、确认、预算和数据分类策略。

领域 Provider 仍负责本领域对象状态和不变量校验，但不能重新实现身份系统。

### 8.3 审批与确认

Gateway Confirmation 是调用安全协议，不是业务审批。Base Approval 是有申请人、审批人、对象快照和正式决定的业务服务。

领域提交审批时保存精确 ResourceRef、revision/hash 和申请原因。Base 不修改领域数据。审批通过后，由原领域验证对象仍与审批快照一致并继续状态转换。

## 9. 数据库独立性

### 9.1 物理部署

可以共用 OceanBase 集群，但每个领域使用独立 Database、数据库用户、连接池和迁移版本表：

| 领域 | 目标 Database |
|---|---|
| Base 与 Plugin Platform | ai00_base |
| Project Management | ai00_project |
| Factory | ai00_factory |
| Craft | ai00_craft |
| Knowledge | ai00_knowledge |
| Ontology | ai00_ontology |
| Agent | ai00_agent |
| Integration | ai00_integration |
| Local Runtime Control Plane | ai00_local_runtime |
| Digital Model | ai00_digital_model |
| Simulation | ai00_simulation |

每个账号只拥有本 Database 的读写和迁移权限。运行时账号没有其他 Database 权限。数据库级权限测试必须证明跨域 SELECT、INSERT、UPDATE、DELETE 均失败。

### 9.2 迁移策略

现有数据为空，采用 clean bootstrap：

- 新建目标 Database 和初始 Schema。
- 不搬迁旧业务数据，不生成 backfill，不双写。
- 不依赖旧表兼容视图。
- 历史迁移文件可保留作为代码历史，但新部署只运行目标领域迁移流。
- 旧表在所有消费者切换并通过验收后删除。

一个领域的迁移可以独立执行和回滚，不能要求同时运行其他领域迁移。

### 9.3 事务与事件

一个数据库事务只能写一个领域。跨域流程使用：

- 同步 Gateway 调用，适合需要立即验证的查询或短操作。
- 本领域事务写入 Aggregate 与 Outbox，提交后异步发布事件。
- 消费方使用 inbox/dedupe key 保证幂等。
- 补偿操作调用公开 Capability，不直接反向修改其他领域表。

不实现分布式数据库事务。

## 10. 公共引用契约

跨域引用采用带类型和版本的稳定结构：

~~~json
{
  "resource_type": "factory.asset",
  "resource_id": "asset_...",
  "tenant_gid": "tenant_...",
  "version": 3,
  "content_hash": "sha256:..."
}
~~~

tenant_gid 不允许由普通调用者填写；它由 Gateway 绑定或由 Provider 输出。不可变资源必须包含 version/hash。可变身份引用只保存 resource_id，使用前通过所有者 Provider 重新校验。

ArtifactRef 只指向 OIS 中的不可变内容并包含 media type、sha256、byte size 和 artifact version。OperationRef 只表达异步执行状态，不代替领域 Run、Job 或 Version ID。

## 11. Base 详细设计

### 11.1 Base 拥有

- Tenant、User、Team、身份认证和授权策略。
- Capability Gateway、Catalog Release、Delegation、Outcome、Approval Challenge。
- 正式业务 Approval 服务。
- Notification、Workspace、团队工作台模板。
- Plugin Publisher、Release、Installation、Mount 和私有存储。
- System Audit、Activity 聚合、Job 聚合、Lineage 与 Change Impact 聚合。
- OIS 和 Operation 的公共协议与适配。

### 11.2 业务 Capability

- base.approval.request.create/get/search/decide/cancel。
- base.notification.search/read_state.set/preference.get/preference.update。
- base.workspace.template.read/publish。
- system.audit.search、system.activity.search。
- system.job.get/cancel。
- system.search、system.lineage.get、system.change_impact.preview。
- identity.principal.search。
- plugin.publisher.register、plugin.publisher.key.rotate。
- plugin.release.submit/get/search/review.decide/revoke。
- plugin.installation.install/get/search/enable/disable/upgrade/rollback/uninstall。
- plugin.storage.value.get/put/delete、plugin.storage.key.search。

### 11.3 排除

原始日志、debug trace、health、ready、worker heartbeat、outbox、幂等表、任务租约、Catalog 生成、Gateway token、mount token、升级健康回调和插件月度统计关闭均为内部或运维机制。

Base Revision 引擎只提供不可变 revision graph 和内部校验，不提供可修改任意领域对象的 revision.apply。

## 12. Project Management 详细设计

### 12.1 拥有

- Project、Project Member、Project Access Scope。
- Task、Issue、Milestone 和各自状态机。
- Project List、列表项和列表访问控制。
- Task Template 及实例化。
- Follow、Comment、Mention、Collaboration、Share Link。
- 项目活动事件，不拥有 Notification 投递。

### 12.2 关键能力边界

- Project 与 Project Member 分开授权。
- Task 和 Issue 保留独立状态机，在数据模型真正统一前不合并。
- Task Template 的维护与 instantiate 分开。
- Follow 是个人订阅关系，不是 ACL。
- List Share 是访问控制，不是 Collaboration 内容。
- External Share Link 会向系统外暴露信息，必须单独授权和审计。
- 工作台首页是读投影；个人布局归 Base Workspace 偏好。
- Project line scope 调用 Craft 公开 Provider 校验，不读取 Craft 表。

### 12.3 代码迁移

所有位于 plugins/craft 下但属于 Project、List、Follow、Share、Collaboration、Task Template 的实现迁入 plugins/project_management。旧 backend/routers 仅在切换窗口保留 Gateway 兼容适配器。

## 13. Factory 详细设计

### 13.1 领域模型

Factory 分为三部分：

1. Physical Structure：Factory、Section、Physical Line、Physical Station。
2. Resource Catalog：设备、工具、工装的类型、规格和模板。
3. Physical Asset：有资产编号和生命周期的实物设备、工具、工装。

asset_type 区分 equipment、tool、fixture；三者共享资产聚合，除非未来出现不同生命周期。

### 13.2 Capability

- factory.structure.create/get/search/update/archive。
- factory.resource_catalog.get/search/create/revise/publish/deprecate。
- factory.asset.register/get/search/update。
- factory.asset.maintenance.start/complete。
- factory.asset.scrap。

不提供普通硬删除。现有数据为空，不需要 registration.cancel 或旧资产状态迁移。报废是不可逆高风险动作，必须独立授权和确认。

Factory 当前不建立 allocation/reservation 能力，因为产品尚无真实预订聚合、冲突规则和释放生命周期。

### 13.3 与 BOP 的边界

BOP StationProcess 和 LineProcess 只是计划节点。Craft 可以保存 Factory ResourceRef，并在绑定时调用 Factory Provider 校验。Factory 不保存 BOP 节点，不参与 BOP 树事务。

## 14. Craft 详细设计

Craft 只负责“如何制造”，由 PBOM、BOP、GBOP、工艺规则和工艺知识目录组成。

### 14.1 PBOM

当前可修改 Snapshot 改为 Draft/Published Version 模型：

- craft.pbom.version.create/get/search/submit/publish/archive/compare。
- craft.pbom.draft.change.preview/apply。
- craft.pbom.part.search。
- craft.pbom.import.preview。

发布版本不可变。导入文件的通用解析由 Data Exchange 完成，PBOM import.preview 负责领域语义、结构和哈希校验。

### 14.2 BOP

- craft.bop.version.create/get/search/validate/submit/publish/archive/compare。
- craft.bop.draft.change.preview/apply。
- craft.bop.execution_plan.get。
- craft.bop.import.preview。
- craft.bop.pbom_link.preview/apply。
- craft.bop.gbop_link.preview/apply。
- craft.bop.factory_binding.preview/apply。

节点编辑通过 typed command 和 expected revision 原子执行，不为每种节点生成独立 CRUD Capability。preview 生成短期、绑定调用者和 base revision 的 preview ref；apply 只能消费精确 preview，且检查内容哈希和并发版本。

层级名称固定为 LineProcess、StationProcess、WorkPosition、Process、Operation。旧 operator、post、step 等含混或错误名称全部移除。

### 14.3 GBOP

- craft.gbop.draft.create/get/search/change.preview/change.apply/submit。
- craft.gbop.release.get/search/publish/activate/archive/compare。
- craft.gbop.item.search、item.usage.get、item.knowledge.search。

从 GBOP 创建项目 BOP 使用 craft.bop.version.create，并固定精确 GBOP Release；fork、copy、smart-fork 不再各自形成 Capability。

### 14.4 工艺规则

- craft.rule.draft.create/get/search/revise/submit。
- craft.rule.release.get/search/publish/activate。
- craft.rule.evaluate。
- craft.bop.validation.run/get。
- craft.rule.waiver.create/search/revoke。

Ignore 改为正式 Waiver，记录理由、负责人、作用范围、规则版本和有效期。

### 14.5 移出 Craft

- Factory 结构、资源目录和实物资产移入 Factory。
- Ontology 编辑和 Release 移入 Ontology。
- Project、List、Follow、Share、Collaboration、Task Template 移入 Project Management。
- Canvas 和工作台移入 Base Workspace。
- Approval 使用 Base Approval。
- Excel/飞书连接和同步移入 Integration 或内部 Data Exchange。

## 15. Knowledge 详细设计

### 15.1 领域模型

正式模型为 Space → Document → Immutable Revision。Legacy Knowledge Entry、Hub Item 和 Folder 迁移逻辑不进入新模型；现有数据为空，直接删除兼容路径。

### 15.2 Capability

- knowledge.space.create/get/search/update/archive。
- knowledge.document.create/get/search/revise/restore/archive/diff/history.get。
- knowledge.document.access.list/grant/revoke。
- knowledge.document.favorite.set。
- knowledge.document.pin.set。
- knowledge.context.retrieve。
- knowledge.proposal.create/get/search/revise/submit/withdraw。
- knowledge.proposal.review.decide。

收藏查询和最近访问查询作为 document.search 的过滤或排序。最近访问写入在 document.get 成功后由 Knowledge 内部记录。置顶是全局编辑治理行为，与个人收藏分离。隐藏状态归发布或归档治理，不作为普通字段修改。

Revision 内容存入 OIS，数据库只保存不可变引用、哈希和元数据。Knowledge 不导入 Craft history helper，也不保存 file_path。

Proposal outbox、retry、migration status 和 recent-access write 不进入业务 Catalog。

## 16. Ontology 详细设计

### 16.1 Capability

- ontology.concept.resolve/get/search。
- ontology.mapping.assess。
- ontology.proposal.create/get/search/revise/submit/withdraw/review.decide。
- ontology.release.get/search/diff/publish/activate。

Concept、Property、Relation、Mapping、Constraint 的持久化修改全部表示为 Proposal change，不提供直接 CRUD。

Proposal Revision 不可变。review 决定绑定精确 revision/hash，作者不能评审自己的提案。任何修改都会产生新 revision，旧评审不自动继承。

publish 创建不可变但未激活的 Release；activate 在兼容性证明无阻断后原子切换 Active Ref。回退通过生成新的前向 Release 完成，不直接激活历史 Release。

Ontology 不保存 entity_table，不动态查询其他领域表，不修改 BOP、Factory、PBOM 或 Project 实体。

## 17. Agent 详细设计

### 17.1 核心聚合

- Agent Definition：模型、Prompt、工具集合、预算和执行策略。
- Flow：节点、分支、依赖和错误路径组成的可执行图。
- Skill：可复用指令、知识和工具使用内容。
- Session：对话与上下文容器。
- Run：一次实际执行。
- Memory：跨 Session 的长期用户数据。
- Run Trace：执行步骤与工具证据。

Definition、Flow、Skill 均采用长期身份、不可变 Revision、发布和归档。Run 必须固定已发布 Revision 和 Catalog Release。

### 17.2 Capability

- agent.definition create/get/search/revise/publish/archive 家族。
- agent.flow create/get/search/revise/publish/archive 家族。
- agent.skill create/get/search/revise/publish/archive 家族。
- agent.session.create/get/search/archive。
- agent.run.start/get/search/continue。
- agent.memory.get/search/remember/forget。
- agent.run.trace.get/search。

Run 取消统一走 system.job.cancel。chat/stream 是 Run 的传输适配。Flow step、checkpoint、budget counter、tool selection、delegation envelope、恢复重试和 ask-clarification 事件属于运行时内部状态。

Agent Tool 只能来自冻结 Catalog。手写 craft_tools、knowledge_tools、project_tools 等业务 Handler 删除。Agent Trace 与 System Audit 分开：Trace 解释模型如何运行，Audit 证明 Capability 是否被授权和执行。

## 18. Integration 详细设计

### 18.1 Capability

- integration.connector.create/get/search/update/archive。
- integration.connector.credential.rotate。
- integration.connector.connection.test。
- integration.connector.schema.discover。
- integration.mapping.create/get/search/update/archive/preview。
- integration.sync.start/get/search/cancel。

Connection Test 使用密钥并访问网络，必须有独立 SSRF、网络策略、超时、审计和结果脱敏。Mapping 不接受任意 SQL 或可执行转换脚本，只接受受限表达式。

Sync 可以编排目标领域 Capability，但不能直接写目标领域数据库。飞书目录同步、外部数据库、SaaS、Webhook 都是不同 Connector Adapter，共用同一 Connector 聚合。

Webhook、cursor、lease、retry、outbox 和定时触发属于内部协议。

## 19. Local Runtime 详细设计

### 19.1 Capability

- local.device.enrollment.create。
- local.device.get/search/revoke。
- local.operation.get/cancel。
- vismockup.status/launch/model.open/tree/highlight/visibility/capture。

每个本地动作具有固定输入、设备资源选择器、签名 Operation、确认策略和结果证据。禁止任意命令执行能力。

设备 activation、heartbeat、command lease、complete、Artifact 下载和结果上传属于 Local Runtime 协议。Local Runtime 与 Integration 分别维护代码和数据库，不再使用 local_integration 混合 owner。

## 20. Digital Model 详细设计

### 20.1 模型修正

Model 是长期身份，Version 是不可变内容快照。取消单独 Snapshot 生命周期和命名。

### 20.2 Capability

- digital_model.model.create/get/search/update/archive。
- digital_model.version.create/get/search/compare。
- digital_model.component.search。

Version 固定可信 ArtifactRef、父版本、内容哈希和组件索引。组件清单由受信任解析 Provider 从 Artifact 提取，或验证为与 Artifact 哈希绑定的结果，不能信任调用者任意提交的组件数组。

project_ref 是不透明跨域引用，通过 Project Provider 验证访问。PBOM、BOP 和 Factory 资产不属于 Digital Model。

## 21. Simulation 详细设计

### 21.1 聚合与 Capability

- simulation.parameter_set.create/get/search。
- simulation.solver_profile.create/get/search。
- simulation.environment.create/get/search/archive。
- simulation.run.start/get/search。
- simulation.result.get/compare。

Parameter Set、Solver Profile 和 Environment 创建后不可修改。Environment 固定 Craft Execution Plan、Digital Model Version、Parameter Set 和 Solver Profile，并计算总 fingerprint。

Run 是业务记录，Operation 是异步协议，两者使用不同 ID。Run 取消由 system.job.cancel 调用 Simulation Job Provider。Solver 和版本来自平台允许清单。Result 使用不可变 OIS Artifact，并绑定 Run 输入 fingerprint。

## 22. Plugin Platform 详细设计

Publisher、Release 和 Tenant Installation 是不同聚合。Release submit、review、revoke 分别对应发布方提交、平台审核和安全撤销。安全撤销会传播到所有安装。

Installation install、enable、disable、upgrade、rollback、uninstall 保持明确状态。upgrade.finish 是可信部署健康回调，不是业务 Capability。卸载根据 Manifest Data Policy 执行 delete、retain 或 export-then-delete。

插件私有存储以 tenant_gid、plugin_id 和显式 scope 隔离。支持 tenant 与 user scope，但 scope 权限由安装授权决定。普通 Agent 不能借用插件命名空间。

## 23. 错误、并发、幂等与证据

### 23.1 错误

每个 Capability 声明完整、稳定的领域错误代码。禁止把数据库异常、外部响应正文或堆栈直接返回消费者。错误至少区分：not found、forbidden、state conflict、revision conflict、validation failed、dependency unavailable、outcome unknown。

### 23.2 并发

所有可变聚合使用 expected revision 或 expected state。Draft preview 绑定 base revision；Apply 时版本不一致必须失败，不能静默覆盖。

### 23.3 幂等

可能重复提交的写操作必须使用 Gateway Idempotency Key。异步 start 返回稳定 OperationRef。外部或本地执行超时后，如果结果未知，返回 outcome_unknown 并进入对账，禁止自动重复执行有副作用动作。

### 23.4 Evidence

发布、激活、审批、仿真、模型版本、BOP 执行计划和本地动作必须返回可验证 EvidenceRef。Evidence 引用不可变对象、版本和哈希，不保存仅供展示的模糊文本。

## 24. 可观测性

三类记录严格分离：

1. 原始应用日志：运维使用，不是 Capability。
2. System Audit：授权、确认、委托、调用和执行结果的不可变安全审计。
3. Domain Activity / Agent Trace：用户业务活动或 Agent 执行解释。

日志必须包含 trace_id、request_id、tenant_gid、consumer、capability_id、major、catalog_release、provider 和 outcome，但不得记录密钥、Token、完整敏感 Payload 或未脱敏模型内容。

## 25. 实施阶段与退出条件

### 阶段 0：冻结设计与清单

- 将本文转化为机器可校验的 Capability Ledger。
- 每个能力记录 owner、业务结果、非目标、策略和消费者暴露。
- 删除数量目标和通用 change.apply 候选中的语义歧义。

退出条件：没有 unreviewed、candidate-only 或无 owner 的正式业务项。

### 阶段 1：Kernel 与领域脚手架

- 固化 Descriptor Bundle、Provider Manifest 和 Domain Bootstrap 接口。
- 建立独立 Database 配置和 Migration Runner。
- 建立 DomainCapabilityClient、Event Envelope、Outbox/Inbox 公共契约。
- 更新边界检查器，使新跨域依赖立即失败。

退出条件：空领域包可以独立迁移、注册 Provider、构建 Catalog 和运行契约测试。

### 阶段 2：Base

- 重建 Tenant、Approval、Notification、Workspace、Plugin Platform 和 System Provider。
- 清除 system.echo、worker health 等伪业务能力。
- 修复所有领域显式 Tenant 上下文。

退出条件：其他领域只依赖 Base 公共契约，不依赖 Base Router 或表。

### 阶段 3：Project Management 与 Factory

- 从 Craft 物理迁出 Project/Collaboration 与 Factory。
- 建立独立数据库和 Provider。
- Web 兼容路由切换到 Gateway。

退出条件：Craft 不再拥有项目表、物理工厂表或相关业务代码。

### 阶段 4：Knowledge 与 Ontology

- 建立 Document/Revision、Proposal/Review/Release 目标模型。
- 删除 Legacy Entry、Hub、直接 Schema CRUD 和跨域历史工具。

退出条件：Knowledge、Ontology 各自独立迁移、发布和测试，跨域 SQL 为零。

### 阶段 5：Craft

- 依次交付 PBOM、BOP、GBOP、Rule 垂直切片。
- 完成名称修正和计划结构/物理结构分离。
- 删除旧节点 CRUD、freeze/promote/copy 路由中的业务实现。

退出条件：Craft 只维护“如何制造”，所有发布版本不可变，三种跨域关联均通过 Provider。

### 阶段 6：Digital Model 与 Simulation

- 统一 Model Version 命名。
- 分离 Run 与 Operation。
- 固化可复现引用和结果 Evidence。

退出条件：下游使用精确不可变引用，结果可复现和比较。

### 阶段 7：Integration 与 Local Runtime

- 拆分 Connector 和设备控制面。
- 清除任意 SQL、任意本地命令和混合 owner。

退出条件：外部同步只能通过 Capability 写入目标域，本地命令只允许白名单动作。

### 阶段 8：Agent

- 重建 Definition、Flow、Skill、Session、Run、Memory、Trace。
- Agent Tools 全部改为 Catalog 生成。
- 删除旧业务 Tool Handler 和旧 App Flow Run。

退出条件：Agent 不导入任何业务领域实现，所有工具调用经过 Gateway。

### 阶段 9：消费者切换与清理

- Web、REST、Plugin、Agent、MCP、Local Runtime 完成消费者一致性验证。
- 删除兼容 Router、旧表、旧 Capability alias 和边界 baseline 豁免。

退出条件：只有目标实现可达，旧实现和双路径为零。

## 26. 测试策略

### 26.1 领域测试

- 纯 Domain 状态机和不变量测试。
- Application Command/Query 测试。
- Repository 与独立 Database 集成测试。
- Migration 从空库升级和回滚测试。

### 26.2 Capability 测试

- Descriptor Schema、权限、资源选择器和暴露策略测试。
- Provider 正常、拒绝、冲突、幂等和错误契约测试。
- Evidence、Outcome、Operation 和审计完整性测试。
- 同一 Capability 在 Web、REST、Plugin、Agent、MCP 的消费者一致性测试。

### 26.3 边界测试

- 静态扫描跨域 Router、Repository、ORM、DB helper import。
- SQL 扫描表所有权。
- 使用真实数据库 Grant 验证跨域访问失败。
- 检查一个表、Migration、Provider 和 Capability 只有一个 owner。

### 26.4 系统验收

- Registry 中每个稳定用户功能都有 existing capability、new capability 或具体 exclusion。
- stable Capability 均有生产 Provider。
- Catalog、SDK、OpenAPI、Agent/MCP tools 和文档无漂移。
- Offline strict acceptance 无失败和强制跳过。
- RC 还必须在隔离环境完成 OceanBase、OIS、JWT/OAuth、Local Runtime 和 Windows .NET 证据。

## 27. 发布、切换与回滚

每个领域独立发布 artifact、schema version、descriptor bundle 和 provider manifest。切换使用领域级开关，但任一请求只能进入一个权威实现，不允许双写。

切换步骤：

1. 部署新领域 Database 和 Provider，保持消费者不可见。
2. 完成 Provider 集成与 Gateway shadow-read；shadow-read 仅比较无副作用查询。
3. 冻结新 Catalog Release。
4. 将 REST 兼容适配器和 Web SDK 切到新 Capability。
5. 观察错误率、延迟、审计完整性和领域指标。
6. 删除旧业务路径和旧表。

回滚只回滚代码路由和未破坏兼容性的领域 Migration。已发布的不可变业务 Version、Release 和 Evidence 不删除。因为没有旧业务数据，首次切换失败时可以清空目标测试 Database 后重新 bootstrap，但不得在生产发布后用清库代替正式回滚。

## 28. 安全要求

- 密钥只存专用 Secret Store 或加密列，任何 API 均不回显。
- 外部 Connector 执行网络 allowlist、DNS/IP 复核、超时和响应大小限制。
- 本地 Operation 签名、防重放、设备撤销和结果对账必须开启。
- Plugin iframe、mount session、installation grants 和 Capability delegation 全链路绑定。
- Agent 输入和模型输出均视为不可信数据，不得生成或选择未授权 Capability。
- 高风险动作如 Ontology activate、Plugin revoke、Factory asset scrap、外部 Share Link 创建必须有独立权限和相应确认。
- 审批人身份必须为真实人类交互上下文，Agent 和 Plugin 不能伪造。

## 29. 明确非目标

本次重构不包含：

- 为追求数量而合并业务语义。
- 迁移当前空数据库中的历史业务数据。
- 引入分布式数据库事务。
- 新建 Factory 资源预订或排产系统。
- 新建插件计费、分账或结算系统。
- 开放任意 SQL、任意脚本或任意本地命令。
- 把全部 REST 路由机械转换成 Capability。
- 在一个实施计划中同时重写所有领域。

## 30. 完成定义

Capability V2 领域重构只有在以下条件全部满足时完成：

- 业务语义清单已经固化，Capability 数量是语义结果而非目标。
- 所有正式消费者共用同一 Capability、Descriptor、Provider 和 Gateway。
- 所有一级领域独立维护代码、数据库、迁移、测试和发布。
- 跨域 SQL、JOIN、外键和内部实现 import 全部为零。
- PBOM 命名统一，BOP 计划结构与 Factory 物理结构完全分离。
- Base 没有任意领域写入后门。
- Agent、Plugin 和 Local Runtime 只能执行明确授权的 Capability。
- 所有 stable Capability 有真实生产 Provider 和完整验收证据。
- 兼容业务实现、旧表、重复 Capability 和治理 baseline 豁免全部删除。

本文批准后，下一步不是直接写代码，而是按阶段拆分实施计划。每个阶段应进一步分成可验证的垂直任务，列出准确文件、测试、迁移、切换点和删除项。
