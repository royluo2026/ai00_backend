# Capability V2 原子業務能力治理審計（代碼級，第五輪）

- **審計日期：** 2026-09-01（同日第二次）
- **審計類型：** 靜態門禁 + 提供者加載 + 路由合約 + Catalog 字段 + 測試
- **規範版本：** 《原子業務能力開發治理規範 V2.1》（`docs/governance/atomic-capability-spec-v2.md`）
- **結論：** **不可發佈（BLOCKED）— 僅剩 1 項阻塞**
- **後端 HEAD：** `5c748db7a730f35be2f612dd772617232fc63ae7`（`test [ahead 127]`）
- **工作樹狀態：** 有 3 個未提交修改（`.github/CODEOWNERS`、`backend/capability_v2/official_domains.json`、`backend/capability_v2/schema_compiler.py`）以及大量 LF→CRLF 行尾自動轉換。功能性修改僅前三個文件。

> **注意：** 本輪審計針對**包含工作樹修改**的當前文件狀態。這些修改尚未提交；若需要可提交的基線，應先提交後重新運行一次門禁驗證。

---

## 1. 與上輪（第四輪）對比：三項回歸的消除情況

| 上輪 Blocking | 本輪狀態 | 修復方式 |
|---|---|---|
| B-NEW-1：Integration provider `provider_load_failed` | **已消除**（未提交修改中） | `backend/capability_v2/official_domains.json` 更新了 craft 和 integration 兩個 provider 的 `artifact_hash`；15 個聚焦測試全部通過 |
| B-NEW-2：`approval.js` wrapper contract hash 過期 | **仍阻塞** | `web-api-wrapper-contracts.json` 中存儲 hash `d2975a2d…`，當前文件 hash `04495dee…`，不匹配；Release Gate 異常退出 |
| B-NEW-3：4 個 base 遷移缺 CODEOWNERS | **已消除**（未提交修改中） | `.github/CODEOWNERS` 補充了 6 個 base 遷移和 1 個 craft 遷移的 `@maintainers` 條目 |

---

## 2. 靜態門禁驗證（本輪）

| 檢查項 | 結果 |
|---|---|
| Provider manifest 凍結 | ✅ **通過**；`sha256:f05ae87b…` |
| Catalog release build | ✅ **通過**；`rel_04c998e5…`，495 descriptors（479 stable） |
| 領域所有權/CODEOWNERS | ✅ **通過** |
| 跨域 import | ✅ **通過**；0 reviewed violations（上輪 1，本輪降至 0） |
| 完成度檢查（無 web scan） | ✅ **通過**；`complete=True`，`cross_domain_sql=0`，`internal_imports=0`，`consumer_bypasses=0` |
| Release Gate（完整 web root） | ❌ **異常退出**；`RouteScanConfigurationError: wrapper contract source hash is stale: packages/craft-plugin/web/approval/approval.js` |
| Catalog audit | ✅ **通過**；stable=479，required_fields 全 0，`invalid_error_schema_count=0`，`test_evidence_not_run_count=0` |
| 聚焦測試 | ✅ **15 passed**（上輪 4 failed + 11 passed，本輪全部通過） |

---

## 3. 當前唯一阻塞：Wrapper Contract Hash 過期（B-NEW-2）

**根因：** `docs/governance/web-api-wrapper-contracts.json` 中 `approval.js` 的存儲 hash 未與文件同步：

```
存儲 sha256: d2975a2db6081d2c1bc40dc4d9ffc750463c6ce002a8a2820b4517af52a669f1
當前 sha256: 04495deeced75c275da108fc797af937d194541b597c6186d52faa6d82cf7539
文件路徑:   packages/craft-plugin/web/approval/approval.js
```

**影響：** `backend/capability_v2/consumer_routes.py` 的 `WrapperContract` 系統在掃描前驗證每個合約源文件的 sha256，不匹配時拋 `RouteScanConfigurationError`。Release Gate 在進入 web 掃描階段時直接退出，`web_consumer_bypasses` 無法計算，`web_route_inventory_drift` 無法驗證，整個 `evaluate_release_gate()` 調用無法返回結果。

**最小整改方向：** 更新 `web-api-wrapper-contracts.json` 中 `approval.js` 條目的 `source_sha256` 為 `04495dee…`；或重新運行負責刷新此文件的腳本（通常是 `build_web_wrapper_contracts.py` 或等價腳本）。

**複驗條件：** `evaluate_release_gate(web_root=全前端根目錄)` 不再拋 `RouteScanConfigurationError`，`passed` 字段返回 `true`。

---

## 4. Catalog 與能力質量

- **Stable descriptor：** 479（前幾輪：317→435→437→479）
- **Required fields 缺失：** 全部 0（capability_version_gid、error_schema、transaction_policy 等 9 個字段）
- **Generic operation count：** 35（全部有 `disposition=split`）
- **Open arguments count：** 0
- **Invalid error_schema：** 0；**Test evidence not_run：** 0

---

## 5. 持續 P1 事項（未阻塞門禁）

| 事項 | 狀態 |
|---|---|
| consumer_refs 部分能力為空 `[]` | 88/479 有真實 consumer_id，391 為空；門禁接受空數組 |
| business_capability_ledger 0 節點 | 文件存在但無業務節點數據 |
| 治理 Release Gate runtime evidence | 需受控 CI 環境生成 snapshot_gid + test_run_gid + 簽名 release report |

---

## 6. 發佈前剩餘步驟

```
P0（唯一阻塞）：
  更新 docs/governance/web-api-wrapper-contracts.json 中 approval.js 的 source_sha256
  → 新值：04495deeced75c275da108fc797af937d194541b597c6186d52faa6d82cf7539
  → 驗證：evaluate_release_gate(web_root=...) passed=true

P0（提交）：
  將工作樹中已修復的 3 個文件提交（CODEOWNERS、official_domains.json、schema_compiler.py）
  → 提交後重新運行所有靜態門禁確認通過

P0（之後）：
  在受控 CI/CD 環境對當前提交執行：
  base.capability_scan.run → base.capability_test.run → base.capability_release_gate.evaluate
```

---

## 7. 五輪審計趨勢

| 日期 | 提交 | Stable | Gate | Tests | Blocking |
|---|---|---|---|---|---|
| 2026-08-21 | `697aac` | 317 | ❌ 失敗 | 9 pass | 7 |
| 2026-08-25 | `d5b6f9` | 435 | ❌ drift | 20 pass | 3 |
| 2026-08-26 | `b3f4367e` | 437 | ✅ 通過 | 20 pass | 0 (靜態) |
| 2026-09-01（第一輪） | `5c748db7` | 479 | ❌ 異常退出 | 11 pass | 3 (新回歸) |
| **2026-09-01（本輪）** | `5c748db7`+WD | **479** | ❌ 異常退出 | **15 pass** | **1** |
