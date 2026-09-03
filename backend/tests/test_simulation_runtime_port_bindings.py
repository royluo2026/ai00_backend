from plugins.simulation.simulation_backend.capabilities.capture_runs import (
    default_provider as capture_provider,
)
from plugins.simulation.simulation_backend.capabilities.environment_composition import (
    default_provider as composition_provider,
)


def test_production_simulation_providers_use_real_owner_domain_ports():
    ports = (
        composition_provider.craft_port,
        composition_provider.knowledge_port,
        composition_provider.connector_port,
        capture_provider.workflow.connector_port,
        capture_provider.workflow.craft_port,
    )

    assert all(not type(port).__name__.startswith("_Unavailable") for port in ports)
