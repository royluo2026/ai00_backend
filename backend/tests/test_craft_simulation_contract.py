import copy
import unittest

from backend.contracts.craft_execution_plan_v1 import (
    ContractValidationError,
    seal_execution_plan,
    validate_execution_plan,
)
from backend.contracts.simulation_environment_source_v1 import (
    pin_environment_source,
    verify_environment_source,
)


def sample_plan():
    return {
        "contract_id": "craft.execution-plan",
        "contract_version": 1,
        "source": {"bop_version_gid": "bop-v7", "revision": 3, "project_gid": "project-1"},
        "published_at": "2026-08-03T10:00:00Z",
        "operations": [
            {
                "operation_id": "op-10",
                "sequence": 10,
                "kind": "operation",
                "name": "Position part",
                "predecessor_ids": [],
                "resource_refs": ["fixture:A"],
                "model_refs": ["ois:model-a@sha256:abc"],
                "parameters": {"station": "S10"},
            },
            {
                "operation_id": "op-20",
                "sequence": 20,
                "kind": "operation",
                "name": "Fasten part",
                "predecessor_ids": ["op-10"],
                "resource_refs": ["tool:T1"],
                "model_refs": [],
                "parameters": {"torque_nm": 30},
            },
        ],
    }


class CraftSimulationContractTests(unittest.TestCase):
    def test_simulation_pins_version_revision_and_hash(self):
        sealed = seal_execution_plan(sample_plan())
        pinned = pin_environment_source(sealed, "ois://craft/execution-plans/bop-v7/r3.json")
        self.assertEqual(pinned["source_bop_version_gid"], "bop-v7")
        self.assertEqual(pinned["source_bop_revision"], 3)
        self.assertEqual(pinned["source_bop_hash"], sealed["content_hash"])
        verify_environment_source(pinned, sealed)

    def test_hash_is_deterministic_for_set_like_reference_order(self):
        first = sample_plan()
        first["operations"][0]["resource_refs"] = ["fixture:B", "fixture:A"]
        second = copy.deepcopy(first)
        second["operations"][0]["resource_refs"].reverse()
        self.assertEqual(seal_execution_plan(first)["content_hash"], seal_execution_plan(second)["content_hash"])

    def test_modified_plan_cannot_reuse_old_hash(self):
        sealed = seal_execution_plan(sample_plan())
        modified = copy.deepcopy(sealed)
        modified["operations"][1]["parameters"]["torque_nm"] = 45
        with self.assertRaises(ContractValidationError):
            validate_execution_plan(modified)

    def test_unknown_or_forward_predecessor_is_rejected(self):
        invalid = sample_plan()
        invalid["operations"][0]["predecessor_ids"] = ["op-20"]
        with self.assertRaises(ContractValidationError):
            seal_execution_plan(invalid)

    def test_pinned_source_rejects_different_revision(self):
        sealed = seal_execution_plan(sample_plan())
        pinned = pin_environment_source(sealed, "ois://craft/execution-plans/bop-v7/r3.json")
        pinned["source_bop_revision"] = 2
        with self.assertRaises(ContractValidationError):
            verify_environment_source(pinned, sealed)
