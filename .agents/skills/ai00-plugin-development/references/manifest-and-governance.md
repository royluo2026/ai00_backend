# Manifest and Capability Governance

## Select the manifest

| Need | Manifest | Generic helper | Additional release work |
|---|---|---|---|
| Sandbox Web UI that consumes registered Capabilities | 2.0 | Supported | Publisher registration, review, publish, install |
| Plugin that supplies one or more local JavaScript Providers | 2.1 | Rejected deliberately | Governed Provider registration, binding, runtime fence, owner approval, evidence |

Both versions require a reverse-DNS `plugin_id` below `publisher_id`, SemVer, compatibility ranges, a safe Web entry, unique permissions, and declared Capability dependencies. Look up every consumed Capability and major in the current generated Catalog before editing the manifest.

## Manifest 2.1 Provider declaration

Each `provides` item requires:

- `id`: the supplied Capability ID;
- `major`: positive supported major;
- `owner_domain`: below the publisher namespace; the Capability ID must be below this owner namespace;
- `module`: canonical package-relative `.mjs` path without traversal;
- `export`: a non-reserved named export;
- `result`: `json` or `artifact`.

Provider `(capability_id, major)` pairs must be unique. A declaration does not make the Provider callable. The platform must bind the exact installed plugin release and Provider artifact under the local-provider runtime fence.

## Owner and Descriptor contract

For every supplied Capability, record the real owner domain and owner team. A governed Descriptor must define the business effect, business invariants, closed input/output/error schemas, side-effect level and list, authorization, transaction and idempotency policies, lifecycle, consumer references, exact Provider reference and artifact hash, API references, test references, and Catalog release identity. Generated candidates remain `unverified` until the responsible owner accepts the exact business-definition hash through the governance path.

Do not reuse an official Provider registration, borrow another owner's namespace, or infer approval from source presence. Plugin permission scope cannot grant access that the Provider contract does not authorize.

## v2.6 evidence states

Treat these as separate facts:

| State | Meaning | What can establish it |
|---|---|---|
| `machine_passed` | Required checks passed for the exact governed Snapshot/revision | Trusted test run bound to the Snapshot and Release Gate |
| `human_approved` | The accountable owner approved the exact business definition/release | Recorded governance approval for the exact hash/release |
| `runtime_verified` | The released Provider worked in the intended runtime | Bound runtime evidence for the installed release |

Local unit tests, an `.ai00pkg` signature, a chat message, or a successful build cannot set any other state. Without current trusted evidence, report each affected value as `unverified`; do not convert absence into `false`, `pass`, or approval.
