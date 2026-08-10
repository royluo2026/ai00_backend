from pathlib import Path

from backend.routers.capabilities import router


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_only_versioned_capability_route_is_public():
    paths = {route.path for route in router.routes}

    assert not any(path.startswith("/api/capabilities") for path in paths)
    assert any(path.startswith("/api/v1/capabilities") for path in paths)


def test_legacy_capability_registry_modules_are_absent():
    assert not (REPO_ROOT / "backend/capabilities/models.py").exists()
    assert not (REPO_ROOT / "backend/capabilities/registry.py").exists()
    assert (REPO_ROOT / "backend/capabilities/models_next.py").exists()
    assert (REPO_ROOT / "backend/capabilities/registry_next.py").exists()


def test_retirement_runbook_records_safe_observation_and_rollback_boundary():
    runbook = (REPO_ROOT / "docs/migrations/capability-v1-retirement.md").read_text(encoding="utf-8")

    for required in (
        "Last observed",
        "Replacement Capability",
        "Owner",
        "Rollback",
        "Do not delete",
    ):
        assert required in runbook
