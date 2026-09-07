"""Compute a truthful, non-promotable App impact closure from native Registry sources.

The full Catalog gate is always run separately. This evidence never replaces a
failed full Catalog release or asserts that future Electron/binary work exists.
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import tempfile
from fnmatch import fnmatchcase
import hashlib
import inspect
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = ROOT / "docs/governance/desktop-app-impact-closure.json"


def _hash(blob):
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _module_index(tracked):
    modules = {}
    for name in tracked:
        if not name.endswith(".py"):
            continue
        module = name[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        modules[module] = name
        if module.startswith("plugins."):
            # Official provider loaders also expose plugin-local package names.
            modules[".".join(module.split(".")[2:])] = name
    return modules


def _static_imports(path, content, modules):
    package = path[:-3].replace("/", ".").split(".")[:-1]
    dependencies = set()
    def include(module):
        parts = module.split(".")
        for end in range(1, len(parts) + 1):
            name = ".".join(parts[:end])
            if name in modules:
                dependencies.add(modules[name])
    for node in ast.walk(ast.parse(content, filename=path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                include(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[:len(package) - node.level + 1] if node.level else []
            base = ".".join([*prefix, *([node.module] if node.module else [])])
            include(base)
            for alias in node.names:
                include(f"{base}.{alias.name}")
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            if ((isinstance(func, ast.Name) and func.id == "__import__") or
                (isinstance(func, ast.Attribute) and func.attr == "import_module")):
                if isinstance(node.args[0].value, str):
                    include(node.args[0].value)
    return dependencies


def build_impact_closure(source_revision="HEAD"):
    """Resolve once, then load Registry, metadata and source from that Git tree.

    The child interpreter avoids already-imported mutable working-tree modules.
    git cat-file supplies exact tracked blobs; untracked and dirty files cannot
    enter provider discovery, dependency scans, Catalog generation or hashes.
    """
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)
    commit = git("rev-parse", f"{source_revision}^{{commit}}").decode().strip()
    tree = git("rev-parse", f"{commit}^{{tree}}").decode().strip()
    blobs = {}
    for item in git("ls-tree", "-r", "-z", commit).split(b"\0"):
        if not item:
            continue
        info, raw_name = item.split(b"\t", 1)
        mode, kind, oid = info.decode().split()
        if kind == "blob":
            if mode not in ("100644", "100755"):
                raise ValueError("non_regular_source_blob")
            blobs[raw_name.decode("utf-8")] = oid
    with tempfile.TemporaryDirectory(prefix="ai00-desktop-git-") as directory:
        snapshot = Path(directory).resolve()
        objects = subprocess.check_output(["git", "cat-file", "--batch"], cwd=ROOT,
            input="".join(oid + "\n" for oid in blobs.values()).encode())
        offset = 0
        for name, oid in blobs.items():
            end = objects.index(b"\n", offset)
            actual_oid, kind, size = objects[offset:end].decode().split()
            size = int(size)
            data = objects[end + 1:end + 1 + size]
            offset = end + size + 2
            if actual_oid != oid or kind != "blob":
                raise ValueError(f"source_blob_mismatch: {name}")
            target = (snapshot / name).resolve()
            if not target.is_relative_to(snapshot):
                raise ValueError("source_path_outside_snapshot")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        # Native governance validates historical baseline revisions. Give the
        # snapshot its own fixed detached HEAD and read-only object alternates;
        # never redirect that validation to the mutable original working tree.
        git_dir = snapshot / ".git"
        (git_dir / "objects/info").mkdir(parents=True)
        (git_dir / "refs").mkdir()
        common_dir = Path(git("rev-parse", "--git-common-dir").decode().strip())
        objects_dir = (ROOT / common_dir / "objects").resolve()
        (git_dir / "objects/info/alternates").write_text(objects_dir.as_posix() + "\n", encoding="utf-8", newline="\n")
        (git_dir / "HEAD").write_text(commit + "\n", encoding="ascii")
        (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = false\n", encoding="ascii")
        # Execute the committed generator too. Load installed dependency paths
        # directly, without PYTHONPATH, .pth or sitecustomize startup execution.
        worker = snapshot / "backend/scripts/build_desktop_app_governance.py"
        launcher = ("import runpy,site,sys; sys.path.extend(site.getsitepackages()); "
                    "sys.path.append(site.getusersitepackages()); sys.argv=sys.argv[1:]; "
                    "runpy.run_path(sys.argv[0],run_name='__main__')")
        result = subprocess.run([sys.executable, "-I", "-S", "-c", launcher,
            str(worker), "--snapshot", str(snapshot)],
            cwd=snapshot, input=json.dumps(dict(commit=commit, tree=tree, blobs=blobs)),
            text=True, encoding="utf-8", capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}, check=True)
        return json.loads(result.stdout)


def _snapshot_impact_closure(metadata):
    from backend.capability_v2.bootstrap import build_capability_registry
    from backend.capability_v2.catalog import build_catalog_entry, complete_governance_metadata, load_catalog_release
    from backend.capability_v2.identity import DESKTOP_CONSUMER_ID
    from backend.scripts.build_capability_catalog import _verified_consumer_refs, current_release
    from backend.scripts.build_user_function_registry import capability_ids_in_source
    from plugins.simulation.simulation_backend.capabilities import connector_pairing, connector_runtime

    registry = build_capability_registry(ROOT)
    registrations = {(r.spec.id, r.spec.version): r for r in registry.snapshot()}
    known_ids = {key[0] for key in registrations}
    roots = set((*connector_pairing.DESKTOP_CAPABILITY_BINDINGS, *connector_runtime.DESKTOP_CAPABILITY_BINDINGS))
    keys = set(roots)
    # A conservative source-reference fixed point includes all pinned versions
    # when a Python source literal does not specify its major version. Dynamic
    # dispatch remains explicitly unverified, rather than guessed complete.
    tracked = metadata["blobs"]
    sources = set()
    # fnmatch '*' spans directory separators; enumerate only committed paths.
    for pattern in ("plugins/simulation/simulation_backend/*.py", "backend/db/migrations/domains/simulation/*.sql",
                    "local-runtime/src/Ai00.Connector.Adapters.VisMockup/*.csproj"):
        sources.update(ROOT / name for name in tracked if fnmatchcase(name, pattern)
                       and not {"bin", "obj"}.intersection(part.lower() for part in Path(name).parts))
    # All interactive sibling entrypoints share this principal trust boundary.
    sources.update(ROOT / name for name in tracked if name.endswith(".py")
                   and "/tests/" not in name and "get_authenticated_principal" in
                   (ROOT / name).read_text(encoding="utf-8-sig"))
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
    modules = _module_index(tracked)
    edges = set()
    scanned = set()
    while sources - scanned:
        for path in sorted(sources - scanned):
            scanned.add(path)
            content = path.read_text(encoding="utf-8-sig")
            if path.suffix == ".py":
                for dependency in _static_imports(path.relative_to(ROOT).as_posix(), content, modules):
                    sources.add(ROOT / dependency)
                    edges.add((path.relative_to(ROOT).as_posix(), dependency))
            elif path.suffix == ".csproj":
                project = ET.fromstring(content)
                dependencies = {ROOT / name for name in tracked if name.endswith(".cs")
                    and (ROOT / name).is_relative_to(path.parent)
                    and not {"bin", "obj"}.intersection(part.lower() for part in Path(name).parts)}
                for reference in project.iter("ProjectReference"):
                    dependencies.add((path.parent / reference.attrib["Include"].replace("\\", "/")).resolve())
                # Repository-wide MSBuild properties are static project inputs.
                dependencies.update(parent / name for parent in (path.parent, *path.parents)
                    if parent.is_relative_to(ROOT) for name in ("Directory.Build.props", "Directory.Build.targets")
                    if (parent / name).relative_to(ROOT).as_posix() in tracked)
                for dependency in dependencies:
                    relative = dependency.relative_to(ROOT).as_posix()
                    if relative not in tracked:
                        raise ValueError(f"untracked_project_dependency: {relative}")
                    sources.add(dependency)
                    edges.add((path.relative_to(ROOT).as_posix(), relative))
            refs = capability_ids_in_source(content, known_ids)
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
                  "git_blob_oid": tracked[p.relative_to(ROOT).as_posix()],
                  "sha256": _hash(p.read_bytes())}
                 for p in sorted(sources)]
    # Git blobs are immutable even before the final evidence commit. The exact
    # source-set digest allows consumers to verify this candidate independently
    # of a mutable branch name; no dirty working tree is called release-ready.
    source_set = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    return dict(schema_version=1, consumer_id=DESKTOP_CONSUMER_ID,
        consumer_type="web", transport_classification="authenticated interactive Gateway; single Windows x64 App product",
        source_basis="immutable Git commit tree; not a promoted release candidate",
        source_commit=metadata["commit"], source_tree=metadata["tree"],
        source_hash_format="exact Git blob bytes (no working directory normalization)",
        source_set_hash=_hash(source_set),
        published_catalog_release=published.release_id, published_catalog_hash=published.catalog_hash,
        published_catalog_current=catalog_current, catalog_generation_errors=catalog_errors,
        roots=[f"{capability_id}@{version}" for capability_id, version in sorted(roots)],
        capabilities=descriptors, artifacts=artifacts,
        transport_bindings=list(connector_runtime.DESKTOP_TRANSPORT_BINDINGS),
        dependency_analysis="fixed point over registered Capability literals, handlers, and all repository-resolvable Python AST imports (including conditional/function-local imports and package initializers), plus C# ProjectReference/default compile inputs and MSBuild properties",
        static_dependency_edges=[{"source": source, "dependency": dependency} for source, dependency in sorted(edges)],
        unverified_artifacts=["Electron main/preload/Renderer consumer migration and IPC",
            "AppHost Windows x64 executable and installer", "signed release manifest and Authenticode",
            "non-literal runtime dispatch (static imports are included above)", "native MySQL execution", "production runtime evidence"],
        blockers=[*([] if catalog_current else ["full_catalog_not_current"]),
            "full_release_gate_not_verified", "capability_human_approval_missing",
            "runtime_evidence_missing", "technical_release_approval_missing", "app_artifacts_not_yet_verified"],
        machine_passed=False, human_approved=False, runtime_verified=False, technical_release_approved=False, advisory=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--source-revision", default=None)
    args = parser.parse_args(argv)
    revision = args.source_revision
    if revision is None and args.check and OUTPUT.is_file():
        revision = json.loads(OUTPUT.read_text(encoding="utf-8")).get("source_commit", "HEAD")
    content = json.dumps(build_impact_closure(revision or "HEAD"), ensure_ascii=False, indent=2) + "\n"
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
    if len(sys.argv) == 3 and sys.argv[1] == "--snapshot":
        ROOT = Path(sys.argv[2]).resolve()
        sys.path.insert(0, str(ROOT))
        print(json.dumps(_snapshot_impact_closure(json.load(sys.stdin)), ensure_ascii=True))
    else:
        raise SystemExit(main())
