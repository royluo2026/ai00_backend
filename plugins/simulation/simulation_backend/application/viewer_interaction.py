"""Issue bounded grants; interactive execution never calls this per click."""
from backend.contracts.viewer_interaction_v1 import AuthorizeRequest, PROTOCOL
from backend.contracts.connector_execution_plan_v2 import canonicalize_v2
from backend.capability_v2.business_definition import business_definition_hash
import hashlib


OPERATION_CAPABILITIES = {
    'vismockup.node.visibility.change@1': ('simulation.vismockup.node.visibility.change.apply', 1),
    'vismockup.node.selection.change@1': ('simulation.vismockup.node.selection.change.apply', 1),
}


AUTHORIZATION_ISSUERS = frozenset({('simulation.viewer.interaction.authorize', 1),
    ('simulation.environment.online_source.live_document.bind', 3),
    ('simulation.environment.cache_source.live_document.bind', 1)})


def catalog_binding(context, operations, *, issuer=('simulation.viewer.interaction.authorize', 1)):
    from backend.capability_v2.gateway import get_default_gateway
    try:
        release_id = context.catalog_release
        if not context.outcome_operation_id:
            raise ValueError('missing operation')
        release = get_default_gateway().catalog(release_id)
        if release.release_id != release_id:
            raise ValueError('release mismatch')
        if issuer not in AUTHORIZATION_ISSUERS:
            raise ValueError('unsupported issuer')
        authorization = release.descriptor(*issuer)
        if (authorization is None or authorization.capability_version_gid != context.capability_version_gid
            or business_definition_hash(authorization) != context.business_definition_hash):
            raise ValueError('authorization mismatch')
        provider = next(p for p in release.provider_artifacts if p.plugin_id == 'official.simulation')
        bindings = []
        for operation in operations:
            descriptor = release.descriptor(*OPERATION_CAPABILITIES[operation['id']])
            if (descriptor is None or not descriptor.capability_version_gid
                or descriptor.provider_ref != authorization.provider_ref
                or descriptor.owner_domain != authorization.owner_domain):
                raise ValueError('operation binding missing')
            bindings.append(dict(operation_id=operation['id'], contract_hash=operation['contract_hash'],
                descriptor=descriptor.model_dump(mode='json'), business_definition_hash=business_definition_hash(descriptor)))
        return dict(catalog_release=release_id, catalog_hash=release.catalog_hash,
            authorization_descriptor=authorization.model_dump(mode='json'),
            authorization_business_definition_hash=business_definition_hash(authorization),
            provider_artifact=provider.model_dump(mode='json'), operation_bindings=bindings,
            authorization_operation_id=context.outcome_operation_id)
    except (AttributeError, LookupError, ValueError, StopIteration) as exc:
        raise ValueError('interaction_catalog_binding_unavailable') from exc


def authorize_interaction(context, request, repository, signer, now, *, transaction=None,
                          issuer=('simulation.viewer.interaction.authorize', 1)):
    if context.source != 'web' or not context.user_gid or not context.team_gid:
        raise ValueError('interaction_scope_denied')
    request = AuthorizeRequest.model_validate(request)
    if signer is None:
        raise ValueError('interaction_signer_unavailable')
    # Reuse the established Adapter operation contracts; do not create a second
    # set of hashes that could silently drift from signed-plan execution.
    from ..capabilities.connector_runtime import DIRECT_VISMOCKUP_OPERATIONS
    operations = [dict(id=op, contract_hash=digest) for op, digest in
                  (DIRECT_VISMOCKUP_OPERATIONS[name] for name in ('node_visibility', 'node_selection'))]
    proof = catalog_binding(context, operations, issuer=issuer)
    with repository.authorize_scope(context, request, now, evidence=proof, transaction=transaction) as scope:
        grant = signer.sign_interaction_grant(dict(**scope, protocol=PROTOCOL,
            operations=operations, policy_version='viewer-interaction-v1', audience='ai00.connector.viewer-interaction'))
        proof['signed_grant'] = grant.model_dump(mode='json')
        proof['signed_grant_digest'] = 'sha256:' + hashlib.sha256(canonicalize_v2(grant)).hexdigest()
        return grant
