# 01 身份、所有权、版本与一致性

状态：设计草案。实体为逻辑设计，现有对象能承担时优先复用；物理表名、Catalog 身份及 GID 待真实归属调查，不在本文虚构。

## 1. 权威边界

| 所有者 | 管理事实 | 消费原则 |
|---|---|---|
| TC | 工程版本、配置规则、解析结构、实例及几何来源 | 经真实登录与受支持服务解析 |
| craft | BOP、工位／工序／操作／需求、语义关系、正式工艺绑定及附件 | 其他域使用公开契约，不直接写 craft 表 |
| simulation | 场景、模型集合、配置快照引用、绑定草稿／适配工作场景、执行及比较 | placement 不等于正式工艺绑定，不另造可写 BOP 主库 |
| digital_model | 模型身份、不可变模型版本／实例端点、正式关联反向查询投影 | 不独立编辑 craft 权威绑定，不用原生节点号充当端点 |
| knowledge／规则归属域 | 标准工序、知识、规则、引用和检查定义 | 版本引用与检查结果分开 |
| project／基线协调所有者 | 项目阶段关联与跨域基线清单，所有者待确认 | 固定各域不可变引用，不吞并域对象 |
| 桌面 Main／Connector | 本机 SQLite、原生会话、调度、输出暂存 | Renderer 不指定任意磁盘路径或伪造 actor |

冻结协调所有者未确认前不创建跨域写表服务。只读 BFF 可以聚合显示，不能借 BFF 绕过事务和所有权。

## 2. 精确身份与版本向量

每个云端身份至少带租户／资源范围。TC 引用至少带 `source_system_id`；不同 TC 的相同 UID 不合并。

`ConfigurationSpec`：根对象与精确 revision、BOM View、规则 UID、可得规则内容摘要、变量规则列表及作用域、日期／单位有效性、配置上下文、布局、解析器／规范化版本。列表是否有序按 TC 真实语义处理，不擅自排序变量覆盖规则。

`ModelSnapshot`：不可变解析结果、配置条件、开始／完成时间、来源变更证据、完整性、缺失清单、结构内容摘要。`latest` 不是身份，规则名不是版本。

`OccurrenceRef`：`snapshot_id + occurrence_key`。键以可信根路径／上下文表达重复子装配；末级 occurrence UID、零件号、CAD ID 不保证全局唯一。

`RepresentationRef`：来源系统、工程 revision UID、dataset／named-reference／file UID、原生文件 GUID（若可取得）、格式／精度／单位元数据。file UID 与 FMS GUID 不假定相同；映射由受支持证据建立。内容哈希是可选的独立属性，不把 dependency-key 冒充内容 SHA。

`ModelSetRef`：`workspace_revision_id + model_set_id + model_snapshot_id`，同一快照可以在文档中插入两次并有独立放置。

`NativeRef`：设备、进程 PID＋启动身份、原生文档、模型集合、文档生成号、节点句柄。只在该会话有效，不直接存入长期绑定。

`ProcessRef`：BOP 来源身份＋固定业务对象身份＋相关内容版本。流程图节点引用它，GBOP 标准定义另行引用。

`ProcessRevisionRef`：固定技术修订身份与内容摘要。业务发布标签另行指向不可变修订；用户未手动升版也不能改变旧快照。已发布 A版不接受原地编辑，后续显示为“基于 A版的未发布草稿”。

`BindingSchemeRef`：绑定方案身份＋方案修订，固定精确工艺快照和一个或多个明确的模型／资源目标配置。允许同一工艺快照有多份方案；同一方案可以有多条零件／资源关系，不能以 BOP ID 作为方案唯一键。

工作场景版本向量建议包含 `bop_structure_revision / process_content_revision / diagram_view_revision / model_snapshot_id / binding_revision / scene_revision`。实施可映射现有粗版本，但不能只用一个 `updated_at` 同时表达全部语义。

## 3. 逻辑实体与约束

| 实体 | 关键字段 | 必须约束 |
|---|---|---|
| configuration_spec | 来源、规则／变量、上下文、规范版本 | 序列化可规范化，日期有明确时区和语义 |
| model_snapshot | spec、内容摘要、完整性、证据 | 完成后不可变，生成过程失败不变成完成 |
| model_occurrence | snapshot、key、parent、order、revision、representation、transform | 同 snapshot 内 key 唯一，父存在且无环 |
| representation_ref | 文件身份及可得内容证明 | 不按名称去重；同文件跨配置引用不复制 |
| simulation_workspace_revision | parent、version vector、状态、差异 | CAS 提交，不覆盖 parent |
| simulation_bop_ref | source、pinned version、working-copy identity | 插入引用与源最新版本分开 |
| simulation_model_set | snapshot、角色、场景放置 | 集合级命名空间，放置不改来源位置 |
| process_technical_revision | parent、内容摘要、有效变更集、actor、事务版本 | 有效内容提交自动产生；重复请求／无变化不重复升修订 |
| process_release_ref | 业务版本标签、固定 technical revision、发布状态 | 发布后不可原地覆盖，不以标签作身份 |
| binding_scheme_revision | 工艺技术快照、目标配置集合、方案版本与状态 | 同一工艺可有多方案；执行显式选择 |
| binding_revision | 方案、process requirement、typed model/resource target、角色、证据 | 正式端点完整且可验证；unresolved 仅在草稿，保留人工选择 |
| baseline_manifest | label、parent、各域固定引用、封存摘要 | 标签不是身份，冻结不可变 |
| result_dependency | run、工序、配置、绑定、需求和策略摘要 | 可判断适用范围，不因无关布局变更失效 |

位置记录区分来源 local-to-parent、派生 world、场景移动、比较对齐；带矩阵约定、单位、父坐标系和来源。world 计算为可重建投影，不作为另一份可自由编辑来源位置。缺失变换不能偷偷补 identity 冒充精确位置。

## 4. 提交一致性

AI00 单域事务内：校验 expected revision、执行变更、增加受影响 revision、记录变更序号及审计，原子提交。附件更新只更新对应关联，不覆盖整份 BOP。

工艺有效保存自动产生技术修订，布局另记视图修订；发布标签、技术内容、绑定方案分别版本化。正式工艺绑定由 craft 事务同时保存关系版本与可靠发件记录，数字模型反向投影幂等消费，详情见 [08](08-alternate-hierarchy-binding-and-cloud-sync.md) 和 [09](09-process-auto-revision-and-multi-model-binding.md)。

跨域协调：使用固定不可变引用和幂等准备凭据，在提交前检查依赖仍有效；不用浏览器拿到的几份 `latest` 拼出“完整基线”。不能跨域直连数据库来模拟原子提交。

TC：优先使用配置上下文／BOM 窗口固定并记录可得一致性证据。若无法证明解析一致，标记 `consistency_unverified`，不得声称审计级可重现。解析日期不等于历史数据库事务快照。

## 5. 旧数据与孤儿

历史仅规则名称／空 BOM View 的数据标记 provenance incomplete；不补假 UID。删除使用域内保留策略／墓碑，历史基线仍引用已知对象版本。工作场景中未识别原生模型保留独立观察身份，不直接绑定到某个 TC revision。

## 6. 接口语义候选

这不是已注册 Capability ID：读取可访问配置、解析快照、创建工作场景版本、保存绑定版本、冻结清单、读取差异、发布工艺附件各自有独立业务效果和所有者。实施先搜索现有 Catalog 复用，不把这些函数一次塞入一个万能能力。

读返回 `identity + revision + completeness + data`；写消费 `expected_revision + idempotency_key + exact resource selectors`。actor／tenant 由服务端注入。错误至少区分依赖变化、引用不存在、来源不明、权限撤回、解析不完整和并发冲突，正式代码和 GID 由所属域评审登记。

## 7. 最小验收

- 同一 JT、同一零件、同一末级 UID 在两个模型集合中仍可准确定位。
- 配置相同名称但内容变化生成不同快照身份。
- 只移动卡片不改变绑定／几何依赖摘要。
- 原生 PID 或节点变化只使 NativeRef 过期，不删除 binding revision。
- 绑定端点缺失保持 unresolved，不能用最相似名称自动通过。
- 两域准备期间 BOP 改变，冻结不提交混合版本。
