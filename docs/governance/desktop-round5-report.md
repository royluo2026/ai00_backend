# Task 11 — round5 nine-gap closure

The nine remaining route gaps (zero-based groups **28, 29, 45, 58, 59, 68, 71, 72, 73**) are closed with real owner-handler and production Gateway evidence. The frontend matrix now records `business_equivalence_gap_groups=[]` and `task_complete=true`. This closes the implementation and deterministic verification scope; production data migration and release approval have not occurred.

Backend source: `4353070c39266c53ba0e8336674f05aa61c21979`. Frontend source: `6d996519661b94b084be7aa448f6128cc0ee27c4`. Source and evidence are separate local commits. No push, merge, published Catalog replacement or publication occurred.

| Groups | Implemented and verified closure |
| --- | --- |
| 28, 29 | Owner-scoped historical resolution for Project Task/Issue, Knowledge entry/document, Craft rule and BOP version attachments. Actual parent SQL and active identity/tenant checks authorize stored references before Base pins an immutable ArtifactRef. Upgrade DDL and a bounded, idempotent migration command are included. Hash, size, MIME, path and parent checks reject cross-tenant, dangling and arbitrary-key/path requests. Renderer preview and subsequent saves use typed ArtifactRefs. |
| 45 | Actual Base Feishu directory sync service and persistence through Gateway policy and confirmation, followed by Main/facade projection. |
| 58 | Actual Craft rule mutation through Gateway. Reads and writes enforce tenant/owner predicates; v2 uses the existing production `rule.manage` permission. Cross-tenant mutation is rejected. |
| 59 | Actual Knowledge entry update handler, repository, Gateway confirmation and output projection. |
| 68, 71 | Closed Project Issue/Task update v2 definitions match real `arguments.gid`, bounded `updates`, and `{success:true}` output. All desktop consumers select v2 and normalize actual field inputs. Historical v1 definitions remain unchanged. |
| 72, 73 | Actual Project search, Follow list, Task search and Issue search constituents pass Gateway and Main/facade projection. Follow output excludes its internal `user_gid`, matching the existing closed public contract. |

Verification:

- **41 backend tests passed**, with two existing Pydantic deprecation warnings: round5 Base, Agent, Project, exchange, remaining, Gateway, gap closure, historical attachment and v1 immutability suites. Actual repositories/services run against deterministic SQL/storage/external ports; permission, confirmation and schema services are production implementations.
- **89 owner executions covering 85 distinct IDs/majors** pass the real Gateway and actual Main confirmation client/facade projection. The seven outcome fixtures include the nine previously missing handler outcomes and six authoritative historical parent cases. Local migration fixtures execute owner SQL through SQLite, real ArtifactService logic and repeated migration/resolution; they reject changed metadata, foreign tenants, dangling parents and arbitrary paths/keys.
- **78 unpublished closed candidates**: the previous 73 plus Task/Issue update v2 and three owner attachment resolvers. Provider freeze and isolated committed-bootstrap impact `--check` pass. Candidate fields remain `machine_passed=false`, `human_approved=false`, `runtime_verified=false`.
- Frontend runtime AST scan: **0 literal / 0 dynamic** business transport calls, 272 files, zero parse errors, eight existing authentication/bootstrap exceptions and the fixed Gateway boundary. Original coverage remains 76 groups / 115 literal occurrences / 43 dynamic entries. Scanner adversarial tests passed.
- Full `npm test` and `npm run build:web` passed (Web **154/154**, Agent canvas **14/14**). Artifact preview/save, native Artifact, Main projection and unchanged UI-structure checks passed.
- Real Electron **8/8 pixel and documented interaction comparisons passed** against original source `3223170e54b9f700105d9c872a6b7d489e0d60bf`: Electron 41.8.0, 1920×1080, scale 1.25, unique temporary userData directories, no masks or CSS overrides. Seven views have zero changed pixels; workspace differs by 1,651 pixels (0.07962%, below 0.1%). Current approval fixtures traverse pending → in_review → approved through Main and the facade. These are deterministic shell/interaction checks, not complete live business workflow coverage. Existing unbound fixture/asset diagnostics are retained in logs.

The executable upgrade procedure and local fixture command are in [desktop-historical-attachment-upgrade.md](desktop-historical-attachment-upgrade.md). Production migration was **not executed**. Historical rows lacking authoritative owner/tenant proof require business-data repair; no object-key-only download fallback exists.

The complete Catalog check still reports exactly **16 pre-existing Knowledge unbounded collection paths**, with no new candidate collection failures. Optional broad table-inventory and boundary audits are not clean: existing inventory drift and an existing unregistered Project desktop table remain, and the boundary scan also discovers ignored historical test-fixture directories. These unrelated failures are retained rather than expanded into this nine-gap task. Task completion does not grant release/runtime approval.

Evidence is in `backend/tests/fixtures/desktop_round5_{base,agent,project,file,remaining,gaps,historical}_outcomes.json`, [candidates](desktop-round5-candidates.json), [immutable impact closure](desktop-app-impact-closure.json), and `desktop-round5-gap-*.log`. The paired frontend repository contains the final route matrix, runtime scanner ledger, production build and fresh eight-view capture/comparison artifacts.
