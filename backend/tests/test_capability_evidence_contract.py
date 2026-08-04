import unittest

from backend.capabilities.models_next import CapabilityContext, CapabilityOutput, CapabilitySpec, EvidenceRef
from backend.capabilities.registry_next import CapabilityRegistry


class CapabilityEvidenceContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_handler_evidence_is_separate_from_business_data(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilitySpec(id="test.evidence", plugin_callable=True),
            lambda _payload, _context: CapabilityOutput(
                data={"decision": "pass"},
                evidence=(EvidenceRef(kind="ois.revision", reference="ois://knowledge/rev-1", digest="sha256:abc", summary="published revision"),),
            ),
        )
        result = await registry.invoke(
            "test.evidence", {},
            CapabilityContext(user_gid="u1", source="plugin", request_id="r1", plugin_id="acme.ai00.hello", plugin_version="1.0.0"),
        )
        self.assertEqual(result.data, {"decision": "pass"})
        self.assertEqual(result.evidence[0].reference, "ois://knowledge/rev-1")
        self.assertEqual(result.audit["plugin_id"], "acme.ai00.hello")
        self.assertEqual(result.audit["request_id"], "r1")


if __name__ == "__main__":
    unittest.main()