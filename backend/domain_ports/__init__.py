"""Stable cross-domain application ports; implementations remain domain-owned."""

from .craft import BopVersionRef, CraftChangeRef, CraftCommandPort, CraftQueryPort, PbomSnapshotRef
from .project_management import ProjectManagementDomainPort, ProjectRef
from .knowledge import KnowledgeOperationsPort
from .operations import OperationsPortRegistry, OperationsProvider, operations_registry

__all__ = [
    "BopVersionRef", "CraftChangeRef", "CraftCommandPort", "CraftQueryPort",
    "KnowledgeOperationsPort", "OperationsPortRegistry", "OperationsProvider",
    "PbomSnapshotRef", "ProjectManagementDomainPort", "ProjectRef", "operations_registry",
]
