#!/usr/bin/env python3
"""Run the signed reference-plugin upload, review, install, runtime and uninstall smoke path."""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

import requests


class AcceptanceError(RuntimeError):
    pass


def _message(response: requests.Response) -> str:
    try:
        value = response.json()
        detail = value.get("detail") or value.get("msg") or value
        return detail.get("message") if isinstance(detail, dict) and detail.get("message") else str(detail)
    except Exception:
        return response.text[:500]


class Client:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.headers = {"X-AI00-Token": token}

    def request(self, method: str, path: str, **kwargs):
        headers = dict(self.headers); headers.update(kwargs.pop("headers", {}))
        response = requests.request(method, self.base + path, headers=headers, timeout=(5, 60), **kwargs)
        if not response.ok:
            raise AcceptanceError(f"{method} {path} returned {response.status_code}: {_message(response)}")
        return response.json()

    def lifecycle(self, capability: str, payload: dict):
        path = f"/api/v1/capabilities/{capability}"
        confirmed = self.request("POST", path + ":confirm", json={"payload":payload}, headers={"X-AI00-Source":"web"})
        token = confirmed["data"]["confirmation_token"]
        return self.request("POST", path + ":invoke", json={"payload":payload,"confirmation_token":token}, headers={"X-AI00-Source":"web"})


def run(args) -> list[str]:
    release = json.loads(args.release.read_text(encoding="utf-8"))
    plugin_id, version = release["plugin_id"], release["version"]
    permissions = release.get("permissions", [])
    signature = args.signature.read_text(encoding="utf-8").strip()
    public_key = args.publisher_public_key.read_text(encoding="utf-8")
    client = Client(args.api_url, args.token)
    steps: list[str] = []

    if not args.publisher_exists:
        client.request("POST", "/api/v1/plugin-marketplace/publishers", json={"publisher_id":release["publisher_id"],"display_name":args.publisher_name,"public_key_pem":public_key})
        steps.append("publisher registered")

    def submit(package_path: Path, manifest: dict, detached_signature: str) -> None:
        with package_path.open("rb") as package:
            client.request("POST", "/api/v1/plugin-marketplace/releases", data={"manifest_json":json.dumps(manifest,ensure_ascii=False,separators=(",",":")),"publisher_signature":detached_signature}, files={"package":(package_path.name,package,"application/zip")})
        client.request("POST", f"/api/v1/plugin-marketplace/releases/{manifest['plugin_id']}/{manifest['version']}/review", json={"approved":True,"note":"automated staging acceptance"})

    submit(args.package, release, signature)
    steps.append("release uploaded, reviewed and platform-signed")

    payload={"plugin_id":plugin_id,"version":version,"granted_capabilities":permissions}
    client.lifecycle("plugin.install",payload); steps.append("installed disabled")
    client.lifecycle("plugin.enable",{"plugin_id":plugin_id}); steps.append("enabled")

    registry=client.request("GET","/api/v1/plugin-marketplace/registry")["data"]
    mounted=next((item for item in registry if item["plugin_id"]==plugin_id),None)
    if not mounted: raise AcceptanceError("enabled plugin is absent from tenant registry")
    asset=requests.get(client.base + mounted["mount_url"],timeout=(5,30))
    if not asset.ok or b"<html" not in asset.content.lower(): raise AcceptanceError("sandbox entry asset could not be mounted")
    steps.append("sandbox entry mounted from OIS")

    invoke_path="/api/v1/capabilities/system.echo:invoke"
    identity={"X-AI00-Source":"plugin","X-AI00-Plugin-ID":plugin_id,"X-AI00-Plugin-Version":version,"X-Request-ID":f"accept-web-{uuid.uuid4().hex}"}
    client.request("POST",invoke_path,json={"payload":{"acceptance":"web"}},headers=identity); steps.append("web plugin capability invoked")
    run_id=f"accept-agent-{uuid.uuid4().hex}"
    agent_identity={"X-AI00-Source":"agent","X-AI00-Plugin-ID":plugin_id,"X-AI00-Plugin-Version":version,"X-AI00-Agent-Run-ID":run_id}
    client.request("POST",invoke_path,json={"payload":{"acceptance":"agent-1"}},headers=agent_identity)
    client.request("POST",invoke_path,json={"payload":{"acceptance":"agent-2"}},headers=agent_identity)
    steps.append("agent run invoked twice with one usage dedupe identity")

    upgrade_values = (args.upgrade_package, args.upgrade_release, args.upgrade_signature)
    if any(upgrade_values) and not all(upgrade_values):
        raise AcceptanceError("upgrade package, release and signature must be supplied together")
    if all(upgrade_values):
        upgrade = json.loads(args.upgrade_release.read_text(encoding="utf-8"))
        if upgrade["plugin_id"] != plugin_id or upgrade["version"] == version:
            raise AcceptanceError("upgrade release must use the same plugin_id and a different version")
        submit(args.upgrade_package, upgrade, args.upgrade_signature.read_text(encoding="utf-8").strip())
        client.lifecycle("plugin.upgrade", {"plugin_id":plugin_id,"version":upgrade["version"],"granted_capabilities":upgrade.get("permissions",[])})
        client.lifecycle("plugin.upgrade.finish", {"plugin_id":plugin_id,"healthy":False})
        client.lifecycle("plugin.rollback", {"plugin_id":plugin_id})
        steps.append("upgrade failure and rollback verified")

    client.lifecycle("plugin.disable",{"plugin_id":plugin_id}); steps.append("disabled")
    if any(item["plugin_id"]==plugin_id for item in client.request("GET","/api/v1/plugin-marketplace/registry")["data"]):
        raise AcceptanceError("disabled plugin remains in tenant registry")
    client.lifecycle("plugin.uninstall",{"plugin_id":plugin_id}); steps.append("uninstalled")
    return steps


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url",default=os.getenv("AI00_ACCEPTANCE_API_URL",""))
    parser.add_argument("--token",default=os.getenv("AI00_ACCEPTANCE_ADMIN_TOKEN",""))
    parser.add_argument("--package",type=Path,required=True)
    parser.add_argument("--release",type=Path,required=True)
    parser.add_argument("--signature",type=Path,required=True)
    parser.add_argument("--upgrade-package",type=Path)
    parser.add_argument("--upgrade-release",type=Path)
    parser.add_argument("--upgrade-signature",type=Path)
    parser.add_argument("--publisher-public-key",type=Path,required=True)
    parser.add_argument("--publisher-name",default="AI00 Acceptance Publisher")
    parser.add_argument("--publisher-exists",action="store_true")
    args=parser.parse_args()
    if not args.api_url or not args.token: raise SystemExit("AI00_ACCEPTANCE_API_URL and AI00_ACCEPTANCE_ADMIN_TOKEN are required")
    steps=run(args)
    print(json.dumps({"ok":True,"steps":steps},ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())