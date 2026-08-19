# Capability Governance Center 验收记录

日期：2026-08-19  
环境：`AI00_DEPLOYMENT_PROFILE=test-governance`，OceanBase 测试库，后端端口 `127.0.0.1:8094`

## 已完成

- 新增并注册只读治理能力：
  - `base.capability_proposal.search@1`
  - `base.capability_health.get@1`
  - `base.capability_audit.search@1`
- 能力清单、Finding、变更评审、健康、发布闸门、审计六个页面均有真实加载路径；依赖不可用时保留上次成功数据并显示错误码。
- 发布闸门继续使用服务端固定证据，调用方不能用自带 Finding/审批/哈希伪造通过。
- 治理中心前端加入筛选清除、请求代次保护、重复点击抑制、脱敏审计和 `select/change` 事件处理。
- 测试治理构建已同步到后端 `dist/web/admin/capability_governance`。

## 证据

```text
Frontend: node web/tests/run_tests.js
Result: ✅ 全部通过 130/130

Backend governance focused suite:
python -m pytest backend/tests/test_capability_governance_catalog.py \
  backend/tests/test_capability_governance_provider.py \
  backend/tests/test_capability_governance_service_workflow.py \
  backend/tests/test_capability_governance_store.py \
  backend/tests/test_capability_governance_workflow.py \
  backend/tests/test_capability_governance_permissions.py \
  backend/tests/test_capability_governance_execution_ports.py \
  backend/tests/test_frontend_deployment_check.py -q -p no:cacheprovider
Result: 54 passed

HTTP deployment:
python backend/scripts/check_frontend_deployment.py --base-url http://127.0.0.1:8094
Result: passed; health/ready/root/settings/governance HTML、model、API、controller、controller_next、CSS 均 HTTP 200
```

真实测试库直连验证：

- Snapshot：`215674262172897281`
- Registry：返回 200 条（受上限约束）
- Findings：返回 200 条（受上限约束）
- 健康查询已按领域返回状态、能力数和 Finding 数。

## 需要管理员完成的最后一步

当前登录账户没有停止 Windows 服务的权限，因此本次会话无法重启正在运行的 `AI00Backend-CapabilityV2` 进程。代码和静态文件已部署到工作树，但新增后端能力要等服务重启后才会进入进程内注册表。

请在管理员 PowerShell 执行：

```powershell
Restart-Service AI00Backend-CapabilityV2
Invoke-RestMethod http://127.0.0.1:8094/health
python E:\Projects\ai00_v3\.worktrees\capability-v2-implementation\backend\scripts\check_frontend_deployment.py --base-url http://127.0.0.1:8094
```

预期：健康返回 `status=ok`，部署检查返回 `status=passed`。重启后进入治理中心切换到“测试与健康”“变更与评审”“审计”，分别确认页面显示真实结果或明确的依赖不可用状态；不得把依赖不可用显示为健康或发布通过。
