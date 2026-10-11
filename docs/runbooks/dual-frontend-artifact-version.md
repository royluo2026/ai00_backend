# 双前端发布版本与产物只读校验

当前集成后端的 `backend/VERSION` 定义后端版本；Browser 和 Desktop 各自产物内的 `frontend-version.json` 定义对应前端版本。整体版本只有环境专属的 `release-manifest.json` 能声明，不能由安装包、API 文档版本或当前源码推断。

FastAPI/OpenAPI 的 `info.version` 也从同一个有界、普通文件 `backend/VERSION` 读取；缺失或格式无效时仅显示 `unmarked`，不再硬编码 `1.0.0` 或从整体清单猜测后端版本。独立 `/api/system/version` 仍以 `backendVersion: null` 表达无效源版本，并只有清单与当前 profile/双前端版本闭合时才声明整体版本。OpenAPI 元数据是源码版本提示，不是可发布产物、运行后端或人审证据。

在受控发布候选完成、仍未部署或切换流量时，对**同一次构建**的三个展开目录运行组合预检：

```powershell
python -B -m backend.scripts.check_deployment_candidate --env-file <受控ENV_FILE> --manifest <受审清单路径> --environment test|production --browser-artifact <Browser展开目录> --desktop-artifact <Desktop-renderer展开目录> --backend-artifact <后端展开目录>
```

组合预检先检查 ENV_FILE 的显式 profile、前缀、域账号与 OAuth 等纯配置，再确认参数环境一致，核对清单环境、三端版本、固定后端地址、资源清单与产物字节哈希；随后**对同一后端展开产物**只读扫描源码权属，复核产物内 `backend/governance/{domain_boundaries,domain_table_ownership,table_inventory,boundary_baseline}.json` 和 `docs/governance/capability-coverage-review/manifest.json` 及审查处置文件，拒绝缺失、未归属、库存漂移、新违规或缺少唯一处置的违规。审计后重新核对后端产物哈希与清单，源文件变更即拒绝。四工况组合入口和候选暂存复用此门；只运行单独 `backend.scripts.verify_release_artifacts` **不包含**源码权属审计，不得据此宣称组合候选通过。任一目录内有 `release-blocked.json`、旧后端 Web dist、环境文件或缺少必需域源码即拒绝。不能传源码目录替代最终产物，不能把拒发骨架的标记删掉后冒充发布候选；产物哈希不包含清单本身，应在冻结产物后计算并由发布 Owner 审核清单来源。产物内处置文件的静态存在不证明处置由可信人工批准；校验成功不意味着已签名安装包、运行 Registry/账号权限、`test_`/`pp_` 实库隔离或人工批准。当前集成树仍缺受控合并/发布流水线，不得仅凭此命令解除部署拒发。

审计规则与权属输入**不能由候选产物自行声明**：上述四份治理 JSON 和 `docs/governance/capability-coverage-review` 顶层全部审查 JSON 必须与运行检查器的受控后端源码树逐字节一致；`generated/` 等非审查子目录不参与处置 ID 读取。源码扫描使用检查器的 Registry/权属/审查快照，只扫描被提交的后端产物，检查前后复核一致性。检查器及其治理快照也须由发布 Owner 冻结、复核来源；本机未提交工作树不是已签核发布政策。合法治理更新应先经对应领域 Owner 审查并同步到受控检查器和候选构建，再计算产物哈希，不要靠放宽检查或让候选附带自审文件绕过。

组合候选门还要求后端产物内的 `backend/capability_v2/official_domains.json` 与检查器受控副本逐字节一致，并对**该候选产物**逐域重算 Provider artifact hash；任一目录缺失、路径异常或冻结哈希不符即拒绝，不从候选自行重算并回写 manifest。四工况及暂存入口复用同一门。`verify_release_artifacts` 单独产物检查不执行此 Provider 审计；即使组合候选通过，也不代替在线 Registry/Descriptor、消费者审核或人审签核。

候选产物通过只读门禁后，可在**尚未部署**的本机隔离目录暂存后端展开产物与经校验的清单。输出路径必须全新、不得位于 Browser/Desktop/后端任一源产物目录内，且上级是实际目录；程序先复制到同级随机 `.incomplete-*` 目录，重新核对后端产物 SHA-256，再将原始清单放到默认运行路径 `release-manifest.json`（与 `backend/VERSION` 同根），确认运行时三版本解析后才重命名为目标目录：

```powershell
python -B -m backend.scripts.stage_backend_candidate --env-file <受控ENV_FILE> --manifest <受审清单路径> --environment test|production --browser-artifact <Browser展开目录> --desktop-artifact <Desktop-renderer展开目录> --backend-artifact <后端展开目录> --output <全新的隔离后端候选目录>
```

清单是后端产物哈希之外的同根 sidecar，不能放入被哈希的后端源目录形成自引用。复制中源文件漂移或清单变化会拒绝目标目录晋升；失败时 `.incomplete-*` 保留供人工取证，不自动删除。此工具**不复制 ENV_FILE**，也不部署、签名、启动服务或取得发布批准；实际发布流程仍须由发布 Owner 审核目的目录、清单传输、源/目标字节、环境隔离与回退。旧 `scripts/deploy.bat` 保持拒发。

产物校验还要求 Browser 的首页/分享详情和 Desktop 的主窗/关于/设置各有且仅有一个 `app-version` meta，精确匹配该端产物内的版本 JSON；仅改清单哈希或 JSON 无法把过时页面重新标为新版本。两个客户端的版本号可以不同，不从后端版本或安装包版本自动推断。

运行时只读版本接口和候选产物校验共用拒绝重复 JSON 对象键的清单解析；整体及双前端版本字段须是精确版本字符串，不接受前后空白。`backend/VERSION` 可以保留文件末尾换行。重复键、错配或未通过的清单不能声明整体版本，不能因为接口报告后端源码版本就推断整体版本已发布。跨 test/production 的只读组合检查命令及 共享账号的单库、不同表前缀配置配对边界见 `docs/startup.md`；它不替代真实服务、签名包和人审。
