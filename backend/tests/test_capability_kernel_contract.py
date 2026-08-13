import asyncio
import unittest
from pathlib import Path

from backend.capability_v2 import provider_contracts as models_next
from backend.capability_v2.bootstrap import build_capability_registry
from backend.capability_v2.provider_contracts import CapabilityContext, CapabilitySpec
from backend.capabilities.registry_next import CapabilityRegistry


class CapabilityKernelContractTests(unittest.TestCase):
    def test_capability_spec_exposes_governance_metadata(self):
        expected = {"owner", "use_when", "do_not_use_when", "subject_concepts", "effects"}
        self.assertTrue(expected.issubset(CapabilitySpec.model_fields))

    def test_registered_capabilities_declare_their_real_owner(self):
        expected_owners = {
            "system": "base",
            "craft": "craft",
            "digital_model": "digital_model",
            "factory": "factory",
            "integration": "integration",
            "knowledge": "knowledge",
            "ontology": "ontology",
            "identity": "base",
            "semantic": "base",
            "base": "base",
            "plugin": "base",
            "project": "project_management",
            "local": "device",
            "simulation": "simulation",
            "vismockup": "device",
            "agent": "agent",
        }
        repository_root = Path(__file__).resolve().parents[2]
        registry = build_capability_registry(
            repository_root,
            repository_root / "backend/capability_v2/official_domains.json",
        )
        for spec in registry.list():
            expected_owner = (
                "project_management"
                if spec.id.startswith("base.project.")
                else expected_owners[spec.id.split(".", 1)[0]]
            )
            self.assertEqual(spec.owner, expected_owner, spec.id)

    def test_business_error_keeps_stable_code_and_details(self):
        self.assertTrue(hasattr(models_next, "CapabilityBusinessError"))
        error_type = getattr(models_next, "CapabilityBusinessError")
        error = error_type(
            "version_not_published",
            "BOP version is not published",
            details={"version_gid": "v1"},
        )
        self.assertEqual(error.code, "version_not_published")
        self.assertEqual(error.details, {"version_gid": "v1"})
        self.assertFalse(error.retryable)

    def test_registry_rejects_invalid_handler_output(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilitySpec(
                id="test.output.get",
                owner="test",
                output_schema={"type": "object", "required": ["gid"]},
            ),
            lambda _payload, _context: {"wrong": True},
        )
        with self.assertRaisesRegex(ValueError, "output.*missing required field: gid"):
            asyncio.run(
                registry.invoke(
                    "test.output.get",
                    {},
                    CapabilityContext(user_gid="u1", request_id="r1"),
                )
            )


if __name__ == "__main__":
    unittest.main()
