"""Stable cross-domain application ports; implementations remain domain-owned."""

from .craft import BopVersionRef, CraftChangeRef, CraftCommandPort, CraftQueryPort, PbomSnapshotRef
from .project_management import ProjectManagementDomainPort, ProjectRef

__all__ = [
    "BopVersionRef", "CraftChangeRef", "CraftCommandPort", "CraftQueryPort",
    "PbomSnapshotRef", "ProjectManagementDomainPort", "ProjectRef",
]
