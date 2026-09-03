"""Simulation-facing proxies for owner-populated neutral domain ports."""

from backend.domain_ports.simulation_runtime import (
    ConnectorPortProxy,
    CraftExecutionPlanPortProxy,
    CraftScreenshotPortProxy,
    KnowledgeMappingPortProxy,
)

craft_execution_port = CraftExecutionPlanPortProxy()
craft_screenshot_port = CraftScreenshotPortProxy()
connector_port = ConnectorPortProxy()
knowledge_mapping_port = KnowledgeMappingPortProxy()

__all__ = [
    "craft_execution_port", "craft_screenshot_port", "connector_port",
    "knowledge_mapping_port",
]
