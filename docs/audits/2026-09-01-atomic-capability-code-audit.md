# Capability V2 原子業務能力治理審計（代碼級，第四輪）

- **審計日期：** 2026-09-01
- **審計類型：** 代碼級復核（靜態門禁 + 提供者加載 + 路由合約 + CODEOWNERS + Catalog 字段）
- **規範版本：** 《原子業務能力開發治理規範 V2.1》（`docs/governance/atomic-capability-spec-v2.md`）
- **結論：** **不可發佈（BLOCKED）— 三項新回歸**
- **後端基線：** `E:\Projects\ai00_v3\.worktrees\capability-v2-implementation`，`test [ahead 127]`，`5c748db7a730f35be2f612dd772617232fc63ae7`
- **前端基線：** `E:\Projects\ai00\workmanship-web`，`test`
- **對比上輪：** 2026-08-26 審計靜態門禁通過；本輪 55 個新提交後出現 3 項新 Blocking 回歸。

---

## 1. 靜態門禁驗證（2026-09-01）

| 檢查項 | 結果 | 說明 |
|---|---|---|
| Provider manifest 凍結 | ✅ **通過** | `sha256:ba5483b5…` |
| Catalog release | ❌ **失敗** | `provider_load_failed: integration` — integration 提供者無法加載 |
| 領域所有權/CODEOWNERS | ❌ **失敗** | 4 個 base 遷移文件缺少 CODEOWNERS 條目 |
| 跨域 import | ✅ **通過**（有 1 個基線已接受違規） | 1 reviewed violation（`project_management/tests` 導入 `backend.capabilities.registry_next`，已記錄在 `domain-dependency-baseline.json`），無新增 |
| Release Gate（完整 web root） | ❌ **異常退出** | `RouteScanConfigurationError: wrapper contract source hash is stale: packages/craft-plugin/web/approval/approval.js` |
| Catalog audit | ✅ **通過** | stable=479，required_fields 全零缺失，atomicity.passed=true |
| 聚焦測試（15 個文件） | ❌ **4 failed，11 passed** | 上輪 20 passed，本輪出現 4 個新失敗 |

---

## 2. 三項新 Blocking 回歸（代碼根因）

### B-NEW-1：Integration Provider `provider_load_failed` — 引入強制環境變量后破壞 Bootstrap（**Blocking**）

**根因：** `plugins/integration/integration_backend/capabilities/wiring.py:48` 新增強制要求：

```python
def _configured_factory() -> AdapterFactory:
    target = os.getenv("AI00_INTEGRATION_ADAPTER_FACTORY", "").strip()
    if not target:
        raise RuntimeError(
            "AI00_INTEGRATION_ADAPTER_FACTORY is required to wire the Integration vault, "
            "immutable Catalog, and bounded connector runtime"
        )
```

**影響：** 在未設置 `AI00_INTEGRATION_ADAPTER_FACTORY` 的靜態審計、CI、測試環境中，integration 提供者在加載時拋出 `RuntimeError`，被 `provider_loader.py:88` 包裝為 `ProviderTrustError: provider_load_failed: integration`，導致整個 Registry 無法構建。

**受影響的測試（4 個，均為上輪通過）：**
- `backend/tests/test_capability_bootstrap.py::test_bootstrap_builds_one_complete_registry`
- `backend/tests/test_capability_provider_loading.py::test_official_domain_providers_load_without_kernel_importing_domains`
- `backend/tests/test_capability_provider_loading.py::test_third_party_manifest_cannot_load_backend_provider`
- `backend/tests/test_capability_provider_loading.py::test_discovered_official_backend_cannot_bypass_central_manifest`

**注意：** integration 自身測試（`plugins/integration/tests/`）通過 `monkeypatch.setenv("AI00_INTEGRATION_ADAPTER_FACTORY", "integration_test_adapter_factory:build")` 設置測試用 adapter，因此 integration 自身測試不受影響。問題在於 bootstrap 測試期望所有 11 個提供者無需特殊環境變量即可加載。

**最小整改方向：** 以下任一方案：
1. 在 integration provider 的 `register_capabilities()` 入口增加"無 adapter 時跳過/降級"邏輯（讀取 env var 只在 handle 時而非加載時）
2. 在 bootstrap 測試的 conftest 中設置 `AI00_INTEGRATION_ADAPTER_FACTORY` 為測試 stub
3. 在 `ProviderLoader` 層加入"缺少必要 env 時記錄警告而非拋異常"的可配置模式

**複驗條件：** `python -m pytest backend/tests/test_capability_bootstrap.py backend/tests/test_capability_provider_loading.py -q` 全部通過，無 `provider_load_failed`。

---

### B-NEW-2：Web 路由包裝合約 Hash 過期，Release Gate 異常退出（**Blocking**）

**根因：** `docs/governance/web-api-wrapper-contracts.json` 中存儲的 `approval.js` 源文件 hash 已過期：

```
存儲 sha256: d2975a2db6081d2c1bc40dc4d9ffc750463c6ce002a8a2820b4517af52a669f1
當前 sha256: 04495deeced75c275da108fc797af937d194541b597c6186d52faa6d82cf7539
文件路徑: packages/craft-plugin/web/approval/approval.js
```

`backend/capability_v2/consumer_routes.py` 的 `WrapperContract` 系統在掃描前驗證源文件 hash，hash 不匹配時拋出 `RouteScanConfigurationError`，導致 `evaluate_release_gate()` 無法完成。

**影響：** Release Gate 整個 web 掃描階段無法執行，既無法確認零 legacy 路由，也無法生成 `web_route_inventory_drift` 比較。從代碼邏輯看，上輪靜態門禁通過的前提（`web_consumer_bypasses: 0`）本輪無法驗證。

**最小整改方向：** 重新生成 `web-api-wrapper-contracts.json`（運行負責刷新此文件的腳本），或手動更新 `approval.js` 對應條目的 `source_sha256` 為當前值 `04495dee…`。

**複驗條件：** `evaluate_release_gate(web_root=全前端根目錄)` 不再拋 `RouteScanConfigurationError`，並返回完整 `passed` 結果。

---

### B-NEW-3：4 個 Base 遷移文件缺少 CODEOWNERS（**Blocking**）

**根因：** 4 個近期新增的 base domain SQL 遷移文件未在 `.github/CODEOWNERS` 中添加對應條目：

```
backend/db/migrations/202608280001_base_saved_view_governance.sql
backend/db/migrations/202608280002_base_self_annotation_governance.sql
backend/db/migrations/202608280003_base_plugin_lifecycle_governance.sql
backend/db/migrations/202608280004_base_plugin_lifecycle_idempotency_scope.sql
```

CODEOWNERS 中已有早期同前綴遷移文件（如 `202608040002_base_plugin_usage_metrics.sql @ai00/base-maintainers`）的條目，但 `202608280001-4` 的四個文件未被覆蓋。

**影響：** `check_domain_change_governance.py --check` 失敗，領域所有權門禁不通過。

**最小整改方向：** 在 `.github/CODEOWNERS` 中為這 4 個文件各添加 `@ai00/base-maintainers` 條目；或使用通配符 `/backend/db/migrations/202608*_base_*.sql @ai00/base-maintainers` 統一覆蓋。

**複驗條件：** `check_domain_change_governance.py --check --frontend-root <frontend>` 輸出 `Domain change governance check passed`，無 missing CODEOWNERS 警告。

---

## 3. 持續存在的非 Gate 問題（P1，上輪已知）

| Finding | 狀態 | 說明 |
|---|---|---|
| consumer_refs 391/479 為空 | P1 | 僅 88/479 有真實 consumer_id；空數組當前被門禁接受 |
| business_capability_ledger 0 節點 | P1 | 文件存在但無業務節點數據 |
| task_tool_registry 僅 1 條 | P1 | 骨架存在，高頻場景尚未系統登記 |
| 治理 Release Gate（runtime evidence）未執行 | 發佈阻塞 | 無當前提交的 snapshot_gid/test_run_gid/簽名 release report |

---

## 4. 本輪新增能力質量抽查

Catalog stable 從 437 增至 **479**，新增 42 個能力，主要來自：
- Integration 域：19 個新 stable 能力（connector/mapping/sync 相關）
- Agent 域：22 個（包含 canvas runtime 相關）
- Craft 域：approval-related 新增

Catalog audit 驗證 479 個 stable descriptor：required_fields 全零缺失，`invalid_error_schema_count: 0`，`test_evidence_not_run_count: 0`。新增能力在字段完整性上符合 V2.1 要求。

---

## 5. 四輪審計趨勢

| 指標 | 2026-08-21 | 2026-08-25 | 2026-08-26 | **2026-09-01** |
|---|---|---|---|---|
| 提交數（`ahead`） | 0 | 14 | 72 | **127** |
| Catalog stable | 317 | 435 | 437 | **479** |
| 靜態 Release Gate | 失敗 | 失敗 | **通過** | ❌ **異常退出** |
| Catalog 字段缺失 | 333×9 | 0 | 0 | **0**（維持） |
| web_consumer_bypasses | 392 | 271 | 0 | **N/A（掃描失敗）** |
| 聚焦測試通過 | 9 | 20 | 20 | **11（4 回歸）** |
| Blocking Finding 數 | 7 | 3 | 0 | **3（新回歸）** |

---

## 6. 發佈前必要步驟

```
P0-1（緊急）：修復 Integration provider 加載回歸
  → 選擇一個方案：env var 延遲讀取 / 測試 stub / ProviderLoader 降級模式
  → 驗證：4 個 bootstrap/provider loading 測試全部通過

P0-2：更新 approval.js 的 wrapper contract hash
  → 更新 docs/governance/web-api-wrapper-contracts.json 中對應條目的 source_sha256
  → 驗證：evaluate_release_gate 不拋 RouteScanConfigurationError

P0-3：補全 4 個 base 遷移文件的 CODEOWNERS
  → 在 .github/CODEOWNERS 中添加對應條目
  → 驗證：check_domain_change_governance.py --check 通過

P0-4（完成 P0-1/2/3 後）：以完整 web root 重新運行 Release Gate 確認通過
  → 若通過：在受控 CI 環境執行 capability_scan.run + capability_test.run + release_gate.evaluate
```
