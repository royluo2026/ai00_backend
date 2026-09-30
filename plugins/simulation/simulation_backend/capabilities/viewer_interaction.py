"""Owner-only low-frequency authorization for the local viewer channel."""
from datetime import UTC, datetime

from backend.capability_v2.provider_contracts import CapabilityBusinessError, CapabilitySpec, CapabilityRisk
from backend.contracts.viewer_interaction_v1 import ScopeRequest, AuthorizeRequest, SignedGrant
from ..application.viewer_interaction import authorize_interaction
from ..data.viewer_interaction_repository import ViewerInteractionRepository
from .live_documents import LiveDocumentProvider, obj, KEY


class ViewerInteractionProvider:
    def __init__(self, repository, signer, *, clock=lambda: datetime.now(UTC)):
        self.repository, self.signer, self.clock = repository, signer, clock

    def scope_get(self, payload, context):
        try:
            if context.source != 'web' or not context.user_gid or not context.team_gid:
                raise ValueError('interaction_scope_denied')
            request = ScopeRequest.model_validate(payload)
            with self.repository.authorize_scope(context, request, self.clock(), allocate=False) as scope:
                result = dict(scope)
            return LiveDocumentProvider._output(result)
        except ValueError as exc:
            code = 'interaction_source_unassociated' if str(exc) == 'interaction_source_unassociated' else 'interaction_scope_denied'
            raise CapabilityBusinessError(code, str(exc)) from exc

    def authorize(self, payload, context):
        try:
            result = authorize_interaction(context, payload, self.repository, self.signer, self.clock())
            return LiveDocumentProvider._output(result.model_dump(mode='json'))
        except ValueError as exc:
            code = str(exc) if str(exc).startswith('interaction_') else 'interaction_authorization_rejected'
            raise CapabilityBusinessError(code, code) from exc


def register_viewer_interaction_capabilities(registry, control_plane):
    from .provider import register
    provider = ViewerInteractionProvider(ViewerInteractionRepository(), control_plane.plan_signer, clock=control_plane.clock)
    for suffix, schema, output, handler, risk in (
        ('scope.get', ScopeRequest, obj(dict(source_association_id=KEY)), provider.scope_get, CapabilityRisk.READ),
        ('authorize', AuthorizeRequest, SignedGrant.model_json_schema(), provider.authorize, CapabilityRisk.WRITE),
    ):
        register(registry, CapabilitySpec(id='simulation.viewer.interaction.' + suffix, version=1, owner='simulation',
            description='Resolve or authorize an owned current-open viewer source association.',
            use_when='The authenticated owner opens or renews a local interactive session.',
            do_not_use_when='There is no verified current-open binding or the caller is automated.',
            risk=risk, confirmation='none', permissions=('simulation.use',), input_schema=schema.model_json_schema(),
            output_schema=output, tags=('simulation', 'viewer_interaction', 'experimental')), handler)
