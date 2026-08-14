#!/usr/bin/env python3
"""Exercise the signed cross-domain project-readiness plugin lifecycle."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import requests

from backend.scripts.plugin_platform_acceptance import AcceptanceError, Client


def verify_mount_contract(
    manifest: Mapping[str, Any], mount: Mapping[str, Any]
) -> tuple[str, ...]:
    """Require the runtime grant to be exactly the manifest declaration at major 1."""
    if mount.get("plugin_id") != manifest.get("plugin_id"):
        raise AcceptanceError("mount plugin_id differs from manifest")
    if not mount.get("mount_session_id") or not mount.get("mount_url"):
        raise AcceptanceError("mount is missing its session or entry URL")
    declared = tuple(str(item) for item in manifest.get("permissions") or ())
    granted = mount.get("capability_versions") or {}
    if set(declared) != set(granted) or any(granted[item] != 1 for item in declared):
        raise AcceptanceError("mount grants differ from the exact manifest permissions")
    return declared


def _submit(
    client: Client,
    package_path: Path,
    release: Mapping[str, Any],
    signature_path: Path,
) -> None:
    signature = signature_path.read_text(encoding="utf-8").strip()
    with package_path.open("rb") as package:
        client.request(
            "POST",
            "/api/v1/plugin-marketplace/releases",
            data={
                "manifest_json": json.dumps(
                    release, ensure_ascii=False, separators=(",", ":")
                ),
                "publisher_signature": signature,
            },
            files={"package": (package_path.name, package, "application/zip")},
        )
    client.request(
        "POST",
        f"/api/v1/plugin-marketplace/releases/{release['plugin_id']}/{release['version']}/review",
        json={"approved": True, "note": "project-readiness automated acceptance"},
    )


def _mounted(client: Client, plugin_id: str) -> Mapping[str, Any]:
    registry = client.request("GET", "/api/v1/plugin-marketplace/registry")["data"]
    mount = next((item for item in registry if item["plugin_id"] == plugin_id), None)
    if mount is None:
        raise AcceptanceError("enabled plugin is absent from tenant registry")
    return mount


def invoke_mount(
    client: Client,
    mount: Mapping[str, Any],
    capability_id: str,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    path = (
        f"/api/v1/plugin-marketplace/mounts/{mount['mount_session_id']}"
        f"/capabilities/{capability_id}:invoke"
    )
    result = client.request(
        "POST", path, json={"major_version": 1, "payload": dict(payload)}
    )
    if not result.get("ok"):
        error = result.get("error") or {}
        raise AcceptanceError(
            f"{capability_id} failed through Mount: "
            f"{error.get('code', 'unknown')}: {error.get('message', '')}"
        )
    return result


def run(args: argparse.Namespace) -> list[str]:
    release = json.loads(args.release.read_text(encoding="utf-8"))
    plugin_id = release["plugin_id"]
    client = Client(args.api_url, args.token)
    steps: list[str] = []

    if not args.publisher_exists and not args.resume_enabled:
        client.request(
            "POST",
            "/api/v1/plugin-marketplace/publishers",
            json={
                "publisher_id": release["publisher_id"],
                "display_name": args.publisher_name,
                "public_key_pem": args.publisher_public_key.read_text(encoding="utf-8"),
            },
        )
        steps.append("publisher registered")

    if not args.resume_enabled:
        _submit(client, args.package, release, args.signature)
        steps.append("release uploaded and approved")
        client.lifecycle(
            "plugin.install",
            {
                "plugin_id": plugin_id,
                "version": release["version"],
                "granted_capabilities": release["permissions"],
            },
        )
        client.lifecycle("plugin.enable", {"plugin_id": plugin_id})
    else:
        steps.append("resumed existing enabled installation")
    mount = _mounted(client, plugin_id)
    verify_mount_contract(release, mount)
    asset = requests.get(client.base + mount["mount_url"], timeout=(5, 30))
    if not asset.ok or b"<html" not in asset.content.lower():
        raise AcceptanceError("sandbox entry asset could not be mounted")
    invoke_mount(client, mount, "base.project.search", {"query": args.project_query, "limit": 20})
    steps.append("exact Mount contract and project search verified")

    upgrades = (args.upgrade_package, args.upgrade_release, args.upgrade_signature)
    if any(upgrades) and not all(upgrades):
        raise AcceptanceError("upgrade package, release and signature must be supplied together")
    if all(upgrades):
        upgrade = json.loads(args.upgrade_release.read_text(encoding="utf-8"))
        _submit(client, args.upgrade_package, upgrade, args.upgrade_signature)
        client.lifecycle(
            "plugin.upgrade",
            {
                "plugin_id": plugin_id,
                "version": upgrade["version"],
                "granted_capabilities": upgrade["permissions"],
            },
        )
        client.lifecycle("plugin.rollback", {"plugin_id": plugin_id})
        steps.append("upgrade and rollback verified")
        if args.activate_upgrade_after_rollback:
            client.lifecycle(
                "plugin.upgrade",
                {
                    "plugin_id": plugin_id,
                    "version": upgrade["version"],
                    "granted_capabilities": upgrade["permissions"],
                },
            )
            client.request(
                "POST",
                f"/api/v1/plugin-marketplace/installations/{plugin_id}/upgrade-health",
                json={"healthy": True},
            )
            verify_mount_contract(upgrade, _mounted(client, plugin_id))
            steps.append("upgrade re-activated and health verification completed")

    if args.leave_enabled:
        steps.append("left enabled for browser acceptance")
        return steps

    client.lifecycle("plugin.disable", {"plugin_id": plugin_id})
    if any(
        item["plugin_id"] == plugin_id
        for item in client.request("GET", "/api/v1/plugin-marketplace/registry")["data"]
    ):
        raise AcceptanceError("disabled plugin remains in tenant registry")
    client.lifecycle("plugin.uninstall", {"plugin_id": plugin_id})
    steps.append("disabled and uninstalled")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("AI00_ACCEPTANCE_API_URL", ""))
    parser.add_argument("--token", default=os.getenv("AI00_ACCEPTANCE_ADMIN_TOKEN", ""))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--upgrade-package", type=Path)
    parser.add_argument("--upgrade-release", type=Path)
    parser.add_argument("--upgrade-signature", type=Path)
    parser.add_argument("--publisher-public-key", type=Path, required=True)
    parser.add_argument("--publisher-name", default="Devteam Project Readiness")
    parser.add_argument("--publisher-exists", action="store_true")
    parser.add_argument("--resume-enabled", action="store_true")
    parser.add_argument("--activate-upgrade-after-rollback", action="store_true")
    parser.add_argument("--project-query", default="E2E-")
    parser.add_argument("--leave-enabled", action="store_true")
    args = parser.parse_args()
    if not args.api_url or not args.token:
        raise SystemExit("AI00_ACCEPTANCE_API_URL and AI00_ACCEPTANCE_ADMIN_TOKEN are required")
    print(json.dumps({"ok": True, "steps": run(args)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
