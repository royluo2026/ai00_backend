import hashlib
import json
from pathlib import Path

from plugins.simulation.simulation_backend.capabilities.connector_contracts import (
    OPERATION_REF, OUTPUT_SCHEMAS, TREE_NODE,
)
from plugins.simulation.simulation_backend.capabilities.connector_runtime import (
    DIRECT_VISMOCKUP_OPERATIONS,
)


def test_live_tree_visibility_does_not_mutate_the_published_legacy_capability_schema():
    assert "visible" not in TREE_NODE["properties"]
    assert OUTPUT_SCHEMAS["simulation.vismockup.tree.read.request"] is OPERATION_REF


def test_live_tree_visibility_keeps_the_governed_read_operation_pin():
    descriptor = Path(__file__).resolve().parents[3] / "docs/contracts/vismockup.tree.read@2.json"
    canonical = json.dumps(json.loads(descriptor.read_text(encoding="utf-8")),
                           ensure_ascii=False, separators=(",", ":"))
    expected_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert DIRECT_VISMOCKUP_OPERATIONS["tree"] == (
        "vismockup.tree.read@2",
        expected_hash,
    )
    assert expected_hash == "sha256:5d69cc98e38bd721fb55623b62df5162e68cbfb9bcb51c1b6c25d351c486de7c"
