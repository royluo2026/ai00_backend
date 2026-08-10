"""Stable cross-domain application ports; implementations remain domain-owned."""

from .craft import BopVersionRef, CraftChangeRef, CraftCommandPort, CraftQueryPort, PbomSnapshotRef
from .digital_model import ComponentRef, DigitalModelQueryPort, ModelRef, ModelSnapshotRef, ModelVersionRef
from .project_management import ProjectManagementDomainPort, ProjectRef
from .knowledge import KnowledgeOperationsPort
from .operations import OperationsPortRegistry, OperationsProvider, operations_registry

__all__ = [
    "BopVersionRef", "ComponentRef", "CraftChangeRef", "CraftCommandPort", "CraftQueryPort",
    "DigitalModelQueryPort", "ModelRef", "ModelSnapshotRef", "ModelVersionRef",
    "KnowledgeOperationsPort", "OperationsPortRegistry", "OperationsProvider",
    "PbomSnapshotRef", "ProjectManagementDomainPort", "ProjectRef", "operations_registry",
]
