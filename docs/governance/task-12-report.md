# Task 12 — Windows x64 local packaging and release evidence

Status: **local content artifact produced; Task 12 release/pilot acceptance remains blocked and incomplete**. No signing, approval, pilot, installation, publication, merge or push is claimed.

## Changes and immutable identities

Frontend source commits: `3612c7a00d0528cd0aae41cebf3129446ef52a56` (`build: package governed Windows x64 App`), `27501b128d25ea3b732ca26f599caa607c23629d` (legacy update/publication retirement, installed Electron reuse and scanner compatibility), and `2ea7ed1f9eb4d9f6b3a98847d563bcaa69e80fe2` (production main-process EPIPE protection). Backend source: `0d004c3976161931c989bc4e05523535a8c22ced` (`governance: define Electron App release evidence`). A following evidence-only commit binds these exact commits, source trees, generated closure and actual file hashes in `docs/acceptance/electron-app-release-candidate.json`.

The supported builder configuration is NSIS Windows x64 only, with one Start Menu shortcut and no desktop shortcut, Service, independent Tray or SessionHost. Connector resources allow only `AI00.ConnectorHost.exe`. The existing Electron 41.8.0 native addon is unpacked outside ASAR. Production Vite assets and official manifests/handlers are included. Source, tests, PDBs, Python, credentials, journals and prior installers are excluded from the artifact. Uninstall configuration removes Connector security state and the App installation/updater identity while retaining App document files and user document directories; actual uninstall remains unexecuted.

ConnectorHost is published self-contained with `PublishSingleFile=true`, embedded native runtime libraries and no debug symbols. The first publish failed on IL3000 at legacy `AdapterManifestLoader.LoadBuiltIn`. That method requires an actual signed assembly file and is unused by AppHost, which uses its compiled adapter. `RequiresAssemblyFiles` now declares that existing legacy API limitation. No signature verifier was weakened and no directory was substituted for an executable path. The exact publish command then passed.

Legacy electron-updater auto-download/quit-install code and the old release workflow were retired. The signed production command has no unsigned parameter and fails closed: certificate, authoritative approval and real signed install/update integration are unavailable. **It does not yet implement signed production assembly or a complete NSIS transactional update path.** The release-policy helper checks exact signed bytes, RSA-PSS, trusted/revoked keys and validity, HTTPS origin, channel, component hashes, publisher result, versions, Catalog, security floor and schema compatibility. It is a tested source-side policy helper, not an installed updater. Its atomic-pointer helper is tested only on a temporary filesystem; incompatible state returns `requiresRepairing`, and real re-pairing/new-generation orchestration remains pilot work.

The pilot harness can emit a bounded template covering install, upgrade, failed update, rollback, repair, uninstall, single instance, Host exit, VisMockup survival/absence, pairing, wake, normal/duplicate plans, network loss, App/Host crash, COM timeout and reconciliation. Every case is `not_run`; it is not an automated real pilot. The existing capture poll is bounded to five minutes. The closed release schema binds all required policy and component fields; synthetic schema examples are explicitly not approval evidence.

`capture_app_ui_baseline.js` and local packaging reuse a small stdout/stderr handler that ignores only `error.code === 'EPIPE'`. Other stream errors are rethrown. This directly addresses the reported disconnected harness output pipe without hiding other failures.

## Artifact and checks

Local-only installer: frontend `dist/app-local-content/AI00-UNSIGNED-CONTENT-ONLY-1.0.3-win-x64.exe`.

Installer SHA256: `6af8e60a504246124c48ae5a777df6981cc458d6ac62f85397758e982236ac43`. Actual `Get-AuthenticodeSignature` result: `NotSigned`. The empty Host signature and explicit inert local manifest cannot pass Host startup trust. No installer was executed.

- TDD: installer configuration/allowlist, signed update policy/staged-pointer failure, EPIPE behavior, release schema and pilot template all failed before implementation and passed after it. Additional RED checks caught the legacy updater/workflow and absent installed-Electron reuse.
- Actual unpacked artifact inspection passed: 79 external files and 1,107 ASAR entries; exact Connector file allowlist, required native unpack and forbidden contents verified.
- Production web build passed. Local NSIS build passed twice; final build copies installed Electron distribution after checking package version `41.8.0`, PE x64 machine and recording executable SHA256.
- Full frontend `npm test` passed with `AI00_BACKEND_ROOT` set (Web 154/154). Initial run without that environment failed on the expected sibling backend fixture path. Final security, ConnectorHost manager/lifecycle, packaging, web defaults, AST scanner adversarial checks and UI structure checks passed.
- Runtime scanner: 272 files, 0 literal and 0 dynamic business transport violations, eight documented auth exceptions and zero parse errors.
- Final `.NET Release`: 153 passed, 0 failed, 0 skipped. Backend release-evidence tests: 2 passed.
- Backend full `pytest backend/tests plugins/simulation/tests -q` was interrupted at 57% after observed failures/errors, to avoid blocking the requested local handoff. No complete failure summary or traceback was emitted, so those failures are untriaged, not attributed to a cause or credited as passed.
- Root local smoke started the final backend and development App shell, then rebuilt and started `win-unpacked/AI00.exe`. The packaged App showed one main window, rejected a second instance, and exited with zero App/Host processes. No post-fix EPIPE was logged. Backend `/health` passed; `/ready` remained blocked only by `DatabaseNotMigratedError` in the configured test database. This is local shell evidence, not a signed product pilot.
- The existing Task10 compiled addon was reused. The packaged shell loaded successfully, but unsigned trust correctly prevented ConnectorHost startup; native Host control is not credited as a signed pilot.
- Fresh screenshots were not captured. UI structure passed; attempting to reuse the existing baseline/current screenshots rejected a fixture digest mismatch. The Task11 report retains its own earlier eight-view result, which is not relabeled as Task12 evidence.
- Immutable Git-blob bootstrap generation and check passed for backend source `0d004c3976161931c989bc4e05523535a8c22ced`. Direct mutable generator invocation was rejected as designed. The full Catalog/release gate was not rerun; existing Knowledge, route/audit/Registry and native MySQL release blockers remain.

Logs: frontend `.superpowers/task-12-{build,nsis-final,npm-test,scanner-current,native,existing-ui-comparison}.*`; backend `.superpowers/sdd/2026-09-07-governed-electron-app-migration/task-12-{python,dotnet-final,impact,impact-check}.log`.

## Governance and remaining work

`machine_passed=false`, `human_approved=false`, `technical_release_approved=false`, `runtime_verified=false`, `release_ready=false`, `pilot_ready=false`. Code-signing identity, trusted production release configuration, signed manifest/Authenticode chain, fully integrated coordinated update/re-pairing/rollback and actual install/uninstall/repair/VisMockup/Feishu pilot remain required. No exception or approval was fabricated. No subagents, GitLab, push, merge or publish were used.

## Root local smoke handoff

Backend terminal, from the backend worktree:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Frontend web terminal, from the frontend worktree:

```powershell
$env:AI00_BACKEND_ROOT='E:\Projects\ai00_v3\.worktrees\orchestration-merge-backend-20260905'
npm run dev
```

Frontend Electron terminal:

```powershell
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$env:AI00_VITE_DEV='1'
$env:AI00_BACKEND_URL='http://127.0.0.1:8080'
npm run app
```

This exercises the local backend and App shell. Production desktop authentication/Capability origin still requires configured HTTPS and real Feishu; unsigned/unpackaged ConnectorHost correctly stays unavailable. Local shell smoke is not a signed product pilot.
