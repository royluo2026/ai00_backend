# AI00 Third-Party Plugin Guide and Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale Feishu third-party plugin guide and add a repository-shared Skill that safely generates publisher keys and prepares verified `.ai00pkg` upload bundles.

**Architecture:** Keep policy and decision guidance in a concise Skill with two focused references. Put deterministic cryptographic and packaging operations in two importable Python helpers with tests. Maintain a Markdown source for the Feishu guide, then replace the requested live Wiki body and verify the rendered headings and key commands without changing its L3 classification or sharing settings.

**Tech Stack:** Python 3.12, `cryptography`, `zipfile`, `unittest`, AI00 Plugin SDK build/signing tools, Codex Skill format, Feishu Docs UI.

**Spec:** `docs/superpowers/specs/2026-09-23-third-party-plugin-guide-and-skill-design.md`

## Global Constraints

- Manifest 2.0 is the supported generic deterministic build path; Manifest 2.1 local Providers require the additional governed Provider path.
- Publisher keys use Ed25519; private PEM is PKCS#8 and public PEM is SubjectPublicKeyInfo.
- Never print, upload, commit, bundle, or transmit the publisher private key.
- Never overwrite an existing key or release bundle.
- `.ai00pkg` contains exactly `plugin.zip`, `release.json`, and `publisher.sig` at its root.
- No helper may register a publisher, upload a release, approve, publish, install, or alter governance state.
- Without a trusted current Snapshot and Release Gate, `machine_passed`, `human_approved`, and `runtime_verified` remain independent and `unverified` as applicable.
- Preserve all unrelated dirty changes.

## Review Focus

- Existing key files: key generation must fail before changing either file, and both original hashes must remain identical.
- Mismatched public/private keys: release preparation must fail before producing `.ai00pkg`.
- Tampered ZIP, release JSON, or signature: offline verification must fail with no success report.
- Manifest 2.1 passed to the generic 2.0 release helper: fail with an explicit governed-Provider message rather than silently down-converting.
- Feishu paste or editor virtualization: verify the final title, Manifest 2.0/2.1 section, key-generation commands, `.ai00pkg` contents, and governance boundary from a fresh DOM/readback.

---

### Task 1: Scaffold the shared Skill and lock down publisher key generation

**Files:**
- Create: `.agents/skills/ai00-plugin-development/SKILL.md`
- Create: `.agents/skills/ai00-plugin-development/agents/openai.yaml`
- Create: `.agents/skills/ai00-plugin-development/scripts/generate_publisher_keypair.py`
- Create: `.agents/skills/ai00-plugin-development/tests/test_release_helpers.py`

**Interfaces:**
- Consumes: `cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey`
- Produces: `generate_keypair(output_dir: Path, publisher_id: str) -> dict[str, str]`
- Produces files: `<publisher_id>-private.pem`, `<publisher_id>-public.pem`

- [ ] **Step 1: Initialize the Skill without example placeholders**

Run:

```powershell
python C:\Users\luoyi8\.codex\skills\.system\skill-creator\scripts\init_skill.py ai00-plugin-development --path .agents\skills --resources scripts,references --interface display_name="AI00 Plugin Development" --interface short_description="Build and prepare governed AI00 third-party plugins" --interface default_prompt="Use $ai00-plugin-development to prepare this AI00 plugin for development or release."
```

Expected: the Skill directory, `SKILL.md`, and `agents/openai.yaml` exist; no example placeholder files are created.

- [ ] **Step 2: Write failing key-generation tests**

Add these cases to `tests/test_release_helpers.py` using `unittest` and `tempfile.TemporaryDirectory`:

```python
def test_generate_keypair_matches_platform_fingerprint(self):
    result = keygen.generate_keypair(self.root, "huangjing")
    private = serialization.load_pem_private_key(Path(result["private_key"]).read_bytes(), password=None)
    public_pem = Path(result["public_key"]).read_text(encoding="utf-8")
    self.assertIsInstance(private, Ed25519PrivateKey)
    self.assertEqual(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw),
                     serialization.load_pem_public_key(public_pem.encode()).public_bytes(Encoding.Raw, PublicFormat.Raw))
    self.assertEqual(result["fingerprint"], hashlib.sha256(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).hexdigest())

def test_generate_keypair_refuses_overwrite_without_changing_files(self):
    first = keygen.generate_keypair(self.root, "huangjing")
    before = {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in first.items() if name.endswith("key")}
    with self.assertRaises(FileExistsError):
        keygen.generate_keypair(self.root, "huangjing")
    after = {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in first.items() if name.endswith("key")}
    self.assertEqual(before, after)
```

- [ ] **Step 3: Run the tests and verify RED**

Run:

```powershell
python .agents\skills\ai00-plugin-development\tests\test_release_helpers.py -v
```

Expected: import or attribute failure because `generate_publisher_keypair.py` is not implemented.

- [ ] **Step 4: Implement exclusive Ed25519 key generation**

Implement `generate_keypair` with:

```python
PRIVATE = serialization.PrivateFormat.PKCS8
PUBLIC = serialization.PublicFormat.SubjectPublicKeyInfo

def generate_keypair(output_dir: Path, publisher_id: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,127}", publisher_id):
        raise ValueError("publisher_id must be one lowercase namespace segment")
    output_dir.mkdir(parents=True, exist_ok=True)
    private_path = output_dir / f"{publisher_id}-private.pem"
    public_path = output_dir / f"{publisher_id}-public.pem"
    if private_path.exists() or public_path.exists():
        raise FileExistsError("publisher key output already exists; refusing to overwrite")
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(Encoding.PEM, PRIVATE, serialization.NoEncryption())
    public_bytes = key.public_key().public_bytes(Encoding.PEM, PUBLIC)
    _exclusive_write(private_path, private_bytes)
    try:
        _exclusive_write(public_path, public_bytes)
    except Exception:
        private_path.unlink(missing_ok=True)
        raise
    if os.name != "nt": private_path.chmod(0o600)
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"private_key": str(private_path), "public_key": str(public_path), "fingerprint": hashlib.sha256(raw).hexdigest()}
```

The CLI prints JSON containing paths and fingerprint only. It prints a Windows directory-ACL reminder to stderr and never reads the private bytes back into output.

- [ ] **Step 5: Run key-generation tests and verify GREEN**

Run the unittest command from Step 3.

Expected: both key-generation tests pass.

- [ ] **Step 6: Commit only Task 1 files**

```powershell
git add -- .agents/skills/ai00-plugin-development/SKILL.md .agents/skills/ai00-plugin-development/agents/openai.yaml .agents/skills/ai00-plugin-development/scripts/generate_publisher_keypair.py .agents/skills/ai00-plugin-development/tests/test_release_helpers.py
git commit -m "feat: scaffold AI00 plugin development skill"
```

### Task 2: Prepare and verify signed `.ai00pkg` bundles

**Files:**
- Create: `.agents/skills/ai00-plugin-development/scripts/prepare_signed_package.py`
- Modify: `.agents/skills/ai00-plugin-development/tests/test_release_helpers.py`

**Interfaces:**
- Consumes: `build_release.build(source, output_dir, version_override)` from the selected SDK root
- Consumes: generated Ed25519 private/public PEM paths
- Produces: `prepare_package(source: Path, sdk_root: Path, private_key: Path, public_key: Path, output: Path, version: str | None) -> dict[str, object]`
- Produces: verified `.ai00pkg` plus sibling ZIP, release JSON, and `publisher.sig`

- [ ] **Step 1: Add failing package tests**

Create a minimal Manifest 2.0 plugin fixture inside each temporary test directory. Test:

```python
def test_prepare_package_builds_exact_verified_bundle(self):
    result = prepare.prepare_package(self.plugin, SDK_ROOT, self.private, self.public, self.output, None)
    self.assertEqual(set(zipfile.ZipFile(self.output).namelist()), {"plugin.zip", "release.json", "publisher.sig"})
    self.assertEqual(prepare.verify_bundle(self.output, self.public)["artifact_sha256"], result["artifact_sha256"])

def test_prepare_package_rejects_mismatched_keys(self):
    other = keygen.generate_keypair(self.root / "other", "otherpub")
    with self.assertRaisesRegex(ValueError, "does not match"):
        prepare.prepare_package(self.plugin, SDK_ROOT, self.private, Path(other["public_key"]), self.output, None)

def test_verify_bundle_rejects_each_tampered_entry(self):
    prepare.prepare_package(...)
    for entry in ("plugin.zip", "release.json", "publisher.sig"):
        tampered = rewrite_one_entry(self.output, entry)
        with self.assertRaises(ValueError):
            prepare.verify_bundle(tampered, self.public)

def test_prepare_package_rejects_manifest_v21(self):
    set_schema_and_provides(self.plugin, "2.1")
    with self.assertRaisesRegex(ValueError, "governed Provider"):
        prepare.prepare_package(...)
```

- [ ] **Step 2: Run the package tests and verify RED**

Run:

```powershell
python .agents\skills\ai00-plugin-development\tests\test_release_helpers.py -v
```

Expected: failures because package preparation and verification do not exist.

- [ ] **Step 3: Implement build, signature, bundle, and readback verification**

Implementation requirements:

```python
def canonical_release(release: dict) -> bytes:
    return json.dumps(
        {"artifact_sha256": release["artifact"]["sha256"], "manifest": release},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")

def verify_bundle(bundle: Path, public_key: Path) -> dict[str, object]:
    with zipfile.ZipFile(bundle) as archive:
        if set(archive.namelist()) != {"plugin.zip", "release.json", "publisher.sig"} or len(archive.infolist()) != 3:
            raise ValueError("signed package must contain exactly release.json, publisher.sig and plugin.zip")
        release = json.loads(archive.read("release.json").decode("utf-8-sig"))
        package = archive.read("plugin.zip")
        signature = base64.b64decode(archive.read("publisher.sig").strip(), validate=True)
    digest = hashlib.sha256(package).hexdigest()
    if digest != release.get("artifact", {}).get("sha256") or len(package) != release["artifact"]["size"]:
        raise ValueError("plugin ZIP does not match release artifact")
    key = serialization.load_pem_public_key(public_key.read_bytes())
    if not isinstance(key, Ed25519PublicKey): raise ValueError("public key must be Ed25519")
    key.verify(signature, canonical_release(release))
    return {"artifact_sha256": digest, "version": release["version"], "plugin_id": release["plugin_id"]}
```

`prepare_package` must reject any source `plugin.json` whose `schema_version` is not `2.0`, dynamically load the SDK root's official builder, verify the private key's derived public key equals the supplied public key, create every output with exclusive mode, and delete a partial outer bundle after any failure.

- [ ] **Step 4: Run package tests and verify GREEN**

Run the unittest command from Step 2.

Expected: key generation, happy-path package, key mismatch, three tamper cases, and Manifest 2.1 rejection all pass.

- [ ] **Step 5: Commit only Task 2 files**

```powershell
git add -- .agents/skills/ai00-plugin-development/scripts/prepare_signed_package.py .agents/skills/ai00-plugin-development/tests/test_release_helpers.py
git commit -m "feat: prepare verified AI00 plugin upload bundles"
```

### Task 3: Write and validate the Skill guidance

**Files:**
- Modify: `.agents/skills/ai00-plugin-development/SKILL.md`
- Modify: `.agents/skills/ai00-plugin-development/agents/openai.yaml`
- Create: `.agents/skills/ai00-plugin-development/references/manifest-and-governance.md`
- Create: `.agents/skills/ai00-plugin-development/references/release-workflow.md`

**Interfaces:**
- Consumes: `generate_publisher_keypair.py` and `prepare_signed_package.py`
- Produces: automatic Skill routing for AI00 third-party plugin development and release preparation

- [ ] **Step 1: Write the compact Skill entrypoint**

The frontmatter is:

```yaml
---
name: ai00-plugin-development
description: Use when creating, updating, building, signing, packaging, or preparing release evidence for a third-party AI00 App plugin in an AI00 or workmanship workspace.
---
```

The body must route 2.0 work to the generic builder and 2.1 work to `references/manifest-and-governance.md`, require current Catalog lookup, preserve governance state boundaries, and link release/key operations to `references/release-workflow.md`. Keep the entrypoint under 500 words.

- [ ] **Step 2: Write the two references**

`manifest-and-governance.md` contains the exact 2.0/2.1 decision table, provider declaration requirements, owner and Descriptor requirements, and v2.6 governance status rules.

`release-workflow.md` contains exact PowerShell commands for:

```powershell
python .agents\skills\ai00-plugin-development\scripts\generate_publisher_keypair.py --publisher-id huangjing --output-dir D:\AI00-Secrets\huangjing
python .agents\skills\ai00-plugin-development\scripts\prepare_signed_package.py --source .\my-plugin --sdk-root .\packages\plugin-sdk --private-key D:\AI00-Secrets\huangjing\huangjing-private.pem --public-key D:\AI00-Secrets\huangjing\huangjing-public.pem --output .\dist\huangjing.my-plugin-1.0.0.ai00pkg
```

It explains that only the public PEM and displayed fingerprint go to the super-admin registration UI, while the private PEM remains local.

- [ ] **Step 3: Validate the Skill**

Run:

```powershell
python C:\Users\luoyi8\.codex\skills\.system\skill-creator\scripts\quick_validate.py .agents\skills\ai00-plugin-development
python .agents\skills\ai00-plugin-development\tests\test_release_helpers.py -v
```

Expected: validator passes with no scaffold placeholders; all helper tests pass.

- [ ] **Step 4: Commit Skill documentation**

```powershell
git add -- .agents/skills/ai00-plugin-development
git commit -m "docs: add governed AI00 plugin development workflow"
```

### Task 4: Replace the repository guide source

**Files:**
- Create: `docs/plugin-platform-third-party-developer-guide.md`
- Modify: `docs/superpowers/specs/2026-09-23-third-party-plugin-guide-and-skill-design.md` only if implementation reveals a factual mismatch

**Interfaces:**
- Consumes: current Manifest parser, SDK, signing, bundle, lifecycle, and governance behavior
- Produces: canonical source text for the live Feishu Wiki

- [ ] **Step 1: Write the guide using the approved 14-section structure**

Include copyable examples for:

- minimal Manifest 2.0;
- Manifest 2.1 `provides` fragment with a warning that declaration is not approval;
- `CapabilityResult.ok` handling;
- key generation and fingerprint comparison;
- public-key registration versus private-key custody;
- build/sign/bundle commands;
- `.ai00pkg` contents;
- lifecycle roles and governance state table;
- common errors including `marketplace_state_conflict`, `authentication_stale`, `plugin_mount_unavailable`, signature mismatch, immutable version conflict, and missing governed Provider binding.

- [ ] **Step 2: Run factual static checks**

Run a Python check that asserts the guide contains `schema_version` examples for both `2.0` and `2.1`, `publisher-private.pem`, `publisher-public.pem`, `publisher.sig`, `.ai00pkg`, all three exact bundle entry names, `CapabilityResult.ok`, and `machine_passed=unverified`; assert it does not claim the private key is uploaded or that local tests create approval.

Expected: PASS.

- [ ] **Step 3: Cross-check commands against real CLIs**

Run:

```powershell
python packages\plugin-sdk\tools\build_release.py --help
python packages\plugin-sdk\tools\sign_release.py --help
python backend\scripts\build_plugin_upload_bundle.py --help
python .agents\skills\ai00-plugin-development\scripts\generate_publisher_keypair.py --help
python .agents\skills\ai00-plugin-development\scripts\prepare_signed_package.py --help
```

Expected: every command shown in the guide uses accepted arguments.

- [ ] **Step 4: Commit the guide source**

```powershell
git add -- docs/plugin-platform-third-party-developer-guide.md docs/superpowers/specs/2026-09-23-third-party-plugin-guide-and-skill-design.md
git commit -m "docs: rewrite third-party AI00 plugin guide"
```

### Task 5: Update and verify the live Feishu Wiki

**Files:**
- External document: `https://li.feishu.cn/wiki/EkDEwtePziYon8kw1tgcioconxj`

**Interfaces:**
- Consumes: `docs/plugin-platform-third-party-developer-guide.md`
- Produces: updated live Wiki with unchanged L3 classification and share settings

- [ ] **Step 1: Reopen the exact Wiki and verify identity**

Confirm the page URL and current title `AI00 第三方 Web 插件开发者与开发 Agent 指南(待更新）`. Record the visible `敏感（L3）` classification. Do not open or edit sharing settings.

- [ ] **Step 2: Replace the title and body**

Set the title to `AI00 第三方插件开发与发布指南`. Replace the document body with the canonical guide, using rich HTML paste so headings, lists, code blocks, and tables remain structured. This edit is already authorized by the user's request.

- [ ] **Step 3: Verify the live document from a fresh readback**

Reload the page and verify all Review Focus UI anchors:

- title is updated and L3 remains visible;
- both `Manifest 2.0` and `Manifest 2.1` appear;
- Ed25519 key generation command appears;
- the page says only the public key is registered and the private key remains local;
- `.ai00pkg` lists exactly `plugin.zip`, `release.json`, `publisher.sig`;
- governance section states local checks do not create formal approval or trusted `machine_passed`.

If any anchor is missing, restore from the repository guide and repeat the readback once. Do not change permissions, comments, or classification.

### Task 6: Final verification and delivery

**Files:**
- Verify only: all Task 1–4 files and the live Wiki

**Interfaces:**
- Consumes: completed Skill, scripts, guide, and Wiki
- Produces: final delivery report with exact evidence and human-only next steps

- [ ] **Step 1: Run the final focused suite**

```powershell
python .agents\skills\ai00-plugin-development\tests\test_release_helpers.py -v
python C:\Users\luoyi8\.codex\skills\.system\skill-creator\scripts\quick_validate.py .agents\skills\ai00-plugin-development
python -m pytest backend\tests\test_plugin_package_upload.py backend\tests\test_plugin_platform_next.py -q -p no:cacheprovider
```

Expected: all new helper tests pass, Skill validation passes, and platform package/signature regression tests pass.

- [ ] **Step 2: Perform a disposable end-to-end release preparation**

In a temporary directory, copy the official Manifest 2.0 template, generate a disposable publisher keypair, prepare `.ai00pkg`, verify it, then remove the temporary directory. Record only plugin ID, version, public fingerprint, artifact SHA-256, package size, and PASS; never record private key contents.

- [ ] **Step 3: Report completion accurately**

Report:

- Wiki URL and updated title;
- Skill path and invocation name;
- test counts and commands;
- disposable package verification result;
- formal governance states remain unchanged;
- developers still need an authorized super-admin to register the public key and review a submitted release.
