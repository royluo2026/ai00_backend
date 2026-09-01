import json
from pathlib import Path

from backend.capability_v2.catalog import load_catalog_release
from backend.capability_v2.docs.generator import build_documentation


ROOT = Path(__file__).resolve().parents[3]


def document(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def stable_capabilities():
    return [
        item for item in build_documentation(load_catalog_release(
            (ROOT / "docs/governance/capability-catalog-release.json").read_text(encoding="utf-8")
        )).machine_catalog["capabilities"]
        if item["lifecycle_status"] == "stable"
    ]


def key(item):
    return f'{item["id"]}@{item["major_version"]}'
