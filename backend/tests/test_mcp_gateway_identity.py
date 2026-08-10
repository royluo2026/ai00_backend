from pathlib import Path

import pytest

from backend.capabilities.models_next import CapabilityExecution, CapabilityRisk, CapabilitySpec
from backend.capability_v2.v1_adapter import adapt_v1_spec
from backend.routers import mcp_capabilities


ROOT = Path(__file__).resolve().parents[2]


def _spec(*, risk=CapabilityRisk.READ, execution=CapabilityExecution.CLOUD):
    return CapabilitySpec(
        id="system.mcp_test", version=1, owner="base", description="MCP test.", execution=execution,
        risk=risk, confirmation="none", permissions=(),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "properties": {"value": {"type": "string"}}, "additionalProperties": False},
    )


def test_mcp_exposure_is_read_only_cloud_and_has_output_projection():
    adapted = adapt_v1_spec(_spec())
    assert adapted.exposure.mcp is True
    assert adapted.agent_output_schema == adapted.output_schema
    assert adapt_v1_spec(_spec(risk=CapabilityRisk.WRITE)).exposure.mcp is False
    assert adapt_v1_spec(_spec(execution=CapabilityExecution.LOCAL)).exposure.mcp is False


def test_mcp_service_authentication_and_routes_fail_closed(monkeypatch):
    monkeypatch.delenv("MCP_GATEWAY_SERVICE_TOKEN", raising=False)
    with pytest.raises(Exception) as missing:
        mcp_capabilities._require_service("anything")
    assert missing.value.status_code == 503
    monkeypatch.setenv("MCP_GATEWAY_SERVICE_TOKEN", "mcp-service-secret-with-at-least-32-bytes")
    with pytest.raises(Exception) as wrong:
        mcp_capabilities._require_service("wrong")
    assert wrong.value.status_code == 401
    mcp_capabilities._require_service("mcp-service-secret-with-at-least-32-bytes")
    paths = {route.path for route in mcp_capabilities.router.routes}
    assert "/api/v2/mcp-capabilities/delegations" in paths
    assert "/api/v2/mcp-capabilities/{capability_id}:invoke" in paths


def test_mcp_gateway_has_no_raw_bearer_capability_path_and_is_base_owned():
    client = (ROOT / "services/mcp-gateway/src/capability-client.ts").read_text(encoding="utf-8")
    server = (ROOT / "services/mcp-gateway/src/server.ts").read_text(encoding="utf-8")
    ownership = (ROOT / "docs/governance/domain-ownership.json").read_text(encoding="utf-8")
    assert "/api/v1/capabilities" not in client
    assert "X-AI00-Source" not in client
    assert '"X-AI00-Delegation": delegationToken' in client
    assert "getOrExchange" in server and "CatalogCache" in server
    assert '"services/mcp-gateway/**"' in ownership
