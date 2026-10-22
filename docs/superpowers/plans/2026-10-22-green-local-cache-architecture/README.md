# 绿标工程场景与本地缓存架构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. 若用户明确选择逐任务子代理执行，再使用 superpowers:subagent-driven-development；本计划本身不授权自动创建子代理。Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在正式绿标实现可追溯工艺／产品关联、自动技术修订、多模型方案、外置原生协同、快速流程图、受控缓存与可恢复截图回填。

**Architecture:** craft 权威保存工艺修订、方案及正式绑定；digital_model 管模型身份和反向使用投影；simulation 管工作场景、模型集合、运行与比较。云端事实与本地投影分离，JT 复用受支持的 FCC 接口；原生目标精确且受本机调度约束。

**Tech Stack:** 现有 Python Capability/Gateway/Provider、MySQL 兼容数据库、Electron/Node、现有 SQLite worker、原生 C++ 窗口桥、.NET Connector/STA、Teamcenter SOA 与 VisMockup 官方接口；不引入通用消息平台或新前端框架。

**Spec:** [详细规格 v0.3](../../specs/2026-10-22-green-local-cache-architecture/README.md)，执行者先读全部相关专题；[完整指南](../../../architecture/green-local-cache/README.md)。

状态：实施计划草案 v0.2，G0及T01–T25均未执行。已补入Siemens 14.2文档调查；文档调查不是原生验证。本文不是实施完成、运行通过或生产审批的证明。

## Global Constraints

- Teamcenter 负责工程配置解析；AI00 不仿制版本／变量规则解释器。
- 在线业务事实由各云端业务域负责；SQLite 是本地工作集、恢复及待同步结果，不是第二个权威业务库。
- 普通 JT 文件采用 Siemens FCC 缓存，不按项目、版本、配置默认复制完整文件包。
- AI00 自有数模存储仅包含用户明确通过 App 保存、供长期使用的数模；普通打开不自动归入长期保留区。
- VisMockup 默认独立窗口，支持副屏，用户正常旋转、选择、插入、移动、切换文档；AI00 保留自动化控制。
- 所有自动化精确到进程、文档、模型集合及实例，不独占全部进程，不默默操作当前活动文档。
- TG0、TG1 等基线冻结后不可原地修改；同一原生文档可装入多个阶段的独立模型集合。
- 流程图缩略图持久缓存，原图按需在线读取，不建立长期原图缓存。待交付截图是可靠暂存结果，不能提前清理。
- 生产数据、配置、缓存不得用于开发试写；实施先在隔离测试环境及演示数据副本验证。
- 名称、临时编码、路径和原生节点号不能替代业务身份。
- 备选树 placement 不等于正式工艺绑定；正式语义关系只有一个权威写入者，数模域的反向索引不是第二份绑定主表。
- 业务版本名称不代替自动技术修订；每个有效工艺内容提交原子产生技术修订，已发布版本不可原地改变。
- 同一精确工艺快照可有多份数模适配方案；执行必须明确方案及版本，不能使用全局“最后一次绑定”。
- 已有工作集线体从点击到可操作 p95 ≤ 1 秒为目标；热态单工序原生到可靠落盘 p95 ≤ 5 秒为目标，上传回填另报；两者均待实测。
- 存储监控建议初始调度：空闲后首次、5 分钟周期、手动最短 30 秒；低空间建议初值 max(10 GiB, 卷容量 5%)。均经设备测量确认，不自动清理 FCC／长期模型／待交付结果。
- 所有业务写保留真实权限、版本、幂等、审计及契约治理；不从橘标迁入跳过校核特例。

原生环境原件、结构投影和业务绑定分别保管；完整环境不经过结构codec重建后冒充无损。普通保存不复制JT，冻结选择静态结构，保存/恢复不进入逐工序热路径。

## Review Focus

1. 同快照插入两次且 CAD ID 重复：T05/T09/T19 必须按集合定位，不误操作另一套模型。
2. 已发布 A版继续编辑但未点升版：T04/T06/T21 保留旧版且固定新草稿技术快照。
3. 提交／上传／回填已成功但响应丢失：T06/T07/T20 按稳定请求身份恢复，不生成重复关系或附件。
4. 原生变化事件漏报、PID/窗口复用：T09/T10/T11 检测会话／generation 失效，旧 fence 不继续执行。
5. 稀疏／硬链接／无权限＋待交付磁盘满：T15/T17/T20 返回部分／未知、准确背压、不以删文件兜底。

## 1. 仓库、恢复点与当前实现入口

实施文件标记 `B:` 表示后端，`F:` 表示前端；子计划使用仓库相对路径。不能把两仓库路径混用。当前目录为后端主本，前端同路径镜像。

- B：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-backend-20260905`；计划起点 `0b9ef6a2850780cdb4746dfad53a9da717ffc620`。
- F：`E:/Projects/ai00_v3/.worktrees/orchestration-merge-frontend-20260905`；计划起点 `9db39262caff17f4b545118512455866e5d9febd`。
- 改造前标签两仓库均为 `pre-local-cache-architecture-20261022`；不移动、不强推重写该标签。
- 先通过 managed worktree 流程建立实施隔离环境，或复用用户指定且已隔离的工作树；不要因文档里有当前路径就直接重启正在演示的绿标。
- 当前 craft 已有 node/binding revisions、space head/version、事务写和幂等账本；必须扩展复用，不另外建设第二套全量 BOP 版本库。
- 当前 simulation 已有 workspace、alternate hierarchy/placement、freeze、publish plan、cache 和 Connector；必须明确迁移边界，不删除旧任务解释器。
- 当前 digital_model 已有模型／版本／component 与公共端口；普通绑定变更不创建新的几何版本。
- 当前 Electron 已有可信 IPC、tree cache worker、状态栏入口；读取目录和 SQLite 继续由 Main/worker 控制。

## 2. G0 执行准备（所有产品代码前）

- [ ] 核实工作树干净程度、实际启动入口、分支和当前变更；保留其他任务改动，不 reset。
- [ ] 在实施工作树保存 `docs/superpowers/reports/2026-10-22-green-cache-contract-inventory.json`：列出现有 Catalog／Descriptor／Provider／消费者／表归属及真实版本身份。缺项记录，不生成假 GID。
- [ ] 区分传统 BOP 写入口与 managed BOP space 入口：列出所有能修改节点／需求／绑定的能力及网页、桌面调用方；为 T04 指定同一权威写入内核，保留兼容适配。
- [ ] 以真实运行配置和只读连接证明测试库及前缀；未证明前不执行迁移、业务写或原生副作用。
- [ ] 为新业务能力逐项记录业务效果、权限、事务、幂等、审计、Provider、消费者和兼容版本；读 BFF 不承担写。
- [ ] 新 schema 沿所属域的 schema compiler／受治理迁移路径构建和验证，不手写生产 SQL 试错。
- [ ] 建立脱敏的 native/TC 数据副本、故障注入样例和性能数据规模清单；运行票据、密钥、模型文件不进入 Git。
- [ ] 记录基线测试命令、结果和未覆盖项；当前文档检查不能视为原生验证。

G0 产物为事实清单与隔离环境，不发布新能力。测试环境或权威归属不明时，仅继续不受影响的纯单元测试／文档工作。

## 3. 子计划、依赖与交付

| 子计划 | 任务 | 必要依赖 | 可独立验收交付 |
|---|---|---|---|
| [01 原生验证门](01-native-and-source-probes.md) | T01–T02 | G0 | TC 配置、精确文档、事件和 FCC 的实证能力矩阵 |
| [02 身份与自动修订](02-identities-and-process-revisions.md) | T03–T05 | G0；配置持久化最终定型依赖 T01 | 自动技术修订、不可变发布、精确快照／集合 |
| [03 绑定与云端同步](03-bindings-and-cloud-sync.md) | T06–T08 | T03/T04/T05 | 树草稿→正式关系→数模反查→多端查询闭环 |
| [04 外置与双向协同](04-native-collaboration-and-leases.md) | T09–T11 | T02/T03/T05 | 原生自由使用、准确联动、变化与租约控制 |
| [05 流程图与媒体工作集](05-flowgraph-workset-and-thumbnails.md) | T12–T14 | T03/T04；绑定显示依赖 T07 | 缓存首屏、增量同步、缩略图、在线原图 |
| [06 存储监控与保留](06-storage-accounting-and-retention.md) | T15–T17 | G0；FCC 归属依据 T02 | 状态栏容量、可访问细项、显式长期模型保存 |
| [07 截图与交付](07-capture-and-delivery.md) | T18–T20 | T06/T08/T09/T11/T14/T17 | 固定计划、本地连续截图、幂等云端回填 |
| [08 基线、比较、迁移](08-baselines-comparison-and-rollout.md) | T21–T23 | 前述所消费接口；原生部分T24/T25 | TG0/TG1 联合比较及灰度／回退证据 |
| [09 PLMXML保存恢复](09-plmxml-persistence-and-roundtrip.md) | T24–T25 | T02/T03/T05/T09/T10/T11/T17 | 原生原件、依赖manifest、静态往返和优先重接 |

T24/T25必须在T21/T22原生环境部分之前完成；T21/T22的数据逻辑可先做。编号按专题分配，不代表执行先后；依赖无环：G0→验证/身份→绑定/协同/存储→保存恢复/截图→基线比较→T23。

首个可见交付优先 T15/T16 容量监控，不等待所有原生功能完成。身份和自动修订可与原生只读调查在逻辑上独立推进；本计划不授权自动并行创建任务／子代理。原生能力门失败仅阻止依赖它的实现，不能靠全量下载、关其他实例或弱化校核通过门。

## 4. 统一接口约定

Python 跨域引用由 `backend/domain_ports` 的闭合模型定义；新 DTO 字段见 T03。actor/tenant 从服务端 context 注入，不从 Renderer 采信。内部应用函数名不是 Capability ID，正式登记由 G0 清单和所属域评审决定。

Node Main 的只读本地接口无任意路径输入，返回带 scope、时间、水位和完整性的数据。C# 原生指令携带 DocSession 和 fence。所有任务使用同一字段名：`technical_revision_id`、`scheme_id`、`scheme_revision_id`、`model_snapshot_id`、`model_set_id`、`mutation_id`、`expected_revision`。

每任务先新增失败测试，运行看到预期失败，再最小实现，运行通过、相关边界回归，最后提交。每个任务独立提交，前后端跨仓成对记录 commit；不要等整次重构完成才首次提交。

## 5. 测试与部署命令约定

`B>` 表示后端工作目录；`F>` 表示前端工作目录。Python 单元测试用 `python -B -m pytest -p no:cacheprovider ... -q`，Node 用 `node --test ...`，原生用 `dotnet test local-runtime/tests/Ai00.Connector.Tests/Ai00.Connector.Tests.csproj --filter ...`。测试路径未存在时是待创建任务，不声称现在能通过。

测试替身只证明逻辑；MySQL 兼容事务、真实 TC／VisMockup、Windows 文件元数据、Electron IPC 和性能另有实测门。原生测试若需退出／重启共享程序，先依据当前授权和现场占用确认范围，不继承过去某轮的特定 PID 授权。

## 6. 规格覆盖表

| 规格 | 覆盖任务 |
|---|---|
| 01 身份与一致性 | G0、T03–T07、T21 |
| 02 流程图／媒体 | T04、T08、T12–T14、T20 |
| 03 TC/FCC／原生 | T01–T02、T05、T09–T11、T17 |
| 04 自动化交付 | T11、T18–T20 |
| 05 基线比较 | T05、T21–T23 |
| 06 存储监控 | T15–T17、T20 |
| 07 迁移治理 | G0、全部任务提交检查、T23 |
| 08 绑定回传 | T03、T06–T08、T18、T23 |
| 09 自动修订／多方案 | T04、T06、T08、T18、T21–T23 |
| 10 原生环境保存 | T02、T17、T24–T25、T21–T23 |

最终联合验收必须覆盖规格 AC01–AC18、AB01–AB08、PR01–PR08、PE01–PE08；子计划指定具体负责测试。原生真实支持和所属域契约审批是实施门，不用“全部通过”掩盖未验证。

## 7. 发布与回退

按能力／场景／设备分阶段开关，新旧任务按原契约完成；新消费者默认关闭直至对应测试和治理满足。保留新增 schema 和可靠结果，回退不破坏性降库、不删除原图、不移动基线标签。

发布前核对域契约、closed schema、签名 Provider 和真实 Registry；仅实现测试通过不能替代发布门禁。设计／文档分支不自动部署。计划完成后由用户评审并选择执行方式，再进入产品实现。
