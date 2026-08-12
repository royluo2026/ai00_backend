"""Initialize, validate, and render Capability V2 coverage review documents."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from fnmatch import fnmatch
from pathlib import Path
from typing import NamedTuple

import jsonschema


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_ROOT = REPOSITORY_ROOT / "docs" / "governance"
REVIEW_ROOT = GOVERNANCE_ROOT / "capability-coverage-review"
GENERATED_ROOT = REVIEW_ROOT / "generated"
SCHEMA_PATH = GOVERNANCE_ROOT / "capability-coverage-review.schema.json"
REGISTRY_PATH = GOVERNANCE_ROOT / "user-function-registry.json"
CATALOG_PATH = REPOSITORY_ROOT / "docs" / "capabilities" / "catalog.v2.json"
MANIFEST_PATH = REVIEW_ROOT / "manifest.json"
OWNERSHIP_PATH = GOVERNANCE_ROOT / "domain-ownership.json"
DEPENDENCY_BASELINE_PATH = GOVERNANCE_ROOT / "domain-dependency-baseline.json"
BOUNDARY_BASELINE_PATH = REPOSITORY_ROOT / "backend" / "governance" / "boundary_baseline.json"
TABLE_INVENTORY_PATH = REPOSITORY_ROOT / "backend" / "governance" / "table_inventory.json"
RUNTIME_OWNERSHIP_PATH = REPOSITORY_ROOT / "backend" / "governance" / "domain_boundaries.json"
DOMAINS = (
    "Base Platform", "Project Management", "Factory", "Craft", "Knowledge",
    "Ontology", "Agent", "Integration", "Local Runtime", "Digital Model",
    "Simulation",
)
DOMAIN_FILES = {domain: domain.lower().replace(" ", "-") + ".json" for domain in DOMAINS}
CONSUMERS = ("web", "rest", "plugin", "agent", "mcp", "local_runtime")
BOOTSTRAP_REVIEWER = "existing-user-function-registry"
BOOTSTRAP_DATE = "2026-08-11"
RUNTIME_TO_DOMAIN = {
    "base": "Base Platform", "agent": "Agent", "craft": "Craft",
    "factory": "Factory", "integration": "Integration",
    "digital_model": "Digital Model", "project_management": "Project Management",
    "simulation": "Simulation", "ontology": "Ontology", "knowledge": "Knowledge",
    "device": "Local Runtime", "local_integration": "Local Runtime",
    "local_runtime": "Local Runtime",
}


class AuditSources(NamedTuple):
    registry: dict
    catalog: dict
    manifest: dict
    reviewed_against: dict
    ownership: dict
    dependency_baseline: dict
    boundary_baseline: dict
    table_inventory: dict
    runtime_ownership: dict


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
    ).strip()


def load_sources(root: Path = REPOSITORY_ROOT) -> AuditSources:
    governance = root / "docs" / "governance"
    review_root = governance / "capability-coverage-review"
    registry_path = governance / "user-function-registry.json"
    catalog_path = root / "docs" / "capabilities" / "catalog.v2.json"
    manifest_path = review_root / "manifest.json"
    registry = _json(registry_path)
    catalog = _json(catalog_path)
    manifest = _json(manifest_path) if manifest_path.exists() else {}
    previous_binding = manifest.get("reviewed_against", {})
    reviewed_against = {
        "git_commit": previous_binding.get("git_commit", _head(root)),
        "registry_sha256": _sha256(registry_path),
        "catalog_release": catalog["release_id"],
        "catalog_sha256": _sha256(catalog_path),
    }
    return AuditSources(
        registry, catalog, manifest, reviewed_against,
        _json(root / "docs" / "governance" / "domain-ownership.json"),
        _json(root / "docs" / "governance" / "domain-dependency-baseline.json"),
        _json(root / "backend" / "governance" / "boundary_baseline.json"),
        _json(root / "backend" / "governance" / "table_inventory.json"),
        _json(root / "backend" / "governance" / "domain_boundaries.json"),
    )


def _discovered(row: dict) -> dict:
    return {
        "function_id": row["function_id"],
        "domain": (
            "Local Runtime" if row["domain"] == "Local Integration" else row["domain"]
        ),
        "source_paths": sorted(row["source_paths"]),
        "current_consumers": sorted(row.get("current_consumers", [])),
        "target_capability": row.get("target_capability"),
        "classification": row.get("classification", "unreviewed"),
        "exclusion_reason": row.get("exclusion_reason"),
    }


def stable_functions(sources: AuditSources) -> list[dict]:
    return [
        _discovered(row) for row in sources.registry["functions"].values()
        if row.get("stability") == "stable"
    ]


def _empty_review(domain: str, reviewed_against: dict) -> dict:
    return {
        "schema_version": 1,
        "domain": domain,
        "reviewed_against": copy.deepcopy(reviewed_against),
        "unreviewed_functions": {},
        "excluded_functions": {},
        "capabilities": {},
        "code_extractions": [],
        "database_boundaries": [],
        "debt_dispositions": [],
        "review": {
            "reviewer": "pending-domain-review",
            "reviewed_at": BOOTSTRAP_DATE,
            "status": "draft",
        },
    }


def _reviewed_function_ids(document: dict) -> set[str]:
    result = set(document.get("unreviewed_functions", {})) | set(document.get("excluded_functions", {}))
    for group in document.get("capabilities", {}).values():
        result.update(group.get("function_dispositions", {}))
    return result


def merge_domain_review(existing: dict, discovered: list[dict]) -> dict:
    """Preserve authored decisions and append newly discovered functions as unreviewed."""
    merged = copy.deepcopy(existing)
    discovered_ids = {row["function_id"] for row in discovered}
    merged["unreviewed_functions"] = {
        function_id: row for function_id, row in merged["unreviewed_functions"].items()
        if function_id in discovered_ids
    }
    known = _reviewed_function_ids(merged)
    for row in sorted(discovered, key=lambda item: item["function_id"]):
        function_id = row["function_id"]
        if function_id in known:
            continue
        merged["unreviewed_functions"][function_id] = {
            "resolution": "unreviewed",
            "source_paths": sorted(row["source_paths"]),
            "owner": row["domain"],
            "evidence": "Discovered as a stable user function in the bound Registry source evidence.",
        }
    merged["unreviewed_functions"] = dict(sorted(merged["unreviewed_functions"].items()))
    return merged


def _exposure(row: dict) -> dict:
    labels = " ".join(row.get("current_consumers", [])).lower()
    enabled = {
        "web": "web" in labels,
        "rest": "rest" in labels or row["function_id"].startswith(("rest:", "agent_runtime:")),
        "plugin": "plugin" in labels,
        "agent": "agent" in labels or row["function_id"].startswith("agent_tool:"),
        "mcp": "mcp" in labels or row["function_id"].startswith("mcp_tool:"),
        "local_runtime": "local" in labels or row["function_id"].startswith("local_command:"),
    }
    result = {"shared_pipeline": "capability_provider_gateway"}
    for consumer in CONSUMERS:
        result[consumer] = {
            "enabled": enabled[consumer],
            "reason": ("Existing Registry evidence includes this consumer." if enabled[consumer]
                       else "No approved exposure for this consumer in the existing Registry."),
            "policy_ref": "existing-registry-policy",
        }
    return result


def _bootstrap_existing(document: dict, rows: list[dict]) -> dict:
    """Project already-reviewed Registry mappings; never classify unresolved rows."""
    for row in sorted(rows, key=lambda item: item["function_id"]):
        function_id = row["function_id"]
        target = row.get("target_capability")
        if target:
            group = document["capabilities"].setdefault(target, {
                "kind": "existing", "function_dispositions": {}, "consumer_exposure": _exposure(row)
            })
            group["function_dispositions"][function_id] = {
                "resolution": "existing_capability",
                "source_paths": row["source_paths"],
                "owner": row["domain"],
                "evidence": "Existing reviewed Registry mapping to the frozen Capability Catalog.",
                "reviewer": BOOTSTRAP_REVIEWER,
                "reviewed_at": BOOTSTRAP_DATE,
            }
        elif row.get("classification") != "unreviewed":
            document["excluded_functions"][function_id] = {
                "resolution": "excluded", "target_capability": None,
                "source_paths": row["source_paths"],
                "evidence": "Existing reviewed Registry classification and source-path evidence.",
                "reason": row["exclusion_reason"], "classification": row["classification"],
                "owner": row["domain"], "reviewer": BOOTSTRAP_REVIEWER,
                "reviewed_at": BOOTSTRAP_DATE,
            }
    document["capabilities"] = dict(sorted(document["capabilities"].items()))
    document["excluded_functions"] = dict(sorted(document["excluded_functions"].items()))
    return document


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _runtime_source_domain(path: str, runtime_ownership: dict) -> str | None:
    normalized = Path(path).as_posix().lstrip("./")
    for rule in runtime_ownership.get("source_overrides", []):
        if normalized == rule["path"]:
            return rule["domain"]
    matches = []
    for rule in runtime_ownership.get("source_roots", []):
        prefix = rule["path"].rstrip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            matches.append((len(prefix), rule["domain"]))
    return max(matches)[1] if matches else None


def _domain_name(runtime_domain: str | None) -> str:
    return RUNTIME_TO_DOMAIN.get(runtime_domain or "", "Unowned Internal")


def _module_debt(row: dict) -> dict:
    identity = {key: row[key] for key in ("source", "imported_module", "source_domain", "target_domain")}
    return {
        "id": "module:" + _canonical_hash(identity),
        "category": "dependency",
        "source_paths": [row["source"]],
        "owner_domain": row["source_domain"],
        "current_owner": row["source_domain"],
        "target_owner": row["target_domain"],
        "replacement_boundary": "versioned_public_port:" + _owner_slug(row["target_domain"]),
        "resolution_plan": "Replace the concrete cross-domain import with a versioned public Application Port.",
        "disposition": "remove_after_extraction",
        "reason": row["reason"],
    }


def _owner_slug(domain: str) -> str:
    if domain == "Base Platform":
        return "base"
    if domain == "Local Runtime":
        return "local_runtime"
    return domain.lower().replace(" ", "_")


def _boundary_debt(row: dict, sources: AuditSources, table_owners: dict[str, str]) -> dict:
    current_runtime = _runtime_source_domain(row["path"], sources.runtime_ownership)
    current_owner = _domain_name(current_runtime)
    if row["category"] == "cross_domain_sql":
        target_owner = _domain_name(table_owners.get(row["target"]))
        category = "database"
        boundary = "application_port:" + _owner_slug(target_owner)
        plan = "Remove direct SQL and route the operation through the target domain Application Port."
    else:
        module_path = row["target"].replace(".", "/") + ".py"
        target_owner = _domain_name(_runtime_source_domain(module_path, sources.runtime_ownership))
        category = "dependency"
        boundary = "versioned_public_port:" + _owner_slug(target_owner)
        plan = "Replace the internal module import with a versioned public contract or Application Port."
    return {
        "id": "boundary:" + row["fingerprint"],
        "category": category,
        "source_paths": [row["path"]],
        "owner_domain": current_owner,
        "current_owner": current_owner,
        "target_owner": target_owner,
        "replacement_boundary": boundary,
        "resolution_plan": plan,
        "disposition": "remove_after_extraction",
        "reason": row["detail"],
    }


def _merge_evidence(document: dict, sources: AuditSources) -> dict:
    domain = document["domain"]
    runtime_names = {runtime for runtime, name in RUNTIME_TO_DOMAIN.items() if name == domain}
    existing_tables = {row["table"]: row for row in document.get("database_boundaries", [])}
    generated_tables = []
    for item in sorted(sources.table_inventory["tables"], key=lambda row: row["table"]):
        if item["runtime_domain"] not in runtime_names:
            continue
        generated = {
            "table": item["table"],
            "owner_domain": domain,
            "access_mode": "read_write",
            "migration_stream": _owner_slug(domain),
            "evidence": "Owned by the exact runtime table inventory bound to this coverage review.",
        }
        generated_tables.append({**generated, **existing_tables.get(item["table"], {})})
    document["database_boundaries"] = generated_tables

    table_owners = {row["table"]: row["runtime_domain"] for row in sources.table_inventory["tables"]}
    generated_debts = [
        _module_debt(row) for row in sources.dependency_baseline["violations"]
        if row["source_domain"] == domain
    ]
    generated_debts.extend(
        debt for debt in (
            _boundary_debt(row, sources, table_owners)
            for row in sources.boundary_baseline["violations"]
        ) if debt["owner_domain"] == domain
    )
    existing_debts = {row["id"]: row for row in document.get("debt_dispositions", [])}
    merged_debts = [
        {**row, **existing_debts.get(row["id"], {})}
        for row in sorted(generated_debts, key=lambda item: item["id"])
    ]
    generated_ids = {row["id"] for row in generated_debts}
    merged_debts.extend(row for debt_id, row in sorted(existing_debts.items()) if debt_id not in generated_ids)
    document["debt_dispositions"] = sorted(merged_debts, key=lambda item: item["id"])
    return document


def initialize_documents(sources: AuditSources, existing: dict[str, dict] | None = None) -> list[dict]:
    existing = existing or {}
    rows = stable_functions(sources)
    result = []
    for domain in DOMAINS:
        domain_rows = [row for row in rows if row["domain"] == domain]
        document = copy.deepcopy(existing.get(domain)) if domain in existing else _empty_review(domain, sources.reviewed_against)
        if domain not in existing:
            document = _bootstrap_existing(document, domain_rows)
        document["excluded_functions"].pop("capability:system.echo", None)
        if domain == "Base Platform" and "system.echo" in document["capabilities"]:
            echo = document["capabilities"].pop("system.echo")
            disposition = echo["function_dispositions"]["capability:system.echo"]
            document["excluded_functions"]["capability:system.echo"] = {
                "resolution": "excluded",
                "target_capability": None,
                "source_paths": disposition["source_paths"],
                "evidence": "The legacy echo probe is absent from the frozen business Capability Catalog.",
                "reason": "system.echo is a development probe, not an independently invokable business outcome.",
                "classification": "operations",
                "owner": "Base Platform",
                "reviewer": "capability-v2-architecture-review",
                "reviewed_at": BOOTSTRAP_DATE,
            }
        document["reviewed_against"] = copy.deepcopy(sources.reviewed_against)
        document = merge_domain_review(document, domain_rows)
        result.append(_merge_evidence(document, sources))
    return result


def _lines(title: str, header: str, rows: list[str]) -> str:
    return "\n".join([f"# {title}", "", header, "", *rows, ""])


def render_views(documents: list[dict]) -> dict[str, str]:
    """Return all generated views with canonical ordering independent of input order."""
    functions, candidates, exposures, extractions, databases = [], [], [], [], []
    counts = Counter()
    functions_by_domain: dict[str, Counter] = defaultdict(Counter)
    candidates_by_domain = Counter()
    exposure_counts = Counter()
    debt_counts = Counter()
    for document in sorted(documents, key=lambda item: item["domain"]):
        domain = document["domain"]
        for function_id in sorted(document["unreviewed_functions"]):
            functions.append(f"| {domain} | `{function_id}` | unreviewed | — |")
            counts["unreviewed"] += 1
            functions_by_domain[domain]["unreviewed"] += 1
        for function_id in sorted(document["excluded_functions"]):
            functions.append(f"| {domain} | `{function_id}` | excluded | — |")
            counts["excluded"] += 1
            functions_by_domain[domain]["excluded"] += 1
        for capability_id, group in sorted(document["capabilities"].items()):
            if group["kind"] == "candidate":
                outcome = group["candidate_definition"]["business_outcome"].replace("|", "\\|")
                candidates.append(f"| {domain} | {outcome} | `{capability_id}` |")
                counts["candidate_capabilities"] += 1
                candidates_by_domain[domain] += 1
            exposure = group["consumer_exposure"]
            flags = [name for name in CONSUMERS if exposure[name]["enabled"]]
            exposure_counts.update(flags)
            exposures.append(f"| {domain} | `{capability_id}` | {', '.join(flags) or 'none'} |")
            for function_id, disposition in sorted(group["function_dispositions"].items()):
                functions.append(f"| {domain} | `{function_id}` | {disposition['resolution']} | `{capability_id}` |")
                counts[disposition["resolution"]] += 1
                functions_by_domain[domain][disposition["resolution"]] += 1
        for row in sorted(document["code_extractions"], key=lambda item: item["id"]):
            extractions.append(f"| {domain} | `{row['id']}` | {row['disposition']} |")
        for row in sorted(document["database_boundaries"], key=lambda item: item["table"]):
            databases.append(f"| {domain} | `{row['table']}` | {row['owner_domain']} | {row['migration_stream']} |")
        for row in sorted(document["debt_dispositions"], key=lambda item: item["id"]):
            debt_counts[row["category"]] += 1
            if row["category"] in {"database", "migration"}:
                databases.append(f"| {domain} | `{row['id']}` | debt:{row['target_owner']} | {row['disposition']} |")
            else:
                extractions.append(f"| {domain} | `{row['id']}` | debt:{row['disposition']} |")
    summary = {
        "schema_version": 1,
        "domains": len(documents),
        "stable_functions": counts["unreviewed"] + counts["excluded"] + counts["existing_capability"] + counts["new_capability"],
        "resolutions": {key: counts[key] for key in ("existing_capability", "new_capability", "excluded", "unreviewed")},
        "candidate_capabilities": counts["candidate_capabilities"],
        "candidate_additions_by_domain": dict(sorted(candidates_by_domain.items())),
        "function_dispositions_by_domain": {
            domain: {key: functions_by_domain[domain][key] for key in ("existing_capability", "new_capability", "excluded", "unreviewed")}
            for domain in sorted(functions_by_domain)
        },
        "consolidation_ratio": {
            "new_function_dispositions": counts["new_capability"],
            "candidate_capabilities": counts["candidate_capabilities"],
            "functions_per_candidate": round(counts["new_capability"] / counts["candidate_capabilities"], 3) if counts["candidate_capabilities"] else 0,
        },
        "enabled_exposures": {consumer: exposure_counts[consumer] for consumer in CONSUMERS},
        "code_extractions": sum(len(document["code_extractions"]) for document in documents),
        "debt_backlog": {category: debt_counts[category] for category in sorted(debt_counts)},
    }
    return {
        "function-dispositions.md": _lines("Function dispositions", "| Domain | Function | Resolution | Capability |\n|---|---|---|---|", functions),
        "capability-candidates.md": _lines("Capability candidates", "| Domain | Business outcome | Capability |\n|---|---|---|", candidates),
        "consumer-exposure.md": _lines("Consumer exposure", "| Domain | Capability | Enabled consumers |\n|---|---|---|", exposures),
        "code-ownership-extractions.md": _lines("Code ownership extractions", "| Domain | Extraction | Disposition |\n|---|---|---|", extractions),
        "database-ownership-migrations.md": _lines("Database ownership and migrations", "| Domain | Table | Owner | Migration stream |\n|---|---|---|---|", databases),
        "summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    }


def migration_owner_rows(sources: AuditSources, root: Path = REPOSITORY_ROOT) -> list[dict]:
    rows = []
    for path in sorted((root / "backend" / "db" / "migrations").glob("*.sql")):
        relative = path.relative_to(root).as_posix()
        matches = []
        for domain, descriptor in sources.ownership["domains"].items():
            for pattern in descriptor["migration_paths"]:
                if fnmatch(relative, pattern):
                    specificity = len(pattern.replace("*", "").replace("?", ""))
                    matches.append((specificity, domain))
        if not matches:
            raise ValueError(f"unowned migration: {relative}")
        best = max(score for score, _ in matches)
        owners = sorted({domain for score, domain in matches if score == best})
        if len(owners) != 1:
            raise ValueError(f"ambiguous migration owner: {relative}: {owners}")
        rows.append({"path": relative, "owner_domain": owners[0], "migration_stream": _owner_slug(owners[0])})
    return rows


def render_evidence_views(views: dict[str, str], sources: AuditSources) -> dict[str, str]:
    views = dict(views)
    migration_lines = [
        f"| {row['owner_domain']} | `{row['path']}` | migration | {row['migration_stream']} |"
        for row in migration_owner_rows(sources)
    ]
    views["database-ownership-migrations.md"] = (
        views["database-ownership-migrations.md"].rstrip() + "\n" + "\n".join(migration_lines) + "\n"
    )
    summary = json.loads(views["summary.json"])
    summary["catalog_descriptors"] = len(sources.catalog["capabilities"])
    summary["current_catalog_capabilities"] = sum(
        row.get("lifecycle_status") == "stable" for row in sources.catalog["capabilities"]
    )
    summary["proposed_final_catalog_capabilities"] = (
        summary["current_catalog_capabilities"] + summary["candidate_capabilities"]
    )
    categories = Counter(row["category"] for row in sources.boundary_baseline["violations"])
    summary["evidence"] = {
        "module_dependencies": len(sources.dependency_baseline["violations"]),
        "boundary_violations": len(sources.boundary_baseline["violations"]),
        "cross_domain_sql": categories["cross_domain_sql"],
        "internal_import": categories["internal_import"],
        "tables": sources.table_inventory["table_count"],
        "migrations": len(migration_owner_rows(sources)),
    }
    views["summary.json"] = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    return views


def _load_documents() -> dict[str, dict]:
    result = {}
    for domain, filename in DOMAIN_FILES.items():
        path = REVIEW_ROOT / filename
        if domain == "Local Runtime" and not path.exists():
            legacy_path = REVIEW_ROOT / "local-integration.json"
            if legacy_path.exists():
                legacy = legacy_path.read_text(encoding="utf-8").replace(
                    "Local Integration",
                    "Local Runtime",
                )
                result[domain] = json.loads(legacy)
                continue
        if path.exists():
            result[domain] = _json(path)
    return result


def _manifest(sources: AuditSources, documents: list[dict]) -> dict:
    candidate_counts = {
        document["domain"]: sum(group["kind"] == "candidate" for group in document["capabilities"].values())
        for document in documents
    }
    candidate_total = sum(candidate_counts.values())
    stable_catalog_total = sum(
        row.get("lifecycle_status") == "stable" for row in sources.catalog["capabilities"]
    )
    proposed_total = stable_catalog_total + candidate_total
    return {
        "schema_version": 1,
        "discussion_status": "architecture_review_required" if proposed_total > 170 or max(candidate_counts.values()) > 40 else "ready_for_domain_approval",
        "thresholds": {"maximum_catalog_capabilities": 170, "maximum_domain_additions": 40},
        "catalog_descriptors": len(sources.catalog["capabilities"]),
        "current_catalog_capabilities": stable_catalog_total,
        "candidate_capabilities": candidate_total,
        "proposed_final_catalog_capabilities": proposed_total,
        "candidate_additions_by_domain": candidate_counts,
        "reviewed_against": sources.reviewed_against,
        "ownership_sha256": _sha256(OWNERSHIP_PATH),
        "table_inventory_sha256": _sha256(TABLE_INVENTORY_PATH),
        "dependency_baseline_sha256": _sha256(DEPENDENCY_BASELINE_PATH),
        "boundary_baseline_sha256": _sha256(BOUNDARY_BASELINE_PATH),
        "runtime_ownership_sha256": _sha256(RUNTIME_OWNERSHIP_PATH),
        "domains": list(DOMAINS),
    }


def _serialize(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _validate(documents: list[dict], strict: bool) -> list[str]:
    validator = jsonschema.Draft202012Validator(_json(SCHEMA_PATH))
    errors = []
    for document in documents:
        for error in validator.iter_errors(document):
            errors.append(f"{document['domain']}: {error.message}")
        if strict and document["review"]["status"] != "approved":
            errors.append(f"{document['domain']}: review is not approved")
        if strict and document["unreviewed_functions"]:
            errors.append(f"{document['domain']}: {len(document['unreviewed_functions'])} unreviewed functions")
    return sorted(errors)


def audit_consistency_errors(documents: list[dict], sources: AuditSources) -> list[str]:
    errors: list[str] = []
    function_counts = Counter()
    capability_domains: dict[str, str] = {}
    table_counts = Counter()
    debt_counts = Counter()
    catalog_ids = {row["id"] for row in sources.catalog["capabilities"]}
    for document in documents:
        domain = document["domain"]
        function_counts.update(document["unreviewed_functions"].keys())
        function_counts.update(document["excluded_functions"].keys())
        table_counts.update(row["table"] for row in document["database_boundaries"])
        debt_counts.update(row["id"] for row in document["debt_dispositions"])
        for capability_id, group in document["capabilities"].items():
            previous = capability_domains.setdefault(capability_id, domain)
            if previous != domain:
                errors.append(f"Capability appears in multiple domain reviews: {capability_id}")
            if group["kind"] == "existing" and capability_id not in catalog_ids:
                errors.append(f"dangling existing Capability: {capability_id}")
            if group["kind"] == "candidate" and capability_id in catalog_ids:
                errors.append(f"candidate collides with existing Catalog Capability: {capability_id}")
            function_counts.update(group["function_dispositions"].keys())
    stable_ids = {
        function_id for function_id, row in sources.registry["functions"].items()
        if row.get("stability") == "stable"
    }
    for function_id in sorted(stable_ids - set(function_counts)):
        errors.append(f"missing stable function disposition: {function_id}")
    for function_id in sorted(set(function_counts) - stable_ids):
        errors.append(f"unknown stable function disposition: {function_id}")
    for function_id, count in sorted(function_counts.items()):
        if count != 1:
            errors.append(f"function disposition occurs {count} times: {function_id}")
    inventory_tables = {row["table"] for row in sources.table_inventory["tables"]}
    for table in sorted(inventory_tables | set(table_counts)):
        if table_counts[table] != 1:
            errors.append(f"table ownership occurs {table_counts[table]} times: {table}")
    expected_debts = {
        _module_debt(row)["id"] for row in sources.dependency_baseline["violations"]
    } | {"boundary:" + row["fingerprint"] for row in sources.boundary_baseline["violations"]}
    for debt_id in sorted(expected_debts):
        if debt_counts[debt_id] != 1:
            errors.append(f"baseline debt occurs {debt_counts[debt_id]} times: {debt_id}")
    return sorted(set(errors))


def _write(documents: list[dict], views: dict[str, str], sources: AuditSources) -> None:
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(_serialize(_manifest(sources, documents)), encoding="utf-8")
    for document in documents:
        (REVIEW_ROOT / DOMAIN_FILES[document["domain"]]).write_text(_serialize(document), encoding="utf-8")
    for filename, content in views.items():
        (GENERATED_ROOT / filename).write_text(content, encoding="utf-8")


def _drift(documents: list[dict], views: dict[str, str], sources: AuditSources) -> list[str]:
    expected = {MANIFEST_PATH: _serialize(_manifest(sources, documents))}
    expected.update({REVIEW_ROOT / DOMAIN_FILES[d["domain"]]: _serialize(d) for d in documents})
    expected.update({GENERATED_ROOT / name: content for name, content in views.items()})
    return [str(path.relative_to(REPOSITORY_ROOT)) for path, content in expected.items()
            if not path.exists() or path.read_text(encoding="utf-8") != content]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    sources = load_sources()
    documents = initialize_documents(sources, _load_documents())
    views = render_evidence_views(render_views(documents), sources)
    summary = json.loads(views["summary.json"])
    errors = _validate(documents, False)
    errors.extend(audit_consistency_errors(documents, sources))
    if args.write:
        if errors:
            print("Coverage review validation failed:", *errors, sep="\n- ", file=sys.stderr)
            return 1
        _write(documents, views, sources)
    else:
        errors.extend(f"generated drift: {path}" for path in _drift(documents, views, sources))
        if errors:
            print("Coverage review check failed:", *errors, sep="\n- ", file=sys.stderr)
            return 1
        if args.strict:
            domain_counts = summary["candidate_additions_by_domain"]
            if (summary["proposed_final_catalog_capabilities"] > 170
                    or any(count > 40 for count in domain_counts.values())):
                print(json.dumps({
                    "status": "architecture_review_required",
                    "current_catalog_capabilities": summary["current_catalog_capabilities"],
                    "candidate_capabilities": summary["candidate_capabilities"],
                    "proposed_final_catalog_capabilities": summary["proposed_final_catalog_capabilities"],
                    "candidate_additions_by_domain": domain_counts,
                }, ensure_ascii=False, sort_keys=True))
                return 3
            strict_errors = _validate(documents, True)
            if strict_errors:
                print("Coverage review strict check failed:", *strict_errors, sep="\n- ", file=sys.stderr)
                return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
