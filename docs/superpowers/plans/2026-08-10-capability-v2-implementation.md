# AI00 Capability V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将全部稳定用户业务功能迁移到统一 Capability V2，使 Web、插件、AI Agent、REST、MCP 和 Local Runtime 在同一可信安全边界内发现、调用、测试和审计这些能力。

**Architecture:** 以不可变 User Function Registry 和 Catalog Release 为事实来源，所有入口先构造服务端可信 ConsumerIdentity，再经唯一 CapabilityGatewayService 调用领域 Application Port。迁移采用领域纵切片和旧接口绞杀策略，Revision/Lineage、Ontology、Artifact、Operation、审批、Outcome 与 Audit Outbox 是一级平台能力。

**Domain ownership:** Base Platform、Agent、Craft、Digital Model 和 Project Management 为必须独立维护和发布的一级域；Simulation、Ontology、Knowledge 和 Local Integration 遵守同样边界。领域间只通过 Gateway、Application Port、ResourceRef 或 Domain Event 协作。

**Tech Stack:** Python 3 / FastAPI / Pydantic / pytest，OceanBase MySQL 兼容 SQL，Node.js 22 / TypeScript / Node Test Runner，Electron Web，.NET 8 / C#，OIS 对象存储，JSON Schema Draft 2020-12。

## Global Constraints

- 实施前使用 `superpowers:using-git-worktrees` 创建干净隔离工作树；不得在当前含大量未提交改动的工作树直接开始 V2 实现。
- 使用 TDD：每个行为先写失败测试、确认失败原因、实现最小变更、再跑聚焦与回归测试。
- 所有稳定用户业务功能必须存在于 User Function Registry，并映射正式 Capability；纯内部、运维和非稳定 UI 功能必须记录排除理由。
- 所有消费者只能调用 `CapabilityGatewayService.invoke()`；禁止新增 `capability_registry.invoke()` 消费者旁路。
- Base Platform、Agent、Craft、Digital Model、Project Management、Simulation、Ontology、Knowledge 和 Local Integration 分别拥有代码、Provider、数据/Migration、测试、文档、版本和 CODEOWNERS。
- 禁止领域 A 直接导入领域 B 的 Router、Repository、ORM、Migration 或实现类；迁移前历史违规必须锁定基线并逐项清零，不得新增。
- Base Platform 不得承接项目/任务/问题/里程碑业务；Agent 不得内置工艺、数模或项目管理业务实现。
- 客户端不得通过 `X-AI00-Source`、插件 ID、插件版本、Agent Run ID 或自报 permissions 构造可信身份。
- 所有公开对象 Schema 必须 `additionalProperties: false`；输入、输出、错误和示例必须通过契约测试。
- 禁止新增 `plugin_callable`；使用 Web/Plugin/Agent/API/MCP 的结构化 Exposure Policy。
- 写入必须声明权限、资源选择器、数据范围、并发、幂等、确认、Evidence、Outcome 和审计策略。
- 大文件、CAD、模型和仿真制品使用 `ArtifactRef`；异步、本地和设备操作使用 `OperationRef`。
- Runtime 禁止运行时 DDL；所有表结构通过版本化 Migration 创建。
- 正式环境不得使用内存 Confirmation、Idempotency、Audit、Operation 或 Run Store。
- 不宣称跨数据库与设备 exactly-once；使用 at-least-once、领域去重和 `outcome_unknown`。
- 不接触生产数据库、生产 OIS、真实设备或发布通道；破坏性测试仅使用隔离租户、数据库和设备。
- 每个 Task 只提交列出的文件；执行前后检查暂存区，不能混入用户已有改动。
- 设计约束来源：`docs/superpowers/specs/2026-08-10-capability-v2-plugin-agent-architecture-design.md`。

---

## Program File Map

### Backend 主仓库新增边界

- `backend/capability_v2/contracts.py`：Descriptor、Identity、Envelope、Result 和标准引用。
- `backend/capability_v2/catalog.py`：Catalog Release 构建、固定与兼容校验。
- `backend/capability_v2/identity.py`：各入口可信身份适配。
- `backend/capability_v2/gateway.py`：唯一执行管线。
- `backend/capability_v2/policies.py`：Exposure、ABAC、数据投影、自动化等级。
- `backend/capability_v2/reliability.py`：幂等、配额、Outcome、审批协调接口。
- `backend/capability_v2/artifacts.py`：ArtifactRef 和受控上传/下载会话。
- `backend/capability_v2/operations.py`：OperationRef 与状态机。
- `backend/capability_v2/revision/`：Commit、Branch、Snapshot、Diff、Merge 和 Lineage。
- `backend/capability_v2/docs/`：Catalog/SDK/OpenAPI/MCP/开发者手册生成器。
- `backend/domain_ports/`：Base、Craft、Digital Model、Simulation、Ontology、Knowledge、Local Integration 的公开端口协议。
- `backend/domains/`：迁移期领域包；每域内部按 `application/capabilities/domain/data/tests/docs` 分层，成熟后可独立制品发布。
- `docs/governance/domain-ownership.json`：领域路径、数据表、Migration、Provider、制品、负责人和允许依赖的事实来源。
- `docs/governance/domain-dependency-baseline.json`：审计过的历史跨域依赖债务，只允许减少。
- `.github/CODEOWNERS`：将每个领域的代码、Migration、测试和文档绑定到对应维护组。
- `docs/governance/user-function-registry.json`：完整用户功能覆盖事实来源。
- `docs/capabilities/`：自动生成且版本化的开发者手册。

### 受版本控制的服务

- `services/agent-runtime/`：从根目录导入 Backend 主仓库并演进为持久化 Agent Run 服务。
- `services/mcp-gateway/`：从根目录导入 Backend 主仓库并改为可信 Gateway 适配器。
- `local-runtime/`：从根目录导入 Backend 主仓库并建立 .NET 8 CI、签名和恢复测试。

### Web 独立仓库

- `workmanship-web/web/core/capability_client.js`：Web 统一 CapabilityResultV2 客户端。
- `workmanship-web/web/core/web_compat.js`：只保留迁移期兼容入口。
- `workmanship-web/web/workspace/workspace.js`：Plugin Host Bridge、审批挑战与完整结果转发。
- `workmanship-web/packages/plugin-sdk/`：Manifest V2、Mount Session 和客户端类型。

---

## Wave 0 — 基线、所有权与强制门禁

### Task 1: 建立完整 User Function Registry

**Files:**
- Create: `docs/governance/user-function-registry.schema.json`
- Create: `docs/governance/user-function-registry.json`
- Create: `backend/scripts/build_user_function_registry.py`
- Create: `backend/tests/test_user_function_registry.py`
- Read: `docs/audit/consumer-route-registry.json`
- Read: `docs/audit/agreed-capability-consumer-matrix.md`

**Interfaces:**
- Produces: `UserFunctionRecord` JSON objects keyed by `function_id` with `domain`, `stability`, `current_consumers`, `target_capability`, `exposure`, `automation_level`, `resource_types`, `data_classification`, `migration_status`, `owner`, and `exclusion_reason`.
- Produces: command `python backend/scripts/build_user_function_registry.py --check` returning non-zero for missing or stale stable functions.

- [ ] **Step 1: Write the registry schema and failing completeness test**

```python
def test_every_stable_user_function_has_capability_or_valid_exclusion(registry):
    invalid = [row["function_id"] for row in registry
               if row["stability"] == "stable"
               and not row.get("target_capability")
               and row.get("classification") not in {"internal", "operations", "ui_transient"}]
    assert invalid == []
```

- [ ] **Step 2: Run the test and verify the initial registry is incomplete**

Run: `python -m pytest backend/tests/test_user_function_registry.py -q`

Expected: FAIL listing stable Web/REST functions not yet mapped.

- [ ] **Step 3: Implement deterministic scanners and commit the reviewed baseline**

The scanner must parse FastAPI route decorators, Web `fetch`/bridge calls, existing Capability registrations, Agent tools, MCP tools and Local Runtime advertised commands. It writes sorted records and never silently deletes manually reviewed metadata.

```python
def merge_discovery(existing: dict[str, dict], discovered: list[dict]) -> list[dict]:
    """Merge generated evidence while preserving reviewed governance fields."""
```

- [ ] **Step 4: Run registry and drift checks**

Run: `python backend/scripts/build_user_function_registry.py --check`

Expected: PASS with counts by Base Platform, Agent, Craft, Digital Model, Project Management, Simulation, Ontology, Knowledge and Local Integration.

- [ ] **Step 5: Commit**

```bash
git add docs/governance/user-function-registry.schema.json docs/governance/user-function-registry.json backend/scripts/build_user_function_registry.py backend/tests/test_user_function_registry.py
git commit -m "test: establish user function capability baseline"
```

### Task 2: 将 Agent、MCP 和 Local Runtime 纳入主仓库

**Files:**
- Create: `services/agent-runtime/package.json`, `package-lock.json`, `tsconfig.json`, `src/capability-client.ts`, `src/config.ts`, `src/crypto.ts`, `src/pi-runtime.ts`, `src/server.ts`, `src/session-store.ts`, and `test/runtime-policy.test.ts` from `E:/Projects/ai00_v3/services/agent-runtime/`
- Create: `services/mcp-gateway/package.json`, `package-lock.json`, `tsconfig.json`, `src/capability-client.ts`, `src/mcp.ts`, `src/schema.ts`, `src/server.ts`, and `test/schema.test.ts` from `E:/Projects/ai00_v3/services/mcp-gateway/`
- Create: `local-runtime/Ai00.LocalRuntime.sln`, `Directory.Build.props`, `appsettings.example.json`, `README.md`, and the three existing projects under `local-runtime/src/` from `E:/Projects/ai00_v3/local-runtime/`
- Create: `.github/workflows/capability-v2-services.yml`
- Create: `backend/tests/test_external_service_ownership.py`

**Interfaces:**
- Produces: one Git commit that can build exact Agent, MCP and .NET source revisions referenced by Catalog Release metadata.

- [ ] **Step 1: Write a failing source-ownership test**

```python
def test_external_consumers_are_tracked(repo_root):
    required = ["services/agent-runtime/package.json", "services/mcp-gateway/package.json", "local-runtime/Ai00.LocalRuntime.sln"]
    assert all((repo_root / path).is_file() for path in required)
```

- [ ] **Step 2: Run the test and verify it fails in the clean implementation worktree**

Run: `python -m pytest backend/tests/test_external_service_ownership.py -q`

Expected: FAIL with the three missing tracked paths.

- [ ] **Step 3: Import source-only trees and add CI**

CI must run:

```yaml
- run: npm ci && npm test
  working-directory: services/agent-runtime
- run: npm ci && npm test
  working-directory: services/mcp-gateway
- run: dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release
```

- [ ] **Step 4: Verify source ownership and service tests**

Run: `python -m pytest backend/tests/test_external_service_ownership.py -q`

Run: `npm test` in `services/agent-runtime` and `services/mcp-gateway`.

Run on Windows .NET CI: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release`.

- [ ] **Step 5: Commit**

```bash
git add services/agent-runtime services/mcp-gateway local-runtime .github/workflows/capability-v2-services.yml backend/tests/test_external_service_ownership.py
git commit -m "build: bring capability consumers under release control"
```

### Task 2A: 建立领域所有权与依赖门禁

**Files:**
- Create: `docs/governance/domain-ownership.json`
- Create: `docs/governance/domain-dependency-baseline.json`
- Create: `backend/scripts/check_domain_dependencies.py`
- Create: `backend/tests/test_domain_independence_v2.py`
- Modify: `.github/CODEOWNERS`
- Modify: `docs/governance/user-function-registry.schema.json`
- Modify: `backend/scripts/build_user_function_registry.py`
- Modify: `backend/tests/test_user_function_registry.py`

**Interfaces:**
- Produces: 一级域 `Base Platform`, `Agent`, `Craft`, `Digital Model`, `Project Management`, `Simulation`, `Ontology`, `Knowledge`, `Local Integration` 的机器可验证所有权清单。
- Produces: `python backend/scripts/check_domain_dependencies.py --check` command that rejects new cross-domain implementation imports, cross-domain table writes, undeclared providers and dependency cycles.
- Requires: 历史违规使用精确文件+符号基线，基线只可减少；禁止用宽泛 allowlist 掩盖新违规。

- [ ] **Step 1: Write failing domain classification and architecture tests**

Tests must prove Agent and Project Management are not classified as Base/Craft, every owned path has one owner, every table/Migration has one owner, and domains cannot import another domain's implementation.

- [ ] **Step 2: Inventory existing ownership and exact dependency debt**

Record source evidence and owner for every legacy exception. Mark unresolved ownership as a release blocker rather than assigning it silently to Base.

- [ ] **Step 3: Implement dependency scanner and regenerate User Function Registry**

Run:

```bash
python backend/scripts/build_user_function_registry.py --write
python backend/scripts/build_user_function_registry.py --check
python backend/scripts/check_domain_dependencies.py --check
```

- [ ] **Step 4: Add CODEOWNERS and per-domain CI matrix**

Each domain's provider, migrations, tests and docs must be reviewable independently. Catalog Release records the domain artifact version and schema hash.

- [ ] **Step 5: Commit**

```bash
git add docs/governance/domain-ownership.json docs/governance/domain-dependency-baseline.json backend/scripts/check_domain_dependencies.py backend/tests/test_domain_independence_v2.py .github/CODEOWNERS docs/governance/user-function-registry.schema.json backend/scripts/build_user_function_registry.py backend/tests/test_user_function_registry.py
git commit -m "arch: enforce independently owned domain boundaries"
```

## Wave 1 — Capability V2 Kernel

### Task 3: 定义 V2 契约和 V1 只读适配

**Files:**
- Create: `backend/capability_v2/__init__.py`
- Create: `backend/capability_v2/contracts.py`
- Create: `backend/capability_v2/v1_adapter.py`
- Create: `backend/tests/test_capability_v2_contracts.py`
- Modify: `backend/capabilities/models_next.py`

**Interfaces:**
- Produces: `CapabilityDescriptorV2`, `ExposurePolicy`, `AutomationLevel`, `ConsumerIdentity`, `InvocationEnvelope`, `CapabilityResultV2`, `ArtifactRef`, `OperationRef`, `ResourceSelector`.
- Produces: `adapt_v1_spec(spec: CapabilitySpec) -> CapabilityDescriptorV2`; it must mark adapted descriptors `experimental` and never infer Plugin/Agent write access.

- [ ] **Step 1: Write failing closed-contract tests**

```python
def test_consumer_identity_forbids_client_permissions():
    with pytest.raises(ValidationError):
        ConsumerIdentity.model_validate({"actor": {"user_id": "u1"}, "permissions": ["admin"]})

def test_result_distinguishes_accepted_from_completed():
    result = CapabilityResultV2.accepted("cap_1", OperationRef(operation_id="op_1", status="accepted"))
    assert result.status == "accepted" and result.operation_ref.operation_id == "op_1"
```

- [ ] **Step 2: Run the tests and verify missing V2 types**

Run: `python -m pytest backend/tests/test_capability_v2_contracts.py -q`

Expected: FAIL on import from `backend.capability_v2.contracts`.

- [ ] **Step 3: Implement frozen Pydantic contracts**

```python
class CapabilityDescriptorV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    major_version: int
    owner_domain: str
    lifecycle_status: Literal["experimental", "stable", "deprecated", "retired"]
    exposure: ExposurePolicy
    automation_level: AutomationLevel
    authorization_policy: str
    resource_selectors: tuple[ResourceSelector, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    schema_hash: str
```

- [ ] **Step 4: Verify V2 contracts and existing V1 tests**

Run: `python -m pytest backend/tests/test_capability_v2_contracts.py backend/tests/test_capability_kernel_contract.py backend/tests/test_capability_schema_contract.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2 backend/capabilities/models_next.py backend/tests/test_capability_v2_contracts.py
git commit -m "feat: define capability v2 contracts"
```

### Task 4: 构建不可变 Catalog Release

**Files:**
- Create: `backend/capability_v2/catalog.py`
- Create: `backend/capability_v2/catalog_store.py`
- Create: `backend/capability_v2/official_providers.json`
- Create: `backend/db/migrations/202608100001_base_capability_catalog_releases.sql`
- Create: `backend/scripts/build_capability_catalog.py`
- Create: `docs/governance/capability-catalog-release.json`
- Create: `backend/tests/test_capability_catalog_release.py`
- Modify: `backend/capabilities/registry_next.py`
- Modify: `backend/plugin_loader.py`

**Interfaces:**
- Produces: `CatalogRelease(release_id, catalog_hash, descriptors, provider_artifacts, created_at)`.
- Produces: `CatalogResolver.resolve(release_id, capability_id, major_version) -> RegisteredCapability` with no maximum-version fallback.

- [ ] **Step 1: Write failing deterministic-release tests**

```python
def test_catalog_hash_is_order_independent(descriptors):
    assert build_release(descriptors).catalog_hash == build_release(reversed(descriptors)).catalog_hash

def test_resolve_requires_pinned_major(resolver):
    with pytest.raises(CatalogResolutionError, match="major_version_required"):
        resolver.resolve("rel_1", "craft.routing.get", None)

def test_official_provider_requires_build_allowlist(plugin_loader):
    with pytest.raises(ProviderTrustError, match="provider_not_in_release"):
        plugin_loader.load_capability_provider("official.lookalike", artifact_hash="0" * 64)
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest backend/tests/test_capability_catalog_release.py -q`

Expected: FAIL because Catalog Release does not exist.

- [ ] **Step 3: Implement canonical JSON hashing, persistence and compatibility scanner**

```python
def canonical_catalog_bytes(descriptors: Sequence[CapabilityDescriptorV2]) -> bytes:
    ordered = sorted((d.model_dump(mode="json") for d in descriptors), key=lambda d: (d["id"], d["major_version"]))
    return json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

The migration must store release ID, catalog SHA-256, descriptor JSON, provider artifact JSON and creation time; published rows are immutable. `backend/plugin_loader.py` may load an official Capability Provider only when plugin ID, module, version and artifact hash exactly match `official_providers.json` embedded in the frozen Release; an `official.*` prefix is not trust evidence.

- [ ] **Step 4: Run release, migration and provider-loading tests**

Run: `python -m pytest backend/tests/test_capability_catalog_release.py backend/tests/test_capability_provider_loading.py backend/tests/test_versioned_migration_files.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/catalog.py backend/capability_v2/catalog_store.py backend/capability_v2/official_providers.json backend/db/migrations/202608100001_base_capability_catalog_releases.sql backend/scripts/build_capability_catalog.py docs/governance/capability-catalog-release.json backend/tests/test_capability_catalog_release.py backend/capabilities/registry_next.py backend/plugin_loader.py plugins/craft/manifest.json docs/governance/domain-ownership.json .github/CODEOWNERS
git commit -m "feat: add immutable capability catalog releases"
```

### Task 5: 建立可信 Identity Broker

**Files:**
- Create: `backend/capability_v2/identity.py`
- Create: `backend/capability_v2/delegation.py`
- Create: `backend/db/migrations/202608100002_consumer_delegations.sql`
- Create: `backend/tests/test_consumer_identity_broker.py`
- Modify: `backend/routers/deps.py`

**Interfaces:**
- Produces: `IdentityBroker.for_web()`, `.for_plugin_mount()`, `.for_agent_delegation()`, `.for_mcp_client()`, `.for_worker()`, `.for_local_runtime()`.
- Produces: `DelegationGrant` bound to actor, tenant, consumer, Catalog Release, Capability scopes, resource scopes, data scopes, maximum automation level and expiry.

- [ ] **Step 1: Write identity-forgery and revocation tests**

```python
def test_web_identity_ignores_source_headers(identity_broker, request):
    request.headers["X-AI00-Source"] = "worker"
    assert identity_broker.for_web(request).consumer.type == "web"

def test_revoked_delegation_cannot_build_agent_identity(identity_broker, revoked_grant):
    with pytest.raises(IdentityError, match="delegation_revoked"):
        identity_broker.for_agent_delegation(revoked_grant.token)
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest backend/tests/test_consumer_identity_broker.py -q`

Expected: FAIL because IdentityBroker is absent.

- [ ] **Step 3: Implement server-only adapters and hashed delegation tokens**

```python
class IdentityBroker:
    def for_web(self, principal: AuthenticatedPrincipal, tenant_id: str) -> ConsumerIdentity:
        return self._from_principal(principal, tenant_id, consumer_type="web", consumer_id="ai00.web")

    def for_plugin_mount(self, token: str) -> ConsumerIdentity:
        return self._from_mount_claims(self.mount_store.consume_active(token))

    def for_agent_delegation(self, token: str) -> ConsumerIdentity:
        return self._from_delegation(self.delegation_store.consume_active(token))
```

Token persistence stores only token hashes. High-risk invocation re-checks active membership and `authentication_time`.

- [ ] **Step 4: Run identity, plugin authority and tenant boundary tests**

Run: `python -m pytest backend/tests/test_consumer_identity_broker.py backend/tests/test_plugin_authority_boundary.py backend/tests/test_domain_grant_generation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/identity.py backend/capability_v2/delegation.py backend/db/migrations/202608100002_consumer_delegations.sql backend/tests/test_consumer_identity_broker.py backend/routers/deps.py
git commit -m "feat: add trusted capability consumer identities"
```

### Task 6: 实现唯一 CapabilityGatewayService

**Files:**
- Create: `backend/capability_v2/gateway.py`
- Create: `backend/capability_v2/policies.py`
- Create: `backend/tests/test_capability_gateway_pipeline.py`
- Create: `backend/tests/test_no_registry_consumer_bypass.py`
- Modify: `backend/routers/capabilities.py`
- Modify: `backend/platform_sdk/capabilities.py`
- Modify: `backend/capabilities/registry_next.py`

**Interfaces:**
- Consumes: `CatalogResolver`, `IdentityBroker`, `InvocationEnvelope`.
- Produces: `await CapabilityGatewayService.invoke(envelope) -> CapabilityResultV2`.
- Registry exposes only `resolve_provider()` to the Gateway; consumer modules cannot import or call `invoke()`.

- [ ] **Step 1: Write failing pipeline-order and bypass tests**

```python
async def test_gateway_rejects_exposure_before_provider_dispatch(gateway, plugin_envelope, provider):
    result = await gateway.invoke(plugin_envelope)
    assert result.error.code == "consumer_not_allowed"
    provider.assert_not_called()

def test_no_consumer_calls_registry_invoke(repo_root):
    violations = scan_calls(repo_root, "capability_registry.invoke", allowed={"backend/capability_v2/gateway.py"})
    assert violations == []
```

- [ ] **Step 2: Verify tests expose current Router/SDK bypasses**

Run: `python -m pytest backend/tests/test_capability_gateway_pipeline.py backend/tests/test_no_registry_consumer_bypass.py -q`

Expected: FAIL listing `backend/platform_sdk/capabilities.py` and Worker/Agent bypasses.

- [ ] **Step 3: Implement fixed pipeline and migrate HTTP/SDK adapters**

```python
async def invoke(self, envelope: InvocationEnvelope) -> CapabilityResultV2:
    resolved = self.catalog.resolve(envelope.catalog_release, envelope.capability_id, envelope.major_version)
    decision = self.policies.authorize(resolved.descriptor, envelope.identity, envelope.payload)
    decision.raise_if_denied()
    return await self.dispatcher.dispatch(resolved, envelope)
```

The real implementation must preserve the design order: catalog, identity, exposure, ABAC/data, schema/precondition, approval, idempotency/quota, dispatch, outcome/outbox, projection.

- [ ] **Step 4: Run Gateway and existing consumer regression**

Run: `python -m pytest backend/tests/test_capability_gateway_pipeline.py backend/tests/test_no_registry_consumer_bypass.py backend/tests/test_capability_consumer_e2e.py backend/tests/test_agent_capability_adapters.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/gateway.py backend/capability_v2/policies.py backend/tests/test_capability_gateway_pipeline.py backend/tests/test_no_registry_consumer_bypass.py backend/routers/capabilities.py backend/platform_sdk/capabilities.py backend/capabilities/registry_next.py
git commit -m "feat: route every capability through one gateway"
```

### Task 7: 下沉 ABAC、数据投影与资源选择器

**Files:**
- Create: `backend/capability_v2/authorization.py`
- Create: `backend/capability_v2/projection.py`
- Create: `backend/tests/test_capability_abac_matrix.py`
- Create: `backend/tests/test_llm_projection_policy.py`
- Modify: `backend/capability_v2/policies.py`
- Modify: `backend/routers/deps.py`

**Interfaces:**
- Produces: `AuthorizationDecision(allowed, code, policy_version, resource_refs, data_scopes)`.
- Produces: `project_result(result, descriptor, identity) -> CapabilityResultV2`.

- [ ] **Step 1: Write failing resource/data scope tests**

```python
@pytest.mark.parametrize("consumer,resource_scope,expected", [
    ("web", "project:p1", True),
    ("plugin", "project:p2", False),
    ("agent", "tenant:other", False),
])
def test_resource_scope_matrix(authorizer, consumer, resource_scope, expected):
    assert authorizer.authorize(identity(consumer), target(resource_scope)).allowed is expected
```

- [ ] **Step 2: Verify current string permissions are insufficient**

Run: `python -m pytest backend/tests/test_capability_abac_matrix.py backend/tests/test_llm_projection_policy.py -q`

Expected: FAIL on missing resource/data decisions.

- [ ] **Step 3: Implement ABAC decisions and LLM-safe projections**

The Agent projection removes secrets, personal data, raw paths and fields not listed by `agent_output_schema`; strings from business data are wrapped as untrusted content with source Evidence and size limits.

- [ ] **Step 4: Run authorization and Agent data-boundary suites**

Run: `python -m pytest backend/tests/test_capability_abac_matrix.py backend/tests/test_llm_projection_policy.py backend/tests/test_agent_data_boundaries.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/authorization.py backend/capability_v2/projection.py backend/capability_v2/policies.py backend/tests/test_capability_abac_matrix.py backend/tests/test_llm_projection_policy.py backend/routers/deps.py
git commit -m "feat: enforce resource and data scoped capability access"
```

### Task 8: 统一审批、幂等、配额、Outcome 和 Audit Outbox

**Files:**
- Create: `backend/capability_v2/reliability.py`
- Create: `backend/capability_v2/outcomes.py`
- Create: `backend/db/migrations/202608100003_capability_outcomes_and_approvals.sql`
- Create: `backend/tests/test_capability_reliability_pipeline.py`
- Modify: `backend/capabilities/confirmation_next.py`
- Modify: `backend/capabilities/idempotency_next.py`
- Modify: `backend/capabilities/rate_limit_next.py`
- Modify: `backend/capabilities/audit_next.py`
- Modify: `backend/capabilities/outbox_worker_next.py`

**Interfaces:**
- Produces: `ApprovalChallenge` bound to consumer, Run/Mount, resource, policy version and payload hash.
- Produces: `OutcomeRecord` with `started|accepted|completed|failed|outcome_unknown`.
- Produces: idempotency scope `tenant + consumer + capability + major + key + normalized_payload_hash`.

- [ ] **Step 1: Write failure-injection and approval-binding tests**

```python
async def test_committed_write_survives_audit_delivery_failure(gateway, outbox_down):
    result = await gateway.invoke(write_envelope("idem-1"))
    assert result.status == "completed"
    assert load_outcome(result.correlation.request_id).status == "completed"
    assert pending_audit_outbox_count() == 1

def test_approval_cannot_cross_agent_runs(approval_store):
    assert not approval_store.consume(challenge_for("run-a"), request_for("run-b"))
```

- [ ] **Step 2: Verify current non-atomic and weak-binding behavior fails**

Run: `python -m pytest backend/tests/test_capability_reliability_pipeline.py -q`

Expected: FAIL on audit failure, consumer-scoped idempotency and cross-run approval.

- [ ] **Step 3: Implement transaction participant and remove Worker self-confirmation**

```python
class ReliabilityCoordinator:
    def begin(self, envelope: InvocationEnvelope, descriptor: CapabilityDescriptorV2) -> InvocationLease:
        return self.store.begin(build_invocation_lease(envelope, descriptor))

    def complete(self, lease: InvocationLease, result: CapabilityResultV2, transaction: Any) -> None:
        self.store.complete_in_transaction(lease, result, transaction)

    def mark_unknown(self, lease: InvocationLease, error_code: str) -> CapabilityResultV2:
        return self.store.mark_unknown(lease, error_code)
```

High-risk writes fail closed when durable Outcome/Audit storage is unavailable. Rate limiting includes tenant, consumer, Agent Run/plugin installation and descriptor cost weight.

- [ ] **Step 4: Run reliability, confirmation, idempotency, rate and audit suites**

Run: `python -m pytest backend/tests/test_capability_reliability_pipeline.py backend/tests/test_confirmation_storage.py backend/tests/test_capability_idempotency.py backend/tests/test_rate_limit.py backend/tests/test_audit_reliability.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/reliability.py backend/capability_v2/outcomes.py backend/db/migrations/202608100003_capability_outcomes_and_approvals.sql backend/tests/test_capability_reliability_pipeline.py backend/capabilities/confirmation_next.py backend/capabilities/idempotency_next.py backend/capabilities/rate_limit_next.py backend/capabilities/audit_next.py backend/capabilities/outbox_worker_next.py
git commit -m "feat: make capability outcomes and approvals durable"
```

### Task 9: 实现 ArtifactRef 与 OperationRef

**Files:**
- Create: `backend/capability_v2/artifacts.py`
- Create: `backend/capability_v2/operations.py`
- Create: `backend/db/migrations/202608100004_artifacts_and_operations.sql`
- Create: `backend/routers/capability_artifacts.py`
- Create: `backend/routers/capability_operations.py`
- Create: `backend/tests/test_artifact_operation_protocol.py`
- Modify: `backend/main.py`

**Interfaces:**
- Produces: host-mediated upload session returning `ArtifactRef` after hash verification.
- Produces: `OperationService.create()`, `.transition()`, `.get_authorized()` with an explicit state transition table.

- [ ] **Step 1: Write failing reference and state-machine tests**

```python
def test_operation_cannot_skip_from_accepted_to_completed_without_policy(service):
    op = service.create(kind="device.command", requested_by=identity())
    with pytest.raises(OperationTransitionError):
        service.transition(op.operation_id, "completed")

def test_artifact_hash_mismatch_is_rejected(artifact_service):
    with pytest.raises(ArtifactIntegrityError):
        artifact_service.finalize("upload_1", reported_sha256="0" * 64)
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest backend/tests/test_artifact_operation_protocol.py -q`

Expected: FAIL because services are absent.

- [ ] **Step 3: Implement authorized references, upload sessions and transition CAS**

Valid operation states are `accepted`, `claimed`, `preparing`, `running`, `post_processing`, `completed`, `failed`, `cancelled`, `outcome_unknown`; every transition uses expected current version.

- [ ] **Step 4: Run protocol and OceanBase migration tests**

Run: `python -m pytest backend/tests/test_artifact_operation_protocol.py backend/tests/test_oceanbase_compatibility.py backend/tests/test_versioned_migration_files.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/artifacts.py backend/capability_v2/operations.py backend/db/migrations/202608100004_artifacts_and_operations.sql backend/routers/capability_artifacts.py backend/routers/capability_operations.py backend/tests/test_artifact_operation_protocol.py backend/main.py
git commit -m "feat: add governed artifact and operation protocols"
```

## Wave 2 — 文档、插件、Agent 与 MCP

### Task 10: 生成开发者手册、SDK 与机器目录

**Files:**
- Create: `backend/capability_v2/docs/generator.py`
- Create: `backend/capability_v2/docs/templates/capability.md.j2`
- Create: `backend/scripts/generate_capability_docs.py`
- Create: `docs/capabilities/README.md`
- Create: `docs/capabilities/catalog.v2.json`
- Create: `backend/tests/test_capability_docs_generation.py`
- Modify: `packages/plugin-sdk/src/index.ts`
- Modify: `packages/plugin-sdk/src/index.js`

**Interfaces:**
- Consumes: immutable Catalog Release.
- Produces: deterministic Markdown manual, JSON Catalog, Plugin SDK types, Agent Tool schema, OpenAPI/MCP fragments and executable examples.

- [ ] **Step 1: Write failing drift and example tests**

```python
def test_every_stable_descriptor_has_generated_page(catalog, docs_root):
    missing = [d.id for d in catalog.descriptors if d.lifecycle_status == "stable" and not (docs_root / f"{d.id}.md").is_file()]
    assert missing == []

def test_generated_examples_validate_against_schema(generated_examples):
    for descriptor, example in generated_examples:
        validate_payload(descriptor.input_schema, example.input)
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest backend/tests/test_capability_docs_generation.py -q`

Expected: FAIL because generated pages and Catalog do not exist.

- [ ] **Step 3: Implement deterministic generation and `--check` mode**

Run interface:

```bash
python backend/scripts/generate_capability_docs.py --catalog-release rel_x --output docs/capabilities
python backend/scripts/generate_capability_docs.py --check
```

The generator fails for missing owner, use/do-not-use text, exposure, permissions, resource selector, data classification, errors, examples, lifecycle or migration guidance.

- [ ] **Step 4: Generate artifacts and run drift checks**

Run: `python backend/scripts/generate_capability_docs.py --check`

Run: `python -m pytest backend/tests/test_capability_docs_generation.py -q`

Run: `npm test` in `packages/plugin-sdk`.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/docs backend/scripts/generate_capability_docs.py docs/capabilities packages/plugin-sdk/src backend/tests/test_capability_docs_generation.py
git commit -m "docs: generate the capability developer manual"
```

### Task 11: 升级 Plugin Manifest、Mount Session 和 Host Bridge

**Files:**
- Modify: `backend/plugin_platform/manifest.py`
- Replace: `backend/plugin_platform/mounts.py`
- Modify: `backend/plugin_platform/service.py`
- Modify: `backend/routers/plugin_marketplace.py`
- Create: `backend/db/migrations/202608100005_plugin_mount_sessions.sql`
- Create: `backend/tests/test_plugin_mount_sessions_v2.py`
- Modify: `packages/plugin-sdk/manifest-v2.schema.json`
- Modify: `packages/plugin-sdk/src/host.ts`
- Modify in Web repo: `web/workspace/workspace.js`
- Modify in Web repo: `web/core/web_compat.js`
- Modify in Web repo: `packages/plugin-sdk/frontend/plugin-sdk.js`

**Interfaces:**
- Produces: `PluginMountSession` bound to installation, artifact hash, user, tenant, Catalog Release, Capability version ranges, resource/data scopes and revocation version.
- Host Bridge sends/receives full `CapabilityResultV2`; ApprovalChallenge is handled by host UI and never exposed as a reusable token.

- [ ] **Step 1: Write failing Manifest and mount forgery tests**

```python
def test_mount_token_cannot_cross_users(mount_service):
    token = mount_service.issue(user_id="u1", installation_id="i1")
    with pytest.raises(MountTokenError):
        mount_service.resolve(token, current_user="u2")

def test_optional_capability_does_not_block_install(parse_manifest):
    manifest = parse_manifest(manifest_with(required=[], optional=[{"id": "craft.routing.get", "major": 1}]))
    assert manifest.optional_capabilities[0].id == "craft.routing.get"
```

- [ ] **Step 2: Run Backend and Web bridge tests to expose Header identity/result truncation**

Run: `python -m pytest backend/tests/test_plugin_mount_sessions_v2.py backend/tests/test_plugin_mount_tokens_next.py -q`

Run in Web repo: `npm test`.

Expected: FAIL on user/install binding and full result preservation.

- [ ] **Step 3: Implement persisted Mount Session and host-owned approval loop**

```ts
export interface PluginCapabilityResponse<T> {
  ok: boolean;
  status: "completed" | "accepted" | "rejected" | "failed" | "outcome_unknown";
  data: T | null;
  operation_ref: OperationRef | null;
  error: CapabilityError | null;
  evidence: EvidenceRef[];
}
```

Static assets use the session identity, survive page lazy loading, and check live revocation. Remove `X-AI00-Plugin-ID`, `X-AI00-Plugin-Version` and `data.data` rewrapping.

- [ ] **Step 4: Run plugin security and full Web regression**

Run: `python -m pytest backend/tests/test_plugin_mount_sessions_v2.py backend/tests/test_plugin_authority_boundary.py backend/tests/test_plugin_platform_next.py backend/tests/test_plugin_acceptance_tooling.py -q`

Run in Web repo: `npm test`.

Expected: PASS.

- [ ] **Step 5: Commit separately in Backend and Web repositories**

```bash
git add backend/plugin_platform backend/routers/plugin_marketplace.py backend/db/migrations/202608100005_plugin_mount_sessions.sql backend/tests/test_plugin_mount_sessions_v2.py packages/plugin-sdk
git commit -m "feat: bind plugin capabilities to mount sessions"
```

Web commit: `feat: preserve capability results in the plugin host`.

### Task 12: 将 Agent Runtime 升级为持久化 Run 与审批调度器

**Files:**
- Create: `backend/db/migrations/202608100006_agent_runs.sql`
- Create: `services/agent-runtime/src/run-store.ts`
- Create: `services/agent-runtime/src/delegation-client.ts`
- Create: `services/agent-runtime/src/tool-selector.ts`
- Create: `services/agent-runtime/src/approval-dispatcher.ts`
- Create: `services/agent-runtime/src/projection.ts`
- Modify: `services/agent-runtime/src/session-store.ts`
- Modify: `services/agent-runtime/src/capability-client.ts`
- Modify: `services/agent-runtime/src/pi-runtime.ts`
- Modify: `services/agent-runtime/src/server.ts`
- Create: `services/agent-runtime/test/run-lifecycle.test.ts`
- Create: `services/agent-runtime/test/approval.test.ts`

**Interfaces:**
- Produces: persistent AgentRun state machine and Run-scoped DelegationGrant.
- Produces: `ToolSelector.select(goal, catalogRelease, identity) -> ToolSelection` with a bounded selected set.
- Produces: pause/resume/cancel endpoints and host-facing ApprovalRequest endpoints.

- [ ] **Step 1: Write failing restart, group membership and approval tests**

```ts
test("run resumes after runtime restart", async () => {
  const run = await store.create(input);
  await store.transition(run.id, "awaiting_approval");
  const reopened = new RunStore(pool);
  assert.equal((await reopened.load(run.id)).status, "awaiting_approval");
});
```

- [ ] **Step 2: Verify current session-only Runtime fails**

Run: `npm test` in `services/agent-runtime`.

Expected: FAIL because RunStore and approval state do not exist; test also asserts `SessionStore.initialize()` issues no DDL.

- [ ] **Step 3: Implement Run state, group participants, delegation and bounded ToolSelection**

The Runtime sends only a service credential plus DelegationGrant reference to Backend. UI context is structured untrusted input, not appended to system prompt. Tool results use Agent projection and size limits.

- [ ] **Step 4: Run service and Backend Agent suites**

Run: `npm test` in `services/agent-runtime`.

Run: `python -m pytest backend/tests/test_agent_consumer_catalog.py backend/tests/test_agent_data_boundaries.py backend/tests/test_agent_capability_adapters.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/db/migrations/202608100006_agent_runs.sql services/agent-runtime
git commit -m "feat: persist agent runs delegations and approvals"
```

### Task 13: 将 MCP 改为固定 Catalog 的可信适配器

**Files:**
- Create: `services/mcp-gateway/src/delegation.ts`
- Create: `services/mcp-gateway/src/catalog-cache.ts`
- Modify: `services/mcp-gateway/src/capability-client.ts`
- Modify: `services/mcp-gateway/src/mcp.ts`
- Modify: `services/mcp-gateway/src/server.ts`
- Create: `services/mcp-gateway/test/catalog-release.test.ts`
- Create: `services/mcp-gateway/test/delegation.test.ts`
- Create: `backend/tests/test_mcp_gateway_identity.py`

**Interfaces:**
- MCP session exchanges external authentication for a server-side delegation; it does not forward raw long-lived Bearer tokens.
- Tool names resolve one pinned major version from one Catalog Release; duplicate names fail service startup.

- [ ] **Step 1: Write failing raw-token and catalog-drift tests**

```ts
test("mcp backend calls use delegation reference, not user bearer", async () => {
  const headers = client.backendHeaders(session);
  assert.equal(headers.Authorization, undefined);
  assert.match(headers["X-AI00-Delegation"], /^dlg_/);
});
```

- [ ] **Step 2: Verify failure**

Run: `npm test` in `services/mcp-gateway`.

Expected: FAIL because the current server constructs a catalog per request and forwards Bearer token.

- [ ] **Step 3: Implement service identity, delegation exchange and immutable catalog cache**

Write CapabilityResultV2 to MCP `structuredContent`; apply Agent-safe projection and Artifact/Operation references. Keep writes disabled until ApprovalChallenge transport is proven by tests.

- [ ] **Step 4: Run MCP and Backend identity tests**

Run: `npm test` in `services/mcp-gateway`.

Run: `python -m pytest backend/tests/test_mcp_gateway_identity.py backend/tests/test_capability_consumer_e2e.py -q`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/mcp-gateway backend/tests/test_mcp_gateway_identity.py
git commit -m "feat: pin mcp sessions to delegated catalog releases"
```

## Wave 3 — Revision、Ontology 与领域迁移

### Task 14: 实现 Revision & Lineage Kernel

**Files:**
- Create: `backend/capability_v2/revision/models.py`
- Create: `backend/capability_v2/revision/repository.py`
- Create: `backend/capability_v2/revision/service.py`
- Create: `backend/capability_v2/revision/diff.py`
- Create: `backend/capability_v2/revision/merge.py`
- Create: `backend/db/migrations/202608100007_revision_lineage.sql`
- Create: `backend/tests/test_revision_kernel.py`
- Create: `backend/tests/golden/revision/linear-history.json`
- Create: `backend/tests/golden/revision/three-way-field-conflict.json`
- Create: `backend/tests/golden/revision/protected-branch-approval.json`

**Interfaces:**
- Produces: RepositoryRef, BranchRef, CommitRef, SnapshotRef, ChangeSetRef, DiffRef, BaselineRef and three-way MergeResult.
- Domain adapter protocol: `normalize()`, `diff()`, `validate_changeset()`, `apply_changeset()`, `classify_conflict()`.

- [ ] **Step 1: Write failing immutable history and three-way merge tests**

```python
def test_restore_creates_new_commit_without_rewriting_history(service):
    restored = service.restore(branch="main", source_commit="c1", expected_head="c3")
    assert restored.parent_ids == ("c3",)
    assert service.get("c1").content_hash == original_hash

def test_move_is_not_delete_plus_add(craft_diff_adapter):
    diff = craft_diff_adapter.diff(before_route, moved_route)
    assert [c.change_type for c in diff.changes] == ["move"]
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest backend/tests/test_revision_kernel.py -q`

Expected: FAIL on missing Revision service.

- [ ] **Step 3: Implement immutable commits, snapshots, semantic adapters and protected branches**

All hashes use the same canonical JSON as Catalog. Merge to protected branches returns ApprovalChallenge. Snapshot policy is deterministic by change count and byte size.

- [ ] **Step 4: Run Revision Golden Cases and migration tests**

Run: `python -m pytest backend/tests/test_revision_kernel.py backend/tests/test_versioned_migration_files.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/capability_v2/revision backend/db/migrations/202608100007_revision_lineage.sql backend/tests/test_revision_kernel.py backend/tests/golden/revision
git commit -m "feat: add revision diff merge and lineage kernel"
```

### Task 15: 将 Ontology 接入 Revision、Proposal 和影响分析

**Files:**
- Create: `backend/domain_ports/ontology.py`
- Create: `backend/capability_v2/revision/ontology_adapter.py`
- Create: `backend/ontology/impact_analysis.py`
- Modify: `backend/capabilities/ontology_concepts_next.py`
- Modify: `backend/capabilities/ontology_proposals_next.py`
- Modify: `backend/capabilities/ontology_releases_next.py`
- Create: `backend/tests/test_ontology_revision_impact.py`
- Create: `backend/tests/golden/ontology/concept-rename.json`
- Create: `backend/tests/golden/ontology/constraint-breaking-change.json`
- Create: `backend/tests/golden/ontology/release-impact.json`

**Interfaces:**
- Produces: stable ConceptRef and OntologyVersionRef in every read result.
- Produces: proposal → review → immutable release → compatibility check → activation flow; proposer/Agent cannot self-approve.

- [ ] **Step 1: Write failing rename and impact Golden Cases**

```python
def test_concept_rename_preserves_identity(ontology_diff):
    change = ontology_diff(before, after).changes[0]
    assert change.change_type == "rename"
    assert change.resource_ref.concept_id == "concept.operation"
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest backend/tests/test_ontology_revision_impact.py -q`

Expected: FAIL because releases are not backed by common Revision/impact analysis.

- [ ] **Step 3: Implement adapter and reference scans across Craft, model mappings, plugins and Agent workflows**

Activation is blocked when a breaking change has unresolved consumers. Inference extensions accept only reviewed declarative rules with execution budgets.

- [ ] **Step 4: Run all Ontology regression and Golden Cases**

Run: `python -m pytest backend/tests/test_ontology_revision_impact.py backend/tests/test_ontology_concept_capabilities.py backend/tests/test_ontology_proposal_capabilities.py backend/tests/test_ontology_release_capabilities.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domain_ports/ontology.py backend/capability_v2/revision/ontology_adapter.py backend/ontology/impact_analysis.py backend/capabilities/ontology_concepts_next.py backend/capabilities/ontology_proposals_next.py backend/capabilities/ontology_releases_next.py backend/tests/test_ontology_revision_impact.py backend/tests/golden/ontology
git commit -m "feat: version ontology changes and analyze impact"
```

### Task 16: 迁移 Base Platform、Project Management、Knowledge 与 Craft 独立纵切片

**Files:**
- Create: `backend/domain_ports/base.py`
- Create: `backend/domain_ports/project_management.py`
- Create: `backend/domain_ports/knowledge.py`
- Create: `backend/domain_ports/craft.py`
- Create: `plugins/project_management/manifest.json`
- Create: `plugins/project_management/project_management_backend/application/`
- Create: `plugins/project_management/project_management_backend/capabilities/`
- Create: `plugins/project_management/project_management_backend/data/migrations/`
- Create: `plugins/project_management/tests/`
- Modify: `backend/system_capabilities/base_provider.py`
- Modify: `backend/capabilities/knowledge_context_next.py`
- Modify: `backend/capabilities/knowledge_documents_next.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_compare.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_structure.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_versions.py`
- Modify: `plugins/craft/craft_backend/capabilities/bop_writes.py`
- Modify: `plugins/craft/craft_backend/capabilities/gbop_read.py`
- Modify: `plugins/craft/craft_backend/capabilities/pbom_read.py`
- Create: `backend/capability_v2/revision/craft_adapter.py`
- Create: `backend/tests/test_domain_capability_coverage.py`
- Create: `backend/tests/golden/craft/route-move.json`
- Create: `backend/tests/golden/craft/parameter-change.json`
- Create: `backend/tests/golden/craft/material-replacement.json`

**Interfaces:**
- Consumes: reviewed User Function Registry records for Base Platform, Project Management, Knowledge and Craft.
- Produces: one V2 Descriptor and Gateway Provider for every stable record; no direct Router/Repository consumer access.
- Requires: project/workspace/task/issue/milestone/member-role/change-coordination behavior is owned by Project Management, not Base Platform or Craft.

- [ ] **Step 1: Write a failing data-driven domain coverage test**

```python
@pytest.mark.parametrize("domain", ["Base Platform", "Project Management", "Knowledge", "Craft"])
def test_stable_domain_functions_have_v2_descriptors(domain, user_functions, catalog):
    expected = {r["target_capability"] for r in user_functions if r["domain"] == domain and r["stability"] == "stable"}
    actual = {d.id for d in catalog.descriptors if d.owner_domain == domain}
    assert expected - actual == set()
```

- [ ] **Step 2: Run and capture the exact missing Capability IDs**

Run: `python -m pytest backend/tests/test_domain_capability_coverage.py -q`

Expected: FAIL with the registry-derived missing IDs; attach the list to the Task review.

- [ ] **Step 3: Implement one complete vertical slice at a time**

For every missing ID: add Descriptor, closed schemas, resource selectors, automation policy, Application Port method, Provider, success/error tests, Plugin/Agent contract examples and generated docs. Migrate read/validate first, draft writes second, publish/restore/bulk writes last. Craft writes create ChangeSet/Commit; Knowledge revisions preserve Evidence and immutable history. Project Management stores only stable refs to Craft/Model/Simulation/Knowledge resources and cannot write their tables.

- [ ] **Step 4: Require zero missing stable records and run domain regressions**

Run: `python -m pytest backend/tests/test_domain_capability_coverage.py backend/tests/test_base_capability_providers.py plugins/project_management/tests backend/tests/test_knowledge_document_capabilities.py backend/tests/test_craft_bop_version_capabilities.py backend/tests/test_craft_write_capabilities.py -q`

Expected: PASS with zero skipped stable Capability rows.

- [ ] **Step 5: Commit each reviewed vertical slice**

Commit format: `feat(<domain>): expose <user-function-id> through capability v2`.

### Task 17: 建立 Digital Model 领域并补齐 Simulation

**Files:**
- Create: `backend/domain_ports/digital_model.py`
- Create: `plugins/digital_model/manifest.json`
- Create: `plugins/digital_model/digital_model_backend/capabilities/`
- Create: `plugins/digital_model/digital_model_backend/services/`
- Create: `backend/capability_v2/revision/digital_model_adapter.py`
- Modify: `plugins/simulation/simulation_backend/capabilities/environments.py`
- Modify: `plugins/simulation/simulation_backend/environments.py`
- Create: `backend/capability_v2/revision/simulation_adapter.py`
- Create: `backend/tests/test_digital_model_capabilities.py`
- Create: `backend/tests/test_simulation_reproducibility.py`
- Create: `backend/tests/golden/digital_model/component-move.json`
- Create: `backend/tests/golden/digital_model/component-replacement.json`
- Create: `backend/tests/golden/digital_model/geometry-summary-change.json`

**Interfaces:**
- Digital Model consumes/produces ModelRef, ModelVersionRef, ModelSnapshotRef, ComponentRef and ArtifactRef.
- Simulation environment creation accepts only `execution_plan_ref`, `model_snapshot_ref`, `parameter_set_ref`, `simulation_profile_ref` and resolves them through domain ports.

- [ ] **Step 1: Write failing no-file-path and reproducibility tests**

```python
def test_simulation_rejects_caller_supplied_plan_json(provider):
    with pytest.raises(SchemaValidationError):
        provider.create_environment({"execution_plan": {"steps": []}, "snapshot_uri": "file:///x"})

def test_model_capabilities_never_return_server_paths(result):
    assert "file_path" not in json.dumps(result.model_dump(mode="json"))
```

- [ ] **Step 2: Verify current Simulation contract fails**

Run: `python -m pytest backend/tests/test_digital_model_capabilities.py backend/tests/test_simulation_reproducibility.py -q`

Expected: FAIL because Digital Model is absent and Simulation trusts caller data.

- [ ] **Step 3: Implement model identity/snapshot/diff first, then Simulation environment/run/result slices**

Every Simulation Run records exact Craft commit, model snapshot hash, parameter version, solver version and result ArtifactRefs. Large geometry Diff and Simulation use OperationRef.

- [ ] **Step 4: Run domain, Revision and coverage tests**

Run: `python -m pytest backend/tests/test_digital_model_capabilities.py backend/tests/test_simulation_reproducibility.py backend/tests/test_simulation_capabilities.py backend/tests/test_craft_simulation_contract.py backend/tests/test_domain_capability_coverage.py -q`

Expected: PASS.

- [ ] **Step 5: Commit each Digital Model and Simulation vertical slice**

Commit the identity/snapshot slice as `feat(digital-model): add governed model snapshots`, the semantic Diff slice as `feat(digital-model): add semantic model comparison`, and the Simulation slice as `feat(simulation): resolve versioned model and craft inputs`.

### Task 18: 重构 Local Integration 与跨语言协议

**Files:**
- Create: `backend/domain_ports/local_integration.py`
- Modify: `plugins/device/device_backend/capabilities/runtime.py`
- Modify: `plugins/device/device_backend/control_plane.py`
- Delete after migration: `backend/capabilities/local_runtime_next.py`
- Modify: `local-runtime/src/Ai00.LocalRuntime.Contracts/Contracts.cs`
- Modify: `local-runtime/src/Ai00.LocalRuntime.Service/RuntimeWorker.cs`
- Modify: `local-runtime/src/Ai00.LocalRuntime.SessionHost/CommandLedger.cs`
- Create: `local-runtime/tests/Ai00.LocalRuntime.Tests/CanonicalJsonTests.cs`
- Create: `backend/tests/fixtures/device_protocol_vectors.json`
- Create: `backend/tests/test_local_operation_protocol_v2.py`

**Interfaces:**
- Produces: signed Canonical JSON Operation Envelope and Outcome shared by Python/C# test vectors.
- Local commands accept ArtifactRef/ModelRef; device ownership supports explicit tenant/workstation grants.

- [ ] **Step 1: Write shared-vector, crash-recovery and path-rejection tests**

```python
def test_python_signature_matches_dotnet_vector(vector):
    assert sign_canonical(vector["payload"], vector["secret"]) == vector["signature"]

def test_local_command_rejects_file_path(provider):
    with pytest.raises(SchemaValidationError):
        provider.invoke({"device_gid": "d1", "file_path": "C:\\secret.jt"})
```

- [ ] **Step 2: Verify mismatched capability lists and missing formal canonicalization**

Run: `python -m pytest backend/tests/test_local_operation_protocol_v2.py backend/tests/test_device_runtime_protocol.py -q`

Run on Windows CI: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release`.

Expected: FAIL before shared vectors and crash recovery are implemented.

- [ ] **Step 3: Implement signed envelopes, bounded ledger, reconciliation and sanitized errors**

On startup, `started` entries become `outcome_unknown` and reconcile with cloud; they are not replayed automatically. Named-pipe ACL is restricted to the service/session identity, and secrets support rotation.

- [ ] **Step 4: Run Backend/.NET protocol and device suites**

Run: `python -m pytest backend/tests/test_local_operation_protocol_v2.py backend/tests/test_device_capabilities.py backend/tests/test_device_runtime_protocol.py backend/tests/test_device_domain_boundary.py -q`.

Run on Windows CI: `dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domain_ports/local_integration.py plugins/device backend/tests/test_local_operation_protocol_v2.py backend/tests/fixtures/device_protocol_vectors.json local-runtime
git rm backend/capabilities/local_runtime_next.py
git commit -m "feat: secure local capability operations end to end"
```

## Wave 4 — Web 统一、退役与正式验收

### Task 19: 将 Web 功能迁移到统一 Capability Client

**Files in Web repo:**
- Create: `web/core/capability_client.js`
- Create: `web/core/capability_client.test.js`
- Modify: `web/core/web_compat.js`
- Modify: pages identified by `docs/governance/user-function-registry.json`
- Modify: `package.json`
- Create: `scripts/check_legacy_capability_routes.js`

**Interfaces:**
- Produces: `capabilities.invoke(id, majorVersion, payload, options) -> CapabilityResultV2`.
- Produces: a route-usage checker proving each migrated stable function no longer calls a legacy business Router.

- [ ] **Step 1: Write failing result, approval and Operation tests**

```javascript
test('invoke preserves accepted operation result', async () => {
  const result = await client.invoke('simulation.run.start', 1, payload);
  assert.equal(result.status, 'accepted');
  assert.equal(result.operation_ref.operation_id, 'op_1');
});
```

- [ ] **Step 2: Run Web tests and verify current result truncation/legacy calls fail**

Run: `npm test` in `E:/Projects/ai00_v3/workmanship-web`.

Expected: FAIL on full CapabilityResult and registry-derived legacy routes.

- [ ] **Step 3: Migrate one User Function Registry row per commit**

Each migration changes the page call, preserves UX, handles ApprovalChallenge/OperationRef, adds a test, marks the registry row migrated, and leaves the old REST Adapter read-only until observation completes.

- [ ] **Step 4: Require zero stable Web functions on legacy business routes**

Run: `node scripts/check_legacy_capability_routes.js --registry E:/Projects/ai00_v3/.worktrees/capability-v2-implementation/docs/governance/user-function-registry.json`.

Run: `npm test`.

Expected: PASS with zero violations.

- [ ] **Step 5: Commit each Web vertical slice**

Commit format: `refactor(web): route <function-id> through capability v2`.

### Task 20: 退役 V1 旁路和双 URL

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/capabilities.py`
- Modify: `backend/capabilities/__init__.py`
- Delete: `backend/capabilities/models.py`
- Delete: `backend/capabilities/registry.py`
- Delete after all adapters migrate: V1 adapter modules recorded by the Registry
- Create: `backend/tests/test_capability_v1_retirement.py`
- Create: `docs/migrations/capability-v1-retirement.md`

**Interfaces:**
- `/api/v1/capabilities` remains the only public Capability URL.
- Legacy REST endpoints return deprecation metadata during observation and are removed only after measured zero use and rollback review.

- [ ] **Step 1: Write failing import and route-retirement tests**

```python
def test_only_one_capability_route(app):
    paths = {route.path for route in app.routes if "capabilities" in route.path}
    assert "/api/capabilities" not in paths

def test_legacy_registry_modules_are_absent(repo_root):
    assert not (repo_root / "backend/capabilities/registry.py").exists()
```

- [ ] **Step 2: Verify failure and capture remaining consumers**

Run: `python -m pytest backend/tests/test_capability_v1_retirement.py backend/tests/test_no_registry_consumer_bypass.py -q`

Expected: FAIL until all callers have migrated.

- [ ] **Step 3: Remove old modules/routes and document rollback boundary**

Do not delete any legacy business endpoint with observed traffic. Record last-seen time, replacement Capability, rollback Feature Flag and owner in the migration document.

- [ ] **Step 4: Run full Backend, Agent, MCP and Web regression**

Run: `python -m pytest backend/tests -q`.

Run: `npm test` in `services/agent-runtime`, `services/mcp-gateway`, and Web repo.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend docs/migrations/capability-v1-retirement.md
git commit -m "refactor: retire capability v1 bypasses"
```

### Task 21: 建立完整验收套件和发布门禁

**Files:**
- Create: `backend/tests/acceptance/test_consumer_parity.py`
- Create: `backend/tests/acceptance/test_failure_recovery.py`
- Create: `backend/tests/acceptance/test_security_matrix.py`
- Create: `backend/tests/acceptance/test_catalog_release.py`
- Create: `backend/tests/acceptance/fixtures/`
- Create: `backend/scripts/run_capability_v2_acceptance.py`
- Create: `.github/workflows/capability-v2-nightly.yml`
- Create: `.github/workflows/capability-v2-release.yml`
- Create: `docs/acceptance/capability-v2-report.schema.json`

**Interfaces:**
- Produces: immutable acceptance report bound to Git Commit, Catalog Release, Schema Hashes, Migration version, Provider artifacts and environment ID.
- Release command exits non-zero for failed, skipped or missing mandatory cases.

- [ ] **Step 1: Write a failing acceptance-manifest completeness test**

```python
def test_every_stable_capability_has_mandatory_cases(catalog, case_manifest):
    required = {"success", "invalid_input", "unauthenticated", "resource_denied", "output_contract", "consumer_contract", "version_pin"}
    for descriptor in catalog.stable_descriptors:
        assert required <= set(case_manifest[descriptor.key])
```

- [ ] **Step 2: Run acceptance in offline mode and verify missing cases block release**

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict`.

Expected: FAIL with exact missing cases, never a generic coverage percentage.

- [ ] **Step 3: Add deterministic fixtures and tiered workflows**

PR runs schema/unit/provider/architecture/consumer contracts. Nightly runs concurrency, fault injection, multi-instance and plugin/Agent/MCP E2E. Release Candidate runs isolated OceanBase, OIS, JWT/OAuth and Local Runtime. Developer-manual examples execute as tests.

- [ ] **Step 4: Run the complete release gate**

Run: `python backend/scripts/run_capability_v2_acceptance.py --mode release-candidate --strict --report docs/acceptance/latest.json`.

Expected: PASS with zero required skips and a report validating against `capability-v2-report.schema.json`.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/acceptance backend/scripts/run_capability_v2_acceptance.py .github/workflows/capability-v2-nightly.yml .github/workflows/capability-v2-release.yml docs/acceptance
git commit -m "test: gate capability v2 releases on full acceptance"
```

## Execution Checkpoints

### Checkpoint A — Kernel 可用

Tasks 1–9（含 Task 2A）完成后必须证明：完整功能基线存在；服务源码可复现；领域所有权唯一且无新增跨域实现依赖；V2 Contract/Catalog/Identity/Gateway 生效；没有消费者 Registry 旁路；审批、幂等、Outcome、Audit、Artifact 和 Operation 通过故障测试。未达到不得开放业务 Plugin/Agent 写能力。

### Checkpoint B — 消费者安全可用

Tasks 10–13 完成后必须证明：开发者手册可自动生成；PluginMountSession 和 Agent Delegation 替代 Header/长期 JWT；Agent Run 可恢复和审批；MCP 固定 Catalog；Web Plugin Bridge 保留完整结果。

### Checkpoint C — 领域覆盖完成

Tasks 14–18 完成后必须证明：Revision、Diff、Ontology、Base Platform、Project Management、Knowledge、Craft、Digital Model、Simulation 和 Local Integration 的稳定功能覆盖差集为零，语义 Golden Cases 通过，每域能独立测试、发布和回滚。

### Checkpoint D — 旧架构退出

Tasks 19–21 完成后必须证明：Web 稳定功能走统一 Capability；旧 Registry/双 URL/来源 Header/运行时 DDL 退出；正式验收报告绑定 Catalog Release，所有强制用例通过且无跳过。

## Final Verification Commands

Backend:

```powershell
python backend/scripts/build_user_function_registry.py --check
python backend/scripts/generate_capability_docs.py --check
python -m pytest backend/tests -q
python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict
```

Node services:

```powershell
Push-Location services/agent-runtime; npm test; Pop-Location
Push-Location services/mcp-gateway; npm test; Pop-Location
```

Web:

```powershell
Push-Location E:\Projects\ai00_v3\workmanship-web; npm test; Pop-Location
```

Windows .NET CI:

```powershell
dotnet test local-runtime\Ai00.LocalRuntime.sln -c Release
```

Release Candidate:

```powershell
python backend/scripts/run_capability_v2_acceptance.py --mode release-candidate --strict --report docs/acceptance/latest.json
```

只有以上命令全部通过、强制用例无跳过、User Function Registry 稳定功能差集为零、Catalog Hash 在所有实例一致时，才允许进入正式发布评审。
