"""Initialize, validate, and render Capability V2 coverage review documents."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from collections import Counter
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
DOMAINS = (
    "Base Platform", "Agent", "Craft", "Digital Model", "Project Management",
    "Simulation", "Ontology", "Knowledge", "Local Integration",
)
DOMAIN_FILES = {domain: domain.lower().replace(" ", "-") + ".json" for domain in DOMAINS}
CONSUMERS = ("web", "rest", "plugin", "agent", "mcp", "local_runtime")
BOOTSTRAP_REVIEWER = "existing-user-function-registry"
BOOTSTRAP_DATE = "2026-08-11"


class AuditSources(NamedTuple):
    registry: dict
    catalog: dict
    manifest: dict
    reviewed_against: dict


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
    reviewed_against = manifest.get("reviewed_against") or {
        "git_commit": _head(root),
        "registry_sha256": _sha256(registry_path),
        "catalog_release": catalog["release_id"],
        "catalog_sha256": _sha256(catalog_path),
    }
    return AuditSources(registry, catalog, manifest, reviewed_against)


def _discovered(row: dict) -> dict:
    return {
        "function_id": row["function_id"],
        "domain": row["domain"],
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


def initialize_documents(sources: AuditSources, existing: dict[str, dict] | None = None) -> list[dict]:
    existing = existing or {}
    rows = stable_functions(sources)
    result = []
    for domain in DOMAINS:
        domain_rows = [row for row in rows if row["domain"] == domain]
        document = copy.deepcopy(existing.get(domain)) if domain in existing else _empty_review(domain, sources.reviewed_against)
        if domain not in existing:
            document = _bootstrap_existing(document, domain_rows)
        document["reviewed_against"] = copy.deepcopy(sources.reviewed_against)
        result.append(merge_domain_review(document, domain_rows))
    return result


def _lines(title: str, header: str, rows: list[str]) -> str:
    return "\n".join([f"# {title}", "", header, "", *rows, ""])


def render_views(documents: list[dict]) -> dict[str, str]:
    """Return all generated views with canonical ordering independent of input order."""
    functions, candidates, exposures, extractions, databases = [], [], [], [], []
    counts = Counter()
    for document in sorted(documents, key=lambda item: item["domain"]):
        domain = document["domain"]
        for function_id in sorted(document["unreviewed_functions"]):
            functions.append(f"| {domain} | `{function_id}` | unreviewed | — |")
            counts["unreviewed"] += 1
        for function_id in sorted(document["excluded_functions"]):
            functions.append(f"| {domain} | `{function_id}` | excluded | — |")
            counts["excluded"] += 1
        for capability_id, group in sorted(document["capabilities"].items()):
            if group["kind"] == "candidate":
                outcome = group["candidate_definition"]["business_outcome"].replace("|", "\\|")
                candidates.append(f"| {domain} | {outcome} | `{capability_id}` |")
                counts["candidate_capabilities"] += 1
            exposure = group["consumer_exposure"]
            flags = [name for name in CONSUMERS if exposure[name]["enabled"]]
            exposures.append(f"| {domain} | `{capability_id}` | {', '.join(flags) or 'none'} |")
            for function_id, disposition in sorted(group["function_dispositions"].items()):
                functions.append(f"| {domain} | `{function_id}` | {disposition['resolution']} | `{capability_id}` |")
                counts[disposition["resolution"]] += 1
        for row in sorted(document["code_extractions"], key=lambda item: item["id"]):
            extractions.append(f"| {domain} | `{row['id']}` | {row['disposition']} |")
        for row in sorted(document["database_boundaries"], key=lambda item: item["table"]):
            databases.append(f"| {domain} | `{row['table']}` | {row['owner_domain']} | {row['migration_stream']} |")
    summary = {
        "schema_version": 1,
        "domains": len(documents),
        "stable_functions": counts["unreviewed"] + counts["excluded"] + counts["existing_capability"] + counts["new_capability"],
        "resolutions": {key: counts[key] for key in ("existing_capability", "new_capability", "excluded", "unreviewed")},
        "candidate_capabilities": counts["candidate_capabilities"],
    }
    return {
        "function-dispositions.md": _lines("Function dispositions", "| Domain | Function | Resolution | Capability |\n|---|---|---|---|", functions),
        "capability-candidates.md": _lines("Capability candidates", "| Domain | Business outcome | Capability |\n|---|---|---|", candidates),
        "consumer-exposure.md": _lines("Consumer exposure", "| Domain | Capability | Enabled consumers |\n|---|---|---|", exposures),
        "code-ownership-extractions.md": _lines("Code ownership extractions", "| Domain | Extraction | Disposition |\n|---|---|---|", extractions),
        "database-ownership-migrations.md": _lines("Database ownership and migrations", "| Domain | Table | Owner | Migration stream |\n|---|---|---|---|", databases),
        "summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    }


def _load_documents() -> dict[str, dict]:
    result = {}
    for domain, filename in DOMAIN_FILES.items():
        path = REVIEW_ROOT / filename
        if path.exists():
            result[domain] = _json(path)
    return result


def _manifest(reviewed_against: dict) -> dict:
    return {"schema_version": 1, "reviewed_against": reviewed_against, "domains": list(DOMAINS)}


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


def _write(documents: list[dict], views: dict[str, str], reviewed_against: dict) -> None:
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(_serialize(_manifest(reviewed_against)), encoding="utf-8")
    for document in documents:
        (REVIEW_ROOT / DOMAIN_FILES[document["domain"]]).write_text(_serialize(document), encoding="utf-8")
    for filename, content in views.items():
        (GENERATED_ROOT / filename).write_text(content, encoding="utf-8")


def _drift(documents: list[dict], views: dict[str, str], reviewed_against: dict) -> list[str]:
    expected = {MANIFEST_PATH: _serialize(_manifest(reviewed_against))}
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
    views = render_views(documents)
    errors = _validate(documents, args.strict)
    if args.write:
        if errors:
            print("Coverage review validation failed:", *errors, sep="\n- ", file=sys.stderr)
            return 1
        _write(documents, views, sources.reviewed_against)
    else:
        errors.extend(f"generated drift: {path}" for path in _drift(documents, views, sources.reviewed_against))
        if errors:
            print("Coverage review check failed:", *errors, sep="\n- ", file=sys.stderr)
            return 1
    summary = json.loads(views["summary.json"])
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
