# Capability V2 Domain Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking. Subagent-driven execution is prohibited by the repository owner.

**Goal:** Build the manifest-driven Provider, database, migration, cross-domain invocation and event foundation required to extract every Capability V2 domain without changing business behavior.

**Architecture:** Keep CapabilityGatewayService and Descriptor V2 as the execution kernel, but remove import-time domain registration from the registry. Load trusted official domain Providers, search exports and event subscriptions from one frozen manifest, give every target domain an explicit database/migration identity, and expose shared contracts for governed cross-domain invocation and outbox events. Existing business implementations remain authoritative during this foundation slice and are wrapped without semantic changes.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, PyMySQL, OceanBase MySQL mode, pytest, JSON Schema-style Capability contracts, PowerShell-compatible test commands.

## Global Constraints

- Web, REST, Plugin, Agent, MCP and Local Runtime use one Capability ID, Descriptor, Provider and Gateway path for the same business outcome.
- A route or internal function is evidence, not automatically a Capability.
- Tenant is explicit and never inferred from team, owner or a default value.
- No cross-domain SQL, JOIN, foreign key, Router, Repository, ORM, concrete Service or database-helper import.
- Each first-class domain owns its code, database, runtime credential, DDL credential, migration ledger, Provider and tests.
- Cross-domain synchronous work uses CapabilityGatewayService; asynchronous work uses versioned events plus Outbox/Inbox.
- DomainManifest is the only deployment declaration for search exports and event subscription version ranges.
- Central governance and frozen artifacts are finalized serially by one designated integrator against the latest integration HEAD.
- Do not add business capabilities, change business schemas or move business data in this foundation plan.
- Existing business data is empty; do not implement backfill, dual-write or legacy table views.
- Do not use subagents.

---

## Target File Map

### Shared kernel files

- Create backend/capability_v2/domain_manifest.py: immutable domain/provider/database manifest types and loader.
- Create backend/capability_v2/provider_loader.py: trusted artifact hashing, module loading and Provider registration.
- Create backend/capability_v2/bootstrap.py: side-effect-free construction of the complete runtime CapabilityRegistry.
- Create backend/capability_v2/domain_database.py: explicit per-domain database configuration parsing.
- Create backend/capability_v2/domain_client.py: governed server-side cross-domain invocation.
- Create backend/capability_v2/domain_events.py: versioned event, Outbox and Inbox contracts.
- Create backend/capability_v2/official_domains.json: frozen official Provider, database, search export and event subscription manifest.
- Delete backend/capability_v2/official_providers.json after all loader callers use official_domains.json.
- Modify backend/capabilities/registry_next.py: retain registry types only; remove domain imports and registrations.
- Modify backend/capability_v2/catalog.py: embed DomainArtifact metadata in releases without weakening existing provider hashes.
- Modify backend/plugin_loader.py: keep Web/plugin discovery; delegate official Capability loading to DomainProviderLoader.
- Modify plugins/device/manifest.json: rename the official package identity to official.local-runtime without changing its Capability contracts.

### Transitional official Provider modules

- Create backend/base/official_provider.py: register current Base/System/Plugin Platform capabilities.
- Create backend/knowledge/official_provider.py: register current Knowledge capabilities without moving implementation yet.
- Create backend/ontology/official_provider.py: register current Ontology capabilities without moving implementation yet.

### Runtime and deployment

- Modify backend/main.py: construct one registry through bootstrap before constructing the Gateway.
- Modify backend/capabilities/init_next.py and backend/capabilities/__init__.py: export the bootstrapped registry from bootstrap.
- Modify backend/capability_v2/gateway.py: resolve the default registry through bootstrap instead of registry import side effects.
- Modify backend/plugin_platform/service.py: receive or lazily resolve the bootstrapped registry.
- Modify backend/scripts/build_capability_catalog.py: build from one bootstrapped registry.
- Create backend/scripts/freeze_official_domains.py: deterministically refresh trusted artifact hashes.
- Create backend/scripts/run_domain_migrations.py: run one domain's migrations against its DDL URL.

### Governance and tests

- Modify docs/governance/domain-ownership.json and backend/governance/domain_boundaries.json: add Factory and Integration, rename Local Integration to Local Runtime, and declare target migration roots.
- Modify .github/CODEOWNERS: cover new domain roots and migration roots.
- Modify backend/scripts/check_domain_dependencies.py: fail on imports of private domain layers and allow only declared Public Ports/shared contracts.
- Create backend/tests/test_domain_manifest.py.
- Create backend/tests/test_domain_provider_loader.py.
- Create backend/tests/test_capability_bootstrap.py.
- Create backend/tests/test_domain_database_config.py.
- Create backend/tests/test_domain_migration_runner.py.
- Create backend/tests/test_domain_capability_client.py.
- Create backend/tests/test_domain_event_contracts.py.
- Modify backend/tests/test_domain_independence_v2.py.
- Modify backend/tests/test_capability_provider_loading.py.

---

### Task 1: Define the immutable domain manifest contract

**Files:**
- Create: backend/capability_v2/domain_manifest.py
- Test: backend/tests/test_domain_manifest.py

**Interfaces:**
- Produces: CapabilityExportManifest, EventSubscriptionManifest, DomainManifest, DomainDatabaseManifest, DomainManifestSet and load_domain_manifests(path: Path) -> DomainManifestSet.
- Consumes: FrozenModel and ProviderArtifact from the Capability V2 kernel.

- [ ] **Step 1: Write the failing manifest validation tests**

~~~python
import json
from pathlib import Path

import pytest

from backend.capability_v2.domain_manifest import load_domain_manifests


def _document():
    return {
        "schema_version": 1,
        "domains": [{
            "domain_id": "craft",
            "artifact": {
                "plugin_id": "official.craft",
                "module": "craft_backend.capabilities",
                "version": "1.2.0",
                "artifact_hash": "sha256:" + "a" * 64,
            },
            "artifact_path": "plugins/craft/craft_backend",
            "allowed_owners": ["craft"],
            "search_export": {
                "capability_id": "craft.object.search",
                "major_version": 1,
            },
            "event_subscriptions": [{
                "subscription_id": "craft.factory_asset_events",
                "producer_domain": "factory",
                "event_type": "factory.asset.scrapped",
                "min_version": 1,
                "max_version": 2,
            }],
            "database": {
                "database_name": "ai00_craft",
                "runtime_url_env": "AI00_CRAFT_DB_URL",
                "ddl_url_env": "AI00_CRAFT_DDL_DB_URL",
                "migration_path": "plugins/craft/migrations",
            },
        }],
    }


def test_manifest_loads_one_explicit_domain(tmp_path: Path):
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")
    manifests = load_domain_manifests(path)
    craft = manifests.require("craft")
    assert craft.database.database_name == "ai00_craft"
    assert craft.database.runtime_url_env == "AI00_CRAFT_DB_URL"
    assert craft.search_export.capability_id == "craft.object.search"
    assert craft.event_subscriptions[0].max_version == 2


def test_manifest_rejects_duplicate_domain_and_database_names(tmp_path: Path):
    document = _document()
    document["domains"].append({**document["domains"][0], "domain_id": "factory"})
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate database_name"):
        load_domain_manifests(path)


def test_manifest_rejects_path_escape(tmp_path: Path):
    document = _document()
    document["domains"][0]["artifact_path"] = "../outside"
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="repository-relative"):
        load_domain_manifests(path)


def test_manifest_rejects_inverted_event_version_range(tmp_path: Path):
    document = _document()
    document["domains"][0]["event_subscriptions"][0].update(min_version=3, max_version=2)
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="min_version"):
        load_domain_manifests(path)


def test_manifest_rejects_duplicate_subscription_ids(tmp_path: Path):
    document = _document()
    subscription = document["domains"][0]["event_subscriptions"][0]
    document["domains"][0]["event_subscriptions"].append(dict(subscription))
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate subscription_id"):
        load_domain_manifests(path)
~~~

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: python -m pytest backend/tests/test_domain_manifest.py -q

Expected: collection fails with ModuleNotFoundError for backend.capability_v2.domain_manifest.

- [ ] **Step 3: Implement the closed Pydantic manifest models**

~~~python
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from .catalog import ProviderArtifact
from .contracts import FrozenModel


class DomainDatabaseManifest(FrozenModel):
    database_name: str = Field(pattern=r"^ai00_[a-z][a-z0-9_]{1,62}$")
    runtime_url_env: str = Field(pattern=r"^AI00_[A-Z0-9_]+_DB_URL$")
    ddl_url_env: str = Field(pattern=r"^AI00_[A-Z0-9_]+_DDL_DB_URL$")
    migration_path: str


class CapabilityExportManifest(FrozenModel):
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,127}$")
    major_version: int = Field(ge=1)


class EventSubscriptionManifest(FrozenModel):
    subscription_id: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,127}$")
    producer_domain: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    min_version: int = Field(ge=1)
    max_version: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered_versions(self):
        if self.min_version > self.max_version:
            raise ValueError("min_version must be <= max_version")
        return self


class DomainManifest(FrozenModel):
    domain_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    artifact: ProviderArtifact
    artifact_path: str
    allowed_owners: tuple[str, ...]
    database: DomainDatabaseManifest
    search_export: CapabilityExportManifest | None = None
    event_subscriptions: tuple[EventSubscriptionManifest, ...] = ()

    @model_validator(mode="after")
    def safe_paths(self):
        for value in (self.artifact_path, self.database.migration_path):
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or "\\" in value:
                raise ValueError("paths must be repository-relative POSIX paths")
        if not self.allowed_owners or self.domain_id not in self.allowed_owners:
            raise ValueError("allowed_owners must include domain_id")
        subscription_ids = [item.subscription_id for item in self.event_subscriptions]
        if len(subscription_ids) != len(set(subscription_ids)):
            raise ValueError("duplicate subscription_id")
        return self


class DomainManifestSet(FrozenModel):
    schema_version: Literal[1]
    domains: tuple[DomainManifest, ...]

    @model_validator(mode="after")
    def unique_identities(self):
        checks = {
            "domain_id": [item.domain_id for item in self.domains],
            "plugin_id": [item.artifact.plugin_id for item in self.domains],
            "database_name": [item.database.database_name for item in self.domains],
        }
        for label, values in checks.items():
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label}")
        return self

    def require(self, domain_id: str) -> DomainManifest:
        for item in self.domains:
            if item.domain_id == domain_id:
                return item
        raise KeyError(domain_id)


def load_domain_manifests(path: Path) -> DomainManifestSet:
    return DomainManifestSet.model_validate_json(path.read_text(encoding="utf-8"))
~~~

- [ ] **Step 4: Run focused tests**

Run: python -m pytest backend/tests/test_domain_manifest.py -q

Expected: 5 passed.

- [ ] **Step 5: Commit the manifest contract**

~~~powershell
git add backend/capability_v2/domain_manifest.py backend/tests/test_domain_manifest.py
git commit -m "feat: define official domain manifest contract"
~~~

### Task 2: Add transitional official Provider entry points

**Files:**
- Create: backend/base/official_provider.py
- Create: backend/knowledge/official_provider.py
- Create: backend/ontology/official_provider.py
- Test: backend/tests/test_official_domain_entrypoints.py

**Interfaces:**
- Produces: register_capabilities(registry: CapabilityRegistry) -> None in each official module.
- Consumes: existing registration functions only; no Router or Repository imports are added.

- [ ] **Step 1: Write the failing entry-point test**

~~~python
from backend.capabilities.registry_next import CapabilityRegistry
from backend.base.official_provider import register_capabilities as register_base
from backend.knowledge.official_provider import register_capabilities as register_knowledge
from backend.ontology.official_provider import register_capabilities as register_ontology


def _owners(register):
    registry = CapabilityRegistry()
    register(registry)
    return {item.spec.owner for item in registry.snapshot()}


def test_official_entrypoints_register_only_their_domain_owner():
    assert _owners(register_base) == {"base", "plugin"}
    assert _owners(register_knowledge) == {"knowledge"}
    assert _owners(register_ontology) == {"ontology"}
~~~

- [ ] **Step 2: Verify the imports fail**

Run: python -m pytest backend/tests/test_official_domain_entrypoints.py -q

Expected: collection fails because the three official_provider modules do not exist.

- [ ] **Step 3: Implement narrow registration wrappers**

Base wrapper calls register_system_shared_capabilities, register_plugin_marketplace_capabilities, register_plugin_storage_capabilities and the existing Base operation registration. Knowledge wrapper calls all current Knowledge registration functions. Ontology wrapper calls concept, proposal and release registration functions. Do not add system.echo and do not change any Capability contract in this task.

Example shape:

~~~python
def register_capabilities(registry) -> None:
    register_knowledge_capabilities(registry)
    register_knowledge_document_capabilities(registry)
    register_knowledge_context_capability(registry)
    register_knowledge_migration_capabilities(registry)
    register_proposal_capability(registry)
    register_review_capability(registry)
    register_proposal_query_capabilities(registry)
    register_outbox_capability(registry)
    register_retry_capability(registry)
~~~

- [ ] **Step 4: Run entry-point and current domain contract tests**

Run: python -m pytest backend/tests/test_official_domain_entrypoints.py backend/tests/test_knowledge_document_capabilities.py backend/tests/test_ontology_concept_capabilities.py -q

Expected: all pass; capability IDs are unchanged except system.echo is not registered by any new entry point.

- [ ] **Step 5: Commit official entry points**

~~~powershell
git add backend/base/official_provider.py backend/knowledge/official_provider.py backend/ontology/official_provider.py backend/tests/test_official_domain_entrypoints.py
git commit -m "refactor: expose official domain provider entrypoints"
~~~

### Task 3: Implement trusted manifest-driven Provider loading

**Files:**
- Create: backend/capability_v2/provider_loader.py
- Create: backend/capability_v2/official_domains.json
- Create: backend/scripts/freeze_official_domains.py
- Test: backend/tests/test_domain_provider_loader.py
- Modify: backend/plugin_loader.py

**Interfaces:**
- Produces: hash_domain_artifact(root: Path, relative_path: str) -> str.
- Produces: current_repository_head(root: Path) -> str, hash_manifest(path: Path) -> str and freeze_official_domains(root: Path, path: Path, expected_head: str | None, expected_manifest_sha256: str | None, check: bool) -> str.
- Produces: DomainProviderLoader(root: Path, manifests: DomainManifestSet).register_all(registry: CapabilityRegistry) -> tuple[str, ...].
- PluginLoader continues discovering Web plugin manifests but no longer owns official domain Provider trust logic.

- [ ] **Step 1: Write loader failure and success tests**

~~~python
def test_loader_registers_domains_in_sorted_domain_order(tmp_path):
    registry = CapabilityRegistry()
    loader = DomainProviderLoader(REPOSITORY_ROOT, load_domain_manifests(OFFICIAL_DOMAINS))
    loaded = loader.register_all(registry)
    assert loaded == tuple(sorted(loaded))
    assert "base" in loaded
    assert "craft" in loaded
    assert registry.get("system.search", 1).spec.owner == "base"


def test_loader_rejects_changed_artifact_hash(tmp_path):
    document = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    document["domains"][0]["artifact"]["artifact_hash"] = "sha256:" + "0" * 64
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ProviderTrustError, match="artifact_mismatch"):
        DomainProviderLoader(REPOSITORY_ROOT, load_domain_manifests(path)).register_all(CapabilityRegistry())


def test_loader_rejects_search_export_owned_by_another_domain(tmp_path):
    document = json.loads(OFFICIAL_DOMAINS.read_text(encoding="utf-8"))
    craft = next(item for item in document["domains"] if item["domain_id"] == "craft")
    craft["search_export"] = {"capability_id": "system.search", "major_version": 1}
    path = tmp_path / "domains.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ProviderTrustError, match="search_export_owner_mismatch"):
        DomainProviderLoader(REPOSITORY_ROOT, load_domain_manifests(path)).register_all(CapabilityRegistry())


def test_freeze_rejects_stale_manifest_digest(tmp_path):
    path = tmp_path / "official_domains.json"
    path.write_bytes(OFFICIAL_DOMAINS.read_bytes())
    with pytest.raises(ProviderTrustError, match="stale_manifest"):
        freeze_official_domains(
            REPOSITORY_ROOT,
            path,
            expected_head=current_repository_head(REPOSITORY_ROOT),
            expected_manifest_sha256="sha256:" + "0" * 64,
            check=False,
        )


def test_freeze_rejects_stale_integration_head(tmp_path):
    path = tmp_path / "official_domains.json"
    path.write_bytes(OFFICIAL_DOMAINS.read_bytes())
    with pytest.raises(ProviderTrustError, match="stale_head"):
        freeze_official_domains(
            REPOSITORY_ROOT,
            path,
            expected_head="0" * 40,
            expected_manifest_sha256=hash_manifest(path),
            check=False,
        )
~~~

- [ ] **Step 2: Run tests and verify missing loader failure**

Run: python -m pytest backend/tests/test_domain_provider_loader.py -q

Expected: collection fails for provider_loader.

- [ ] **Step 3: Implement artifact hashing and fail-closed loading**

The hash covers every file below artifact_path with suffix .py or .json, normalizes line endings, includes each repository-relative filename, rejects symlinks/path escapes, and imports only the frozen module. register_all snapshots registry keys before and after each module registration and rejects any newly registered Capability whose owner is outside manifest.allowed_owners. After all Providers load, validate every non-null search_export resolves to a registered read Descriptor whose owner is in that same DomainManifest.allowed_owners. The Base manifest declares allowed_owners as [base, plugin]; every other current manifest declares only its domain_id.

Core loop:

~~~python
for manifest in sorted(self._manifests.domains, key=lambda item: item.domain_id):
    actual = hash_domain_artifact(self._root, manifest.artifact_path)
    if actual != manifest.artifact.artifact_hash:
        raise ProviderTrustError(f"provider_artifact_mismatch: {manifest.domain_id}")
    before = set(registry.keys())
    module = importlib.import_module(manifest.artifact.module)
    module.register_capabilities(registry)
    added = set(registry.keys()) - before
    owners = {registry.get(capability_id, major).spec.owner for capability_id, major in added}
    if not owners <= set(manifest.allowed_owners):
        raise ProviderTrustError(f"provider_owner_mismatch: {manifest.domain_id}")
~~~

Add keys() -> tuple[tuple[str, int], ...] to CapabilityRegistry rather than reading its private dictionary.

- [ ] **Step 4: Implement deterministic manifest freezing**

freeze_official_domains.py reads the current Git HEAD and exact file-byte sha256 before doing work, and rejects supplied --expected-head or --expected-manifest-sha256 values when either differs. It then recomputes every artifact_hash, sorts domains by domain_id, writes UTF-8 JSON with indent=2 and a final newline, reloads through DomainManifestSet, rechecks HEAD and the original manifest digest immediately before replacement, and prints the new manifest digest. It accepts --check to compare without writing; --check never replaces the file. No network access is used. These optimistic guards are mandatory during every later domain finalization and complement the single-integrator queue defined in the roadmap.

The designated integrator runs the freeze from the latest integration HEAD with:

~~~powershell
$manifestDigest = "sha256:" + (Get-FileHash backend/capability_v2/official_domains.json -Algorithm SHA256).Hash.ToLowerInvariant()
$integrationHead = git rev-parse HEAD
python backend/scripts/freeze_official_domains.py --expected-head $integrationHead --expected-manifest-sha256 $manifestDigest
python backend/scripts/freeze_official_domains.py --check
~~~

Expected: the write prints the new digest, the check exits 0, and no second plan enters finalization until the resulting central freeze commit lands.

- [ ] **Step 5: Populate official_domains.json**

Include Base, Knowledge, Ontology and the current Craft, Project Management, Digital Model, Simulation and Local Runtime providers. Use domain_id local_runtime and plugin_id official.local-runtime, and rename plugins/device/manifest.json to that plugin ID. Because the currently published major-1 VisMockup descriptors still declare owner local_integration, the Local Runtime manifest alone temporarily declares allowed_owners [local_runtime, local_integration]. Record that exact alias as transition debt for Plan 13; no other manifest may declare a legacy owner. Point future Factory, Integration and Agent entries at official Provider entry points only after those entry points exist in their own domain plans; do not declare unloadable providers here. Set search_export only where an actual registered read Descriptor already satisfies the owner check; otherwise serialize null until the owning domain plan delivers it. Set event_subscriptions to an empty array until a consumer plan defines a real handler and version range. Delete official_providers.json once its callers and tests use official_domains.json so there is one trust source.

- [ ] **Step 6: Delegate PluginLoader capability registration**

Keep discover(), get_routers() and get_web_registry() unchanged. Replace its official allowlist loading path with DomainProviderLoader for register_capabilities(), and keep a deprecated adapter signature only for current tests. The adapter must not scan third-party manifests for backend modules.

- [ ] **Step 7: Run loader and security tests**

Run: python -m pytest backend/tests/test_domain_provider_loader.py backend/tests/test_capability_provider_loading.py backend/tests/test_plugin_loader_boundary_next.py -q

Expected: all pass; third-party backend declarations remain rejected.

- [ ] **Step 8: Commit trusted loading**

~~~powershell
git add backend/capability_v2/domain_manifest.py backend/capability_v2/provider_loader.py backend/capability_v2/official_domains.json backend/scripts/freeze_official_domains.py backend/plugin_loader.py backend/capabilities/registry_next.py backend/tests/test_domain_provider_loader.py backend/tests/test_capability_provider_loading.py plugins/device/manifest.json
git rm backend/capability_v2/official_providers.json
git commit -m "feat: load official capabilities from frozen domain manifests"
~~~

### Task 4: Make registry bootstrap explicit and side-effect free

**Files:**
- Create: backend/capability_v2/bootstrap.py
- Modify: backend/capabilities/registry_next.py
- Modify: backend/capabilities/init_next.py
- Modify: backend/capabilities/__init__.py
- Modify: backend/main.py
- Modify: backend/capability_v2/gateway.py
- Modify: backend/plugin_platform/service.py
- Modify: backend/scripts/build_capability_catalog.py
- Test: backend/tests/test_capability_bootstrap.py
- Modify: backend/tests/test_base_capability_contracts.py
- Modify: backend/tests/test_capability_consumer_e2e.py
- Modify: backend/tests/test_plugin_authority_boundary.py
- Modify: backend/tests/test_plugin_mount_sessions_v2.py
- Modify: backend/tests/test_plugin_platform_next.py
- Modify: backend/tests/test_plugin_usage_metrics.py

**Interfaces:**
- Produces: build_capability_registry(root: Path | None = None, manifest_path: Path | None = None) -> CapabilityRegistry.
- Produces: get_capability_registry() -> CapabilityRegistry, cached after the first successful complete build.
- Consumes: DomainProviderLoader from Task 3.

- [ ] **Step 1: Write tests proving registry imports have no domain side effects**

~~~python
def test_registry_module_is_empty_until_bootstrap():
    module = importlib.reload(importlib.import_module("backend.capabilities.registry_next"))
    assert module.CapabilityRegistry().snapshot() == ()
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "register_knowledge" not in source
    assert "register_ontology" not in source
    assert "register_plugin_marketplace" not in source


def test_bootstrap_builds_one_complete_registry():
    registry = build_capability_registry(REPOSITORY_ROOT, OFFICIAL_DOMAINS)
    keys = registry.keys()
    assert len(keys) == len(set(keys))
    assert ("system.search", 1) in keys
    assert ("knowledge.document.get", 1) in keys
    assert ("ontology.release.get", 1) in keys
    assert ("system.echo", 1) not in keys
~~~

- [ ] **Step 2: Run tests and verify failure against import-time registration**

Run: python -m pytest backend/tests/test_capability_bootstrap.py -q

Expected: test_registry_module_is_empty_until_bootstrap fails because registry_next imports domains.

- [ ] **Step 3: Move composition into bootstrap.py**

registry_next.py retains CapabilityRegistry, RegisteredCapability and its exception types only. bootstrap.py builds into a local registry, returns it only after every Provider loads, and never publishes a partially built registry. Cache with an explicit module lock. Add reset_capability_registry_for_tests() guarded by an environment check for pytest; production code cannot reset it.

~~~python
def build_capability_registry(root=None, manifest_path=None):
    repository_root = root or Path(__file__).resolve().parents[2]
    path = manifest_path or Path(__file__).with_name("official_domains.json")
    registry = CapabilityRegistry()
    DomainProviderLoader(repository_root, load_domain_manifests(path)).register_all(registry)
    return registry
~~~

- [ ] **Step 4: Update runtime consumers**

main.py calls get_capability_registry() once, passes that instance to Gateway construction and stops calling PluginLoader.register_capabilities separately. build_capability_catalog.py uses the same builder. gateway.py default construction and plugin_platform/service.py resolve through get_capability_registry(); delete the current `from backend.capabilities.registry_next import capability_registry` fallback so no runtime path can reactivate import-time registration. init_next.py and backend/capabilities/__init__.py expose a lazy proxy only for compatibility; new code imports bootstrap functions directly.

- [ ] **Step 5: Run bootstrap, catalog and bypass tests**

Run: python -m pytest backend/tests/test_capability_bootstrap.py backend/tests/test_capability_catalog_release.py backend/tests/test_no_registry_consumer_bypass.py -q

Expected: all pass; Catalog count equals one registry snapshot and contains no duplicate merge of base and plugin registries.

- [ ] **Step 6: Remove system.echo test coupling and regenerate its artifacts**

Remove system.echo from STABLE_CAPABILITIES in test_base_capability_contracts.py. In test_capability_consumer_e2e.py, monkeypatch the router's get_default_gateway with a recording fake and invoke test.web.read so the test proves the REST result envelope without requiring a diagnostic business Capability. In test_plugin_authority_boundary.py use plugin.install as the positive exposure case and missing.capability as the rejection case. In test_plugin_mount_sessions_v2.py replace system.echo@1/system.echo with test.plugin.read@1/test.plugin.read because its Gateway is already fake. In test_plugin_platform_next.py use plugin.storage.get as the example manifest permission. In test_plugin_usage_metrics.py use test.first.read and test.second.read as opaque dedupe inputs. Regenerate acceptance fixtures, Catalog JSON and generated Capability docs so no generated source lists system.echo.

Run: python -m pytest backend/tests/test_base_capability_contracts.py backend/tests/test_capability_consumer_e2e.py backend/tests/test_plugin_authority_boundary.py backend/tests/test_plugin_mount_sessions_v2.py backend/tests/test_plugin_platform_next.py backend/tests/test_plugin_usage_metrics.py -q

Expected: all pass; `rg -n "system\.echo" docs/capabilities backend/tests/acceptance/fixtures` returns no matches, and any remaining backend/tests match is an explicit negative absence assertion rather than an invocation or grant.

- [ ] **Step 7: Check generated Catalog drift**

Run: python backend/scripts/freeze_official_domains.py --check

Expected: exit 0.

Run: python backend/scripts/build_capability_catalog.py --check

Expected: exit 0; system.echo is absent from the registry, acceptance fixture, Catalog and generated docs and is recorded as a removed diagnostic protocol, not deprecated business behavior.

- [ ] **Step 8: Commit explicit bootstrap**

~~~powershell
git add backend/capability_v2/bootstrap.py backend/capabilities/registry_next.py backend/capabilities/init_next.py backend/capabilities/__init__.py backend/main.py backend/capability_v2/gateway.py backend/plugin_platform/service.py backend/scripts/build_capability_catalog.py backend/tests/test_capability_bootstrap.py backend/tests/test_base_capability_contracts.py backend/tests/test_capability_consumer_e2e.py backend/tests/test_plugin_authority_boundary.py backend/tests/test_plugin_mount_sessions_v2.py backend/tests/test_plugin_platform_next.py backend/tests/test_plugin_usage_metrics.py backend/tests/acceptance/fixtures docs/capabilities docs/governance/capability-catalog-release.json
git commit -m "refactor: bootstrap one capability registry from domain providers"
~~~

### Task 5: Add explicit per-domain database configuration

**Files:**
- Create: backend/capability_v2/domain_database.py
- Test: backend/tests/test_domain_database_config.py
- Modify: backend/config.py
- Modify: backend/.env.example

**Interfaces:**
- Produces: DomainDatabaseConfig(domain_id, database_name, runtime_url, ddl_url).
- Produces: load_domain_database_config(manifest: DomainManifest, environ: Mapping[str, str]) -> DomainDatabaseConfig.
- Produces: connect_runtime(config) and connect_ddl(config); separate credentials are mandatory.

- [ ] **Step 1: Write fail-closed configuration tests**

~~~python
def test_domain_database_requires_both_explicit_urls(craft_manifest):
    with pytest.raises(DomainDatabaseConfigurationError, match="AI00_CRAFT_DB_URL"):
        load_domain_database_config(craft_manifest, {})


def test_domain_database_rejects_wrong_database_name(craft_manifest):
    env = {
        "AI00_CRAFT_DB_URL": "mysql://runtime:secret@db/ai00_base",
        "AI00_CRAFT_DDL_DB_URL": "mysql://ddl:secret@db/ai00_craft",
    }
    with pytest.raises(DomainDatabaseConfigurationError, match="database_name_mismatch"):
        load_domain_database_config(craft_manifest, env)


def test_domain_database_rejects_same_runtime_and_ddl_user(craft_manifest):
    env = {
        "AI00_CRAFT_DB_URL": "mysql://craft:secret@db/ai00_craft",
        "AI00_CRAFT_DDL_DB_URL": "mysql://craft:secret@db/ai00_craft",
    }
    with pytest.raises(DomainDatabaseConfigurationError, match="credential_separation_required"):
        load_domain_database_config(craft_manifest, env)
~~~

- [ ] **Step 2: Run tests and verify missing module failure**

Run: python -m pytest backend/tests/test_domain_database_config.py -q

Expected: collection fails for domain_database.

- [ ] **Step 3: Implement URL parsing without connecting**

Require mysql or mysql+pymysql, explicit host/user/password/database, exact manifest database_name and different runtime/DDL usernames. Do not accept a global AI00_DB_URL fallback. Redact credentials in repr and errors.

- [ ] **Step 4: Document every target environment variable**

Add runtime and DDL URL examples for BASE, PROJECT, FACTORY, CRAFT, KNOWLEDGE, ONTOLOGY, AGENT, INTEGRATION, LOCAL_RUNTIME, DIGITAL_MODEL and SIMULATION. Use non-secret placeholders and state that runtime users have no DDL or cross-database grants.

- [ ] **Step 5: Run configuration tests**

Run: python -m pytest backend/tests/test_domain_database_config.py backend/tests/test_oceanbase_compatibility.py -q

Expected: all pass.

- [ ] **Step 6: Commit domain DB configuration**

~~~powershell
git add backend/capability_v2/domain_database.py backend/config.py backend/.env.example backend/tests/test_domain_database_config.py
git commit -m "feat: require explicit per-domain database credentials"
~~~

### Task 6: Create the independent domain migration runner

**Files:**
- Create: backend/capability_v2/domain_migrations.py
- Create: backend/scripts/run_domain_migrations.py
- Test: backend/tests/test_domain_migration_runner.py
- Modify: backend/db/versioned_migrations.py

**Interfaces:**
- Produces: discover_domain_migrations(root: Path, manifest: DomainManifest) -> tuple[DomainMigration, ...].
- Produces: apply_domain_migrations(conn, manifest, migrations) -> tuple[str, ...].
- CLI: python backend/scripts/run_domain_migrations.py --domain craft --check or --apply.

- [ ] **Step 1: Write migration ownership and ledger tests**

~~~python
def test_discovers_only_selected_domain_migrations(tmp_path, craft_manifest):
    path = tmp_path / "plugins/craft/migrations"
    path.mkdir(parents=True)
    (path / "0001_initial.sql").write_text(
        "CREATE TABLE IF NOT EXISTS craft_versions (id VARCHAR(64) PRIMARY KEY);",
        encoding="utf-8",
    )
    migrations = discover_domain_migrations(tmp_path, craft_manifest)
    assert [item.migration_id for item in migrations] == ["0001"]


def test_rejects_cross_database_identifier(tmp_path, craft_manifest):
    path = tmp_path / "plugins/craft/migrations"
    path.mkdir(parents=True)
    (path / "0001_initial.sql").write_text(
        "CREATE TABLE ai00_factory.assets (id VARCHAR(64));", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="cross_database_identifier"):
        discover_domain_migrations(tmp_path, craft_manifest)
~~~

- [ ] **Step 2: Run tests and verify missing runner failure**

Run: python -m pytest backend/tests/test_domain_migration_runner.py -q

Expected: collection fails for domain_migrations.

- [ ] **Step 3: Implement domain-local naming and ledger**

Migration filenames match NNNN_name.sql. Each database owns ai00_schema_migrations with migration_id, name, checksum, applied_at and artifact_version. Reject CREATE DATABASE, USE, qualified database.table identifiers, GRANT, REVOKE and statements that cannot safely resume after OceanBase implicit commits. Reuse split_sql and OceanBase normalization from versioned_migrations.py; do not duplicate the parser.

- [ ] **Step 4: Implement the deployment-only CLI**

--domain selects exactly one manifest. --check validates files and URL shape without connecting. --apply requires that domain's DDL env var, verifies OceanBase MySQL mode, obtains lock ai00:migrations:{domain_id}:v1 and applies only that domain directory. Application startup must never call this CLI module.

- [ ] **Step 5: Run migration tests**

Run: python -m pytest backend/tests/test_domain_migration_runner.py backend/tests/test_domain_governance.py backend/tests/test_oceanbase_compatibility.py -q

Expected: all pass.

- [ ] **Step 6: Check all configured empty migration roots**

Run each domain with --check. Expected: exit 0 and a deterministic message such as domain=factory migrations=0 until its domain plan adds 0001_initial.sql.

- [ ] **Step 7: Commit migration foundation**

~~~powershell
git add backend/capability_v2/domain_migrations.py backend/scripts/run_domain_migrations.py backend/db/versioned_migrations.py backend/tests/test_domain_migration_runner.py
git commit -m "feat: add independent domain migration runner"
~~~

### Task 7: Add the governed internal DomainCapabilityClient

**Files:**
- Create: backend/capability_v2/domain_client.py
- Test: backend/tests/test_domain_capability_client.py

**Interfaces:**
- Produces: DomainInvocation(capability_id: str, major_version: int, payload: Mapping[str, Any], idempotency_key: str | None, expected_resource_version: str | None, approval_reference: str | None).
- Produces: DomainCapabilityClient.invoke(invocation: DomainInvocation, identity: ConsumerIdentity, correlation: CorrelationRef, deadline: datetime | None = None) -> CapabilityResultV2.
- Consumes: a bound CapabilityGatewayService; never accepts a Repository or raw domain Service.

- [ ] **Step 1: Write identity-preservation and release-pinning tests**

~~~python
@pytest.mark.asyncio
async def test_internal_client_preserves_identity_and_pins_gateway_release(identity):
    gateway = RecordingGateway(catalog_release="rel_" + "a" * 32)
    client = DomainCapabilityClient(gateway)
    await client.invoke(
        DomainInvocation("factory.asset.get", 1, {"asset_id": "asset_1"}),
        identity,
        CorrelationRef(request_id="req_1", trace_id="trace_1"),
    )
    envelope = gateway.envelopes[0]
    assert envelope.identity == identity
    assert envelope.catalog_release == gateway.catalog_release
    assert envelope.capability_id == "factory.asset.get"


@pytest.mark.asyncio
async def test_internal_client_rejects_tenant_in_payload(identity):
    client = DomainCapabilityClient(RecordingGateway())
    with pytest.raises(DomainInvocationError, match="tenant_payload_forbidden"):
        await client.invoke(
            DomainInvocation("factory.asset.get", 1, {"tenant_gid": "other", "asset_id": "asset_1"}),
            identity,
            CorrelationRef(request_id="req_1", trace_id="trace_1"),
        )
~~~

- [ ] **Step 2: Run tests and verify missing module failure**

Run: python -m pytest backend/tests/test_domain_capability_client.py -q

Expected: collection fails for domain_client.

- [ ] **Step 3: Implement the thin Gateway client**

Construct InvocationEnvelope with the bound release and original identity. Reject tenant_id and tenant_gid anywhere at the top payload level. Require idempotency_key for writes through Descriptor inspection rather than guessing from the capability name. Return the Gateway result unchanged so callers must handle rejected, failed, accepted and outcome_unknown explicitly.

- [ ] **Step 4: Run client and Gateway tests**

Run: python -m pytest backend/tests/test_domain_capability_client.py backend/tests/test_capability_gateway_pipeline.py -q

Expected: all pass and the client never calls RegisteredCapability.handler directly.

- [ ] **Step 5: Commit the cross-domain client**

~~~powershell
git add backend/capability_v2/domain_client.py backend/tests/test_domain_capability_client.py
git commit -m "feat: add governed cross-domain capability client"
~~~

### Task 8: Define versioned Domain Event and Outbox/Inbox contracts

**Files:**
- Create: backend/capability_v2/domain_events.py
- Test: backend/tests/test_domain_event_contracts.py

**Interfaces:**
- Produces: DomainEventEnvelope, OutboxWriter Protocol, InboxDeduplicator Protocol, supports_event_version(subscription, event) -> bool and require_event_subscription(manifest, event) -> EventSubscriptionManifest.
- Does not produce a shared SQL repository; every domain implements these protocols against its own database.

- [ ] **Step 1: Write closed event contract tests**

~~~python
def test_event_requires_explicit_tenant_aggregate_version_and_correlation():
    event = DomainEventEnvelope(
        event_id="evt_1",
        event_type="factory.asset.scrapped",
        event_version=1,
        producer_domain="factory",
        tenant_id="tenant_1",
        aggregate_type="factory.asset",
        aggregate_id="asset_1",
        aggregate_version=7,
        occurred_at=datetime.now(UTC),
        payload={"asset_ref": "factory-asset:asset_1"},
        request_id="req_1",
        trace_id="trace_1",
        causation_id="req_1",
    )
    assert event.tenant_id == "tenant_1"


def test_event_rejects_reserved_identity_fields_in_payload():
    with pytest.raises(ValueError, match="reserved event payload field"):
        valid_event(payload={"tenant_id": "forged"})


def test_subscription_accepts_only_declared_type_producer_and_version():
    subscription = EventSubscriptionManifest(
        subscription_id="base.factory_assets",
        producer_domain="factory",
        event_type="factory.asset.scrapped",
        min_version=1,
        max_version=2,
    )
    assert supports_event_version(subscription, valid_event(event_version=2)) is True
    assert supports_event_version(subscription, valid_event(event_version=3)) is False


def test_unmatched_or_unsupported_event_fails_before_inbox_completion():
    from types import SimpleNamespace

    manifest = SimpleNamespace(event_subscriptions=())
    with pytest.raises(UnsupportedEventVersion, match="event_subscription_not_declared"):
        require_event_subscription(manifest, valid_event())
~~~

- [ ] **Step 2: Run tests and verify missing module failure**

Run: python -m pytest backend/tests/test_domain_event_contracts.py -q

Expected: collection fails for domain_events.

- [ ] **Step 3: Implement immutable event and protocols**

Use FrozenModel. Enforce timezone-aware occurred_at, event_type pattern domain.aggregate.past_tense_event, event_version and aggregate_version >= 1, non-empty request/trace/causation IDs, and reject tenant_id, tenant_gid, producer_domain, aggregate_id and aggregate_version inside payload. Match subscriptions by producer_domain and exact event_type, then require min_version <= event_version <= max_version before InboxDeduplicator.begin. Unsupported events use stable reasons event_subscription_not_declared or event_version_unsupported and are not marked complete. Define:

~~~python
class OutboxWriter(Protocol):
    def append(self, event: DomainEventEnvelope, *, transaction: object) -> None: ...


class InboxDeduplicator(Protocol):
    def begin(self, event_id: str, *, tenant_id: str) -> bool: ...
    def complete(self, event_id: str, *, tenant_id: str) -> None: ...
    def fail(self, event_id: str, *, tenant_id: str, error_code: str) -> None: ...
~~~

- [ ] **Step 4: Run event tests**

Run: python -m pytest backend/tests/test_domain_event_contracts.py -q

Expected: all pass.

- [ ] **Step 5: Commit event contracts**

~~~powershell
git add backend/capability_v2/domain_events.py backend/tests/test_domain_event_contracts.py
git commit -m "feat: define versioned domain event contracts"
~~~

### Task 9: Align governance, ownership and foundation acceptance

**Files:**
- Modify: docs/governance/domain-ownership.json
- Modify: backend/governance/domain_boundaries.json
- Modify: .github/CODEOWNERS
- Modify: backend/scripts/check_domain_dependencies.py
- Modify: backend/tests/test_domain_independence_v2.py
- Modify: backend/tests/test_capability_kernel_contract.py
- Modify: backend/governance/boundary_baseline.json
- Modify: backend/scripts/build_capability_coverage_review.py
- Modify: docs/governance/capability-coverage-review/craft.json
- Create: docs/governance/capability-coverage-review/factory.json
- Create: docs/governance/capability-coverage-review/integration.json
- Create: docs/governance/capability-coverage-review/local-runtime.json
- Delete: docs/governance/capability-coverage-review/local-integration.json
- Modify: docs/governance/capability-coverage-review/manifest.json
- Modify: docs/governance/capability-coverage-review/generated/capability-candidates.md
- Modify: docs/governance/capability-coverage-review/generated/code-ownership-extractions.md
- Modify: docs/governance/capability-coverage-review/generated/consumer-exposure.md
- Modify: docs/governance/capability-coverage-review/generated/database-ownership-migrations.md
- Modify: docs/governance/capability-coverage-review/generated/function-dispositions.md
- Modify: docs/governance/capability-coverage-review/generated/summary.json
- Create: plugins/factory/README.md
- Create: plugins/integration/README.md
- Create: plugins/factory/factory_backend/__init__.py
- Create: plugins/integration/integration_backend/__init__.py
- Create: plugins/factory/migrations/README.md
- Create: plugins/integration/migrations/README.md
- Modify: docs/superpowers/specs/2026-08-11-capability-v2-domain-rearchitecture-design.md only if implementation reveals a contradiction; otherwise leave the approved spec unchanged.

**Interfaces:**
- Produces: one target ownership record for Base, Project Management, Factory, Craft, Knowledge, Ontology, Agent, Integration, Local Runtime, Digital Model and Simulation.
- Governance accepts public imports only from backend.capability_v2, backend.contracts, backend.domain_ports and backend.platform_sdk.

- [ ] **Step 1: Update failing expected-domain assertions first**

Change EXPECTED_DOMAINS to the eleven approved first-class domains. Change DOMAIN_SLUGS Local Integration → device to Local Runtime → local_runtime, and add Factory → factory and Integration → integration. Add assertions that Factory and Integration have unique code, migration, provider, test and documentation paths even though their business Providers are delivered in later plans.

- [ ] **Step 2: Run governance tests and capture expected failures**

Run: python -m pytest backend/tests/test_domain_independence_v2.py -q

Expected: failures identify missing Factory/Integration ownership records, Local Runtime rename and CODEOWNERS paths.

- [ ] **Step 3: Add target domain ownership and minimal roots**

Create only package markers and README files; do not add empty fake Capabilities. Assign existing device code to Local Runtime. Factory and Integration target roots are owned immediately. Update build_capability_coverage_review.py DOMAINS and RUNTIME_TO_DOMAIN to the eleven approved names, rename local-integration.json to local-runtime.json, and let the merge-preserving initializer create factory.json and integration.json without inventing Capabilities. Update table ownership classification first and capture `audit_domain_boundaries.py --json` before and after. Match reclassified violations by the unchanged tuple (category, path, scope, target); when only owner/detail changes, replace the old `boundary:<fingerprint>` debt ID with the new fingerprint in the same source-domain review document and update its evidence text. Then run `audit_domain_boundaries.py --write-baseline` and `build_capability_coverage_review.py --write`. A changed owner may replace an old reviewed fingerprint, but any violation with no matching old tuple is genuinely new and must be fixed rather than accepted. Existing misplaced implementations remain reviewed debt until their extraction plans remove them.

- [ ] **Step 4: Tighten the import checker**

Treat domain, application, infrastructure, repositories, api and routers modules as private across owners. Only shared prefixes and a domain's ports/public module may cross a domain boundary. Add fixture tests showing plugins.craft importing plugins.factory.factory_backend.infrastructure.database fails while importing backend.domain_ports.factory succeeds.

- [ ] **Step 5: Run foundation gates**

Run: python -m pytest backend/tests/test_domain_manifest.py backend/tests/test_official_domain_entrypoints.py backend/tests/test_domain_provider_loader.py backend/tests/test_capability_bootstrap.py backend/tests/test_domain_database_config.py backend/tests/test_domain_migration_runner.py backend/tests/test_domain_capability_client.py backend/tests/test_domain_event_contracts.py backend/tests/test_domain_independence_v2.py backend/tests/test_capability_kernel_contract.py -q

Expected: all pass.

Run: python backend/scripts/freeze_official_domains.py --check

Expected: official_domains.json is current.

Run: python backend/scripts/check_domain_dependencies.py --check

Expected: no new cross-domain dependency; existing exact reviewed debt may remain until extraction plans.

Run: python backend/scripts/audit_domain_boundaries.py

Expected: new_violations=0, unowned_tables=[], and Factory/Integration-owned tables are not reported as Craft-owned.

Run: python backend/scripts/build_capability_coverage_review.py --check

Expected: exit 0; every current boundary fingerprint has exactly one reviewed disposition and generated review views have no drift.

Run: python backend/scripts/build_capability_catalog.py --check

Expected: no Catalog drift.

- [ ] **Step 6: Run the broader offline acceptance**

Run: python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict

Expected: status passed, failed=0, skipped=0 for mandatory offline cases. This foundation plan does not claim RC environment acceptance.

- [ ] **Step 7: Commit governance alignment**

~~~powershell
git add docs/governance/domain-ownership.json docs/governance/capability-coverage-review backend/governance/domain_boundaries.json backend/governance/boundary_baseline.json .github/CODEOWNERS backend/scripts/check_domain_dependencies.py backend/scripts/build_capability_coverage_review.py backend/tests/test_domain_independence_v2.py backend/tests/test_capability_kernel_contract.py plugins/factory plugins/integration
git commit -m "chore: establish capability v2 domain foundation gates"
~~~

## Plan Completion Criteria

- CapabilityRegistry has no import-time business-domain registration.
- Runtime and Catalog builds construct the same registry from the same frozen official domain manifest.
- Every loaded Provider artifact is hash-pinned and owner-checked.
- Every search target comes from a validated DomainManifest.search_export; no mutable handwritten search Provider list is a source of truth.
- Event consumers declare exact producer/type/min/max ranges in DomainManifest.event_subscriptions and unsupported versions fail before Inbox completion.
- Frozen central manifests reject stale expected HEAD or manifest digests and are finalized by one designated integrator on the latest integration HEAD.
- system.echo is absent from the business Catalog.
- Every target domain has an explicit database name, runtime URL env, DDL URL env and migration root.
- No global database URL fallback exists in the new domain database API.
- Domain migration runner can validate and independently target one domain.
- Cross-domain code has a governed Gateway client and versioned event contracts, but no shared Repository.
- Factory and Integration are recognized as first-class target domains; governance and package identity use Local Runtime. The old local_integration owner remains only as an explicit major-1 Descriptor alias scheduled for removal in Plan 13.
- No business data, business Capability semantics or consumer behavior changed in this plan.
- All focused tests, dependency checks, Catalog checks and strict offline acceptance pass.

## Execution Handoff

Execute this plan inline with superpowers:executing-plans. Work task-by-task, run each stated red/green test cycle, commit after each task, and stop for review after Tasks 3, 6 and 9. Do not use subagents.
