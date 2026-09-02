# Capability Governance Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Capability V2 从“目录和契约已生成”收口为“所有稳定业务消费路径可证明地经过 Gateway，并由运行时证据发布”。

**Architecture:** 保留现有 Capability Gateway、领域 Provider、Application Service 和 Repository 分层。新增跨仓库消费路径证据层，先扫描 Web/REST/Plugin/Agent/MCP 的真实入口，再以 descriptor 为唯一事实源生成暴露、验收和发布证据；旧 REST 只保留为无业务逻辑的兼容适配器。

**Tech Stack:** Python 3、AST/正则静态扫描、pytest、现有 Capability V2 catalog/registry/gateway、Node Web source tree。

**Spec:** `docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md`

## Global Constraints

- 不删除或覆盖已有用户未提交改动。
- stable business action 必须有 Gateway path evidence；只存在 registry 映射不算迁移完成。
- ui_transient、internal_protocol、operations 类接口可以保留 REST，但必须显式登记 allowlist。
- 所有新增扫描器 fail-closed；解析失败或路径不可读必须报告错误。
- 每个生产行为先写失败测试，再写最小实现，再运行定向测试。
- 运行时发布前必须有 clean commit、组件实际运行证据和 0 bypass。

### Task 1: Cross-repository Web route inventory

**Files:**
- Create: `backend/capability_v2/consumer_routes.py`
- Create: `backend/scripts/check_web_capability_routes.py`
- Test: `backend/tests/test_capability_v2_consumer_routes.py`

**Interfaces:**
- `scan_web_routes(root: Path, roots: Sequence[str], legacy_prefixes: Sequence[str]) -> RouteScanReport`
- `RouteScanReport.serialized() -> dict[str, object]`
- CLI accepts `--web-root`, `--fail-on-legacy`, and emits JSON evidence.

- [x] Write a failing test for literal legacy routes, capability invoke routes, tests/dist exclusion, and syntax-error fail-closed behavior.
- [x] Run the focused test and verify it fails because the scanner does not exist.
- [x] Implement the scanner and CLI with source path, line, route, route kind, and method evidence.
- [x] Run focused tests and the CLI against the V2 Web worktree.

### Task 2: Consumer-path truth in completion evidence

**Files:**
- Modify: `backend/capability_v2/completion.py`
- Modify: `backend/governance/capability_v2_completion.json`
- Modify: `backend/scripts/check_capability_v2_completion.py`
- Test: `backend/tests/test_capability_v2_completion.py`

- [x] Add a separate `web_consumer_bypasses` field without changing legacy fixture semantics.
- [x] Make strict completion fail when a configured Web route is not explicitly allowlisted or proven to invoke Gateway.
- [x] Add a generated JSON route evidence artifact and drift check.

The Web inventory now supports an explicit internal-protocol allowlist; the
three Flow metadata/test endpoints are recorded as six allowlisted uses across
the current Web tree. Flow CRUD/run/history, the Project/Vehicle Model
management page, the Factory resource page, and BOP version/project/factory
discovery now invoke capabilities through the Web client. The current scan
reports 331 executable legacy route uses after comment-only references are
excluded by the fail-closed scanner; all remaining routes remain release-gate
blockers. The lineage viewer now routes exact BOP version reads and version
discovery through `craft.bop.version.get/list`, including the lifecycle panel
and version manager, removing ten additional browser bypasses without
changing lifecycle mutation semantics. The Craft version-list output contract
now carries the UI-required family, maturity, lifecycle timestamps, factory,
PBOM and vehicle fields; Web bridges normalize the native `version_gid`/
`family_gid`/`archived` names at the compatibility boundary so grouping and
filtering do not silently regress.

### Task 3: Agent Skill/Flow Gateway convergence

**Files:**
- Modify: `plugins/agent/agent_backend/routers/skills.py`
- Modify: `plugins/agent/agent_backend/routers/flows.py`
- Modify: corresponding agent capability providers/application services
- Test: focused Skill/Flow gateway path tests

- [x] Add red tests proving the registered Flow/Skill routers use the Agent Capability adapter.
- [x] Replace registered Flow/Skill router SQL with Gateway adapters and move persistence into the Agent Repository provider path.
- [x] Add static guard forbidding `get_agent_conn` and SQL in the registered stable Flow/Skill handlers.

### Task 4: Contract and exposure hardening

**Files:**
- Modify: reviewed domain descriptor sources, especially Project Management
- Modify: catalog and exposure generation
- Remove/replace: `backend/capabilities/agreed_catalog.py` as a second truth source
- Test: descriptor schema, exposure matrix, and generated artifact drift tests

- [ ] Split generic operation envelopes where permission/risk/idempotency differs.
- [ ] Make exposure deny-by-default and require explicit consumer grants.
- [ ] Generate all projections from domain descriptors and remove manual global capability lists.

The machine audit groundwork is now available through
`backend/scripts/check_capability_v2_catalog_audit.py`; it currently reports
30 generic operation descriptors, 0 open argument schemas, and 0 stable
descriptors exposed to all five consumer classes by an implicit adapter
default. Every native provider now records `exposure_policy_source` as an
explicit reviewed grant; adapter defaults remain distinguishable and are
rejected by the release audit. These counts are findings, not an allowlist and
therefore do not mark this task complete. Knowledge's five
reviewed envelopes and 25 Project envelopes now publish explicit operation
enums and closed top-level argument objects. Six Project capabilities with no
application outcomes were moved to `deprecated` with an empty operation enum,
so they remain discoverable for compatibility but are no longer invocable. The
same fail-closed treatment now covers the 11 unbound Craft reviewed identities
and 2 unbound Local Runtime device identities.

Project browser searches now receive access scope server-side in the reviewed
capability handler, preventing callers from forging team/project membership
while removing the need for Web code to reconstruct database-derived scope.

### Task 5: Runtime evidence and release gate

**Files:**
- Modify: V2 acceptance runner and release evidence scripts
- Create: runtime consumer parity and negative bypass tests
- Documentation: governance closure acceptance record

- [ ] Run Backend, Agent Runtime, Plugin, MCP, Local Runtime and database components.
- [ ] Verify same capability outcome, permission, confirmation, idempotency, and audit across consumers.
- [ ] Require clean tree, runtime evidence hash, zero skip, and zero bypass for release.

The static fail-closed gate is now available through
`backend/scripts/check_capability_v2_release_gate.py`. It intentionally fails
against the current V2 state until the Web route inventory and catalog debt
are resolved; runtime component evidence remains a later task. The offline
contract runner now emits a passing report for 248 stable capabilities with
1736/1736 mandatory cases and zero skips; its Windows harness excludes only
the runner-self-test fixture that creates ACL-protected temporary Git trees.
