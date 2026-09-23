---
name: ai00-plugin-development
description: Use when creating, updating, building, signing, packaging, or preparing release evidence for a third-party AI00 App plugin in an AI00 or workmanship workspace.
---

# AI00 Plugin Development

Build third-party App plugins against the repository's current contracts. Treat repository code and generated Catalog artifacts as authoritative; examples in old documents are not a substitute for a current lookup.

## Start Here

1. Locate the workspace root and read its `AGENTS.md` files.
2. Load `ai00-capability-governance` for Capability, Provider, Descriptor, lifecycle, or release work.
3. Inspect the current Catalog before choosing Capability IDs and majors. Do not invent an ID because a similar name appears in an example.
4. Read [manifest-and-governance.md](references/manifest-and-governance.md) and choose Manifest 2.0 or 2.1.
5. Keep source, generated files, keys, and output packages in separate directories.

## Choose the Path

- Use **Manifest 2.0** for a consumer-only sandbox Web plugin. Build it with the official generic builder through `scripts/prepare_signed_package.py`.
- Use **Manifest 2.1** only when the plugin supplies a local JavaScript Provider. A `provides` entry is a declaration, not approval. Complete the governed Provider, owner, Descriptor, test-evidence, binding, and runtime-fence path described in the reference. The generic helper intentionally rejects 2.1.

Use `CapabilityResult.ok` for new Web SDK code. Treat the deprecated `success` alias only as a compatibility input.

## Keys and Release Packages

Follow [release-workflow.md](references/release-workflow.md). Generate an Ed25519 publisher key pair once, keep the private PKCS#8 PEM outside the repository, and give only the public SPKI PEM plus its fingerprint to an authorized super-admin. Build a single `.ai00pkg` containing exactly `plugin.zip`, `release.json`, and `publisher.sig`; verify it offline before upload.

The helpers refuse overwrite and never register, upload, approve, publish, install, or alter governance state.

## Governance Boundary

Keep `machine_passed`, `human_approved`, and `runtime_verified` independent. Local tests and offline signature verification are useful evidence but do not create a trusted Snapshot, formal approval, or runtime verification. When current trusted evidence is absent, report the affected state as `unverified`. Never generate platform signing keys, mount secrets, database credentials, approval records, or Release Gate claims.
