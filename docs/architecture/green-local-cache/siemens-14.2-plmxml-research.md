# Siemens 14.2：PLMXML、原生会话与仿真环境持久化调查

调查日期：2026-10-22。范围：用户指定的 Teamcenter Lifecycle Visualization 14.2 官方文档门户中，与保存、恢复、快照、分析结果、配置结构和跨机移交直接相关的章节；不是对整套手册的穷尽审查。

本次仅阅读文档和现有源代码；没有操作原生模型、修改保存偏好、重启 App/FCC、下载 JT 或验证真实保存往返。下面区分官方说明、代码事实和架构选择。当前安装版本、许可证和 COM 可调用性仍须实测。

## 1. 调查结论

PLMXML 应成为 AI00 场景持久化的重要原生载体，但不能把“一个 XML 文件”当成完整环境、跨机模型包或业务数据库。推荐组合为：**精确业务清单 + 原生场景文档 + 必要的派生文件引用**；模型字节继续优先由 TC/FCC 获取，明确长期归档时才复制。

14.2 帮助正文确认 PLMXML 支持扩展会话内容，比仅保存结构丰富得多。碰撞/间隙结果有独立文件依赖；多文档工作会话与可搬移压缩包又有各自格式。现有结构导出应保留，而不是全局改成最重的环境导出。

## 2. 来源与证据等级

以下均为 Siemens 一手来源。门户路径中部分实际正文资源位于 `tcv/14.1`，但本次读取的 HTML 页脚明确标注 **Teamcenter Lifecycle Visualization 14.2 / ©2022**；记录此现象，不自行改 URL 或据此推断安装版本。

| 编号 | 已阅读章节 | 关键用途 |
|---|---|---|
| S01 | [Session 与 PLMXML 的区别](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/genid_understanding_the_differences_between_session_files_and_files_60_1795) | 文档、模型、快照、扩展内容的定义 |
| S02 | [保存方式概览](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/genid_save_options_40_916) | Save As、Export、派生文档与会话 |
| S03 | [PLMXML 保存偏好](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/plmxml_p_plmxml_prefs) | 扩展内容、默认视图、插入模型、复制与引用 |
| S04 | [静态与配置结构](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/id1119088) | 冻结实际结构和按规则重解析的区别 |
| S05 | [Session 偏好](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/work_sessions_specify_session_preferences) | 合并窗口、动态引用、AppSession 互操作边界 |
| S06 | [快照可捕获内容](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.working_with_3D_models/Snapshots_module_c_snapshot) | 切面、位置、材质、显隐及其他状态 |
| S07 | [使用 PLMXML Product Views](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.working_with_3D_models/Snapshots_module_productviews) | 与兼容结构合并的轻量视图 |
| S08 | [将快照保存为 Product Views](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.working_with_3D_models/Snapshots_module_productviews_create) | 结构、视图、当前状态可分别选择 |
| S09 | [保存间隙结果列表](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.working_with_3D_models/xid1354584) | results.txt 依赖及不支持外部解析的限制 |
| S10 | [Session Package 概览](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/Export_module_session_package) | 压缩包及大小/文件数限制 |
| S11 | [保存 Session Package](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/Export_module_session_package_save_package) | 可选文件、静态结构、本地保存 |
| S12 | [导出活动模型为 PLMXML](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/plmxml_p_export_plmxml) | 层次结构/插入模型选择，文件名限制 |
| S13 | [另存活动文档为 PLMXML](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.managing_files/plmxml_p_save_plmxml) | 服务级别、保存偏好、部分加载视图 |
| S14 | [延迟加载 TC Product Views](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.visualization_integrations/xid1187313) | Abort / Ignore / LoadAll / Ask |
| S15 | [向 TC 保存 Product Views](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.visualization_integrations/id1359126) | SnapshotViewData 和允许/禁止的来源场景 |
| S16 | [PLM XML Document Guidelines PDF](https://docs.sw.siemens.com/en-US/doc/229029598/PL20220422633039925.pdf) | 结构、实例路径、矩阵、表示引用的补充说明 |

S16 虽挂在本门户，正文是 **Version 4.0、2012-12-13、©2013** 的补充指南（面向 Visualization 8 及以后）。它适合解释其明确列出的元素，不能作为 14.2 全部功能、Schema 全量支持或当前导出器行为的保证。优先采用上述 14.2 功能正文。

## 3. 格式和操作的分工

| 载体/操作 | 官方支持的用途 | AI00 应如何利用 | 不能据此推断 |
|---|---|---|---|
| JT | 模型几何及自身数据；结构引用可指向 JT（S16） | 几何字节复用 TC/FCC | 同一 JT 等于同一装配实例/配置/位置 |
| PLMXML 文档 | 结构及可选扩展会话内容（S01） | 场景版本的主要原生载体 | 文件存在就表示几何依赖可用、绑定有效 |
| 原生 Snapshot | 可选地捕获场景状态（S06） | 保存命名起始态/分析视图，恢复和比较 | 每次操作都必须重新捕获或完整导出 |
| 仅 Product View 的 PLMXML | 不含结构时必须合并到匹配结构（S07/S08） | 同一精确结构上的轻量视图增量 | 可以独立打开，或能随意套到新配置 |
| `.vf` | 二进制会话，可包含一个或多个文档（S01） | 多文档工作会话、必要的原生兼容回退 | 脱离原文件也一定可恢复 |
| `.vfz` | 可包含引用文件的压缩 Session Package（S10/S11） | 用户明确要求跨机移交/长期离线时采用 | 无大小限制，或应该每次自动生成 |
| Save As | 保存活动 3D 视窗中受支持内容（S02） | 明确保存环境的候选原生操作 | 可跨所有窗口/所有文档无选择全存 |
| Export | 可控制保存范围（S02/S12） | 区分结构投影、视图增量和完整环境档位 | 现有 Export 调用默认就是全内容 |

`.vf` 和 `.vfz` 的保留应由实际需求决定，不要求每个场景同时生成三份格式。原生快照、业务不可变快照、截图 PNG 是三个不同概念；界面与契约中不要混用同一个“snapshot”而不注明类型。

## 4. 快照、切面与分析结果

S06 的快照清单覆盖活动层次结构、相机、位置/旋转/缩放、显隐、材质、切面、测量标签、标注、坐标系、爆炸图和部分分析/显示状态；可用项受服务级别/可选模块影响。它不是当前安装许可证清单。

应逐项保存并重开核对：平面位置/方向与启用态、材质与透明度、各集合实例位置和显隐、相机、活动备选层次结构。重开后测量标签出现，不代表其数值对新模型仍有效；S06 对恢复后的非关联/未更新测量有过期提示说明。

**碰撞/间隙结果是独立依赖**：S09 说明 `.vf` 及开启扩展内容的 PLMXML 保存 `results.txt` 的引用；未保存结果会要求先保存该文件。因此场景依赖清单必须包含它。官方明确该文本格式面向 VisMockup，自定义外部解析不受支持：AI00 可保留文件、指纹、来源和原生重载能力，不把解析它作为正式业务结果接口。

碰撞检测开关/输入范围/容差/结果列表/报告/问题状态分别建模。文档证明“可保存结果引用”，没有证明所有算法输入、运行中状态、结果及问题业务都完整内嵌在 PLMXML；这些项进入原生往返验证，不作推定。

## 5. 保存偏好决定是否真的“保存环境”

S03 的关键选项及选择原则：

| 原生选项 | 调查后的设计选择 |
|---|---|
| Save extended 3D content into PLM XML | 环境档位需要；结构投影档位不需要 |
| Save the default snapshot | 环境恢复需要验证当前状态是否被完整记录；不存可缩短保存时间和文件大小，但不能同时声称已保存当前显示状态 |
| Save inserted models | 同文档多集合环境必须明确覆盖所选插入模型，不能只存原始根 |
| Copy parts locally | 普通保存关闭；跨机/离线归档另立用户动作，不默默复制整套 JT |
| Retain references to original Product Structure | 明确引用关系，不把此选项等同于静态冻结或离线归档 |
| Include late loaded attributes | 可能额外获取未读取 TC 属性；结构投影和截图热路径不默认开启，必需属性在环境准备中按范围处理 |

另有 Product View 延迟加载，与属性延迟加载不同。S14：Ignore 会丢弃部分加载视图；LoadAll 可能增加准备/保存耗时；Abort 明确终止；Ask 会弹窗。环境保存必须事先报告所选视图是否就绪与策略，不隐式忽略后宣称完整，也不为免弹窗全局修改用户 TC 偏好。

若 API 需要临时修改应用级偏好，必须串行、保存原值并在失败/取消后恢复；它不一定只影响当前文档。未确认作用域前，不能认为不同文档可以无冲突并行保存。

## 6. TG0/TG1：规则保存不等于结构冻结

S04 区分配置结构和静态结构。动态结构按版本规则、有效性、变量规则、装配安排等形成；Session 保存配置条件后，再开可能动态解析。`Capture Static Structure` 另存实际结构，并存在静态/配置重开选择。

因此分两种用户意图：

1. **继续工作/跟随配置**：保存规则和场景来源，允许用户明确刷新；刷新形成新快照/修订，不能替换旧冻结引用。
2. **冻结 TG0/TG1/审计比较**：固定实际解析实例/表示/位置、选静态恢复，保持业务快照、绑定方案和文件身份；不能因为规则含日期或保存了 `.vf` 就认定永远可复现。

静态结构仍可能引用外部 JT 或 TC 文件。TC 历史文件不可再获取且未明确归档时，结构可读与几何可恢复应显示为两个状态。打开冻结文件不得回退到同名最新文件。

## 7. 结构映射和备选层次结构

S16 第4–7页有可用的低层语义：产品定义、实例图、表示引用、Product View 和实例路径分开；实例图里的 Transform 相对父，Product View 下 Occurrence 的 Transform 解释为全局位置。表示可引用相对路径、绝对路径、URL 或需 VVI 协助解析的 PDM 位置。

这支持我们的“文件≠实例≠位置≠配置”设计，但旧指南不保证当前导出器保留稳定业务 ID。XML `id`、原生 node key、树位置不得直接成为永久云端绑定主键；往返重建运行映射时使用精确快照/集合/来源实例证据，歧义必须显式报告。

原生备选树可以作为用户操作和环境内容保存；正式 BOP 语义绑定仍通过 craft 权威事务+outbox 回传云端。PLMXML 中出现同名工序、UserData 或树父子关系，都不自动等于已提交的工艺绑定；导入只产生带来源的草稿/候选。

## 8. 跨机与 TC 回存边界

S10 记载 Session Package 一般上限4GB，含 JT9.x 时有约2.1GB的限制，64位系统约64,000文件；实际还受系统影响。实施前按实际 JT/产品版本验证，不承诺整车都能打成一个包。包内排除文档会减少可恢复范围；S11 的显式选取要进入 manifest。

S15 的 TC Product View 可保存为 SnapshotViewData dataset，但有重要限制，例如本地装配、TC 的 PLMXML来源、动态装配插入无关装配等情形不能创建该类 Product View。**TG0/TG1 混合比较文档不能默认走这一条回存 TC 的路。** AI00 云端保存场景文件与业务清单是独立受治理流程，不冒充 TC 原生 Product View 更新。

## 9. 当前代码与差距

已只读检查后端 `local-runtime/src/Ai00.Connector.Adapters.VisMockup/IVisMockupCom.cs` 中 `VisMockupPlmxmlExport.Run`：

- 当前接口是 `ExportPlmxml(path, hierarchyIndex)`。
- 临时设置 SaveExtendedInPlmxml=0、CopyParts=0、RetainReferences=1、SaveInsertedAssemblies=0、ForceRetainReferences=1、SaveLateLoadedProperties=0，调用既有 export，再 finally 恢复偏好。
- 这证明现有路径有意输出精简结构，不能作为完整环境保存的完成证据；不猜测 `export(2, …)` 的枚举含义或直接翻转全部开关。

另查现有 `plugins/simulation/simulation_backend/capabilities/plmxml_environments.py` 已有受治理的环境导入/导出与Artifact边界，`environment_documents.py` 已有主/补充文档和portability记录，应扩展复用。`domain/plmxml_environment_codec.py` 的运行模型只表达 documents/hierarchies/placements 等投影，导出重新生成 XML，报告明确 `original_artifact_passthrough_eligible=False`；它不表达完整切面/相机/分析状态。因此不能让原生完整文件先经该投影再重建，之后仍宣称无损。原生原件应按字节保留，结构/业务投影另存并记录覆盖范围。

应保留此模式的兼容行为，新增经安装接口验证的独立场景保存路径。默认快照选择、插入集合范围、结果依赖、静态恢复、错误弹窗及 API 支持仍未被现有接口表达。

## 10. 建议落地的五个用例

1. **重连优先**：App 重启先找精确活文档，generation/身份一致就接回，不为业务恢复先关闭文档、重载 JT。
2. **恢复保存场景**：原生文档已丢失才用保存的 PLMXML/必要 VF恢复；复用可用 FCC引用，重新建立运行句柄映射，复用业务绑定。
3. **截图起始态/重置**：每条线固定快照/范围；一次准备起始显隐和材质，运行只做必要改变。具名快照能否完整重置须测试；不为每道工序保存完整环境文件。
4. **TG0/TG1比较**：两个静态快照，集合命名空间隔离；场景保存含两套模型和对齐状态，不能用一个 Product View 猜测兼容替换。
5. **显式跨机移交**：用户选择范围、容量和保留策略后生成原生包/受控依赖包；保存验证后报告哪些依赖齐全。默认日常保存不会复制 FCC 整库。

预期收益是减少重复结构遍历、逐节点恢复和无必要重开；**PLMXML 本身不会消除 JT 解析、磁盘/网络读取、显卡载入和原生界面阻塞**。性能必须分别量原生热态重连、场景冷恢复、依赖获取、句柄映射和截图循环。

## 11. 必须先做的实机验证

在隔离测试模型/独立副本上验证，不能拿当前演示或他人文档试写：

- 双集合（含相同零件/同一快照插入两次）、位姿、显隐、材质、当前相机、命名切面、标注、活动备选树保存后重开逐项比对。
- `.plmxml` / 必要 `.vf` / 显式 `.vfz` 各记录所需依赖、字节增长、保存/重开时间，不以文件生成成功代替可恢复。
- 结果文本缺失、移动目录、FCC淘汰、TC离线、同名新版本出现，必须准确标 missing/partial，不替换来源。
- 当前状态 Product View 自动应用是否改变工作场景、是否能恢复选中/材质，重建后业务绑定保持但旧句柄被拒绝。
- Save As 与 Export 的实际 COM 接口/枚举/许可证、原生模态窗口、应用级偏好锁及 finally 恢复。
- 产品视图的部分加载策略、插入模型范围、未保存派生结果；TC Product View回存禁用条件。
- 上传依赖包成功但提交业务清单失败、重复请求、同步期间源文档发生变化时，不发布混合版本。

调查结果已转为 [专题规格10](../../superpowers/specs/2026-10-22-green-local-cache-architecture/10-plmxml-environment-persistence.md) 和 [实施子计划09](../../superpowers/plans/2026-10-22-green-local-cache-architecture/09-plmxml-persistence-and-roundtrip.md)。这些是待实施设计，不是已完成的原生验证。
