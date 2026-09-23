# Publisher Keys and Release Workflow

Run commands from the repository root. Store publisher keys outside the repository and outside synced folders.

## 1. Generate a publisher key pair

```powershell
python .agents\skills\ai00-plugin-development\scripts\generate_publisher_keypair.py --publisher-id huangjing --output-dir D:\AI00-Secrets\huangjing
```

The command creates:

- `huangjing-private.pem`: Ed25519 private key in PKCS#8 PEM form;
- `huangjing-public.pem`: Ed25519 public key in SubjectPublicKeyInfo PEM form;
- a SHA-256 fingerprint of the raw 32-byte public key, printed with the two paths.

It refuses to overwrite either file. On Windows, restrict `D:\AI00-Secrets\huangjing` to the developer account with a user-only ACL and protect it with the normal encrypted backup process. Never paste, upload, email, commit, or bundle `huangjing-private.pem`.

Give an authorized super-admin only `huangjing-public.pem` and the displayed fingerprint. Compare the fingerprint shown after platform registration with the local value over a separate trusted channel. Publisher registration is immutable; key replacement uses the audited rotation workflow.

## 2. Prepare a Manifest 2.0 upload file

```powershell
python .agents\skills\ai00-plugin-development\scripts\prepare_signed_package.py --source .\my-plugin --sdk-root .\packages\plugin-sdk --private-key D:\AI00-Secrets\huangjing\huangjing-private.pem --public-key D:\AI00-Secrets\huangjing\huangjing-public.pem --output .\dist\huangjing.my-plugin-1.0.0.ai00pkg
```

The helper:

1. verifies the private and public keys match;
2. invokes the selected SDK root's official deterministic Manifest 2.0 builder;
3. signs the platform's canonical release bytes with Ed25519;
4. writes sibling build evidence and a single `.ai00pkg`;
5. reopens the `.ai00pkg` and verifies size, SHA-256, signature, plugin ID, and version.

The `.ai00pkg` root contains exactly:

```text
plugin.zip
release.json
publisher.sig
```

All outputs are exclusive-create. Use a new immutable SemVer or remove a disposable failed output deliberately; the helper never overwrites.

Manifest 2.1 is rejected with a governed-Provider message because its Provider artifact and governance binding require the project-specific 2.1 release path.

## 3. Human lifecycle steps

An authorized super-admin registers the public key, uploads the `.ai00pkg`, reviews it, and publishes an approved immutable version. A tenant admin then installs/enables it. Developers must not treat successful local verification as review, publication, installation, `machine_passed`, `human_approved`, or `runtime_verified`.
