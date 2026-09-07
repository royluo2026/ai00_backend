# Windows desktop governance contract

The product is one Windows x64 Electron App. The backend and Capability Gateway remain cloud services. `ai00.desktop.windows-x64` identifies the authenticated App. The existing `web` consumer type classifies the interactive Gateway transport and preserves existing exposure contracts; it does not identify an independent browser product.

`jwt_service.sign_desktop_session` is a server-only seam for a verified `oauth2_pkce` principal. The OAuth adapter must verify state, redirect binding and PKCE before constructing that principal. There is no browser-token-to-desktop exchange endpoint. The signed token binds the actor, tenant, installation, App version, issue time and expiry. Authentication revalidates the claim and current user/tenant. Canonical invocation and confirmation reject consumer overrides in both the envelope body and payload. Gateway performs the same payload check, and compatibility adapters preserve the signed App identity.

Simulation owns the exact interactive consumer declarations in `connector_pairing.py` and `connector_runtime.py`, including pairing v2, takeover, compatibility preflight, plan dispatch and outcome reads. `DESKTOP_TRANSPORT_BINDINGS` separately identifies the twelve device protocol adapters and their authentication modes. Device identity remains `ai00.connector`; neither Renderer input nor App metadata supplies a device session credential.

Technical release approval is independent from Capability business approval. `DesktopReleaseApprovalService.verify` accepts the candidate plus server-resolved expected release identity and artifact hashes. Each Ed25519 authority signature covers the canonical `ai00.desktop.release-approval.v1` domain, complete approval body, reviewer and key ID. The server configures the signature threshold and resolves current release-authority keys, reviewer roles and approval revocation. Every verification rechecks those sources and the validity interval. Reviewers require `desktop_release_approver`, must be distinct, and cannot be the author. Unknown fields, changed artifacts, unavailable/revoked authority, invalid signatures and insufficient reviewers fail closed. The verifier does not issue approvals or set Capability `human_approved` or runtime evidence. Promotion and update must invoke it against their current trusted release inputs; its result is not a durable authorization token.

Run the repository generators:

```powershell
python backend/scripts/freeze_official_domains.py
python backend/scripts/build_capability_catalog.py --write
python backend/scripts/generate_capability_docs.py --write
python backend/scripts/build_user_function_registry.py
```

Generate desktop evidence through an immutable bootstrap, with isolation active at Python startup. From the repository root in PowerShell:

```powershell
$desktopRevision = git rev-parse --verify 'HEAD^{commit}'
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve desktop source commit' }
$desktopBootstrap = git show "${desktopRevision}:backend/scripts/desktop_governance_bootstrap.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot load committed desktop bootstrap' }
$desktopBootstrap | python -I -S - --bootstrap-commit $desktopRevision --write
if ($LASTEXITCODE -ne 0) { throw 'Desktop generation failed' }
```

Use `--check` instead of `--write` to reproduce the artifact's pinned source commit. The release gate uses `isolated_command()` to start the equivalent `python -I -S -c` Git-blob loader before it can report success. Neither path executes the working-directory generator or bootstrap, even if either file is replaced. The bootstrap and native implementation come from a commit resolved once; the source snapshot retains exact Git blobs, Python static imports, C# project dependencies and native Provider/Catalog checks. Installed dependency directories are added without running `.pth` or `sitecustomize` hooks.

Direct `python backend/scripts/build_desktop_app_governance.py --write/--check` is unsupported and exits with `isolated_bootstrap_required`; direct isolated invocation of that mutable file is also rejected. A normal Python process may already execute `sitecustomize` before any script can inspect its flags. The rejection does not undo that startup code and is not an isolation guarantee. Arbitrary replacement of a directly executed file can replace its rejection too; only the documented immutable-blob entry and the controlled governance caller are evidence-producing trust boundaries.

The desktop closure is a content-addressed candidate inventory derived from the fixed commit's trusted Registry, actual source references and Provider bindings. It contains exact descriptor/source hashes, conservative transitive references, and full Catalog generation errors. Full Catalog generation currently fails on sixteen unbounded collection paths across nine Knowledge v1 Capabilities; the last valid published Catalog and its generated manual are retained. Existing route-governance blockers and missing authoritative approvals remain unresolved. Electron call sites, AppHost/installer artifacts, nonliteral runtime dispatch, native MySQL and production runtime evidence require their owning later tasks' verification before promotion.
