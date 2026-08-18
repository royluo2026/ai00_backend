from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

DOMAINS = {
    "base": ("backend/db/connection.py", "AI00_BASE", 2, 20),
    "agent": ("plugins/agent/agent_backend/data/connection.py", "AI00_AGENT", 1, 10),
    "craft": ("plugins/craft/craft_backend/data/connection.py", "AI00_CRAFT", 1, 20),
    "device": ("plugins/device/device_backend/data/connection.py", "AI00_DEVICE", 1, 10),
    "digital_model": ("plugins/digital_model/digital_model_backend/data/connection.py", "AI00_DIGITAL_MODEL", 1, 20),
    "factory": ("plugins/factory/factory_backend/infrastructure/connection.py", "AI00_FACTORY", 1, 20),
    "integration": ("plugins/integration/integration_backend/data/connection.py", "AI00_INTEGRATION", 1, 10),
    "knowledge": ("plugins/knowledge/knowledge_backend/data/connection.py", "AI00_KNOWLEDGE", 1, 20),
    "ontology": ("plugins/ontology/ontology_backend/infrastructure/connection.py", "AI00_ONTOLOGY", 1, 20),
    "project_management": ("plugins/project_management/project_management_backend/data/connection.py", "AI00_PROJECT_MANAGEMENT", 1, 20),
    "simulation": ("plugins/simulation/simulation_backend/data/connection.py", "AI00_SIMULATION", 1, 10),
}


def test_every_domain_uses_shared_parser_with_unique_prefix_and_own_pool():
    prefixes = set()
    for domain, (relative, prefix, _minimum, _maximum) in DOMAINS.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert f'pool_limits("{domain}")' in source
        assert "_pool" in source
        prefixes.add(prefix)
    assert len(prefixes) == len(DOMAINS)


def test_domain_defaults_preserve_existing_pool_limits():
    from backend.capability_v2.domain_resource_config import DOMAIN_POOL_DEFAULTS, pool_limits

    for domain, (_relative, prefix, minimum, maximum) in DOMAINS.items():
        assert DOMAIN_POOL_DEFAULTS[domain].env_prefix == prefix
        limits = pool_limits(domain, environ={})
        assert (limits.minimum, limits.maximum) == (minimum, maximum)


def test_domain_pool_overrides_are_bounded_and_independent():
    from backend.capability_v2.domain_resource_config import pool_limits

    limits = pool_limits("craft", environ={
        "AI00_CRAFT_DB_POOL_MIN": "2",
        "AI00_CRAFT_DB_POOL_MAX": "7",
    })
    assert (limits.minimum, limits.maximum) == (2, 7)
    with pytest.raises(ValueError, match="minimum cannot exceed maximum"):
        pool_limits("craft", environ={
            "AI00_CRAFT_DB_POOL_MIN": "8",
            "AI00_CRAFT_DB_POOL_MAX": "7",
        })


def test_aggregate_budget_multiplies_by_workers_and_fails_closed():
    from backend.capability_v2.domain_resource_config import validate_aggregate_pool_budget

    result = validate_aggregate_pool_budget(environ={
        "AI00_WEB_WORKERS": "1",
        "AI00_DB_POOL_TOTAL_MAX": "180",
    })
    assert result.total_max_connections == 180
    with pytest.raises(ValueError, match="exceeds deployment ceiling"):
        validate_aggregate_pool_budget(environ={
            "AI00_WEB_WORKERS": "2",
            "AI00_DB_POOL_TOTAL_MAX": "180",
        })


def test_resource_checker_never_reads_or_prints_database_urls():
    source = (ROOT / "backend/scripts/check_runtime_resource_budget.py").read_text(encoding="utf-8")
    assert "DB_URL" not in source
    assert "password" not in source.lower()
