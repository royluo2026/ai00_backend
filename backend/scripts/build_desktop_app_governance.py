"""Compute a truthful, non-promotable App impact closure from native Registry sources.

The full Catalog gate is always run separately. This evidence never replaces a
failed full Catalog release or asserts that future Electron/binary work exists.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.catalog import build_catalog_entry, complete_governance_metadata, load_catalog_release
from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
from backend.scripts.build_capability_catalog import _verified_consumer_refs, current_release
from backend.scripts.build_user_function_registry import capability_ids_in_source
from plugins.simulation.simulation_backend.capabilities import connector_pairing, connector_runtime

OUTPUT = ROOT / "docs/governance/desktop-app-impact-closure.json"


def _hash(blob):
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def build_impact_closure():
    registry = build_capability_registry(ROOT)
    registrations = {(r.spec.id, r.spec.version): r for r in registry.snapshot()}
    known_ids = {key[0] for key in registrations}
    roots = set((*connector_pairing.DESKTOP_CAPABILITY_BINDINGS, *connector_runtime.DESKTOP_CAPABILITY_BINDINGS))
    keys = set(roots)
    # A conservative source-reference fixed point includes all pinned versions
    # when a Python source literal does not specify its major version. Dynamic
    # dispatch remains explicitly unverified, rather than guessed complete.
    sources = set()
    for pattern in ("plugins/simulation/simulation_backend/**/*.py", "backend/db/migrations/domains/simulation/*.sql",
                    "local-runtime/src/Ai00.Connector.Adapters.VisMockup/**/*.cs"):
        sources.update(p for p in ROOT.glob(pattern) if p.is_file()
                       and not {"bin", "obj"}.intersection(part.lower() for part in p.parts))
    sources.update(ROOT / p for p in (
        "backend/capability_v2/identity.py", "backend/capability_v2/gateway.py",
        "backend/capability_v2/policies.py", "backend/capability_v2/authorization.py",
        "backend/capability_v2/desktop_release_approval.py", "backend/capability_v2/official_domains.json",
        "backend/capability_v2/web_compatibility.py", "backend/routers/capabilities.py", "backend/routers/deps.py",
        "backend/routers/simulation_connector.py", "backend/services/jwt_service.py",
        "backend/contracts/connector_execution_plan_v1.py", "backend/contracts/connector_execution_plan_v2.py",
        "backend/domain_ports/simulation_runtime.py", "backend/scripts/build_capability_catalog.py",
        "backend/scripts/build_user_function_registry.py", "backend/scripts/build_desktop_app_governance.py",
    ))
    scanned = set()
    while sources - scanned:
        for path in sorted(sources - scanned):
            scanned.add(path)
            refs = capability_ids_in_source(path.read_text(encoding="utf-8-sig"), known_ids)
            keys.update(key for key in registrations if key[0] in refs)
        for key in keys:
            path = inspect.getsourcefile(registrations[key].handler)
            if path and ROOT in Path(path).resolve().parents:
                sources.add(Path(path).resolve())
    descriptors = []
    for key in sorted(keys):
        entry = build_catalog_entry(complete_governance_metadata(
            registrations[key].descriptor, provider_ref=f"{registrations[key].spec.owner}.provider",
            consumer_refs=_verified_consumer_refs(*key)))
        descriptors.append({**{name: entry[name] for name in (
            "id", "major_version", "capability_version_gid", "business_definition_hash",
            "owner_domain", "provider_ref", "consumer_refs", "exposure", "confirmation_policy",
            "authorization_policy", "execution_mode", "lifecycle_status")},
            "descriptor_hash": _hash(json.dumps(entry, sort_keys=True, separators=(",", ":")).encode())})
    published_path = ROOT / "docs/governance/capability-catalog-release.json"
    published = load_catalog_release(published_path.read_text(encoding="utf-8"))
    try:
        candidate = current_release()
        catalog_errors = []
        catalog_current = candidate.catalog_hash == published.catalog_hash
    except ValueError as exc:
        catalog_errors = str(exc).split("; ")
        catalog_current = False
    artifacts = [{"path": p.relative_to(ROOT).as_posix(),
                  "sha256": _hash(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))}
                 for p in sorted(sources)]
    # Git blobs are immutable even before the final evidence commit. The exact
    # source-set digest allows consumers to verify this candidate independently
    # of a mutable branch name; no dirty working tree is called release-ready.
    source_set = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    return dict(schema_version=1, consumer_id=DESKTOP_CONSUMER_ID,
        consumer_type="web", transport_classification="authenticated interactive Gateway; single Windows x64 App product",
        source_basis="content-addressed source set; not a promoted release candidate",
        source_hash_format="UTF-8 source bytes with LF line endings, matching native Provider hashing",
        source_set_hash=_hash(source_set),
        published_catalog_release=published.release_id, published_catalog_hash=published.catalog_hash,
        published_catalog_current=catalog_current, catalog_generation_errors=catalog_errors,
        roots=[f"{capability_id}@{version}" for capability_id, version in sorted(roots)],
        capabilities=descriptors, artifacts=artifacts,
        transport_bindings=list(connector_runtime.DESKTOP_TRANSPORT_BINDINGS),
        dependency_analysis="conservative fixed point over actual registered Capability literals and provider source files",
        unverified_artifacts=["Electron main/preload/Renderer consumer migration and IPC",
            "AppHost Windows x64 executable and installer", "signed release manifest and Authenticode",
            "dynamic Capability dependency dispatch", "native MySQL execution", "production runtime evidence"],
        blockers=[*([] if catalog_current else ["full_catalog_not_current"]),
            "full_release_gate_not_verified", "capability_human_approval_missing",
            "runtime_evidence_missing", "technical_release_approval_missing", "app_artifacts_not_yet_verified"],
        machine_passed=False, human_approved=False, runtime_verified=False, technical_release_approved=False, advisory=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = json.dumps(build_impact_closure(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != content:
            print("Desktop impact closure drift")
            return 1
        print("Desktop impact closure content-addressed sources verified; release remains blocked")
        return 0
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print("Desktop impact closure written; all approval/runtime states remain false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
