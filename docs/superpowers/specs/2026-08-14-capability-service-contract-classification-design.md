# Capability 标准语义与分类设计

## 1. 目的

本文为现有 Capability V2 Catalog 建立与软件行业通用术语一致的语义模型和分类规则。此次调整不重新梳理业务，不改变现有 Capability ID、Major、调用地址、权限或运行实现；第一阶段只增加分类、关系和复核状态。

本文只处理 Capability 治理问题，不展开业务运行语言、Judgment 或业务流程建模。

## 2. 行业术语基线

采用 SOA、WSDL、OpenAPI 和 DDD 应用层常用术语：

- **Service Contract / Service Interface（服务契约/服务接口）**：定义一组相关服务操作的抽象语义、输入输出、约束和错误，不承担具体执行。
- **Service Operation（服务操作）**：一次可独立调用的业务动作。
- **Application Use Case（应用用例）**：从应用层观察的完整用户或系统意图；通过一个或多个 Service Operation、规则和必要判断形成可复用执行方案。
- **Provider / Handler（提供者/处理器）**：Service Operation 的具体实现。
- **Service Facade（服务门面）**：为了兼容或聚合而提供的入口，通过 `operation`、`action` 或类似判别字段分派到多个实际操作。

WSDL 的 Interface 组织 Operations，并由 Service/Endpoint 提供具体实现；OpenAPI 将单个可调用行为称为 Operation。AI00 不再创建与这些概念重复但只有项目内部才能理解的新术语。

参考：

- W3C WSDL 2.0: https://www.w3.org/TR/wsdl20/wsdl20-z.html
- OpenAPI 3.0: https://spec.openapis.org/oas/v3.0.0.html
- OMG SoaML: https://www.omg.org/spec/SoaML/

## 3. AI00 正式模型

AI00 保留 `Capability` 作为产品和治理术语，其正式含义为：

> Catalog 中拥有稳定 ID 和 Major，可以独立授权、调用、版本化、审计和验证的 Service Operation。

Capability 不是 Application Use Case。前者表达单一、确定性的受治理动作；后者表达为了完成一个可复用目标而组织的一组 Capability、规则、判断和事务边界。

正式关系如下：

```text
Service Contract / Service Interface
    └── defines_operation
            └── Capability（受治理的 Service Operation）
                    ├── implemented_by Provider / Handler
                    ├── exposed_through REST / Mount / Agent / MCP / UI Action
                    ├── used_by Application Use Case
                    ├── consumed_by UI / Plugin / Agent / Automation
                    └── operates_on Aggregate / Entity / Reference Dataset
```

Capability 与 DDD Aggregate Root 不属于同一分类维度：

- Capability 是外部可治理的动作边界。
- Aggregate Root 是内部状态和一致性边界。
- 一个 Capability 原则上只修改一个主要 Aggregate；跨 Aggregate 或跨领域写入通过 Domain Port、事件或 Saga 协调。
- 一个 Aggregate Root 可以被多个 Capability 操作。

### 3.1 Capability 到业务编排之间的正式层级

业务编排采用以下层次：

```text
Business Process / Business Scenario
    └── Business Activity / Task
            └── invokes Application Use Case
                    ├── uses Capability
                    ├── evaluates Rule / Decision
                    ├── requests Judgment / Approval
                    └── controls transaction / compensation
```

- **Business Activity / Task** 是某条业务流程或业务场景中的具体步骤，带有当前 Case、角色、时限和上下文。
- **Application Use Case** 是可跨页面、插件、Agent 和流程复用的目标导向执行方案。它声明前置条件、输入、输出、成功条件、失败与补偿，并组合一个或多个 Capability。
- **Capability** 只承担单一确定性业务效果，不知道自己被哪条流程调用，也不承担整段业务目标。

Application Use Case 是 Capability 与可编排业务步骤之间缺失的正式层。它可以由 UI、插件、Agent Workflow 或后台自动化实现，但其语义和身份不等同于任何一种实现载体。

## 4. Catalog 分类

每个 Catalog Entry 必须声明 `semantic_kind`：

### 4.1 `service_operation`

满足以下条件：

- 表达一个清晰、单一的业务动作。
- 可以独立授权、调用、版本化、审计和测试。
- 输入不依赖开放式 `operation`、`action` 或类似字段选择不同业务动作。
- 副作用、确认、幂等、一致性和错误语义可以在一个契约中明确描述。

典型例子：`simulation.run.start@1`、`craft.bop.version.create@1`、`digital_model.version.get@1`。

### 4.2 `service_facade`

满足任一条件：

- 通过 `operation`、`action`、`command` 或类似字段分派多个不同动作。
- 一个入口承载多个不同的权限、副作用、确认、幂等或错误模型。
- 主要作用是兼容旧 API、旧页面或聚合调用，而不是表达单一业务动作。

Service Facade 可以暂时保留，但属于兼容入口。其内部实际操作必须逐步进入关系图；需要独立治理的实际操作最终升格为独立 Capability。

### 4.3 `internal_operation`

满足全部条件：

- 只能由一个 Provider 或 Handler 内部调用。
- 没有独立外部入口和消费者。
- 不需要独立授权、Major、生命周期和发布承诺。
- 生命周期完全从属于父 Capability。

`internal_operation` 不是正式 Capability，原则上不得作为稳定条目保留在公开 Catalog。扫描发现正式 Catalog Entry 实际属于内部操作时，应生成治理 Finding，经过影响分析后再退役，不能自动删除或改 ID。

## 5. 单一业务效果字段

每个 Capability 必须具有 `business_effect`，中文显示名为“单一业务效果”。该字段用一句业务语言说明 Capability 成功完成后，哪个业务对象发生了什么可观察变化或返回了什么确定结果。

编写规则：

- 使用“动词 + 业务对象 + 结果状态”的结构。
- 一条只表达一个效果。
- 不写 API、数据库、Provider、Handler、协议或代码实现。
- 不写“用于……”“帮助……”或它可能参与的业务流程。
- 不把多个动作的执行顺序写入一条 Capability。
- `service_facade` 无法形成单一效果时，写成“按指定操作读取/变更……”并保持 `needs_review`，不得伪装成原子动作。

示例：

- `craft.bop.version.create`：为指定 BOP 创建一个新的可编辑版本。
- `digital_model.version.get`：取得指定数模版本及其受控快照信息。
- `simulation.run.start`：将已配置完成的仿真运行置为启动状态。
- `project.task.change.apply`：按指定操作变更项目任务或其状态。

`business_effect` 只是 Capability 的动作语义，不替代 Application Use Case。Application Use Case 通过 `uses_capability` 关系组合多个 Capability，并声明自己的目标、前置条件和成功标准。

## 6. 初始机器分类规则

第一轮分类只产生基线，不直接触发拆分或退役：

1. 当前 264 个 Capability ID 和 Major 全部保持不变。
2. 输入 Schema 包含通用 `operation` 或 `action` 分派字段的条目，初始标记为 `service_facade`，复核状态为 `needs_review`。
3. 其余条目初始标记为 `service_operation`，复核状态为 `provisional`。
4. 初始扫描不得直接将 Catalog Entry 标记为 `internal_operation`；这一结论必须具有实现、暴露和消费者证据，并经过人工批准。
5. 名称中包含 `read`、`search`、`change.apply` 等词不能单独决定分类，最终结论以真实契约和分派行为为准。

按 2026-08-14 Catalog 与飞书清单基线，第一轮得到：

- 总计：264。
- `service_facade` 候选：67。
- `service_operation` 候选：197。
- `internal_operation`：0；后续只能由治理发现和人工审批确认。

## 7. 人工复核规则

`needs_review` 条目必须核对：

- `operation/action` 是否只承担技术模式选择，还是确实分派不同业务动作。
- 不同分支是否拥有不同权限、确认、幂等、副作用、事务或错误语义。
- 是否有 UI、插件、Agent、MCP 或自动化直接依赖父 Facade。
- 是否能够在不破坏现有消费者的前提下新增原子 Capability。
- 是否需要设置兼容窗口、迁移提示和退役条件。

复核状态采用：

- `provisional`：机器初判，尚未人工确认。
- `needs_review`：存在 Facade 或其他歧义，必须人工审查。
- `confirmed`：领域负责人已确认分类与证据。
- `migration_planned`：已确认需要拆分或退役，并已有迁移方案。
- `legacy_frozen`：兼容入口冻结，只允许缺陷修复，不再增加新 Operation。

## 8. 迁移原则

- 不修改现有 264 个 Capability ID 和 Major。
- 第一阶段只增加 `semantic_kind`、`review_status`、依据和关系。
- 新能力默认必须是 `service_operation`；新增 Facade 需要明确兼容理由和平台批准。
- 现有 Facade 不立即删除。先新增原子 Capability，再迁移消费者，最后根据真实消费证据决定退役。
- Facade 中新发现的实际操作如果需要独立授权、版本、审计、测试或生命周期，必须升格为 Capability。
- 仅属于实现细节的步骤登记为 Handler 内部关系，不进入公开 Catalog。
- 新增业务编排优先建立 Application Use Case，再由流程 Task 引用；禁止让流程长期直接堆叠大量低层 Capability。

## 9. 治理与发布门禁

后续治理扫描必须增加：

- Catalog Entry 缺失 `semantic_kind` 时阻断新版本发布。
- `service_operation` 出现开放式操作分派字段时生成冲突 Finding。
- `service_facade` 新增分派值时视为行为变更，并要求消费者影响分析。
- 新增 `service_facade` 默认阻断，除非存在有期限的兼容豁免。
- `internal_operation` 出现在公开 Catalog 或外部暴露时生成冲突 Finding。
- Facade 拆分前后必须验证权限、副作用、事务、幂等、审计和消费者映射不丢失。
- Capability 缺少 `business_effect`、效果包含实现术语或描述多个独立动作时生成待审 Finding。
- Application Use Case 必须引用已批准的 Capability Major，并声明成功条件、失败语义和补偿策略。

## 10. 与现有治理设计的关系

现有 `CapabilityImplementationGraph` 保留，但语义调整为：

- `capability` 节点增加 `semantic_kind` 和 `review_status`。
- `capability` 节点增加 `business_effect`，并将它纳入 Catalog Release Hash 和变更审核。
- 增加 `application_use_case` 节点以及 `uses_capability`、`evaluates_rule`、`requests_judgment` 和 `realizes_activity` 关系。
- 原 `operation` 节点只表示 Facade 的受控分派分支或 Handler 内部操作，不再与 Capability 形成两个长期并列的可治理动作层。
- 增加 `service_contract` 节点和 `defines_operation`、`conforms_to_contract` 关系。
- `dispatches_operation` 只允许从 `service_facade` 指向受控分派分支。
- 需要独立治理的分派分支升格为 Capability 后，使用 `supersedes`、`compatible_with` 和消费者迁移关系连接旧入口。

## 11. 完成标准

- 飞书 264 条 Capability 清单全部具有初始分类和复核状态。
- 飞书 264 条 Capability 清单全部具有单一业务效果说明。
- 本地 Catalog 能稳定生成相同分类结果，且与飞书基线一致。
- 67 个 Facade 候选进入待审清单，不自动拆分。
- 现有调用、前端、插件、Agent 和跨域关系不因分类增加而改变。
- 后续新增或修改 Capability 时，分类校验成为正式变更与发布门禁的一部分。
