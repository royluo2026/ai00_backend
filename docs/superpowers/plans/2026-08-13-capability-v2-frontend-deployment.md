# Capability V2 Frontend Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the existing Capability V2 Web/plugin-center implementation with the backend on `http://127.0.0.1:8094` and prove the sample plugin lifecycle and mounted capability path work after a Windows service restart.

**Architecture:** Keep one browser shell and the existing domain packages. Build the clean `workmanship-web` source repository, copy its generated static tree into the isolated backend worktree `dist`, and let FastAPI serve the UI and API from one origin. The Web plugin host continues to obtain signed tenant mounts from `/api/v1/plugin-marketplace/registry` and invokes only the exact granted Capability V2 contracts through the mount bridge.

**Tech Stack:** Vite 4, vanilla JavaScript, FastAPI, pytest/unittest, OceanBase MySQL mode, NSSM Windows service.

## Global Constraints

- Do not create subagents or additional worktrees.
- Do not modify or stage `CODEX-DESKTOP-HANDOFF.md` or `docs/superpowers/reviews/`.
- Preserve `AI00Backend-V2`; only restart `AI00Backend-CapabilityV2`.
- Keep the deployed backend bound to `127.0.0.1:8094`.
- Do not publish or push either repository without a new explicit user instruction.
- The frontend remains one shell; domain isolation is expressed through packages and Capability V2 contracts, not eleven independent frontend servers.

---

### Task 1: Runtime backend resolution regression

**Files:**
- Modify: `E:/Projects/ai00_v3/workmanship-web/scripts/test_runtime_backend_resolution.js`
- Modify: `E:/Projects/ai00_v3/workmanship-web/web/admin/ai_audit.html`

**Interfaces:**
- Consumes: `window.AI00RuntimeConfig.getRuntimeBackendBase(configBackendUrl)`.
- Produces: the AI audit fallback fetch uses the same resolved backend origin as the rest of the Web shell.

- [ ] **Step 1: Add `web/admin/ai_audit.html` to `runtimeFiles` in `scripts/test_runtime_backend_resolution.js`.**
- [ ] **Step 2: Run `node scripts/test_runtime_backend_resolution.js` and verify it fails on the inline `http://127.0.0.1:8080` fallback.**
- [ ] **Step 3: Replace the inline fallback with `AI00RuntimeConfig.getRuntimeBackendBase('')`, falling back only to `window.location.origin`.**
- [ ] **Step 4: Re-run `node scripts/test_runtime_backend_resolution.js` and verify it passes.**
- [ ] **Step 5: Run `npm test` in `E:/Projects/ai00_v3/workmanship-web`.**

### Task 2: Deployed plugin-center contract

**Files:**
- Create: `backend/scripts/check_frontend_deployment.py`
- Generate and synchronize: `dist/**`

**Interfaces:**
- Consumes: `E:/Projects/ai00_v3/workmanship-web/dist/**` from `npm run build:web`.
- Produces: FastAPI-served `/web/settings/index.html` references `/web/settings/plugin_center.js`, and that JavaScript contains the V2 catalog/installations/release workflow.

- [ ] **Step 1: Add an HTTP acceptance check that requests the running service UI/settings/plugin-center resources and validates the deployed settings page loads the V2 script.**
- [ ] **Step 2: Run `python backend/scripts/check_frontend_deployment.py --base-url http://127.0.0.1:8094` and verify it fails because the deployed plugin-center asset returns 404.**
- [ ] **Step 3: Run `npm run build:web` in `E:/Projects/ai00_v3/workmanship-web`.**
- [ ] **Step 4: Overlay the complete generated `workmanship-web/dist` tree into the isolated backend worktree `dist` without deleting unrelated user files.**
- [ ] **Step 5: Re-run the HTTP acceptance check and `python -m pytest backend/tests/test_plugin_center_contract.py -q`; verify both pass.**

### Task 3: Static deployment and service persistence

**Files:**
- Verify: `dist/web/index.html`
- Verify: `dist/web/settings/index.html`
- Verify: `dist/web/settings/plugin_center.js`
- Verify: `E:/Projects/ai00_v3/.runtime/deployment/logs/capability-v2.stderr.log`

**Interfaces:**
- Consumes: `AI00Backend-CapabilityV2` Windows service and its existing launcher.
- Produces: HTTP 200 for the UI, settings page, plugin-center asset, health and readiness after a real service restart.

- [ ] **Step 1: Run the focused frontend tests and backend plugin-center/mount/acceptance tests.**
- [ ] **Step 2: Restart only `AI00Backend-CapabilityV2`.**
- [ ] **Step 3: Verify `/health`, `/ready`, `/`, `/web/settings/index.html`, and `/web/settings/plugin_center.js` return successful responses.**
- [ ] **Step 4: Inspect the fresh service log cycle for `ERROR`, `Traceback`, asset 404s, or startup warnings.**

### Task 4: End-to-end plugin acceptance

**Files:**
- Execute: `backend/scripts/plugin_platform_acceptance.py`
- Verify: `workmanship_base_plugin_invocation_audit`

**Interfaces:**
- Consumes: the signed `acme.ai00.hello` sample package, MinIO/OIS, OceanBase, the plugin marketplace APIs, and the Capability V2 gateway.
- Produces: evidence for publish/review/install/enable/mount/invoke/upgrade rollback/disable/uninstall and a persisted completed invocation audit.

- [ ] **Step 1: Run the existing persistent plugin acceptance command against `http://127.0.0.1:8094`.**
- [ ] **Step 2: Verify the marketplace registry returns a mount URL and exact versioned grants while the sample plugin is enabled.**
- [ ] **Step 3: Verify the mounted plugin calls `craft.bop.version.list@1` successfully and persists a completed audit row.**
- [ ] **Step 4: Verify the acceptance cleanup leaves the sample plugin uninstalled.**
- [ ] **Step 5: Open the deployed root in the in-app browser and verify the real login UI loads without missing static assets; report that a human Feishu login is required for visual authenticated plugin-center interaction if no reusable session exists.**

### Task 5: Final verification and handoff

**Files:**
- Review: both repository status outputs
- Preserve: `CODEX-DESKTOP-HANDOFF.md`, `docs/superpowers/reviews/`

**Interfaces:**
- Consumes: all test, HTTP, database-audit, browser, and service evidence from Tasks 1-4.
- Produces: a concise handoff with access URL, verification counts, commit scope, and any action that still requires the user.

- [ ] **Step 1: Run `git diff --check` in both repositories.**
- [ ] **Step 2: Run fresh final test/build/HTTP verification commands and read their complete output.**
- [ ] **Step 3: Confirm no unrelated user files are staged or modified.**
- [ ] **Step 4: Commit each repository intentionally, without pushing.**
- [ ] **Step 5: Use `superpowers:finishing-a-development-branch` to present integration options.**
