import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def document(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def stable_capabilities():
    return [
        item for item in document("docs/capabilities/catalog.v2.json")["capabilities"]
        if item["lifecycle_status"] == "stable"
    ]


def key(item):
    return f'{item["id"]}@{item["major_version"]}'
