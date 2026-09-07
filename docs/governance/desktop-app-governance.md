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
python backend/scripts/build_desktop_app_governance.py --write
```

The desktop closure is a content-addressed candidate inventory derived from the trusted live Registry, actual source references and Provider bindings. It contains exact descriptor and source hashes, conservative transitive references, and the full Catalog generation errors. It is not a replacement Catalog release. `--check` recomputes it. Full Catalog generation currently fails on sixteen unbounded collection paths across nine Knowledge v1 Capabilities; the last valid published Catalog and its generated manual are retained. Existing route-governance blockers and missing authoritative approvals remain unresolved. Electron call sites, AppHost/installer artifacts, dynamic dispatch, native MySQL and production runtime evidence must be verified by their owning later tasks before promotion.
