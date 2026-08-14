# Capability V2 LAN Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagents are prohibited for this work.

**Goal:** Expose the Capability V2 test service to the local development team at `http://pc-pc2l7vve:8094/web/` and make Feishu OAuth return to that same service.

**Architecture:** Uvicorn listens on all IPv4 interfaces at port 8094, while a Windows Firewall rule restricts inbound access to the domain-authenticated local subnet. The frontend and API remain same-origin. Feishu OAuth uses the hostname-based 8094 callback, and only the Capability V2 Windows service is restarted.

**Tech Stack:** PowerShell, NSSM Windows service, Uvicorn/FastAPI, Windows Defender Firewall, Feishu OAuth.

## Global Constraints

- Do not use subagents or create worktrees.
- Modify only `AI00Backend-CapabilityV2`; do not modify the old service.
- Keep port `8094`; change the Uvicorn listener from `127.0.0.1` to `0.0.0.0`.
- Restrict the inbound rule to TCP 8094, the Domain profile, and `LocalSubnet`.
- Do not expose database, MinIO, or other internal service ports.
- Set `FEISHU_REDIRECT_URI` exactly to `http://pc-pc2l7vve:8094/auth/feishu/callback`.
- Back up runtime files before editing. Do not commit backups, secrets, tokens, or passwords.
- Preserve `CODEX-DESKTOP-HANDOFF.md` and `docs/superpowers/reviews/` unchanged.
- Do not push or merge.

---

### Task 1: Capture the failing deployment assertions

**Files:**
- Inspect: `E:/Projects/ai00_v3/.runtime/deployment/start-capability-v2.ps1`
- Inspect: `E:/projects/ai00-v2/backend/.env.v2.runtime`
- Inspect: Windows Firewall rule `AI00 Capability V2 LAN 8094`

**Interfaces:**
- Consumes: Current service and runtime configuration.
- Produces: A read-only assertion report proving the listener, callback, and hostname access are not yet compliant.

- [ ] **Step 1: Assert the required listener and callback values**

Run a PowerShell assertion that checks the startup script contains
`--host 0.0.0.0`, the environment contains the exact 8094 callback, and the
firewall rule is present with `Profile=Domain`, `RemoteAddress=LocalSubnet`,
and `LocalPort=8094`.

- [ ] **Step 2: Verify the assertion fails for the diagnosed reasons**

Expected: the listener assertion reports `127.0.0.1`, the callback assertion
reports port `8082`, and the required firewall rule is absent or noncompliant.

### Task 2: Back up and update runtime configuration

**Files:**
- Modify: `E:/Projects/ai00_v3/.runtime/deployment/start-capability-v2.ps1`
- Modify: `E:/projects/ai00-v2/backend/.env.v2.runtime`
- Create locally: timestamped `.bak` copies beside both files

**Interfaces:**
- Consumes: The exact diagnosed values from Task 1.
- Produces: A startup command with `--host 0.0.0.0` and the exact 8094 Feishu callback.

- [ ] **Step 1: Create timestamped backups**

Use `Copy-Item -LiteralPath` for each exact file, suffixing the destination with
`.bak-YYYYMMDD-HHMMSS`. Verify both backup files exist before editing.

- [ ] **Step 2: Apply two exact replacements**

Replace only `--host 127.0.0.1` with `--host 0.0.0.0` in the startup script.
Replace only the value of `FEISHU_REDIRECT_URI` with
`http://pc-pc2l7vve:8094/auth/feishu/callback` in the runtime environment.
Abort if either source pattern occurs other than exactly once.

- [ ] **Step 3: Re-run static assertions**

Expected: listener and callback assertions pass. No secret values are printed.

### Task 3: Add the restricted firewall rule and restart the new service

**Files:**
- Modify external state: Windows Firewall rule `AI00 Capability V2 LAN 8094`
- Restart external state: Windows service `AI00Backend-CapabilityV2`

**Interfaces:**
- Consumes: Updated runtime configuration from Task 2.
- Produces: A running service listening on all IPv4 interfaces, reachable only from the local subnet under the Domain profile.

- [ ] **Step 1: Create or normalize the firewall rule**

Create one enabled inbound allow rule with protocol TCP, local port 8094,
profile Domain, and remote address `LocalSubnet`. If a rule with the exact
display name exists, validate and update that rule rather than creating a
duplicate.

- [ ] **Step 2: Restart only Capability V2**

Run `Restart-Service AI00Backend-CapabilityV2`, wait for `Running`, and do not
issue any operation against the old service.

- [ ] **Step 3: Verify the process listener**

Expected: `netstat -ano` shows `0.0.0.0:8094 LISTENING`, and the owning process
is the Python process launched by `AI00Backend-CapabilityV2`.

### Task 4: Complete HTTP, OAuth, and service acceptance

**Files:**
- Inspect: deployed HTTP resources and service logs
- No product file changes

**Interfaces:**
- Consumes: The live listener and firewall rule from Task 3.
- Produces: Deployment evidence and the remaining Feishu-console action, if any.

- [ ] **Step 1: Verify both local access paths**

Use proxy-bypassed HTTP checks for `127.0.0.1:8094` and
`pc-pc2l7vve:8094`. Expected: `/health` and `/web/` return HTTP 200 for both.

- [ ] **Step 2: Verify generated OAuth metadata**

Call `/auth/feishu/login-url` and parse only its public query metadata.
Expected: `redirect_uri` exactly equals
`http://pc-pc2l7vve:8094/auth/feishu/callback`; do not print state or tokens.

- [ ] **Step 3: Verify firewall and service persistence**

Expected: firewall rule is enabled and restricted as specified; service is
`Running` with startup type `Automatic`.

- [ ] **Step 4: Check the new startup log cycle**

Expected: no `Traceback`, bind failure, static-resource 404, or callback
configuration error. Report whether Feishu Open Platform still needs the exact
8094 callback added to its redirect allowlist.

- [ ] **Step 5: Obtain a second-device LAN check**

A team developer opens `http://pc-pc2l7vve:8094/web/` from another computer on
the same local subnet. Expected: the login page loads. This is the only
acceptance item that requires an external device.

### Task 5: Record the runtime handoff

**Files:**
- Do not modify protected handoff or review files
- Inspect: Git status in the backend worktree

**Interfaces:**
- Consumes: Acceptance results from Task 4.
- Produces: A concise report of live URL, backup locations, firewall scope, service health, Feishu-console requirement, and the second-device check.

- [ ] **Step 1: Confirm repository scope**

Run `git status --short` and verify runtime backups, environment credentials,
and firewall state are not staged or committed.

- [ ] **Step 2: Report final access instructions**

Provide the team URL, exact OAuth callback, completed automated checks, and any
manual Feishu-console or second-device action still required. Do not push or
merge.
