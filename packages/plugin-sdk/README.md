# AI00 Plugin SDK (Manifest v2)

The first public runtime is a Web Plugin in a sandboxed iframe. It has no cookie, database, OIS, Electron IPC, Python import, shell, COM, or direct internal-router access. All useful work goes through capabilities explicitly declared in `plugin.json` and approved during tenant installation.

## Package format

The ZIP root contains `plugin.json` and the built web assets. `plugin.json` is the descriptor and does not contain the enclosing ZIP's hash. Submission adds a detached `artifact` envelope (`object_key`, `sha256`, `size`, `media_type`) before the publisher signs the canonical release document.

The platform verifies the publisher signature and ZIP, stores the immutable artifact in OIS, then an administrator reviews and platform-signs the release. A tenant install starts disabled. Enable, upgrade, health completion, rollback and revocation are explicit audited transitions.

A manifest may request only capabilities whose descriptor has `plugin_callable: true`. Use `GET /api/v1/capabilities?consumer=plugin` as the authoritative development catalog. Every invocation carries plugin id and version; the server re-checks the tenant installation state, active version, release status and exact grant. Browser-side checks are only an additional guard.

## Runtime

Instantiate `Ai00PluginClient` after page load and call `await client.ready()` before invoking. The client refuses undeclared capabilities locally; the host and Capability Kernel enforce the same grant independently. The deterministic builder automatically places `ai00-plugin-sdk.js` at the package root, so plugin code should import `./ai00-plugin-sdk.js`.

Do not put secrets in a Web Plugin. Do not use `postMessage` received from any source other than `window.parent`; the SDK binds every response to the host-issued per-instance channel token.


## Namespace storage

Request only the methods you use: `plugin.storage.get`, `plugin.storage.list`, `plugin.storage.put`, and `plugin.storage.delete`. The SDK exposes `storageGet`, `storageList`, `storagePut`, and `storageDelete`. Keys and values are isolated by tenant and plugin id; values are limited to 256 KiB and writes support optimistic versions. Uninstall follows the signed manifest data policy.

## Start a plugin

Copy `templates/web-capability` and follow its README. It is a deployable template with a valid Manifest v2 descriptor, sandbox UI, host-handshake handling, capability invocation and namespace storage.

## Deterministic build and staging acceptance

Build the reference release without editing its source descriptor:

```powershell
python tools/build_release.py examples/hello-capability --output-dir examples/hello-capability/dist
python tools/build_release.py examples/hello-capability --output-dir examples/hello-capability/dist --version 1.1.0
```

The builder produces a deterministic ZIP and detached `.release.json`. It rejects unsafe paths, symlinks, invalid identities, invalid SemVer, missing entries, embedded artifact metadata and publisher namespace mismatches. The optional version override rewrites only the packaged descriptor, so upgrade fixtures remain reproducible.

Sign each detached release with the publisher's Ed25519 private key:

```powershell
python tools/sign_release.py examples/hello-capability/dist/acme.ai00.hello-1.0.0.release.json publisher-private.pem
```

Never commit private keys or generated signature files. The complete staging sequence is documented in the repository root `PLUGIN_PLATFORM_ACCEPTANCE.md`.