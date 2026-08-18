from pathlib import Path

import pytest

from backend.capability_governance_test.config import GovernanceSettings
from backend.config import get_governance_settings


def test_governance_settings_requires_test_governance_profile():
    with pytest.raises(RuntimeError, match="AI00_DEPLOYMENT_PROFILE=test-governance"):
        GovernanceSettings.from_environ({"AI00_DEPLOYMENT_PROFILE": "local"})


def test_governance_settings_resolves_repo_and_redacts_database_values():
    settings = GovernanceSettings.from_environ(
        {
            "AI00_DEPLOYMENT_PROFILE": "test-governance",
            "AI00_BASE_DDL_DB_URL": "mysql://user:secret@db.internal:3306/governance",
        }
    )

    assert settings.repository_root.is_dir()
    assert all(not Path(root).is_absolute() for root in settings.allowlisted_relative_roots)
    assert isinstance(settings.allowlisted_relative_roots, tuple)
    assert "mysql://" not in repr(settings)
    assert "secret" not in repr(settings)


def test_governance_allowlisted_roots_are_immutable():
    settings = GovernanceSettings.from_environ(
        {"AI00_DEPLOYMENT_PROFILE": "test-governance"}
    )

    with pytest.raises((AttributeError, TypeError)):
        settings.allowlisted_relative_roots += ("outside",)


def test_backend_config_uses_the_fail_closed_governance_settings():
    settings = get_governance_settings(
        {"AI00_DEPLOYMENT_PROFILE": "test-governance"}
    )

    assert isinstance(settings, GovernanceSettings)
