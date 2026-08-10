"""Stable cross-domain application ports; implementations remain domain-owned."""

from .project_management import ProjectManagementDomainPort, ProjectRef

__all__ = ["ProjectManagementDomainPort", "ProjectRef"]
