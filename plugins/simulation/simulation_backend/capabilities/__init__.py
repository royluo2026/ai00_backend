"""Official Simulation Capability provider."""
from __future__ import annotations

from typing import Any

from backend.domain_ports.resource_authorization import resource_authorizers
from .models import specs
from .environment_composition import EnvironmentCompositionProvider, specs as composition_specs
from .capture_runs import CaptureRunProvider, specs as capture_specs
from .capture_runs import default_provider as default_capture_provider
from .models import repository as legacy_repository
from .environment_composition import repository as environment_repository
from .document_snapshots import default_workflow as default_snapshot_workflow
from .document_snapshots import specs as document_snapshot_specs
from .connector_outcomes import ConnectorOutcomeProvider, specs as connector_outcome_specs
from .provider import register


def _authorize_document_snapshot(resource_id, identity) -> bool:
    user_gid = identity.actor.user_id
    return bool(user_gid) and default_snapshot_workflow.repository.can_read_request(
        resource_id,
        user_gid=user_gid or "",
        team_gid=identity.tenant.tenant_id,
    )


def _identity_scope(identity):
    return {
        "user_gid": identity.actor.user_id or "",
        "team_gid": identity.tenant.tenant_id,
    }


def _authorize_environment(resource_id, identity) -> bool:
    scope = _identity_scope(identity)
    return bool(scope["user_gid"]) and (
        environment_repository.can_read_environment(resource_id, **scope)
        or legacy_repository.can_read_environment(resource_id, **scope)
    )


def _authorize_capture_run(resource_id, identity) -> bool:
    scope = _identity_scope(identity)
    return bool(scope["user_gid"]) and default_capture_provider.workflow.repository.can_read_capture_run(
        resource_id, **scope,
    )


def _authorize_materialization_run(resource_id, identity) -> bool:
    scope = _identity_scope(identity)
    return bool(scope["user_gid"]) and default_capture_provider.workflow.repository.can_read_materialization_run(
        resource_id, **scope,
    )


def _authorize_parameter_set(resource_id, identity) -> bool:
    scope = _identity_scope(identity)
    return bool(scope["user_gid"]) and legacy_repository.can_read_parameter_set(resource_id, **scope)


def _authorize_profile(resource_id, identity) -> bool:
    scope = _identity_scope(identity)
    return bool(scope["user_gid"]) and legacy_repository.can_read_profile(resource_id, **scope)


def _authorize_run(resource_id, identity) -> bool:
    scope = _identity_scope(identity)
    return bool(scope["user_gid"]) and legacy_repository.can_read_run(resource_id, **scope)


def register_capabilities(
    registry: Any, *, composition_provider: EnvironmentCompositionProvider | None = None,
    capture_provider: CaptureRunProvider | None = None,
) -> None:
    resource_authorizers.register("simulation-document-snapshot", _authorize_document_snapshot)
    resource_authorizers.register("simulation-environment", _authorize_environment)
    resource_authorizers.register("simulation-capture-run", _authorize_capture_run)
    resource_authorizers.register("simulation-materialization-run", _authorize_materialization_run)
    resource_authorizers.register("simulation-parameter-set", _authorize_parameter_set)
    resource_authorizers.register("simulation-profile", _authorize_profile)
    resource_authorizers.register("simulation-run", _authorize_run)
    selected_capture_provider = capture_provider or default_capture_provider
    for spec, handler in specs():
        register(registry, spec, handler)
    for spec, handler in composition_specs(composition_provider) if composition_provider else composition_specs():
        register(registry, spec, handler)
    for spec, handler in capture_specs(selected_capture_provider):
        register(registry, spec, handler)
    for spec, handler in document_snapshot_specs():
        register(registry, spec, handler)
    outcome_provider = ConnectorOutcomeProvider(
        selected_capture_provider.workflow, default_snapshot_workflow,
    )
    for spec, handler in connector_outcome_specs(outcome_provider):
        register(registry, spec, handler)


__all__ = ["register_capabilities"]
