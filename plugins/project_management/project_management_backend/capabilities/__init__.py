"""Project Management-owned Capability provider entry point."""
from __future__ import annotations

from typing import Any

from .projects import register_project_capabilities
from .desktop_actions import register_desktop_capabilities
from .reviewed import register_reviewed_capabilities, register_desktop_v2_capabilities
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
    register_desktop_v2_capabilities(registry)
    register_desktop_capabilities(registry)
    from .desktop_attachments import register_attachments
    register_attachments(registry)
