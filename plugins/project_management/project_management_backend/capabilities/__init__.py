"""Project Management-owned Capability provider entry point."""
from __future__ import annotations

from typing import Any

from .projects import register_project_capabilities
from .reviewed import register_reviewed_capabilities
from ..application.outcomes import project_outcome_port
from ..application.service import ProjectManagementApplication
from ..infrastructure.repository import ProjectManagementRepository


def register_capabilities(registry: Any) -> None:
    if project_outcome_port.provider is None:
        project_outcome_port.bind(
            ProjectManagementApplication(ProjectManagementRepository())
        )
    register_project_capabilities(registry)
    register_reviewed_capabilities(registry)
