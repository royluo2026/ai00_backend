from pathlib import Path
import pytest

from plugins.digital_model.digital_model_backend.application.versions import ModelVersionService
from plugins.digital_model.digital_model_backend.domain.versions import ImmutableVersionError, ModelVersion

def test_published_model_version_is_immutable():
    version = ModelVersion(ref="model:M1@V1", artifact_ref="artifact:A1", project_ref="project:P1", published=True, components=("component:C1",))
    service = ModelVersionService([version])
    with pytest.raises(ImmutableVersionError):
        service.replace_component(version.ref, "component:C2")

def test_domain_has_independent_migration_and_credential():
    root = Path(__file__).parents[3]
    sql = (root / "backend/db/migrations/domains/digital_model/0001_digital_model.sql").read_text(encoding="utf-8")
    assert "workmanship_model_versions" in sql
    assert "workmanship_proj_" not in sql
